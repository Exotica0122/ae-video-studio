"""The taste gate: reference images the user supplies to define the look, measured and kept.

refs/ holds the downloaded or copied references, refs/sources.json where each came from, and
refs/taste.json the working copy that gets measured, annotated with traits and ticked on the
board. taste-choose validates it and writes plan/taste.json, the only file later stages read.
"""
import colorsys
import html
import json
import math
import re
import shutil
import statistics
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from .media import MediaError, _raw, extract_frame, probe
from .preview import ChoiceHandler, read_choice

REFS = "refs"
SOURCES = "refs/sources.json"
WORKING = "refs/taste.json"
APPROVED = "plan/taste.json"
BOARD = "board.html"
ROLES = ("want", "avoid")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")
VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
                 "image/bmp": ".bmp", "image/tiff": ".tif", "video/mp4": ".mp4", "video/quicktime": ".mov",
                 "video/webm": ".webm", "video/x-matroska": ".mkv"}
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.5 Safari/605.1.15")
MAX_DOWNLOAD = 300 * 1024 * 1024
SAMPLE = 64                   # measure on a 64x64 thumbnail: palette and tone survive, noise does not
PALETTE_SIZE = 5
TARGET_SWATCHES = 6
MERGE_DISTANCE = 48.0         # RGB distance under which two ref swatches count as the same colour
SCENE_THRESHOLD = 0.3
STATS = ("luma", "contrast", "warmth", "saturation")


class TasteError(ValueError):
    pass


# ---------------------------------------------------------------- collecting

def _ytdlp():
    return shutil.which("yt-dlp")


def _read_sources(root: Path) -> list:
    path = root / SOURCES
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TasteError(f"cannot read {path}: {e}") from e
    if not isinstance(data, list):
        raise TasteError(f"{path}: expected a list of sources")
    return data


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _is_url(source: str) -> bool:
    return urllib.parse.urlparse(str(source)).scheme in ("http", "https")


def _download(url: str, stem: Path) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "image/*,video/*;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if kind.startswith("text/html"):
                return _download_page(url, stem)
            suffix = CONTENT_TYPES.get(kind) or Path(urllib.parse.urlparse(url).path).suffix.lower()
            if suffix not in IMAGE_SUFFIXES + VIDEO_SUFFIXES:
                raise TasteError(f"{url} is {kind or 'an unknown type'}, not an image or a video")
            out = stem.with_suffix(suffix)
            data = response.read(MAX_DOWNLOAD + 1)
    except (urllib.error.URLError, OSError) as e:
        raise TasteError(f"cannot download {url}: {e}") from e
    if len(data) > MAX_DOWNLOAD:
        raise TasteError(f"{url} is over {MAX_DOWNLOAD // 2**20} MB — download a shorter clip yourself")
    out.write_bytes(data)
    return out


def _download_page(url: str, stem: Path) -> Path:
    tool = _ytdlp()
    if not tool:
        raise TasteError(f"{url} is a web page, not an image — open it and copy the image address, "
                         "or install yt-dlp for video pages")
    result = subprocess.run([tool, "-q", "--no-playlist", "--no-warnings", "-f", "b[height<=720]/b",
                             "-o", f"{stem}.%(ext)s", url], capture_output=True, text=True)
    found = sorted(p for p in stem.parent.glob(f"{stem.name}.*") if p.suffix.lower() in VIDEO_SUFFIXES)
    if result.returncode != 0 or not found:
        tail = " / ".join((result.stderr or "").strip().splitlines()[-2:])
        raise TasteError(f"yt-dlp could not fetch {url}: {tail or 'no video file written'}")
    return found[0]


def _frame_times(duration: float, count: int = 3) -> list:
    if duration <= 0:
        return [0.0]
    return [round(duration * (0.15 + 0.7 * i / max(1, count - 1)), 3) for i in range(count)]


def add_refs(project_root, sources, role: str = "want", at=None, today=None) -> list:
    """Copy or download each source into refs/ and record it; a source already there is skipped."""
    if role not in ROLES:
        raise TasteError(f"role must be one of {ROLES}, not {role!r}")
    root = Path(project_root).expanduser()
    (root / REFS).mkdir(parents=True, exist_ok=True)
    entries = _read_sources(root)
    known = {e.get("source"): e for e in entries}
    added = []
    for source in sources:
        source = str(source)
        key = source if _is_url(source) else str(Path(source).expanduser().resolve())
        if key in known:
            added.append(known[key])
            continue
        ref_id = f"ref-{len(entries) + 1:02d}"
        stem = root / REFS / ref_id
        if _is_url(source):
            path = _download(source, stem)
        else:
            src = Path(key)
            if not src.is_file():
                raise TasteError(f"reference not found: {source}")
            if src.suffix.lower() not in IMAGE_SUFFIXES + VIDEO_SUFFIXES:
                raise TasteError(f"{src.name} is not an image or a video this gate can read")
            path = stem.with_suffix(src.suffix.lower())
            shutil.copyfile(src, path)
        kind = "video" if path.suffix.lower() in VIDEO_SUFFIXES else "image"
        entry = {"id": ref_id, "file": f"{REFS}/{path.name}", "source": key, "role": role, "kind": kind,
                 "added": (today or date.today()).isoformat()}
        if kind == "video":
            entry["frames"] = _video_frames(path, at)
        entries.append(entry)
        known[key] = entry
        added.append(entry)
        _write_json(root / SOURCES, entries)
    return added


def _video_frames(path: Path, at=None) -> list:
    try:
        duration = probe(path).duration
        times = [float(t) for t in at] if at else _frame_times(duration)
        frames = []
        for i, t in enumerate(times, 1):
            out = path.with_name(f"{path.stem}-f{i}.jpg")
            extract_frame(path, min(t, max(0.0, duration - 0.05)), out, width=960)
            frames.append(f"{REFS}/{out.name}")
    except MediaError as e:
        raise TasteError(f"cannot sample frames from {path.name}: {e}") from e
    return frames


# ---------------------------------------------------------------- measuring

def _pixels(src, at: float = 0.0) -> list:
    data = _raw(src, at, f"{SAMPLE}:{SAMPLE}", "rgb24", f"reading pixels of {Path(src).name}")
    return [tuple(data[i:i + 3]) for i in range(0, len(data) - 2, 3)]


def _luma(p) -> float:
    return (0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2]) / 255


def _dist(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c))) for c in rgb)


def rgb_of(hex_value: str) -> tuple:
    h = hex_value.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _seeds(pixels: list, k: int) -> list:
    """Deterministic seeds spread across the brightness range, so the same image gives the same palette."""
    ordered = sorted(pixels, key=_luma)
    return [ordered[min(len(ordered) - 1, int((i + 0.5) * len(ordered) / k))] for i in range(k)]


def _kmeans_py(pixels: list, k: int, rounds: int) -> list:
    centres = [tuple(float(c) for c in s) for s in _seeds(pixels, k)]
    counts = [0] * k
    for _ in range(rounds):
        sums = [[0.0, 0.0, 0.0] for _ in centres]
        counts = [0] * len(centres)
        for p in pixels:
            best = min(range(len(centres)), key=lambda i: sum((p[j] - centres[i][j]) ** 2 for j in range(3)))
            counts[best] += 1
            for j in range(3):
                sums[best][j] += p[j]
        moved = [tuple(s[j] / n for j in range(3)) if n else c for s, n, c in zip(sums, counts, centres)]
        if moved == centres:
            break
        centres = moved
    return [(c, n) for c, n in zip(centres, counts) if n]


def _kmeans_np(pixels: list, k: int, rounds: int):
    try:
        import numpy as np
    except ImportError:
        return None
    data = np.asarray(pixels, dtype=float)
    centres = np.asarray(_seeds(pixels, k), dtype=float)
    labels = np.zeros(len(data), dtype=int)
    for _ in range(rounds):
        labels = ((data[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        moved = np.array([data[labels == i].mean(axis=0) if (labels == i).any() else centres[i]
                          for i in range(len(centres))])
        if np.allclose(moved, centres):
            break
        centres = moved
    counts = np.bincount(labels, minlength=len(centres))
    return [(tuple(c), int(n)) for c, n in zip(centres, counts) if n]


def palette(pixels: list, k: int = PALETTE_SIZE, rounds: int = 12) -> list:
    """Dominant colours by k-means, heaviest first, as [{"hex", "weight"}]."""
    if not pixels:
        return []
    k = max(1, min(k, len(set(pixels))))
    clusters = _kmeans_np(pixels, k, rounds) or _kmeans_py(pixels, k, rounds)
    total = sum(n for _, n in clusters)
    merged = _merge([(c, n / total) for c, n in clusters], MERGE_DISTANCE / 2)
    return [{"hex": _hex(rgb), "weight": round(w, 3)} for rgb, w in merged]

def pixel_stats(pixels: list) -> dict:
    lumas = sorted(_luma(p) for p in pixels)
    n = len(lumas)
    sats = [0.0 if max(p) == 0 else (max(p) - min(p)) / max(p) for p in pixels]
    return {"palette": palette(pixels),
            "luma": round(sum(lumas) / n, 4),
            "contrast": round(lumas[min(n - 1, int(n * 0.95))] - lumas[int(n * 0.05)], 4),
            "contrast_std": round(statistics.pstdev(lumas), 4),
            "warmth": round(sum(p[0] - p[2] for p in pixels) / n / 255, 4),
            "saturation": round(sum(sats) / n, 4)}


def cut_rate(src, threshold: float = SCENE_THRESHOLD) -> dict:
    """Cuts per minute by ffmpeg scene detection."""
    duration = probe(src).duration
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TasteError("ffmpeg not found — install it with `brew install ffmpeg`")
    result = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(src), "-an", "-vf",
                             f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise TasteError(f"scene detection failed on {Path(src).name}")
    cuts = len(re.findall(r"pts_time:", result.stderr))
    minutes = duration / 60 if duration else 0
    return {"cuts": cuts, "cuts_per_min": round(cuts / minutes, 2) if minutes else 0.0,
            "shot_len": round(duration / (cuts + 1), 2) if duration else 0.0}


def measure(ref) -> dict:
    """Palette, mean luma, contrast (p95-p5 and std), warmth (R-B) and saturation; video adds cut rate."""
    ref = Path(ref)
    if not ref.is_file():
        raise TasteError(f"reference not found: {ref}")
    try:
        if ref.suffix.lower() in VIDEO_SUFFIXES:
            duration = probe(ref).duration
            pixels = [p for t in _frame_times(duration) for p in _pixels(ref, min(t, max(0.0, duration - 0.05)))]
            return {**pixel_stats(pixels), **cut_rate(ref)}
        return pixel_stats(_pixels(ref))
    except MediaError as e:
        raise TasteError(f"cannot measure {ref.name}: {e}") from e


# ---------------------------------------------------------------- the taste file

def _range(values: list) -> dict:
    return {"min": round(min(values), 4), "max": round(max(values), 4),
            "mean": round(sum(values) / len(values), 4)}


def _merge(swatches, distance: float) -> list:
    """Fold each colour into a heavier one within `distance`, heaviest first."""
    groups = []
    for rgb, weight in sorted(swatches, key=lambda s: -s[1]):
        home = next((g for g in groups if _dist(g[0], rgb) < distance), None)
        if home is None:
            groups.append([list(rgb), weight])
            continue
        total = home[1] + weight
        home[0] = [(a * home[1] + b * weight) / total for a, b in zip(home[0], rgb)]
        home[1] = total
    return sorted(groups, key=lambda g: -g[1])


def _merge_swatches(refs: list) -> list:
    pooled = [(rgb_of(s["hex"]), s["weight"] / len(refs)) for r in refs for s in r["stats"]["palette"]]
    return [{"hex": _hex(rgb), "weight": round(w, 3)} for rgb, w in _merge(pooled, MERGE_DISTANCE)[:TARGET_SWATCHES]]

def _aggregate(refs: list) -> dict:
    out = {"refs": [r["id"] for r in refs], "palette": _merge_swatches(refs)}
    for key in STATS:
        out[key] = _range([r["stats"][key] for r in refs])
    rates = [r["stats"]["cuts_per_min"] for r in refs if "cuts_per_min" in r["stats"]]
    if rates:
        out["cuts_per_min"] = _range(rates)
    return out


def targets(refs: list) -> dict:
    """What the "want" refs share, and what the "avoid" refs share, for later stages to aim at."""
    measured = [r for r in refs if r.get("stats")]
    want = [r for r in measured if r["role"] == "want"]
    avoid = [r for r in measured if r["role"] == "avoid"]
    out = _aggregate(want) if want else {}
    if avoid:
        out["avoid"] = _aggregate(avoid)
    return out


def _check_stats(stats, where: str, errors: list):
    if not isinstance(stats, dict):
        errors.append(f"{where}: 'stats' must be the measured values (run taste-measure)")
        return
    for key in STATS:
        if not isinstance(stats.get(key), (int, float)):
            errors.append(f"{where}: stats.{key} must be a number")
    swatches = stats.get("palette")
    if not isinstance(swatches, list) or not swatches or not all(
            isinstance(s, dict) and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(s.get("hex", ""))) for s in swatches):
        errors.append(f"{where}: stats.palette must be a list of {{\"hex\": \"#RRGGBB\", \"weight\"}}")


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def validate_taste(data, where: str = "taste.json", measured: bool = True) -> dict:
    errors = []
    if not isinstance(data, dict):
        raise TasteError(f"{where}: expected a JSON object")
    refs = data.get("refs")
    if not isinstance(refs, list):
        errors.append("'refs' must be a list")
        refs = []
    seen = set()
    for i, ref in enumerate(refs):
        at = f"refs[{i}]"
        if not isinstance(ref, dict):
            errors.append(f"{at}: must be an object")
            continue
        if not isinstance(ref.get("id"), str) or not ref["id"]:
            errors.append(f"{at}: 'id' is required")
        elif ref["id"] in seen:
            errors.append(f"{at}: duplicate id '{ref['id']}'")
        seen.add(ref.get("id"))
        for key in ("path", "source"):
            if not isinstance(ref.get(key), str) or not ref[key]:
                errors.append(f"{at}: '{key}' is required")
        if ref.get("role") not in ROLES:
            errors.append(f"{at}: 'role' must be one of {list(ROLES)}")
        if not _strings(ref.get("traits", [])):
            errors.append(f"{at}: 'traits' must be a list of short non-empty strings")
        if measured or ref.get("stats") is not None:
            _check_stats(ref.get("stats"), at, errors)
    for key in ("approved_traits", "rejected_traits"):
        if not _strings(data.get(key, [])):
            errors.append(f"'{key}' must be a list of strings")
    both = set(data.get("approved_traits") or []) & set(data.get("rejected_traits") or [])
    if both:
        errors.append(f"traits both approved and rejected: {sorted(both)}")
    if not isinstance(data.get("targets", {}), dict):
        errors.append("'targets' must be an object")
    if errors:
        raise TasteError(f"{where}:\n  " + "\n  ".join(errors))
    return data


def load_taste(path, measured: bool = True) -> dict:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TasteError(f"cannot read {path}: {e}") from e
    return validate_taste(data, str(path), measured=measured)


def approved_taste(project_root):
    """plan/taste.json, or None when the project has none — callers then behave as before."""
    path = Path(project_root).expanduser() / APPROVED
    return load_taste(path) if path.exists() else None


def measure_refs(project_root) -> dict:
    """Measure every source into refs/taste.json, keeping traits and ticks already written."""
    root = Path(project_root).expanduser()
    sources = _read_sources(root)
    if not sources:
        raise TasteError(f"no references in {root / SOURCES} — add some with taste-add first")
    working = root / WORKING
    old = load_taste(working, measured=False) if working.exists() else {}
    previous = {r["id"]: r for r in old.get("refs", [])}
    refs = []
    for entry in sources:
        kept = previous.get(entry["id"], {})
        ref = {"id": entry["id"], "path": entry["file"], "source": entry["source"], "role": entry["role"],
               "kind": entry.get("kind", "image"), "added": entry.get("added"),
               "stats": measure(root / entry["file"]), "traits": list(kept.get("traits", []))}
        if entry.get("frames"):
            ref["frames"] = list(entry["frames"])
        refs.append(ref)
    data = {"version": 1, "refs": refs,
            "approved_traits": list(old.get("approved_traits", [])),
            "rejected_traits": list(old.get("rejected_traits", [])),
            "targets": targets(refs)}
    _write_json(working, validate_taste(data, str(working)))
    return data


def all_traits(data: dict) -> list:
    return list(dict.fromkeys(t for r in data.get("refs", []) for t in r.get("traits", [])))


def choose(project_root, none: bool = False, note: str = None) -> Path:
    """Validate refs/taste.json and write it as plan/taste.json, the approved taste."""
    root = Path(project_root).expanduser()
    if none:
        data = {"version": 1, "refs": [], "approved_traits": [], "rejected_traits": [], "targets": {},
                "note": note or "no references — the look comes from the brief and the footage"}
    else:
        working = root / WORKING
        if not working.exists():
            raise TasteError(f"no {working} — run taste-measure first, or pass --none if there are no references")
        data = load_taste(working)
        if not data["refs"]:
            raise TasteError(f"{working} has no references — pass --none to approve an empty taste")
        unlooked = [r["id"] for r in data["refs"] if not r.get("traits")]
        if unlooked:
            raise TasteError(f"no traits written for {', '.join(unlooked)} — look at each reference and "
                             "describe it before approving")
        data["targets"] = targets(data["refs"])
        choice = read_choice(root / REFS) or {}
        data["note"] = note or choice.get("note")
    data["approved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = root / APPROVED
    _write_json(out, validate_taste(data, str(out)))
    return out


# ---------------------------------------------------------------- the board

class TasteHandler(ChoiceHandler):
    """Records ticked and struck traits into refs/taste.json as well as choice.json."""

    def choose(self, payload: dict):
        working = self._root / Path(WORKING).name
        try:
            data = load_taste(working, measured=False)
        except TasteError as e:
            return None, str(e)
        known = set(all_traits(data))
        approved, rejected = payload.get("approved", []), payload.get("rejected", [])
        if not _strings(approved) or not _strings(rejected):
            return None, "approved and rejected must be lists of traits"
        unknown = (set(approved) | set(rejected)) - known
        if unknown:
            return None, f"unknown traits {sorted(unknown)}"
        if set(approved) & set(rejected):
            return None, "a trait cannot be both wanted and avoided"
        note = payload.get("note")
        if note is not None and not isinstance(note, str):
            return None, "note must be a string"
        data["approved_traits"], data["rejected_traits"] = list(approved), list(rejected)
        _write_json(working, data)
        return {"id": "taste", "approved": list(approved), "rejected": list(rejected), "note": note or None}, None


BOARD_CSS = """
:root { --bg:#14161a; --fg:#eef1f5; --muted:#9aa4b2; --line:#2b3038; --want:#7dd3a0; --avoid:#f08a7a; }
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px 64px; background:var(--bg); color:var(--fg);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
h1 { font-size:22px; margin:0 0 4px; } .sub { color:var(--muted); margin:0 0 24px; max-width:70ch; }
.refs { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:18px; }
.ref { border:1px solid var(--line); border-radius:12px; padding:14px; min-width:0; }
.ref.avoid { border-color:#5a3530; }
.ref img { width:100%; border-radius:8px; display:block; }
.frames { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; }
.head { display:flex; justify-content:space-between; align-items:baseline; gap:8px; margin:10px 0 6px; }
.role { font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.06em; }
.want .role { color:var(--want); } .avoid .role { color:var(--avoid); }
.src { color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
.swatches { display:flex; height:22px; border-radius:6px; overflow:hidden; margin:8px 0; }
.stats { color:var(--muted); font-size:12px; margin:0 0 10px; }
.traits { list-style:none; padding:0; margin:0; }
.traits li { display:flex; align-items:center; gap:6px; padding:4px 0; border-top:1px solid var(--line); }
.traits li span { flex:1; } .traits li.no span { text-decoration:line-through; color:var(--muted); }
.traits button { background:none; border:1px solid var(--line); color:var(--muted); border-radius:6px;
                 width:32px; height:28px; cursor:pointer; font:inherit; }
.traits li.yes button.yes { background:var(--want); color:#0f1115; border-color:var(--want); }
.traits li.no button.no { background:var(--avoid); color:#0f1115; border-color:var(--avoid); }
.empty { color:var(--muted); font-size:13px; }
.save { margin-top:24px; max-width:640px; }
textarea.note { width:100%; background:#0f1115; color:var(--fg); border:1px solid var(--line);
                border-radius:8px; padding:8px; font:inherit; margin-bottom:10px; }
button.choose { background:var(--want); color:#0f1115; border:0; border-radius:8px; padding:9px 16px;
                font:600 14px inherit; cursor:pointer; }
button.choose:disabled { background:#3a4048; color:var(--muted); cursor:default; }
"""

BOARD_JS = """
const offline = location.protocol === 'file:';
document.querySelectorAll('.traits li').forEach(function (li) {
  li.querySelectorAll('button').forEach(function (b) {
    b.addEventListener('click', function () {
      const same = document.querySelectorAll('.traits li[data-trait="' + CSS.escape(li.dataset.trait) + '"]');
      const next = li.classList.contains(b.className) ? '' : b.className;
      same.forEach(function (x) { x.classList.remove('yes', 'no'); if (next) x.classList.add(next); });
    });
  });
});
const save = document.querySelector('button.choose');
if (offline) { save.disabled = true; save.textContent = 'open via taste-board to save'; }
save.addEventListener('click', async function () {
  const pick = function (cls) {
    return Array.from(new Set(Array.from(document.querySelectorAll('.traits li.' + cls))
      .map(function (li) { return li.dataset.trait; })));
  };
  save.disabled = true;
  try {
    const r = await fetch('/choose', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: 'taste', approved: pick('yes'), rejected: pick('no'),
                            note: document.querySelector('.note').value})});
    if (!r.ok) throw new Error((await r.json()).error);
    save.textContent = 'Saved — you can close this tab';
  } catch (e) { save.disabled = false; save.textContent = 'Save (retry): ' + e.message; }
});
"""


def _ref_card(ref: dict, approved: set, rejected: set) -> str:
    e = html.escape
    images = ref.get("frames") or ([ref["path"]] if ref.get("kind", "image") == "image" else [])
    tags = "".join(f'<img src="{e(Path(p).name)}" alt="">' for p in images)
    media = f'<div class="frames">{tags}</div>' if len(images) > 1 else tags
    stats = ref.get("stats") or {}
    swatches = "".join(f'<span title="{e(s["hex"])}" style="background:{e(s["hex"])};flex:{float(s["weight"]):g}"></span>'
                       for s in stats.get("palette", []))
    numbers = (f'luma {stats["luma"]:.2f} · contrast {stats["contrast"]:.2f} · warmth {stats["warmth"]:+.2f} · '
               f'saturation {stats["saturation"]:.2f}' if stats else "not measured")
    if "cuts_per_min" in stats:
        numbers += f' · {stats["cuts_per_min"]:.0f} cuts/min'
    rows = []
    for trait in ref.get("traits", []):
        state = "yes" if trait in approved else "no" if trait in rejected else ""
        rows.append(f'<li class="{state}" data-trait="{e(trait)}"><span>{e(trait)}</span>'
                    f'<button class="yes" title="want this">✓</button>'
                    f'<button class="no" title="avoid this">✗</button></li>')
    traits = f'<ul class="traits">{"".join(rows)}</ul>' if rows else '<p class="empty">No traits written yet.</p>'
    source = ref["source"] if _is_url(ref["source"]) else Path(ref["source"]).name
    return (f'<section class="ref {e(ref["role"])}">{media}'
            f'<div class="head"><strong>{e(ref["id"])}</strong><span class="role">{e(ref["role"])}</span></div>'
            f'<div class="src">{e(source)}</div><div class="swatches">{swatches}</div>'
            f'<p class="stats">{e(numbers)}</p>{traits}</section>')


def render_board(project_root) -> Path:
    root = Path(project_root).expanduser()
    working = root / WORKING
    if not working.exists():
        raise TasteError(f"no {working} — run taste-measure first")
    data = load_taste(working)
    approved, rejected = set(data.get("approved_traits", [])), set(data.get("rejected_traits", []))
    cards = "".join(_ref_card(r, approved, rejected) for r in data["refs"])
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Taste board</title><style>{BOARD_CSS}</style></head><body>'
            f'<h1>Taste board</h1><p class="sub">Your references, measured. Tick ✓ what the video should have '
            f'and ✗ what it must not. Every later stage — type, layout, motion and grade — is held to what '
            f'you save here.</p><div class="refs">{cards}</div>'
            f'<div class="save"><textarea class="note" rows="2" placeholder="Anything the references miss?">'
            f'</textarea><button class="choose">Save</button></div><script>{BOARD_JS}</script></body></html>')
    out = root / REFS / BOARD
    out.write_text(page, encoding="utf-8")
    return out


# ---------------------------------------------------------------- comparing

def palette_distance(swatches: list, target: list) -> float:
    """Weighted mean distance from each swatch to its nearest target colour, 0 (same) to 1 (opposite)."""
    if not swatches or not target:
        return 0.0
    goal = [rgb_of(t["hex"]) for t in target]
    total = sum(s["weight"] for s in swatches) or 1.0
    far = sum(s["weight"] * min(_dist(rgb_of(s["hex"]), g) for g in goal) for s in swatches)
    return round(far / total / _dist((0, 0, 0), (255, 255, 255)), 4)


def mood_words(taste: dict) -> list:
    """Words from approved traits written as "mood: ..." — they rank designs and looks like brief moods."""
    words = []
    for trait in (taste or {}).get("approved_traits", []):
        facet, _, text = trait.partition(":")
        if text and facet.strip().lower() == "mood":
            words += [w.strip().lower() for w in re.split(r"[,/]| and ", text) if w.strip()]
    return words
