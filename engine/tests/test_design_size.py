import json
import tempfile
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.design import DESIGNS_DIR, load_design
from aestudio.plan import PlanError, load_plan

GRAPHICS = [
    {"type": "layout", "in": 2, "out": 8, "band": False, "crt": True, "bar_top": 60, "bar_bottom": 0.15,
     "panels": [{"clip": "a.mp4", "x": 0, "y": 0, "w": 1920, "h": 1080, "sw": 1280, "sh": 720}]},
    {"type": "layout", "in": 9, "out": 14, "kicker": "Two",
     "panels": [{"clip": "a.mp4", "x": 100, "y": 50, "w": 800, "h": 600, "sw": 1280, "sh": 720},
                {"clip": "a.mp4", "x": 1000, "y": 50, "w": 820, "h": 600, "sw": 1280, "sh": 720}]},
    {"type": "block", "in": 15, "out": 19, "x": 0.06, "y": 0.1, "kicker": "Question", "items": [{"lines": [["학교"]]}]},
]


class DesignSizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.mp4").write_text("x")
        design = json.loads((DESIGNS_DIR / "cinematic-minimal" / "design.json").read_text(encoding="utf-8"))
        design["components"]["layout"] = {"treatment": "accent-band"}
        (self.root / "design.json").write_text(json.dumps(design))
        self.design = load_design(self.root / "design.json")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, width, height, design_size=None):
        data = {"name": "SCALE", "format": {"width": width, "height": height, "duration": 20},
                "shots": [{"clip": "a.mp4", "in": 0, "out": 20}], "graphics": GRAPHICS}
        if design_size:
            data["design_size"] = design_size
        (self.root / "edit.json").write_text(json.dumps(data))
        return load_plan(self.root / "edit.json")

    def assertDoubled(self, big, small, key):
        for b, v in zip(big if isinstance(big, list) else [big], small if isinstance(small, list) else [small]):
            self.assertAlmostEqual(b, 2 * v, delta=0.01, msg=key)

    def ops(self, *args):
        return {o.get("id"): o for o in compile_plan(self.plan(*args), self.design)}

    def test_a_1080_plan_rendered_at_4k_doubles_every_coordinate(self):
        hd = self.ops(1920, 1080, [1920, 1080])
        uhd = self.ops(3840, 2160, [1920, 1080])
        for key in ("LAYOUT_01_01", "LAYOUT_02_01", "LAYOUT_02_02"):
            for field in ("mask", "position", "width"):
                self.assertDoubled(uhd[key][field], hd[key][field], f"{key}.{field}")
        for key in ("LAYOUT_01_BAR_TOP", "LAYOUT_01_BAR_BOT"):
            self.assertDoubled(uhd[key]["size"], hd[key]["size"], key)
            self.assertDoubled(uhd[key]["center"], hd[key]["center"], key)
        self.assertEqual(uhd["LAYOUT_01_BAR_TOP"]["size"][1], 120)
        self.assertDoubled(uhd["BLOCK_01_KICK"]["position"], hd["BLOCK_01_KICK"]["position"], "kicker")
        self.assertDoubled(uhd["BLOCK_01_KICK"]["size"], hd["BLOCK_01_KICK"]["size"], "kicker")

    def test_matches_a_plan_written_at_4k_by_hand(self):
        scaled = self.ops(3840, 2160, [1920, 1080])
        plan = self.plan(3840, 2160)
        for g in plan.graphics:
            for p in g.get("panels") or []:
                p.update({k: p[k] * 2 for k in ("x", "y", "w", "h")})
        plan.graphics[0]["bar_top"] = 120
        by_hand = {o.get("id"): o for o in compile_plan(plan, self.design)}
        self.assertEqual(scaled, by_hand)

    def test_without_design_size_pixels_are_comp_pixels(self):
        ops = self.ops(3840, 2160)
        self.assertEqual(ops["LAYOUT_01_01"]["mask"], [1920, 1080])
        self.assertEqual(ops["LAYOUT_01_BAR_TOP"]["size"][1], 60)

    def test_design_size_is_validated(self):
        for bad in ([1920], [0, 1080], "1920x1080", [True, 1080]):
            with self.assertRaises(PlanError, msg=bad):
                self.plan(3840, 2160, bad)


if __name__ == "__main__":
    unittest.main()
