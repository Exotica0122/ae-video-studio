"""Log a folder of footage: probe every clip, sample frames, measure brightness and colour."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .media import MediaError, average_color, contact_sheet, extract_frame, mean_luma, probe

VIDEO_SUFFIXES = (".mp4", ".mov", ".mxf", ".m4v", ".avi")
AUDIO_SUFFIXES = (".wav", ".m4a", ".mp3", ".aif", ".aiff")


def _candidates(sources) -> list:
    files = []
    for source in sources:
        source = Path(source).expanduser()
        if source.is_dir():
            files += sorted(p for p in source.iterdir() if p.is_file())
        else:
            files.append(source)
    keep, seen = [], set()
    for f in files:
        if f.name.startswith("._") or f.suffix.lower() not in VIDEO_SUFFIXES + AUDIO_SUFFIXES:
            continue
        if f.resolve() not in seen:
            seen.add(f.resolve())
            keep.append(f)
    return keep


def _frame_times(duration: float, every: float, max_frames: int) -> list:
    times, t = [], 0.5
    while len(times) < max_frames and t < max(duration - 0.2, 0.5):
        times.append(round(t, 3))
        t += every
    return times or [0.0]


def log_footage(sources, out_dir, every: float = 4.0, max_frames: int = 6, sheet_cols: int = 4,
                frame_width: int = 640) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    (out_dir / "sheets").mkdir(parents=True, exist_ok=True)
    log = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "clips": [], "audio": [], "errors": []}

    for path in _candidates(sources):
        try:
            info = probe(path)
        except MediaError as e:
            log["errors"].append(f"{path.name}: {e}")
            continue
        if not info.has_video:
            log["audio"].append({"path": str(path), "name": path.name, "duration": info.duration})
            continue
        frames, lumas = [], []
        for at in _frame_times(info.duration, every, max_frames):
            rel = f"frames/{path.stem}_{at}.jpg"
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
            sheet = f"sheets/{path.stem}.jpg"
            try:
                contact_sheet([out_dir / f["file"] for f in frames], out_dir / sheet, cols=sheet_cols,
                              tile_width=max(160, frame_width // 2))
                entry["sheet"] = sheet
            except MediaError as e:
                log["errors"].append(f"{path.name} sheet: {e}")
        log["clips"].append(entry)

    (out_dir / "footage.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return log
