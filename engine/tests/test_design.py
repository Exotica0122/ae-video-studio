import json
import tempfile
import unittest
from pathlib import Path

from aestudio.design import COMPONENTS, DesignError, load_design


class DesignTest(unittest.TestCase):
    def test_builtin_designs_load(self):
        for ref in ("notebook", "cinematic-minimal"):
            d = load_design(ref)
            self.assertEqual(d.id, ref)
            self.assertEqual(set(d.components), set(COMPONENTS))
            self.assertEqual(len(d.color("ink")), 3)
            self.assertGreater(d.size("headline"), 0)

    def test_designs_are_actually_different(self):
        a, b = load_design("notebook"), load_design("cinematic-minimal")
        self.assertNotEqual(a.fonts(), b.fonts())
        self.assertNotEqual(a.color("paper"), b.color("paper"))
        self.assertNotEqual({c: a.treatment(c)[0] for c in COMPONENTS}, {c: b.treatment(c)[0] for c in COMPONENTS})

    def test_treatment_returns_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads((Path(__file__).resolve().parents[2] / "designs/notebook/design.json").read_text(encoding="utf-8"))
            raw["components"]["caption"] = {"treatment": "paper-card", "tilt": 2}
            p = Path(tmp) / "d.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(load_design(p).treatment("caption"), ("paper-card", {"tilt": 2}))

    def test_rejects_missing_role_and_bad_colour(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads((Path(__file__).resolve().parents[2] / "designs/notebook/design.json").read_text(encoding="utf-8"))
            del raw["tokens"]["type"]["label"]
            raw["tokens"]["palette"]["ink"] = "navy"
            p = Path(tmp) / "d.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(DesignError) as cm:
                load_design(p)
            self.assertIn("type role 'label'", str(cm.exception))
            self.assertIn("palette 'ink'", str(cm.exception))

    def test_unknown_design_id(self):
        with self.assertRaisesRegex(DesignError, "design not found"):
            load_design("does-not-exist")


if __name__ == "__main__":
    unittest.main()
