import unittest

from aestudio.components import REGISTRY
from aestudio.ops import validate_ops
from tests.helpers import make_ctx, voice

WORDS = [("모든", 0.10, 0.50), ("여정은", 0.50, 1.10), ("작은", 1.20, 1.60), ("한", 1.60, 1.80),
         ("걸음에서", 1.80, 2.60), ("시작됩니다.", 2.60, 3.50)]
CAPTION = {"type": "caption", "voice": "N1", "lines": [["모든 여정은"], ["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]]}


def by_id(ctx):
    return {o.get("id"): o for o in ctx.ops.items}


class NotebookCaptionTest(unittest.TestCase):
    def build(self, graphic, width=3840):
        ctx = make_ctx("notebook", voices={"N1": voice("N1", 10.0, WORDS)}, width=width, height=width * 9 // 16)
        REGISTRY[(graphic["type"], "paper-card" if graphic["type"] in ("caption", "quote") else "paper-tab")](ctx, graphic, {})
        validate_ops(ctx.ops.items)
        return ctx

    def test_caption_timing_style_and_card(self):
        ctx = self.build(CAPTION)
        items = by_id(ctx)
        group = items["CAPTION_01"]
        self.assertIn("so((time-9.8)/0.35)", group["fade"])
        self.assertIn("(time-13.6)/0.4", group["fade"])         # out = offset 13.5 + 0.5 = 14.0; fade-out starts 0.4 s earlier
        seg = items["CAPTION_01_L2S2"]
        self.assertEqual(seg["text"], "한 걸음")
        self.assertEqual(seg["font"], "Paperlogy-7Bold")         # line with a highlight uses the emphasis role
        self.assertEqual(items["CAPTION_01_L1S1"]["font"], "Paperlogy-5Medium")
        self.assertEqual(seg["reveal"]["times"], [11.6, 11.8])
        self.assertIn("eio((time-11.65)/0.5)", items["CAPTION_01_L2S2_HL"]["rect_expr"]["size"])
        card = [o for o in ctx.ops.items if o["op"] == "order" and o["layer"] == "CAPTION_01_CARD"][0]
        self.assertIn("CAPTION_01_L2S2_HL", card["below"])
        self.assertEqual(items["CAPTION_01_CARD"]["color"], ctx.design.color("paper"))

    def test_quote_has_mark_and_default_place(self):
        g = dict(CAPTION, type="quote")
        items = by_id(self.build(g))
        self.assertEqual(items["QUOTE_01_MARK"]["text"], "“")
        self.assertEqual(items["QUOTE_01_L1S1"]["font"], "Paperlogy-6SemiBold")
        self.assertEqual(items["QUOTE_01"]["anchor"][0], 2112.0)   # top-right: 0.55 * 3840

    def test_scales_with_width(self):
        items = by_id(self.build(CAPTION, width=1920))
        self.assertEqual(items["CAPTION_01_L1S1"]["size"], 50.0)

    def test_lower_third(self):
        ctx = self.build({"type": "lower-third", "at": 5, "name": "이하늘", "role": "스튜디오 참가자"})
        items = by_id(ctx)
        self.assertIn("(time-8.8)/0.45", items["LOWER_THIRD_01"]["fade"])    # dur 4.25 → out 9.25; fade-out starts 0.45 s earlier
        self.assertEqual(items["LOWER_THIRD_01_NAME"]["text"], "이하늘")
        self.assertEqual(items["LOWER_THIRD_01_ROLE"]["color"], ctx.design.color("paper"))
        pill = items["LOWER_THIRD_01_PILL"]
        self.assertEqual(pill["color"], ctx.design.color("ink"))
        self.assertIn("bo((time-5.35)/0.45)", pill["expr"]["scale"])
        self.assertIn("eio((time-5.6)/0.55)", items["LOWER_THIRD_01_NAME_HL"]["rect_expr"]["size"])
        self.assertIn("LOWER_THIRD_01_CARD", items)


if __name__ == "__main__":
    unittest.main()
