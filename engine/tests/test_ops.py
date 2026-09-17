import unittest

from aestudio.ops import Ops, OpsError, validate_ops

COMP = dict(name="C", width=3840, height=2160, fps=23.976, duration=10)


class OpsTest(unittest.TestCase):
    def test_uid_and_add(self):
        ops = Ops()
        self.assertEqual(ops.uid("CAPTION"), "CAPTION_01")
        self.assertEqual(ops.uid("CAPTION"), "CAPTION_02")
        ops.add("comp", **COMP)
        self.assertEqual(ops.add("group", id="G", parent=None), "G")
        self.assertEqual(ops.items[1], {"op": "group", "id": "G"})

    def test_duplicate_id(self):
        ops = Ops()
        ops.add("group", id="G")
        with self.assertRaisesRegex(OpsError, "duplicate id 'G'"):
            ops.add("rect", id="G", color=[1, 1, 1])

    def test_valid_list_passes(self):
        ops = Ops()
        ops.add("comp", **COMP)
        ops.add("group", id="G", fade="100")
        ops.add("text", id="T", parent="G", text="a", font="F", size=10, color=[0, 0, 0],
                expr={"opacity": 'thisComp.layer("G").effect("FADE")(1)'})
        ops.add("rect", id="R", color=[1, 1, 1], rect_expr={"size": 'var L=thisComp.layer("T");[1,1]'})
        ops.add("effect", layer="R", match="ADBE Noise", props={"1": {"expr": 'thisComp.layer("T").index'}})
        ops.add("order", layer="R", below=["T"])
        ops.add("expr", layer="G", exprs={"position": 'thisComp.layer("R").index;value'})
        validate_ops(ops.items)

    def test_reference_must_be_defined_earlier(self):
        ops = Ops()
        ops.add("comp", **COMP)
        ops.add("text", id="T", text="a", font="F", size=10, color=[0, 0, 0], expr={"position": 'thisComp.layer("LATER").index'})
        ops.add("group", id="LATER")
        with self.assertRaisesRegex(OpsError, "op 1 .*'LATER'"):
            validate_ops(ops.items)

    def test_missing_fields_and_first_op(self):
        with self.assertRaisesRegex(OpsError, "first op must be 'comp'"):
            validate_ops([{"op": "group", "id": "G"}])
        with self.assertRaisesRegex(OpsError, "missing 'font'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "text", "id": "T", "text": "a", "size": 1, "color": [0, 0, 0]}])
        with self.assertRaisesRegex(OpsError, "unknown op 'sparkle'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "sparkle"}])

    def test_parent_and_below_refs(self):
        with self.assertRaisesRegex(OpsError, "parent 'NOPE'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "group", "id": "G", "parent": "NOPE"}])
        with self.assertRaisesRegex(OpsError, "below 'NOPE'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "group", "id": "G"}, {"op": "order", "layer": "G", "below": ["NOPE"]}])


if __name__ == "__main__":
    unittest.main()
