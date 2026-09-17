"""Transcript timing: absolute voice times and caption-to-speech word alignment."""
import json
from dataclasses import dataclass
from pathlib import Path

_SKIP = set(" \t\r\n.,!?;:'\"""''()[]{}…·-–—~")


class TimingError(ValueError):
    pass


@dataclass
class Transcript:
    onset: float
    offset: float
    words: list


@dataclass
class VoiceTimes:
    id: str
    onset: float
    offset: float
    words: list


def load_transcript(path) -> Transcript:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        words = [(str(w), float(s), float(e)) for w, s, e in data["words"]]
    except (OSError, KeyError, ValueError, TypeError) as e:
        raise TimingError(f"bad transcript {path}: {e}") from e
    if not words:
        raise TimingError(f"transcript {path} has no words")
    return Transcript(float(data.get("onset", words[0][1])), float(data.get("offset", words[-1][2])), words)


def voice_times(voice, tr: Transcript) -> VoiceTimes:
    shift = voice.at - voice.src_in
    end = voice.src_out if voice.src_out is not None else float("inf")
    kept = [(w, round(s + shift, 3), round(e + shift, 3)) for w, s, e in tr.words
            if s >= voice.src_in - 1e-6 and e <= end + 1e-6]
    if not kept:
        raise TimingError(f"voice {voice.id}: no transcript words inside src_in/src_out")
    if voice.src_in == 0 and voice.src_out is None:
        onset, offset = round(tr.onset + shift, 3), round(tr.offset + shift, 3)
    else:
        onset, offset = kept[0][1], kept[-1][2]
    return VoiceTimes(voice.id, onset, offset, kept)


def _letters(text: str) -> list[str]:
    return [ch.lower() for ch in text if ch not in _SKIP]


def _clock(words) -> list[tuple[str, float]]:
    out = []
    for w, s, e in words:
        letters = _letters(w)
        for i, ch in enumerate(letters):
            out.append((ch, s + (e - s) * i / len(letters)))
    return out


def align_words(caption_words: list[str], words) -> list[float]:
    clock = _clock(words)
    if not clock:
        raise TimingError("transcript has no letters to align against")
    pos, times = 0, []
    for cw in caption_words:
        letters = _letters(cw)
        if not letters:
            times.append(times[-1] if times else round(clock[0][1], 3))
            continue
        j = pos
        while j + len(letters) <= len(clock) and [c for c, _ in clock[j:j + len(letters)]] != letters:
            j += 1
        if j + len(letters) > len(clock):
            raise TimingError(f"caption word '{cw}' not found in the transcript after letter {pos}")
        times.append(round(clock[j][1], 3))
        pos = j + len(letters)
    return times
