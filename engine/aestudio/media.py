"""ffprobe/ffmpeg helpers: probing, frames, contact sheets and pixel statistics.

Image work goes through ffmpeg (no Pillow): a scaled rawvideo dump gives averaged pixels.
"""
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    path: Path
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    has_video: bool


def _binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} not found — install it with `brew install ffmpeg`")
    return found


def run(args: list, what: str) -> str:
    result = subprocess.run([_binary(args[0])] + [str(a) for a in args[1:]], capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise MediaError(f"{what} failed: " + " / ".join(tail))
    return result.stdout


def _fraction(value, default=0.0) -> float:
    try:
        if isinstance(value, str) and "/" in value:
            num, den = value.split("/", 1)
            return float(num) / float(den) if float(den) else default
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return default


def probe(path) -> MediaInfo:
    path = Path(path)
    if not path.exists():
        raise MediaError(f"file not found: {path}")
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path], f"probing {path.name}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise MediaError(f"unreadable ffprobe output for {path.name}: {e}") from e
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = _fraction(data.get("format", {}).get("duration"), 0.0)
    if video and not duration:
        duration = _fraction(video.get("duration"), 0.0)
    return MediaInfo(path=path,
                     width=int(video.get("width", 0)) if video else 0,
                     height=int(video.get("height", 0)) if video else 0,
                     fps=_fraction(video.get("r_frame_rate"), 0.0) if video else 0.0,
                     duration=round(duration, 3),
                     has_audio=audio is not None,
                     has_video=video is not None)


def extract_frame(src, at: float, out, width: int = 1280) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-ss", max(0.0, float(at)), "-i", src,
         "-frames:v", 1, "-vf", f"scale={int(width)}:-2", "-q:v", 3, out], f"extracting a frame from {Path(src).name}")
    if not out.exists():
        raise MediaError(f"no frame written at {at}s of {Path(src).name} (is the clip shorter than that?)")
    return out


def contact_sheet(frames: list, out, cols: int = 4, tile_width: int = 480) -> Path:
    frames = [Path(f) for f in frames]
    if not frames:
        raise MediaError("contact_sheet needs at least one frame")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = max(1, min(cols, len(frames)))
    rows = (len(frames) + cols - 1) // cols
    args = ["ffmpeg", "-v", "error", "-y"]
    for f in frames:
        args += ["-i", f]
    scaled = "".join(f"[{i}:v]scale={int(tile_width)}:-2,setsar=1[t{i}];" for i in range(len(frames)))
    joined = "".join(f"[t{i}]" for i in range(len(frames)))
    args += ["-filter_complex", f"{scaled}{joined}xstack=inputs={len(frames)}:layout={_layout(len(frames), cols)}[v]"
             if len(frames) > 1 else f"{scaled}[t0]copy[v]",
             "-map", "[v]", "-frames:v", 1, "-q:v", 3, out]
    run(args, "building a contact sheet")
    if rows and not out.exists():
        raise MediaError(f"no contact sheet written to {out}")
    return out


def _layout(count: int, cols: int) -> str:
    cells = []
    for i in range(count):
        col, row = i % cols, i // cols
        x = "0" if col == 0 else "+".join(f"w{c}" for c in range(col))
        y = "0" if row == 0 else "+".join(f"h{r * cols}" for r in range(row))
        cells.append(f"{x}_{y}")
    return "|".join(cells)


def _raw(src, at: float, size: str, pix_fmt: str, what: str) -> bytes:
    args = [_binary("ffmpeg"), "-v", "error", "-ss", str(max(0.0, float(at))), "-i", str(src),
            "-frames:v", "1", "-vf", f"scale={size}", "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"]
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        tail = (result.stderr.decode("utf-8", "replace") or "").strip().splitlines()[-3:]
        raise MediaError(f"{what} failed: " + " / ".join(tail))
    return result.stdout


def mean_luma(src, at: float) -> float:
    data = _raw(src, at, "1:1", "gray", f"reading brightness of {Path(src).name}")
    return round(data[0] / 255, 4)


def average_color(src, at: float, grid: int = 1) -> list:
    grid = max(1, int(grid))
    data = _raw(src, at, f"{grid}:{grid}", "rgb24", f"reading colours of {Path(src).name}")
    if len(data) < grid * grid * 3:
        raise MediaError(f"short colour dump for {Path(src).name}")
    return [tuple(data[i * 3:i * 3 + 3]) for i in range(grid * grid)]
