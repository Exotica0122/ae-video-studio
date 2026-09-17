"""Load and validate a per-video edit plan (plan/edit.json)."""
import json
from dataclasses import dataclass, field
from pathlib import Path

GRAPHIC_TYPES = ("title-page", "caption", "quote", "lower-third", "end-card")


class PlanError(ValueError):
    pass


@dataclass
class Format:
    width: int = 3840
    height: int = 2160
    fps: float = 23.976
    duration: float = 0.0


@dataclass
class Voice:
    id: str
    file: Path
    at: float
    transcript: Path
    gain_db: float = 0.0
    src_in: float = 0.0
    src_out: float | None = None


@dataclass
class Shot:
    clip: Path
    start: float
    end: float
    src_in: float = 0.0
    exposure: float = 0.0
    zoom: float = 1.0


@dataclass
class Sfx:
    file: Path
    at: float
    gain_db: float = 0.0
    fade_before_voice: bool = False


@dataclass
class Music:
    file: Path
    gain_db: float = 0.0
    start: float = 0.0
    duck: dict = field(default_factory=dict)


@dataclass
class Plan:
    name: str
    root: Path
    format: Format
    voices: list
    shots: list
    sfx: list
    music: Music | None
    graphics: list
    grade: dict
    fade_out: float
    project: Path | None


class _Checker:
    def __init__(self, root: Path, check_files: bool):
        self.root, self.check_files, self.errors = root, check_files, []

    def num(self, obj, key, where, default=None, minimum=0.0):
        value = obj.get(key, default)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            self.errors.append(f"{where}: '{key}' must be a number")
            return 0.0
        if minimum is not None and value < minimum:
            self.errors.append(f"{where}: '{key}' must be >= {minimum}")
        return float(value)

    def path(self, obj, key, where, required=True):
        value = obj.get(key)
        if value is None:
            if required:
                self.errors.append(f"{where}: '{key}' is required")
            return None
        p = Path(value).expanduser()
        p = (p if p.is_absolute() else self.root / p).resolve()
        if self.check_files and not p.exists():
            self.errors.append(f"{where}: file not found: {p}")
        return p


def load_plan(path, check_files: bool = True) -> Plan:
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PlanError(f"cannot read {path}: {e}") from e
    c = _Checker(path.parent, check_files)

    name = data.get("name")
    if not isinstance(name, str) or not name:
        c.errors.append("'name' must be a non-empty string")
    f = data.get("format", {})
    fmt = Format(int(f.get("width", 3840)), int(f.get("height", 2160)), float(f.get("fps", 23.976)),
                 c.num(f, "duration", "format"))
    if fmt.duration <= 0:
        c.errors.append("format: 'duration' must be > 0")

    voices, seen = [], set()
    for i, v in enumerate(data.get("voices", [])):
        where = f"voices[{i}]"
        vid = v.get("id")
        if not isinstance(vid, str) or not vid:
            c.errors.append(f"{where}: 'id' is required")
        elif vid in seen:
            c.errors.append(f"{where}: duplicate voice id '{vid}'")
        seen.add(vid)
        src_out = v.get("src_out")
        voices.append(Voice(vid, c.path(v, "file", where), c.num(v, "at", where), c.path(v, "transcript", where),
                            c.num(v, "gain_db", where, 0.0, None), c.num(v, "src_in", where, 0.0),
                            None if src_out is None else c.num(v, "src_out", where)))

    shots = []
    for i, s in enumerate(data.get("shots", [])):
        where = f"shots[{i}]"
        shot = Shot(c.path(s, "clip", where), c.num(s, "in", where), c.num(s, "out", where),
                    c.num(s, "src_in", where, 0.0), c.num(s, "exposure", where, 0.0, None), c.num(s, "zoom", where, 1.0))
        if shot.end <= shot.start:
            c.errors.append(f"{where}: out must be greater than in")
        shots.append(shot)

    sfx = [Sfx(c.path(s, "file", f"sfx[{i}]"), c.num(s, "at", f"sfx[{i}]"), c.num(s, "gain_db", f"sfx[{i}]", 0.0, None),
               bool(s.get("fade_before_voice", False))) for i, s in enumerate(data.get("sfx", []))]

    m = data.get("music")
    music = None
    if m is not None:
        music = Music(c.path(m, "file", "music"), c.num(m, "gain_db", "music", 0.0, None), c.num(m, "start", "music", 0.0),
                      dict(m.get("duck", {})))

    graphics = []
    for i, g in enumerate(data.get("graphics", [])):
        where = f"graphics[{i}]"
        g = json.loads(json.dumps(g))
        gtype = g.get("type")
        if gtype not in GRAPHIC_TYPES:
            c.errors.append(f"{where}: unknown type '{gtype}' (expected one of {', '.join(GRAPHIC_TYPES)})")
        if gtype in ("caption", "quote") and g.get("voice") not in seen:
            c.errors.append(f"{where}: unknown voice '{g.get('voice')}'")
        if gtype == "end-card":
            if isinstance(g.get("photo"), dict):
                p = c.path(g["photo"], "clip", where + ".photo")
                g["photo"]["clip"] = str(p) if p else None
            if isinstance(g.get("logo"), dict):
                p = c.path(g["logo"], "file", where + ".logo")
                g["logo"]["file"] = str(p) if p else None
        graphics.append(g)

    project = data.get("project")
    project = (path.parent / project).resolve() if project else None
    if c.errors:
        raise PlanError(f"{path}:\n  " + "\n  ".join(c.errors))
    return Plan(name, path.parent, fmt, voices, shots, sfx, music, graphics, dict(data.get("grade", {})),
                float(data.get("fade_out", 0.75)), project)
