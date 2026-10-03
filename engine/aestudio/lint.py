"""Timing lint over the resolved timeline: flash frames, text overlap, read time, text leaving before its voice."""
from dataclasses import asdict, dataclass

from .components.editorial import RAMP_IN
from .timing import TimingError, align_words, load_transcript, voice_times

MIN_FRAGMENT = 0.5
CJK_CHARS_PER_SEC = 14.0
LATIN_CHARS_PER_SEC = 17.0
FADE_OVERHEAD = 0.6
OVERLAP_TOLERANCE = 0.1
EPS = 1e-3

TEXT_TYPES = ("caption", "quote", "lower-third", "title-page")
OVERLAP_TYPES = ("caption", "quote", "lower-third")

# (lead before onset, tail after offset) a voice-linked caption gets from its treatment
CAPTION_PAD = {"line-fade": (0.4, 0.6), "paper-card": (0.3, 0.5), "editorial": (0.35, 0.55)}

# where a treatment draws its text when the plan gives no "place"; FIXED ignores "place"
DEFAULT_PLACE = {("caption", "line-fade"): "lower-center", ("quote", "line-fade"): "lower-center",
                 ("caption", "paper-card"): "bottom-left", ("quote", "paper-card"): "top-right"}
FIXED_PLACE = {("caption", "editorial"): "bottom-left", ("quote", "editorial"): "bottom-left",
               ("lower-third", "rule-wipe"): "bottom-left", ("lower-third", "paper-tab"): "center-left"}


@dataclass
class Finding:
    kind: str
    start: float
    end: float
    message: str

    def __str__(self):
        return f"[{self.kind}] {self.start:.2f}-{self.end:.2f}s: {self.message}"

    def to_dict(self):
        return asdict(self)


def plan_voices(plan) -> dict:
    return {v.id: voice_times(v, load_transcript(v.transcript)) for v in plan.voices}


def _treatment(design, gtype):
    try:
        return design.treatment(gtype)[0]
    except KeyError:
        return None


def graphic_times(g, treatment, voices, duration):
    """(in, out) of a plan graphic as its treatment resolves them."""
    t = g.get("type")
    if t == "lower-third":
        return float(g["at"]), float(g["at"]) + float(g.get("dur", 4.25))
    if t == "end-card":
        return float(g["in"]), duration
    if t == "backdrop":
        return float(g.get("in", 0)), float(g.get("out", duration))
    vt = voices.get(g.get("voice")) if g.get("voice") else None
    lead, tail = CAPTION_PAD.get(treatment, (0.4, 0.6))
    t_in = float(g["in"]) if g.get("in") is not None else vt.onset - lead
    t_out = float(g["out"]) if g.get("out") is not None else vt.offset + tail
    return t_in, t_out


def cover_span(g, treatment, t_in, t_out):
    """The span over which a graphic fully hides the footage beneath it, or None."""
    if "opaque" in g:
        return (t_in, t_out) if g["opaque"] else None
    t = g.get("type")
    last = max([float(p.get("delay", 0.0)) for p in g.get("panels") or []] or [0.0])
    if t == "layout":
        if treatment == "notebook" and not g.get("page", True):
            return None
        return (t_in + last + (0.35 if treatment == "notebook" else RAMP_IN), t_out)
    if t == "title-page":
        return (t_in, t_out) if treatment in ("black-frame", "notebook-page") or g.get("photo") else None
    if t == "opening":
        return (t_in, t_out) if treatment in ("notebook", "postcard") or g.get("photo") else None
    if t == "end-card":
        if treatment == "notebook-page":
            return (t_in + 0.75, t_out)
        return (t_in + 0.8, t_out) if g.get("photo") else None
    if t == "backdrop":
        return (t_in, t_out)
    return None


def _subtract(span, holes):
    out = [span]
    for h0, h1 in holes:
        nxt = []
        for a, b in out:
            if h1 <= a or h0 >= b:
                nxt.append((a, b))
                continue
            if h0 > a:
                nxt.append((a, h0))
            if h1 < b:
                nxt.append((h1, b))
        out = nxt
    return [(a, b) for a, b in out if b - a > EPS]


def _overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _resolved(plan, design, voices):
    out = []
    for g in plan.graphics:
        tr = _treatment(design, g.get("type"))
        try:
            t_in, t_out = graphic_times(g, tr, voices, plan.format.duration)
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
        out.append((g, tr, t_in, t_out))
    return out


def flash_frames(plan, design, voices, min_fragment=MIN_FRAGMENT):
    f = plan.format
    default_dis = float(plan.grade.get("dissolve", 0.0) or 0.0)
    dis = [s.dissolve if s.dissolve is not None else default_dis for s in plan.shots]
    layers = []
    for i, s in enumerate(plan.shots):
        end = min(s.end + dis[i + 1], f.duration) if i + 1 < len(plan.shots) and dis[i + 1] > 0 else s.end
        head = dis[i] if i > 0 else 0.0
        layers.append((s.start, end, head))
    covers = [c for g, tr, a, b in _resolved(plan, design, voices) if (c := cover_span(g, tr, a, b)) and c[1] > c[0]]
    findings = []
    for i, (start, end, head) in enumerate(layers):
        above = [(layers[j][0] + layers[j][2], layers[j][1]) for j in range(i + 1, len(layers))
                 if plan.shots[j].fit != "width"]
        # the dissolves into this shot and out of it are expected to show it only partly
        blends = [(start, start + head)]
        if i + 1 < len(layers):
            blends.append((layers[i + 1][0], layers[i + 1][0] + layers[i + 1][2]))
        for a, b in _subtract((start, end), above + covers):
            solid = (b - a) - sum(_overlap((a, b), x) for x in blends)
            if EPS < solid < min_fragment:
                findings.append(Finding("flash", round(a, 3), round(b, 3),
                                        f"shot {i + 1} ({plan.shots[i].clip.name}) is visible for only "
                                        f"{solid:.2f}s - extend the cover or trim the shot"))
    return findings


def _place(g, gtype, tr):
    return FIXED_PLACE.get((gtype, tr)) or g.get("place") or DEFAULT_PLACE.get((gtype, tr), "lower-center")


def _region(place):
    vert = "center" if place == "center" else ("top" if place.startswith("top") else
                                               "center" if place.startswith("center") else "bottom")
    horiz = "center" if place.endswith("center") else place.split("-")[1]
    return vert, horiz


def _label(g, i):
    return f"graphics[{i}] {g.get('type')}"


def text_overlap(plan, design, voices):
    items = [(i, g, tr, a, b) for i, (g, tr, a, b) in enumerate(_resolved(plan, design, voices))
             if g.get("type") in OVERLAP_TYPES]
    findings = []
    for x, (i, g, tr, a, b) in enumerate(items):
        ra = _region(_place(g, g["type"], tr))
        for j, h, tr2, c, d in items[x + 1:]:
            if _overlap((a, b), (c, d)) <= OVERLAP_TOLERANCE:
                continue
            rb = _region(_place(h, h["type"], tr2))
            if ra[0] == rb[0] and (ra[1] == rb[1] or "center" in (ra[1], rb[1])):
                findings.append(Finding("overlap", round(max(a, c), 3), round(min(b, d), 3),
                                        f"{_label(g, i)} and {_label(h, j)} share the {ra[0]} of the frame"))
    return findings


def _segments(line):
    for seg in line:
        yield seg["hl"] if isinstance(seg, dict) else str(seg)


def graphic_text(g) -> str:
    if g.get("type") == "lower-third":
        return " ".join(str(g.get(k, "")) for k in ("name", "role"))
    parts = ["".join(_segments(line)) for line in g.get("lines") or []]
    if g.get("ref"):
        parts.append(str(g["ref"]))
    return " ".join(parts)


def _cjk(ch):
    o = ord(ch)
    return (0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F
            or 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF)


def read_seconds(text) -> float:
    chars = [c for c in text if not c.isspace()]
    cjk = sum(1 for c in chars if _cjk(c))
    return cjk / CJK_CHARS_PER_SEC + (len(chars) - cjk) / LATIN_CHARS_PER_SEC + FADE_OVERHEAD


def read_time(plan, design, voices):
    findings = []
    for i, (g, tr, a, b) in enumerate(_resolved(plan, design, voices)):
        if g.get("type") not in TEXT_TYPES:
            continue
        need = read_seconds(graphic_text(g))
        if b - a < need:
            findings.append(Finding("read-time", round(a, 3), round(b, 3),
                                    f"{_label(g, i)} is on screen {b - a:.2f}s but needs about {need:.2f}s to read"))
    return findings


def _spoken_end(g, vt):
    words = graphic_text(g).split()
    try:
        last = align_words(words, vt.words)[-1]
    except (TimingError, IndexError):
        return vt.offset
    return next((e for _, s, e in vt.words if e >= last), vt.offset)


def text_before_voice(plan, design, voices):
    findings = []
    for i, (g, tr, a, b) in enumerate(_resolved(plan, design, voices)):
        vt = voices.get(g.get("voice")) if g.get("voice") else None
        if vt is None or g.get("out") is None:
            continue
        spoken = _spoken_end(g, vt)
        if b < spoken - EPS:
            findings.append(Finding("leaves-early", round(b, 3), round(spoken, 3),
                                    f"{_label(g, i)} leaves at {b:.2f}s but voice '{vt.id}' speaks it until {spoken:.2f}s"))
    return findings


def lint(plan, design, voices=None, min_fragment=MIN_FRAGMENT) -> list:
    voices = plan_voices(plan) if voices is None else voices
    findings = (flash_frames(plan, design, voices, min_fragment) + text_overlap(plan, design, voices)
                + read_time(plan, design, voices) + text_before_voice(plan, design, voices))
    return sorted(findings, key=lambda x: (x.start, x.kind))
