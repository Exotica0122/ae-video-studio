"""Check a render the way an editor would, but with numbers.

Everything here measures the file that was actually produced. A QA pass that reasons about
the edit plan instead of the export cannot catch the failures worth catching: a comp that
rendered black, music that swallows the first word, an SFX nobody can hear.
"""
import array
import contextlib
import json
import math
import re
import tempfile
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .audiopost import AudioPostError, parse_loudness
from . import taste as tastelib
from .media import MediaError, probe

TARGET_LUFS = -16.0
PEAK_CEILING = -1.5
LOUDNESS_TOLERANCE = 1.5     # a section this far off target is worth a note
MUSIC_HEADROOM_DB = 6.0      # music should sit at least this far under the voice that follows
PRE_VOICE_WINDOW = 0.30      # docs/design.md §8: music must be down before the voice starts
WCAG_AA = 4.5
TASTE_PALETTE_MAX = 0.18     # mean swatch distance (0-1) past which the render has left the refs' colours
TASTE_SLACK = {"luma": 0.08, "contrast": 0.08, "warmth": 0.05, "saturation": 0.08}


class QAError(RuntimeError):
    pass


@dataclass
class Finding:
    check: str
    status: str              # "ok" | "warn" | "fail" | "skip"
    detail: str

    @property
    def bad(self) -> bool:
        return self.status in ("warn", "fail")


@dataclass
class QAReport:
    export: str
    findings: list = field(default_factory=list)

    @property
    def failures(self) -> list:
        return [f for f in self.findings if f.status == "fail"]

    @property
    def warnings(self) -> list:
        return [f for f in self.findings if f.status == "warn"]


def _ffmpeg(args: list, what: str) -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise QAError("ffmpeg not found — install it with `brew install ffmpeg`")
    result = subprocess.run([binary] + [str(a) for a in args], capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise QAError(f"{what} failed: " + " / ".join(tail))
    return result.stderr or ""


# ---------------------------------------------------------------- decode

DECODE_NOISE = re.compile(r"deprecated|Last message repeated|^\s*$", re.IGNORECASE)


def decode_check(path) -> Finding:
    """Decode every frame and sample. A render can finish and still be broken."""
    path = Path(path)
    if not path.exists():
        raise QAError(f"no such export: {path}")
    out = _ffmpeg(["-v", "error", "-i", path, "-f", "null", "-"], f"decoding {path.name}")
    lines = [l for l in out.strip().splitlines() if l.strip() and not DECODE_NOISE.search(l)]
    if lines:
        return Finding("decode", "fail", f"{len(lines)} decode error(s): " + lines[0][:160])
    return Finding("decode", "ok", "decodes cleanly end to end")


def stream_check(path) -> list:
    """The export must actually carry both a video and an audio stream."""
    try:
        info = probe(path)
    except MediaError as e:
        raise QAError(str(e)) from e
    findings = [Finding("video-stream", "ok", f"{info.width}×{info.height} @ {info.fps:.3f} fps, {info.duration:.2f}s")]
    findings.append(Finding("audio-stream", "ok", "present") if info.has_audio
                    else Finding("audio-stream", "fail", "the export has no audio stream at all"))
    return findings


# ---------------------------------------------------------------- loudness

def measure_segment(path, start: float = None, end: float = None):
    """Integrated loudness and true peak over the whole file or one span of it."""
    args = ["-v", "info"]
    if start is not None:
        args += ["-ss", f"{max(0.0, start):.3f}"]
    args += ["-i", str(path)]
    if end is not None and start is not None:
        args += ["-t", f"{max(0.01, end - start):.3f}"]
    args += ["-af", "loudnorm=print_format=json", "-f", "null", "-"]
    try:
        return parse_loudness(_ffmpeg(args, f"measuring {Path(path).name}"))
    except AudioPostError as e:
        raise QAError(str(e)) from e


def mix_loudness(path, target: float = TARGET_LUFS, ceiling: float = PEAK_CEILING) -> list:
    loud = measure_segment(path)
    findings = []
    off = loud.lufs - target
    if abs(off) > LOUDNESS_TOLERANCE:
        findings.append(Finding("mix-loudness", "warn",
                                f"{loud.lufs:.1f} LUFS is {off:+.1f} dB from the {target:.0f} target"))
    else:
        findings.append(Finding("mix-loudness", "ok", f"{loud.lufs:.1f} LUFS ({off:+.1f} from target)"))
    if loud.peak_db > ceiling:
        findings.append(Finding("true-peak", "fail",
                                f"{loud.peak_db:.1f} dBFS is above the {ceiling} ceiling — this will clip"))
    else:
        findings.append(Finding("true-peak", "ok", f"{loud.peak_db:.1f} dBFS"))
    return findings


def section_loudness(path, sections: list, target: float = TARGET_LUFS) -> list:
    """Per-section loudness: an average on target can still hide one inaudible passage."""
    findings = []
    for section in sections:
        name = section.get("id") or section.get("name") or "section"
        start, end = float(section["start"]), float(section["end"])
        if end - start < 0.4:
            continue                      # too short for an integrated measurement to mean anything
        loud = measure_segment(path, start, end)
        if not loud.measured:
            findings.append(Finding(f"section:{name}", "fail",
                                    f"{start:.2f}–{end:.2f}s measures as silence"))
            continue
        off = loud.lufs - target
        status = "warn" if abs(off) > LOUDNESS_TOLERANCE * 2 else "ok"
        findings.append(Finding(f"section:{name}", status,
                                f"{start:.2f}–{end:.2f}s at {loud.lufs:.1f} LUFS ({off:+.1f})"))
    return findings


def rms_db(path, start: float, end: float) -> float:
    """Mean RMS over a window, via astats.

    The window is cut with atrim rather than by seeking: `-ss` before the input is a fast seek
    that lands on the nearest packet boundary, which in a compressed export can be tens of
    milliseconds away from the moment being measured — enough to read the wrong side of a duck.
    """
    start, end = max(0.0, float(start)), max(0.01, float(end))
    out = _ffmpeg(["-v", "info", "-i", str(path),
                   "-af", f"atrim=start={start:.3f}:end={end:.3f},astats=metadata=1:reset=0",
                   "-f", "null", "-"], "measuring RMS")
    found = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", out)
    if not found:
        raise QAError("astats reported no RMS level; is there an audio stream?")
    value = found[-1]
    return -120.0 if value == "-inf" else float(value)


def reference_bed(path, spans: list, duration: float, window: float = PRE_VOICE_WINDOW,
                  guard: float = 0.8, step: float = 0.5):
    """The music bed at full level: the loudest voice-free window in the video.

    Measuring "before the voice" against "during the voice" would prove only that the voice is
    louder than the bed, which is true of every mix including a badly ducked one. The bed has
    to be compared against itself.
    """
    blocked = [(float(a) - guard, float(b) + guard) for a, b in spans]
    best, t = None, 0.0
    while t + window <= duration:
        if not any(start < t + window and t < end for start, end in blocked):
            level = rms_db(path, t, t + window)
            best = level if best is None else max(best, level)
        t = round(t + step, 3)
    return best


@contextlib.contextmanager
def decoded_audio(path, rate: int = 16000):
    """Decode the soundtrack once to a small mono wav.

    Every window is cut with atrim, which decodes from the start of the file each time. That is
    right but quadratic: measuring a 60s 4K master window by window meant decoding ~900MB over
    a hundred times. Measuring the same windows on a 2MB wav is the same arithmetic in
    milliseconds.
    """
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        _ffmpeg(["-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate),
                 "-c:a", "pcm_s16le", str(out)], f"decoding the audio of {path.name}")
        yield out


def music_before_voice(path, spans: list, duration: float, window: float = PRE_VOICE_WINDOW,
                       min_drop: float = MUSIC_HEADROOM_DB) -> list:
    """Music must already be down before a voice begins, not duck as it begins.

    docs/design.md §8: fully down 0.25s before the onset. If the bed in the moments before a
    voice still sits at its full level, the first word arrives underneath it.
    """
    spans = [(float(a), float(b)) for a, b in spans]
    if not spans:
        return []
    with decoded_audio(path) as audio:
        return _music_before_voice(audio, spans, duration, window, min_drop)


def _music_before_voice(path, spans, duration, window, min_drop) -> list:
    full = reference_bed(path, spans, duration, window=window)
    if full is None:
        return [Finding("music-before-voice", "ok", "voices run throughout; no bed-only window to compare")]
    findings = []
    for i, (onset, _) in enumerate(sorted(spans), start=1):
        if onset < window + 0.05:
            continue                      # nothing before the first voice to measure
        pre = rms_db(path, onset - window, onset)
        drop = full - pre
        if drop < min_drop:
            findings.append(Finding(f"music-before-voice:{i}", "warn",
                                    f"voice at {onset:.2f}s: bed is {pre:.1f} dB in the {window:.2f}s before it "
                                    f"vs {full:.1f} dB at full — only {drop:.1f} dB down, so the first word "
                                    f"lands under the music"))
        else:
            findings.append(Finding(f"music-before-voice:{i}", "ok",
                                    f"voice at {onset:.2f}s: bed already {drop:.1f} dB down before it starts"))
    return findings


def _clear_window(at: float, length: float, spans: list, search: float = 3.0, step: float = 0.1):
    """The nearest window of `length` ending by `at` that no voice runs through."""
    blocked = [(a - 0.1, b + 0.1) for a, b in spans]
    end = at
    while end - length >= max(0.0, at - search):
        start = end - length
        if not any(s < end and start < e for s, e in blocked):
            return start, end
        end = round(end - step, 3)
    return None


def sfx_audible(path, events: list, spans: list = None, floor: float = 3.0) -> list:
    """An SFX nobody can hear is a note in the edit plan, not a sound in the video.

    The baseline must be a stretch with no voice in it. On a real master the end-card sounds
    landed 30ms after the last word, so measuring "just before" measured the voice tail and
    reported a negative lift — the sounds looked inaudible when the comparison was simply wrong.
    """
    with decoded_audio(path) as audio:
        return _sfx_audible(audio, events, list(spans or []), floor)


def _sfx_audible(path, events, spans, floor) -> list:
    findings = []
    for event in events:
        at = float(event["at"])
        name = event.get("role") or Path(event.get("file", "sfx")).stem
        if at < 0.4:
            continue
        # other SFX block the baseline too: on an end card three sounds land inside two
        # seconds, and measuring one against another says nothing about either
        others = [(float(e["at"]), float(e["at"]) + 0.4) for e in events if e is not event]
        window = _clear_window(at, 0.3, spans + others)
        if window is None:
            findings.append(Finding(f"sfx:{name}", "ok",
                                    f"at {at:.2f}s — not measurable from the mix: speech or another "
                                    f"sound runs up to it, so there is no clear moment to compare "
                                    f"against. Listen to this one."))
            continue
        before = rms_db(path, *window)
        during = rms_db(path, at, at + 0.35)
        lift = during - before
        status = "ok" if lift >= floor else "warn"
        gap = at - window[1]
        where = "" if gap < 0.05 else f" (baseline {gap:.2f}s earlier, clear of speech)"
        findings.append(Finding(f"sfx:{name}", status,
                                f"at {at:.2f}s lifts the mix {lift:+.1f} dB{where}"
                                + ("" if status == "ok" else " — probably inaudible in the mix")))
    return findings


# ---------------------------------------------------------------- legibility

def relative_luminance(rgb) -> float:
    """WCAG relative luminance from linear-ish 0–1 sRGB components."""
    def channel(c):
        c = max(0.0, min(1.0, float(c)))
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in list(rgb)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return round((lighter + 0.05) / (darker + 0.05), 2)


# the pairs a design must get right: text colour against the surface it is set on
LEGIBILITY_PAIRS = (("ink", "paper"), ("accent", "paper"), ("paper", "shade"))


def legibility(design, minimum: float = WCAG_AA) -> list:
    """Check the design's own declared colour pairs.

    Designs here are generated from the footage, so a palette can come out pretty and
    unreadable. Checking the declared pairs is exact — no guessing where text landed.
    """
    findings = []
    for text, ground in LEGIBILITY_PAIRS:
        if text not in design.palette or ground not in design.palette:
            continue
        ratio = contrast_ratio(design.color(text), design.color(ground))
        status = "ok" if ratio >= minimum else "warn"
        findings.append(Finding(f"contrast:{text}-on-{ground}", status,
                                f"{ratio}:1" + ("" if status == "ok" else f" is under the {minimum}:1 minimum")))
    return findings


# ---------------------------------------------------------------- render diff

DIFF_FPS = 10
DIFF_WIDTH = 320
PIXEL_DELTA = 24             # a luma change this large is content, not encoder noise
CHANGED_PIXELS_PCT = 0.1     # % of the frame that must change for the frame to count
AUDIO_WINDOW = 0.5
AUDIO_DELTA_DB = 1.0
AUDIO_FLOOR_DB = -70.0       # below this both sides are silence; dither differences mean nothing


@dataclass
class Change:
    start: float
    end: float
    peak: float

    @property
    def mid(self) -> float:
        return round((self.start + self.end) / 2, 2)


@dataclass
class RenderDiff:
    previous: str
    current: str
    prev_duration: float
    cur_duration: float
    video: list = field(default_factory=list)
    audio: list = field(default_factory=list)
    audio_note: str = ""

    @property
    def common(self) -> float:
        return min(self.prev_duration, self.cur_duration)

    @property
    def same_duration(self) -> bool:
        return abs(self.prev_duration - self.cur_duration) < 1.0 / DIFF_FPS


def clock(t: float) -> str:
    minutes, seconds = divmod(max(0.0, float(t)), 60)
    return f"{int(minutes)}:{seconds:05.2f}"


def changed_ranges(samples: list, threshold: float, step: float, gap: int = 1) -> list:
    """Merge (time, score) samples over `threshold` into Changes, bridging `gap` quiet samples."""
    ranges = []
    for t, score in sorted(samples):
        if score <= threshold:
            continue
        if ranges and t - ranges[-1].end <= gap * step + 1e-6:
            ranges[-1].end = round(t + step, 3)
            ranges[-1].peak = max(ranges[-1].peak, score)
        else:
            ranges.append(Change(round(t, 3), round(t + step, 3), score))
    return ranges


def frame_differences(previous, current, fps: int = DIFF_FPS, width: int = DIFF_WIDTH) -> list:
    """(time, % of pixels whose luma moved by more than PIXEL_DELTA) for each sampled frame."""
    info = probe(current)
    height = max(2, round(width * info.height / max(1, info.width) / 2) * 2)
    prep = f"fps={fps},scale={width}:{height},format=yuv420p,setpts=PTS-STARTPTS"
    graph = (f"[0:v]{prep}[a];[1:v]{prep}[b];"
             f"[a][b]blend=all_mode=difference:shortest=1,"
             f"lutyuv=y='if(gt(val,{PIXEL_DELTA}),255,0)',signalstats,metadata=mode=print")
    out = _ffmpeg(["-v", "info", "-i", previous, "-i", current, "-filter_complex", graph,
                   "-an", "-f", "null", "-"], "diffing frames")
    samples, t = [], None
    for line in out.splitlines():
        if (m := re.search(r"pts_time:(\S+)", line)):
            t = float(m.group(1))
        elif t is not None and (m := re.search(r"signalstats\.YAVG=(\S+)", line)):
            samples.append((round(t, 3), float(m.group(1)) / 255 * 100))
            t = None
    return samples


def window_levels(wav_path, window: float = AUDIO_WINDOW) -> list:
    """RMS level in dB of each consecutive window of a mono 16-bit wav."""
    with wave.open(str(wav_path), "rb") as w:
        rate = w.getframerate()
        data = array.array("h", w.readframes(w.getnframes()))
    size = max(1, int(rate * window))
    levels = []
    for i in range(0, len(data) - size + 1, size):
        chunk = data[i:i + size]
        rms = math.sqrt(sum(s * s for s in chunk) / size) / 32768
        levels.append(20 * math.log10(rms) if rms > 0 else -120.0)
    return levels


def audio_differences(previous, current, window: float = AUDIO_WINDOW) -> list:
    with decoded_audio(previous) as a, decoded_audio(current) as b:
        before, after = window_levels(a, window), window_levels(b, window)
    return [(round(i * window, 3), abs(max(x, AUDIO_FLOOR_DB) - max(y, AUDIO_FLOOR_DB)))
            for i, (x, y) in enumerate(zip(before, after))]


def render_diff(previous, current, fps: int = DIFF_FPS, width: int = DIFF_WIDTH,
                pixels_pct: float = CHANGED_PIXELS_PCT, audio_db: float = AUDIO_DELTA_DB) -> RenderDiff:
    """Where two renders differ, in picture and in sound, over the span they share."""
    for path in (previous, current):
        if not Path(path).exists():
            raise QAError(f"no such export: {path}")
    try:
        before, after = probe(previous), probe(current)
    except MediaError as e:
        raise QAError(str(e)) from e
    diff = RenderDiff(str(previous), str(current), before.duration, after.duration)
    diff.video = changed_ranges(frame_differences(previous, current, fps, width), pixels_pct, 1.0 / fps)
    if before.has_audio and after.has_audio:
        diff.audio = changed_ranges(audio_differences(previous, current), audio_db, AUDIO_WINDOW)
    elif before.has_audio != after.has_audio:
        diff.audio_note = "only one of the two renders has an audio stream"
    return diff


def diff_findings(diff: RenderDiff) -> list:
    findings = []
    if not diff.same_duration:
        findings.append(Finding("diff:duration", "warn",
                                f"previous {diff.prev_duration:.2f}s vs now {diff.cur_duration:.2f}s "
                                f"({diff.cur_duration - diff.prev_duration:+.2f}s); compared the first "
                                f"{diff.common:.2f}s"))
    spans = ", ".join(f"{clock(c.start)}–{clock(c.end)}" for c in diff.video) or "none"
    findings.append(Finding("diff:picture", "ok", f"{len(diff.video)} changed range(s): {spans}"))
    if diff.audio_note:
        findings.append(Finding("diff:sound", "warn", diff.audio_note))
    else:
        spans = ", ".join(f"{clock(c.start)}–{clock(c.end)}" for c in diff.audio) or "none"
        findings.append(Finding("diff:sound", "ok", f"{len(diff.audio)} changed range(s): {spans}"))
    return findings


def diff_section(diff: RenderDiff, still_pairs: dict = None) -> list:
    """Markdown lines for "Changes vs previous"; still_pairs maps a midpoint to (previous, current)."""
    lines = [f"- Previous: `{diff.previous}`"]
    if not diff.same_duration:
        lines.append(f"- Duration changed: {diff.prev_duration:.2f}s → {diff.cur_duration:.2f}s; "
                     f"only the first {diff.common:.2f}s were compared")
    if not diff.video and not diff.audio:
        lines.append("- No picture or sound changes in the compared span.")
    for kind, ranges, unit in (("Picture", diff.video, "% of pixels"), ("Sound", diff.audio, " dB")):
        for c in ranges:
            line = f"- {kind} {clock(c.start)}–{clock(c.end)} (peak {c.peak:.2f}{unit})"
            pair = (still_pairs or {}).get(c.mid)
            if pair:
                line += f" — stills at {clock(c.mid)}: `{pair[0]}` → `{pair[1]}`"
            lines.append(line)
    if diff.audio_note:
        lines.append(f"- Sound not compared: {diff.audio_note}")
    return lines


# ---------------------------------------------------------------- taste

def taste_check(stills: list, taste: dict) -> list:
    """How far the render's stills sit from the approved references' measured targets."""
    goal = (taste or {}).get("targets") or {}
    if not goal or not stills:
        return []
    measured = [tastelib.measure(s) for s in stills]
    swatches = [sw for m in measured for sw in m["palette"]]
    findings = []
    near = tastelib.palette_distance(swatches, goal["palette"])
    findings.append(Finding("taste:palette", "ok" if near <= TASTE_PALETTE_MAX else "warn",
                            f"distance {near:.3f} from the references' palette (warn above {TASTE_PALETTE_MAX})"))
    for key, slack in TASTE_SLACK.items():
        value = round(sum(m[key] for m in measured) / len(measured), 3)
        lo, hi = goal[key]["min"] - slack, goal[key]["max"] + slack
        off = round(lo - value if value < lo else value - hi if value > hi else 0.0, 3)
        findings.append(Finding(f"taste:{key}", "warn" if off else "ok",
                                f"{value} vs references {goal[key]['min']}–{goal[key]['max']}"
                                + (f", {off} outside" if off else "")))
    avoid = goal.get("avoid")
    if avoid:
        far = tastelib.palette_distance(swatches, avoid["palette"])
        findings.append(Finding("taste:avoid", "warn" if far < near else "ok",
                                f"palette distance {far:.3f} from the avoid refs, {near:.3f} from the wanted ones"))
    return findings


# ---------------------------------------------------------------- outputs

def share_copy(src, out, height: int = 1080, crf: int = 20) -> Path:
    """A copy small enough to send to someone."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-v", "error", "-y", "-i", str(src), "-vf", f"scale=-2:{height}",
             "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
            f"making a share copy of {Path(src).name}")
    return out


def stills(src, times: list, outdir, width: int = 1920, prefix: str = "still") -> list:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for t in times:
        out = outdir / f"{prefix}-{float(t):07.2f}.jpg".replace(" ", "0")
        _ffmpeg(["-v", "error", "-y", "-ss", f"{float(t):.3f}", "-i", str(src), "-frames:v", "1",
                 "-vf", f"scale={width}:-2", "-q:v", "3", str(out)], f"still at {t}s")
        made.append(out)
    return made


def next_version(qa_dir) -> int:
    qa_dir = Path(qa_dir)
    used = [int(m.group(1)) for p in qa_dir.glob("report-v*.md")
            for m in [re.match(r"report-v(\d+)\.md$", p.name)] if m]
    return max(used, default=0) + 1


MARK = {"ok": "ok", "warn": "warn", "fail": "FAIL", "skip": "skipped"}


def format_report(report: QAReport, version: int, extras: dict = None, today=None,
                  sections: dict = None) -> str:
    lines = [f"# QA report v{version:02d}", "",
             f"- Export: `{report.export}`",
             f"- Date: {(today or date.today()).isoformat()}",
             f"- Result: **{len(report.failures)} failed, {len(report.warnings)} warnings**", ""]
    for key, value in (extras or {}).items():
        lines.append(f"- {key}: {value}")
    if extras:
        lines.append("")
    if report.failures or report.warnings:
        lines += ["## Needs attention", ""]
        for f in report.failures + report.warnings:
            lines.append(f"- **[{MARK[f.status]}] {f.check}** — {f.detail}")
        lines.append("")
    for heading, body in (sections or {}).items():
        lines += [f"## {heading}", ""] + list(body) + [""]
    lines += ["## All checks", "", "| check | result | detail |", "|---|---|---|"]
    for f in report.findings:
        lines.append(f"| {f.check} | {MARK[f.status]} | {f.detail} |")
    lines.append("")
    return "\n".join(lines)


def write_report(qa_dir, report: QAReport, extras: dict = None, today=None,
                 sections: dict = None) -> Path:
    qa_dir = Path(qa_dir)
    qa_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(qa_dir)
    out = qa_dir / f"report-v{version:02d}.md"
    out.write_text(format_report(report, version, extras, today, sections), encoding="utf-8")
    return out
