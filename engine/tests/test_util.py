import tempfile
import unittest
from pathlib import Path

from aestudio.util import hex_rgb, js, next_free, r3


class UtilTest(unittest.TestCase):
    def test_js_escapes_non_ascii_and_is_compact(self):
        self.assertEqual(js({"t": "가 “x”", "n": [1, 2.5]}), '{"t":"\\uac00 \\u201cx\\u201d","n":[1,2.5]}')

    def test_hex_rgb(self):
        self.assertEqual(hex_rgb("#FFD84D"), [1.0, 0.84706, 0.30196])
        self.assertEqual(hex_rgb("22304a"), [0.13333, 0.18824, 0.2902])

    def test_hex_rgb_rejects_bad_input(self):
        for bad in ("#FFF", "#GG0000", ""):
            with self.assertRaises(ValueError):
                hex_rgb(bad)

    def test_r3(self):
        self.assertEqual(r3(1.23456), 1.235)
        self.assertEqual(r3(2), 2.0)

    def test_next_free_counts_past_taken_versions(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "my-video.aep"
            self.assertEqual(next_free(base), base)
            base.write_text("x")
            (Path(d) / "my-video-v02.aep").write_text("x")
            self.assertEqual(next_free(base).name, "my-video-v03.aep")


if __name__ == "__main__":
    unittest.main()
