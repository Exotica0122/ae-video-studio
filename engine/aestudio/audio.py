"""Music ducking keyed from voice onsets/offsets, and fades for long SFX (docs/design.md §8)."""


def _num(x):
    x = round(float(x), 3)
    return int(x) if x == int(x) else x


def duck_keys(voices, duration, *, base=0.0, under_voice=-12.0, breath=-9.0, swell=-4.0, tail=-2.0,
              lead=0.25, ramp=1.0, fade_in=1.2, fade_out=1.2, floor=-40.0):
    voices = sorted(voices)
    keys = [(0, floor), (fade_in, base)]
    if voices:
        first_on = voices[0][0]
        keys += [(first_on - lead - ramp, base), (first_on - lead, under_voice)]
        for (_, off_a), (on_b, _) in zip(voices, voices[1:]):
            gap = on_b - off_a
            if gap < 0.8:
                continue
            if gap < 2.0:
                keys += [(off_a + 0.12, under_voice), ((off_a + on_b) / 2, breath), (on_b - lead, under_voice)]
            else:
                keys += [(off_a + 0.15, under_voice), (off_a + 0.8, swell), (on_b - 0.9, swell), (on_b - lead, under_voice)]
        last_off = voices[-1][1]
        keys += [(last_off + 0.15, under_voice), (last_off + 1.05, tail), (duration - fade_out, tail)]
    else:
        keys += [(duration - fade_out, base)]
    keys.append((duration - 0.05, floor))
    merged = {}
    for t, db in keys:
        merged[round(t, 3)] = db
    return [[_num(t), _num(db)] for t, db in sorted(merged.items())]


def sfx_fade_keys(at, gain_db, onsets):
    later = sorted(o for o in onsets if o > at + 1.0)
    if not later:
        return None
    on = later[0]
    return [[_num(on - 1.0), _num(gain_db)], [_num(on - 0.1), _num(gain_db - 17)]]
