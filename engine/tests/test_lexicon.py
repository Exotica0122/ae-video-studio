import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from aestudio.__main__ import main
from aestudio.lexicon import LexiconError, load_lexicon, scan

ENTRY = {"text": "성과 가정", "say": "성꽈 가정", "note": "read as 성과 [result]; re-spell or reword"}


class LexiconTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lexicon = self.root / "lexicon.json"
        self.lexicon.write_text(json.dumps([ENTRY], ensure_ascii=False), encoding="utf-8")
        self.script = self.root / "narration.md"
        self.script.write_text("# 3. 주제\n\n아이들은 성과  가정에 대해 배웁니다.\n성과를 냈습니다.\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_the_line_despite_extra_spaces(self):
        hits = scan(load_lexicon(self.lexicon), [self.script])
        self.assertEqual([(h["line"], h["say"]) for h in hits], [(3, "성꽈 가정")])
        self.assertEqual(hits[0]["context"], "아이들은 성과  가정에 대해 배웁니다.")

    def test_rejects_an_entry_without_text(self):
        self.lexicon.write_text(json.dumps([{"say": "x"}]), encoding="utf-8")
        with self.assertRaisesRegex(LexiconError, r"\[0\]: 'text'"):
            load_lexicon(self.lexicon)

    def test_cli_prints_the_hits(self):
        with redirect_stdout(io.StringIO()) as out:
            code = main(["lexicon-check", str(self.script), "--lexicon", str(self.lexicon)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["hits"][0]["text"], "성과 가정")


if __name__ == "__main__":
    unittest.main()
