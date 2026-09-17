import json
import tempfile
import unittest
from pathlib import Path

from aestudio import fonts


class FontsTest(unittest.TestCase):
    def test_catalogue_loads_and_is_valid(self):
        catalogue = fonts.load_catalogue()
        ids = [f.id for f in catalogue]
        self.assertIn("paperlogy", ids)
        self.assertIn("maruburi", ids)
        self.assertEqual(len(ids), len(set(ids)))
        for font in catalogue:
            self.assertTrue(font.licence and font.url, font.id)
            self.assertTrue(font.postscript, font.id)
            self.assertIn(font.style, ("sans", "serif", "hand", "display"), font.id)
            self.assertTrue(set(font.scripts) <= {"ko", "latin", "ja"}, font.id)

    def test_installed_detection(self):
        catalogue = {f.id: f for f in fonts.load_catalogue()}
        files = fonts.installed_files()
        self.assertTrue(fonts.is_installed(catalogue["paperlogy"], files))
        self.assertTrue(fonts.is_installed(catalogue["maruburi"], files))

        fake = fonts.Font(id="fake", family="Fake", postscript={"regular": "NoSuchFont-Regular"},
                           scripts=["latin"], style="sans")
        self.assertFalse(fonts.is_installed(fake, files))

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "SomeFont-Regular.ttf").write_bytes(b"")
            findable = fonts.Font(id="findable", family="Findable",
                                   postscript={"regular": "SomeFont-Regular"},
                                   scripts=["latin"], style="sans")
            self.assertTrue(fonts.is_installed(findable, dirs=[Path(d)]))

    def test_pairings_prefer_installed_and_mix_styles(self):
        pairs = fonts.pairings(["warm", "friendly"], scripts=("ko",))
        self.assertTrue(pairs)
        for pair in pairs:
            self.assertTrue(pair["installed"])
            self.assertEqual(pair["notes"], [])
            for role in ("headline", "body", "quote"):
                self.assertIn("ko", pair[role].scripts)
        self.assertTrue(any(p["headline"].style != p["body"].style for p in pairs))

    def test_pairings_can_include_uninstalled_with_a_note(self):
        pairs = fonts.pairings(["modern", "clean"], scripts=("ko",), installed_only=False)
        notes = [n for p in pairs for n in p["notes"]]
        self.assertTrue(any("install" in n.lower() for n in notes), notes)

    def test_fonts_for_fills_every_role(self):
        pair = fonts.pairings(["warm"], scripts=("ko",))[0]
        roles = fonts.fonts_for(pair, ("headline", "body", "emphasis", "quote", "label", "scripture"))
        self.assertEqual(set(roles), {"headline", "body", "emphasis", "quote", "label", "scripture"})
        for name in roles.values():
            self.assertRegex(name, r"^[A-Za-z0-9\-]+$")

    def test_bad_catalogue_reports_every_problem(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fonts.json"
            path.write_text(json.dumps([{"id": "x", "family": "X", "postscript": {}, "scripts": ["klingon"],
                                         "style": "wobbly", "moods": [], "licence": "", "url": ""}]), encoding="utf-8")
            with self.assertRaises(fonts.FontError) as cm:
                fonts.load_catalogue(path)
        message = str(cm.exception)
        for expected in ("postscript", "scripts", "style", "licence"):
            self.assertIn(expected, message)


if __name__ == "__main__":
    unittest.main()
