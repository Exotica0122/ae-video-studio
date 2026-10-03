"""Text must not cover the people: Apple Vision finds faces, bodies and text in a still.

Boxes are (x, y, w, h), normalised to 0–1 with a top-left origin.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .videoqa import Finding

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


def text_over_people(images: list, limit: float = COVER_LIMIT) -> list:
    """Findings for any stills: warn where text covers more than `limit` of a face or person."""
    images = [Path(p) for p in images]
    if not images:
        return []
    try:
        return cover_findings(detect(images), limit)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return [Finding("text-over-people", "skip", f"skipped — {e}")]
