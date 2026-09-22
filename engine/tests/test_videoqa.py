"""video-qa: contrast maths, report shaping, and real measurement of a real file."""
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from aestudio import videoqa as qa


def _sine(path, seconds, amplitude, freq=110):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency={freq}:duration={seconds}",
                    "-af", f"volume={amplitude}", "-c:a", "pcm_s16le", str(path)], check=True)


class ContrastTest(unittest.TestCase):
    def test_black_on_white_is_the_maximum_ratio(self):
        self.assertAlmostEqual(qa.contrast_ratio([0, 0, 0], [1, 1, 1]), 21.0, places=1)

    def test_a_colour_against_itself_has_no_contrast(self):
        self.assertAlmostEqual(qa.contrast_ratio([0.4, 0.5, 0.6], [0.4, 0.5, 0.6]), 1.0, places=2)

    def test_the_order_of_the_pair_does_not_change_the_ratio(self):
        a, b = [0.13, 0.19, 0.29], [0.98, 0.97, 0.94]
        self.assertEqual(qa.contrast_ratio(a, b), qa.contrast_ratio(b, a))

    def test_green_weighs_more_than_blue_as_wcag_says(self):
        self.assertGreater(qa.relative_luminance([0, 1, 0]), qa.relative_luminance([0, 0, 1]))


class _Design:
    def __init__(self, palette):
        self.palette = palette

    def color(self, name):
        return list(self.palette[name])


class LegibilityTest(unittest.TestCase):
    def test_the_real_paper_notebook_palette_passes(self):
        design = _Design({"paper": [0.98431, 0.96863, 0.93725], "ink": [0.13333, 0.18824, 0.2902],
                          "accent": [1.0, 0.84706, 0.30196], "shade": [0.06275, 0.07843, 0.09412]})
        by_check = {f.check: f for f in qa.legibility(design)}
        self.assertEqual(by_check["contrast:ink-on-paper"].status, "ok")

    def test_a_pretty_but_unreadable_pair_is_flagged(self):
        design = _Design({"paper": [0.95, 0.93, 0.90], "ink": [0.80, 0.78, 0.74]})
        finding = qa.legibility(design)[0]
        self.assertEqual(finding.status, "warn")
        self.assertIn("under the", finding.detail)

    def test_pairs_the_palette_does_not_define_are_skipped_not_invented(self):
        self.assertEqual(qa.legibility(_Design({"paper": [1, 1, 1]})), [])


class ReportTest(unittest.TestCase):
    def test_versions_count_up_from_the_files_already_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(qa.next_version(tmp), 1)
            (Path(tmp) / "report-v01.md").write_text("x", encoding="utf-8")
            (Path(tmp) / "report-v02.md").write_text("x", encoding="utf-8")
            self.assertEqual(qa.next_version(tmp), 3)

    def test_an_unrelated_markdown_file_does_not_shift_the_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "notes.md").write_text("x", encoding="utf-8")
            (Path(tmp) / "report-v07.md").write_text("x", encoding="utf-8")
            self.assertEqual(qa.next_version(tmp), 8)

    def test_problems_are_listed_before_the_full_table(self):
        report = qa.QAReport("out.mp4", [qa.Finding("decode", "ok", "clean"),
                                         qa.Finding("true-peak", "fail", "clipping")])
        text = qa.format_report(report, 3, today=date(2026, 9, 22))
        self.assertIn("# QA report v03", text)
        self.assertIn("**1 failed, 0 warnings**", text)
        self.assertLess(text.index("Needs attention"), text.index("All checks"))
        self.assertIn("clipping", text)

    def test_a_clean_report_has_no_needs_attention_section(self):
        report = qa.QAReport("out.mp4", [qa.Finding("decode", "ok", "clean")])
        self.assertNotIn("Needs attention", qa.format_report(report, 1))

    def test_writing_a_report_picks_the_next_free_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = qa.write_report(tmp, qa.QAReport("a.mp4", [qa.Finding("decode", "ok", "clean")]))
            second = qa.write_report(tmp, qa.QAReport("a.mp4", [qa.Finding("decode", "ok", "clean")]))
            self.assertEqual(first.name, "report-v01.md")
            self.assertEqual(second.name, "report-v02.md")


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class MeasurementTest(unittest.TestCase):
    """The numbers have to be right; a QA tool that measures the wrong window is worse than none."""

    def test_rms_matches_a_known_amplitude_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            loud, quiet = Path(tmp) / "loud.wav", Path(tmp) / "quiet.wav"
            _sine(loud, 1.0, 0.35)
            _sine(quiet, 1.0, 0.05)
            difference = qa.rms_db(loud, 0.1, 0.9) - qa.rms_db(quiet, 0.1, 0.9)
            self.assertAlmostEqual(difference, 16.9, delta=0.3,
                                   msg="0.35 over 0.05 is 16.9 dB; a different answer means "
                                       "the measured window is not the requested one")

    def test_the_window_is_cut_accurately_not_by_seeking(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "step.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                            "-i", "sine=frequency=110:duration=4",
                            "-af", "volume='if(lt(t,2),0.35,0.05)':eval=frame",
                            "-c:a", "pcm_s16le", str(src)], check=True)
            before = qa.rms_db(src, 1.5, 1.9)
            after = qa.rms_db(src, 2.1, 2.5)
            self.assertAlmostEqual(before - after, 16.9, delta=0.5)

    def test_a_bed_that_ducks_late_is_caught_and_one_that_ducks_early_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            early, late = Path(tmp) / "early.wav", Path(tmp) / "late.wav"
            for path, duck_at in ((early, 2.5), (late, 3.4)):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                                "-i", "sine=frequency=110:duration=8",
                                "-af", f"volume='if(between(t,{duck_at},5.3),0.05,0.35)':eval=frame",
                                "-c:a", "pcm_s16le", str(path)], check=True)
            spans = [(3.0, 5.0)]
            good = qa.music_before_voice(early, spans, 8.0)
            bad = qa.music_before_voice(late, spans, 8.0)
            self.assertEqual(good[0].status, "ok", good[0].detail)
            self.assertEqual(bad[0].status, "warn", bad[0].detail)

    def test_a_file_with_voices_throughout_says_so_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "talky.wav"
            _sine(src, 3.0, 0.3)
            findings = qa.music_before_voice(src, [(0.0, 3.0)], 3.0)
            self.assertEqual(findings[0].status, "ok")
            self.assertIn("no bed-only window", findings[0].detail)



class SfxBaselineTest(unittest.TestCase):
    """Found on a real master: the end-card sounds land 30ms after the last word."""

    def test_a_clear_window_is_found_before_the_event(self):
        window = qa._clear_window(10.0, 0.3, spans=[(2.0, 5.0)])
        self.assertEqual(window, (9.7, 10.0), "nothing is in the way; use the moment before")

    def test_a_short_voice_just_before_the_event_pushes_the_baseline_earlier(self):
        window = qa._clear_window(10.0, 0.3, spans=[(9.5, 9.95)])
        self.assertIsNotNone(window)
        self.assertLessEqual(window[1], 9.4, "the baseline must clear the voice and its guard")

    def test_a_voice_covering_the_whole_search_range_leaves_nowhere_to_measure(self):
        self.assertIsNone(qa._clear_window(10.0, 0.3, spans=[(5.0, 9.95)]),
                          "3s of continuous speech before the event means no baseline exists")

    def test_no_clear_window_at_all_returns_none(self):
        self.assertIsNone(qa._clear_window(10.0, 0.3, spans=[(0.0, 10.0)]))

    def test_the_search_gives_up_rather_than_wandering_off(self):
        self.assertIsNone(qa._clear_window(10.0, 0.3, spans=[(6.0, 10.0)], search=1.0))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class SfxMeasurementTest(unittest.TestCase):
    def _mix(self, path):
        """A quiet bed with a loud blip at 5.0s."""
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=110:duration=8",
                        "-af", "volume='if(between(t,5.0,5.3),1.0,0.05)':eval=frame",
                        "-c:a", "pcm_s16le", str(path)], check=True)

    def test_an_audible_sfx_is_reported_with_its_lift(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mix.wav"
            self._mix(src)
            finding = qa.sfx_audible(src, [{"at": 5.0, "role": "blip"}], spans=[])[0]
            self.assertEqual(finding.status, "ok")
            self.assertIn("lifts the mix", finding.detail)

    def test_a_voice_running_into_the_event_makes_it_unmeasurable_not_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mix.wav"
            self._mix(src)
            finding = qa.sfx_audible(src, [{"at": 5.0, "role": "blip"}], spans=[(0.0, 5.0)])[0]
            self.assertEqual(finding.status, "ok", "an unmeasurable sound is not a defect")
            self.assertIn("not measurable", finding.detail)
            self.assertIn("Listen", finding.detail)

    def test_another_sfx_just_before_pushes_the_baseline_clear_of_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mix.wav"
            self._mix(src)
            events = [{"at": 4.8, "role": "first"}, {"at": 5.0, "role": "second"}]
            by_name = {f.check: f for f in qa.sfx_audible(src, events, spans=[])}
            self.assertIn("earlier", by_name["sfx:second"].detail,
                          "the baseline must skip back past the other sound, and say that it did")

    def test_speech_and_another_sfx_together_leave_nothing_to_measure(self):
        """The real end card: three sounds inside two seconds, 30ms after the last word."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mix.wav"
            self._mix(src)
            events = [{"at": 4.6, "role": "first"}, {"at": 5.0, "role": "second"}]
            by_name = {f.check: f for f in qa.sfx_audible(src, events, spans=[(0.0, 4.55)])}
            self.assertIn("not measurable", by_name["sfx:second"].detail)
            self.assertEqual(by_name["sfx:second"].status, "ok", "unmeasurable is not a defect")


if __name__ == "__main__":
    unittest.main()
