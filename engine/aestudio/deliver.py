"""Delivery: H.264 copies of the ProRes master with normalised audio, the old set archived, the new set verified."""
import re
import shutil
from pathlib import Path

from .audiopost import _ffmpeg, measure
from .media import probe
from .render import render

TARGET_LUFS = -16.0
TRUE_PEAK = -2.0
LRA = 11
CRF = 18
PRESET = "slow"
LUFS_TOLERANCE = 1.0
DURATION_TOLERANCE = 0.1


class DeliverError(RuntimeError):
    pass


def parse_sizes(text: str) -> list:
    """'4k,1080' -> [2160, 1080]; 'master' -> None, meaning the master's own size."""
    sizes = []
    for token in (t.strip().lower() for t in str(text).split(",")):
        if not token:
            continue
        if token == "master":
            sizes.append(None)
        elif token == "4k":
            sizes.append(2160)
        elif re.fullmatch(r"\d+p?", token):
            sizes.append(int(token.rstrip("p")))
        else:
            raise DeliverError(f"unknown size '{token}': use 4k, master or a height such as 1080")
    if not sizes:
        raise DeliverError("--sizes needs at least one size")
    return list(dict.fromkeys(sizes))


def label(short_side: int) -> str:
    return "4k" if short_side == 2160 else f"{short_side}p"


def audio_filter(lufs: float = TARGET_LUFS, tp: float = TRUE_PEAK) -> str:
    limit = round(10 ** (tp / 20), 3)
    return f"loudnorm=I={lufs:g}:TP={tp:g}:LRA={LRA},alimiter=limit={limit:g}:level=false"


def encode_args(master, out, width: int, height: int, short_side, has_audio: bool,
                lufs: float = TARGET_LUFS, tp: float = TRUE_PEAK) -> list:
    """ffmpeg arguments for one H.264 delivery copy; short_side None keeps the master's size."""
    args = ["-v", "error", "-y", "-i", str(master)]
    if short_side is not None and short_side != min(width, height):
        # scale the short side so a vertical master gets the same treatment as a landscape one
        args += ["-vf", f"scale=-2:{short_side}" if width >= height else f"scale={short_side}:-2"]
    args += ["-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF), "-pix_fmt", "yuv420p"]
    if has_audio:
        args += ["-af", audio_filter(lufs, tp), "-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
    else:
        args += ["-an"]
    return args + ["-movflags", "+faststart", str(out)]


def archive_previous(final_dir, keep=()) -> Path | None:
    """Move the files already in final_dir into the next unused previous-vNN/ beside them."""
    final_dir = Path(final_dir)
    keep = {Path(k).resolve() for k in keep}
    old = [p for p in sorted(final_dir.glob("*"))
           if p.is_file() and not p.name.startswith(".") and p.resolve() not in keep]
    if not old:
        return None
    used = [int(m.group(1)) for p in final_dir.glob("previous-v*") for m in [re.fullmatch(r"previous-v(\d+)", p.name)] if m]
    dest = final_dir / f"previous-v{max(used, default=0) + 1:02d}"
    dest.mkdir()
    for p in old:
        shutil.move(str(p), str(dest / p.name))
    return dest


def verify(path, duration: float, size: tuple, lufs: float, tp: float, has_audio: bool) -> dict:
    info = probe(path)
    problems = []
    if abs(info.duration - duration) > DURATION_TOLERANCE:
        problems.append(f"duration {info.duration:.3f}s vs master {duration:.3f}s")
    if (info.width, info.height) != tuple(size):
        problems.append(f"size {info.width}x{info.height}, expected {size[0]}x{size[1]}")
    result = {"file": str(path), "width": info.width, "height": info.height, "duration": info.duration,
              "bytes": Path(path).stat().st_size}
    if has_audio:
        loud = measure(path)
        result.update(lufs=loud.lufs, true_peak=loud.peak_db)
        if abs(loud.lufs - lufs) > LUFS_TOLERANCE:
            problems.append(f"integrated loudness {loud.lufs:.1f} LUFS, target {lufs:g}")
        if loud.peak_db > tp + 0.5:  # AAC can overshoot the limiter slightly; more than this is audible
            problems.append(f"true peak {loud.peak_db:.1f} dBTP, ceiling {tp:g}")
    result["problems"] = problems
    result["ok"] = not problems
    return result


def _target_size(width: int, height: int, short_side) -> tuple:
    if short_side is None or short_side == min(width, height):
        return width, height
    if short_side > min(width, height):
        raise DeliverError(f"the master is {width}x{height}; refusing to upscale it to {label(short_side)}. "
                           "Use --sizes master or a smaller size")
    scale = short_side / min(width, height)
    if width >= height:
        return 2 * round(width * scale / 2), short_side
    return short_side, 2 * round(height * scale / 2)


def deliver(out_dir, name: str, sizes: list, master=None, project=None, comp=None,
            lufs: float = TARGET_LUFS, tp: float = TRUE_PEAK, allow_running_ae=False, aerender=None) -> dict:
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if master is None and not (project and comp):
        raise DeliverError("give --master <file.mov>, or --project and --comp to render one")
    if master is not None:
        master = Path(master).resolve()
        if not master.exists():
            raise DeliverError(f"master not found: {master}")
    archived = archive_previous(out_dir, keep=[master] if master else [])
    if master is None:
        master = render(project, comp, out_dir / f"{name}-master.mov", allow_running_ae=allow_running_ae,
                        aerender=aerender)
    info = probe(master)
    if not info.has_video:
        raise DeliverError(f"{master.name} has no video stream")
    targets = list({_target_size(info.width, info.height, s): s for s in sizes}.items())
    outputs = []
    for size, short_side in targets:
        out = out_dir / f"{name}-{label(min(size))}.mp4"
        _ffmpeg(encode_args(master, out, info.width, info.height, short_side, info.has_audio, lufs, tp),
                f"encoding {out.name}")
        outputs.append(verify(out, info.duration, size, lufs, tp, info.has_audio))
    return {"master": str(master), "duration": info.duration, "archived": str(archived) if archived else None,
            "target": {"lufs": lufs, "true_peak": tp}, "outputs": outputs, "ok": all(o["ok"] for o in outputs)}
