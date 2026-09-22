"""Font catalogue: what is installed, which pairings suit a mood, and licences to pass on."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CATALOGUE = Path(__file__).resolve().parents[2] / "designs" / "fonts.json"
FONT_DIRS = (Path("~/Library/Fonts").expanduser(), Path("/Library/Fonts"), Path("/System/Library/Fonts"))
STYLES = ("sans", "serif", "hand", "display")
SCRIPTS = ("ko", "latin", "ja")
ROLE_WEIGHTS = {"headline": ("extrabold", "bold", "semibold"), "emphasis": ("bold", "semibold", "medium"),
                "body": ("medium", "regular", "light"), "label": ("bold", "semibold", "medium"),
                "quote": ("semibold", "regular", "medium"), "scripture": ("light", "regular", "medium")}
QUOTE_ROLES = ("quote", "scripture")


class FontError(ValueError):
    pass


@dataclass
class Font:
    id: str
    family: str
    postscript: dict
    scripts: list
    style: str
    moods: list = field(default_factory=list)
    licence: str = ""
    url: str = ""
    files: list = field(default_factory=list)

    def weight(self, preferences) -> str:
        for want in preferences:
            if want in self.postscript:
                return self.postscript[want]
        return sorted(self.postscript.values())[0]


def load_catalogue(path=CATALOGUE) -> list:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise FontError(f"cannot read {path}: {e}") from e
    errors, catalogue, seen = [], [], set()
    for i, entry in enumerate(raw if isinstance(raw, list) else []):
        where = f"fonts[{i}]"
        fid = entry.get("id")
        if not isinstance(fid, str) or not fid:
            errors.append(f"{where}: 'id' is required")
        elif fid in seen:
            errors.append(f"{where}: duplicate id '{fid}'")
        seen.add(fid)
        if not isinstance(entry.get("postscript"), dict) or not entry["postscript"]:
            errors.append(f"{where}: 'postscript' must map weight names to PostScript names")
        bad_scripts = [s for s in entry.get("scripts", []) if s not in SCRIPTS]
        if not entry.get("scripts") or bad_scripts:
            errors.append(f"{where}: 'scripts' must be a non-empty subset of {SCRIPTS}")
        if entry.get("style") not in STYLES:
            errors.append(f"{where}: 'style' must be one of {STYLES}")
        if not entry.get("licence"):
            errors.append(f"{where}: 'licence' is required (it travels with the font)")
        if not entry.get("url"):
            errors.append(f"{where}: 'url' is required")
        files = entry.get("files", [])
        if not isinstance(files, list) or not all(isinstance(x, str) for x in files):
            errors.append(f"{where}: 'files' must be a list of font file stems when present")
            files = []
        catalogue.append(Font(id=fid, family=entry.get("family", fid), postscript=entry.get("postscript", {}),
                              scripts=list(entry.get("scripts", [])), style=entry.get("style", ""),
                              moods=list(entry.get("moods", [])), licence=entry.get("licence", ""),
                              url=entry.get("url", ""), files=list(files)))
    if errors:
        raise FontError(f"{path}:\n  " + "\n  ".join(errors))
    return catalogue


def font_dirs() -> tuple:
    """FONT_DIRS, or the os.pathsep-separated folders in AESTUDIO_FONT_DIRS."""
    override = os.environ.get("AESTUDIO_FONT_DIRS")
    return tuple(Path(d).expanduser() for d in override.split(os.pathsep) if d) if override else FONT_DIRS


def installed_files(dirs=None) -> set:
    stems = set()
    for directory in font_dirs() if dirs is None else dirs:
        try:
            for f in Path(directory).iterdir():
                if f.is_file() and f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    stems.add(f.stem.lower())
        except OSError:
            continue
    return stems


def is_installed(font: Font, files=None, dirs=None) -> bool:
    files = installed_files(dirs) if files is None else files
    stems = font.files if font.files else list(font.postscript.values())
    return bool(stems) and all(stem.lower() in files for stem in stems)


def _score(font: Font, moods) -> int:
    return len(set(m.lower() for m in moods) & set(m.lower() for m in font.moods))


def pairings(moods, scripts=("ko",), catalogue=None, installed_only=True, dirs=None) -> list:
    catalogue = catalogue or load_catalogue()
    files = installed_files(dirs)
    usable = [f for f in catalogue if set(scripts) <= set(f.scripts)]
    if installed_only:
        usable = [f for f in usable if is_installed(f, files)]
    if not usable:
        raise FontError("no catalogue font covers " + ", ".join(scripts)
                        + (" and is installed" if installed_only else ""))
    ranked = sorted(usable, key=lambda f: (-_score(f, moods), f.family))
    out = []
    for headline in ranked:
        body = next((f for f in ranked if f.style != headline.style), None) or headline
        quote = next((f for f in ranked if f.style == "serif"), body)
        pair = {"headline": headline, "body": body, "quote": quote, "notes": []}
        pair["installed"] = all(is_installed(f, files) for f in (headline, body, quote))
        seen_ids = set()
        for font in (headline, body, quote):
            if font.id in seen_ids:
                continue
            seen_ids.add(font.id)
            if not is_installed(font, files):
                pair["notes"].append(f"install {font.family} first: {font.licence} — {font.url}")
        if not any(p["headline"].id == headline.id and p["body"].id == body.id for p in out):
            out.append(pair)
        if len(out) == 3:
            break
    return out


def fonts_for(pairing, weights) -> dict:
    roles = {}
    for role in weights:
        font = pairing["quote"] if role in QUOTE_ROLES else (
            pairing["headline"] if role in ("headline", "label") else pairing["body"])
        roles[role] = font.weight(ROLE_WEIGHTS.get(role, ("regular",)))
    return roles
