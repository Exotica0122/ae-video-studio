import json
import tempfile
import unittest
from pathlib import Path

from aestudio.audio import duck_keys
from aestudio.compiler import CompileError, compile_plan
from aestudio.components import REGISTRY
from aestudio.design import load_design
from aestudio.plan import load_plan
from tests.helpers import make_ctx

WORDS_A = [["하나", 0.1, 0.5], ["둘", 0.6, 1.0]]
WORDS_B = [["셋", 0.2, 0.7]]


def build_plan(root: Path, graphics=()):
    for f in ("a.mp4", "b.mp4", "n1.wav", "n2.wav", "m.wav", "s.wav"):
        (root / f).write_text("x")
    (root / "n1.json").write_text(json.dumps({"words": WORDS_A}))
    (root / "n2.json").write_text(json.dumps({"words": WORDS_B}))
    plan = {
        "name": "UNIT", "format": {"duration": 20},
        "grade": {"lumetri": {"17": 104}},
        "shots": [{"clip": "a.mp4", "in": 0, "out": 10}, {"clip": "b.mp4", "in": 10, "out": 20, "src_in": 2, "exposure": 0.2}],
        "voices": [{"id": "N1", "file": "n1.wav", "at": 2, "transcript": "n1.json"},
                   {"id": "N2", "file": "n2.wav", "at": 9, "transcript": "n2.json", "gain_db": -2}],
        "music": {"file": "m.wav", "gain_db": -6, "duck": {"under_voice": -14}},
        "sfx": [{"file": "s.wav", "at": 7.5, "gain_db": -8, "fade_before_voice": True}, {"file": "s.wav", "at": 15, "gain_db": -3}],
        "graphics": list(graphics),
    }
    (root / "edit.json").write_text(json.dumps(plan))
    return load_plan(root / "edit.json")


class CompilerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_media_audio_and_fade(self):
        ops = compile_plan(build_plan(self.root), load_design("notebook"))
        by_id = {o.get("id"): o for o in ops}
        self.assertEqual(ops[0]["op"], "comp")
        self.assertEqual(by_id["SHOT_01"]["lumetri"], {"17": 104})
        self.assertEqual(by_id["SHOT_02"]["lumetri"], {"17": 104, "20": 0.2})
        self.assertEqual(by_id["SHOT_02"]["src_in"], 2.0)
        self.assertEqual(by_id["VOICE_N2"]["gain_db"], -2.0)
        self.assertEqual(by_id["VOICE_N1"]["end"], 3.5)
        expected = [[t, round(db - 6, 3)] for t, db in duck_keys([(2.1, 3.0), (9.2, 9.7)], 20.0, under_voice=-14)]
        self.assertEqual(by_id["MUSIC"]["levels"], expected)
        self.assertEqual(by_id["SFX_01"]["levels"], [[8.2, -8], [9.1, -25]])
        self.assertEqual(by_id["SFX_02"]["gain_db"], -3.0)
        self.assertEqual(ops[-1]["id"], "FADE_OUT")
        self.assertIn("so((time-19.25)/0.7)", ops[-1]["expr"]["opacity"])

    def test_unregistered_treatment(self):
        plan = build_plan(self.root, graphics=[{"type": "lower-third", "at": 3, "name": "A", "role": "B"}])
        design = load_design("notebook")
        design.components["lower-third"] = {"treatment": "does-not-exist"}
        with self.assertRaisesRegex(CompileError, "no treatment 'does-not-exist' for 'lower-third'"):
            compile_plan(plan, design)

    def test_dispatches_to_registry(self):
        calls = []
        REGISTRY[("lower-third", "unit-test")] = lambda ctx, g, opts: calls.append((g["name"], opts, ctx.s))
        try:
            plan = build_plan(self.root, graphics=[{"type": "lower-third", "at": 3, "name": "A", "role": "B"}])
            design = load_design("notebook")
            design.components["lower-third"] = {"treatment": "unit-test", "x": 1}
            compile_plan(plan, design)
        finally:
            del REGISTRY[("lower-third", "unit-test")]
        self.assertEqual(calls, [("A", {"x": 1}, 1.0)])

    def test_context_helpers(self):
        ctx = make_ctx(width=1920, height=1080)
        self.assertEqual(ctx.s, 0.5)
        self.assertEqual(ctx.px(100), 50.0)
        self.assertEqual(ctx.size("label"), 32.0)


if __name__ == "__main__":
    unittest.main()
