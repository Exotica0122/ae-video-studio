import json
import tempfile
import unittest
from pathlib import Path

from aestudio import footage

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo" / "media"


@unittest.skipUnless((DEMO / "shot_a.mp4").exists(), "run examples/demo/make_media.py first")
class FootageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_logs_clips_frames_and_audio(self):
        log = footage.log_footage([DEMO / "shot_a.mp4", DEMO / "narration-1.wav"], self.out, every=4.0, max_frames=3)
        self.assertEqual([c["name"] for c in log["clips"]], ["shot_a.mp4"])
        self.assertEqual([a["name"] for a in log["audio"]], ["narration-1.wav"])
        self.assertEqual(log["errors"], [])
        clip = log["clips"][0]
        self.assertEqual(len(clip["frames"]), 3)
        self.assertEqual([f["at"] for f in clip["frames"]], [0.5, 4.5, 8.5])
        self.assertTrue(0 < clip["luma"] < 1)
        self.assertEqual(len(clip["frames"][0]["colors"]), 4)
        for rel in [f["file"] for f in clip["frames"]] + [clip["sheet"]]:
            self.assertTrue((self.out / rel).exists(), rel)
        written = json.loads((self.out / "footage.json").read_text(encoding="utf-8"))
        self.assertEqual(written["clips"][0]["name"], "shot_a.mp4")

    def test_walks_a_folder_and_reports_bad_files(self):
        broken = self.out / "src" / "broken.mp4"
        broken.parent.mkdir(parents=True)
        broken.write_text("not a video")
        (broken.parent / "._shot_a.mp4").write_text("apple double")
        (broken.parent / "notes.txt").write_text("ignored")
        log = footage.log_footage([broken.parent], self.out / "analysis")
        self.assertEqual(log["clips"], [])
        self.assertEqual(len(log["errors"]), 1)
        self.assertIn("broken.mp4", log["errors"][0])

    def test_frames_stay_inside_the_clip(self):
        log = footage.log_footage([DEMO / "shot_a.mp4"], self.out, every=10.0, max_frames=6)
        ats = [f["at"] for f in log["clips"][0]["frames"]]
        self.assertTrue(all(a < log["clips"][0]["duration"] for a in ats), ats)


if __name__ == "__main__":
    unittest.main()
