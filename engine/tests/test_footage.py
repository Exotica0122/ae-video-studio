import json
import os
import shutil
import subprocess
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
        times = [f["at"] for f in clip["frames"]]
        self.assertEqual(sorted(times), times, "frames are sampled in order")
        self.assertGreater(times[0], 0, "not the very first frame, where a fade often is")
        self.assertLess(times[-1], clip["duration"], "not past the end of the clip")
        self.assertGreater(times[-1] - times[0], clip["duration"] * 0.5,
                           "frames must span the clip, not cluster at its head")
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

    def test_same_named_clips_in_different_folders_do_not_collide(self):
        for day in ("day1", "day2"):
            folder = self.out / "src" / day
            folder.mkdir(parents=True)
            shutil.copyfile(DEMO / "shot_a.mp4", folder / "interview.mp4")
        analysis = self.out / "analysis"
        log = footage.log_footage([self.out / "src" / "day1", self.out / "src" / "day2"], analysis,
                                  every=10.0, max_frames=2)
        self.assertEqual([c["name"] for c in log["clips"]], ["interview.mp4", "interview.mp4"])
        first, second = log["clips"]
        self.assertNotEqual(first["frames"][0]["file"], second["frames"][0]["file"])
        self.assertNotEqual(first["sheet"], second["sheet"])
        for clip in log["clips"]:
            for rel in [f["file"] for f in clip["frames"]] + [clip["sheet"]]:
                self.assertTrue((analysis / rel).exists(), rel)

    def test_clip_path_is_absolute_even_for_a_relative_source(self):
        cwd = Path.cwd()
        try:
            os.chdir(DEMO)
            relative = os.path.relpath(DEMO / "shot_a.mp4", DEMO)
            log = footage.log_footage([relative], self.out, every=10.0, max_frames=1)
        finally:
            os.chdir(cwd)
        self.assertTrue(Path(log["clips"][0]["path"]).is_absolute(), log["clips"][0]["path"])

    def _make_jpeg(self, path: Path, color="red", size="320x240"):
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", f"color=c={color}:s={size}", "-frames:v", "1", str(path)], check=True)

    def test_logs_a_jpeg_under_images(self):
        photo = self.out / "src" / "photo.jpg"
        self._make_jpeg(photo)
        log = footage.log_footage([photo.parent], self.out / "analysis")
        self.assertEqual(log["errors"], [])
        self.assertEqual(len(log["images"]), 1)
        entry = log["images"][0]
        self.assertEqual(entry["name"], "photo.jpg")
        self.assertTrue(Path(entry["path"]).is_absolute())
        self.assertEqual(entry["width"], 320)
        self.assertEqual(entry["height"], 240)
        self.assertTrue(0 <= entry["luma"] <= 1)
        self.assertEqual(len(entry["colors"]), 4)
        self.assertTrue((self.out / "analysis" / entry["file"]).exists())
        self.assertEqual(log["clips"], [])          # a still image is not a clip

    def test_same_named_images_in_different_folders_do_not_collide(self):
        for day in ("day1", "day2"):
            self._make_jpeg(self.out / "src" / day / "photo.jpg", color=("red" if day == "day1" else "blue"))
        analysis = self.out / "analysis"
        log = footage.log_footage([self.out / "src" / "day1", self.out / "src" / "day2"], analysis)
        self.assertEqual(len(log["images"]), 2)
        first, second = log["images"]
        self.assertNotEqual(first["file"], second["file"])
        for entry in log["images"]:
            self.assertTrue((analysis / entry["file"]).exists(), entry["file"])

    def test_xml_sidecar_is_ignored_and_a_corrupt_jpeg_is_an_error(self):
        folder = self.out / "src"
        folder.mkdir(parents=True)
        (folder / "shot_a.xml").write_text("<xmeml/>")
        (folder / "bad.jpg").write_text("not a jpeg")
        good = folder / "photo.jpg"
        self._make_jpeg(good)
        log = footage.log_footage([folder], self.out / "analysis")
        self.assertEqual(len(log["images"]), 1)
        self.assertEqual(log["images"][0]["name"], "photo.jpg")
        self.assertEqual(len(log["errors"]), 1)
        self.assertIn("bad.jpg", log["errors"][0])


if __name__ == "__main__":
    unittest.main()


class FrameSamplingTest(unittest.TestCase):
    """Sampling is proportional: a short clip should not be represented by one frame."""

    def test_a_short_clip_still_earns_several_frames(self):
        self.assertGreaterEqual(len(footage._frame_times(7.5, 4.0, 6)), 3,
                                "the median clip of a real shoot was getting 1-2")

    def test_more_duration_earns_more_frames_up_to_the_cap(self):
        counts = [len(footage._frame_times(d, 4.0, 6)) for d in (2.0, 7.5, 12.0, 20.0, 600.0)]
        self.assertEqual(counts, sorted(counts), "longer clips never get fewer frames")
        self.assertEqual(counts[-1], 6, "max_frames is respected")

    def test_frames_are_inset_from_both_ends(self):
        times = footage._frame_times(10.0, 4.0, 6)
        self.assertGreater(times[0], 0.0)
        self.assertLess(times[-1], 10.0)

    def test_a_clip_shorter_than_a_second_gets_its_middle(self):
        self.assertEqual(footage._frame_times(0.6, 4.0, 6), [0.3])

    def test_a_zero_length_clip_does_not_crash(self):
        self.assertEqual(footage._frame_times(0, 4.0, 6), [0.0])
