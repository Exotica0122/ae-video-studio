import unittest

from aestudio.components import REGISTRY
from aestudio.ops import validate_ops
from tests.helpers import make_ctx

TITLE = {"type": "title-page", "in": 0, "out": 6.5, "lines": [["함께 배우고,"], ["함께 ", {"hl": "자라는"}, " 시간"]], "ref": "OPEN DAY"}
END = {"type": "end-card", "in": 30, "title": "오픈 스튜디오", "year": 2027, "tagline": "누구나 시작할 수 있는 자리",
       "rows": [{"label": "신청 기간", "values": ["9월 1일 – 9월 20일"]}, {"label": "문의", "values": ["사무실", "010-0000-0000"]}],
       "photo": {"clip": "/tmp/c.mp4", "src_in": 2}, "logo": {"file": "/tmp/logo.png"}}


def items(ctx):
    return {o.get("id"): o for o in ctx.ops.items}


class NotebookPagesTest(unittest.TestCase):
    def test_title_page(self):
        ctx = make_ctx("notebook")
        REGISTRY[("title-page", "notebook-page")](ctx, TITLE, {})
        validate_ops(ctx.ops.items)
        it = items(ctx)
        self.assertIn("si((time-6.5)/0.7)", it["TITLE_01"]["expr"]["position"])
        self.assertEqual(it["TITLE_01_PAPER"]["out"], 7.25)
        self.assertEqual(it["TITLE_01_RULES"]["count"], 23)
        self.assertEqual(it["TITLE_01_L1S1"]["font"], "MaruBuri-Bold")
        self.assertEqual(it["TITLE_01_L1S1"]["reveal"]["times"], [1.0, 1.09])
        self.assertEqual(it["TITLE_01_L2S2"]["reveal"]["times"], [1.62])
        self.assertIn("eio((time-2.07)/0.6)", it["TITLE_01_L2S2_HL"]["rect_expr"]["size"])
        self.assertEqual(it["TITLE_01_REF"]["reveal"]["times"][0], 2.51)

    def test_end_card(self):
        ctx = make_ctx("notebook", duration=40.0)
        ctx.grade = {"lumetri": {"17": 104}}
        REGISTRY[("end-card", "notebook-page")](ctx, END, {})
        validate_ops(ctx.ops.items)
        it = items(ctx)
        photo = it["END_01_POLAROID_PHOTO"]
        self.assertEqual((photo["op"], photo["parent"], photo["start"], photo["end"], photo["src_in"]), ("footage", "END_01_POLAROID", 30.0, 40.0, 2))
        self.assertEqual(photo["lumetri"], {"17": 104})
        self.assertEqual(it["END_01_YEAR"]["text"], "2027")
        self.assertEqual(it["END_01_TITLE"]["reveal"]["by"], "chars")
        self.assertEqual(len(it["END_01_TITLE"]["reveal"]["times"]), len("오픈 스튜디오"))
        self.assertEqual(it["END_01_ROW2_VALUE2"]["text"], "010-0000-0000")
        self.assertAlmostEqual(it["END_01_ROW2_VALUE2"]["position"][1], it["END_01_ROW2_VALUE1"]["position"][1] + 92, places=2)
        self.assertEqual(it["END_01_LOGO"]["tint"], ctx.design.color("ink"))
        self.assertIn("so((time-33.9)/0.5)", it["END_01_LOGO"]["expr"]["opacity"])

    def test_end_card_minimal(self):
        ctx = make_ctx("notebook")
        REGISTRY[("end-card", "notebook-page")](ctx, {"type": "end-card", "in": 10, "title": "T"}, {})
        validate_ops(ctx.ops.items)
        self.assertNotIn("END_01_LOGO", items(ctx))
        self.assertNotIn("END_01_POLAROID_PHOTO", items(ctx))


if __name__ == "__main__":
    unittest.main()
