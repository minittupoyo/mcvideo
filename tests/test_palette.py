import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcvideo import palette  # noqa: E402


class PaletteTests(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(len(palette.build_palette("bw")), 2)
        self.assertEqual(len(palette.build_palette("gray")), 4)
        self.assertEqual(len(palette.build_palette("color")), 16)
        self.assertEqual(len(palette.build_palette("plus")), 49)
        self.assertGreater(len(palette.build_palette("full")), 100)

    def test_red_values_are_unique_and_in_range(self):
        for name in palette.CHOICES:
            reds = [rgb[0] for rgb, _ in palette.build_palette(name)]
            self.assertEqual(len(reds), len(set(reds)), name)
            self.assertTrue(all(0 <= r <= 255 for r in reds), name)

    def test_background_is_the_darkest(self):
        for name in ("color", "plus", "full"):
            pal = palette.build_palette(name)
            luma = [r * 299 + g * 587 + b * 114 for (r, g, b), _ in pal]
            self.assertEqual(luma[0], min(luma), name)

    def test_block_ids_have_no_namespace(self):
        for name in palette.CHOICES:
            for _, block in palette.build_palette(name):
                self.assertNotIn(":", block)

    def test_unique_red_moves_collisions_a_little(self):
        entries = [((100, 0, 0), "a"), ((100, 5, 5), "b"), ((100, 9, 9), "c"), ((0, 0, 0), "d")]
        fixed = palette.unique_red(entries)
        reds = [rgb[0] for rgb, _ in fixed]
        self.assertEqual(len(set(reds)), 4)
        self.assertTrue(all(abs(r - o[0][0]) <= 2 for r, o in zip(reds, entries)))

    def test_unique_red_rejects_more_than_256(self):
        entries = [((i % 256, 0, 0), str(i)) for i in range(257)]
        with self.assertRaises(palette.PaletteError):
            palette.unique_red(entries)

    def test_unknown_palette(self):
        with self.assertRaises(palette.PaletteError):
            palette.build_palette("nope")

    def test_missing_data_file(self):
        with self.assertRaises(palette.PaletteError):
            palette.build_palette("plus", data_file="does-not-exist.json")


if __name__ == "__main__":
    unittest.main()
