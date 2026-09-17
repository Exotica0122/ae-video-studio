import subprocess
import sys
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.design import load_design
from aestudio.jsx import emit_script
from aestudio.plan import load_plan

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo"


class DemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEMO / "transcripts" / "narration-1.json").exists():
            subprocess.run([sys.executable, str(DEMO / "make_media.py")], check=True)

    def test_demo_compiles_with_both_designs(self):
        plan = load_plan(DEMO / "edit.json")
        self.assertEqual({g["type"] for g in plan.graphics}, {"title-page", "caption", "quote", "lower-third", "end-card"})
        for ref in ("notebook", "cinematic-minimal"):
            ops = compile_plan(plan, load_design(ref))
            self.assertIn("AES.build(", emit_script(ops))
            self.assertGreater(len(ops), 60, ref)


if __name__ == "__main__":
    unittest.main()
