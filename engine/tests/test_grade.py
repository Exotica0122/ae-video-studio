"""color-grade: the look catalogue, exposure matching maths, and the preview page."""
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aestudio import grade
from aestudio.grade import GradeError


def _catalogue(tmp, entries):
    path = Path(tmp) / "looks.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


VALID = [{"id": "neutral", "name": "Neutral", "mood": ["clean"], "ae": {"exposure": 0}},
         {"id": "warm", "name": "Warm", "mood": ["warm", "hopeful"], "ae": {"exposure": 0.1},
          "preview": "eq=contrast=1.05"}]


class CatalogueTest(unittest.TestCase):
    def test_the_shipped_catalogue_loads_and_every_look_carries_builder_parameters(self):
        looks = grade.load_looks()
        self.assertGreaterEqual(len(looks), 3)
        for look in looks:
            self.assertTrue(look.ae, f"{look.id} has no 'ae' parameters for the builder")

    def test_duplicate_ids_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _catalogue(tmp, [VALID[0], VALID[0]])
            with self.assertRaises(GradeError) as caught:
                grade.load_looks(path)
            self.assertIn("duplicate", str(caught.exception))

    def test_a_look_without_builder_parameters_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _catalogue(tmp, [{"id": "x", "name": "X"}])
            with self.assertRaises(GradeError):
                grade.load_looks(path)

    def test_an_empty_or_unreadable_catalogue_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(GradeError):
                grade.load_looks(_catalogue(tmp, []))
            with self.assertRaises(GradeError):
                grade.load_looks(Path(tmp) / "absent.json")


class RankingTest(unittest.TestCase):
    def setUp(self):
        self.catalogue = grade.load_looks()

    def test_moods_pick_the_matching_look_first(self):
        chosen = grade.looks_for(["warm", "hopeful"], catalogue=self.catalogue)
        self.assertEqual(chosen[0].id, "warm-airy")

    def test_neutral_is_always_offered_as_a_baseline(self):
        chosen = grade.looks_for(["cinematic", "dramatic"], catalogue=self.catalogue)
        self.assertIn("neutral", [l.id for l in chosen], "there must always be a do-nothing option")

    def test_no_moods_still_returns_a_usable_set(self):
        self.assertTrue(grade.looks_for([], catalogue=self.catalogue))


def _log(lumas, root="."):
    return {"root": root,
            "clips": [{"name": f"c{i}.MP4", "path": f"/src/c{i}.MP4", "luma": l, "duration": 5.0,
                       "frames": []} for i, l in enumerate(lumas)]}


class ExposureMatchTest(unittest.TestCase):
    def test_the_median_shot_is_the_one_everything_joins(self):
        match = grade.exposure_offsets(_log([0.2, 0.4, 0.8]))
        self.assertEqual(match["target_luma"], 0.4)
        self.assertEqual(match["offsets"]["c1.MP4"], 0.0, "the median shot needs no correction")

    def test_the_correction_is_log2_of_the_brightness_ratio(self):
        # 0.3 -> 0.5 is log2(5/3) = 0.737 stops, just inside the clamp
        match = grade.exposure_offsets(_log([0.3, 0.5]), target=0.5)
        self.assertAlmostEqual(match["offsets"]["c0.MP4"], math.log2(0.5 / 0.3), places=3)

    def test_a_full_stop_is_already_beyond_the_match_limit(self):
        match = grade.exposure_offsets(_log([0.25, 0.5]), target=0.5)
        self.assertEqual(match["offsets"]["c0.MP4"], grade.MAX_MATCH_STOPS,
                         "one stop of push is a relight, not a match")

    def test_an_extreme_shot_is_clamped_and_reported_rather_than_pushed(self):
        match = grade.exposure_offsets(_log([0.05, 0.5]), target=0.5)
        self.assertEqual(match["offsets"]["c0.MP4"], grade.MAX_MATCH_STOPS)
        named = [b["name"] for b in match["beyond_match"]]
        self.assertEqual(named, ["c0.MP4"])
        self.assertGreater(abs(match["beyond_match"][0]["stops"]), grade.MAX_MATCH_STOPS)

    def test_a_darker_shot_gets_a_positive_correction(self):
        match = grade.exposure_offsets(_log([0.3, 0.4]), target=0.4)
        self.assertGreater(match["offsets"]["c0.MP4"], 0)

    def test_clips_without_a_brightness_measurement_are_refused(self):
        with self.assertRaises(GradeError):
            grade.exposure_offsets({"clips": [{"name": "a.MP4", "luma": 0}]})


class RepresentativeTest(unittest.TestCase):
    def test_the_sample_spans_the_darkest_and_brightest_shots(self):
        chosen = grade.representative_clips(_log([0.1, 0.2, 0.3, 0.4, 0.5, 0.9]), count=4)
        lumas = [c["luma"] for c in chosen]
        self.assertEqual(lumas[0], 0.1)
        self.assertEqual(lumas[-1], 0.9)
        self.assertEqual(len(chosen), 4)

    def test_fewer_clips_than_asked_for_returns_them_all(self):
        self.assertEqual(len(grade.representative_clips(_log([0.3, 0.6]), count=4)), 2)

    def test_footage_without_brightness_yields_nothing_rather_than_guessing(self):
        self.assertEqual(grade.representative_clips({"clips": []}), [])


class PlanTest(unittest.TestCase):
    def test_the_plan_carries_the_builder_parameters_beside_the_match(self):
        look = grade.load_looks()[1]
        plan = grade.grade_plan(look, grade.exposure_offsets(_log([0.3, 0.5])), design_hint="warm-airy")
        self.assertEqual(plan["look"]["id"], look.id)
        self.assertIn("exposure", plan["look"])
        self.assertIn("offsets", plan["match"])
        self.assertEqual(plan["design_hint"], "warm-airy")

    def test_saving_creates_the_folder_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan" / "grade.json"
            grade.save_grade({"look": {"id": "neutral"}}, out)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["look"]["id"], "neutral")


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class PreviewTest(unittest.TestCase):
    def _log_with_frames(self, root):
        frames_dir = Path(root) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        clips = []
        for i, colour in enumerate(("gray:s=320x180", "red:s=320x180")):
            rel = f"frames/c{i}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:d=1",
                            "-frames:v", "1", str(Path(root) / rel)], check=True)
            clips.append({"name": f"c{i}.MP4", "path": f"/nowhere/c{i}.MP4", "luma": 0.3 + 0.2 * i,
                          "duration": 5.0, "frames": [{"at": 0.5, "file": rel}]})
        return {"root": str(root), "clips": clips}

    def test_the_page_uses_the_sampled_frames_so_the_source_drive_is_not_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._log_with_frames(tmp)
            out = Path(tmp) / "preview"
            index = grade.render_look_previews(grade.load_looks()[:2], log, out)
            self.assertTrue(index.exists(), "the source clips do not exist; only the frames do")
            html = index.read_text(encoding="utf-8")
            self.assertIn('class="choose"', html)
            self.assertIn("data-id=", html)

    def test_every_look_gets_an_image_for_every_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._log_with_frames(tmp)
            out = Path(tmp) / "preview"
            looks = grade.load_looks()[:3]
            grade.render_look_previews(looks, log, out)
            for look in looks:
                made = list(out.glob(f"{look.id}-*.jpg"))
                self.assertEqual(len(made), 2, f"{look.id} is missing a shot")

    def test_drafts_json_lists_the_ids_the_choose_server_will_accept(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._log_with_frames(tmp)
            out = Path(tmp) / "preview"
            looks = grade.load_looks()[:2]
            grade.render_look_previews(looks, log, out)
            ids = [d["id"] for d in json.loads((out / "drafts.json").read_text(encoding="utf-8"))]
            self.assertEqual(ids, [l.id for l in looks])

    def test_a_look_actually_changes_the_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                            "-i", "color=c=0x7a6250:s=320x180:d=1", "-frames:v", "1", str(src)], check=True)
            warm = next(l for l in grade.load_looks() if l.id == "warm-airy")
            neutral = next(l for l in grade.load_looks() if l.id == "neutral")
            a = grade.apply_look(src, warm, Path(tmp) / "warm.jpg")
            b = grade.apply_look(src, neutral, Path(tmp) / "flat.jpg")
            self.assertNotEqual(a.read_bytes(), b.read_bytes(), "the look had no effect on the frame")

    def test_a_missing_frame_and_an_unreachable_source_says_so_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = {"root": tmp, "clips": [{"name": "c.MP4", "path": "/nowhere/c.MP4", "luma": 0.4,
                                           "duration": 5.0, "frames": []}]}
            with self.assertRaises(GradeError) as caught:
                grade.render_look_previews(grade.load_looks()[:1], log, Path(tmp) / "out")
            self.assertIn("drive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
