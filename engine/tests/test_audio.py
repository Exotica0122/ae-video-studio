import unittest

from aestudio.audio import duck_keys, level_at, segment_keys, sfx_fade_keys

VOICES = [(8.4, 12.526), (13.646, 19.303), (20.353, 24.236), (24.736, 30.191), (31.191, 37.615),
          (40.515, 47.651), (48.651, 56.918), (57.918, 63.319), (63.819, 69.893), (70.893, 77.799)]
EXPECTED = [[0, -40], [1.2, 5], [7.15, 5], [8.15, -8], [12.646, -8], [13.086, -5], [13.396, -8], [19.423, -8],
            [19.828, -5], [20.103, -8], [30.311, -8], [30.691, -5], [30.941, -8], [37.765, -8], [38.415, -1],
            [39.615, -1], [40.265, -8], [47.771, -8], [48.151, -5], [48.401, -8], [57.038, -8], [57.418, -5],
            [57.668, -8], [70.013, -8], [70.393, -5], [70.643, -8], [77.949, -8], [78.849, 2], [86.899, 2],
            [88.049, -40]]


class AudioTest(unittest.TestCase):
    def test_duck_keys_match_approved_mix(self):
        keys = duck_keys(VOICES, 88.099, base=5, under_voice=-8, breath=-5, swell=-1, tail=2)
        self.assertEqual(keys, EXPECTED)

    def test_no_voices_is_a_plain_fade(self):
        self.assertEqual(duck_keys([], 10.0, base=-3), [[0, -40], [1.2, -3], [8.8, -3], [9.95, -40]])

    def test_voices_are_sorted(self):
        self.assertEqual(duck_keys(list(reversed(VOICES)), 88.099, base=5, under_voice=-8, breath=-5, swell=-1, tail=2),
                         EXPECTED)

    def test_sfx_fade_before_next_voice(self):
        self.assertEqual(sfx_fade_keys(37.965, -7, [31.191, 40.515, 48.651]), [[39.515, -7], [40.415, -24]])

    def test_sfx_fade_none_without_later_voice(self):
        self.assertIsNone(sfx_fade_keys(50.0, -7, [10.0, 50.5]))


class SegmentKeysTest(unittest.TestCase):
    KEYS = [[0, -40], [1, 0], [5, -12], [9, -12], [10, -40]]

    def test_level_at_interpolates_between_keys(self):
        self.assertEqual(level_at(self.KEYS, 3), -6)
        self.assertEqual(level_at(self.KEYS, 20), -40)

    def test_a_segment_fades_from_and_to_the_floor_around_the_duck_curve(self):
        self.assertEqual(segment_keys(self.KEYS, 2, 8, fade_in=1, fade_out=1),
                         [[2, -40], [3, -6], [5, -12], [7, -12], [8, -40]])

    def test_without_fades_it_starts_and_ends_on_the_curve(self):
        self.assertEqual(segment_keys(self.KEYS, 3, 7), [[3, -6], [5, -12], [7, -12]])

if __name__ == "__main__":
    unittest.main()
