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
from .design import COMPONENTS, PALETTE_KEYS, ROLES, load_design

ARCHETYPES = Path(__file__).resolve().parents[2] / "designs" / "archetypes"
BASE_SIZES = {"headline": 150, "body": 100, "emphasis": 118, "quote": 92, "label": 64, "scripture": 128}
FALLBACK_ACCENT = "#C9A46A"


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
    r, g, b = colorsys.hls_to_rgb(colorsys.rgb_to_hls(*best)[0], 0.58, min(1.0, max(0.35, colorsys.rgb_to_hls(*best)[2])))
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
            catalogue=None, dirs=fontlib.FONT_DIRS) -> list:
    archetypes = archetypes or load_archetypes()
    moods = [m.lower() for m in brief_moods or []]
    ranked = sorted(archetypes, key=lambda a: (-len(set(moods) & {m.lower() for m in a.get("moods", [])}), a["id"]))
    accent = accent_from_footage(log)
    drafts, used = [], set()
    for arch in ranked:
        pairs = fontlib.pairings(arch.get("font_moods") or arch.get("moods", []), scripts=scripts,
                                 catalogue=catalogue, installed_only=installed_only, dirs=dirs)
        for pairing in pairs:
            key = (arch["id"], pairing["headline"].id)
            if key in used:
                continue
            used.add(key)
            recipe = _recipe(arch, pairing, accent)
            drafts.append(Draft(id=recipe["id"], name=recipe["name"], mood=recipe["mood"], recipe=recipe,
                                fonts={r: s["font"] for r, s in recipe["tokens"]["type"].items()},
                                notes=list(pairing["notes"])))
            break
        if len(drafts) >= limit:
            break
    if not drafts:
        raise DesignGenError("no design draft could be composed; check the font catalogue and archetypes")
    return drafts


def save_design(draft: Draft, out_path) -> Path:
    """Validate first, replace second: a bad draft must not destroy a good design.json."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f".{out_path.name}.tmp.json")      # same directory, so os.replace is atomic
    tmp.write_text(json.dumps(draft.recipe, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        load_design(tmp)           # fails loudly if the draft is not a valid design
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, out_path)
    return out_path


def style_frame_plan(draft: Draft, log, out_dir, script_lines=None, duration=6.0) -> Path:
    clips = sorted((c for c in (log or {}).get("clips", []) if c.get("path")),
                   key=lambda c: -(c.get("luma") or 0))[:2]
    if not clips:
        raise DesignGenError("style frames need at least one logged clip with a path")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = script_lines or [["이 화면의 글자 크기와"], ["색이 ", {"hl": "잘 보이는지"}, " 확인해 주세요."]]
    half = round(duration / 2, 3)
    shots = [{"clip": clips[0]["path"], "in": 0, "out": half, "src_in": 1.0}]
    if len(clips) > 1:
        shots.append({"clip": clips[1]["path"], "in": half, "out": duration, "src_in": 1.0})
    else:
        shots[0]["out"] = duration
    plan = {"name": "STYLE_" + draft.id.upper().replace("-", "_"),
            "format": {"width": 3840, "height": 2160, "fps": 23.976, "duration": duration},
            "shots": shots, "voices": [], "graphics": [
                {"type": "caption", "voice": None, "lines": lines, "in": 0.3, "out": half + 0.2},
                {"type": "lower-third", "at": 0.8, "dur": half, "name": "이름 예시", "role": "역할 예시"},
                {"type": "end-card", "in": half + 0.3, "title": "제목 예시", "year": 2027,
                 "tagline": "한 줄 설명이 들어갑니다",
                 "rows": [{"label": "안내", "values": ["첫째 줄", "둘째 줄"]}]}],
            "fade_out": 0.5}
    path = out_dir / "edit.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
