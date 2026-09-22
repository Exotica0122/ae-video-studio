"""Check a render the way an editor would, but with numbers.

Everything here measures the file that was actually produced. A QA pass that reasons about
the edit plan instead of the export cannot catch the failures worth catching: a comp that
rendered black, music that swallows the first word, an SFX nobody can hear.
"""
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .audiopost import AudioPostError, parse_loudness
from .media import MediaError, probe

TARGET_LUFS = -16.0
PEAK_CEILING = -1.5
LOUDNESS_TOLERANCE = 1.5     # a section this far off target is worth a note
MUSIC_HEADROOM_DB = 6.0      # music should sit at least this far under the voice that follows
PRE_VOICE_WINDOW = 0.30      # docs/design.md §8: music must be down before the voice starts
WCAG_AA = 4.5


class QAError(RuntimeError):
    pass


@dataclass
class Finding:
    check: str
    status: str              # "ok" | "warn" | "fail"
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


def music_before_voice(path, spans: list, duration: float, window: float = PRE_VOICE_WINDOW,
                       min_drop: float = MUSIC_HEADROOM_DB) -> list:
    """Music must already be down before a voice begins, not duck as it begins.

    docs/design.md §8: fully down 0.25s before the onset. If the bed in the moments before a
    voice still sits at its full level, the first word arrives underneath it.
    """
    spans = [(float(a), float(b)) for a, b in spans]
    if not spans:
        return []
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


def sfx_audible(path, events: list, floor: float = 3.0) -> list:
    """An SFX nobody can hear is a note in the edit plan, not a sound in the video."""
    findings = []
    for event in events:
        at = float(event["at"])
        name = event.get("role") or Path(event.get("file", "sfx")).stem
        if at < 0.4:
            continue
        before = rms_db(path, max(0.0, at - 0.35), at - 0.05)
        during = rms_db(path, at, at + 0.35)
        lift = during - before
        status = "ok" if lift >= floor else "warn"
        findings.append(Finding(f"sfx:{name}", status,
                                f"at {at:.2f}s lifts the mix {lift:+.1f} dB"
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


def stills(src, times: list, outdir, width: int = 1920) -> list:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for t in times:
        out = outdir / f"still-{float(t):07.2f}.jpg".replace(" ", "0")
        _ffmpeg(["-v", "error", "-y", "-ss", f"{float(t):.3f}", "-i", str(src), "-frames:v", "1",
                 "-vf", f"scale={width}:-2", "-q:v", "3", str(out)], f"still at {t}s")
        made.append(out)
    return made


def next_version(qa_dir) -> int:
    qa_dir = Path(qa_dir)
    used = [int(m.group(1)) for p in qa_dir.glob("report-v*.md")
            for m in [re.match(r"report-v(\d+)\.md$", p.name)] if m]
    return max(used, default=0) + 1


MARK = {"ok": "ok", "warn": "warn", "fail": "FAIL"}


def format_report(report: QAReport, version: int, extras: dict = None, today=None) -> str:
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
    lines += ["## All checks", "", "| check | result | detail |", "|---|---|---|"]
    for f in report.findings:
        lines.append(f"| {f.check} | {MARK[f.status]} | {f.detail} |")
    lines.append("")
    return "\n".join(lines)


def write_report(qa_dir, report: QAReport, extras: dict = None, today=None) -> Path:
    qa_dir = Path(qa_dir)
    qa_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(qa_dir)
    out = qa_dir / f"report-v{version:02d}.md"
    out.write_text(format_report(report, version, extras, today), encoding="utf-8")
    return out
