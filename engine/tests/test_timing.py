import json
import tempfile
import unittest
from pathlib import Path

from aestudio.plan import Voice
from aestudio.timing import TimingError, Transcript, align_words, load_transcript, voice_times

WORDS = [["모든", 0.10, 0.50], ["여정은", 0.50, 1.10], ["작은", 1.20, 1.60], ["한", 1.60, 1.80],
         ["걸음에서", 1.80, 2.60], ["시작됩니다.", 2.60, 3.50]]


class TimingTest(unittest.TestCase):
    def test_load_transcript_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps({"words": WORDS}), encoding="utf-8")
            tr = load_transcript(p)
        self.assertEqual((tr.onset, tr.offset), (0.10, 3.50))
        self.assertEqual(tr.words[1], ("여정은", 0.50, 1.10))

    def test_voice_times_shift(self):
        tr = Transcript(0.08, 3.52, [tuple(w) for w in WORDS])
        vt = voice_times(Voice("N1", Path("a.wav"), 10.0, Path("t.json")), tr)
        self.assertEqual((vt.onset, vt.offset), (10.08, 13.52))
        self.assertEqual(vt.words[0], ("모든", 10.1, 10.5))

    def test_voice_times_trimmed_range(self):
        tr = Transcript(0.08, 3.52, [tuple(w) for w in WORDS])
        v = Voice("I1", Path("a.mov"), 20.0, Path("t.json"), src_in=1.2, src_out=2.6)
        vt = voice_times(v, tr)
        self.assertEqual([w[0] for w in vt.words], ["작은", "한", "걸음에서"])
        self.assertEqual((vt.onset, vt.offset), (20.0, 21.4))

    def test_align_splits_inside_a_spoken_word(self):
        words = [tuple(w) for w in WORDS]
        times = align_words(["모든", "여정은", "작은", "한", "걸음", "에서", "시작됩니다."], words)
        self.assertEqual(times[:5], [0.1, 0.5, 1.2, 1.6, 1.8])
        self.assertAlmostEqual(times[5], 2.2)   # "에서" starts half-way through "걸음에서"
        self.assertEqual(times[6], 2.6)

    def test_align_skips_words_not_in_caption_and_punctuation(self):
        words = [tuple(w) for w in WORDS]
        self.assertEqual(align_words(["“", "작은", "걸음에서”"], words), [0.1, 1.2, 1.8])

    def test_align_raises_when_text_is_missing(self):
        with self.assertRaisesRegex(TimingError, "'바다' not found"):
            align_words(["모든", "바다"], [tuple(w) for w in WORDS])


if __name__ == "__main__":
    unittest.main()
