"""taste: collecting, measuring and approving the references, and the stages that read them."""
import io
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from aestudio import designgen, grade, preview, taste
from aestudio.__main__ import main
from aestudio.project import gates, init_project
from aestudio.taste import TasteError
from aestudio.videoqa import taste_check

HAS_FFMPEG = bool(shutil.which("ffmpeg"))


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def solid(path, color, size="160x90"):
    ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s={size}", "-frames:v", 1, path)
    return Path(path)


def split(path, left, right):
    """Left half one colour, right half another."""
    ffmpeg("-f", "lavfi", "-i", f"color=c={right}:s=160x90,drawbox=x=0:y=0:w=80:h=90:c={left}:t=fill",
           "-frames:v", 1, path)
    return Path(path)


def three_shots(path):
    ffmpeg("-f", "lavfi", "-i", "color=c=red:s=160x90:d=1", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=1",
           "-f", "lavfi", "-i", "color=c=green:s=160x90:d=1",
           "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", path)
    return Path(path)


def stats(luma=0.3, contrast=0.5, warmth=0.1, saturation=0.4, hexes=("#202830", "#C86428")):
    return {"palette": [{"hex": h, "weight": round(1 / len(hexes), 3)} for h in hexes], "luma": luma,
            "contrast": contrast, "contrast_std": contrast / 3, "warmth": warmth, "saturation": saturation}


def ref(ref_id, role="want", traits=("mood: quiet",), **kw):
    return {"id": ref_id, "path": f"refs/{ref_id}.png", "source": f"/src/{ref_id}.png", "role": role,
            "kind": "image", "stats": stats(**kw), "traits": list(traits)}


def taste_of(*refs, approved=(), rejected=()):
    return {"version": 1, "refs": list(refs), "approved_traits": list(approved),
            "rejected_traits": list(rejected), "targets": taste.targets(list(refs))}


def run_cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main([str(a) for a in argv])
    return code, out.getvalue()


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required")
class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "video"
        init_project(self.root)
        self.src = Path(self.tmp.name) / "src"
        self.src.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_local_image_is_copied_and_its_source_role_and_date_recorded(self):
        image = solid(self.src / "look.png", "orange")
        added = taste.add_refs(self.root, [image], role="avoid")
        self.assertEqual(added[0]["id"], "ref-01")
        self.assertTrue((self.root / "refs" / "ref-01.png").exists())
        sources = json.loads((self.root / "refs" / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(sources[0]["source"], str(image.resolve()))
        self.assertEqual(sources[0]["role"], "avoid")
        self.assertRegex(sources[0]["added"], r"^\d{4}-\d\d-\d\d$")

    def test_adding_the_same_source_twice_keeps_one_copy(self):
        image = solid(self.src / "look.png", "orange")
        taste.add_refs(self.root, [image])
        taste.add_refs(self.root, [image])
        self.assertEqual(len(json.loads((self.root / "refs" / "sources.json").read_text(encoding="utf-8"))), 1)

    def test_a_missing_file_or_an_unknown_role_is_refused(self):
        with self.assertRaises(TasteError):
            taste.add_refs(self.root, [self.src / "absent.png"])
        with self.assertRaises(TasteError):
            taste.add_refs(self.root, [solid(self.src / "a.png", "red")], role="maybe")

    def test_a_video_reference_is_sampled_into_frames(self):
        added = taste.add_refs(self.root, [three_shots(self.src / "clip.mp4")], at=[0.5, 2.5])
        self.assertEqual(added[0]["kind"], "video")
        self.assertEqual(len(added[0]["frames"]), 2)
        for frame in added[0]["frames"]:
            self.assertTrue((self.root / frame).exists(), frame)

    def test_a_url_is_downloaded_with_a_browser_user_agent(self):
        solid(self.src / "web.png", "teal")
        agents = []

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                agents.append(self.headers.get("User-Agent"))
                return super().do_GET()

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(self.src)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/web.png"
            added = taste.add_refs(self.root, [url])
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(added[0]["source"], url)
        self.assertTrue((self.root / added[0]["file"]).exists())
        self.assertIn("Mozilla", agents[0])

    def test_a_web_page_without_yt_dlp_says_how_to_get_the_image(self):
        (self.src / "page.html").write_text("<html></html>", encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(preview.ChoiceHandler, directory=str(self.src)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with mock.patch.object(taste, "_ytdlp", return_value=None):
                with self.assertRaises(TasteError) as caught:
                    taste.add_refs(self.root, [f"http://127.0.0.1:{server.server_address[1]}/page.html"])
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("image address", str(caught.exception))


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required")
class MeasureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_two_colour_image_gives_both_colours_as_the_palette(self):
        measured = taste.measure(split(self.dir / "s.png", "0x1E2A50", "0xC86428"))
        hexes = [s["hex"] for s in measured["palette"]]
        self.assertEqual(len(hexes), 2)
        for want in ((30, 42, 80), (200, 100, 40)):
            self.assertLess(min(taste._dist(taste.rgb_of(h), want) for h in hexes), 12, hexes)

    def test_warmth_follows_the_red_blue_balance(self):
        self.assertGreater(taste.measure(solid(self.dir / "w.png", "0xD08040"))["warmth"], 0.2)
        self.assertLess(taste.measure(solid(self.dir / "c.png", "0x4070D0"))["warmth"], -0.2)

    def test_contrast_is_high_for_black_and_white_and_nil_for_flat_grey(self):
        self.assertGreater(taste.measure(split(self.dir / "bw.png", "black", "white"))["contrast"], 0.9)
        flat = taste.measure(solid(self.dir / "g.png", "gray"))
        self.assertLess(flat["contrast"], 0.02)
        self.assertLess(flat["saturation"], 0.05)

    def test_a_video_reference_adds_its_cut_rate(self):
        measured = taste.measure(three_shots(self.dir / "v.mp4"))
        self.assertEqual(measured["cuts"], 2)
        self.assertAlmostEqual(measured["cuts_per_min"], 40.0, delta=2)

    def test_the_pure_python_palette_matches_without_numpy(self):
        pixels = [(10, 10, 10)] * 30 + [(240, 200, 40)] * 10
        with mock.patch.object(taste, "_kmeans_np", return_value=None):
            result = taste.palette(pixels)
        self.assertEqual([s["hex"] for s in result], ["#0A0A0A", "#F0C828"])
        self.assertEqual([s["weight"] for s in result], [0.75, 0.25])


class TasteFileTest(unittest.TestCase):
    def test_targets_come_from_the_want_refs_and_the_avoid_refs_stand_apart(self):
        refs = [ref("ref-01", luma=0.2, warmth=0.1), ref("ref-02", luma=0.4, warmth=0.2),
                ref("ref-03", role="avoid", luma=0.9, hexes=("#F0F0F0",))]
        goal = taste.targets(refs)
        self.assertEqual(goal["refs"], ["ref-01", "ref-02"])
        self.assertEqual(goal["luma"], {"min": 0.2, "max": 0.4, "mean": 0.3})
        self.assertAlmostEqual(goal["warmth"]["mean"], 0.15)
        self.assertEqual(goal["avoid"]["refs"], ["ref-03"])
        self.assertNotIn("#F0F0F0", [s["hex"] for s in goal["palette"]])

    def test_near_identical_swatches_from_two_refs_merge_into_one_target(self):
        goal = taste.targets([ref("ref-01", hexes=("#C86428",)), ref("ref-02", hexes=("#CA6629",))])
        self.assertEqual(len(goal["palette"]), 1)
        self.assertAlmostEqual(goal["palette"][0]["weight"], 1.0)

    def test_the_validator_names_every_problem(self):
        bad = taste_of(ref("ref-01"), approved=["mood: quiet"], rejected=["mood: quiet"])
        bad["refs"].append({"id": "ref-01", "path": "x", "source": "y", "role": "maybe", "stats": None,
                            "traits": [""]})
        with self.assertRaises(TasteError) as caught:
            taste.validate_taste(bad)
        message = str(caught.exception)
        for expected in ("duplicate id", "'role'", "'traits'", "stats", "both approved and rejected"):
            self.assertIn(expected, message)

    def test_mood_traits_become_mood_words(self):
        words = taste.mood_words({"approved_traits": ["mood: quiet, reverent", "type: condensed sans"]})
        self.assertEqual(words, ["quiet", "reverent"])

    def test_no_taste_file_means_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(taste.approved_taste(tmp))


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required")
class GateFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "video"
        init_project(self.root)
        src = Path(self.tmp.name)
        taste.add_refs(self.root, [split(src / "a.png", "0x1E2A50", "0xC86428")])
        taste.add_refs(self.root, [solid(src / "b.png", "white")], role="avoid")
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.tmp.cleanup()

    def _write_traits(self, traits):
        working = self.root / taste.WORKING
        data = json.loads(working.read_text(encoding="utf-8"))
        for r, t in zip(data["refs"], traits):
            r["traits"] = t
        working.write_text(json.dumps(data), encoding="utf-8")

    def test_re_measuring_keeps_the_traits_already_written(self):
        taste.measure_refs(self.root)
        self._write_traits([["layout: big left-aligned type"], ["mood: clinical"]])
        data = taste.measure_refs(self.root)
        self.assertEqual(data["refs"][0]["traits"], ["layout: big left-aligned type"])
        self.assertEqual(data["targets"]["refs"], ["ref-01"])

    def test_approval_is_refused_until_every_ref_has_traits(self):
        taste.measure_refs(self.root)
        with self.assertRaises(TasteError) as caught:
            taste.choose(self.root)
        self.assertIn("ref-01", str(caught.exception))

    def test_the_board_records_ticks_and_approval_closes_the_gate(self):
        taste.measure_refs(self.root)
        self._write_traits([["mood: quiet", "type: condensed sans"], ["layout: crowded grid"]])
        board = taste.render_board(self.root)
        page = board.read_text(encoding="utf-8")
        self.assertIn("type: condensed sans", page)
        self.assertIn("background:#", page)
        self.server, url = preview.serve(board.parent, page=taste.BOARD, handler=taste.TasteHandler)
        body = json.dumps({"id": "taste", "approved": ["mood: quiet"], "rejected": ["layout: crowded grid"],
                           "note": "darker"}).encode("utf-8")
        request = urllib.request.Request(f"{url}/choose", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
        out = taste.choose(self.root)
        approved = taste.load_taste(out)
        self.assertEqual(approved["approved_traits"], ["mood: quiet"])
        self.assertEqual(approved["rejected_traits"], ["layout: crowded grid"])
        self.assertEqual(approved["note"], "darker")
        self.assertTrue(next(g for g in gates(self.root) if g.label == "taste").done)

    def test_the_board_refuses_a_trait_no_reference_has(self):
        taste.measure_refs(self.root)
        self._write_traits([["mood: quiet"], ["mood: loud"]])
        board = taste.render_board(self.root)
        self.server, url = preview.serve(board.parent, page=taste.BOARD, handler=taste.TasteHandler)
        body = json.dumps({"approved": ["invented"], "rejected": []}).encode("utf-8")
        request = urllib.request.Request(f"{url}/choose", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 400)

    def test_the_cli_runs_the_gate_end_to_end(self):
        code, out = run_cli("taste-measure", "--dir", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["untraited"], ["ref-01", "ref-02"])
        self._write_traits([["mood: quiet"], ["mood: loud"]])
        code, out = run_cli("taste-board", "--dir", self.root, "--no-serve")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "refs" / "board.html").exists())
        code, out = run_cli("taste-choose", "--dir", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["refs"], 2)


class NoReferencesTest(unittest.TestCase):
    def test_none_approves_an_empty_taste_that_downstream_ignores(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            out = taste.choose(tmp, none=True)
            data = taste.load_taste(out)
            self.assertEqual((data["refs"], data["targets"]), ([], {}))
            self.assertTrue(next(g for g in gates(tmp) if g.label == "taste").done)


DARK = taste_of(ref("ref-01", luma=0.12, hexes=("#101418", "#2A6F8F")),
                ref("ref-02", luma=0.18, hexes=("#14181C", "#3A7FA0")))


class DesignBiasTest(unittest.TestCase):
    def _propose(self, taste_data=None):
        return designgen.propose(["warm"], log={"clips": []}, installed_only=False, pairings=1,
                                 taste=taste_data)

    def test_without_a_taste_file_proposals_are_unchanged(self):
        self.assertEqual([d.recipe for d in self._propose()], [d.recipe for d in self._propose(None)])
        self.assertTrue(all(not d.refs for d in self._propose()))

    def test_the_references_brightness_breaks_ties_between_directions(self):
        light = taste_of(ref("ref-01", luma=0.9, hexes=("#F4F1EA", "#B8452F")))
        first = lambda drafts: drafts[0].recipe["id"]
        self.assertTrue(first(designgen.propose([], log={"clips": []}, installed_only=False, pairings=1,
                                                taste=DARK)).startswith("cinematic-minimal"))
        self.assertFalse(first(designgen.propose([], log={"clips": []}, installed_only=False, pairings=1,
                                                 taste=light)).startswith("cinematic-minimal"))

    def test_approved_mood_traits_rank_like_brief_moods_and_the_refs_lend_the_accent(self):
        calm = lambda t: designgen.propose(["calm"], log={"clips": []}, installed_only=False, pairings=1, taste=t)
        self.assertTrue(calm(None)[0].recipe["id"].startswith("editorial-press"))
        moody = {**DARK, "approved_traits": ["mood: restrained, premium"]}
        top = calm(moody)[0]
        self.assertTrue(top.recipe["id"].startswith("cinematic-minimal"))
        self.assertEqual(top.recipe["tokens"]["palette"]["accent"], designgen.accent_from_taste(DARK))

    def test_every_draft_cites_the_refs_it_draws_on(self):
        for draft in self._propose(DARK):
            self.assertTrue(draft.refs, draft.id)
            self.assertEqual(draft.recipe["taste_refs"], draft.refs)
            self.assertTrue(set(draft.refs) <= {"ref-01", "ref-02"})


class GradeBiasTest(unittest.TestCase):
    def test_the_reference_look_moves_contrast_and_warmth_towards_the_refs(self):
        goal = taste_of(ref("ref-01", contrast=0.8, warmth=0.15, saturation=0.3, luma=0.45))["targets"]
        footage = {"luma": 0.45, "contrast": 0.5, "warmth": 0.0, "saturation": 0.3}
        look = grade.look_from_taste(goal, footage)
        self.assertGreater(look.ae["contrast"], 0)
        self.assertGreater(look.ae["temperature"], 0)
        self.assertEqual(look.ae["saturation"], 0)
        self.assertIn("colortemperature=temperature=", look.preview)

    def test_extreme_references_are_clamped_to_a_grade_not_a_relight(self):
        goal = taste_of(ref("ref-01", contrast=1.0, warmth=-0.9, saturation=1.0, luma=0.95))["targets"]
        look = grade.look_from_taste(goal, {"luma": 0.1, "contrast": 0.1, "warmth": 0.5, "saturation": 0.0})
        self.assertEqual((look.ae["contrast"], look.ae["temperature"], look.ae["saturation"]), (25, -25, 25))
        self.assertEqual(look.ae["exposure"], 0.3)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required")
class GradeCliTest(unittest.TestCase):
    def test_a_project_with_a_taste_file_offers_and_records_the_reference_look_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            solid(root / "analysis" / "frames" / "c0.jpg", "gray", size="320x180")
            log = {"clips": [{"name": "c0.MP4", "path": "/nowhere/c0.MP4", "luma": 0.5, "duration": 5.0,
                              "frames": [{"at": 0.5, "file": "frames/c0.jpg"}]}]}
            (root / "analysis" / "footage.json").write_text(json.dumps(log), encoding="utf-8")
            (root / "plan" / "taste.json").write_text(json.dumps(taste_of(ref("ref-01", warmth=0.2))),
                                                      encoding="utf-8")
            out = root / "preview" / "grade"
            code, printed = run_cli("grade-propose", "--analysis", root / "analysis", "--out", out)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(printed)["looks"][0], grade.TASTE_LOOK)
            code, printed = run_cli("grade-choose", "--dir", out, "--analysis", root / "analysis",
                                    "--out", root / "plan" / "grade.json", "--id", grade.TASTE_LOOK)
            self.assertEqual(code, 0)
            saved = json.loads((root / "plan" / "grade.json").read_text(encoding="utf-8"))
            self.assertGreater(saved["look"]["temperature"], 0)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required")
class TasteCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        want = split(self.dir / "want.png", "0x1E2A50", "0xC86428")
        avoid = solid(self.dir / "avoid.png", "0xF0F0F0")
        refs = [{**ref("ref-01"), "stats": taste.measure(want)},
                {**ref("ref-02", role="avoid"), "stats": taste.measure(avoid)}]
        self.taste = taste_of(*refs)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stills_that_match_the_references_pass(self):
        still = split(self.dir / "still.png", "0x202C52", "0xC4622A")
        findings = taste_check([still], self.taste)
        self.assertEqual({f.status for f in findings}, {"ok"}, [(f.check, f.detail) for f in findings])

    def test_stills_that_look_like_the_avoid_refs_are_flagged(self):
        findings = {f.check: f for f in taste_check([solid(self.dir / "pale.png", "0xEEEEEE")], self.taste)}
        for check in ("taste:palette", "taste:luma", "taste:avoid"):
            self.assertEqual(findings[check].status, "warn", check)

    def test_no_targets_means_no_checks(self):
        self.assertEqual(taste_check([self.dir / "anything.png"], {"targets": {}}), [])


if __name__ == "__main__":
    unittest.main()
