import unittest

from aestudio.components.layout import (LayoutError, fade_ref, highlighter, paper_card, parse_line, place_block,
                                        schedule_times, segment_times, text_block)
from aestudio.ops import validate_ops
from tests.helpers import make_ctx

WORDS = [("모든", 0.10, 0.50), ("여정은", 0.50, 1.10), ("작은", 1.20, 1.60), ("한", 1.60, 1.80),
         ("걸음에서", 1.80, 2.60), ("시작됩니다.", 2.60, 3.50)]


class LayoutTest(unittest.TestCase):
    def test_parse_line_gaps(self):
        segs = parse_line(["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."], 30)
        self.assertEqual([(s.text, s.hl, s.gap) for s in segs],
                         [("작은", False, 0.0), ("한 걸음", True, 30.0), ("에서 시작됩니다.", False, 0.0)])
        self.assertEqual(parse_line(["a", " ", "b"], 10)[1].gap, 10.0)

    def test_parse_line_errors(self):
        for bad in ([], ["  "], [{"bold": "x"}], "text"):
            with self.assertRaises(LayoutError):
                parse_line(bad, 10)

    def test_segment_and_schedule_times(self):
        lines = [parse_line(["모든 여정은"], 30), parse_line(["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."], 30)]
        self.assertEqual(segment_times(lines, WORDS), [[[0.1, 0.5]], [[1.2], [1.6, 1.8], [2.2, 2.6]]])
        self.assertEqual(schedule_times(lines, 1.0, 0.1, 0.5), [[[1.0, 1.1]], [[1.7], [1.8, 1.9], [2.0, 2.1]]])

    def test_place_block(self):
        self.assertEqual(place_block("bottom-left", 2, 100, 3840, 2160), (345.6, 1736.0, "left"))
        self.assertEqual(place_block("top-center", 1, 100, 3840, 2160), (1920.0, 367.2, "center"))
        self.assertEqual(place_block("lower-center", 3, 100, 3840, 2160), (1920.0, 1636.0, "center"))
        with self.assertRaises(LayoutError):
            place_block("middle", 1, 100, 3840, 2160)

    def test_text_block_left_highlight_and_card(self):
        ctx = make_ctx()
        ctx.ops.add("group", id="G", fade="100")
        lines = [parse_line(["모든 여정은"], 30), parse_line(["작은 ", {"hl": "한 걸음"}, "에서"], 30)]
        times = [[[0.1, 0.5]], [[1.2], [1.6, 1.8], [2.2]]]
        style = lambda i, s: {"font": "F", "size": 100.0, "color": [0, 0, 0]}
        block = text_block(ctx, prefix="G", parent="G", lines=lines, times=times, x=300, y_first=1500, gap=130, style=style,
                           align="left", reveal={"dur": 0.35, "rise": 14, "blur": 6, "by": "words"}, opacity=fade_ref("G"), t_in=0, t_out=5)
        self.assertEqual(block.segments, [["G_L1S1"], ["G_L2S1", "G_L2S2", "G_L2S3"]])
        items = {o.get("id"): o for o in ctx.ops.items}
        self.assertEqual(items["G_L2S1"]["position"], [300, 1630])
        self.assertIn('thisComp.layer("G_L2S1")', items["G_L2S2"]["expr"]["position"])
        self.assertIn("+30.0,value[1]]", items["G_L2S2"]["expr"]["position"])
        self.assertEqual(items["G_L2S2"]["reveal"]["times"], [1.6, 1.8])
        self.assertEqual(items["G_L2S2"]["in"], 0)
        highlighter(ctx, id="HL", parent="G", target="G_L2S2", size=100, t0=1.65, dur=0.5, color=[1, 1, 0])
        self.assertIn("eio((time-1.65)/0.5)", items_of(ctx)["HL"]["rect_expr"]["size"])
        paper_card(ctx, id="CARD", parent="G", members=block.ids, below=block.ids + ["HL"], pad=(100, 60), color=[1, 1, 1], radius=18, noise=4)
        orders = [o for o in ctx.ops.items if o["op"] == "order"]
        self.assertEqual(orders[-1], {"op": "order", "layer": "CARD", "below": block.ids + ["HL"]})
        effects = [o["match"] for o in ctx.ops.items if o["op"] == "effect" and o["layer"] == "CARD"]
        self.assertEqual(effects, ["ADBE Noise", "ADBE Drop Shadow"])
        validate_ops(ctx.ops.items)

    def test_text_block_center_adds_line_groups(self):
        ctx = make_ctx()
        lines = [parse_line(["하나 ", "둘"], 30)]
        style = lambda i, s: {"font": "F", "size": 100.0, "color": [0, 0, 0]}
        block = text_block(ctx, prefix="C", parent=None, lines=lines, times=[[[0.0], [0.5]]], x=1920, y_first=1800, gap=130,
                           style=style, align="center", reveal={"dur": 0.5, "by": "words"})
        self.assertEqual(block.lines, ["C_L1"])
        items = ctx.ops.items
        self.assertEqual(items[1], {"op": "group", "id": "C_L1", "position": [1920, 1800]})
        self.assertEqual(items[2]["parent"], "C_L1")
        self.assertEqual(items[2]["position"], [0, 0])
        self.assertEqual(items[-1]["op"], "expr")
        self.assertIn("value[0]-(x0+x1)/2", items[-1]["exprs"]["position"])
        validate_ops(items)


def items_of(ctx):
    return {o.get("id"): o for o in ctx.ops.items}


if __name__ == "__main__":
    unittest.main()
