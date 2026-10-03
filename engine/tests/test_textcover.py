"""text-over-people: overlap geometry, findings, and a real Vision pass where macOS allows it."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aestudio import textcover as tc


class GeometryTest(unittest.TestCase):
    def test_disjoint_boxes_do_not_intersect(self):
        self.assertEqual(tc.intersection((0, 0, 0.1, 0.1), (0.5, 0.5, 0.1, 0.1)), 0.0)

    def test_touching_edges_are_not_an_overlap(self):
        self.assertEqual(tc.intersection((0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5)), 0.0)

    def test_intersection_is_the_shared_area(self):
        self.assertAlmostEqual(tc.intersection((0, 0, 0.4, 0.4), (0.2, 0.2, 0.4, 0.4)), 0.04)

    def test_coverage_is_measured_against_the_person_not_the_text(self):
        person = (0.4, 0.2, 0.2, 0.4)
        banner = (0.0, 0.5, 1.0, 0.1)
        self.assertAlmostEqual(tc.covered_fraction(person, [banner]), 0.25)

    def test_several_lines_add_up(self):
        person = (0.0, 0.0, 1.0, 1.0)
        lines = [(0, 0.1, 1, 0.1), (0, 0.3, 1, 0.1)]
        self.assertAlmostEqual(tc.covered_fraction(person, lines), 0.2)

    def test_coverage_never_exceeds_the_whole_person(self):
        self.assertEqual(tc.covered_fraction((0.4, 0.4, 0.1, 0.1), [(0, 0, 1, 1), (0, 0, 1, 1)]), 1.0)

    def test_an_empty_person_box_is_not_covered(self):
        self.assertEqual(tc.covered_fraction((0.5, 0.5, 0, 0), [(0, 0, 1, 1)]), 0.0)


def _detection(text_box, path="still-0030.60.jpg"):
    return {"path": path, "faces": [(0.4, 0.2, 0.2, 0.2)], "humans": [(0.3, 0.1, 0.4, 0.9)],
            "text": [{"box": text_box, "string": "WHO TEACHES THEM"}]}


class CoveredPeopleTest(unittest.TestCase):
    def test_a_title_across_a_face_is_flagged_with_its_words(self):
        hits = tc.covered_people(_detection((0.0, 0.25, 1.0, 0.1)))
        face = next(h for h in hits if h["kind"] == "face")
        self.assertAlmostEqual(face["fraction"], 0.5)
        self.assertEqual(face["text"], ["WHO TEACHES THEM"])

    def test_a_small_overlap_under_the_limit_is_allowed(self):
        self.assertEqual(tc.covered_people(_detection((0.68, 0.5, 0.1, 0.1))), [])

    def test_the_limit_is_a_share_of_the_person_box(self):
        body_only = _detection((0.3, 0.85, 0.4, 0.15))
        self.assertEqual([h["kind"] for h in tc.covered_people(body_only)], ["person"])
        self.assertEqual(tc.covered_people(body_only, limit=0.2), [])

    def test_text_beside_the_people_is_fine(self):
        self.assertEqual(tc.covered_people(_detection((0.75, 0.4, 0.2, 0.1))), [])


class FindingsTest(unittest.TestCase):
    def test_one_finding_per_still(self):
        findings = tc.cover_findings([_detection((0.0, 0.25, 1.0, 0.1)), _detection((0.75, 0.4, 0.2, 0.1), "b.jpg")])
        self.assertEqual([f.status for f in findings], ["warn", "ok"])
        self.assertEqual(findings[0].check, "text-over-people:still-0030.60.jpg")
        self.assertIn("50% of a face", findings[0].detail)
        self.assertIn("WHO TEACHES THEM", findings[0].detail)

    def test_an_unreadable_image_is_skipped_not_passed(self):
        finding = tc.cover_findings([{"path": "x.jpg", "error": "cannot decode"}])[0]
        self.assertEqual(finding.status, "skip")

    def test_without_vision_the_check_says_it_was_skipped(self):
        with mock.patch.object(tc, "vision_unavailable", return_value="needs macOS (Apple Vision)"):
            findings = tc.text_over_people(["still.jpg"])
        self.assertEqual([(f.check, f.status) for f in findings], [("text-over-people", "skip")])
        self.assertIn("needs macOS", findings[0].detail)

    def test_no_stills_means_no_findings(self):
        self.assertEqual(tc.text_over_people([]), [])


@unittest.skipUnless(not tc.vision_unavailable() and shutil.which("ffmpeg"), "needs macOS, swift and ffmpeg")
class VisionTest(unittest.TestCase):
    def test_a_frame_without_people_is_read_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            still = Path(tmp) / "pattern.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=1",
                            "-frames:v", "1", str(still)], check=True)
            detection = tc.detect([still])[0]
            self.assertEqual(detection["faces"], [])
            self.assertEqual(detection["humans"], [])
            for t in detection["text"]:
                self.assertEqual(len(t["box"]), 4)
                self.assertTrue(all(0.0 <= v <= 1.0 for v in t["box"]))
            self.assertEqual(tc.text_over_people([still])[0].status, "ok")


if __name__ == "__main__":
    unittest.main()
