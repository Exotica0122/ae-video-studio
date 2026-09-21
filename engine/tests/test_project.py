"""The project folder: created once, never clobbered, and honest about which gates are done."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from aestudio.project import (DECISIONS, ProjectError, gates, init_project, next_gate,
                              record_decision)


class InitTest(unittest.TestCase):
    def test_it_creates_the_documented_layout_and_a_decision_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "video"
            created = init_project(root)
            for name in ("plan", "analysis/transcripts", "analysis/frames", "analysis/sheets",
                         "preview", "build", "exports", "qa"):
                self.assertTrue((root / name).is_dir(), name)
            self.assertIn(DECISIONS, created)
            self.assertIn("# Decisions", (root / DECISIONS).read_text(encoding="utf-8"))

    def test_re_running_it_creates_nothing_and_preserves_existing_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "video"
            init_project(root)
            (root / "plan" / "design.json").write_text('{"approved": true}', encoding="utf-8")
            record_decision(root, 2, "Paper Notebook · Paperlogy")
            before = (root / DECISIONS).read_text(encoding="utf-8")

            self.assertEqual(init_project(root), [], "a second init must create nothing")
            self.assertEqual((root / "plan" / "design.json").read_text(encoding="utf-8"),
                             '{"approved": true}')
            self.assertEqual((root / DECISIONS).read_text(encoding="utf-8"), before)

    def test_a_file_where_the_project_should_go_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notafolder"
            path.write_text("x", encoding="utf-8")
            with self.assertRaises(ProjectError):
                init_project(path)


class GateTest(unittest.TestCase):
    def test_a_fresh_project_starts_at_gate_0_with_nothing_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            self.assertEqual([g.done for g in gates(tmp)], [False] * 8)
            self.assertEqual(next_gate(tmp).number, 0)

    def test_an_artifact_on_disk_marks_its_gate_done_and_moves_the_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            (Path(tmp) / "plan" / "brief.md").write_text("brief", encoding="utf-8")
            (Path(tmp) / "plan" / "story.md").write_text("story", encoding="utf-8")
            done = [g.number for g in gates(tmp) if g.done]
            self.assertEqual(done, [0, 1])
            self.assertEqual(next_gate(tmp).number, 2)

    def test_a_logged_decision_without_its_artifact_reads_as_recorded_not_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            record_decision(tmp, 0, "60s promo, church audience")
            gate = gates(tmp)[0]
            self.assertFalse(gate.done, "the brief file is what later stages read")
            self.assertEqual(gate.state, "recorded")
            self.assertEqual(next_gate(tmp).number, 0)

    def test_late_gates_have_no_artifact_so_the_log_is_their_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            record_decision(tmp, 6, "Review render approved with two notes")
            by_number = {g.number: g for g in gates(tmp)}
            self.assertTrue(by_number[6].done)
            self.assertFalse(by_number[7].done)


class DecisionTest(unittest.TestCase):
    def test_entries_append_newest_last_and_keep_the_earlier_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            record_decision(tmp, 2, "Paper Notebook", today=date(2026, 9, 21))
            record_decision(tmp, 2, "Changed to Cinematic Minimal", today=date(2026, 9, 22))
            text = (Path(tmp) / DECISIONS).read_text(encoding="utf-8")
            self.assertLess(text.index("Paper Notebook"), text.index("Cinematic Minimal"),
                            "history of a changed mind must survive")
            self.assertIn("## Gate 2 — design (2026-09-22)", text)

    def test_the_detail_is_written_under_the_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            record_decision(tmp, 1, "Three beats", detail="Open on the classroom, close on the invitation.")
            self.assertIn("Open on the classroom", (Path(tmp) / DECISIONS).read_text(encoding="utf-8"))

    def test_an_unknown_gate_or_an_empty_decision_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_project(tmp)
            with self.assertRaises(ProjectError):
                record_decision(tmp, 9, "nope")
            with self.assertRaises(ProjectError):
                record_decision(tmp, 1, "   ")

    def test_recording_before_init_tells_the_user_to_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectError) as caught:
                record_decision(tmp, 0, "something")
            self.assertIn("init", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
