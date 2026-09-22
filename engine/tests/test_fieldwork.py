"""Cover the engine changes that came back from using the plugin on a second production.

These were written while cutting a real video and committed untested (see the wip commit on
the field-work branch). The parts that can fail *silently* are what is pinned here: a path
that no longer matches, a photo that quietly disappears, a treatment that is not registered.
"""
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

import copy

from aestudio import jsx
from aestudio.compiler import compile_plan
from aestudio.components.layout import LayoutError
from aestudio.ops import validate_ops
from aestudio.components import REGISTRY
from aestudio.design import COMPONENTS, load_design
from aestudio.plan import PlanError, load_plan

# 교사대학 in NFC (composed) and NFD (decomposed) — identical to a reader, different bytes
NFC_NAME = unicodedata.normalize("NFC", "교사대학")
NFD_NAME = unicodedata.normalize("NFD", "교사대학")


class NFCTest(unittest.TestCase):
    """macOS hands out NFD paths; After Effects reports NFC. runtime.jsx compares the two."""

    def test_the_two_spellings_really_are_different_bytes(self):
        self.assertNotEqual(NFC_NAME, NFD_NAME, "this whole class is pointless if these match")
        self.assertEqual(len(NFC_NAME), 4)
        self.assertGreater(len(NFD_NAME), 4, "decomposed Korean splits into jamo")

    def test_a_decomposed_path_is_composed(self):
        self.assertEqual(jsx.nfc(f"/Volumes/T7/{NFD_NAME}/a.mp4"), f"/Volumes/T7/{NFC_NAME}/a.mp4")

    def test_an_already_composed_path_is_left_alone(self):
        path = f"/Volumes/T7/{NFC_NAME}/a.mp4"
        self.assertEqual(jsx.nfc(path), path)

    def test_non_strings_pass_through_untouched(self):
        for value in (None, 12, 3.5, ["a"], {"b": 1}):
            self.assertEqual(jsx.nfc(value), value)

    def test_every_op_file_is_normalised_and_other_keys_are_not_disturbed(self):
        ops = [{"op": "import", "file": f"/src/{NFD_NAME}/a.mp4", "id": f"keep-{NFD_NAME}"},
               {"op": "text", "value": NFD_NAME}]
        out = jsx._nfc_paths(ops)
        self.assertEqual(out[0]["file"], f"/src/{NFC_NAME}/a.mp4")
        self.assertEqual(out[0]["id"], f"keep-{NFD_NAME}", "only 'file' is a path")
        self.assertEqual(out[1]["value"], NFD_NAME, "text is the user's, not a path")

    def test_normalising_does_not_mutate_the_caller_s_ops(self):
        ops = [{"op": "import", "file": f"/src/{NFD_NAME}/a.mp4"}]
        jsx._nfc_paths(ops)
        self.assertEqual(ops[0]["file"], f"/src/{NFD_NAME}/a.mp4")

    def test_the_emitted_script_carries_a_composed_project_path(self):
        ops = [{"op": "comp", "id": "root", "name": "ROOT", "width": 1920, "height": 1080,
                "fps": 24, "duration": 5.0}]
        script = jsx.emit_script(ops, project=f"/Users/x/{NFD_NAME}/build/p.aep")
        # the script embeds JSON, which escapes non-ASCII, so compare the escaped spellings
        composed = json.dumps(NFC_NAME)[1:-1]
        decomposed = json.dumps(NFD_NAME)[1:-1]
        self.assertIn(composed, script)
        self.assertNotIn(decomposed, script, "the guard in runtime.jsx compares these strings")


def _plan(graphics, root):
    return {"name": "FIELD_TEST",
            "format": {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0},
            "shots": [{"clip": "clip.mp4", "in": 0.0, "out": 5.0}],
            "voices": [], "graphics": graphics}


class PhotoOnAnyGraphicTest(unittest.TestCase):
    """A title page set over footage carries a photo too; only end cards used to resolve one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "clip.mp4").write_bytes(b"x")
        (self.root / "photo.jpg").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self, graphics):
        path = self.root / "edit.json"
        path.write_text(json.dumps(_plan(graphics, self.root), ensure_ascii=False), encoding="utf-8")
        return load_plan(path, check_files=False)

    def test_a_title_page_photo_is_resolved_to_a_full_path(self):
        plan = self._load([{"type": "title-page", "in": 0, "out": 3, "text": "x",
                            "photo": {"clip": "photo.jpg"}}])
        resolved = plan.graphics[0]["photo"]["clip"]
        self.assertTrue(str(resolved).endswith("photo.jpg"))
        self.assertTrue(Path(resolved).is_absolute(), "the builder needs a path it can import")

    def test_an_end_card_photo_still_works(self):
        plan = self._load([{"type": "end-card", "in": 0, "title": "x",
                            "photo": {"clip": "photo.jpg"}}])
        self.assertTrue(str(plan.graphics[0]["photo"]["clip"]).endswith("photo.jpg"))

    def test_a_photo_that_does_not_exist_is_reported_not_silently_dropped(self):
        with self.assertRaises(PlanError) as caught:
            self._loadbad = self.root / "edit.json"
            self._loadbad.write_text(json.dumps(
                _plan([{"type": "title-page", "in": 0, "out": 3, "text": "x",
                        "photo": {"clip": "absent.jpg"}}], self.root)), encoding="utf-8")
            load_plan(self._loadbad, check_files=True)
        self.assertIn("absent.jpg", str(caught.exception))


class EditorialRegistrationTest(unittest.TestCase):
    def test_the_editorial_treatments_are_registered_and_callable(self):
        editorial = {component: fn for (component, treatment), fn in REGISTRY.items()
                     if treatment == "editorial"}
        self.assertTrue(editorial, "components/__init__ must import editorial for it to register")
        for component, fn in editorial.items():
            self.assertTrue(callable(fn), f"editorial/{component} is not callable")

    def test_editorial_covers_the_text_components_it_claims(self):
        covered = {component for (component, treatment) in REGISTRY if treatment == "editorial"}
        for component in ("caption", "quote", "title-page", "end-card"):
            self.assertIn(component, covered)

    def test_editorial_cannot_yet_back_a_whole_design(self):
        """Documents a real gap: no editorial lower-third exists, so a design must mix.

        If someone adds one, this test fails and should simply be deleted.
        """
        covered = {component for (component, treatment) in REGISTRY if treatment == "editorial"}
        self.assertEqual(sorted(set(COMPONENTS) - covered), ["lower-third"])


class ShippedDesignsStillLoadTest(unittest.TestCase):
    def test_every_shipped_design_loads_with_the_field_changes_applied(self):
        for path in sorted(Path(__file__).resolve().parents[2].glob("designs/*/design.json")):
            with self.subTest(design=path.parent.name):
                design = load_design(path)
                self.assertTrue(design.fonts())
                for component in COMPONENTS:
                    treatment, _ = design.treatment(component)
                    self.assertIn((component, treatment), REGISTRY,
                                  f"{path.parent.name} names a treatment that is not registered")



DESIGNS = Path(__file__).resolve().parents[2] / "designs"


class EditorialCompileTest(unittest.TestCase):
    """Registration alone proves nothing; these push a real plan through the layout code."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "clip.mp4").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def _design(self, components):
        raw = copy.deepcopy(json.loads((DESIGNS / "cinematic-minimal" / "design.json")
                                       .read_text(encoding="utf-8")))
        for component in components:
            raw["components"][component] = {"treatment": "editorial"}
        path = self.root / "design.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return load_design(path)

    def _compile(self, design, graphics):
        path = self.root / "edit.json"
        path.write_text(json.dumps(_plan(graphics, self.root), ensure_ascii=False), encoding="utf-8")
        return compile_plan(load_plan(path, check_files=False), design)

    def test_title_page_caption_and_quote_compile_to_valid_ops(self):
        design = self._design(["title-page", "caption", "quote"])
        ops = self._compile(design, [
            {"type": "title-page", "in": 0.2, "out": 3.0, "ref": "여는 말",
             "lines": [["제목입니다"], ["둘째 ", {"hl": "강조"}, " 줄"]]},
            {"type": "caption", "voice": None, "in": 3.2, "out": 4.4, "lines": [["첫 줄"]]},
            {"type": "quote", "voice": None, "in": 4.6, "out": 4.9, "lines": [["인용문"]]}])
        validate_ops(ops)
        self.assertGreater(len(ops), 10, "the treatments produced almost nothing")

    def test_the_gradient_scrim_is_emitted_for_a_title_over_footage(self):
        design = self._design(["title-page"])
        ops = self._compile(design, [{"type": "title-page", "in": 0.2, "out": 3.0,
                                      "lines": [["제목"]]}])
        self.assertTrue(any("SCRIM" in str(o.get("id", "")) for o in ops),
                        "editorial sets type over footage; without the scrim it is unreadable")

    def test_an_editorial_end_card_needs_lines_and_says_which_treatment_to_use_instead(self):
        design = self._design(["end-card"])
        with self.assertRaises(LayoutError) as caught:
            self._compile(design, [{"type": "end-card", "in": 0.5, "title": "끝", "year": 2027,
                                    "tagline": "한 줄", "rows": [{"label": "안내", "values": ["첫째"]}]}])
        message = str(caught.exception)
        self.assertIn("closing statement", message)
        self.assertIn("notebook-page", message, "the message must name a treatment that works")

    def test_an_editorial_end_card_with_lines_compiles(self):
        design = self._design(["end-card"])
        ops = self._compile(design, [{"type": "end-card", "in": 0.5, "lines": [["마치며"]]}])
        validate_ops(ops)


if __name__ == "__main__":
    unittest.main()
