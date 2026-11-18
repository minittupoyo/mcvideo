"""Core conversion: video -> datapack (+ audio resource pack).

How the generated pack works (see docs/how-it-works.md):

* ``<ns>:start`` summons a *marker* entity in front of the player and every frame is drawn relative to it with local
  coordinates (``^left ^up ^forward``). Scheduled functions lose their position, so this is what makes the screen
  placeable anywhere.
* Frame ``i`` is two functions: ``f/i`` (run at the marker, schedule the next frame) and ``d/i`` (the drawing).
* Block mode only draws the pixels that changed since the previous frame. With ``--method fill`` each
  change is a ``fill ... replace <old>`` so terrain and other builds are never touched. With ``--method structure`` (the default)
  each frame's changes are one structure file (``data/<ns>/structure/d/i.nbt``) placed by ``place template``, which
  keeps the function files tiny but overwrites whatever is in the changed cells. Particle mode re-emits all lit
  pixels each frame.
"""
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from typing import Optional

from . import nbt
from .palette import PaletteError, build_palette
from .tools import ToolError, find_tool, probe_video


class ConvertError(RuntimeError):
    """A user-facing error (bad input, missing tool, ...)."""


@dataclass
class Result:
    namespace: str
    out_dir: str
    data_zip: Optional[str] = None
    audio_zip: Optional[str] = None
    preview: Optional[str] = None
    frames: int = 0
    commands: int = 0


def namespace_for(name):
    """A datapack namespace from a free-form name: lower case ``[a-z0-9_]``, at most 14 characters."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower())[:14].strip("_") or "video"


def rects(changed, width, height):
    """Merge changed pixels into rectangles.

    ``changed`` maps ``(row, col)`` to any hashable "colour" (here ``(new, old)``). Pixels are first joined into
    horizontal runs of equal colour, then runs with the same extent and colour in consecutive rows are stacked.
    Returns ``[((col0, col1, colour), [row0, row1]), ...]``.
    """
    out, open_runs = [], {}
    for r in range(height):
        runs, c = [], 0
        while c < width:
            col = changed.get((r, c))
            if col is None:
                c += 1
                continue
            c1 = c
            while c1 + 1 < width and changed.get((r, c1 + 1)) == col:
                c1 += 1
            runs.append((c, c1, col))
            c = c1 + 1
        keys = set(runs)
        for k in list(open_runs):
            if k not in keys:
                out.append((k, open_runs.pop(k)))
        for k in runs:
            if k in open_runs:
                open_runs[k][1] = r
            else:
                open_runs[k] = [r, r]
    out.extend(open_runs.items())
    return out


def _trim_args(a):
    args = []
    if a.ss:
        args += ["-ss", str(a.ss)]
    if a.seconds:
        args += ["-t", str(a.seconds)]
    return args


def convert(a, log=print):
    """Convert ``a.input`` according to the argparse namespace ``a`` (see ``cli.build_parser``)."""
    if not os.path.exists(a.input):
        raise ConvertError(f"input not found: {a.input}")
    try:
        ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
        vw, vh, source_has_audio = probe_video(ffprobe, a.input)
    except ToolError as e:
        raise ConvertError(str(e)) from e

    NS = namespace_for(a.name or os.path.splitext(os.path.basename(a.input))[0])
    OUT = a.out or os.path.join("build", NS)
    os.makedirs(OUT, exist_ok=True)
    FPS = a.fps
    TICKS = 20 // FPS
    BLOCK = a.mode == "block"
    if a.method == "structure" and not BLOCK:
        raise ConvertError("--method structure only works with --mode block")
    STRUCT = BLOCK and a.method != "fill"  # the default (None) is structure in block mode
    TAG = f"{NS}_o"  # the marker's tag
    W = a.width or (128 if BLOCK else 64)
    H = a.height or max(1, round(W * vh / vw))
    has_audio = source_has_audio and not a.no_audio
    DIST = a.dist if a.dist is not None else (100 if BLOCK else 30)
    result = Result(namespace=NS, out_dir=OUT)
    log(f"namespace '{NS}' | {a.mode} | {W}x{H} @ {FPS}fps | audio: {has_audio}")

    def lx(c):  # integer "left" offset of column c (the marker sits on a block centre in block mode)
        return W // 2 - c

    def ly(r):  # integer "up" offset of row r
        return H // 2 - r

    # structure method: the wall is a W x H x 1 template whose x axis points "left" (column c is x = W-1-c) and whose
    # y axis points up; it is rotated to the marker's snapped facing with `place template`'s rotation argument.
    ROTATIONS = ["none", "clockwise_90", "180", "counterclockwise_90"]  # facing south, west, north, east

    def structure(pixels):
        """NBT bytes of a structure holding ``pixels`` (``{row * W + col: palette index}``); other cells stay empty."""
        used = sorted(set(pixels.values()))
        index = {p: i for i, p in enumerate(used)}
        blocks = []
        for k, v in sorted(pixels.items()):
            r, c = divmod(k, W)
            blocks.append({"pos": [nbt.Int(W - 1 - c), nbt.Int(H - 1 - r), nbt.Int(0)], "state": nbt.Int(index[v])})
        return nbt.dumps({"DataVersion": nbt.Int(a.nbt_data_version),
                          "size": [nbt.Int(W), nbt.Int(H), nbt.Int(1)],
                          "palette": [{"Name": f"minecraft:{pal[p][1]}"} for p in used],
                          "blocks": blocks, "entities": []})

    def place_template(name):
        return [f"execute if score #rot {NS} matches {k} run place template {NS}:{name} "
                f"^{lx(W - 1)} ^{ly(H - 1)} ^ {rot}\n" for k, rot in enumerate(ROTATIONS)]

    # ------------------------------------------------------------ decoding
    cmd = [ffmpeg, "-v", "error"] + _trim_args(a) + ["-i", a.input]
    vf = f"fps={FPS},scale={W}:{H}:flags=area"
    if BLOCK:
        try:
            pal = build_palette(a.palette)
        except PaletteError as e:
            raise ConvertError(str(e)) from e
        log(f"palette '{a.palette}': {len(pal)} blocks")
        pal_path = os.path.join(OUT, "_palette.rgb")
        with open(pal_path, "wb") as f:  # paletteuse needs exactly 256 entries
            for k in range(256):
                f.write(bytes(pal[k][0] if k < len(pal) else pal[0][0]))
        if a.preview is not None:
            png = os.path.join(OUT, f"preview_{a.palette}.png")
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-ss", str(a.preview), "-i", a.input,
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "16x16", "-i", pal_path,
                 "-filter_complex", f"[0:v]scale={W}:{H}:flags=area[v];[v][1:v]paletteuse=dither={a.dither},"
                                    f"format=rgb24,scale=iw*6:ih*6:flags=neighbor",
                 "-frames:v", "1", png], check=True)
            result.preview = os.path.abspath(png)
            log("preview:", result.preview)
            return result
        cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "16x16", "-i", pal_path,
                "-filter_complex", f"[0:v]{vf}[v];[v][1:v]paletteuse=dither={a.dither},format=rgb24"]
        table = bytearray(256)  # red value -> palette index
        for k, (rgb, _) in enumerate(pal):
            table[rgb[0]] = k
        table = bytes(table)
    else:
        cmd += ["-vf", vf, "-pix_fmt", "rgb24"]
    cmd += ["-f", "rawvideo", "-"]
    frame_bytes = W * H * 3

    # ------------------------------------------------------------ where the marker goes
    # an `execute` fragment, run `at @s`
    if a.anchor == "gaze":
        place = f"anchored eyes positioned ^ ^ ^{DIST} positioned ~ ~{a.lift} ~"
    else:  # the bottom edge at the player's feet level, DIST blocks ahead on the horizontal
        up = (H - 1 - H // 2) if BLOCK else (H - 1) / 2 * a.cell
        place = f"rotated ~ 0 positioned ^ ^ ^{DIST} positioned ~ ~{up + a.lift} ~"

    def start_text(snap_lines, place_lines):
        lines = [
            f"execute at @n[type=marker,tag={TAG}] run function {NS}:cleanup\n",
            f"kill @e[type=marker,tag={TAG}]\n",
            f"scoreboard objectives add {NS} dummy\n",
            f"scoreboard players set #run {NS} 1\n",
            f"execute at @s {place} run summon marker ~ ~ ~ {{Tags:[\"{TAG}\"]}}\n",
        ] + snap_lines + place_lines
        if has_audio:
            lines.append(f"execute as @a at @s run playsound {NS}:video master @s ~ ~ ~ 1 1 1\n")
        lines.append(f"function {NS}:f/0\n")
        return "".join(lines)

    data_zip = os.path.join(OUT, f"{NS}_data.zip")
    zf = zipfile.ZipFile(data_zip, "w", zipfile.ZIP_DEFLATED)

    def put(name, text):
        zf.writestr(name, text)

    def put_frame_driver(i, last):
        sched = (f"scoreboard players set #run {NS} 0" if last else
                 f"execute if score #run {NS} matches 1 run schedule function {NS}:f/{i + 1} {TICKS}t")
        put(f"data/{NS}/function/f/{i}.mcfunction",
            f"execute at @n[type=marker,tag={TAG}] run function {NS}:d/{i}\n{sched}\n")

    # ------------------------------------------------------------ frames
    n = 0
    total = 0
    prev = bytearray(W * H)  # block mode: palette indices; 0 = background (painted at start)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            if BLOCK:
                cur = buf[0::3].translate(table)
                changed = {}
                for k in range(W * H):
                    v = cur[k]
                    if v != prev[k]:
                        changed[(k // W, k % W)] = (v, prev[k])  # (new colour, old colour)
                        prev[k] = v
                if STRUCT:  # one template per frame, holding only the changed cells
                    lines = []
                    if changed:
                        put(f"data/{NS}/structure/d/{n}.nbt",
                            structure({r * W + c: new for (r, c), (new, _) in changed.items()}))
                        lines = [x.rstrip("\n") for x in place_template(f"d/{n}")]
                else:  # exact "old -> new" replace: no block tag needed, terrain is never touched
                    lines = [f"fill ^{lx(c0)} ^{ly(r0)} ^ ^{lx(c1)} ^{ly(r1)} ^ "
                             f"minecraft:{pal[new][1]} replace minecraft:{pal[old][1]}"
                             for (c0, c1, (new, old)), (r0, r1) in rects(changed, W, H)]
            else:
                lines = []
                for k in range(W * H):
                    r8, g8, b8 = buf[3 * k], buf[3 * k + 1], buf[3 * k + 2]
                    lum = (r8 * 299 + g8 * 587 + b8 * 114) // 1000
                    if (lum < a.thr) if a.invert else (lum >= a.thr):
                        r, c = divmod(k, W)
                        left, upv = ((W - 1) / 2 - c) * a.cell, ((H - 1) / 2 - r) * a.cell
                        if a.particle == "dust":
                            if a.mono or a.invert:
                                col = "1.00,1.00,1.00"
                            else:  # lift very dark colours so they stay visible
                                m = max(r8, g8, b8, 1)
                                f = max(1.0, 160 / m)
                                col = (f"{min(1.0, r8 * f / 255):.2f},{min(1.0, g8 * f / 255):.2f},"
                                       f"{min(1.0, b8 * f / 255):.2f}")
                            pname = f"dust{{color:[{col}],scale:{a.scale}}}"
                        else:
                            pname = f"minecraft:{a.particle}"
                        lines.append(f"particle {pname} ^{left:.2f} ^{upv:.2f} ^ 0 0 0 0 1 force")
            total += len(lines)
            put(f"data/{NS}/function/d/{n}.mcfunction", "\n".join(lines) + "\n")
            if n > 0:  # frame n-1 is now known not to be the last one
                put_frame_driver(n - 1, last=False)
            n += 1
            if n % 500 == 0:
                log(f"  {n} frames...")
    finally:
        proc.stdout.close()
        proc.wait()
    if n == 0:
        zf.close()
        os.remove(data_zip)
        raise ConvertError("no frames decoded (is the input a video? is --ss past the end?)")
    put_frame_driver(n - 1, last=True)
    log(f"{n} frames ({n / FPS:.1f}s), {total} commands, {total / n:.0f}/frame avg")

    # ------------------------------------------------------------ control functions
    if BLOCK:
        box = f"^{lx(0)} ^{ly(0)} ^ ^{lx(W - 1)} ^{ly(H - 1)} ^"
        put(f"data/{NS}/function/cleanup.mcfunction",
            "".join(f"fill {box} minecraft:air replace minecraft:{b}\n" for _, b in pal))
        snap = f"execute as @n[type=marker,tag={TAG}] at @s run tp @s ~ ~ ~ {{yaw}} 0"
        # fill fails ("out of this world") if a corner leaves the build height: keep the whole wall inside it
        lo = a.min_y + (H - 1 - H // 2)  # lowest marker block y that keeps the bottom row inside
        hi = a.max_y - H // 2  # highest marker block y that keeps the top row inside
        marker = f"@n[type=marker,tag={TAG}]"
        snap_lines = [
            f"execute as {marker} at @s align xyz run tp @s ~0.5 ~0.5 ~0.5\n",
            f"execute store result score #y {NS} run data get entity {marker} Pos[1]\n",
            f"execute if score #y {NS} matches ..{lo + 1} as {marker} at @s run tp @s ~ {lo + 2}.5 ~\n",
            f"execute if score #y {NS} matches {hi - 1}.. as {marker} at @s run tp @s ~ {hi - 2}.5 ~\n",
            # the wall is axis aligned: snap the marker's facing to N / E / S / W
        ]
        for cond, yaw, k in [("-45..45", 0, 0), ("45..135", 90, 1), ("135..180", 180, 2), ("-180..-135", 180, 2),
                             ("-135..-45", -90, 3)]:
            snap_lines.append(f"execute if entity @s[y_rotation={cond}] run {snap.format(yaw=yaw)}\n")
            if STRUCT:  # remember the facing as a rotation for `place template`
                snap_lines.append(f"execute if entity @s[y_rotation={cond}] run scoreboard players set #rot {NS} {k}\n")
        if STRUCT:
            put(f"data/{NS}/structure/bg.nbt", structure({k: 0 for k in range(W * H)}))
            place_lines = [f"execute at {marker} run {x}" for x in place_template("bg")]
        else:
            place_lines = [f"execute at {marker} run fill {box} minecraft:{pal[0][1]} replace minecraft:air\n"]
        put(f"data/{NS}/function/start.mcfunction", start_text(snap_lines, place_lines))
    else:
        half_w, half_h = W * a.cell / 2, H * a.cell / 2
        lefts = [round(-half_w + (k + 0.5) * half_w * 2 / 5, 1) for k in range(5)]
        ups = [round(-half_h + (k + 0.5) * half_h * 2 / 4, 1) for k in range(4)]
        grid = [(lf, u) for lf in lefts for u in ups]
        lights = not a.no_lights and a.particle == "dust"
        put(f"data/{NS}/function/lights_on.mcfunction",
            "".join(f"setblock ^{lf} ^{u} ^ minecraft:light[level=15]\n" for lf, u in grid))
        put(f"data/{NS}/function/cleanup.mcfunction",
            "".join(f"fill ^{lf} ^{u} ^ ^{lf} ^{u} ^ minecraft:air replace minecraft:light\n" for lf, u in grid))
        # particle screens follow the exact yaw (the pitch is flattened)
        rot = " rotated as @s" if a.anchor == "gaze" else ""
        snap_lines = [f"execute at @s {place}{rot} run tp @n[type=marker,tag={TAG}] ~ ~ ~ ~ 0\n"]
        place_lines = [f"execute at @n[type=marker,tag={TAG}] run function {NS}:lights_on\n"] if lights else []
        put(f"data/{NS}/function/start.mcfunction", start_text(snap_lines, place_lines))
    put(f"data/{NS}/function/stop.mcfunction",
        f"scoreboard players set #run {NS} 0\nschedule clear {NS}:f/0\n"
        + (f"stopsound @a master {NS}:video\n" if has_audio else ""))
    put(f"data/{NS}/function/clear.mcfunction",
        f"function {NS}:stop\n"
        f"execute at @n[type=marker,tag={TAG}] run function {NS}:cleanup\n"
        f"kill @e[type=marker,tag={TAG}]\n")
    put("pack.mcmeta", f'{{"pack":{{"description":"mcvideo: {NS}",'
                       f'"min_format":{a.data_format},"max_format":{a.data_format}}}}}')
    zf.close()
    result.data_zip, result.frames, result.commands = data_zip, n, total
    log("wrote", data_zip, os.path.getsize(data_zip), "bytes")

    # ------------------------------------------------------------ audio resource pack
    if has_audio:
        ogg = os.path.join(OUT, "video.ogg")
        subprocess.run([ffmpeg, "-v", "error", "-y"] + _trim_args(a) + ["-i", a.input, "-vn", "-c:a", "libvorbis",
                                                                       "-ac", "2", "-q:a", "4", ogg], check=True)
        rp_zip = os.path.join(OUT, f"{NS}_audio.zip")
        with zipfile.ZipFile(rp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("pack.mcmeta", f'{{"pack":{{"description":"mcvideo audio: {NS}",'
                                      f'"min_format":{a.resource_format},"max_format":{a.resource_format}}}}}')
            z.writestr(f"assets/{NS}/sounds.json", f'{{"video":{{"sounds":[{{"name":"{NS}:video","stream":true}}]}}}}')
            z.write(ogg, f"assets/{NS}/sounds/video.ogg")
        os.remove(ogg)
        result.audio_zip = rp_zip
        log("wrote", rp_zip, os.path.getsize(rp_zip), "bytes")

    if a.world_datapacks:
        shutil.copy(data_zip, a.world_datapacks)
        log("copied datapack ->", a.world_datapacks)
    if a.resourcepacks and result.audio_zip:
        shutil.copy(result.audio_zip, a.resourcepacks)
        log("copied resource pack ->", a.resourcepacks)
    return result
