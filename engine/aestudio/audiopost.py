"""Author the audio half of plan/edit.json from the real recordings.

Three jobs the editor would otherwise do by ear: measure each file's loudness so the mix
lands on target, find where speech actually starts and stops so silence at the head of a
take does not become a pause in the video, and place the takes with breathing room between
them. ffmpeg reports all of this on stderr, not stdout, so this module runs it directly
rather than through media.run.
"""
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

TARGET_LUFS = -16.0          # docs/design.md §8: voices sit at -16 LUFS
PEAK_CEILING = -1.5          # true peak never above this
SILENCE_DB = -40.0           # quieter than this counts as room tone, not speech
MIN_SILENCE = 0.30           # ignore gaps shorter than this when finding speech bounds

# Pauses between takes. A change of speaker needs more air than a new sentence from the
# same one - this is what "natural pauses between narration and testimony" means in numbers.
GAP_SAME_SPEAKER = 0.55
GAP_NEW_SPEAKER = 1.10


class AudioPostError(RuntimeError):
    pass


@dataclass
class Loudness:
    lufs: float
    peak_db: float
    duration: float

    @property
    def measured(self) -> bool:
        return self.lufs > -70.0


@dataclass
class Speech:
    onset: float
    offset: float

    @property
    def length(self) -> float:
        return max(0.0, self.offset - self.onset)


def _ffmpeg(args: list, what: str) -> str:
    """Run ffmpeg and hand back stderr, where its analysis filters report."""
    binary = shutil.which("ffmpeg")
    if not binary:
        raise AudioPostError("ffmpeg not found — install it with `brew install ffmpeg`")
    result = subprocess.run([binary] + [str(a) for a in args], capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise AudioPostError(f"{what} failed: " + " / ".join(tail))
    return result.stderr or ""


def parse_loudness(stderr: str, duration: float = 0.0) -> Loudness:
    """Pull the JSON block `loudnorm=print_format=json` prints.

    ffmpeg keeps logging after that block (muxing overhead, the size= line), so the block is
    matched on the measurement it must contain rather than by taking the last brace.
    """
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)
    if not match:
        raise AudioPostError("could not find loudnorm output; is this file really audio?")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise AudioPostError(f"unreadable loudnorm output: {e}") from e
    try:
        return Loudness(float(data["input_i"]), float(data["input_tp"]), duration)
    except (KeyError, TypeError, ValueError) as e:
        raise AudioPostError(f"loudnorm output is missing a measurement: {e}") from e


def measure(path) -> Loudness:
    path = Path(path)
    if not path.exists():
        raise AudioPostError(f"no such audio file: {path}")
    out = _ffmpeg(["-v", "info", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                  f"measuring {path.name}")
    return parse_loudness(out, duration=_duration(path))


def _duration(path) -> float:
    binary = shutil.which("ffprobe")
    if not binary:
        raise AudioPostError("ffprobe not found — install it with `brew install ffmpeg`")
    out = subprocess.run([binary, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float((out.stdout or "").strip())
    except ValueError:
        return 0.0


def gain_for(loudness: Loudness, target: float = TARGET_LUFS, ceiling: float = PEAK_CEILING) -> float:
    """Gain that puts the file on target without pushing its peak past the ceiling.

    Loudness is an average, so a take with one loud consonant can hit the ceiling before it
    reaches target. Headroom wins: a clipped peak is audible, a decibel under target is not.
    """
    if not loudness.measured:
        raise AudioPostError("this file measures as silence; check it is the right recording")
    wanted = target - loudness.lufs
    headroom = ceiling - loudness.peak_db
    return round(min(wanted, headroom), 2)


def parse_silences(stderr: str, duration: float, edge: float = 0.05) -> Speech:
    """Turn silencedetect's log into the span where speech actually lives.

    A silence that runs to the end of the file is reported with both a start and an end, so a
    trailing silence cannot be spotted by looking for an unmatched start: it is spotted by its
    end landing on the end of the file.
    """
    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?[\d.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*(-?[\d.]+)", stderr)]
    spans = [(start, ends[i] if i < len(ends) else duration) for i, start in enumerate(starts)]
    onset, offset = 0.0, duration
    if spans and spans[0][0] <= edge:
        onset = spans[0][1]
    if spans and duration and spans[-1][1] >= duration - edge and spans[-1][0] > onset:
        offset = spans[-1][0]
    return Speech(round(onset, 3), round(max(onset, offset), 3))


def speech_bounds(path, threshold_db: float = SILENCE_DB, min_silence: float = MIN_SILENCE) -> Speech:
    path = Path(path)
    out = _ffmpeg(["-v", "info", "-i", path,
                   "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}", "-f", "null", "-"],
                  f"finding speech in {path.name}")
    return parse_silences(out, _duration(path))


@dataclass
class Take:
    id: str
    file: str
    speaker: str = ""
    words: str = ""
    loudness: Loudness = None
    speech: Speech = None
    gap_after: float = None


def place(takes: list, start: float = 0.0, target: float = TARGET_LUFS) -> list:
    """Lay the takes out in order, measuring the gap between speech rather than between files.

    `at` is when the file starts, but the pause a viewer hears runs from the last word of one
    take to the first word of the next, so leading and trailing silence is subtracted out.
    """
    if not takes:
        return []
    entries, cursor, previous = [], float(start), None
    for take in takes:
        if take.loudness is None or take.speech is None:
            raise AudioPostError(f"take {take.id} has not been measured yet")
        if previous is not None:
            gap = previous.gap_after
            if gap is None:
                gap = GAP_NEW_SPEAKER if take.speaker != previous.speaker else GAP_SAME_SPEAKER
            cursor += gap
        at = round(cursor - take.speech.onset, 3)
        entry = {"id": take.id, "file": take.file, "at": at,
                 "gain_db": gain_for(take.loudness, target=target),
                 "speech": [round(cursor, 3), round(cursor + take.speech.length, 3)]}
        if take.words:
            entry["words"] = take.words
        if take.speaker:
            entry["speaker"] = take.speaker
        entries.append(entry)
        cursor = round(cursor + take.speech.length, 3)
        previous = take
    return _shift_onto_the_timeline(entries)


def _shift_onto_the_timeline(entries: list) -> list:
    """No take may start before zero.

    A take with leading silence would have to begin before the comp does for its first word to
    land on `start`, and After Effects would simply cut off the head. Shifting the whole
    sequence keeps every gap exactly as placed and costs only a later first word.
    """
    earliest = min((e["at"] for e in entries), default=0.0)
    if earliest >= 0:
        return entries
    for entry in entries:
        entry["at"] = round(entry["at"] - earliest, 3)
        entry["speech"] = [round(t - earliest, 3) for t in entry["speech"]]
    return entries


def voice_spans(entries: list) -> list:
    """The [onset, offset] pairs duck_keys needs, taken from placed voices."""
    return [tuple(e["speech"]) for e in entries if "speech" in e]


def music_plan(duration: float, music_length: float, *, tail: float = 1.2) -> list:
    """Cut one music file to the length of the video.

    Shorter than the video: loop it, but land the final repeat on the end rather than cutting
    mid-bar at an arbitrary point. Longer: take the opening and let it run under the tail.
    """
    if duration <= 0:
        raise AudioPostError("the video needs a duration before the music can be cut")
    if music_length <= 0:
        raise AudioPostError("that music file measures as zero length")
    if music_length >= duration:
        return [[0, round(duration, 3)]]
    segments, filled = [], 0.0
    while filled < duration:
        take = min(music_length, duration - filled)
        segments.append([0, round(take, 3)])
        filled += take
    if len(segments) > 1 and segments[-1][1] < tail:
        segments.pop()               # a sliver of a loop reads as a glitch; let the previous one ring out
    return segments


def load_takes(spec: dict, root=".") -> list:
    """Read the takes half of an audio spec, resolving files against the project root.

    Every problem is collected and reported together, as plan.py and fonts.py do: fixing one
    mistake per run is a poor trade when the spec is hand-written.
    """
    root = Path(root)
    raw = spec.get("takes")
    if not isinstance(raw, list) or not raw:
        raise AudioPostError("the audio spec needs a non-empty 'takes' list")
    takes, seen, errors = [], set(), []
    for i, entry in enumerate(raw):
        where = f"takes[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: each take must be an object")
            continue
        tid, file = entry.get("id"), entry.get("file")
        if not tid or not isinstance(tid, str):
            errors.append(f"{where}: 'id' is required")
        elif tid in seen:
            errors.append(f"{where}: duplicate id '{tid}' — captions reference takes by id")
        if isinstance(tid, str):
            seen.add(tid)
        if not file or not isinstance(file, str):
            errors.append(f"{where}: 'file' is required")
        else:
            path = Path(file) if Path(file).is_absolute() else root / file
            if not path.exists():
                errors.append(f"{where}: no such audio file: {path}")
        gap = entry.get("gap_after")
        if gap is not None and (not isinstance(gap, (int, float)) or gap < 0):
            errors.append(f"{where}: 'gap_after' must be a number of seconds")
        takes.append(Take(id=tid if isinstance(tid, str) else "", file=file if isinstance(file, str) else "",
                          speaker=entry.get("speaker", "") or "", words=entry.get("words", "") or "",
                          gap_after=gap if isinstance(gap, (int, float)) else None))
    if errors:
        raise AudioPostError("the audio spec has problems:\n  " + "\n  ".join(errors))
    return takes


def build(spec: dict, root=".", *, start=0.0, target=TARGET_LUFS) -> dict:
    """Measure every take, place them, and cut the music to the result."""
    root = Path(root)
    takes = load_takes(spec, root)
    for take in takes:
        path = Path(take.file) if Path(take.file).is_absolute() else root / take.file
        take.loudness = measure(path)
        take.speech = speech_bounds(path)
    voices = place(takes, start=start, target=target)
    out = {"voices": voices}
    last = max((v["speech"][1] for v in voices), default=0.0)
    duration = float(spec.get("duration") or 0.0) or round(last + 2.0, 3)
    music = spec.get("music")
    if isinstance(music, dict) and music.get("file"):
        path = Path(music["file"]) if Path(music["file"]).is_absolute() else root / music["file"]
        measured = measure(path)
        out["music"] = {"file": music["file"],
                        "edit": music_plan(duration, measured.duration),
                        "gain_db": gain_for(measured, target=target + float(music.get("under", -6))),
                        "duck": music.get("duck", {"under_voice": -12, "breath": -9, "swell": -4,
                                                   "tail": -2, "lead": 0.25})}
    out["duration"] = duration
    out["voice_spans"] = [list(s) for s in voice_spans(voices)]
    return out


def merge_into(plan: dict, audio: dict) -> dict:
    """Splice the audio sections into an existing edit plan, leaving everything else alone.

    Shots, graphics and format are the story's, not ours: re-running audio-post must never
    silently rewrite a timeline the user has already approved.
    """
    merged = dict(plan)
    merged["voices"] = audio["voices"]
    if "music" in audio:
        merged["music"] = audio["music"]
    return merged
