import json
import tempfile
import unittest
from pathlib import Path

from aestudio import designgen
from aestudio.design import COMPONENTS, ROLES, DesignError, load_design
from aestudio.components import REGISTRY

LOG = {"clips": [
    {"name": "a.mp4", "path": "/tmp/a.mp4", "duration": 14.0, "luma": 0.62, "width": 1920, "height": 1080,
     "frames": [{"at": 0.5, "file": "frames/a_0.5.jpg", "luma": 0.62, "colors": [[240, 170, 60], [30, 40, 70], [200, 150, 90], [20, 20, 25]]}]},
    {"name": "b.mp4", "path": "/tmp/b.mp4", "duration": 12.0, "luma": 0.41, "width": 1920, "height": 1080,
     "frames": [{"at": 0.5, "file": "frames/b_0.5.jpg", "luma": 0.41, "colors": [[60, 110, 90], [40, 60, 55], [70, 120, 100], [30, 50, 45]]}]}],
    "audio": [], "errors": []}


class DesignGenTest(unittest.TestCase):
    def test_archetypes_are_valid_and_use_registered_treatments(self):
        archetypes = designgen.load_archetypes()
        self.assertGreaterEqual(len(archetypes), 3)
        for arch in archetypes:
            self.assertEqual(set(arch["treatments"]), set(COMPONENTS), arch["id"])
            for component, treatment in arch["treatments"].items():
                self.assertIn((component, treatment), REGISTRY, f"{arch['id']}: {component}/{treatment}")

    def test_accent_from_footage_picks_a_saturated_colour(self):
        accent = designgen.accent_from_footage(LOG)
        self.assertRegex(accent, r"^#[0-9A-Fa-f]{6}$")
        self.assertNotEqual(accent.lower(), "#c9a46a")          # not the fallback
        self.assertEqual(designgen.accent_from_footage({"clips": []}), "#C9A46A")

    def test_propose_returns_distinct_complete_drafts(self):
        drafts = designgen.propose(["warm", "friendly"], log=LOG)
        self.assertGreaterEqual(len(drafts), 2)
        self.assertEqual(len({d.id for d in drafts}), len(drafts))
        for draft in drafts:
            recipe = draft.recipe
            self.assertEqual(set(recipe["tokens"]["type"]), set(ROLES), draft.id)
            self.assertEqual(set(recipe["components"]), set(COMPONENTS), draft.id)
            for role, spec in recipe["tokens"]["type"].items():
                self.assertTrue(spec["font"] and spec["size"] > 0, f"{draft.id}/{role}")
            self.assertEqual(draft.notes, [], draft.id)         # installed_only=True by default

    def test_saved_draft_loads_as_a_design(self):
        draft = designgen.propose(["calm"], log=LOG)[0]
        with tempfile.TemporaryDirectory() as d:
            path = designgen.save_design(draft, Path(d) / "design.json")
            design = load_design(path)
        self.assertEqual(design.id, draft.id)
        self.assertEqual(set(design.components), set(COMPONENTS))
        self.assertTrue(design.fonts())

    def test_a_rejected_draft_leaves_the_previous_design_intact(self):
        good = designgen.propose(["calm"], log=LOG)[0]
        with tempfile.TemporaryDirectory() as d:
            path = designgen.save_design(good, Path(d) / "design.json")
            before = path.read_text(encoding="utf-8")
            broken = designgen.Draft(id="broken", name="broken", mood=[], recipe={"id": "broken"})
            with self.assertRaises(DesignError):
                designgen.save_design(broken, path)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertEqual([p.name for p in Path(d).iterdir()], ["design.json"])

    def test_style_frame_plan_is_a_valid_edit_plan(self):
        from aestudio.plan import load_plan
        draft = designgen.propose(["warm"], log=LOG)[0]
        with tempfile.TemporaryDirectory() as d:
            for name in ("a.mp4", "b.mp4"):
                (Path(d) / name).write_text("x")
            log = json.loads(json.dumps(LOG).replace("/tmp/", str(Path(d)) + "/"))
            plan_path = designgen.style_frame_plan(draft, log, Path(d) / "style", duration=6.0)
            plan = load_plan(plan_path)
        self.assertEqual(plan.format.duration, 6.0)
        self.assertEqual(plan.voices, [])
        self.assertEqual({g["type"] for g in plan.graphics}, {"caption", "lower-third", "end-card"})
        self.assertTrue(plan.shots)

    def test_propose_without_a_log_still_works(self):
        drafts = designgen.propose(["modern"], log=None)
        self.assertTrue(drafts)
        self.assertEqual(drafts[0].recipe["tokens"]["palette"]["accent"][:1], "#")


if __name__ == "__main__":
    unittest.main()
