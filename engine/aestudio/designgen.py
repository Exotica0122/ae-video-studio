"""Compose design drafts: archetype × palette sampled from the footage × a font pairing.

Milestone 2a varies palette, fonts and treatment set. New treatments (a genuinely new look
for captions or end cards) are a later milestone — drafts may only use registered treatments.
"""
import colorsys
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import fonts as fontlib
from .design import COMPONENTS, DesignError, PALETTE_KEYS, ROLES, load_design

ARCHETYPES = Path(__file__).resolve().parents[2] / "designs" / "archetypes"
BASE_SIZES = {"headline": 150, "body": 100, "emphasis": 118, "quote": 92, "label": 64, "scripture": 128}
FALLBACK_ACCENT = "#C9A46A"
STYLE_SRC_IN = 1.0             # skip the first second of a clip; style frames want settled footage
STYLE_END_LEN = 5.0            # the end card reveals its rows at +2.8s and needs to finish before the fade


class DesignGenError(ValueError):
    pass


@dataclass
class Draft:
    id: str
    name: str
    mood: list
    recipe: dict
    fonts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def load_archetypes(path=ARCHETYPES) -> list:
    path = Path(path)
    files = sorted(path.glob("*.json"))
    if not files:
        raise DesignGenError(f"no archetypes in {path}")
    out, errors = [], []
    for f in files:
        try:
            arch = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{f.name}: {e}")
            continue
        missing_treatments = set(COMPONENTS) - set(arch.get("treatments", {}))
        missing_palette = set(PALETTE_KEYS) - set(arch.get("palette", {}))
        if missing_treatments:
            errors.append(f"{f.name}: treatments missing {sorted(missing_treatments)}")
        if missing_palette:
            errors.append(f"{f.name}: palette missing {sorted(missing_palette)}")
        out.append(arch)
    if errors:
        raise DesignGenError("bad archetypes:\n  " + "\n  ".join(errors))
    return out


def accent_from_footage(log, fallback=FALLBACK_ACCENT) -> str:
    best, best_score = None, -1.0
    for clip in (log or {}).get("clips", []):
        for frame in clip.get("frames", []):
            for color in frame.get("colors", []):
                if len(color) != 3:
                    continue
                r, g, b = (max(0, min(255, int(c))) / 255 for c in color)
                h, l, s = colorsys.rgb_to_hls(r, g, b)
                score = s * (1 - abs(l - 0.55) * 1.6)
                if score > best_score:
                    best, best_score = (r, g, b), score
    if not best or best_score <= 0:
        return fallback
    hue, _, saturation = colorsys.rgb_to_hls(*best)
    r, g, b = colorsys.hls_to_rgb(hue, 0.58, min(1.0, max(0.35, saturation)))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _recipe(arch, pairing, accent) -> dict:
    scale = float(arch.get("type_scale", 1.0))
    # A font's PostScript name (what After Effects needs) is not its browser family name
    # (what the mockup CSS needs), so carry both. load_design ignores the extra key.
    families = {ps: font.family for font in (pairing["headline"], pairing["body"], pairing["quote"])
                for ps in font.postscript.values()}
    type_block = {}
    for role, name in fontlib.fonts_for(pairing, ROLES).items():
        type_block[role] = {"font": name, "family": families.get(name, name),
                            "size": round(BASE_SIZES[role] * scale, 1)}
    palette = dict(arch["palette"])
    if arch.get("accent_from_footage"):
        palette["accent"] = accent
    return {"id": f"{arch['id']}-{pairing['headline'].id}", "name": f"{arch['name']} · {pairing['headline'].family}",
            "mood": list(arch.get("moods", [])),
            "tokens": {"palette": palette, "type": type_block, "motion": dict(arch.get("motion", {})),
                       "texture": dict(arch.get("texture", {}))},
            "components": {c: {"treatment": t} for c, t in arch["treatments"].items()},
            "grade_hint": arch.get("grade_hint", ""), "sfx_hint": list(arch.get("sfx_hint", []))}


def propose(brief_moods, log=None, scripts=("ko",), installed_only=True, archetypes=None, limit=3,
            catalogue=None, dirs=fontlib.FONT_DIRS, pairings=2) -> list:
    """Compose design drafts: `limit` directions, each offered with up to `pairings` typefaces.

    A font-layer failure is reported as a design failure: callers of this module catch
    DesignGenError, and a raw FontError escaping here reached the CLI as an untranslated
    traceback.

    Each pairing becomes its own draft, because a draft already carries a unique id and its own
    Choose button — the preview page needs nothing new to offer a second typeface.
    """
    archetypes = archetypes or load_archetypes()
    moods = [m.lower() for m in brief_moods or []]
    ranked = sorted(archetypes, key=lambda a: (-len(set(moods) & {m.lower() for m in a.get("moods", [])}), a["id"]))
    accent = accent_from_footage(log)
    drafts, directions = [], 0
    for arch in ranked:
        if directions >= limit:
            break
        try:
            pairs = fontlib.pairings(arch.get("font_moods") or arch.get("moods", []), scripts=scripts,
                                     catalogue=catalogue, installed_only=installed_only, dirs=dirs)
        except fontlib.FontError as e:
            raise DesignGenError(f"the font catalogue is unusable: {e}") from e
        if not pairs:
            continue
        directions += 1
        seen = set()
        for pair in pairs[:max(1, int(pairings))]:
            recipe = _recipe(arch, pair, accent)
            if recipe["id"] in seen:
                continue                      # two pairings sharing a headline font are one option
            seen.add(recipe["id"])
            drafts.append(Draft(id=recipe["id"], name=recipe["name"], mood=recipe["mood"], recipe=recipe,
                                fonts={r: spec["font"] for r, spec in recipe["tokens"]["type"].items()},
                                notes=list(pair["notes"])))
    return drafts


def save_design(draft: Draft, out_path) -> Path:
    """Validate first, replace second: a bad draft must not destroy a good design.json."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f".{out_path.name}.tmp.json")      # same directory, so os.replace is atomic
    tmp.write_text(json.dumps(draft.recipe, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        load_design(tmp)           # fails loudly if the draft is not a valid design
    except DesignError as e:
        tmp.unlink(missing_ok=True)
        # the temp name is an implementation detail; report the file the user asked for
        raise DesignError(str(e).replace(str(tmp), str(out_path))) from None
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, out_path)
    return out_path


def _style_shot(clip, start: float, segment: float) -> dict:
    """Keep the shot inside its clip: a 2s clip cannot give 1s of handle plus 3s of frames."""
    available = float(clip.get("duration") or 0) or STYLE_SRC_IN + segment      # unknown length: trust it
    src_in = STYLE_SRC_IN if available >= STYLE_SRC_IN + segment else 0.0
    segment = round(min(segment, max(available - src_in, 0.2)), 3)
    return {"clip": clip["path"], "in": round(start, 3), "out": round(start + segment, 3), "src_in": src_in}


def style_frame_plan(draft: Draft, log, out_dir, script_lines=None, duration=10.0) -> Path:
    brightest = sorted((c for c in (log or {}).get("clips", []) if c.get("path")),
                       key=lambda c: -(c.get("luma") or 0))
    want = round(duration - STYLE_END_LEN - 0.3, 3)
    # Prefer clips long enough to hold the whole segment; fall back to the brightest ones.
    clips = sorted(brightest, key=lambda c: float(c.get("duration") or 0) < STYLE_SRC_IN + want)[:2]
    if not clips:
        raise DesignGenError("style frames need at least one logged clip with a path")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = script_lines or [["이 화면의 글자 크기와"], ["색이 ", {"hl": "잘 보이는지"}, " 확인해 주세요."]]
    shots = [_style_shot(clips[0], 0.0, want if len(clips) > 1 else want)]
    if len(clips) > 1 and shots[0]["out"] < want:
        shots.append(_style_shot(clips[1], shots[0]["out"], want - shots[0]["out"]))
    # Shots are clamped to the footage that exists; the end card is a full-frame page and
    # needs none, so it always gets its own time after them.
    half = round(max(shot["out"] for shot in shots), 3)
    if half < 0.8:
        raise DesignGenError(
            f"the logged clips give only {half:.2f}s of footage, too little to judge a design on; "
            "log a longer clip")
    duration = round(half + 0.3 + STYLE_END_LEN, 3)
    plan = {"name": "STYLE_" + draft.id.upper().replace("-", "_"),
            "format": {"width": 3840, "height": 2160, "fps": 23.976, "duration": duration},
            "shots": shots, "voices": [], "graphics": [
                {"type": "caption", "voice": None, "lines": lines, "in": 0.3, "out": half + 0.2},
                {"type": "lower-third", "at": 0.8, "dur": half, "name": "이름 예시", "role": "역할 예시"},
                {"type": "end-card", "in": half + 0.3, "title": "제목 예시", "year": 2027,
                 "photo": {"clip": str(clips[0]["path"]), "src_in": STYLE_SRC_IN},
                 "tagline": "한 줄 설명이 들어갑니다",
                 "rows": [{"label": "안내", "values": ["첫째 줄", "둘째 줄"]}]}],
            "fade_out": 0.5}
    path = out_dir / "edit.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
