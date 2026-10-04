"""Text must not cover the people: Apple Vision finds faces, bodies and text in a still.

Boxes are (x, y, w, h), normalised to 0–1 with a top-left origin.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .videoqa import Finding

ASPECT_TOLERANCE = 0.02
SAME_BOX = 0.5

SCRIPT = Path(__file__).with_name("vision_detect.swift")
COVER_LIMIT = 0.15


def intersection(a, b) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def covered_fraction(person, text_boxes) -> float:
    """Share of `person` under text; lines rarely overlap each other, so their areas add."""
    area = person[2] * person[3]
    if area <= 0:
        return 0.0
    return min(1.0, sum(intersection(person, t) for t in text_boxes) / area)


def covered_people(detection: dict, limit: float = COVER_LIMIT) -> list:
    """Each face or body in `detection` that text covers by more than `limit`."""
    texts = detection.get("text") or []
    hits = []
    for kind, key in (("face", "faces"), ("person", "humans")):
        for box in detection.get(key) or []:
            fraction = covered_fraction(box, [t["box"] for t in texts])
            if fraction > limit:
                words = [t.get("string", "") for t in texts if intersection(box, t["box"]) > 0]
                hits.append({"kind": kind, "box": box, "fraction": round(fraction, 3), "text": words})
    return hits


def vision_unavailable() -> str:
    """Why detection cannot run here, or "" when it can."""
    if sys.platform != "darwin":
        return "needs macOS (Apple Vision)"
    if not shutil.which("swift"):
        return "needs the Swift toolchain (`xcode-select --install`)"
    return ""


def detect(images: list, timeout: float = 600) -> list:
    """Run Vision over the images in one pass; one dict per image with faces, humans and text."""
    reason = vision_unavailable()
    if reason:
        raise RuntimeError(reason)
    result = subprocess.run(["swift", str(SCRIPT)] + [str(p) for p in images],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-2:]
        raise RuntimeError("Vision detection failed: " + " / ".join(tail))
    return json.loads(result.stdout)


def cover_findings(detections: list, limit: float = COVER_LIMIT) -> list:
    findings = []
    for d in detections:
        name = Path(d["path"]).name
        check = f"text-over-people:{name}"
        if d.get("error"):
            findings.append(Finding(check, "skip", f"could not read the image: {d['error'][:120]}"))
            continue
        hits = covered_people(d, limit)
        if hits:
            parts = [f"{h['fraction']:.0%} of a {h['kind']}" + (f" by \"{' / '.join(h['text'])[:60]}\""
                                                                  if h["text"] else "") for h in hits]
            findings.append(Finding(check, "warn", "text covers " + "; ".join(parts)))
        else:
            people = len(d.get("faces") or []) + len(d.get("humans") or [])
            findings.append(Finding(check, "ok", f"{people} face/person box(es), "
                                                 f"{len(d.get('text') or [])} text line(s), none covered"))
    return findings


def iou(a, b) -> float:
    inter = intersection(a, b)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def with_clean_people(render: dict, clean: dict) -> dict:
    """Text from the render, people from both: Vision often loses a person once text sits on them."""
    if not clean or clean.get("error"):
        return render
    merged = dict(render)
    for key in ("faces", "humans"):
        boxes = list(render.get(key) or [])
        boxes += [c for c in clean.get(key) or [] if all(iou(c, b) < SAME_BOX for b in boxes)]
        merged[key] = boxes
    return merged


def text_over_people(images: list, limit: float = COVER_LIMIT, clean: list = None) -> list:
    """Findings for any stills: warn where text covers more than `limit` of a face or person.

    `clean`, when given, lines up with `images`: the same frame without graphics (or None).
    """
    images = [Path(p) for p in images]
    if not images:
        return []
    clean = list(clean or [None] * len(images))
    extra = [Path(c) for c in clean if c]
    try:
        found = detect(images + extra)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return [Finding("text-over-people", "skip", f"skipped — {e}")]
    renders, plates = found[:len(images)], iter(found[len(images):])
    merged = [with_clean_people(r, next(plates) if c else None) for r, c in zip(renders, clean)]
    return cover_findings(merged, limit)


def clean_plates(plan, design, times: list, outdir, width: int = 1280) -> list:
    """For each time, a frame of the source shot under it, or None where graphics hide the footage
    or the shot is reframed (zoom, push, other aspect) so its boxes would not line up."""
    from .lint import _resolved, cover_span, plan_voices
    from .media import MediaError, extract_frame, probe
    covers = []
    for g, tr, a, b in _resolved(plan, design, plan_voices(plan)):
        span = cover_span(g, tr, a, b)
        if span:
            covers.append(span)
    frame_aspect = plan.format.width / plan.format.height
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    plates = []
    for t in times:
        shot = next((s for s in reversed(plan.shots) if s.start <= t < s.end), None)
        hidden = any(a <= t < b for a, b in covers)
        if shot is None or hidden or shot.zoom != 1 or shot.motion:
            plates.append(None)
            continue
        try:
            info = probe(shot.clip)
            if not info.height or abs(info.width / info.height - frame_aspect) > ASPECT_TOLERANCE * frame_aspect:
                plates.append(None)
                continue
            out = outdir / f"clean-{float(t):07.2f}.jpg"
            plates.append(extract_frame(shot.clip, shot.src_in + (t - shot.start), out, width=width))
        except (MediaError, OSError, RuntimeError):
            plates.append(None)
    return plates
