"""Block colour palettes used by block mode.

A palette is a list of ``(rgb, block_id)``; ``rgb`` is the colour used for matching and the first entry is the
background (the darkest colour). ``block_id`` has no ``minecraft:`` prefix.

    bw     black / white concrete, matched to pure greys (clean thresholds)
    gray   four greys
    color  the 16 concrete blocks
    plus   concrete + wool + terracotta (49 blocks)
    full   plus ~70 more solid blocks: stone, planks, metal blocks, ... (121 blocks)

The colour sets live in ``data/blockpalette.json`` (made by ``python -m mcvideo.make_palette`` from the game's own
textures).
"""
import json
import os

CHOICES = ["bw", "gray", "color", "plus", "full"]
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "blockpalette.json")


class PaletteError(RuntimeError):
    """The palette data is missing or invalid."""


def _luma(rgb):
    return rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114


def unique_red(entries):
    """Make the red channel of every entry unique.

    The converter reads only the red channel of each quantised pixel and maps it back to a palette index with a
    256-byte translate table, so two entries must never share a red value. Colliding values are moved to the nearest
    free value (a few units at most).
    """
    used, fixed = set(), []
    for (r, g, b), block in entries:
        r2 = None
        for d in range(256):
            for cand in (r + d, r - d):
                if 0 <= cand <= 255 and cand not in used:
                    r2 = cand
                    break
            if r2 is not None:
                break
        if r2 is None:
            raise PaletteError("more than 256 palette entries")
        used.add(r2)
        fixed.append(((r2, g, b), block))
    return fixed


def build_palette(name, data_file=DATA_FILE):
    """Return the palette ``name`` as ``[((r, g, b), block_id), ...]`` with the darkest colour first."""
    if name == "bw":
        return [((0, 0, 0), "black_concrete"), ((255, 255, 255), "white_concrete")]
    if name == "gray":
        return [((0, 0, 0), "black_concrete"), ((85, 85, 85), "gray_concrete"),
                ((170, 170, 170), "light_gray_concrete"), ((255, 255, 255), "white_concrete")]
    if name not in CHOICES:
        raise PaletteError(f"unknown palette '{name}' (choose from {', '.join(CHOICES)})")
    if not os.path.exists(data_file):
        raise PaletteError(f"{data_file} is missing: run  python -m mcvideo.make_palette  (needs a client jar)")
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)
    entries, seen = [], set()
    for block in data["sets"][name]:
        rgb = tuple(data["blocks"][block])
        if rgb not in seen:  # identical colours add nothing
            seen.add(rgb)
            entries.append((rgb, block))
    entries.sort(key=lambda e: _luma(e[0]))  # darkest first = background
    return unique_red(entries)
