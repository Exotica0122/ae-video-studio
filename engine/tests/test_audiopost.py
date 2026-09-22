"""audio-post: parsing ffmpeg's analysis, loudness gains, and laying takes out in time.

The parser tests use output captured from a real ffmpeg run, so they stay honest about the
shape ffmpeg actually emits rather than the shape it would be convenient for it to emit.
"""
import unittest

from aestudio import audiopost as ap

# captured from: ffmpeg -i probe.wav -af loudnorm=print_format=json -f null -
LOUDNORM = """[Parsed_loudnorm_0 @ 0xa66c3c9c0]
{
\t"input_i" : "-20.31",
\t"input_tp" : "-3.05",
\t"input_lra" : "5.20",
\t"input_thresh" : "-30.67",
\t"output_i" : "-22.85",
\t"target_offset" : "-1.15"
}
[out#0/null @ 0xa66c3c180] video:0KiB audio:1500KiB muxing overhead: unknown
size=N/A time=00:00:04.00 bitrate=N/A speed= 114x elapsed=0:00:00.03
"""

# captured from: ffmpeg -i probe.wav -af silencedetect=noise=-40dB:d=0.3 -f null -
SILENCE_BOTH_ENDS = """[Parsed_silencedetect_0 @ 0x824c3c9c0] silence_start: 0
[Parsed_silencedetect_0 @ 0x824c3c9c0] silence_end: 1.00068 | silence_duration: 1.00068
[Parsed_silencedetect_0 @ 0x824c3c9c0] silence_start: 2.999342
[Parsed_silencedetect_0 @ 0x824c3c9c0] silence_end: 4 | silence_duration: 1.000658
"""


def _measured(lufs=-20.0, peak=-6.0, duration=4.0):
    return ap.Loudness(lufs, peak, duration)


def _take(tid, speaker="", onset=0.0, length=2.0, gap_after=None, lufs=-20.0, peak=-6.0):
    return ap.Take(id=tid, file=f"voice/{tid}.wav", speaker=speaker, gap_after=gap_after,
                   loudness=_measured(lufs, peak), speech=ap.Speech(onset, onset + length))


class LoudnessParsingTest(unittest.TestCase):
    def test_it_finds_the_json_block_despite_later_log_lines(self):
        loud = ap.parse_loudness(LOUDNORM, duration=4.0)
        self.assertAlmostEqual(loud.lufs, -20.31)
        self.assertAlmostEqual(loud.peak_db, -3.05)

    def test_output_without_a_measurement_block_is_an_error(self):
        with self.assertRaises(ap.AudioPostError):
            ap.parse_loudness("ffmpeg version 8.0\nno json here\n")

    def test_a_truncated_block_is_an_error_rather_than_a_wrong_number(self):
        with self.assertRaises(ap.AudioPostError):
            ap.parse_loudness('{ "input_i" : "-20.31", ')


class SilenceParsingTest(unittest.TestCase):
    def test_trailing_silence_is_found_although_it_has_both_a_start_and_an_end(self):
        speech = ap.parse_silences(SILENCE_BOTH_ENDS, duration=4.0)
        self.assertEqual((speech.onset, speech.offset), (1.001, 2.999))

    def test_a_file_with_no_silence_at_all_is_speech_end_to_end(self):
        speech = ap.parse_silences("", duration=3.0)
        self.assertEqual((speech.onset, speech.offset), (0.0, 3.0))

    def test_leading_silence_only(self):
        log = "silence_start: 0\nsilence_end: 0.75 | silence_duration: 0.75\n"
        self.assertEqual(ap.parse_silences(log, duration=5.0), ap.Speech(0.75, 5.0))

    def test_a_silence_starting_mid_file_is_not_mistaken_for_leading_room_tone(self):
        log = "silence_start: 2.0\nsilence_end: 2.5 | silence_duration: 0.5\n"
        speech = ap.parse_silences(log, duration=5.0)
        self.assertEqual(speech.onset, 0.0, "speech starts at the top of this file")
        self.assertEqual(speech.offset, 5.0, "a pause in the middle is not the end of speech")


class GainTest(unittest.TestCase):
    def test_a_quiet_take_is_lifted_to_target(self):
        self.assertEqual(ap.gain_for(_measured(lufs=-24.0, peak=-12.0)), 8.0)

    def test_headroom_wins_when_target_would_clip_the_peak(self):
        gain = ap.gain_for(_measured(lufs=-24.0, peak=-2.0))
        self.assertEqual(gain, 0.5, "peak -2.0 can only rise 0.5 dB before the -1.5 ceiling")

    def test_a_silent_file_is_refused_rather_than_boosted_by_fifty_decibels(self):
        with self.assertRaises(ap.AudioPostError):
            ap.gain_for(_measured(lufs=-91.0, peak=-90.0))


class PlacementTest(unittest.TestCase):
    def test_a_change_of_speaker_gets_more_air_than_a_new_line(self):
        placed = ap.place([_take("N1", "narrator"), _take("N2", "narrator"), _take("T1", "teacher")])
        spans = [e["speech"] for e in placed]
        self.assertAlmostEqual(spans[1][0] - spans[0][1], ap.GAP_SAME_SPEAKER, places=3)
        self.assertAlmostEqual(spans[2][0] - spans[1][1], ap.GAP_NEW_SPEAKER, places=3)

    def test_an_explicit_gap_overrides_the_default(self):
        placed = ap.place([_take("N1", "narrator", gap_after=3.0), _take("N2", "narrator")])
        self.assertAlmostEqual(placed[1]["speech"][0] - placed[0]["speech"][1], 3.0, places=3)

    def test_leading_silence_never_pushes_a_take_before_zero(self):
        placed = ap.place([_take("N1", onset=0.8), _take("N2", onset=0.1)])
        self.assertGreaterEqual(min(e["at"] for e in placed), 0.0)
        self.assertEqual(placed[0]["at"], 0.0, "the sequence is shifted, not clamped per take")

    def test_shifting_preserves_every_gap_exactly(self):
        placed = ap.place([_take("N1", "a", onset=0.9), _take("N2", "a", onset=0.0)])
        self.assertAlmostEqual(placed[1]["speech"][0] - placed[0]["speech"][1],
                               ap.GAP_SAME_SPEAKER, places=3)

    def test_an_unmeasured_take_is_refused(self):
        with self.assertRaises(ap.AudioPostError):
            ap.place([ap.Take(id="N1", file="voice/n1.wav")])

    def test_voice_spans_are_what_the_ducking_curve_consumes(self):
        placed = ap.place([_take("N1"), _take("N2")])
        spans = ap.voice_spans(placed)
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(isinstance(s, tuple) and len(s) == 2 for s in spans))


class MusicTest(unittest.TestCase):
    def test_music_longer_than_the_video_is_simply_trimmed(self):
        self.assertEqual(ap.music_plan(30.0, 120.0), [[0, 30.0]])

    def test_short_music_loops_to_cover_the_video(self):
        segments = ap.music_plan(25.0, 10.0)
        self.assertEqual(sum(b - a for a, b in segments), 25.0)
        self.assertEqual(segments[0], [0, 10.0])

    def test_a_sliver_of_a_final_loop_is_dropped_rather_than_glitching(self):
        segments = ap.music_plan(20.4, 10.0)
        self.assertEqual(segments, [[0, 10.0], [0, 10.0]], "0.4s of a third loop would click")

    def test_zero_lengths_are_refused(self):
        with self.assertRaises(ap.AudioPostError):
            ap.music_plan(0, 10.0)
        with self.assertRaises(ap.AudioPostError):
            ap.music_plan(10.0, 0)


class SpecTest(unittest.TestCase):
    def test_takes_without_an_id_or_file_are_refused(self):
        for spec in ({"takes": [{"file": "a.wav"}]}, {"takes": [{"id": "N1"}]}, {"takes": []}):
            with self.assertRaises(ap.AudioPostError):
                ap.load_takes(spec)

    def test_duplicate_ids_are_refused_because_captions_reference_them(self):
        with self.assertRaises(ap.AudioPostError) as caught:
            ap.load_takes({"takes": [{"id": "N1", "file": "a.wav"}, {"id": "N1", "file": "b.wav"}]})
        self.assertIn("duplicate", str(caught.exception))

    def test_a_missing_audio_file_is_named(self):
        with self.assertRaises(ap.AudioPostError) as caught:
            ap.load_takes({"takes": [{"id": "N1", "file": "nope/missing.wav"}]})
        self.assertIn("missing.wav", str(caught.exception))


class MergeTest(unittest.TestCase):
    def test_merging_audio_leaves_the_approved_timeline_untouched(self):
        plan = {"format": {"fps": 24}, "shots": [{"clip": "a.mp4"}],
                "graphics": [{"type": "end-card"}], "voices": [{"id": "old"}]}
        merged = ap.merge_into(plan, {"voices": [{"id": "N1"}], "music": {"file": "m.wav"}})
        self.assertEqual(merged["shots"], [{"clip": "a.mp4"}])
        self.assertEqual(merged["graphics"], [{"type": "end-card"}])
        self.assertEqual(merged["format"], {"fps": 24})
        self.assertEqual(merged["voices"], [{"id": "N1"}], "voices are replaced, not appended")

    def test_merging_does_not_mutate_the_plan_it_was_given(self):
        plan = {"voices": [{"id": "old"}]}
        ap.merge_into(plan, {"voices": [{"id": "N1"}]})
        self.assertEqual(plan["voices"], [{"id": "old"}])


if __name__ == "__main__":
    unittest.main()
