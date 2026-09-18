import json
import tempfile
import unittest
from pathlib import Path

from aestudio import designgen, styleframe

LOG = json.loads(json.dumps({
    "clips": [{"name": "a.mp4", "path": "/tmp/a.mp4", "duration": 14.0, "luma": 0.6, "width": 1920, "height": 1080,
               "frames": [{"at": 0.5, "file": "frames/a_0.5.jpg", "luma": 0.6,
                           "colors": [[240, 170, 60], [30, 40, 70], [200, 150, 90], [20, 20, 25]]}]}],
    "audio": [], "errors": []}))


class StyleFrameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analysis = self.root / "analysis"
        (self.analysis / "frames").mkdir(parents=True)
        (self.analysis / "frames" / "a_0.5.jpg").write_bytes(b"\xff\xd8\xff\xd9")     # stand-in JPEG
        self.log = json.loads(json.dumps(LOG))
        self.log["root"] = str(self.analysis)
        self.drafts = designgen.propose(["warm", "modern"], log=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_has_one_section_per_draft_with_frames_and_buttons(self):
        index = styleframe.render_mockups(self.drafts, self.log, self.root / "preview")
        html = index.read_text(encoding="utf-8")
        for draft in self.drafts:
            self.assertIn(f'data-id="{draft.id}"', html)
            self.assertIn(draft.name, html)
        self.assertEqual(html.count('class="draft d-'), len(self.drafts))
        self.assertEqual(html.count('class="choose"'), len(self.drafts))
        self.assertIn("/choose", html)
        self.assertIn("frames/a_0.5.jpg", html)
        self.assertTrue((self.root / "preview" / "frames" / "a_0.5.jpg").exists())
        self.assertNotIn("http://", html.replace("http://localhost", ""))   # no external requests

    def test_tokens_drive_the_css(self):
        draft = self.drafts[0]
        css = styleframe.mockup_css(draft)
        self.assertIn(draft.recipe["tokens"]["palette"]["accent"], css)
        self.assertIn(draft.recipe["tokens"]["type"]["headline"]["font"].split("-")[0], css)

    def test_caption_html_marks_the_highlight(self):
        html = styleframe.caption_html(self.drafts[0], [["작은 "], [{"hl": "한 걸음"}], ["에서"]])
        self.assertIn("한 걸음", html)
        self.assertIn("class=\"hl\"", html)
        self.assertNotIn("{", html)

    def test_install_notes_are_shown(self):
        drafts = designgen.propose(["modern", "clean"], log=self.log, installed_only=False)
        index = styleframe.render_mockups(drafts, self.log, self.root / "preview2")
        html = index.read_text(encoding="utf-8")
        notes = [n for d in drafts for n in d.notes]
        for note in notes:
            self.assertIn(note.split(":")[0], html)

    def test_missing_frames_do_not_crash(self):
        log = json.loads(json.dumps(LOG))
        log["root"] = str(self.analysis)
        log["clips"][0]["frames"][0]["file"] = "frames/missing.jpg"
        index = styleframe.render_mockups(self.drafts, log, self.root / "preview3")
        self.assertTrue(index.exists())


if __name__ == "__main__":
    unittest.main()
