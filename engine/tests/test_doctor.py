"""Doctor checks must not depend on what happens to be installed on the machine running them."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from aestudio import doctor
from aestudio.fonts import Font


def _font(fid, family, postscript, files=()):
    return Font(id=fid, family=family, postscript=postscript, scripts=["ko"], style="sans",
                licence="OFL", url="https://example.invalid", files=list(files))


class PythonCheckTest(unittest.TestCase):
    def test_a_new_enough_interpreter_passes(self):
        self.assertEqual(doctor.check_python((3, 13)).status, "ok")

    def test_python_39_fails_and_names_the_macos_trap(self):
        check = doctor.check_python((3, 9))
        self.assertEqual(check.status, "fail")
        self.assertIn("/usr/bin/python3", check.fix)


class ToolCheckTest(unittest.TestCase):
    def test_missing_ffmpeg_fails_with_the_brew_fix(self):
        checks = doctor.check_ffmpeg(which=lambda name: None)
        self.assertEqual([c.status for c in checks], ["fail", "fail"])
        self.assertIn("brew install ffmpeg", checks[0].fix)

    def test_present_ffmpeg_reports_its_path(self):
        checks = doctor.check_ffmpeg(which=lambda name: f"/opt/homebrew/bin/{name}")
        self.assertEqual([c.status for c in checks], ["ok", "ok"])
        self.assertEqual(checks[1].detail, "/opt/homebrew/bin/ffprobe")

    def test_missing_whisper_only_warns_because_transcripts_are_optional(self):
        check = doctor.check_whisper(command="uvx mlx-whisper", which=lambda name: None)
        self.assertEqual(check.status, "warn")
        self.assertIn("import-transcript", check.fix)


class AfterEffectsCheckTest(unittest.TestCase):
    def test_no_install_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = doctor.check_after_effects(apps=tmp, running=False)
            self.assertEqual(check.status, "fail")

    def test_the_newest_install_is_reported_with_its_run_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("Adobe After Effects 2025", "Adobe After Effects 2026", "Safari.app"):
                (Path(tmp) / name).mkdir()
            check = doctor.check_after_effects(apps=tmp, running=True)
            self.assertEqual(check.status, "ok")
            self.assertIn("2026", check.detail)
            self.assertIn("running", check.detail)

    def test_a_pre_2025_install_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Adobe After Effects 2022").mkdir()
            self.assertEqual(doctor.check_after_effects(apps=tmp, running=False).status, "warn")


class BridgeCheckTest(unittest.TestCase):
    def test_a_missing_bridge_folder_explains_the_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = doctor.check_bridge(root=Path(tmp) / "absent")
            self.assertEqual(checks[0].status, "fail")
            self.assertIn("Auto-run", checks[0].fix)

    def test_a_running_job_warns_instead_of_looking_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ae_command.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
            checks = doctor.check_bridge(root=tmp)
            self.assertEqual(checks[0].status, "warn")
            self.assertIn("busy", checks[0].detail)

    def test_a_long_stale_result_suggests_the_panel_is_shut(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ae_command.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            result = Path(tmp) / "ae_mcp_result.json"
            result.write_text("{}", encoding="utf-8")
            now = time.time() + (doctor.STALE_RESULT_DAYS + 3) * 86400
            checks = doctor.check_bridge(root=tmp, now=now)
            stale = [c for c in checks if c.name == "bridge-panel"][0]
            self.assertEqual(stale.status, "warn")
            self.assertIn("days old", stale.detail)


class BridgeServerTest(unittest.TestCase):
    def test_a_built_server_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp) / "build"
            build.mkdir()
            (build / "index.js").write_text("//", encoding="utf-8")
            self.assertEqual(doctor.check_bridge_server(tmp).status, "ok")

    def test_a_missing_build_fails_and_names_the_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = doctor.check_bridge_server(Path(tmp) / "absent")
            self.assertEqual(check.status, "fail")
            self.assertIn("install.sh", check.fix)

    def test_a_working_panel_downgrades_a_missing_build_to_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = doctor.check_bridge_server(Path(tmp) / "absent", panel_active=True)
            self.assertEqual(check.status, "warn", "do not tell someone to reinstall a bridge that works")
            self.assertIn("installed elsewhere", check.detail)

    def test_a_half_built_folder_is_distinguished_from_a_missing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = doctor.check_bridge_server(tmp)
            self.assertEqual(check.status, "fail")
            self.assertIn("npm run build", check.fix)

    def test_panel_liveness_comes_from_the_result_file_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(doctor.panel_has_answered(tmp), "no result file at all")
            (Path(tmp) / "ae_mcp_result.json").write_text("{}", encoding="utf-8")
            self.assertTrue(doctor.panel_has_answered(tmp))
            old = time.time() + (doctor.STALE_RESULT_DAYS + 5) * 86400
            self.assertFalse(doctor.panel_has_answered(tmp, now=old))


class DesignFontCheckTest(unittest.TestCase):
    """A design names PostScript names; the filesystem gives file stems. They differ."""

    CATALOGUE = [_font("neo", "NanumSquare Neo", {"regular": "NanumSquareNeoTTF-bRg"},
                       files=["NanumSquareNeo-bRg"]),
                 _font("paperlogy", "Paperlogy", {"bold": "Paperlogy-7Bold"})]

    def test_a_postscript_name_that_differs_from_its_file_stem_is_still_found(self):
        check = doctor._check_design_fonts(["NanumSquareNeoTTF-bRg"], self.CATALOGUE,
                                           {"nanumsquareneo-brg"})
        self.assertEqual(check.status, "ok", "the catalogue's files list should resolve the stem")

    def test_a_design_font_that_is_not_installed_fails_loudly(self):
        check = doctor._check_design_fonts(["Paperlogy-7Bold"], self.CATALOGUE, set())
        self.assertEqual(check.status, "fail")
        self.assertIn("Paperlogy-7Bold", check.detail)
        self.assertIn("substitutes", check.fix)

    def test_a_font_outside_the_catalogue_falls_back_to_the_file_stem(self):
        present = doctor._check_design_fonts(["Custom-Regular"], self.CATALOGUE, {"custom-regular"})
        self.assertEqual(present.status, "ok")
        absent = doctor._check_design_fonts(["Custom-Regular"], self.CATALOGUE, set())
        self.assertEqual(absent.status, "fail")
        self.assertIn("not in the catalogue", absent.detail)

    def test_catalogue_coverage_uses_the_injected_catalogue_not_this_machine(self):
        checks = doctor.check_fonts(catalogue=self.CATALOGUE, dirs=[])
        self.assertEqual(checks[0].status, "warn")
        self.assertIn("NanumSquare Neo", checks[0].detail)


class ReportTest(unittest.TestCase):
    def test_failures_are_counted_and_the_summary_says_it_cannot_build(self):
        report = doctor.Report([doctor.Check("a", "ok", "fine"),
                                doctor.Check("b", "fail", "broken", "do this"),
                                doctor.Check("c", "warn", "iffy", "maybe")])
        self.assertEqual(report.as_dict()["failed"], 1)
        text = doctor.format_report(report)
        self.assertIn("cannot build", text)
        self.assertIn("do this", text)

    def test_a_clean_report_says_so_without_listing_fixes(self):
        text = doctor.format_report(doctor.Report([doctor.Check("a", "ok", "fine", "unused fix")]))
        self.assertIn("Everything the engine needs", text)
        self.assertNotIn("unused fix", text)


if __name__ == "__main__":
    unittest.main()
