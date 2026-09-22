"""Log a folder of footage: probe every clip, sample frames, measure brightness and colour."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .media import MediaError, average_color, contact_sheet, extract_frame, mean_luma, probe

VIDEO_SUFFIXES = (".mp4", ".mov", ".mxf", ".m4v", ".avi")
AUDIO_SUFFIXES = (".wav", ".m4a", ".mp3", ".aif", ".aiff")
# RAW and HEIC are left out: ffmpeg on this machine cannot reliably decode them.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")


def _candidates(sources) -> list:
    files = []
    for source in sources:
        source = Path(source).expanduser().resolve()
        if source.is_dir():
            files += sorted(p for p in source.iterdir() if p.is_file())
        else:
            files.append(source)
    keep, seen = [], set()
    for f in files:
        if f.name.startswith("._") or f.suffix.lower() not in VIDEO_SUFFIXES + AUDIO_SUFFIXES + IMAGE_SUFFIXES:
            continue
        if f.resolve() not in seen:
            seen.add(f.resolve())
            keep.append(f)
    return keep


def _tag(path: Path) -> str:
    """Keep same-named clips from different folders (day1/interview.mp4, day2/interview.mp4) apart."""
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:6]


def _frame_times(duration: float, every: float, max_frames: int) -> list:
    """Sample by proportion of the clip, not at a fixed interval from the head.

    A fixed interval means a short clip gets one frame and a long one gets six, so a contact
    sheet of a 7s clip showed a single frame next to four-frame sheets and told you almost
    nothing. `every` now sets how many frames a clip earns; where they fall is spread evenly
    across it, inset from the very first and last frames where cuts and fades live.
    """
    duration = max(0.0, float(duration))
    if duration <= 0:
        return [0.0]
    if duration < 1.0:
        return [round(duration / 2, 3)]
    wanted = min(max(2, round(duration / max(every, 0.1)) + 1), max(max_frames, 1))
    if wanted == 1:
        return [round(duration / 2, 3)]
    start, span = duration * 0.05, duration * 0.90
    step = span / (wanted - 1)
    return [round(start + i * step, 3) for i in range(wanted)]


def log_footage(sources, out_dir, every: float = 4.0, max_frames: int = 6, sheet_cols: int = 4,
                frame_width: int = 640) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    (out_dir / "sheets").mkdir(parents=True, exist_ok=True)
    log = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "clips": [], "audio": [],
           "images": [], "errors": []}

    for path in _candidates(sources):
        if path.suffix.lower() in IMAGE_SUFFIXES:
            tag = _tag(path)
            rel = f"frames/{path.stem}-{tag}.jpg"
            try:
                info = probe(path)
                extract_frame(path, 0, out_dir / rel, width=frame_width)
                luma = mean_luma(path, 0)
                colors = [list(c) for c in average_color(path, 0, grid=2)]
            except MediaError as e:
                log["errors"].append(f"{path.name}: {e}")
                continue
            log["images"].append({"path": str(path), "name": path.name, "width": info.width, "height": info.height,
                                  "luma": luma, "colors": colors, "file": rel})
            continue
        try:
            info = probe(path)
        except MediaError as e:
            log["errors"].append(f"{path.name}: {e}")
            continue
        if not info.has_video:
            log["audio"].append({"path": str(path), "name": path.name, "duration": info.duration})
            continue
        frames, lumas = [], []
        tag = _tag(path)
        for at in _frame_times(info.duration, every, max_frames):
            rel = f"frames/{path.stem}-{tag}_{at}.jpg"
            try:
                extract_frame(path, at, out_dir / rel, width=frame_width)
                luma = mean_luma(path, at)
                colors = [list(c) for c in average_color(path, at, grid=2)]
            except MediaError as e:
                log["errors"].append(f"{path.name} at {at}s: {e}")
                continue
            lumas.append(luma)
            frames.append({"at": at, "file": rel, "luma": luma, "colors": colors})
        entry = {"path": str(path), "name": path.name, "width": info.width, "height": info.height,
                 "fps": info.fps, "duration": info.duration, "has_audio": info.has_audio,
                 "luma": round(sum(lumas) / len(lumas), 4) if lumas else None, "frames": frames}
        if frames:
            sheet = f"sheets/{path.stem}-{tag}.jpg"
            try:
                contact_sheet([out_dir / f["file"] for f in frames], out_dir / sheet, cols=sheet_cols,
                              tile_width=max(160, frame_width // 2))
                entry["sheet"] = sheet
            except MediaError as e:
                log["errors"].append(f"{path.name} sheet: {e}")
        log["clips"].append(entry)

    (out_dir / "footage.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return log
