import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcvideo import cli  # noqa: E402
from mcvideo.convert import namespace_for, rects  # noqa: E402
from mcvideo.tools import ToolError, find_tool  # noqa: E402

try:
    FFMPEG = find_tool("ffmpeg")
    find_tool("ffprobe")
except ToolError:
    FFMPEG = None


class PureTests(unittest.TestCase):
    def test_namespace(self):
        self.assertEqual(namespace_for("My Clip!"), "my_clip")
        self.assertEqual(namespace_for("a" * 40), "a" * 14)
        self.assertEqual(namespace_for("!!!"), "video")

    def test_rects_merges_runs_and_rows(self):
        changed = {(r, c): "x" for r in range(2) for c in range(1, 4)}  # a 3x2 block
        changed[(0, 6)] = "y"
        got = {(k, tuple(v)) for k, v in rects(changed, 8, 4)}
        self.assertEqual(got, {((1, 3, "x"), (0, 1)), ((6, 6, "y"), (0, 0))})

    def test_rects_does_not_merge_different_colours(self):
        changed = {(0, 0): "a", (0, 1): "b"}
        self.assertEqual(len(rects(changed, 4, 1)), 2)

    def test_rects_covers_every_pixel_exactly_once(self):
        import random
        random.seed(1)
        changed = {(r, c): random.choice("abc") for r in range(12) for c in range(16) if random.random() < 0.6}
        seen = {}
        for (c0, c1, col), (r0, r1) in rects(changed, 16, 12):
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    self.assertNotIn((r, c), seen)
                    self.assertEqual(changed[(r, c)], col)
                    seen[(r, c)] = col
        self.assertEqual(len(seen), len(changed))


@unittest.skipUnless(FFMPEG, "ffmpeg / ffprobe not available")
class PackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = os.path.join(cls.tmp.name, "clip.mp4")
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", cls.clip], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cli(self, name, *extra):
        out = os.path.join(self.tmp.name, name)
        self.assertEqual(cli.main([self.clip, "--name", name, "--out", out, *extra]), 0)
        return zipfile.ZipFile(os.path.join(out, f"{name}_data.zip")), out

    def check_structure(self, z, ns, frames):
        names = set(z.namelist())
        pack = json.loads(z.read("pack.mcmeta"))["pack"]
        self.assertEqual(pack["min_format"], pack["max_format"])
        for fn in ("start", "stop", "clear", "cleanup"):
            self.assertIn(f"data/{ns}/function/{fn}.mcfunction", names)
        for i in range(frames):
            self.assertIn(f"data/{ns}/function/f/{i}.mcfunction", names)
            self.assertIn(f"data/{ns}/function/d/{i}.mcfunction", names)
        self.assertNotIn(f"data/{ns}/function/f/{frames}.mcfunction", names)
        # every referenced function exists, nothing is left unpatched
        for n in names:
            if n.endswith(".mcfunction"):
                text = z.read(n).decode()
                self.assertNotIn("@@", text)
                for ref in re.findall(rf"function {ns}:([a-z0-9_/]+)", text):
                    self.assertIn(f"data/{ns}/function/{ref}.mcfunction", names, f"{n} -> {ref}")
        # the chain runs to the end and then switches itself off
        self.assertIn(f"scoreboard players set #run {ns} 0", z.read(f"data/{ns}/function/f/{frames - 1}.mcfunction").decode())
        self.assertIn(f"schedule function {ns}:f/1 2t", z.read(f"data/{ns}/function/f/0.mcfunction").decode())

    def test_block_mode(self):
        z, out = self.run_cli("tblock", "--mode", "block", "--palette", "plus", "--width", "32")
        self.check_structure(z, "tblock", 20)
        width, height = 32, 24
        box = re.compile(r"fill \^(-?\d+) \^(-?\d+) \^ \^(-?\d+) \^(-?\d+) \^ minecraft:(\w+) replace minecraft:(\w+)$")
        count = 0
        for i in range(20):
            for line in z.read(f"data/tblock/function/d/{i}.mcfunction").decode().splitlines():
                m = box.match(line)
                self.assertIsNotNone(m, line)
                x0, y0, x1, y1, new, old = m.groups()
                self.assertNotEqual(new, old)  # only real changes are drawn
                for x in (int(x0), int(x1)):
                    self.assertTrue(-(width // 2 - 1) <= x <= width // 2, line)
                for y in (int(y0), int(y1)):
                    self.assertTrue(-(height // 2 - 1) <= y <= height // 2, line)
                count += 1
        self.assertGreater(count, 0)
        start = z.read("data/tblock/function/start.mcfunction").decode()
        self.assertIn("replace minecraft:air", start)  # the background only ever fills air
        self.assertIn("matches ..", start)  # build-height clamp
        self.assertIn("playsound tblock:video", start)
        self.assertTrue(os.path.exists(os.path.join(out, "tblock_audio.zip")))

    def test_particle_mode(self):
        z, out = self.run_cli("tpart", "--mode", "particle", "--width", "16")
        self.check_structure(z, "tpart", 20)
        self.assertIn("data/tpart/function/lights_on.mcfunction", z.namelist())
        d = z.read("data/tpart/function/d/5.mcfunction").decode()
        self.assertRegex(d, r"particle dust\{color:\[[\d.,]+\],scale:0\.4\} \^-?[\d.]+ \^-?[\d.]+ \^ 0 0 0 0 1 force")

    def test_no_audio(self):
        z, out = self.run_cli("tquiet", "--no-audio", "--palette", "bw", "--width", "16")
        self.assertFalse(os.path.exists(os.path.join(out, "tquiet_audio.zip")))
        self.assertNotIn("playsound", z.read("data/tquiet/function/start.mcfunction").decode())

    def test_gaze_anchor_and_lift(self):
        z, _ = self.run_cli("tgaze", "--palette", "bw", "--width", "16", "--anchor", "gaze", "--lift", "5")
        self.assertIn("anchored eyes", z.read("data/tgaze/function/start.mcfunction").decode())

    def test_preview_writes_png_only(self):
        out = os.path.join(self.tmp.name, "tprev")
        self.assertEqual(cli.main([self.clip, "--name", "tprev", "--out", out, "--palette", "plus", "--width", "32",
                                   "--preview", "0.5"]), 0)
        self.assertTrue(os.path.exists(os.path.join(out, "preview_plus.png")))
        self.assertFalse(os.path.exists(os.path.join(out, "tprev_data.zip")))

    def test_errors_are_reported_not_raised(self):
        self.assertEqual(cli.main([os.path.join(self.tmp.name, "missing.mp4")]), 1)
        self.assertEqual(cli.main([self.clip, "--name", "tpast", "--out", os.path.join(self.tmp.name, "tpast"),
                                   "--ss", "60"]), 1)


if __name__ == "__main__":
    unittest.main()
