"""Load and validate a per-video edit plan (plan/edit.json)."""
import json
from dataclasses import dataclass, field
from pathlib import Path

GRAPHIC_TYPES = ("title-page", "opening", "backdrop", "scrapbook", "caption", "quote", "lower-third", "end-card", "inset", "layout")


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
    # Optional slow push, anchored on a point in the source rather than its centre.
    # {"from": 1.02, "to": 1.10, "cx": 0.52, "cy": 0.43}
    # cx/cy are 0..1 in source space - put a face there and the subject stays put
    # while the frame moves, instead of drifting out of shot.
    motion: dict | None = None
    # seconds of cross-dissolve INTO this shot. 0 (the default) is a clean cut.
    # Dissolving every join makes a cut feel mushy; dissolves should be motivated.
    dissolve: float | None = None
    # dB for this clip's OWN sound. None leaves the shot silent under the music,
    # which is what a still wants; a moving shot with people talking wants to be heard.
    gain_db: float | None = None
    # "width" fits the picture to the frame's WIDTH instead of covering the frame.
    # A 16:9 clip shown full-bleed in a 9:16 frame keeps 42% of its width, which
    # throws away most of a group; fitting the width keeps all of it and bands the
    # rest of the frame. None (the default) covers, which is right for 16:9.
    fit: str | None = None


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
    # Extra [start, end] spans to duck under. A shot's own audio registers itself,
    # but sound carried by a GRAPHIC - a clip inside a layout panel - is invisible
    # to the compiler, so the plan names those spans here or the bed never dips.
    spans: list = field(default_factory=list)


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
    width = c.num(f, "width", "format", 3840, 1)
    height = c.num(f, "height", "format", 2160, 1)
    fps = c.num(f, "fps", "format", 23.976, 0.001)
    duration = c.num(f, "duration", "format")
    fmt = Format(int(width), int(height), fps, duration)
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
        ft = s.get("fit")
        if ft is not None:
            if ft not in ("width",):
                c.errors.append(f"{where}: 'fit' must be 'width'")
            else:
                shot.fit = ft
        gv = s.get("gain_db")
        if gv is not None:
            if not isinstance(gv, (int, float)) or isinstance(gv, bool):
                c.errors.append(f"{where}: 'gain_db' must be a number")
            else:
                shot.gain_db = float(gv)
        dv = s.get("dissolve")
        if dv is not None:
            if not isinstance(dv,(int,float)) or isinstance(dv,bool) or dv < 0:
                c.errors.append(f"{where}: 'dissolve' must be a number >= 0")
            else:
                shot.dissolve = float(dv)
        m = s.get("motion")
        if m is not None:
            if not isinstance(m, dict):
                c.errors.append(f"{where}: 'motion' must be an object")
            else:
                for k in ("from", "to"):
                    if not isinstance(m.get(k), (int, float)) or isinstance(m.get(k), bool):
                        c.errors.append(f"{where}.motion: '{k}' must be a number")
                for k in ("cx", "cy"):
                    v = m.get(k, 0.5)
                    if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0.0 <= v <= 1.0:
                        c.errors.append(f"{where}.motion: '{k}' must be between 0 and 1")
                shot.motion = dict(m)
        if shot.end <= shot.start:
            c.errors.append(f"{where}: out must be greater than in")
        shots.append(shot)

    sfx = [Sfx(c.path(s, "file", f"sfx[{i}]"), c.num(s, "at", f"sfx[{i}]"), c.num(s, "gain_db", f"sfx[{i}]", 0.0, None),
               bool(s.get("fade_before_voice", False))) for i, s in enumerate(data.get("sfx", []))]

    m = data.get("music")
    music = None
    if m is not None:
        music = Music(c.path(m, "file", "music"), c.num(m, "gain_db", "music", 0.0, None), c.num(m, "start", "music", 0.0),
                      dict(m.get("duck", {})), [tuple(sp) for sp in m.get("spans", [])])

    graphics = []
    for i, g in enumerate(data.get("graphics", [])):
        where = f"graphics[{i}]"
        g = json.loads(json.dumps(g))
        gtype = g.get("type")
        if gtype not in GRAPHIC_TYPES:
            c.errors.append(f"{where}: unknown type '{gtype}' (expected one of {', '.join(GRAPHIC_TYPES)})")
        if gtype in ("caption", "quote"):
            voice = g.get("voice")
            if voice is None:
                if g.get("in") is None or g.get("out") is None:
                    c.errors.append(f"{where}: a caption without a voice needs 'in' and 'out'")
            elif voice not in seen:
                c.errors.append(f"{where}: unknown voice '{voice}'")
        # Any graphic may carry a backing photo - end cards, and title pages that
        # set their type over footage - so resolve it wherever it appears.
        if isinstance(g.get("photo"), dict):
            p = c.path(g["photo"], "clip", where + ".photo")
            g["photo"]["clip"] = str(p) if p else None
        for j, ph in enumerate(g.get("photos") or []):
            if isinstance(ph, dict):
                p = c.path(ph, "clip", f"{where}.photos[{j}]")
                ph["clip"] = str(p) if p else None
        # any graphic may carry a logo, not only an end card
        if isinstance(g.get("logo"), dict):
            p = c.path(g["logo"], "file", where + ".logo")
            g["logo"]["file"] = str(p) if p else None
        if gtype == "layout":
            if g.get("in") is None or g.get("out") is None:
                c.errors.append(f"{where}: a layout needs 'in' and 'out'")
            panels = g.get("panels")
            # One panel is a legitimate layout: a single framed band over the bed,
            # which is how a 16:9 clip keeps a whole line of people inside a 9:16
            # frame instead of being cropped to a third of them.
            if not isinstance(panels, list) or len(panels) < 1:
                c.errors.append(f"{where}: 'panels' must be a non-empty list")
            else:
                for j, pn in enumerate(panels):
                    if not isinstance(pn, dict):
                        c.errors.append(f"{where}.panels[{j}]: must be an object"); continue
                    q = c.path(pn, "clip", f"{where}.panels[{j}]")
                    pn["clip"] = str(q) if q else None
                    for k in ("sw", "sh"):
                        if not isinstance(pn.get(k), (int, float)) or pn.get(k, 0) <= 0:
                            c.errors.append(f"{where}.panels[{j}]: '{k}' (source pixel size) is required")
        if gtype == "inset":
            if g.get("in") is None or g.get("out") is None:
                c.errors.append(f"{where}: an inset needs 'in' and 'out'")
            items = g.get("items")
            if not isinstance(items, list) or not items:
                c.errors.append(f"{where}: 'items' must be a non-empty list")
            else:
                for j, it in enumerate(items):
                    if not isinstance(it, dict):
                        c.errors.append(f"{where}.items[{j}]: must be an object")
                        continue
                    p = c.path(it, "clip", f"{where}.items[{j}]")
                    it["clip"] = str(p) if p else None
        graphics.append(g)

    project = data.get("project")
    project = (path.parent / project).resolve() if project else None
    if c.errors:
        raise PlanError(f"{path}:\n  " + "\n  ".join(c.errors))
    return Plan(name, path.parent, fmt, voices, shots, sfx, music, graphics, dict(data.get("grade", {})),
                float(data.get("fade_out", 0.75)), project)
