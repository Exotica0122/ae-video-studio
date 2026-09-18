import json
import tempfile
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.design import load_design
from aestudio.plan import PlanError, load_plan

LINES = [["이 화면의 글자 크기와"], ["색이 ", {"hl": "잘 보이는지"}, " 확인해 주세요."]]


def write(root: Path, graphic: dict) -> Path:
    (root / "a.mp4").write_text("x")
    plan = {"name": "STYLE", "format": {"duration": 6},
            "shots": [{"clip": "a.mp4", "in": 0, "out": 6}], "voices": [], "graphics": [graphic]}
    (root / "edit.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return root / "edit.json"


class VoicelessCaptionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_accepts_a_voiceless_caption_with_times(self):
        plan = load_plan(write(self.root, {"type": "caption", "voice": None, "lines": LINES, "in": 0.3, "out": 3.2}))
        self.assertIsNone(plan.graphics[0]["voice"])

    def test_plan_rejects_a_voiceless_caption_without_times(self):
        with self.assertRaisesRegex(PlanError, "needs 'in' and 'out'"):
            load_plan(write(self.root, {"type": "caption", "lines": LINES}))

    def test_plan_still_rejects_an_unknown_voice(self):
        with self.assertRaisesRegex(PlanError, "unknown voice 'N9'"):
            load_plan(write(self.root, {"type": "caption", "voice": "N9", "lines": LINES, "in": 0, "out": 3}))

    def test_both_designs_compile_a_voiceless_caption_on_a_schedule(self):
        path = write(self.root, {"type": "caption", "voice": None, "lines": LINES, "in": 0.3, "out": 3.2})
        plan = load_plan(path)
        for ref in ("notebook", "cinematic-minimal"):
            ops = compile_plan(plan, load_design(ref))
            texts = [o for o in ops if o["op"] == "text"]
            self.assertTrue(texts, ref)
            first = texts[0]["reveal"]["times"]
            self.assertEqual(first[0], 0.65, ref)                      # in + 0.35
            self.assertEqual(first[1], 0.77, ref)                      # + 0.12 per word
            later = texts[-1]["reveal"]["times"]
            self.assertGreater(later[0], first[-1], ref)               # later lines come after
            highlights = [o for o in ops if o["op"] == "rect" and o["id"].endswith("_HL")]
            if ref == "notebook":
                self.assertTrue(highlights)                            # marker still keyed to its word


if __name__ == "__main__":
    unittest.main()
