"""Gate 4: look previews and per-shot exposure matching.

Two separate jobs that both belong to the grade. Matching evens out shots that were filmed
under different light, so a cut does not flash; the look is the taste on top of that. The
previews here are ffmpeg approximations of the look, shown for the choice; the real grade is
applied in After Effects from the same numbers when the video is built.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from . import taste as tastelib
from .media import MediaError, extract_frame, run
from .styleframe import PAGE_JS

LOOKS = Path(__file__).resolve().parents[2] / "designs" / "looks.json"
MAX_MATCH_STOPS = 0.75       # beyond this it is a relight, not a match — flag it instead
SHOTS_IN_PREVIEW = 4
NEUTRAL_FOOTAGE = {"luma": 0.45, "contrast": 0.6, "warmth": 0.0, "saturation": 0.3}
TASTE_LOOK = "from-refs"
# Lumetri Color property indices, verified in After Effects
LUMETRI = {"temperature": "15", "tint": "16", "saturation": "17", "exposure": "20",
           "contrast": "21", "highlights": "22", "shadows": "23"}


class GradeError(RuntimeError):
    pass


@dataclass
class Look:
    id: str
    name: str
    mood: list
    note: str
    preview: str
    ae: dict


def load_looks(path=LOOKS) -> list:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise GradeError(f"cannot read {path}: {e}") from e
    if not isinstance(raw, list) or not raw:
        raise GradeError(f"{path}: expected a non-empty list of looks")
    looks, seen = [], set()
    for i, entry in enumerate(raw):
        where = f"looks[{i}]"
        if not isinstance(entry, dict) or not entry.get("id"):
            raise GradeError(f"{where}: 'id' is required")
        if entry["id"] in seen:
            raise GradeError(f"{where}: duplicate id '{entry['id']}'")
        seen.add(entry["id"])
        if not isinstance(entry.get("ae"), dict):
            raise GradeError(f"{where}: 'ae' must be the parameters the builder applies")
        looks.append(Look(id=entry["id"], name=entry.get("name", entry["id"]),
                          mood=list(entry.get("mood", [])), note=entry.get("note", ""),
                          preview=entry.get("preview", "null"), ae=dict(entry["ae"])))
    return looks


def lumetri_keys(values: dict) -> dict:
    """Lumetri values keyed by name ("contrast") or index ("21") -> keyed by index."""
    out = {}
    for key, value in values.items():
        key = str(key)
        if not key.isdigit():
            if key.lower() not in LUMETRI:
                raise GradeError(f"unknown Lumetri parameter '{key}' (expected an index or one of {', '.join(LUMETRI)})")
            key = LUMETRI[key.lower()]
        out[key] = value
    return out


def look_lumetri(look: dict) -> dict:
    """A grade.json look as Lumetri values. Its saturation is an offset; Lumetri's is absolute with 100 unchanged."""
    out = {}
    for name, index in LUMETRI.items():
        value = float(look.get(name, 0) or 0) + (100 if name == "saturation" else 0)
        if value or name == "saturation":
            out[index] = round(value, 3)
    return out


def looks_for(moods, catalogue=None, limit: int = 3) -> list:
    """Rank looks by how well their mood matches the brief, keeping neutral as a baseline."""
    catalogue = catalogue if catalogue is not None else load_looks()
    wanted = {m.lower() for m in moods or []}
    scored = sorted(catalogue, key=lambda l: (-len(wanted & {m.lower() for m in l.mood}), l.id))
    chosen = scored[:limit]
    neutral = next((l for l in catalogue if l.id == "neutral"), None)
    if neutral is not None and neutral not in chosen:
        chosen = chosen[:max(1, limit - 1)] + [neutral]
    return chosen


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def look_from_taste(targets: dict, footage: dict = None) -> Look:
    """A look that moves the footage's measured contrast, warmth and saturation to the references'."""
    footage = footage or NEUTRAL_FOOTAGE
    delta = {k: targets[k]["mean"] - footage[k] for k in NEUTRAL_FOOTAGE}
    exposure = round(_clamp(math.log2(max(targets["luma"]["mean"], 0.01) / max(footage["luma"], 0.01)), 0.3), 2)
    contrast = round(_clamp(delta["contrast"] * 100, 25))
    temperature = round(_clamp(delta["warmth"] * 150, 25))
    saturation = round(_clamp(delta["saturation"] * 100, 25))
    preview = (f"exposure=exposure={exposure},eq=contrast={1 + contrast / 100:.2f}:saturation={1 + saturation / 100:.2f},"
               f"colortemperature=temperature={round(6500 - temperature * 125)}:mix=0.45")
    note = (f"Built from your references: contrast {footage['contrast']:.2f} → {targets['contrast']['mean']:.2f}, "
            f"warmth {footage['warmth']:+.2f} → {targets['warmth']['mean']:+.2f}, "
            f"saturation {footage['saturation']:.2f} → {targets['saturation']['mean']:.2f}.")
    return Look(id=TASTE_LOOK, name="From your references", mood=["references"], note=note, preview=preview,
                ae={"exposure": exposure, "contrast": contrast, "temperature": temperature, "tint": 0,
                    "saturation": saturation, "shadows": 0, "highlights": 0})


def footage_stats(log: dict, out_dir) -> dict:
    """Mean tone of the representative frames, measured the same way as the references."""
    clips = representative_clips(log)
    if not clips:
        return None
    root = Path(log.get("root") or ".")
    measured = [tastelib.measure(_frame_for(c, Path(out_dir), root)) for c in clips]
    return {k: round(sum(m[k] for m in measured) / len(measured), 4) for k in NEUTRAL_FOOTAGE}


def look_from_dir(directory, look_id: str):
    """A look offered on a preview page, including one built from the references."""
    try:
        drafts = json.loads((Path(directory) / "drafts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = next((d for d in drafts if isinstance(d, dict) and d.get("id") == look_id and "ae" in d), None)
    if entry is None:
        return None
    return Look(id=entry["id"], name=entry.get("name", entry["id"]), mood=list(entry.get("mood", [])),
                note=entry.get("note", ""), preview=entry.get("preview", "null"), ae=dict(entry["ae"]))


# ---------------------------------------------------------------- exposure matching

def exposure_offsets(log: dict, target: float = None, limit: float = MAX_MATCH_STOPS) -> dict:
    """Stops of exposure per clip to bring every shot to a common brightness.

    Luma is a linear 0–1 mean, so the correction is log2(target / luma). Clips needing more
    than `limit` are reported rather than corrected: a shot that far off is a different lighting
    situation, and pushing it that hard turns noise into the subject.
    """
    clips = [c for c in log.get("clips", []) if isinstance(c.get("luma"), (int, float)) and c["luma"] > 0]
    if not clips:
        raise GradeError("no clip in this footage log has a usable brightness measurement")
    lumas = sorted(c["luma"] for c in clips)
    if target is None:
        target = lumas[len(lumas) // 2]      # the median shot is the one everything else joins
    offsets, extreme = {}, []
    for clip in clips:
        stops = round(math.log2(target / clip["luma"]), 3)
        if abs(stops) > limit:
            extreme.append({"name": clip["name"], "stops": stops, "luma": clip["luma"]})
            stops = round(math.copysign(limit, stops), 3)
        offsets[clip["name"]] = stops
    return {"target_luma": round(float(target), 4), "offsets": offsets, "beyond_match": extreme}


def grade_plan(look: Look, matching: dict, *, design_hint: str = "") -> dict:
    return {"look": {"id": look.id, "name": look.name, "note": look.note, **look.ae},
            "match": matching, "design_hint": design_hint}


def save_grade(plan: dict, out) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------- previews

def representative_clips(log: dict, count: int = SHOTS_IN_PREVIEW) -> list:
    """Spread the sample across the brightness range, so a look is judged on the hard shots too."""
    clips = [c for c in log.get("clips", []) if isinstance(c.get("luma"), (int, float)) and c["luma"] > 0]
    if not clips:
        return []
    clips.sort(key=lambda c: c["luma"])
    if len(clips) <= count:
        return clips
    step = (len(clips) - 1) / (count - 1)
    return [clips[round(i * step)] for i in range(count)]


def apply_look(src, look: Look, out, width: int = 640) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    chain = f"scale={int(width)}:-2"
    if look.preview and look.preview != "null":
        chain += "," + look.preview
    try:
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-frames:v", 1, "-vf", chain, "-q:v", 3, out],
            f"applying {look.id}")
    except MediaError as e:
        raise GradeError(str(e)) from e
    return out


def _frame_for(clip: dict, out_dir: Path, root: Path) -> Path:
    """One frame per representative clip.

    Frame paths in footage.json are relative to the analysis folder, not to wherever the
    previews are being written — and reusing the already-sampled frame means the grade gate
    works with the source drive unplugged.
    """
    frames = clip.get("frames") or []
    if frames and isinstance(frames[0], dict) and frames[0].get("file"):
        existing = Path(root) / frames[0]["file"]
        if existing.exists():
            return existing
    source = Path(clip["path"])
    if not source.exists():
        raise GradeError(f"{clip['name']}: no sampled frame in the log and the source is not reachable "
                         f"({source}) — is the footage drive plugged in?")
    at = float(frames[0]["at"]) if frames and isinstance(frames[0], dict) else min(1.0, clip.get("duration", 2) / 2)
    return extract_frame(source, at, out_dir / f"src-{Path(clip['name']).stem}.jpg", width=960)


CSS = """
:root { --bg:#14161a; --fg:#eef1f5; --muted:#9aa4b2; --line:#2b3038; }
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px 64px; background:var(--bg); color:var(--fg);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
h1 { font-size:22px; margin:0 0 4px; } .sub { color:var(--muted); margin:0 0 28px; }
.draft { border:1px solid var(--line); border-radius:12px; padding:18px; margin:0 0 22px; }
.draft.picked { border-color:#7dd3a0; box-shadow:0 0 0 1px #7dd3a0 inset; }
.head { display:flex; justify-content:space-between; align-items:baseline; gap:12px; flex-wrap:wrap; }
h2 { font-size:18px; margin:0; } .note-text { color:var(--muted); margin:6px 0 14px; }
.shots { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; }
.shots img { width:100%; border-radius:8px; display:block; }
.cap { color:var(--muted); font-size:12px; margin-top:4px; }
textarea.note { width:100%; margin:14px 0 10px; background:#0f1115; color:var(--fg);
                border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; }
button.choose { background:#7dd3a0; color:#0f1115; border:0; border-radius:8px;
                padding:9px 16px; font:600 14px inherit; cursor:pointer; }
button.choose:disabled { background:#3a4048; color:var(--muted); cursor:default; }
@media (max-width:600px) { body { padding:16px 16px 48px; } }
"""


def render_look_previews(looks: list, log: dict, out_dir, title: str = "Grade looks") -> Path:
    """A page of the same shots in each look, with the same click-to-choose contract as the design gate."""
    import html

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = representative_clips(log)
    if not clips:
        raise GradeError("the footage log has no clips with a brightness measurement to preview")
    root = Path(log.get("root") or ".")
    sources = [_frame_for(c, out_dir, root) for c in clips]
    sections = []
    for look in looks:
        shots = []
        for clip, src in zip(clips, sources):
            rel = f"{look.id}-{Path(clip['name']).stem}.jpg"
            apply_look(src, look, out_dir / rel)
            shots.append(f'<figure style="margin:0"><img src="{html.escape(rel)}" alt="">'
                         f'<figcaption class="cap">{html.escape(clip["name"])} · luma {clip["luma"]:.2f}'
                         f'</figcaption></figure>')
        sections.append(
            f'<section class="draft d-{html.escape(look.id)}" data-id="{html.escape(look.id)}">'
            f'<div class="head"><h2>{html.escape(look.name)}</h2>'
            f'<span class="cap">{html.escape(", ".join(look.mood))}</span></div>'
            f'<p class="note-text">{html.escape(look.note)}</p>'
            f'<div class="shots">{"".join(shots)}</div>'
            f'<textarea class="note" rows="2" placeholder="Anything to change about this look?"></textarea>'
            f'<button class="choose" data-id="{html.escape(look.id)}">Choose this</button></section>')
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{CSS}</style></head><body>'
            f'<h1>{html.escape(title)}</h1>'
            f'<p class="sub">The same {len(clips)} shots, spread across the brightness range of the footage. '
            f'These are ffmpeg previews of each look; the chosen one is applied for real in After Effects.</p>'
            f'{"".join(sections)}<script>{PAGE_JS}</script></body></html>')
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "drafts.json").write_text(
        json.dumps([{"id": l.id, "name": l.name, "mood": l.mood, "note": l.note, "preview": l.preview, "ae": l.ae}
                    for l in looks], ensure_ascii=False, indent=1),
        encoding="utf-8")
    return out_dir / "index.html"
