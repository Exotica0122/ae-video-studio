import json
import tempfile
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.design import load_design
from aestudio.grade import GradeError, look_lumetri, lumetri_keys
from aestudio.plan import PlanError, load_plan

FILMIC = {"id": "filmic", "exposure": -0.05, "contrast": 18, "temperature": 3, "tint": 0, "saturation": -10,
          "shadows": 12, "highlights": -8}


class LumetriKeysTest(unittest.TestCase):
    def test_names_map_to_verified_indices(self):
        names = {"temperature": 1, "tint": 2, "saturation": 3, "exposure": 4, "contrast": 5, "highlights": 6, "shadows": 7}
        self.assertEqual(lumetri_keys(names), {"15": 1, "16": 2, "17": 3, "20": 4, "21": 5, "22": 6, "23": 7})

    def test_numeric_keys_pass_through_and_names_ignore_case(self):
        self.assertEqual(lumetri_keys({"17": 104, 21: 5, "Contrast": 9}), {"17": 104, "21": 9})

    def test_unknown_name(self):
        with self.assertRaisesRegex(GradeError, "unknown Lumetri parameter 'warmth'"):
            lumetri_keys({"warmth": 3})

    def test_look_saturation_is_an_offset_from_100(self):
        self.assertEqual(look_lumetri(FILMIC), {"15": 3.0, "17": 90.0, "20": -0.05, "21": 18.0, "22": -8.0, "23": 12.0})
        self.assertEqual(look_lumetri({}), {"17": 100.0})


class PlanGradeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for f in ("a.mp4", "b.mp4"):
            (self.root / f).write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

    def compile(self, grade, shots=None):
        data = {"name": "GRADE", "format": {"duration": 20}, "grade": grade, "graphics": [],
                "shots": shots or [{"clip": "a.mp4", "in": 0, "out": 10}, {"clip": "b.mp4", "in": 10, "out": 20}]}
        (self.root / "edit.json").write_text(json.dumps(data))
        ops = compile_plan(load_plan(self.root / "edit.json"), load_design("cinematic-minimal"))
        return {o.get("id"): o for o in ops}

    def test_named_plan_grade(self):
        ops = self.compile({"lumetri": {"contrast": 18, "temperature": 3, "17": 90}})
        self.assertEqual(ops["SHOT_01"]["lumetri"], {"21": 18, "15": 3, "17": 90})

    def test_per_shot_lumetri_and_exposure_stack_on_the_base(self):
        ops = self.compile({"lumetri": {"exposure": 0.1, "contrast": 10}},
                           [{"clip": "a.mp4", "in": 0, "out": 10, "exposure": 0.2, "lumetri": {"contrast": 25, "shadows": 5}},
                            {"clip": "b.mp4", "in": 10, "out": 20}])
        self.assertEqual(ops["SHOT_01"]["lumetri"], {"20": 0.3, "21": 25, "23": 5})
        self.assertEqual(ops["SHOT_02"]["lumetri"], {"20": 0.1, "21": 10})

    def test_grade_file_supplies_the_look_and_matching(self):
        (self.root / "grade.json").write_text(json.dumps({"look": FILMIC, "match": {"offsets": {"a.mp4": -0.25, "b.mp4": 0.4}}}))
        ops = self.compile({"file": "grade.json", "lumetri": {"contrast": 12}},
                           [{"clip": "a.mp4", "in": 0, "out": 10}, {"clip": "b.mp4", "in": 10, "out": 20, "exposure": 0}])
        self.assertEqual(ops["SHOT_01"]["lumetri"], {"15": 3.0, "17": 90.0, "20": -0.3, "21": 12, "22": -8.0, "23": 12.0})
        self.assertEqual(ops["SHOT_02"]["lumetri"]["20"], -0.05)

    def test_unknown_names_are_plan_errors(self):
        with self.assertRaisesRegex(PlanError, "grade: unknown Lumetri parameter 'warmth'"):
            self.compile({"lumetri": {"warmth": 3}})
        with self.assertRaisesRegex(PlanError, r"shots\[0\]: unknown Lumetri parameter 'glow'"):
            self.compile({}, [{"clip": "a.mp4", "in": 0, "out": 10, "lumetri": {"glow": 1}}])
        with self.assertRaisesRegex(PlanError, "grade: file not found"):
            self.compile({"file": "missing.json"})


if __name__ == "__main__":
    unittest.main()
