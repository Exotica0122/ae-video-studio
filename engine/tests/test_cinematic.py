import unittest

from aestudio.components import REGISTRY
from aestudio.design import COMPONENTS, load_design
from aestudio.ops import validate_ops
from tests.helpers import make_ctx, voice

WORDS = [("모든", 0.10, 0.50), ("여정은", 0.50, 1.10), ("작은", 1.20, 1.60), ("한", 1.60, 1.80),
         ("걸음에서", 1.80, 2.60), ("시작됩니다.", 2.60, 3.50)]
LINES = [["모든 여정은"], ["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]]


def run(graphic, treatment, **ctx_kw):
    ctx = make_ctx("cinematic-minimal", voices={"N1": voice("N1", 10.0, WORDS)}, **ctx_kw)
    REGISTRY[(graphic["type"], treatment)](ctx, graphic, {})
    validate_ops(ctx.ops.items)
    return ctx, {o.get("id"): o for o in ctx.ops.items}


class CinematicTest(unittest.TestCase):
    def test_every_design_treatment_is_registered(self):
        for ref in ("notebook", "cinematic-minimal"):
            design = load_design(ref)
            for comp in COMPONENTS:
                self.assertIn((comp, design.treatment(comp)[0]), REGISTRY, f"{ref}: {comp}")

    def test_caption_line_fade(self):
        ctx, it = run({"type": "caption", "voice": "N1", "lines": LINES}, "line-fade")
        self.assertEqual(it["CAPTION_01_L1"]["position"], [1920.0, it["CAPTION_01_L1"]["position"][1]])
        hl = it["CAPTION_01_L2S2"]
        self.assertEqual(hl["color"], ctx.design.color("accent"))
        self.assertEqual(hl["font"], "NanumSquareNeoTTF-cBd")
        self.assertEqual(it["CAPTION_01_L1S1"]["color"], ctx.design.color("ink"))
        self.assertNotIn("CAPTION_01_CARD", it)
        shadows = [o for o in ctx.ops.items if o["op"] == "effect" and o["match"] == "ADBE Drop Shadow"]
        self.assertEqual(len(shadows), 4)
        self.assertIn("so((time-9.7)/0.5)", it["CAPTION_01"]["fade"])

    def test_quote_is_wrapped_in_marks(self):
        _, it = run({"type": "quote", "voice": "N1", "lines": LINES}, "line-fade")
        self.assertEqual(it["QUOTE_01_L1S1"]["text"], "“")
        last = [k for k in it if k and k.startswith("QUOTE_01_L2S")][-1]
        self.assertEqual(it[last]["text"], "”")

    def test_lower_third_rule_wipe(self):
        ctx, it = run({"type": "lower-third", "at": 5, "name": "이하늘", "role": "스튜디오 참가자"}, "rule-wipe")
        self.assertIn("eio((time-5.1)/0.6)", it["LOWER_THIRD_01_RULE"]["rect_expr"]["size"])
        self.assertEqual(it["LOWER_THIRD_01_NAME"]["reveal"]["by"], "chars")
        self.assertEqual(it["LOWER_THIRD_01_ROLE"]["tracking"], 120)

    def test_title_black_frame(self):
        _, it = run({"type": "title-page", "in": 0, "out": 6, "lines": [["함께 배우고,"]], "ref": "OPEN DAY"}, "black-frame")
        self.assertEqual(it["TITLE_01_BG"]["out"], 6.95)
        self.assertEqual(it["TITLE_01_L1"]["op"], "group")
        self.assertEqual(it["TITLE_01_REF"]["justify"], "center")

    def test_end_card_centered_stack(self):
        ctx, it = run({"type": "end-card", "in": 30, "title": "오픈 스튜디오", "year": 2027, "tagline": "누구나",
                       "rows": [{"label": "A", "values": ["1"]}, {"label": "B", "values": ["2", "3"]}, {"label": "C", "values": ["4"]}],
                       "photo": {"clip": "/tmp/c.mp4"}, "logo": {"file": "/tmp/l.png"}}, "centered-stack")
        self.assertEqual(it["END_01_BG"]["zoom"], 1.1)
        self.assertEqual([o["match"] for o in ctx.ops.items if o["op"] == "effect" and o["layer"] == "END_01_BG"], ["ADBE Gaussian Blur 2"])
        xs = [it[f"END_01_ROW{i}_LABEL"]["position"][0] for i in (1, 2, 3)]
        self.assertEqual(xs, [960.0, 1920.0, 2880.0])
        self.assertEqual(it["END_01_TITLE"]["justify"], "center")
        self.assertTrue(all(o["position"][1] < 2160 for o in ctx.ops.items if o["op"] == "text"))


if __name__ == "__main__":
    unittest.main()
