import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aestudio import render as r


class RenderTest(unittest.TestCase):
    def test_find_aerender_picks_newest(self):
        with tempfile.TemporaryDirectory() as d:
            for year in ("2025", "2026"):
                p = Path(d) / f"Adobe After Effects {year}"
                p.mkdir()
                (p / "aerender").write_text("")
            self.assertEqual(r.find_aerender(Path(d)).parent.name, "Adobe After Effects 2026")
            with self.assertRaises(r.RenderError):
                r.find_aerender(Path(d) / "nothing")

    def test_cmd(self):
        cmd = r.aerender_cmd("/ae/aerender", "/p.aep", "DEMO", "/out/a.mov")
        self.assertEqual(cmd, ["/ae/aerender", "-project", "/p.aep", "-comp", "DEMO", "-RStemplate", "Best Settings",
                               "-OMtemplate", "High Quality", "-output", "/out/a.mov", "-mem_usage", "50", "70",
                               "-v", "ERRORS_AND_PROGRESS"])

    def test_refuses_when_after_effects_is_open(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "p.aep"
            project.write_text("x")
            with mock.patch.object(r, "ae_ui_running", return_value=True):
                with self.assertRaisesRegex(r.RenderError, "After Effects is open"):
                    r.render(project, "DEMO", Path(d) / "a.mov", aerender="/bin/true")

    def test_render_success_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            project, out = Path(d) / "p.aep", Path(d) / "exports" / "a.mov"
            project.write_text("x")
            fake = Path(d) / "fake_aerender.sh"
            fake.write_text('#!/bin/sh\nwhile [ "$1" != "-output" ]; do shift; done\necho rendered > "$2"\n')
            fake.chmod(0o755)
            with mock.patch.object(r, "ae_ui_running", return_value=False):
                self.assertEqual(r.render(project, "DEMO", out, aerender=str(fake)), out.resolve())
                self.assertTrue(out.with_name("a.mov.log").exists())
                with self.assertRaisesRegex(r.RenderError, "aerender failed"):
                    r.render(project, "DEMO", Path(d) / "b.mov", aerender="/usr/bin/false")

    def test_stale_output_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            project, out = Path(d) / "p.aep", Path(d) / "a.mov"
            project.write_text("x")
            with mock.patch.object(r, "ae_ui_running", return_value=False):
                for fake in ("/usr/bin/false", "/usr/bin/true"):   # fails, or exits 0 without writing the output
                    out.write_text("old render")
                    with self.assertRaisesRegex(r.RenderError, "aerender failed"):
                        r.render(project, "DEMO", out, aerender=fake)
                    self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
