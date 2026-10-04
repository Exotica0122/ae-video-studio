import json
import tempfile
import unittest
from pathlib import Path

from aestudio.plan import PlanError, load_plan


def write_plan(root: Path, plan: dict, files=("media/a.mp4", "media/n1.wav", "t/n1.json", "media/m.wav")) -> Path:
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    path = root / "edit.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return path


def base_plan() -> dict:
    return {
        "name": "DEMO",
        "format": {"width": 3840, "height": 2160, "fps": 23.976, "duration": 20},
        "voices": [{"id": "N1", "file": "media/n1.wav", "at": 2.0, "transcript": "t/n1.json"}],
        "music": {"file": "media/m.wav", "gain_db": -6},
        "shots": [{"clip": "media/a.mp4", "in": 0, "out": 20}],
        "graphics": [{"type": "caption", "voice": "N1", "lines": [["hello"]]}],
    }


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_loads_and_resolves_paths(self):
        plan = load_plan(write_plan(self.root, base_plan()))
        self.assertEqual(plan.name, "DEMO")
        self.assertEqual(plan.format.duration, 20.0)
        self.assertEqual(plan.shots[0].clip, (self.root / "media/a.mp4").resolve())
        self.assertEqual(plan.shots[0].start, 0.0)
        self.assertEqual(plan.voices[0].transcript, (self.root / "t/n1.json").resolve())
        self.assertEqual(plan.music[0].gain_db, -6.0)
        self.assertEqual(plan.fade_out, 0.75)
        self.assertIsNone(plan.project)

    def test_rejects_unknown_voice_reference(self):
        p = base_plan()
        p["graphics"][0]["voice"] = "N9"
        with self.assertRaisesRegex(PlanError, "unknown voice 'N9'"):
            load_plan(write_plan(self.root, p))

    def test_rejects_shot_that_ends_before_it_starts(self):
        p = base_plan()
        p["shots"][0]["out"] = 0
        with self.assertRaisesRegex(PlanError, r"shots\[0\].*out must be greater than in"):
            load_plan(write_plan(self.root, p))

    def test_rejects_unknown_graphic_type(self):
        p = base_plan()
        p["graphics"].append({"type": "sparkles"})
        with self.assertRaisesRegex(PlanError, "unknown type 'sparkles'"):
            load_plan(write_plan(self.root, p))

    def test_reports_missing_files(self):
        path = write_plan(self.root, base_plan(), files=("t/n1.json",))
        with self.assertRaisesRegex(PlanError, "file not found"):
            load_plan(path)
        self.assertEqual(load_plan(path, check_files=False).name, "DEMO")

    def test_end_card_paths_are_resolved(self):
        p = base_plan()
        p["graphics"].append({"type": "end-card", "in": 15, "title": "T", "photo": {"clip": "media/a.mp4"}})
        plan = load_plan(write_plan(self.root, p))
        self.assertEqual(plan.graphics[1]["photo"]["clip"], str((self.root / "media/a.mp4").resolve()))

    def test_duplicate_voice_ids(self):
        p = base_plan()
        p["voices"].append(dict(p["voices"][0]))
        with self.assertRaisesRegex(PlanError, "duplicate voice id 'N1'"):
            load_plan(write_plan(self.root, p))

    def test_rejects_non_numeric_format_width(self):
        p = base_plan()
        p["format"]["width"] = "not-a-number"
        with self.assertRaisesRegex(PlanError, "format.*width.*must be a number"):
            load_plan(write_plan(self.root, p))


class MusicSegmentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self, music):
        p = base_plan()
        p["music"] = music
        return load_plan(write_plan(self.root, p))

    def test_a_single_object_is_one_segment_to_the_end(self):
        plan = self._load({"file": "media/m.wav", "gain_db": -6})
        self.assertEqual(len(plan.music), 1)
        self.assertIsNone(plan.music[0].end)
        self.assertEqual((plan.music[0].src_in, plan.music[0].fade_in), (0.0, 0.0))

    def test_a_list_loads_every_segment(self):
        plan = self._load([{"file": "media/m.wav", "end": 12, "fade_out": 2},
                           {"file": "media/m.wav", "start": 10, "src_in": 4.5, "fade_in": 2, "gain_db": -3}])
        self.assertEqual([m.end for m in plan.music], [12.0, None])
        self.assertEqual(plan.music[1].src_in, 4.5)
        self.assertEqual(plan.music[1].gain_db, -3.0)

    def test_no_music_is_an_empty_list(self):
        p = base_plan()
        del p["music"]
        self.assertEqual(load_plan(write_plan(self.root, p)).music, [])

    def test_rejects_bad_segments(self):
        for music, message in (([], "must not be empty"),
                               ([{"file": "media/m.wav", "start": 5, "end": 5}], r"music\[0\]: 'end' must be greater"),
                               ([{"file": "media/m.wav", "end": 30}], "past the end of the video"),
                               ([{"file": "media/m.wav", "end": 3, "fade_in": 2, "fade_out": 2}], "longer than the segment"),
                               ("m.wav", "must be an object or a list")):
            with self.subTest(music=music), self.assertRaisesRegex(PlanError, message):
                self._load(music)

if __name__ == "__main__":
    unittest.main()
