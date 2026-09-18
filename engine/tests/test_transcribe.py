import json
import tempfile
import unittest
from pathlib import Path

from aestudio import transcribe
from aestudio.timing import load_transcript

WHISPER = {"text": " 모든 여정은", "segments": [
    {"words": [{"word": " 모든", "start": 0.1, "end": 0.5}, {"word": " 여정은", "start": 0.5, "end": 1.1}]},
    {"words": [{"word": " 작은", "start": 1.2, "end": 1.6}, {"word": " ", "start": 1.6, "end": 1.6}]}]}


class TranscribeTest(unittest.TestCase):
    def test_to_engine_from_segments(self):
        out = transcribe.to_engine(WHISPER)
        self.assertEqual(out["words"], [["모든", 0.1, 0.5], ["여정은", 0.5, 1.1], ["작은", 1.2, 1.6]])
        self.assertEqual((out["onset"], out["offset"]), (0.1, 1.6))

    def test_to_engine_from_flat_words(self):
        out = transcribe.to_engine({"words": [{"word": "hello", "start": 1.0, "end": 1.4}]})
        self.assertEqual(out["words"], [["hello", 1.0, 1.4]])

    def test_segment_and_top_level_words_are_alternatives_not_extras(self):
        both = dict(WHISPER, words=[{"word": " 모든", "start": 0.1, "end": 0.5},
                                    {"word": " 여정은", "start": 0.5, "end": 1.1},
                                    {"word": " 작은", "start": 1.2, "end": 1.6}])
        out = transcribe.to_engine(both)
        self.assertEqual(out["words"], [["모든", 0.1, 0.5], ["여정은", 0.5, 1.1], ["작은", 1.2, 1.6]])

    def test_to_engine_rejects_empty(self):
        with self.assertRaises(transcribe.TranscribeError):
            transcribe.to_engine({"segments": []})

    def test_import_transcript_round_trips_through_the_engine(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "w.json", Path(d) / "t.json"
            src.write_text(json.dumps(WHISPER, ensure_ascii=False), encoding="utf-8")
            transcribe.import_transcript(src, out)
            tr = load_transcript(out)
        self.assertEqual([w[0] for w in tr.words], ["모든", "여정은", "작은"])
        self.assertEqual(tr.onset, 0.1)

    def test_whisper_command_substitutes(self):
        cmd = transcribe.whisper_command("/a/b c.wav", "/tmp/out", template="mywhisper {audio} --out {outdir}")
        self.assertEqual(cmd, ["mywhisper", "/a/b c.wav", "--out", "/tmp/out"])

    def test_transcribe_failure_explains_the_manual_route(self):
        with tempfile.TemporaryDirectory() as d:
            audio, out = Path(d) / "a.wav", Path(d) / "t.json"
            audio.write_text("x")
            with self.assertRaises(transcribe.TranscribeError) as cm:
                transcribe.transcribe(audio, out, template="/usr/bin/false {audio} {outdir}")
        self.assertIn("import-transcript", str(cm.exception))

    def test_transcribe_uses_the_command_output(self):
        with tempfile.TemporaryDirectory() as d:
            audio, out = Path(d) / "a.wav", Path(d) / "t.json"
            audio.write_text("x")
            fake = Path(d) / "fake_whisper.py"       # stands in for a Whisper build
            fake.write_text("import json, pathlib, sys\n"
                            "pathlib.Path(sys.argv[2], 'out.json').write_text(pathlib.Path(sys.argv[3]).read_text())\n",
                            encoding="utf-8")
            payload = Path(d) / "payload.json"
            payload.write_text(json.dumps(WHISPER, ensure_ascii=False), encoding="utf-8")
            result = transcribe.transcribe(audio, out, template=f"python3 {fake} {{audio}} {{outdir}} {payload}")
            self.assertEqual(len(result["words"]), 3)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
