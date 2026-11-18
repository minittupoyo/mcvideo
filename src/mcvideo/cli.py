"""Command line interface: ``python -m mcvideo INPUT [options]`` (or ``mcvideo INPUT``)."""
import argparse
import sys

from . import __version__
from .convert import ConvertError, convert
from .palette import CHOICES as PALETTE_CHOICES

DESCRIPTION = """\
Turn any video into a Minecraft Java Edition datapack (+ audio resource pack).

  mcvideo clip.mp4 --name myclip --mode block --palette plus
  mcvideo clip.mp4 --name myclip --mode particle --width 64            (colour dust)
  mcvideo clip.mp4 --name bw     --mode particle --mono --width 64     (white dust)

Outputs (in --out, default build/<name>/):
  <ns>_data.zip   datapack      -> <world>/datapacks/       then /reload
  <ns>_audio.zip  resource pack -> resourcepacks/           enable it, then F3+T
In game, face the way you want the screen and stand at the level you want its bottom edge, then run:
  /function <ns>:start      /function <ns>:stop      /function <ns>:clear
"""


def build_parser():
    p = argparse.ArgumentParser(prog="mcvideo", description=DESCRIPTION,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="video file")
    p.add_argument("--version", action="version", version=f"mcvideo {__version__}")
    p.add_argument("--name", help="pack name, becomes the namespace (default: the file name)")
    p.add_argument("--mode", choices=["block", "particle"], default="block")
    p.add_argument("--width", type=int, help="picture width in pixels (default: 128 block / 64 particle)")
    p.add_argument("--height", type=int, help="picture height (default: keep the video's aspect ratio)")
    p.add_argument("--fps", type=int, default=10, choices=[1, 2, 4, 5, 10, 20],
                   help="frames per second (must divide 20; default 10)")
    p.add_argument("--ss", type=float, default=0, help="start offset in seconds")
    p.add_argument("--seconds", type=float, default=0, help="length to convert, 0 = to the end")
    p.add_argument("--dist", type=float, help="blocks in front of the player (default: block 100 / particle 30)")
    p.add_argument("--anchor", choices=["bottom", "gaze"], default="bottom",
                   help="bottom: the screen's bottom edge is at the player's feet level, --dist blocks ahead "
                        "(horizontal). gaze: the screen's centre is where the player looks")
    p.add_argument("--lift", type=float, default=0, help="raise the screen by this many blocks")
    p.add_argument("--min-y", type=int, default=-64, help="lowest build height of the world (overworld: -64)")
    p.add_argument("--max-y", type=int, default=319, help="highest build height of the world (overworld: 319)")
    p.add_argument("--out", help="output folder (default: build/<name>)")
    p.add_argument("--no-audio", action="store_true", help="do not make the audio resource pack")
    p.add_argument("--data-format", type=int, default=121, help="datapack format (Minecraft 26.3: 121)")
    p.add_argument("--resource-format", type=int, default=97, help="resource pack format (Minecraft 26.3: 97)")
    p.add_argument("--world-datapacks", help="also copy the datapack into this folder")
    p.add_argument("--resourcepacks", help="also copy the audio resource pack into this folder")
    g = p.add_argument_group("block mode")
    g.add_argument("--palette", choices=PALETTE_CHOICES, default="color",
                   help="block colour set: bw, gray, color (16), plus (49), full (121)")
    g.add_argument("--method", choices=["fill", "structure"],
                   help="structure (default): one structure file per frame, drawn with `place template` "
                        "(overwrites the changed cells). fill: one `fill ... replace` per changed rectangle "
                        "(terrain is never touched, but thousands of commands)")
    g.add_argument("--nbt-data-version", type=int, default=4671,
                   help="DataVersion written into structure files (--method structure)")
    g.add_argument("--dither", choices=["none", "bayer", "floyd_steinberg"], default="none")
    g.add_argument("--preview", type=float, metavar="SECONDS",
                   help="only write <out>/preview_<palette>.png (that frame, 6x enlarged) and exit")
    g = p.add_argument_group("particle mode")
    g.add_argument("--cell", type=float, default=0.4, help="blocks per picture pixel")
    g.add_argument("--scale", type=float, default=0.4, help="dust size (small = short-lived)")
    g.add_argument("--thr", type=int, default=40, help="pixels with brightness >= thr are drawn (0-255)")
    g.add_argument("--invert", action="store_true", help="draw the dark pixels instead (white particles)")
    g.add_argument("--mono", action="store_true", help="white particles instead of the video's colours")
    g.add_argument("--particle", default="dust", help="dust (coloured) or e.g. end_rod (always white, long-lived)")
    g.add_argument("--no-lights", action="store_true", help="skip the light blocks that keep dust bright at night")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = convert(args)
    except ConvertError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if result.preview is None:
        ns = result.namespace
        print(f"\nin game:  /function {ns}:start   |   /function {ns}:stop   |   /function {ns}:clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
