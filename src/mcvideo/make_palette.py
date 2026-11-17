"""Measure the average colour of block textures from a Minecraft client jar.

    python -m mcvideo.make_palette [--jar PATH] [--out FILE]

Writes the palette data used by ``--palette color|plus|full`` (default: ``data/blockpalette.json`` inside the
package). Run it again to refresh the colours for another Minecraft version. Only the averaged numbers are stored,
never the textures themselves. Only solid-looking, non-falling, non-glowing, non-ticking blocks are listed.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import zipfile

from .palette import DATA_FILE
from .tools import ToolError, find_tool

DYES = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan",
        "purple", "blue", "brown", "green", "red", "black"]

CONCRETE = [(f"{d}_concrete", f"{d}_concrete") for d in DYES]
WOOL = [(f"{d}_wool", f"{d}_wool") for d in DYES]
TERRACOTTA = [("terracotta", "terracotta")] + [(f"{d}_terracotta", f"{d}_terracotta") for d in DYES]
# (block id, texture name). Directional blocks use the side texture because the wall is seen from the side.
EXTRA = [
    ("snow_block", "snow"), ("quartz_block", "quartz_block_side"), ("smooth_quartz", "quartz_block_bottom"),
    ("smooth_stone", "smooth_stone"), ("stone", "stone"), ("andesite", "andesite"), ("diorite", "diorite"),
    ("granite", "granite"), ("polished_andesite", "polished_andesite"), ("polished_diorite", "polished_diorite"),
    ("polished_granite", "polished_granite"), ("calcite", "calcite"), ("tuff", "tuff"), ("deepslate", "deepslate"),
    ("polished_deepslate", "polished_deepslate"), ("blackstone", "blackstone"),
    ("polished_blackstone", "polished_blackstone"), ("obsidian", "obsidian"),
    ("coal_block", "coal_block"), ("iron_block", "iron_block"), ("gold_block", "gold_block"),
    ("diamond_block", "diamond_block"), ("emerald_block", "emerald_block"), ("lapis_block", "lapis_block"),
    ("redstone_block", "redstone_block"), ("netherite_block", "netherite_block"), ("amethyst_block", "amethyst_block"),
    # waxed copper does not oxidise, so its colour stays put
    ("waxed_copper_block", "copper_block"), ("waxed_exposed_copper", "exposed_copper"),
    ("waxed_weathered_copper", "weathered_copper"), ("waxed_oxidized_copper", "oxidized_copper"),
    ("packed_ice", "packed_ice"), ("blue_ice", "blue_ice"), ("clay", "clay"), ("moss_block", "moss_block"),
    ("bone_block", "bone_block_side"), ("hay_block", "hay_block_side"), ("netherrack", "netherrack"),
    ("nether_bricks", "nether_bricks"), ("red_nether_bricks", "red_nether_bricks"),
    ("warped_wart_block", "warped_wart_block"), ("nether_wart_block", "nether_wart_block"),
    ("end_stone", "end_stone"), ("purpur_block", "purpur_block"), ("prismarine", "prismarine"),
    ("dark_prismarine", "dark_prismarine"), ("prismarine_bricks", "prismarine_bricks"), ("bricks", "bricks"),
    ("mud_bricks", "mud_bricks"), ("stone_bricks", "stone_bricks"), ("sandstone", "sandstone"),
    ("red_sandstone", "red_sandstone"), ("smooth_sandstone", "sandstone_top"),
    ("smooth_red_sandstone", "red_sandstone_top"), ("pumpkin", "pumpkin_side"), ("melon", "melon_side"),
    ("dried_kelp_block", "dried_kelp_side"), ("dripstone_block", "dripstone_block"), ("mud", "mud"),
    ("coarse_dirt", "coarse_dirt"), ("dirt", "dirt"), ("honeycomb_block", "honeycomb_block"),
] + [(f"{w}_planks", f"{w}_planks") for w in
     ["oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "bamboo", "crimson", "warped"]]


def default_jar():
    """The newest client jar in the Prism Launcher libraries folder, or None."""
    pattern = os.path.expandvars(r"%APPDATA%\PrismLauncher\libraries\com\mojang\minecraft\*\minecraft-*-client.jar")
    found = glob.glob(pattern)
    found.sort(key=lambda s: [int(x) if x.isdigit() else 0 for x in os.path.basename(s).replace("-", ".").split(".")])
    return found[-1] if found else None


def measure(jar, ffmpeg):
    """Return ``(blocks, missing)``: block id -> [r, g, b], and the ids whose texture was not found."""
    names_zip = zipfile.ZipFile(jar)
    names = set(names_zip.namelist())
    blocks, missing = {}, []
    for block, texture in CONCRETE + WOOL + TERRACOTTA + EXTRA:
        path = f"assets/minecraft/textures/block/{texture}.png"
        if path not in names:
            missing.append(block)
            continue
        out = subprocess.run(
            [ffmpeg, "-v", "error", "-i", "pipe:0", "-vf", "scale=1:1:flags=area", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], input=names_zip.read(path), capture_output=True, check=True).stdout
        blocks[block] = list(out[:3])
    return blocks, missing


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jar", help="minecraft client jar (default: newest one in the Prism libraries folder)")
    p.add_argument("--out", default=DATA_FILE, help="output file (default: the package data file)")
    a = p.parse_args(argv)
    jar = a.jar or default_jar()
    if not jar:
        print("no client jar found; pass --jar", file=sys.stderr)
        return 1
    try:
        ffmpeg = find_tool("ffmpeg")
    except ToolError as e:
        print(e, file=sys.stderr)
        return 1
    print("jar:", jar)
    blocks, missing = measure(jar, ffmpeg)

    def ids(lst):
        return [b for b, _ in lst if b in blocks]

    data = {
        "source": os.path.basename(jar),
        "blocks": blocks,
        "sets": {
            "color": ids(CONCRETE),
            "plus": ids(CONCRETE) + ids(WOOL) + ids(TERRACOTTA),
            "full": ids(CONCRETE) + ids(WOOL) + ids(TERRACOTTA) + ids(EXTRA),
        },
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print({k: len(v) for k, v in data["sets"].items()}, "| missing textures:", missing, "->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
