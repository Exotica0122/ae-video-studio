import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from aestudio.__main__ import main
from aestudio.components import REGISTRY
from aestudio.lint import (FADE_OVERHEAD, flash_frames, graphic_times, lint, read_seconds, read_time,
                           text_before_voice, text_overlap)
from aestudio.plan import Format, Plan, Shot
from tests.helpers import make_ctx, voice

EDITORIAL = {"caption": "editorial", "quote": "editorial", "layout": "editorial", "title-page": "editorial",
             "end-card": "editorial", "lower-third": "rule-wipe", "inset": "editorial", "scrapbook": "notebook"}


class StubDesign:
    def __init__(self, components=None):
        self.components = components or EDITORIAL

    def treatment(self, component):
        return self.components[component], {}


def shot(name, start, end, **kw):
    return Shot(Path(f"/media/{name}.mp4"), start, end, **kw)


def make_plan(shots, graphics=(), duration=60.0, dissolve=0.0):
    return Plan("T", Path("/tmp"), Format(duration=duration), [], list(shots), [], None, list(graphics),
                {"dissolve": dissolve}, 0.0, None)


def crt_layout(out):
    return {"type": "layout", "in": 26.0, "out": out, "panels": [{"clip": "/media/crt.mp4", "sw": 1920, "sh": 1080}]}


class FlashFrameTest(unittest.TestCase):
    def flashes(self, plan, design=None, **kw):
        return flash_frames(plan, design or StubDesign(), {}, **kw)

    def test_crt_layout_ending_before_bible_shot_flashes_the_bible_plate(self):
        plan = make_plan([shot("intro", 0, 22), shot("bible", 22, 30.8), shot("next", 30.8, 45)], [crt_layout(30.35)])
        [f] = self.flashes(plan)
        self.assertEqual((f.kind, f.start, f.end), ("flash", 30.35, 30.8))
        self.assertIn("bible.mp4", f.message)

    def test_crt_flash_still_caught_when_next_shot_dissolves_in(self):
        shots = [shot("intro", 0, 22), shot("bible", 22, 30.8), shot("next", 30.8, 45, dissolve=0.3)]
        [f] = self.flashes(make_plan(shots, [crt_layout(30.35)]))
        self.assertEqual((f.start, f.end), (30.35, 31.1))

    def test_layout_running_to_the_next_shot_is_clean(self):
        plan = make_plan([shot("intro", 0, 22), shot("bible", 22, 30.8), shot("next", 30.8, 45)], [crt_layout(30.8)])
        self.assertEqual(self.flashes(plan), [])

    def test_pure_dissolve_overlap_is_not_a_flash(self):
        shots = [shot("intro", 0, 22), shot("bible", 22, 30.8), shot("next", 30.8, 45, dissolve=0.5)]
        self.assertEqual(self.flashes(make_plan(shots, [crt_layout(30.8)])), [])

    def test_short_shot_between_cuts(self):
        [f] = self.flashes(make_plan([shot("a", 0, 10), shot("b", 10, 10.3), shot("c", 10.3, 20)]))
        self.assertEqual((f.start, f.end), (10, 10.3))

    def test_min_fragment_is_configurable(self):
        plan = make_plan([shot("a", 0, 10), shot("b", 10, 10.3), shot("c", 10.3, 20)])
        self.assertEqual(self.flashes(plan, min_fragment=0.2), [])

    def test_plan_can_mark_a_graphic_opaque(self):
        g = {"type": "inset", "in": 5.0, "out": 9.7, "items": [], "opaque": True}
        [f] = self.flashes(make_plan([shot("a", 0, 10), shot("b", 10, 20)], [g]))
        self.assertEqual((f.start, f.end), (9.7, 10))

    def test_plan_can_mark_a_layout_transparent(self):
        g = dict(crt_layout(30.35), opaque=False)
        plan = make_plan([shot("intro", 0, 22), shot("bible", 22, 30.8), shot("next", 30.8, 45)], [g])
        self.assertEqual(self.flashes(plan), [])

    def test_editorial_title_without_photo_does_not_cover(self):
        g = {"type": "title-page", "in": 0, "out": 9.7, "lines": [["A"]]}
        self.assertEqual(self.flashes(make_plan([shot("a", 0, 10), shot("b", 10, 20)], [g])), [])

    def test_black_frame_title_covers(self):
        g = {"type": "title-page", "in": 0, "out": 9.7, "lines": [["A"]]}
        design = StubDesign({"title-page": "black-frame"})
        [f] = self.flashes(make_plan([shot("a", 0, 10), shot("b", 10, 20)], [g]), design)
        self.assertEqual((f.start, f.end), (9.7, 10))


def caption(t_in, t_out, text="hello", **kw):
    return dict({"type": "caption", "in": t_in, "out": t_out, "lines": [[text]]}, **kw)


class TextOverlapTest(unittest.TestCase):
    design = StubDesign({"caption": "line-fade", "lower-third": "rule-wipe"})

    def test_two_default_captions_at_once_overlap(self):
        [f] = text_overlap(make_plan([], [caption(1, 5), caption(3, 8)]), self.design, {})
        self.assertEqual((f.kind, f.start, f.end), ("overlap", 3, 5))

    def test_different_places_do_not_overlap(self):
        plan = make_plan([], [caption(1, 5), caption(3, 8, place="top-center")])
        self.assertEqual(text_overlap(plan, self.design, {}), [])

    def test_sequential_captions_do_not_overlap(self):
        self.assertEqual(text_overlap(make_plan([], [caption(1, 5), caption(5, 8)]), self.design, {}), [])

    def test_lower_third_under_a_lower_centre_caption(self):
        lt = {"type": "lower-third", "at": 2, "name": "Kim", "role": "Pastor"}
        self.assertEqual(len(text_overlap(make_plan([], [caption(1, 5), lt]), self.design, {})), 1)


class ReadTimeTest(unittest.TestCase):
    design = StubDesign({"caption": "line-fade"})

    def test_read_seconds_weights_cjk_slower(self):
        self.assertAlmostEqual(read_seconds("가" * 14), 1 + FADE_OVERHEAD)
        self.assertAlmostEqual(read_seconds("a" * 17), 1 + FADE_OVERHEAD)
        self.assertAlmostEqual(read_seconds("ab cd"), 4 / 17 + FADE_OVERHEAD)

    def test_long_korean_caption_on_briefly(self):
        [f] = read_time(make_plan([], [caption(0, 1.5, "모든 여정은 하나님의 은혜로 시작되었습니다")]), self.design, {})
        self.assertEqual(f.kind, "read-time")

    def test_short_caption_with_time_is_fine(self):
        self.assertEqual(read_time(make_plan([], [caption(0, 3, "모든 여정은")]), self.design, {}), [])


class LeavesBeforeVoiceTest(unittest.TestCase):
    design = StubDesign({"caption": "line-fade"})
    voices = {"N1": voice("N1", 10, [("모든", 0.0, 0.5), ("여정은", 0.5, 1.2), ("은혜로", 1.4, 2.0)])}

    def test_out_before_voice_offset(self):
        g = {"type": "caption", "voice": "N1", "out": 11.5, "lines": [["모든 여정은 은혜로"]]}
        [f] = text_before_voice(make_plan([], [g]), self.design, self.voices)
        self.assertEqual((f.kind, f.start, f.end), ("leaves-early", 11.5, 12.0))

    def test_derived_out_never_leaves_early(self):
        g = {"type": "caption", "voice": "N1", "lines": [["모든 여정은 은혜로"]]}
        self.assertEqual(text_before_voice(make_plan([], [g]), self.design, self.voices), [])

    def test_caption_carrying_only_the_first_words_may_leave_after_them(self):
        g = {"type": "caption", "voice": "N1", "out": 11.3, "lines": [["모든 여정은"]]}
        self.assertEqual(text_before_voice(make_plan([], [g]), self.design, self.voices), [])


class CaptionTimesMatchTreatmentsTest(unittest.TestCase):
    def test_voice_linked_caption_times_match_compiled_ops(self):
        vt = voice("N1", 4, [("모든", 0.1, 0.5), ("여정은", 0.5, 1.1)])
        for design_id, treatment in (("notebook", "paper-card"), ("cinematic-minimal", "line-fade"),
                                     ("cinematic-minimal", "editorial")):
            g = {"type": "caption", "voice": "N1", "lines": [["모든 여정은"]]}
            ctx = make_ctx(design_id, voices={"N1": vt})
            REGISTRY[("caption", treatment)](ctx, g, {})
            text = next(o for o in ctx.ops.items if o["op"] == "text")
            t_in, t_out = graphic_times(g, treatment, {"N1": vt}, 40.0)
            self.assertAlmostEqual(text["in"], t_in, msg=treatment)
            self.assertAlmostEqual(text["out"], round(t_out + 0.1, 3), msg=treatment)


class ValidateCliTest(unittest.TestCase):
    def write_plan(self, root: Path, shots):
        for f in ("a.mp4", "b.mp4"):
            (root / f).write_text("x")
        plan = {"name": "LINT", "format": {"duration": 20}, "shots": shots}
        (root / "edit.json").write_text(json.dumps(plan))
        return root / "edit.json"

    def run_validate(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["validate", *args, "--design", "notebook"])
        return code, json.loads(out.getvalue()), err.getvalue()

    def test_warnings_keep_exit_zero_and_strict_fails(self):
        with tempfile.TemporaryDirectory() as d:
            plan = self.write_plan(Path(d), [{"clip": "a.mp4", "in": 0, "out": 10}, {"clip": "b.mp4", "in": 10, "out": 10.3},
                                             {"clip": "a.mp4", "in": 10.3, "out": 20}])
            code, info, err = self.run_validate(str(plan))
            self.assertEqual(code, 0)
            self.assertEqual([f["kind"] for f in info["lint"]], ["flash"])
            self.assertIn("warning: [flash]", err)
            self.assertEqual(self.run_validate(str(plan), "--strict")[0], 1)
            self.assertEqual(self.run_validate(str(plan), "--strict", "--min-flash", "0.2")[0], 0)

    def test_clean_plan_has_empty_lint(self):
        with tempfile.TemporaryDirectory() as d:
            plan = self.write_plan(Path(d), [{"clip": "a.mp4", "in": 0, "out": 20}])
            code, info, err = self.run_validate(str(plan), "--strict")
            self.assertEqual((code, info["lint"], err), (0, [], ""))


class LintTest(unittest.TestCase):
    def test_findings_sorted_by_time(self):
        plan = make_plan([shot("a", 0, 10), shot("b", 10, 10.3), shot("c", 10.3, 20)],
                         [caption(1, 1.2, "a long line of text here")])
        found = lint(plan, StubDesign({"caption": "line-fade"}), {})
        self.assertEqual([f.kind for f in found], ["read-time", "flash"])


if __name__ == "__main__":
    unittest.main()
