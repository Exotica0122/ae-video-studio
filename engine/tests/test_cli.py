import io
import json
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


if __name__ == "__main__":
    unittest.main()
