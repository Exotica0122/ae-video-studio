import tempfile
import unittest
from pathlib import Path

from aestudio import media

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo" / "media"
CLIP, WAV = DEMO / "shot_a.mp4", DEMO / "narration-1.wav"


@unittest.skipUnless(CLIP.exists(), "run examples/demo/make_media.py first")
class MediaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe_video(self):
        info = media.probe(CLIP)
        self.assertEqual((info.width, info.height), (1920, 1080))
        self.assertAlmostEqual(info.fps, 24.0, places=2)
        self.assertGreater(info.duration, 13)
        self.assertTrue(info.has_video)
        self.assertFalse(info.has_audio)

    def test_probe_audio(self):
        info = media.probe(WAV)
        self.assertTrue(info.has_audio)
        self.assertFalse(info.has_video)
        self.assertEqual((info.width, info.height), (0, 0))

    def test_probe_missing_file(self):
        with self.assertRaises(media.MediaError):
            media.probe(self.out / "nope.mp4")

    def test_extract_frame_and_contact_sheet(self):
        frames = [media.extract_frame(CLIP, t, self.out / f"f{i}.jpg", width=320) for i, t in enumerate((1.0, 5.0, 9.0))]
        for f in frames:
            self.assertTrue(f.exists() and f.stat().st_size > 1000)
        self.assertEqual(media.probe(frames[0]).width, 320)
        sheet = media.contact_sheet(frames, self.out / "sheet.jpg", cols=2, tile_width=160)
        info = media.probe(sheet)
        self.assertEqual(info.width, 320)          # 2 columns × 160
        self.assertEqual(info.height, 180)         # 2 rows × 90 (16:9)

    def test_mean_luma_and_average_color(self):
        luma = media.mean_luma(CLIP, 2.0)
        self.assertTrue(0.0 <= luma <= 1.0)
        one = media.average_color(CLIP, 2.0)
        self.assertEqual(len(one), 1)
        self.assertEqual(len(one[0]), 3)
        self.assertTrue(all(0 <= c <= 255 for c in one[0]))
        grid = media.average_color(CLIP, 2.0, grid=2)
        self.assertEqual(len(grid), 4)
        self.assertNotEqual(grid[0], grid[3])       # the demo clips are gradients


if __name__ == "__main__":
    unittest.main()
