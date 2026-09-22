"""Gate 3: look previews and per-shot exposure matching.

Two separate jobs that both belong to the grade. Matching evens out shots that were filmed
under different light, so a cut does not flash; the look is the taste on top of that. The
previews here are ffmpeg approximations of the look, shown for the choice; the real grade is
applied in After Effects from the same numbers when the video is built.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .media import MediaError, extract_frame, run
from .styleframe import PAGE_JS

LOOKS = Path(__file__).resolve().parents[2] / "designs" / "looks.json"
MAX_MATCH_STOPS = 0.75       # beyond this it is a relight, not a match — flag it instead
SHOTS_IN_PREVIEW = 4


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
    """A page of the same shots in each look, with the same click-to-choose contract as gate 2."""
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
        json.dumps([{"id": l.id, "name": l.name} for l in looks], ensure_ascii=False, indent=1),
        encoding="utf-8")
    return out_dir / "index.html"
