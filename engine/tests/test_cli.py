import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from aestudio.__main__ import main


def write_min_plan(root: Path) -> Path:
    for f in ("a.mp4", "n1.wav"):
        (root / f).write_text("x")
    (root / "n1.json").write_text(json.dumps({"words": [["모든", 0.1, 0.5], ["여정은", 0.5, 1.1]]}))
    plan = {"name": "CLI_DEMO", "format": {"duration": 10}, "shots": [{"clip": "a.mp4", "in": 0, "out": 10}],
            "voices": [{"id": "N1", "file": "n1.wav", "at": 1, "transcript": "n1.json"}],
            "graphics": [{"type": "caption", "voice": "N1", "lines": [["모든 여정은"]]}]}
    (root / "edit.json").write_text(json.dumps(plan))
    return root / "edit.json"


class CliTest(unittest.TestCase):
    def test_compile_writes_jsx(self):
        with tempfile.TemporaryDirectory() as d:
            plan = write_min_plan(Path(d))
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["compile", str(plan), "--design", "notebook"])
            self.assertEqual(code, 0)
            info = json.loads(out.getvalue())
            self.assertTrue(info["jsx"].endswith("build/CLI_DEMO.jsx"))
            self.assertIn("Paperlogy-5Medium", info["fonts"])
            self.assertIn("AES.build(", Path(info["jsx"]).read_text(encoding="utf-8"))

    def test_compile_defaults_project_to_build_folder(self):
        with tempfile.TemporaryDirectory() as d:
            plan = write_min_plan(Path(d))
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["compile", str(plan), "--design", "notebook"]), 0)
            jsx = Path(json.loads(out.getvalue())["jsx"]).read_text(encoding="utf-8")
            expected = str(Path(d).resolve() / "build" / "CLI_DEMO.aep")
            self.assertIn('"project":' + json.dumps(expected), jsx)

    def test_compile_creates_project_parent_folder(self):
        with tempfile.TemporaryDirectory() as d:
            plan = write_min_plan(Path(d))
            project = Path(d) / "elsewhere" / "deep" / "p.aep"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["compile", str(plan), "--design", "notebook", "--project", str(project)]), 0)
            self.assertTrue(project.parent.is_dir())
            self.assertFalse(project.exists())

    def test_next_version_never_reuses_an_existing_project(self):
        with tempfile.TemporaryDirectory() as d:
            plan = write_min_plan(Path(d))
            (Path(d) / "build").mkdir()
            (Path(d) / "build" / "CLI_DEMO.aep").write_text("x")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["compile", str(plan), "--design", "notebook", "--next-version"]), 0)
            jsx = Path(json.loads(out.getvalue())["jsx"])
            self.assertEqual(jsx.name, "CLI_DEMO-v02.jsx")
            text = jsx.read_text(encoding="utf-8")
            self.assertIn("CLI_DEMO-v02.aep", text)
            self.assertIn('"closeOpen":true', text)
            self.assertEqual(json.loads(jsx.with_suffix(".plan.json").read_text())["name"], "CLI_DEMO")

    def test_known_error_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["compile", "/nope/edit.json", "--design", "notebook"])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())

    def test_run_exit_code_follows_report(self):
        with tempfile.TemporaryDirectory() as d:
            jsx = Path(d) / "x.jsx"
            jsx.write_text("1")
            for report, expected in (({"ok": True}, 0), ({"ok": False, "expressionErrors": ["x"]}, 1)):
                with mock.patch("aestudio.__main__.Bridge") as bridge, redirect_stdout(io.StringIO()):
                    bridge.return_value.run.return_value = report
                    self.assertEqual(main(["run", str(jsx)]), expected)

    def test_run_exits_1_when_result_is_not_a_report(self):
        with tempfile.TemporaryDirectory() as d:
            jsx = Path(d) / "x.jsx"
            jsx.write_text("1")
            for result in ("not json at all", None, ["ok"], {"ok": "true"}, {"ok": True, "error": "boom"}):
                with mock.patch("aestudio.__main__.Bridge") as bridge, redirect_stdout(io.StringIO()):
                    bridge.return_value.run.return_value = result
                    self.assertEqual(main(["run", str(jsx)]), 1, result)

    def test_log_footage_summary_includes_images(self):
        with tempfile.TemporaryDirectory() as d:
            fake_log = {"clips": [{"name": "a.mp4"}], "audio": [], "images": [{"name": "p.jpg"}, {"name": "q.jpg"}],
                       "errors": []}
            with mock.patch("aestudio.__main__.log_footage", return_value=fake_log) as log_footage, \
                 redirect_stdout(io.StringIO()) as out:
                code = main(["log-footage", d, "--out", str(Path(d) / "analysis")])
            self.assertEqual(code, 0)
            log_footage.assert_called_once()
            summary = json.loads(out.getvalue())
            self.assertEqual(summary["clips"], 1)
            self.assertEqual(summary["images"], 2)
            self.assertEqual(summary["errors"], 0)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class QaDiffCliTest(unittest.TestCase):
    def test_qa_diff_writes_the_changes_section_with_stills_and_checks_them_for_people(self):
        from tests.test_videoqa import _clip
        from aestudio.videoqa import Finding
        with tempfile.TemporaryDirectory() as d:
            a, b, qa_dir = Path(d) / "v1.mp4", Path(d) / "v2.mp4", Path(d) / "qa"
            _clip(a)
            _clip(b, box_at=2.0)
            people = mock.Mock(return_value=[Finding("text-over-people:x", "ok", "none covered")])
            with mock.patch("aestudio.__main__.text_over_people", people), redirect_stdout(io.StringIO()):
                main(["qa", str(b), "--diff", str(a), "--out", str(qa_dir)])
            text = (qa_dir / "report-v01.md").read_text(encoding="utf-8")
            self.assertIn("## Changes vs previous", text)
            self.assertIn("Picture 0:02.", text)
            self.assertTrue(list((qa_dir / "stills").glob("prev-*.jpg")))
            self.assertEqual([p.name[:6] for p in people.call_args[0][0]], ["still-"])


if __name__ == "__main__":
    unittest.main()
