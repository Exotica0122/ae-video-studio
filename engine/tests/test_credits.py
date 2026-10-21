import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from aestudio import credits as cr
from aestudio.__main__ import main

HAND_WRITTEN = """# Credits

| File | Source | Notes |
|---|---|---|
| footage/church/pastor-cut.mov, pastor-cut.wav | church | own footage |
| audio/narration/*.mp3 | AI voice | plan terms |

- `audio/music/bgm.wav` — edit of two MRs, in-church screening only.
"""


def write_plan(root: Path) -> Path:
    plan = {"name": "C", "format": {"duration": 10},
            "shots": [{"clip": "../footage/a.mp4", "in": 0, "out": 10}],
            "music": [{"file": "../audio/music/bgm.wav", "end": 5}, {"file": "../audio/music/b.wav", "start": 5}],
            "sfx": [{"file": "../audio/sfx/whoosh.wav", "at": 1}],
            "graphics": [{"type": "end-card", "logo": {"file": "../assets/logo.png"}},
                         {"type": "layout", "in": 0, "out": 2,
                          "panels": [{"clip": "../footage/church/pastor-cut.wav", "sw": 1920, "sh": 1080}]}]}
    (root / "plan").mkdir()
    (root / "plan" / "edit.json").write_text(json.dumps(plan))
    return root / "plan" / "edit.json"


class CreditsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_creates_the_table_and_replaces_an_entry_for_the_same_file(self):
        cr.add(self.root, "footage/a.mp4", "https://www.pexels.com/video/1/", "A", "Pexels License", when=date(2026, 9, 30))
        path = cr.add(self.root, "footage/a.mp4", "https://www.pexels.com/video/1/", "A | B", "Pexels License",
                      notes="faces checked", when=date(2026, 10, 1))
        text = path.read_text(encoding="utf-8")
        self.assertEqual(path, self.root / "assets" / "CREDITS.md")
        self.assertEqual(text.count("footage/a.mp4"), 1)
        self.assertIn("| footage/a.mp4 | https://www.pexels.com/video/1/ | A \\| B | Pexels License | 2026-10-01 | faces checked |",
                      text)

    def test_add_appends_a_table_to_a_hand_written_file(self):
        (self.root / "assets").mkdir()
        (self.root / "assets" / "CREDITS.md").write_text(HAND_WRITTEN, encoding="utf-8")
        text = cr.add(self.root, "audio/sfx/whoosh.wav", "https://pixabay.com/x/", "B", "Pixabay Content License").read_text()
        self.assertTrue(text.startswith(HAND_WRITTEN.rstrip("\n")))
        self.assertIn(cr.HEADER, text)

    def test_add_needs_a_licence(self):
        with self.assertRaisesRegex(cr.CreditsError, "licence"):
            cr.add(self.root, "a.mp4", "u", "a", "")

    def test_check_lists_plan_media_without_a_credit(self):
        write_plan(self.root)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "CREDITS.md").write_text(HAND_WRITTEN, encoding="utf-8")
        cr.add(self.root, "footage/a.mp4", "u", "a", "Pexels License")
        result = cr.check(self.root)
        self.assertEqual(result["referenced"], 6)
        self.assertEqual(result["missing"], ["audio/music/b.wav", "audio/sfx/whoosh.wav", "assets/logo.png"])

    def test_cli_check_fails_while_anything_is_uncredited(self):
        write_plan(self.root)
        with redirect_stdout(io.StringIO()) as out:
            code = main(["credits", "check", "--dir", str(self.root)])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out.getvalue())["exists"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["credits", "add", "assets/logo.png", "--dir", str(self.root), "--url", "own",
                                   "--author", "church", "--licence", "used with permission", "--date", "2026-09-30"]), 0)
        self.assertIn("2026-09-30", (self.root / "assets" / "CREDITS.md").read_text())


if __name__ == "__main__":
    unittest.main()
