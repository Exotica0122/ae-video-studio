"""Live test: needs After Effects open with the MCP Bridge Auto panel (Auto-run on) and a NEW, unsaved project.

The first run saves examples/demo/build/demo.aep. Re-runs need that .aep opened in After Effects first (or deleted):
the build refuses to save an unsaved project over an existing file.

Run from engine/:  AESTUDIO_AE=1 python3 -m unittest tests.ae.test_demo_in_after_effects -v
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from aestudio.__main__ import main

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "examples" / "demo"
STILLS = DEMO / "build" / "stills"
TIMES = (3.5, 10.5, 16.5, 25.0, 37.0)   # title, caption, lower third + quote, caption, end card


@unittest.skipUnless(os.environ.get("AESTUDIO_AE") == "1", "set AESTUDIO_AE=1 with After Effects open")
class DemoInAfterEffects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEMO / "media" / "shot_a.mp4").exists():
            subprocess.run([sys.executable, str(DEMO / "make_media.py")], check=True)

    def test_build_both_designs_and_save_stills(self):
        project = DEMO / "build" / "demo.aep"
        for ref in ("notebook", "cinematic-minimal"):
            comp = f"DEMO_{ref.upper().replace('-', '_')}"
            code = main(["build", str(DEMO / "edit.json"), "--design", ref, "--name", comp, "--project", str(project), "--timeout", "900"])
            self.assertEqual(code, 0, f"{ref}: build report not ok (see printed report)")
            for t in TIMES:
                out = STILLS / f"{ref}_{t:05.1f}.png"
                self.assertEqual(main(["still", "--comp", comp, "--time", str(t), "--out", str(out)]), 0)
                self.assertGreater(out.stat().st_size, 10_000)
        self.assertTrue(project.exists())
