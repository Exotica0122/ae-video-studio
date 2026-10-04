import json
import tempfile
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.components import DEFAULTS, REGISTRY
from aestudio.design import load_design
from aestudio.ops import validate_ops
from aestudio.plan import PlanError, load_plan
from tests.helpers import make_ctx, voice

WORDS = [("우리", 0.1, 0.4), ("아이들이", 0.4, 0.9), ("학교", 1.0, 1.5)]
PANEL = {"clip": "/m/p.mov", "x": 0, "y": 0, "w": 3840, "h": 2160, "sw": 1280, "sh": 720}


def run(graphic, treatment, **ctx_kw):
    ctx = make_ctx("cinematic-minimal", voices={"N1": voice("N1", 10.0, WORDS)}, **ctx_kw)
    REGISTRY[(graphic["type"], treatment)](ctx, graphic, {})
    validate_ops(ctx.ops.items)
    return ctx, {o.get("id"): o for o in ctx.ops.items}


def exprs_for(ctx, layer):
    return [o["exprs"] for o in ctx.ops.items if o["op"] == "expr" and o["layer"] == layer]


class BlockTest(unittest.TestCase):
    def test_kicker_rule_items_and_rows(self):
        g = {"type": "block", "in": 30, "out": 40, "x": 0.07, "y": 0.26, "scrim": "left", "kicker": "Today", "rule": True,
             "items": [{"lines": [["하나님의 ", {"hl": "기준"}]], "role": "body"}],
             "rows": [{"at": 32, "n": "01", "key": "진화론"}, {"at": 33, "key": "생명", "value": "선물", "key_color": "accent"}]}
        ctx, it = run(g, "positioned")
        self.assertEqual(it["BLOCK_01_KICK"]["text"], "TODAY")
        self.assertEqual(it["BLOCK_01_KICK"]["position"][0], round(3840 * 0.07, 3))
        self.assertTrue(it["BLOCK_01_SCRIM"]["file"].endswith("scrim-left.png"))
        self.assertIn("eio((time-30.1)/0.6)", it["BLOCK_01_RULE"]["rect_expr"]["size"])
        self.assertEqual(it["BLOCK_01_I1_L1S2"]["color"], ctx.design.color("accent"))
        self.assertEqual(it["BLOCK_01_I1_L1S2"]["font"], ctx.design.font("emphasis"))
        self.assertEqual(it["BLOCK_01_N1"]["text"], "01")
        self.assertEqual(it["BLOCK_01_K2"]["color"], ctx.design.color("accent"))
        self.assertEqual(it["BLOCK_01_V2"]["reveal"]["times"][0], 33.25)
        self.assertIn("BLOCK_01_DIV2", it)
        self.assertIn("eio((time-33.2)/0.6)", it["BLOCK_01_DIVEND"]["rect_expr"]["size"])

    def test_right_alignment_anchors_lines_on_their_right_edge(self):
        g = {"type": "block", "in": 4, "out": 8, "x": 0.94, "y": 0.8, "align": "right", "rule": True,
             "items": [{"lines": [["그곳에서 ", {"hl": "무엇을"}]]}]}
        ctx, it = run(g, "positioned")
        self.assertEqual(it["BLOCK_01_I1_L1"]["position"][0], round(3840 * 0.94, 3))
        self.assertIn("[value[0]-x1,value[1]]", exprs_for(ctx, "BLOCK_01_I1_L1")[0]["position"])
        self.assertIn(f"{round(3840 * 0.94 - 150, 3)}+150.0*k/2", it["BLOCK_01_RULE"]["rect_expr"]["center"])

    def test_line_at_sets_each_line_reveal(self):
        g = {"type": "block", "in": 69.7, "out": 75.7, "x": 0.05, "y": 0.2,
             "items": [{"lines": [["첫 줄"], ["둘째"], ["셋째 줄"]]}], "line_at": [70.0, 72.45, 73.5]}
        _, it = run(g, "positioned")
        self.assertEqual(it["BLOCK_01_I1_L1S1"]["reveal"]["times"], [70.0, 70.1])
        self.assertEqual(it["BLOCK_01_I1_L2S1"]["reveal"]["times"], [72.45])
        self.assertEqual(it["BLOCK_01_I1_L3S1"]["reveal"]["times"], [73.5, 73.6])

    def test_voice_drives_the_reveal_and_the_window(self):
        g = {"type": "block", "voice": "N1", "x": 0.06, "y": 0.1, "items": [{"lines": [["우리 아이들이"], ["학교"]]}]}
        _, it = run(g, "positioned")
        self.assertEqual(it["BLOCK_01_I1_L1S1"]["reveal"]["times"], [10.1, 10.4])
        self.assertEqual(it["BLOCK_01_I1_L2S1"]["reveal"]["times"], [11.0])
        self.assertIn("so((time-9.7)/0.5)", it["BLOCK_01"]["fade"])

    def test_rays_take_a_token_or_hex_colour(self):
        g = {"type": "block", "in": 55, "out": 58, "x": 0.07, "y": 0.34, "rays": 1.0, "items": []}
        ctx, it = run(g, "positioned")
        self.assertEqual(it["BLOCK_01_RAY1"]["color"], ctx.design.color("ink"))
        _, it = run(dict(g, ray_color="#FFE3AB"), "positioned")
        self.assertEqual(it["BLOCK_01_RAY4"]["color"], [1.0, 0.8902, 0.67059])


class ChipsSubtitleFadeTest(unittest.TestCase):
    def test_chips(self):
        g = {"type": "chips", "in": 72, "out": 75.6, "y": 0.885, "cell": 620, "scrim": "bottom", "hl": [1],
             "words": ["가치관", "세계관", "물질관"]}
        ctx, it = run(g, "divided")
        self.assertEqual([it[f"CHIPS_01_W{i}"]["text"] for i in (1, 2, 3)], ["가치관", "세계관", "물질관"])
        self.assertEqual(it["CHIPS_01_W2"]["color"], ctx.design.color("accent"))
        self.assertEqual(it["CHIPS_01_W1"]["position"][0], 1920 - 620)
        self.assertNotIn("CHIPS_01_DIV0", it)
        self.assertIn("CHIPS_01_DIV2", it)
        self.assertTrue(it["CHIPS_01_SCRIM"]["file"].endswith("scrim-caption.png"))

    def test_subtitle_shows_whole_lines(self):
        g = {"type": "subtitle", "in": 13.3, "out": 15.5, "lines": [["오늘날 우리가 살고 있는"]], "y": 0.955, "fade": 0.12}
        _, it = run(g, "whole-line", width=1920, height=1080)
        self.assertEqual(it["SUB_01_L1S1"]["reveal"]["times"], [13.32] * 4)
        self.assertIn("so((time-13.3)/0.12)", it["SUB_01"]["fade"])
        self.assertEqual(it["SUB_01_L1"]["position"], [960.0, round(1080 * 0.955, 3)])

    def test_subtitle_follows_the_voice_when_not_whole(self):
        _, it = run({"type": "subtitle", "voice": "N1", "lines": [["우리 아이들이"]], "whole": False}, "whole-line")
        self.assertEqual(it["SUB_01_L1S1"]["reveal"]["times"], [10.1, 10.4])

    def test_fade_in_from_black(self):
        _, it = run({"type": "fade-in", "in": 0.4, "out": 1.8}, "solid")
        solid = it["BLACK_IN_01"]
        self.assertEqual(solid["color"], [0, 0, 0])
        self.assertEqual((solid["in"], solid["out"]), (0, 1.85))
        self.assertEqual(solid["expr"]["opacity"], "100*(1-so((time-0.4)/1.4))")


class LabelScrimTest(unittest.TestCase):
    def test_label_and_by(self):
        g = {"type": "quote", "voice": "N1", "lines": [["우리 아이들이"]], "label": "Question", "by": "Voddie", "tint": 30}
        ctx, it = run(g, "label-scrim")
        self.assertEqual(it["SCRIM_01_LABEL"]["text"], "QUESTION")
        self.assertEqual(it["SCRIM_01_BY"]["color"], ctx.design.color("accent"))
        self.assertEqual(it["SCRIM_01_TINT"]["color"], ctx.design.color("paper"))
        self.assertTrue(it["SCRIM_01_IMG"]["file"].endswith("scrim-caption.png"))
        self.assertIn("QUOTE_01_L1S1", it)

    def test_caption_fields_route_to_the_new_graphics(self):
        cases = [({"black_in": True}, "BLACK_IN_01"), ({"sub": {"cx": 0.5, "y": 0.95, "whole": True}}, "SUB_01"),
                 ({"block": {"x": 0.1, "y": 0.2, "kicker": "K"}}, "BLOCK_01_KICK"),
                 ({"chips": {"y": 0.9, "words": ["a", "b"]}}, "CHIPS_01_W2")]
        for extra, expected in cases:
            g = {"type": "caption", "voice": None, "in": 1, "out": 3, "lines": [["x"]], **extra}
            _, it = run(g, "label-scrim")
            self.assertIn(expected, it, extra)
            self.assertNotIn("SCRIM_01", it)


class TitleEndLayoutTest(unittest.TestCase):
    def test_light_rays_title(self):
        g = {"type": "title-page", "in": 7.2, "out": 12.6, "ref": "사사기 2 : 10",
             "lines": [["그 세대의 사람도"], ["다른 세대는 ", {"hl": "알지 못하며"}]]}
        ctx, it = run(g, "light-rays")
        self.assertEqual(sum(1 for k in it if k and k.startswith("TITLE_01_RAY")), 4)
        self.assertEqual(it["TITLE_01_TINT"]["color"], ctx.design.color("paper"))
        self.assertEqual(it["TITLE_01_L2S2"]["color"], ctx.design.color("accent"))
        self.assertIn("TITLE_01_REF_L", it)
        self.assertEqual(it["TITLE_01_L1S1"]["reveal"]["times"], [7.7, 7.7, 7.7])

    def test_date_row_with_dates(self):
        g = {"type": "end-card", "in": 80, "title": "모임", "kicker": "Invite", "contact": "010", "contact_label": "문의",
             "dates": [{"num": "12", "label": "1차", "sub": "토"}, {"num": "19", "label": "2차"}]}
        _, it = run(g, "date-row")
        for key in ("END_01_RULE_TOP", "END_01_RULE_BOT", "END_01_D1_NUM", "END_01_D1_SUB", "END_01_D2_LAB", "END_01_DIV1",
                    "END_01_CONTACT_LAB", "END_01_CONTACT"):
            self.assertIn(key, it)
        self.assertNotIn("END_01_RULE", it)
        self.assertNotIn("END_01_MARK", it)

    def test_date_row_without_dates_and_a_white_logo(self):
        g = {"type": "end-card", "in": 84.5, "title": "홈스쿨링", "contact": "010",
             "logo": {"file": "/m/logo.png", "width": 820, "color": "white"}}
        _, it = run(g, "date-row")
        self.assertEqual(it["END_01_MARK"]["tint"], [1, 1, 1])
        self.assertIn("END_01_RULE", it)
        self.assertNotIn("END_01_RULE_TOP", it)
        self.assertNotIn("END_01_CONTACT_LAB", it)
        _, it = run(dict(g, logo={"file": "/m/logo.png", "tint": False}), "date-row")
        self.assertNotIn("tint", it["END_01_MARK"])

    def test_accent_band_layout(self):
        g = {"type": "layout", "in": 10, "out": 16, "panels": [PANEL], "kicker": "Family", "title": "가정"}
        ctx, it = run(g, "accent-band")
        self.assertEqual(it["LAYOUT_01_BAND"]["color"], ctx.design.color("accent"))
        self.assertEqual(it["LAYOUT_01_KICKER"]["text"], "FAMILY")
        self.assertIn("LAYOUT_01_TITLE", it)

    def test_crt_layout_bars_take_pixels_or_fractions(self):
        g = {"type": "layout", "in": 13.2, "out": 30.35, "band": False, "panels": [PANEL], "crt": True,
             "bar_top": 120, "bar_bottom": 0.15}
        ctx, it = run(g, "accent-band")
        self.assertNotIn("LAYOUT_01_BAND", it)
        self.assertEqual(it["LAYOUT_01_BAR_TOP"]["size"][1], 120)
        self.assertEqual(it["LAYOUT_01_BAR_BOT"]["size"][1], 324.0)
        self.assertEqual(it["LAYOUT_01_BAR_BOT"]["color"], ctx.design.color("shade"))
        self.assertTrue(it["LAYOUT_01_VIG"]["file"].endswith("crt-vignette.png"))
        self.assertEqual(it["LAYOUT_01_SCAN"]["count"], 361)
        effects = [o["match"] for o in ctx.ops.items if o["op"] == "effect" and o["layer"] == "LAYOUT_01_01"]
        self.assertEqual(effects, ["ADBE Tint", "ADBE Brightness & Contrast 2", "ADBE Noise"])

    def test_split_layout_quotes(self):
        g = {"type": "layout", "in": 20, "out": 30, "panels": [PANEL], "split": True,
             "quotes": [{"in": 21, "out": 25, "lines": [{"text": "첫 줄"}, {"text": "강조", "hl": True}], "note": "출처"}]}
        ctx, it = run(g, "accent-band")
        self.assertTrue(it["LAYOUT_01_SPLIT"]["file"].endswith("scrim-split.png"))
        self.assertEqual(it["LAYOUT_01_Q1_L2"]["color"], ctx.design.color("accent"))
        self.assertEqual(it["LAYOUT_01_Q1_NOTE"]["color"], ctx.design.color("accent2"))
        self.assertIn("eio((time-21.1)/0.6)", it["LAYOUT_01_Q1_RULE"]["rect_expr"]["size"])


class CompileNewTypesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for f in ("a.mp4", "n1.wav"):
            (self.root / f).write_text("x")
        (self.root / "n1.json").write_text(json.dumps({"words": [list(w) for w in WORDS]}))

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, graphics):
        data = {"name": "BLOCKS", "format": {"width": 1920, "height": 1080, "duration": 20},
                "shots": [{"clip": "a.mp4", "in": 0, "out": 20}],
                "voices": [{"id": "N1", "file": "n1.wav", "at": 2, "transcript": "n1.json"}], "graphics": graphics}
        (self.root / "edit.json").write_text(json.dumps(data))
        return load_plan(self.root / "edit.json")

    def test_new_types_compile_with_default_treatments_in_any_design(self):
        self.assertEqual(DEFAULTS, {"block": "positioned", "chips": "divided", "subtitle": "whole-line", "fade-in": "solid"})
        plan = self.plan([
            {"type": "fade-in", "in": 0, "out": 1.5},
            {"type": "block", "voice": "N1", "x": 0.06, "y": 0.1, "kicker": "Question", "items": [{"lines": [["우리 아이들이"]]}]},
            {"type": "chips", "in": 5, "out": 8, "y": 0.88, "words": ["가치관", "세계관"]},
            {"type": "subtitle", "in": 9, "out": 11, "lines": [["실제 학교 선생님들"]]},
        ])
        for design in ("notebook", "cinematic-minimal"):
            ids = {o.get("id") for o in compile_plan(plan, load_design(design))}
            self.assertTrue({"BLACK_IN_01", "BLOCK_01_KICK", "CHIPS_01_W2", "SUB_01_L1S1"} <= ids, design)

    def test_plan_rejects_incomplete_new_types(self):
        bad = [{"type": "chips", "in": 1, "out": 2},
               {"type": "fade-in", "in": 0},
               {"type": "block", "in": 1, "out": 2, "items": []},
               {"type": "subtitle", "in": 1, "out": 2},
               {"type": "block", "voice": "NOPE", "x": 0, "y": 0}]
        with self.assertRaises(PlanError) as cm:
            self.plan(bad)
        msg = str(cm.exception)
        for text in ("'words' must be", "a fade-in needs", "needs 'x' and 'y'", "'lines' must be", "unknown voice 'NOPE'"):
            self.assertIn(text, msg)


if __name__ == "__main__":
    unittest.main()
