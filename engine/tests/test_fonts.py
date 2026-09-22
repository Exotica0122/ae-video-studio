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

    def test_nanumsquareneo_postscript_names_differ_from_file_stems(self):
        # Regression test: After Effects sets fonts by PostScript name, and
        # NanumSquareNeo's real PostScript names ("NanumSquareNeoTTF-*") differ
        # from its installed file stems ("NanumSquareNeo-*"). The catalogue must
        # keep the real PostScript names for AE while still being detected as
        # installed via the separate `files` list.
        neo = {f.id: f for f in fonts.load_catalogue()}["nanumsquareneo"]
        for name in neo.postscript.values():
            self.assertTrue(name.startswith("NanumSquareNeoTTF-"), name)
        self.assertTrue(fonts.is_installed(neo, fonts.installed_files()))

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
        # Two families from the font fixture plus one whose PostScript name exists nowhere.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fonts.json"
            path.write_text(json.dumps([
                {"id": "paperlogy", "family": "Paperlogy", "postscript": {"regular": "Paperlogy-4Regular"},
                 "scripts": ["ko", "latin"], "style": "sans", "moods": ["modern", "clean"],
                 "licence": "OFL-1.1", "url": "https://example.test/paperlogy"},
                {"id": "maruburi", "family": "MaruBuri", "postscript": {"regular": "MaruBuri-Regular"},
                 "scripts": ["ko", "latin"], "style": "serif", "moods": ["modern", "clean"],
                 "licence": "OFL-1.1", "url": "https://example.test/maruburi"},
                {"id": "fixture-absent", "family": "Fixture Absent",
                 "postscript": {"regular": "FixtureAbsent-Regular"}, "scripts": ["ko", "latin"],
                 "style": "display", "moods": ["modern", "clean"],
                 "licence": "SIL Open Font License 1.1", "url": "https://example.test/fixture-absent"},
            ], ensure_ascii=False), encoding="utf-8")
            catalogue = fonts.load_catalogue(path)

            pairs = fonts.pairings(["modern", "clean"], scripts=("ko",), catalogue=catalogue,
                                   installed_only=False)
            notes = [n for p in pairs for n in p["notes"]]
            self.assertTrue(any("Fixture Absent" in n and "SIL Open Font License 1.1" in n
                                and "https://example.test/fixture-absent" in n for n in notes), notes)

            pairs = fonts.pairings(["modern", "clean"], scripts=("ko",), catalogue=catalogue)
            notes = [n for p in pairs for n in p["notes"]]
            self.assertEqual(notes, [])                # installed_only=True (the default): no notes

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
