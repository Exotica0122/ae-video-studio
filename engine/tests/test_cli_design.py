import io
import json
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from aestudio.__main__ import main

LOG = {"clips": [{"name": "a.mp4", "path": "", "duration": 14.0, "luma": 0.6, "width": 1920, "height": 1080,
                  "frames": [{"at": 0.5, "file": "frames/a_0.5.jpg", "luma": 0.6,
                              "colors": [[240, 170, 60], [30, 40, 70], [200, 150, 90], [20, 20, 25]]}]}],
       "audio": [], "errors": []}


class CliDesignTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analysis = self.root / "analysis"
        (self.analysis / "frames").mkdir(parents=True)
        (self.analysis / "frames" / "a_0.5.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        clip = self.root / "a.mp4"
        clip.write_text("x")
        log = json.loads(json.dumps(LOG))
        log["clips"][0]["path"] = str(clip)
        (self.analysis / "footage.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        self.preview = self.root / "preview"

    def tearDown(self):
        self.tmp.cleanup()

    def _propose(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-propose", "--analysis", str(self.analysis), "--out", str(self.preview),
                         "--mood", "warm", "--mood", "modern"])
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_propose_renders_mockups(self):
        info = self._propose()
        self.assertTrue(info["drafts"])
        self.assertTrue(Path(info["index"]).exists())
        self.assertTrue((self.preview / "drafts.json").exists())

    def test_choose_writes_a_design(self):
        info = self._propose()
        design_path = self.root / "plan" / "design.json"
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-choose", "--dir", str(self.preview), "--out", str(design_path),
                         "--id", info["drafts"][0]])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["id"], info["drafts"][0])
        recipe = json.loads(design_path.read_text(encoding="utf-8"))
        self.assertEqual(recipe["id"], info["drafts"][0])

    def _drafts_json_with_an_uninstalled_font(self):
        drafts = json.loads((self.preview / "drafts.json").read_text(encoding="utf-8"))
        drafts = drafts[:1]
        drafts[0]["tokens"]["type"]["headline"] = {"font": "GowunBatang-Bold", "family": "Gowun Batang", "size": 150}
        drafts[0]["_notes"] = ["install Gowun Batang first: SIL Open Font License 1.1 — https://example.test"]
        (self.preview / "drafts.json").write_text(json.dumps(drafts, ensure_ascii=False), encoding="utf-8")
        return drafts[0]["id"]

    def test_choose_warns_about_an_uninstalled_font(self):
        self._propose()
        draft_id = self._drafts_json_with_an_uninstalled_font()
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            code = main(["design-choose", "--dir", str(self.preview), "--out", str(self.root / "design.json"),
                         "--id", draft_id])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["id"], draft_id)
        warnings = err.getvalue()
        self.assertIn("install Gowun Batang first", warnings)
        self.assertIn("GowunBatang-Bold", warnings)

    def test_choose_without_a_choice_fails(self):
        self._propose()
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = main(["design-choose", "--dir", str(self.preview), "--out", str(self.root / "d.json")])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())

    def test_preview_no_wait_prints_a_url(self):
        self._propose()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-preview", "--dir", str(self.preview), "--no-wait"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["url"].startswith("http://127.0.0.1:"))

    def test_preview_waits_for_a_click(self):
        info = self._propose()

        def click():
            url = json.loads((self.preview / "url.json").read_text(encoding="utf-8"))["url"]
            request = urllib.request.Request(url + "/choose", method="POST",
                                             data=json.dumps({"id": info["drafts"][0]}).encode("utf-8"),
                                             headers={"Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=5).read()

        timer = threading.Timer(0.6, click)
        timer.start()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-preview", "--dir", str(self.preview), "--timeout", "8", "--poll", "0.1"])
        timer.cancel()
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in out.getvalue().strip().splitlines()]
        self.assertEqual(lines[-1]["chosen"], info["drafts"][0])

    def test_real_script_lines_reach_the_mockups_and_the_style_frame(self):
        lines = [["작은 "], [{"hl": "한 걸음"}, "에서 시작합니다"]]
        lines_path = self.root / "lines.json"
        lines_path.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-propose", "--analysis", str(self.analysis), "--out", str(self.preview),
                         "--mood", "warm", "--lines", str(lines_path)])
        self.assertEqual(code, 0)
        info = json.loads(out.getvalue())
        page = Path(info["index"]).read_text(encoding="utf-8")
        self.assertIn("에서 시작합니다", page)
        self.assertNotIn("이 화면의 글자 크기와", page)
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-styleplan", "--dir", str(self.preview), "--analysis", str(self.analysis),
                         "--out", str(self.root / "style"), "--id", info["drafts"][0],
                         "--lines", str(lines_path)])
        self.assertEqual(code, 0)
        plan = json.loads(Path(json.loads(out.getvalue())["plan"]).read_text(encoding="utf-8"))
        caption = next(g for g in plan["graphics"] if g["type"] == "caption")
        self.assertEqual(caption["lines"], lines)

    def test_styleplan_writes_an_edit_plan(self):
        from aestudio.plan import load_plan
        info = self._propose()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-styleplan", "--dir", str(self.preview), "--analysis", str(self.analysis),
                         "--out", str(self.root / "style"), "--id", info["drafts"][0]])
        self.assertEqual(code, 0)
        plan = load_plan(json.loads(out.getvalue())["plan"])
        self.assertTrue(plan.name.startswith("STYLE_"))


if __name__ == "__main__":
    unittest.main()
