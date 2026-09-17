# Milestone 1 — Build Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an `edit.json` plus a design recipe into a built After Effects comp (footage, voices, ducked music, SFX, motion graphics) through the MCP bridge, and render it with `aerender`, with two deliberately different designs (`notebook`, `cinematic-minimal`) proving the engine is design-agnostic.

**Architecture:** A pure-Python compiler (`engine/aestudio`) validates the plan, resolves all timing (word alignment, ducking) and asks design *treatments* to emit a flat list of **ops** (plain dicts). The ops are embedded in a generated `.jsx` that loads a small ExtendScript **runtime** (`engine/jsx/runtime.jsx`), which executes each op against the AE DOM. All logic that can be tested lives in Python; the runtime only creates layers, sets values and expressions. A bridge client submits the script to the MCP Bridge Auto panel and waits for the JSON report.

**Tech Stack:** Python 3.10+ standard library only (tests with `unittest`), ExtendScript (ES3) for the runtime, After Effects 2025+ with the MCP Bridge Auto panel (`runJsx` patch in `bridge/runJsx.patch`), `aerender`, ffmpeg (demo media only), Node (optional, syntax check of the runtime).

**Spec:** `docs/design.md` (sections 3, 4, 6, 7 and 8).

## Global Constraints

- Python: standard library only; target 3.10+; run tests from `engine/` with `python3 -m unittest discover -s tests -t . -v`.
- ExtendScript runtime is ES3: no `JSON`, no `Array.prototype.forEach/map`, no `String.prototype.trim`, access `in` via `o["in"]`.
- Default format 3840×2160 @ 23.976 fps. Every pixel constant in treatments is authored for 4K and multiplied by `ctx.s = width / 3840`.
- No video-specific text, timings, names or assets anywhere in `engine/` or `designs/`. Demo content in `examples/demo/` is fictional.
- Bridge jobs are strictly sequential: never submit while `ae_command.json` status is `pending` or `running`.
- The runtime must never "Save As" over a different open project: if a project path is given and a different project is open, the build fails with an explanatory error.
- Final/long renders use `aerender` with After Effects closed; scripted `renderQueue.render()` is not used by this milestone.
- Layer ids are also AE layer names and must be unique; expressions reference layers only as `thisComp.layer("ID")` with ids that were emitted earlier in the op list.
- Bridge folder: `~/.ae-mcp-bridge` (override with env `AESTUDIO_BRIDGE_DIR`). Jobs: `jsx/<jobId>.jsx`, command `ae_command.json` `{command:"runJsx", args:{file, jobId}, timestamp, status:"pending"}`, result `ae_mcp_result.json` `{status, jobId, result}`.

## File Structure

```
engine/
  aestudio/
    __init__.py            version
    util.py                js() literal, hex_rgb(), r3()
    plan.py                edit.json loading + validation (Plan dataclasses)
    timing.py              transcripts, absolute voice times, caption↔transcript word alignment
    audio.py               music ducking keys, long-SFX fade keys
    design.py              design recipe loading + validation (Design)
    ops.py                 Ops builder + static validator
    context.py             Context passed to treatments
    jsx.py                 emit_script(), still_script()
    bridge.py              Bridge client for the MCP Bridge Auto panel
    compiler.py            compile_plan(): media + graphics dispatch
    render.py              aerender wrapper
    __main__.py            CLI: validate | compile | run | build | still | render
    components/
      __init__.py          REGISTRY + register()
      layout.py            segments, word times, text blocks, highlighter, paper card, placement
      notebook.py          paper-card, paper-tab, notebook-page (title), notebook-page (end card)
      cinematic.py         line-fade, rule-wipe, black-frame, centered-stack
  jsx/runtime.jsx          ExtendScript op executor (AES.build)
  tests/                   unittest suites (+ tests/ae/ live After Effects smoke test)
designs/notebook/design.json
designs/cinematic-minimal/design.json
docs/components.md         component contracts (fields, defaults, timing)
examples/demo/             make_media.py, edit.json (fictional)
skills/ae-build-render/SKILL.md
```

---

### Task 1: Engine scaffold and literal helpers

**Files:**
- Create: `engine/aestudio/__init__.py`, `engine/aestudio/util.py`
- Create: `engine/tests/__init__.py`, `engine/tests/test_util.py`

**Interfaces:**
- Produces: `js(value) -> str` (compact JSON, ASCII-escaped, valid ES3 literal); `hex_rgb(hex: str) -> list[float]` (0–1, 5 dp; raises `ValueError`); `r3(x) -> float` (round to 3 dp).

- [ ] **Step 1: Write the failing test**

`engine/tests/__init__.py` is empty. `engine/tests/test_util.py`:

```python
import unittest

from aestudio.util import hex_rgb, js, r3


class UtilTest(unittest.TestCase):
    def test_js_escapes_non_ascii_and_is_compact(self):
        self.assertEqual(js({"t": "가 “x”", "n": [1, 2.5]}), '{"t":"\\uac00 \\u201cx\\u201d","n":[1,2.5]}')

    def test_hex_rgb(self):
        self.assertEqual(hex_rgb("#FFD84D"), [1.0, 0.84706, 0.30196])
        self.assertEqual(hex_rgb("22304a"), [0.13333, 0.18824, 0.2902])

    def test_hex_rgb_rejects_bad_input(self):
        for bad in ("#FFF", "#GG0000", ""):
            with self.assertRaises(ValueError):
                hex_rgb(bad)

    def test_r3(self):
        self.assertEqual(r3(1.23456), 1.235)
        self.assertEqual(r3(2), 2.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest discover -s tests -t . -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'aestudio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/__init__.py`:

```python
"""ae-video-studio build engine."""

__version__ = "0.1.0"
```

`engine/aestudio/util.py`:

```python
"""Small helpers shared by the compiler and treatments."""
import json


def js(value) -> str:
    """Compact JSON that ExtendScript (ES3) accepts as a JavaScript literal; non-ASCII is escaped."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def hex_rgb(value: str) -> list[float]:
    """'#RRGGBB' -> [r, g, b] in 0..1, as After Effects colour properties expect."""
    h = value.lstrip("#") if isinstance(value, str) else ""
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"bad colour {value!r}; expected #RRGGBB")
    return [round(int(h[i:i + 2], 16) / 255, 5) for i in (0, 2, 4)]


def r3(x) -> float:
    return round(float(x), 3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest discover -s tests -t . -v`
Expected: 4 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine
git commit -m "feat(engine): scaffold aestudio package with literal and colour helpers"
```

---

### Task 2: Edit plan loading and validation

**Files:**
- Create: `engine/aestudio/plan.py`
- Test: `engine/tests/test_plan.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class PlanError(ValueError)`
  - dataclasses `Format(width:int, height:int, fps:float, duration:float)`, `Voice(id, file:Path, at:float, transcript:Path, gain_db:float, src_in:float, src_out:float|None)`, `Shot(clip:Path, start:float, end:float, src_in:float, exposure:float, zoom:float)`, `Sfx(file:Path, at:float, gain_db:float, fade_before_voice:bool)`, `Music(file:Path, gain_db:float, start:float, duck:dict)`, `Plan(name, root:Path, format:Format, voices:list[Voice], shots:list[Shot], sfx:list[Sfx], music:Music|None, graphics:list[dict], grade:dict, fade_out:float, project:Path|None)`
  - `GRAPHIC_TYPES = ("title-page", "caption", "quote", "lower-third", "end-card")`
  - `load_plan(path, check_files=True) -> Plan`. Relative paths resolve against the edit.json folder. Graphic dicts are kept as-is except `end-card.photo.clip` and `end-card.logo.file`, which are resolved to absolute path strings.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_plan.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio.plan import PlanError, load_plan


def write_plan(root: Path, plan: dict, files=("media/a.mp4", "media/n1.wav", "t/n1.json", "media/m.wav")) -> Path:
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    path = root / "edit.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return path


def base_plan() -> dict:
    return {
        "name": "DEMO",
        "format": {"width": 3840, "height": 2160, "fps": 23.976, "duration": 20},
        "voices": [{"id": "N1", "file": "media/n1.wav", "at": 2.0, "transcript": "t/n1.json"}],
        "music": {"file": "media/m.wav", "gain_db": -6},
        "shots": [{"clip": "media/a.mp4", "in": 0, "out": 20}],
        "graphics": [{"type": "caption", "voice": "N1", "lines": [["hello"]]}],
    }


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_loads_and_resolves_paths(self):
        plan = load_plan(write_plan(self.root, base_plan()))
        self.assertEqual(plan.name, "DEMO")
        self.assertEqual(plan.format.duration, 20.0)
        self.assertEqual(plan.shots[0].clip, (self.root / "media/a.mp4").resolve())
        self.assertEqual(plan.shots[0].start, 0.0)
        self.assertEqual(plan.voices[0].transcript, (self.root / "t/n1.json").resolve())
        self.assertEqual(plan.music.gain_db, -6.0)
        self.assertEqual(plan.fade_out, 0.75)
        self.assertIsNone(plan.project)

    def test_rejects_unknown_voice_reference(self):
        p = base_plan()
        p["graphics"][0]["voice"] = "N9"
        with self.assertRaisesRegex(PlanError, "unknown voice 'N9'"):
            load_plan(write_plan(self.root, p))

    def test_rejects_shot_that_ends_before_it_starts(self):
        p = base_plan()
        p["shots"][0]["out"] = 0
        with self.assertRaisesRegex(PlanError, r"shots\[0\].*out must be greater than in"):
            load_plan(write_plan(self.root, p))

    def test_rejects_unknown_graphic_type(self):
        p = base_plan()
        p["graphics"].append({"type": "sparkles"})
        with self.assertRaisesRegex(PlanError, "unknown type 'sparkles'"):
            load_plan(write_plan(self.root, p))

    def test_reports_missing_files(self):
        path = write_plan(self.root, base_plan(), files=("t/n1.json",))
        with self.assertRaisesRegex(PlanError, "file not found"):
            load_plan(path)
        self.assertEqual(load_plan(path, check_files=False).name, "DEMO")

    def test_end_card_paths_are_resolved(self):
        p = base_plan()
        p["graphics"].append({"type": "end-card", "in": 15, "title": "T", "photo": {"clip": "media/a.mp4"}})
        plan = load_plan(write_plan(self.root, p))
        self.assertEqual(plan.graphics[1]["photo"]["clip"], str((self.root / "media/a.mp4").resolve()))

    def test_duplicate_voice_ids(self):
        p = base_plan()
        p["voices"].append(dict(p["voices"][0]))
        with self.assertRaisesRegex(PlanError, "duplicate voice id 'N1'"):
            load_plan(write_plan(self.root, p))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_plan -v`
Expected: ERROR `ModuleNotFoundError: No module named 'aestudio.plan'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/plan.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_plan -v`
Expected: 7 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/plan.py engine/tests/test_plan.py
git commit -m "feat(engine): load and validate edit plans"
```

---

### Task 3: Transcripts, voice times and caption word alignment

**Files:**
- Create: `engine/aestudio/timing.py`
- Test: `engine/tests/test_timing.py`

**Interfaces:**
- Consumes: `Voice` from Task 2.
- Produces:
  - `class TimingError(ValueError)`
  - `Transcript(onset: float, offset: float, words: list[tuple[str, float, float]])` — transcript JSON is `{"onset": s, "offset": s, "words": [[word, start, end], ...]}`, times relative to the audio file; `onset`/`offset` default to first/last word.
  - `VoiceTimes(id: str, onset: float, offset: float, words: list[tuple[str, float, float]])` — absolute timeline times.
  - `load_transcript(path) -> Transcript`
  - `voice_times(voice: Voice, tr: Transcript) -> VoiceTimes` — shift = `voice.at - voice.src_in`; words outside `[src_in, src_out]` are dropped; onset/offset come from the transcript when the voice is untrimmed, otherwise from the first/last kept word.
  - `align_words(caption_words: list[str], words) -> list[float]` — start time of each caption word, found by matching letters (ignoring spaces and punctuation) forward through the transcript; a caption word may start in the middle of a spoken word (Korean particles split across segments). Words with no letters (e.g. `“`) take the previous time.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_timing.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio.plan import Voice
from aestudio.timing import TimingError, Transcript, align_words, load_transcript, voice_times

WORDS = [["모든", 0.10, 0.50], ["여정은", 0.50, 1.10], ["작은", 1.20, 1.60], ["한", 1.60, 1.80],
         ["걸음에서", 1.80, 2.60], ["시작됩니다.", 2.60, 3.50]]


class TimingTest(unittest.TestCase):
    def test_load_transcript_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps({"words": WORDS}), encoding="utf-8")
            tr = load_transcript(p)
        self.assertEqual((tr.onset, tr.offset), (0.10, 3.50))
        self.assertEqual(tr.words[1], ("여정은", 0.50, 1.10))

    def test_voice_times_shift(self):
        tr = Transcript(0.08, 3.52, [tuple(w) for w in WORDS])
        vt = voice_times(Voice("N1", Path("a.wav"), 10.0, Path("t.json")), tr)
        self.assertEqual((vt.onset, vt.offset), (10.08, 13.52))
        self.assertEqual(vt.words[0], ("모든", 10.1, 10.5))

    def test_voice_times_trimmed_range(self):
        tr = Transcript(0.08, 3.52, [tuple(w) for w in WORDS])
        v = Voice("I1", Path("a.mov"), 20.0, Path("t.json"), src_in=1.2, src_out=2.6)
        vt = voice_times(v, tr)
        self.assertEqual([w[0] for w in vt.words], ["작은", "한", "걸음에서"])
        self.assertEqual((vt.onset, vt.offset), (20.0, 21.4))

    def test_align_splits_inside_a_spoken_word(self):
        words = [tuple(w) for w in WORDS]
        times = align_words(["모든", "여정은", "작은", "한", "걸음", "에서", "시작됩니다."], words)
        self.assertEqual(times[:5], [0.1, 0.5, 1.2, 1.6, 1.8])
        self.assertAlmostEqual(times[5], 2.2)   # "에서" starts half-way through "걸음에서"
        self.assertEqual(times[6], 2.6)

    def test_align_skips_words_not_in_caption_and_punctuation(self):
        words = [tuple(w) for w in WORDS]
        self.assertEqual(align_words(["“", "작은", "걸음에서”"], words), [0.1, 1.2, 1.8])

    def test_align_raises_when_text_is_missing(self):
        with self.assertRaisesRegex(TimingError, "'바다' not found"):
            align_words(["모든", "바다"], [tuple(w) for w in WORDS])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_timing -v`
Expected: ERROR `No module named 'aestudio.timing'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/timing.py`:

```python
"""Transcript timing: absolute voice times and caption-to-speech word alignment."""
import json
from dataclasses import dataclass
from pathlib import Path

_SKIP = set(" \t\r\n.,!?;:'\"“”‘’()[]{}…·-–—~")


class TimingError(ValueError):
    pass


@dataclass
class Transcript:
    onset: float
    offset: float
    words: list


@dataclass
class VoiceTimes:
    id: str
    onset: float
    offset: float
    words: list


def load_transcript(path) -> Transcript:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        words = [(str(w), float(s), float(e)) for w, s, e in data["words"]]
    except (OSError, KeyError, ValueError, TypeError) as e:
        raise TimingError(f"bad transcript {path}: {e}") from e
    if not words:
        raise TimingError(f"transcript {path} has no words")
    return Transcript(float(data.get("onset", words[0][1])), float(data.get("offset", words[-1][2])), words)


def voice_times(voice, tr: Transcript) -> VoiceTimes:
    shift = voice.at - voice.src_in
    end = voice.src_out if voice.src_out is not None else float("inf")
    kept = [(w, round(s + shift, 3), round(e + shift, 3)) for w, s, e in tr.words
            if s >= voice.src_in - 1e-6 and e <= end + 1e-6]
    if not kept:
        raise TimingError(f"voice {voice.id}: no transcript words inside src_in/src_out")
    if voice.src_in == 0 and voice.src_out is None:
        onset, offset = round(tr.onset + shift, 3), round(tr.offset + shift, 3)
    else:
        onset, offset = kept[0][1], kept[-1][2]
    return VoiceTimes(voice.id, onset, offset, kept)


def _letters(text: str) -> list[str]:
    return [ch.lower() for ch in text if ch not in _SKIP]


def _clock(words) -> list[tuple[str, float]]:
    out = []
    for w, s, e in words:
        letters = _letters(w)
        for i, ch in enumerate(letters):
            out.append((ch, s + (e - s) * i / len(letters)))
    return out


def align_words(caption_words: list[str], words) -> list[float]:
    clock = _clock(words)
    if not clock:
        raise TimingError("transcript has no letters to align against")
    pos, times = 0, []
    for cw in caption_words:
        letters = _letters(cw)
        if not letters:
            times.append(times[-1] if times else round(clock[0][1], 3))
            continue
        j = pos
        while j + len(letters) <= len(clock) and [c for c, _ in clock[j:j + len(letters)]] != letters:
            j += 1
        if j + len(letters) > len(clock):
            raise TimingError(f"caption word '{cw}' not found in the transcript after letter {pos}")
        times.append(round(clock[j][1], 3))
        pos = j + len(letters)
    return times
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_timing -v`
Expected: 6 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/timing.py engine/tests/test_timing.py
git commit -m "feat(engine): voice timing and caption word alignment"
```

---

### Task 4: Music ducking and long-SFX fades

**Files:**
- Create: `engine/aestudio/audio.py`
- Test: `engine/tests/test_audio.py`

**Interfaces:**
- Produces:
  - `duck_keys(voices: list[tuple[float, float]], duration: float, *, base=0.0, under_voice=-12.0, breath=-9.0, swell=-4.0, tail=-2.0, lead=0.25, ramp=1.0, fade_in=1.2, fade_out=1.2, floor=-40.0) -> list[list[float]]` — sorted `[time, dB]` keys (3 dp) for the music Audio Levels. Rules (docs/design.md §8): fully down `lead` s before every onset after a `ramp` s ramp; gaps < 0.8 s stay down; gaps < 2 s lift to `breath` at the midpoint; longer gaps swell to `swell`; after the last voice rise to `tail`; fade in from/out to `floor`.
  - `sfx_fade_keys(at: float, gain_db: float, onsets: list[float]) -> list[list[float]] | None` — for a long SFX, hold `gain_db` until 1.0 s before the next voice onset after `at + 1.0`, reaching `gain_db - 17` 0.1 s before it; `None` when no such onset.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_audio.py` (voice times below are a real, previously approved mix; the expected keys were verified by ear):

```python
import unittest

from aestudio.audio import duck_keys, sfx_fade_keys

VOICES = [(8.4, 12.526), (13.646, 19.303), (20.353, 24.236), (24.736, 30.191), (31.191, 37.615),
          (40.515, 47.651), (48.651, 56.918), (57.918, 63.319), (63.819, 69.893), (70.893, 77.799)]
EXPECTED = [[0, -40], [1.2, 5], [7.15, 5], [8.15, -8], [12.646, -8], [13.086, -5], [13.396, -8], [19.423, -8],
            [19.828, -5], [20.103, -8], [30.311, -8], [30.691, -5], [30.941, -8], [37.765, -8], [38.415, -1],
            [39.615, -1], [40.265, -8], [47.771, -8], [48.151, -5], [48.401, -8], [57.038, -8], [57.418, -5],
            [57.668, -8], [70.013, -8], [70.393, -5], [70.643, -8], [77.949, -8], [78.849, 2], [86.899, 2],
            [88.049, -40]]


class AudioTest(unittest.TestCase):
    def test_duck_keys_match_approved_mix(self):
        keys = duck_keys(VOICES, 88.099, base=5, under_voice=-8, breath=-5, swell=-1, tail=2)
        self.assertEqual(keys, EXPECTED)

    def test_no_voices_is_a_plain_fade(self):
        self.assertEqual(duck_keys([], 10.0, base=-3), [[0, -40], [1.2, -3], [8.8, -3], [9.95, -40]])

    def test_voices_are_sorted(self):
        self.assertEqual(duck_keys(list(reversed(VOICES)), 88.099, base=5, under_voice=-8, breath=-5, swell=-1, tail=2),
                         EXPECTED)

    def test_sfx_fade_before_next_voice(self):
        self.assertEqual(sfx_fade_keys(37.965, -7, [31.191, 40.515, 48.651]), [[39.515, -7], [40.415, -24]])

    def test_sfx_fade_none_without_later_voice(self):
        self.assertIsNone(sfx_fade_keys(50.0, -7, [10.0, 50.5]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_audio -v`
Expected: ERROR `No module named 'aestudio.audio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/audio.py`:

```python
"""Music ducking keyed from voice onsets/offsets, and fades for long SFX (docs/design.md §8)."""


def _num(x):
    x = round(float(x), 3)
    return int(x) if x == int(x) else x


def duck_keys(voices, duration, *, base=0.0, under_voice=-12.0, breath=-9.0, swell=-4.0, tail=-2.0,
              lead=0.25, ramp=1.0, fade_in=1.2, fade_out=1.2, floor=-40.0):
    voices = sorted(voices)
    keys = [(0, floor), (fade_in, base)]
    if voices:
        first_on = voices[0][0]
        keys += [(first_on - lead - ramp, base), (first_on - lead, under_voice)]
        for (_, off_a), (on_b, _) in zip(voices, voices[1:]):
            gap = on_b - off_a
            if gap < 0.8:
                continue
            if gap < 2.0:
                keys += [(off_a + 0.12, under_voice), ((off_a + on_b) / 2, breath), (on_b - lead, under_voice)]
            else:
                keys += [(off_a + 0.15, under_voice), (off_a + 0.8, swell), (on_b - 0.9, swell), (on_b - lead, under_voice)]
        last_off = voices[-1][1]
        keys += [(last_off + 0.15, under_voice), (last_off + 1.05, tail), (duration - fade_out, tail)]
    else:
        keys += [(duration - fade_out, base)]
    keys.append((duration - 0.05, floor))
    merged = {}
    for t, db in keys:
        merged[round(t, 3)] = db
    return [[_num(t), _num(db)] for t, db in sorted(merged.items())]


def sfx_fade_keys(at, gain_db, onsets):
    later = sorted(o for o in onsets if o > at + 1.0)
    if not later:
        return None
    on = later[0]
    return [[_num(on - 1.0), _num(gain_db)], [_num(on - 0.1), _num(gain_db - 17)]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_audio -v`
Expected: 5 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/audio.py engine/tests/test_audio.py
git commit -m "feat(engine): voice-keyed music ducking and long SFX fades"
```

---
### Task 5: Design recipes and loader

**Files:**
- Create: `engine/aestudio/design.py`
- Create: `designs/notebook/design.json`, `designs/cinematic-minimal/design.json`
- Test: `engine/tests/test_design.py`

**Interfaces:**
- Produces:
  - `class DesignError(ValueError)`
  - `ROLES = ("headline", "body", "emphasis", "quote", "label", "scripture")`, `COMPONENTS = ("caption", "quote", "lower-third", "title-page", "end-card")`, `PALETTE_KEYS = ("paper", "ink", "accent", "accent2", "rule", "shade")`
  - `DESIGNS_DIR: Path` (repo `designs/`)
  - `Design(id, name, palette: dict[str, list[float]], type: dict[str, dict], motion: dict, texture: dict, components: dict[str, dict], path: Path)` with methods `font(role) -> str`, `size(role) -> float` (4K px), `color(name) -> list[float]`, `treatment(component) -> tuple[str, dict]` (treatment name, remaining options), `fonts() -> set[str]`
  - `load_design(ref) -> Design` where `ref` is a design id under `DESIGNS_DIR`, a folder containing `design.json`, or a path to a `.json` file. `motion` defaults: `{"in": 0.6, "out": 0.45, "word": 0.35, "rise": 14}`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_design.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio.design import COMPONENTS, DesignError, load_design


class DesignTest(unittest.TestCase):
    def test_builtin_designs_load(self):
        for ref in ("notebook", "cinematic-minimal"):
            d = load_design(ref)
            self.assertEqual(d.id, ref)
            self.assertEqual(set(d.components), set(COMPONENTS))
            self.assertEqual(len(d.color("ink")), 3)
            self.assertGreater(d.size("headline"), 0)

    def test_designs_are_actually_different(self):
        a, b = load_design("notebook"), load_design("cinematic-minimal")
        self.assertNotEqual(a.fonts(), b.fonts())
        self.assertNotEqual(a.color("paper"), b.color("paper"))
        self.assertNotEqual({c: a.treatment(c)[0] for c in COMPONENTS}, {c: b.treatment(c)[0] for c in COMPONENTS})

    def test_treatment_returns_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads((Path(__file__).resolve().parents[2] / "designs/notebook/design.json").read_text(encoding="utf-8"))
            raw["components"]["caption"] = {"treatment": "paper-card", "tilt": 2}
            p = Path(tmp) / "d.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(load_design(p).treatment("caption"), ("paper-card", {"tilt": 2}))

    def test_rejects_missing_role_and_bad_colour(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads((Path(__file__).resolve().parents[2] / "designs/notebook/design.json").read_text(encoding="utf-8"))
            del raw["tokens"]["type"]["label"]
            raw["tokens"]["palette"]["ink"] = "navy"
            p = Path(tmp) / "d.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(DesignError) as cm:
                load_design(p)
            self.assertIn("type role 'label'", str(cm.exception))
            self.assertIn("palette 'ink'", str(cm.exception))

    def test_unknown_design_id(self):
        with self.assertRaisesRegex(DesignError, "design not found"):
            load_design("does-not-exist")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_design -v`
Expected: ERROR `No module named 'aestudio.design'`

- [ ] **Step 3: Write the design recipes and loader**

`designs/notebook/design.json`:

```json
{
  "id": "notebook",
  "name": "Paper Notebook",
  "mood": ["warm", "hand-made", "hopeful"],
  "tokens": {
    "palette": {"paper": "#FBF7EF", "ink": "#22304A", "accent": "#FFD84D", "accent2": "#EE7860", "rule": "#DCD3C3", "shade": "#101418"},
    "type": {
      "headline": {"font": "Paperlogy-8ExtraBold", "size": 150},
      "body": {"font": "Paperlogy-5Medium", "size": 100},
      "emphasis": {"font": "Paperlogy-7Bold", "size": 118},
      "quote": {"font": "Paperlogy-6SemiBold", "size": 92},
      "label": {"font": "Paperlogy-7Bold", "size": 64},
      "scripture": {"font": "MaruBuri-Bold", "size": 128}
    },
    "motion": {"in": 0.6, "out": 0.45, "word": 0.35, "rise": 14},
    "texture": {"noise": 4}
  },
  "components": {
    "caption": {"treatment": "paper-card"},
    "quote": {"treatment": "paper-card"},
    "lower-third": {"treatment": "paper-tab"},
    "title-page": {"treatment": "notebook-page"},
    "end-card": {"treatment": "notebook-page"}
  },
  "grade_hint": "warm-airy",
  "sfx_hint": ["paper-slide", "page-turn", "marker"]
}
```

`designs/cinematic-minimal/design.json`:

```json
{
  "id": "cinematic-minimal",
  "name": "Cinematic Minimal",
  "mood": ["restrained", "emotional", "premium"],
  "tokens": {
    "palette": {"paper": "#0E0F12", "ink": "#F4F1EA", "accent": "#C9A46A", "accent2": "#8FA3B8", "rule": "#3A3D44", "shade": "#0E0F12"},
    "type": {
      "headline": {"font": "MaruBuri-SemiBold", "size": 150},
      "body": {"font": "NanumSquareNeoTTF-bRg", "size": 84},
      "emphasis": {"font": "NanumSquareNeoTTF-cBd", "size": 84},
      "quote": {"font": "MaruBuri-Light", "size": 92},
      "label": {"font": "NanumSquareNeoTTF-cBd", "size": 52},
      "scripture": {"font": "MaruBuri-Light", "size": 120}
    },
    "motion": {"in": 0.8, "out": 0.6, "word": 0.6, "rise": 0},
    "texture": {"noise": 0}
  },
  "components": {
    "caption": {"treatment": "line-fade"},
    "quote": {"treatment": "line-fade"},
    "lower-third": {"treatment": "rule-wipe"},
    "title-page": {"treatment": "black-frame"},
    "end-card": {"treatment": "centered-stack"}
  },
  "grade_hint": "soft-contrast-warm",
  "sfx_hint": ["low-whoosh", "soft-hit"]
}
```

`engine/aestudio/design.py`:

```python
"""Design recipes: tokens plus one treatment per component (docs/design.md §7)."""
import json
from dataclasses import dataclass
from pathlib import Path

from .util import hex_rgb

ROLES = ("headline", "body", "emphasis", "quote", "label", "scripture")
COMPONENTS = ("caption", "quote", "lower-third", "title-page", "end-card")
PALETTE_KEYS = ("paper", "ink", "accent", "accent2", "rule", "shade")
DESIGNS_DIR = Path(__file__).resolve().parents[2] / "designs"
MOTION_DEFAULTS = {"in": 0.6, "out": 0.45, "word": 0.35, "rise": 14}


class DesignError(ValueError):
    pass


@dataclass
class Design:
    id: str
    name: str
    palette: dict
    type: dict
    motion: dict
    texture: dict
    components: dict
    path: Path

    def font(self, role: str) -> str:
        return self.type[role]["font"]

    def size(self, role: str) -> float:
        return float(self.type[role]["size"])

    def color(self, name: str) -> list:
        return list(self.palette[name])

    def treatment(self, component: str) -> tuple:
        opts = dict(self.components[component])
        return opts.pop("treatment"), opts

    def fonts(self) -> set:
        return {spec["font"] for spec in self.type.values()}


def _resolve(ref) -> Path:
    p = Path(ref).expanduser()
    if p.suffix == ".json" and p.is_file():
        return p
    if (p / "design.json").is_file():
        return p / "design.json"
    if (DESIGNS_DIR / str(ref) / "design.json").is_file():
        return DESIGNS_DIR / str(ref) / "design.json"
    raise DesignError(f"design not found: {ref} (looked for a .json file, <dir>/design.json and {DESIGNS_DIR}/<id>/design.json)")


def load_design(ref) -> Design:
    path = _resolve(ref).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DesignError(f"cannot read {path}: {e}") from e
    errors = []
    tokens = raw.get("tokens", {})
    palette = {}
    for key in PALETTE_KEYS:
        try:
            palette[key] = hex_rgb(tokens.get("palette", {}).get(key))
        except ValueError:
            errors.append(f"palette '{key}' must be a #RRGGBB colour")
    types = tokens.get("type", {})
    for role in ROLES:
        spec = types.get(role)
        if not isinstance(spec, dict) or not isinstance(spec.get("font"), str) or not isinstance(spec.get("size"), (int, float)):
            errors.append(f"type role '{role}' needs {{\"font\": PostScript name, \"size\": 4K px}}")
    components = raw.get("components", {})
    for comp in COMPONENTS:
        if not isinstance(components.get(comp), dict) or not isinstance(components[comp].get("treatment"), str):
            errors.append(f"component '{comp}' needs {{\"treatment\": name}}")
    if not isinstance(raw.get("id"), str):
        errors.append("'id' is required")
    if errors:
        raise DesignError(f"{path}:\n  " + "\n  ".join(errors))
    return Design(raw["id"], raw.get("name", raw["id"]), palette, types, {**MOTION_DEFAULTS, **tokens.get("motion", {})},
                  dict(tokens.get("texture", {})), components, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_design -v`
Expected: 5 tests OK

- [ ] **Step 5: Commit**

```bash
git add designs engine/aestudio/design.py engine/tests/test_design.py
git rm --cached designs/.gitkeep 2>/dev/null; rm -f designs/.gitkeep
git commit -m "feat(engine): design recipe loader with notebook and cinematic-minimal designs"
```

---

### Task 6: Ops builder and static validator

**Files:**
- Create: `engine/aestudio/ops.py`
- Test: `engine/tests/test_ops.py`

**Interfaces:**
- Produces:
  - `class OpsError(ValueError)`
  - `REQUIRED: dict[str, list[str]]` — required fields per op: `comp[name,width,height,fps,duration]`, `footage[id,file,start,end]`, `audio[id,file,start,end]`, `group[id]`, `rect[id,color]`, `text[id,text,font,size,color]`, `image[id,file]`, `solid[id,color]`, `rules[id,count,spacing,y0,color]`, `effect[layer,match]`, `order[layer,below]`, `expr[layer,exprs]`.
  - `class Ops`: `.items: list[dict]`; `uid(prefix) -> str` (`CAPTION_01`, `CAPTION_02`, …); `add(op: str, **fields) -> str | None` drops `None` fields, raises `OpsError` on a duplicate id, returns the id.
  - `validate_ops(items) -> None` — first op must be `comp`; required fields; unique ids; `parent`, `layer`, `below` and every `thisComp.layer("X")` inside expression strings (`expr` values, `rect_expr` values, `fade`, `exprs` values, effect prop `{"expr": ...}`) must reference an id defined by an **earlier** op.
- Op field vocabulary (the runtime in Task 7 reads exactly these):
  - common placement: `id, parent, anchor, position, scale, rotation, opacity, expr{anchor|position|scale|rotation|opacity: expression}, in, out`
  - `footage`/`audio`: `file, start, end, src_in, stretch, zoom, width, mask[w,h], lumetri{index: value}, gain_db, levels[[t, dB]]`
  - `group`: `fade` (expression for a Slider named FADE, 0–100)
  - `rect`: `color, size, center, roundness, rect_expr{size|center}`
  - `text`: `text, font, size, color, tracking, justify(left|center|right), reveal{times, dur, rise, blur, by(chars|words|lines)}`
  - `image`: `file, width, tint[r,g,b]`
  - `rules`: `count, spacing, y0, color, stroke, width, margin_x, margin_color`
  - `effect`: `layer, match, name, props{index-or-name: value | {"expr": expression}}`
  - `order`: `layer, below[ids]` (move `layer` directly under the lowest of `below`)
  - `expr`: `layer, exprs{transform key: expression}`

- [ ] **Step 1: Write the failing test**

`engine/tests/test_ops.py`:

```python
import unittest

from aestudio.ops import Ops, OpsError, validate_ops

COMP = dict(name="C", width=3840, height=2160, fps=23.976, duration=10)


class OpsTest(unittest.TestCase):
    def test_uid_and_add(self):
        ops = Ops()
        self.assertEqual(ops.uid("CAPTION"), "CAPTION_01")
        self.assertEqual(ops.uid("CAPTION"), "CAPTION_02")
        ops.add("comp", **COMP)
        self.assertEqual(ops.add("group", id="G", parent=None), "G")
        self.assertEqual(ops.items[1], {"op": "group", "id": "G"})

    def test_duplicate_id(self):
        ops = Ops()
        ops.add("group", id="G")
        with self.assertRaisesRegex(OpsError, "duplicate id 'G'"):
            ops.add("rect", id="G", color=[1, 1, 1])

    def test_valid_list_passes(self):
        ops = Ops()
        ops.add("comp", **COMP)
        ops.add("group", id="G", fade="100")
        ops.add("text", id="T", parent="G", text="a", font="F", size=10, color=[0, 0, 0],
                expr={"opacity": 'thisComp.layer("G").effect("FADE")(1)'})
        ops.add("rect", id="R", color=[1, 1, 1], rect_expr={"size": 'var L=thisComp.layer("T");[1,1]'})
        ops.add("effect", layer="R", match="ADBE Noise", props={"1": {"expr": 'thisComp.layer("T").index'}})
        ops.add("order", layer="R", below=["T"])
        ops.add("expr", layer="G", exprs={"position": 'thisComp.layer("R").index;value'})
        validate_ops(ops.items)

    def test_reference_must_be_defined_earlier(self):
        ops = Ops()
        ops.add("comp", **COMP)
        ops.add("text", id="T", text="a", font="F", size=10, color=[0, 0, 0], expr={"position": 'thisComp.layer("LATER").index'})
        ops.add("group", id="LATER")
        with self.assertRaisesRegex(OpsError, "op 1 .*'LATER'"):
            validate_ops(ops.items)

    def test_missing_fields_and_first_op(self):
        with self.assertRaisesRegex(OpsError, "first op must be 'comp'"):
            validate_ops([{"op": "group", "id": "G"}])
        with self.assertRaisesRegex(OpsError, "missing 'font'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "text", "id": "T", "text": "a", "size": 1, "color": [0, 0, 0]}])
        with self.assertRaisesRegex(OpsError, "unknown op 'sparkle'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "sparkle"}])

    def test_parent_and_below_refs(self):
        with self.assertRaisesRegex(OpsError, "parent 'NOPE'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "group", "id": "G", "parent": "NOPE"}])
        with self.assertRaisesRegex(OpsError, "below 'NOPE'"):
            validate_ops([{"op": "comp", **COMP}, {"op": "group", "id": "G"}, {"op": "order", "layer": "G", "below": ["NOPE"]}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_ops -v`
Expected: ERROR `No module named 'aestudio.ops'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/ops.py`:

```python
"""Ops: the flat instruction list the ExtendScript runtime executes (engine/jsx/runtime.jsx)."""
import re

REQUIRED = {
    "comp": ["name", "width", "height", "fps", "duration"],
    "footage": ["id", "file", "start", "end"],
    "audio": ["id", "file", "start", "end"],
    "group": ["id"],
    "rect": ["id", "color"],
    "text": ["id", "text", "font", "size", "color"],
    "image": ["id", "file"],
    "solid": ["id", "color"],
    "rules": ["id", "count", "spacing", "y0", "color"],
    "effect": ["layer", "match"],
    "order": ["layer", "below"],
    "expr": ["layer", "exprs"],
}
_LAYER_REF = re.compile(r'thisComp\.layer\("([^"]+)"\)')


class OpsError(ValueError):
    pass


class Ops:
    def __init__(self):
        self.items = []
        self._ids = set()
        self._counters = {}

    def uid(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}_{n:02d}"

    def add(self, op: str, **fields):
        item = {"op": op}
        item.update({k: v for k, v in fields.items() if v is not None})
        lid = item.get("id")
        if lid is not None:
            if lid in self._ids:
                raise OpsError(f"duplicate id '{lid}'")
            self._ids.add(lid)
        self.items.append(item)
        return lid


def _expressions(item):
    for key in ("expr", "rect_expr", "exprs"):
        for value in (item.get(key) or {}).values():
            yield value
    if "fade" in item:
        yield item["fade"]
    for value in (item.get("props") or {}).values():
        if isinstance(value, dict) and "expr" in value:
            yield value["expr"]


def validate_ops(items) -> None:
    if not items or items[0].get("op") != "comp":
        raise OpsError("first op must be 'comp'")
    defined = set()
    for i, item in enumerate(items):
        op = item.get("op")
        if op not in REQUIRED:
            raise OpsError(f"op {i}: unknown op '{op}'")
        for key in REQUIRED[op]:
            if key not in item:
                raise OpsError(f"op {i} ({op}): missing '{key}'")
        refs = [("parent", item.get("parent")), ("layer", item.get("layer"))]
        refs += [("below", b) for b in item.get("below", [])]
        refs += [("expression", r) for e in _expressions(item) for r in _LAYER_REF.findall(e)]
        for kind, ref in refs:
            if ref is not None and ref not in defined:
                raise OpsError(f"op {i} ({op} {item.get('id', '')}): {kind} '{ref}' is not defined by an earlier op")
        if "id" in item:
            if item["id"] in defined:
                raise OpsError(f"op {i}: duplicate id '{item['id']}'")
            defined.add(item["id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_ops -v`
Expected: 6 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/ops.py engine/tests/test_ops.py
git commit -m "feat(engine): ops builder and static reference validator"
```

---
### Task 7: ExtendScript runtime and script emitter

**Files:**
- Create: `engine/jsx/runtime.jsx`
- Create: `engine/aestudio/jsx.py`
- Test: `engine/tests/test_jsx.py`

**Interfaces:**
- Consumes: `validate_ops` (Task 6), `js` (Task 1).
- Produces:
  - `RUNTIME: Path` — absolute path of `engine/jsx/runtime.jsx`.
  - `emit_script(ops: list[dict], project: str | None = None, folder: str = "ae-video-studio", runtime: Path = RUNTIME) -> str` — validates, then returns a script whose last expression is `AES.build(spec, ops)`.
  - `still_script(comp: str, time: float, out_png: str) -> str` — saves one frame; returns `'{"ok":true}'` or `'{"ok":false,"error":"comp not found"}'`.
  - Runtime global `AES` with `build(spec, ops) -> string` (JSON report `{ok, comp, layers, expressionErrors[], missingFonts[], warnings[], saved?, error?, seconds}`), `toJSON(value)`, `EASE` (easing functions `c01, so, si, bo, eio` prepended to every expression).

- [ ] **Step 1: Write the failing test**

`engine/tests/test_jsx.py`:

```python
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aestudio.jsx import RUNTIME, emit_script, still_script
from aestudio.ops import OpsError

OPS = [{"op": "comp", "name": "DEMO", "width": 3840, "height": 2160, "fps": 23.976, "duration": 5},
       {"op": "text", "id": "T", "text": "가", "font": "F", "size": 10, "color": [0, 0, 0]}]


class JsxTest(unittest.TestCase):
    def test_emit_script_loads_runtime_and_builds(self):
        code = emit_script(OPS, project="/tmp/p.aep")
        lines = code.splitlines()
        self.assertTrue(lines[0].startswith("// generated by ae-video-studio"))
        self.assertIn(str(RUNTIME), lines[1])
        self.assertTrue(lines[1].startswith("$.evalFile(new File("))
        self.assertTrue(lines[2].startswith('AES.build({"folder":"ae-video-studio","project":"/tmp/p.aep"},[{"op":"comp"'))
        self.assertIn("\\uac00", lines[2])

    def test_emit_script_validates(self):
        with self.assertRaises(OpsError):
            emit_script([{"op": "group", "id": "G"}])

    def test_still_script(self):
        code = still_script("DEMO", 3.5, "/tmp/a.png")
        self.assertIn('it.name==="DEMO"', code)
        self.assertIn('c.saveFrameToPng(3.5,f)', code)
        self.assertIn('new File("/tmp/a.png")', code)

    def test_runtime_exists_and_defines_all_ops(self):
        src = RUNTIME.read_text(encoding="utf-8")
        from aestudio.ops import REQUIRED
        for op in REQUIRED:
            self.assertRegex(src, r"\n\s+%s: function \(o\)" % op, op)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_runtime_is_syntactically_valid(self):
        # node only checks .js files, so check a copy; ES3 ExtendScript is valid JavaScript syntax
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "runtime.js"
            copy.write_text(RUNTIME.read_text(encoding="utf-8"), encoding="utf-8")
            r = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_jsx -v`
Expected: ERROR `No module named 'aestudio.jsx'`

- [ ] **Step 3: Write the runtime**

`engine/jsx/runtime.jsx`:

```javascript
// ae-video-studio runtime: executes op lists produced by the Python compiler (engine/aestudio).
// ExtendScript is ES3: no JSON object, no Array.forEach/map, no String.trim.
var AES = (function () {
    var EASE = "function c01(x){return Math.min(Math.max(x,0),1);}" +
        "function so(x){x=c01(x);return 1-Math.pow(1-x,3);}" +
        "function si(x){x=c01(x);return x*x*x;}" +
        "function bo(x){x=c01(x);var s=1.3;return 1+(s+1)*Math.pow(x-1,3)+s*Math.pow(x-1,2);}" +
        "function eio(x){x=c01(x);return x<0.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;}";
    var TRANSFORM = {anchor: "ADBE Anchor Point", position: "ADBE Position", scale: "ADBE Scale",
        rotation: "ADBE Rotate Z", opacity: "ADBE Opacity"};
    var BASED_ON = {chars: 1, words: 3, lines: 4};
    var ctx = null;

    function toJSON(v) {
        if (v === null || v === undefined) { return "null"; }
        var t = typeof v, i, parts;
        if (t === "number") { return isFinite(v) ? String(v) : "null"; }
        if (t === "boolean") { return v ? "true" : "false"; }
        if (t === "string") {
            return '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")
                .replace(/\r/g, "\\r").replace(/\t/g, "\\t") + '"';
        }
        if (v instanceof Array) {
            parts = [];
            for (i = 0; i < v.length; i++) { parts.push(toJSON(v[i])); }
            return "[" + parts.join(",") + "]";
        }
        parts = [];
        for (var k in v) { if (v.hasOwnProperty(k)) { parts.push(toJSON(k) + ":" + toJSON(v[k])); } }
        return "{" + parts.join(",") + "}";
    }

    function findFolder(name, parent) {
        var root = parent || app.project.rootFolder;
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof FolderItem && it.name === name && it.parentFolder === root) { return it; }
        }
        var f = app.project.items.addFolder(name);
        f.parentFolder = root;
        return f;
    }

    function findComp(name) {
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof CompItem && it.name === name) { return it; }
        }
        return null;
    }

    function removeSolids(folder) {
        for (var i = app.project.numItems; i >= 1; i--) {
            var it = app.project.item(i);
            if (it instanceof FootageItem && it.parentFolder === folder && it.mainSource instanceof SolidSource) { it.remove(); }
        }
    }

    function imp(path) {
        var f = new File(path);
        if (!f.exists) { throw new Error("missing file: " + path); }
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof FootageItem && it.file && it.file.fsName === f.fsName) { return it; }
        }
        var item = app.project.importFile(new ImportOptions(f));
        item.parentFolder = ctx.folder;
        return item;
    }

    function L(id) {
        if (!ctx.layers.hasOwnProperty(id)) { throw new Error("unknown layer id: " + id); }
        return ctx.layers[id];
    }

    function tprop(layer, key) {
        if (!TRANSFORM.hasOwnProperty(key)) { throw new Error("unknown transform key: " + key); }
        return layer.property("ADBE Transform Group").property(TRANSFORM[key]);
    }

    function setExprs(layer, exprs) {
        if (!exprs) { return; }
        for (var k in exprs) { if (exprs.hasOwnProperty(k)) { tprop(layer, k).expression = EASE + exprs[k]; } }
    }

    // Name, parent, static transform, expressions and in/out. Parenting first: AE compensates the child
    // transform when a parent is set, so rotation/scale/position are reset explicitly afterwards.
    function place(layer, o) {
        layer.name = o.id;
        if (o.parent) {
            layer.parent = L(o.parent);
            tprop(layer, "rotation").setValue(0);
            tprop(layer, "scale").setValue([100, 100]);
            tprop(layer, "position").setValue([0, 0]);
        }
        if (o.anchor) { tprop(layer, "anchor").setValue(o.anchor); }
        if (o.position) { tprop(layer, "position").setValue(o.position); }
        if (o.scale) { tprop(layer, "scale").setValue(o.scale); }
        if (o.rotation !== undefined) { tprop(layer, "rotation").setValue(o.rotation); }
        if (o.opacity !== undefined) { tprop(layer, "opacity").setValue(o.opacity); }
        setExprs(layer, o.expr);
        if (o["in"] !== undefined) { layer.inPoint = o["in"]; }
        if (o.out !== undefined) { layer.outPoint = o.out; }
        ctx.layers[o.id] = layer;
        return layer;
    }

    function levels(layer, o) {
        var p = layer.property("ADBE Audio Group").property("ADBE Audio Levels");
        if (o.levels) {
            for (var i = 0; i < o.levels.length; i++) { p.setValueAtTime(o.levels[i][0], [o.levels[i][1], o.levels[i][1]]); }
        } else if (o.gain_db !== undefined) {
            p.setValue([o.gain_db, o.gain_db]);
        }
    }

    function lumetri(layer, values) {
        var lu = layer.property("ADBE Effect Parade").addProperty("ADBE Lumetri");
        for (var k in values) {
            if (values.hasOwnProperty(k)) {
                try { lu.property(parseInt(k, 10)).setValue(values[k]); } catch (e) { ctx.warnings.push(layer.name + " lumetri " + k + ": " + e); }
            }
        }
    }

    function mask(layer, item, size, scalePct) {
        var m = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
        var shp = new Shape();
        var hw = size[0] / 2 / (scalePct / 100), hh = size[1] / 2 / (scalePct / 100);
        var cx = item.width / 2, cy = item.height / 2;
        shp.vertices = [[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh], [cx - hw, cy + hh]];
        shp.closed = true;
        m.property("ADBE Mask Shape").setValue(shp);
    }

    function media(o, audioOnly) {
        var item = imp(o.file);
        var layer = ctx.comp.layers.add(item);
        place(layer, o);
        if (o.stretch) { layer.stretch = o.stretch; }
        var st = (o.stretch || 100) / 100;
        layer.startTime = o.start - (o.src_in || 0) * st;
        layer.inPoint = o.start;
        var end = o.end;
        if (item.duration > 0) { end = Math.min(end, layer.startTime + item.duration * st); }
        layer.outPoint = end;
        if (audioOnly) {
            if (item.hasVideo) { layer.enabled = false; }
        } else if (item.hasVideo) {
            var sc = o.width ? 100 * o.width / item.width :
                Math.max(ctx.comp.width / item.width, ctx.comp.height / item.height) * 100 * (o.zoom || 1);
            tprop(layer, "scale").setValue([sc, sc]);
            if (o.mask) { mask(layer, item, o.mask, sc); }
            if (o.lumetri) { lumetri(layer, o.lumetri); }
        }
        if (item.hasAudio) {
            layer.audioEnabled = !!audioOnly;
            if (audioOnly) { levels(layer, o); }
        }
        return layer;
    }

    function rectGroup(root, index) {
        root.addProperty("ADBE Vector Group");
        root.property(index).property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
        root.property(index).property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
        // re-fetch: adding properties invalidates earlier references
        var g = root.property(index).property("ADBE Vectors Group");
        return {rect: g.property(1), fill: g.property(2)};
    }

    function reveal(layer, rv) {
        var animators = layer.property("ADBE Text Properties").property("ADBE Text Animators");
        animators.addProperty("ADBE Text Animator");
        var an = animators.property(animators.numProperties);
        var ap = an.property("ADBE Text Animator Properties");
        ap.addProperty("ADBE Text Opacity").setValue(0);
        if (rv.rise) { ap.addProperty("ADBE Text Position 3D").setValue([0, rv.rise, 0]); }
        if (rv.blur) { ap.addProperty("ADBE Text Blur").setValue([rv.blur, rv.blur]); }
        an = animators.property(animators.numProperties);
        an.property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
        var sel = animators.property(animators.numProperties).property("ADBE Text Selectors").property(1);
        sel.property("ADBE Text Range Type2").setValue(BASED_ON[rv.by || "words"]);
        sel.property("ADBE Text Expressible Amount").expression = EASE + "var T=" + toJSON(rv.times) +
            ";var i=Math.min(textIndex-1,T.length-1);var k=so((time-T[i])/" + rv.dur + ");var a=100*(1-k);[a,a,a]";
    }

    var OPS = {
        comp: function (o) {
            var old = findComp(o.name);
            if (old) { old.remove(); }
            ctx.comp = app.project.items.addComp(o.name, o.width, o.height, 1, o.duration, o.fps);
            ctx.comp.parentFolder = ctx.folder;
            ctx.comp.motionBlur = true;
            ctx.comp.bgColor = o.bg || [0, 0, 0];
        },
        footage: function (o) { media(o, false); },
        audio: function (o) { media(o, true); },
        group: function (o) {
            var n = ctx.comp.layers.addNull(ctx.comp.duration);
            tprop(n, "anchor").setValue([0, 0]);
            tprop(n, "position").setValue([0, 0]);
            if (o.fade) {
                var fx = n.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
                fx.name = "FADE";
                n.property("ADBE Effect Parade").property("FADE").property(1).expression = EASE + o.fade;
            }
            place(n, o);
        },
        rect: function (o) {
            var s = ctx.comp.layers.addShape();
            var parts = rectGroup(s.property("ADBE Root Vectors Group"), 1);
            parts.fill.property("ADBE Vector Fill Color").setValue(o.color);
            if (o.size) { parts.rect.property("ADBE Vector Rect Size").setValue(o.size); }
            if (o.center) { parts.rect.property("ADBE Vector Rect Position").setValue(o.center); }
            if (o.roundness) { parts.rect.property("ADBE Vector Rect Roundness").setValue(o.roundness); }
            if (o.rect_expr && o.rect_expr.size) { parts.rect.property("ADBE Vector Rect Size").expression = EASE + o.rect_expr.size; }
            if (o.rect_expr && o.rect_expr.center) { parts.rect.property("ADBE Vector Rect Position").expression = EASE + o.rect_expr.center; }
            tprop(s, "position").setValue([0, 0]);
            place(s, o);
        },
        rules: function (o) {
            var s = ctx.comp.layers.addShape();
            var root = s.property("ADBE Root Vectors Group");
            var w = o.width || ctx.comp.width, stroke = o.stroke || 3, i, parts;
            for (i = 0; i < o.count; i++) {
                parts = rectGroup(root, i + 1);
                parts.rect.property("ADBE Vector Rect Size").setValue([w, stroke]);
                parts.rect.property("ADBE Vector Rect Position").setValue([w / 2, o.y0 + i * o.spacing]);
                parts.fill.property("ADBE Vector Fill Color").setValue(o.color);
            }
            if (o.margin_x) {
                parts = rectGroup(root, o.count + 1);
                parts.rect.property("ADBE Vector Rect Size").setValue([stroke, ctx.comp.height]);
                parts.rect.property("ADBE Vector Rect Position").setValue([o.margin_x, ctx.comp.height / 2]);
                parts.fill.property("ADBE Vector Fill Color").setValue(o.margin_color || o.color);
            }
            tprop(s, "position").setValue([0, 0]);
            place(s, o);
        },
        text: function (o) {
            var layer = ctx.comp.layers.addText(o.text);
            var st = layer.property("ADBE Text Properties").property("ADBE Text Document");
            var td = st.value;
            td.resetCharStyle();
            td.resetParagraphStyle();
            td.font = o.font;
            td.fontSize = o.size;
            td.applyFill = true;
            td.fillColor = o.color;
            td.applyStroke = false;
            td.tracking = o.tracking || 0;
            td.justification = o.justify === "center" ? ParagraphJustification.CENTER_JUSTIFY :
                (o.justify === "right" ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.LEFT_JUSTIFY);
            st.setValue(td);
            layer.motionBlur = true;
            place(layer, o);
            if (o.reveal) { reveal(layer, o.reveal); }
        },
        image: function (o) {
            var layer = ctx.comp.layers.add(imp(o.file));
            place(layer, o);
            if (o.width) {
                var sc = 100 * o.width / layer.source.width;
                tprop(layer, "scale").setValue([sc, sc]);
            }
            if (o.tint) { layer.property("ADBE Effect Parade").addProperty("ADBE Fill").property("Color").setValue(o.tint); }
        },
        solid: function (o) {
            var layer = ctx.comp.layers.addSolid(o.color, o.id, ctx.comp.width, ctx.comp.height, 1, ctx.comp.duration);
            layer.source.parentFolder = ctx.folder;
            place(layer, o);
        },
        effect: function (o) {
            var layer = L(o.layer);
            var fx = layer.property("ADBE Effect Parade").addProperty(o.match);
            if (o.name) { fx.name = o.name; }
            var props = o.props || {};
            for (var k in props) {
                if (props.hasOwnProperty(k)) {
                    var p = /^\d+$/.test(k) ? fx.property(parseInt(k, 10)) : fx.property(k);
                    var v = props[k];
                    if (v !== null && typeof v === "object" && !(v instanceof Array) && v.expr !== undefined) {
                        p.expression = EASE + v.expr;
                    } else {
                        p.setValue(v);
                    }
                }
            }
        },
        order: function (o) {
            var low = null;
            for (var i = 0; i < o.below.length; i++) {
                var c = L(o.below[i]);
                if (!low || c.index > low.index) { low = c; }
            }
            L(o.layer).moveAfter(low);
        },
        expr: function (o) { setExprs(L(o.layer), o.exprs); }
    };

    function checkExpressions(group, path, out) {
        for (var i = 1; i <= group.numProperties; i++) {
            var p;
            try { p = group.property(i); } catch (e) { continue; }
            if (!p) { continue; }
            if (p.propertyType === PropertyType.PROPERTY) {
                if (p.canSetExpression && p.expressionEnabled && p.expressionError) { out.push(path + "/" + p.name + ": " + p.expressionError); }
            } else {
                checkExpressions(p, path + "/" + p.name, out);
            }
        }
    }

    function missingFonts(ops) {
        var seen = {}, out = [];
        if (!app.fonts || !app.fonts.getFontsByPostScriptName) { return out; }
        for (var i = 0; i < ops.length; i++) {
            var f = ops[i].font;
            if (ops[i].op === "text" && !seen[f]) {
                seen[f] = true;
                try { if (app.fonts.getFontsByPostScriptName(f).length === 0) { out.push(f); } } catch (e) { /* older AE: skip */ }
            }
        }
        return out;
    }

    function build(spec, ops) {
        var t0 = new Date().getTime();
        var report = {ok: false};
        ctx = {comp: null, folder: null, layers: {}, warnings: []};
        try {
            if (spec.project && app.project.file && app.project.file.fsName !== new File(spec.project).fsName) {
                throw new Error("A different project is open (" + app.project.file.fsName + "). Open " +
                    spec.project + " or a new, unsaved project, then build again.");
            }
            report.missingFonts = missingFonts(ops);
            ctx.folder = findFolder(ops[0].name, findFolder(spec.folder, null));
            removeSolids(ctx.folder);
            for (var i = 0; i < ops.length; i++) {
                var o = ops[i];
                if (!OPS.hasOwnProperty(o.op)) { throw new Error("unknown op: " + o.op); }
                try { OPS[o.op](o); } catch (e) {
                    throw new Error("op " + i + " (" + o.op + (o.id ? " " + o.id : "") + "): " + e.toString());
                }
            }
            var errs = [];
            for (var j = 1; j <= ctx.comp.numLayers; j++) { checkExpressions(ctx.comp.layer(j), ctx.comp.layer(j).name, errs); }
            report.comp = ctx.comp.name;
            report.layers = ctx.comp.numLayers;
            report.expressionErrors = errs;
            report.warnings = ctx.warnings;
            if (spec.project) {
                app.beginSuppressDialogs();
                try {
                    if (app.project.file) { app.project.save(); } else { app.project.save(new File(spec.project)); }
                } finally { app.endSuppressDialogs(false); }
                report.saved = app.project.file.fsName;
            }
            report.ok = errs.length === 0 && report.missingFonts.length === 0;
        } catch (e) {
            report.error = e.toString();
        }
        report.seconds = (new Date().getTime() - t0) / 1000;
        return toJSON(report);
    }

    return {build: build, toJSON: toJSON, EASE: EASE};
})();
```

- [ ] **Step 4: Write the emitter**

`engine/aestudio/jsx.py`:

```python
"""Generate the ExtendScript that the MCP bridge panel evaluates."""
from pathlib import Path

from .ops import validate_ops
from .util import js

RUNTIME = Path(__file__).resolve().parents[1] / "jsx" / "runtime.jsx"


def emit_script(ops, project=None, folder="ae-video-studio", runtime=RUNTIME) -> str:
    validate_ops(ops)
    spec = {"folder": folder, "project": project}
    return "\n".join([
        "// generated by ae-video-studio; rebuild instead of editing",
        f"$.evalFile(new File({js(str(runtime))}));",
        f"AES.build({js(spec)},{js(ops)});",
    ])


def still_script(comp: str, time: float, out_png: str) -> str:
    return ("(function(){var c=null;for(var i=1;i<=app.project.numItems;i++){var it=app.project.item(i);"
            "if(it instanceof CompItem&&it.name===" + js(comp) + ")c=it;}"
            "if(!c){return '{\"ok\":false,\"error\":\"comp not found\"}';}"
            "var f=new File(" + js(out_png) + ");if(f.exists){f.remove();}"
            "c.saveFrameToPng(" + repr(float(time)) + ",f);return '{\"ok\":true}';})();")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd engine && python3 -m unittest tests.test_jsx -v`
Expected: 5 tests OK (the node test is skipped if Node is missing)

- [ ] **Step 6: Commit**

```bash
git add engine/jsx engine/aestudio/jsx.py engine/tests/test_jsx.py
git commit -m "feat(engine): ExtendScript op runtime and script emitter"
```

---
### Task 8: Bridge client

**Files:**
- Create: `engine/aestudio/bridge.py`
- Test: `engine/tests/test_bridge.py`

**Interfaces:**
- Produces:
  - `class BridgeError(RuntimeError)`, `class BridgeBusy(BridgeError)`, `class BridgeTimeout(BridgeError)`
  - `DEFAULT_ROOT = Path(os.environ.get("AESTUDIO_BRIDGE_DIR", "~/.ae-mcp-bridge")).expanduser()`
  - `class Bridge(root: Path = DEFAULT_ROOT, poll: float = 0.25)` with `status() -> str | None`, `submit(code: str) -> str` (job id; raises `BridgeBusy` when status is `pending`/`running`), `wait(job_id: str, timeout: float) -> object` (the panel's `result`; raises `BridgeError` on panel error or if another job replaced the command, `BridgeTimeout` on timeout), `run(code, timeout=600) -> object`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_bridge.py`:

```python
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aestudio.bridge import Bridge, BridgeBusy, BridgeError, BridgeTimeout


def fake_panel(root: Path, result, status="completed", delay=0.2):
    """Mimic the MCP Bridge Auto panel: pick up a pending runJsx command and write a result."""
    def work():
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                cmd = json.loads((root / "ae_command.json").read_text())
            except (OSError, ValueError):
                time.sleep(0.02)
                continue
            if cmd.get("status") == "pending":
                assert Path(cmd["args"]["file"]).parent == root / "jsx"
                cmd["status"] = "running"
                (root / "ae_command.json").write_text(json.dumps(cmd))
                time.sleep(delay)
                panel_status = "error" if status == "error" else "success"
                (root / "ae_mcp_result.json").write_text(json.dumps({"status": panel_status, "jobId": cmd["args"]["jobId"], "result": result}))
                cmd["status"] = status
                (root / "ae_command.json").write_text(json.dumps(cmd))
                return
            time.sleep(0.02)
    t = threading.Thread(target=work, daemon=True)
    t.start()
    return t


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bridge = Bridge(self.root, poll=0.02)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_returns_result_and_writes_job_file(self):
        fake_panel(self.root, {"ok": True, "layers": 3})
        self.assertEqual(self.bridge.run("1+1", timeout=3), {"ok": True, "layers": 3})
        cmd = json.loads((self.root / "ae_command.json").read_text())
        self.assertEqual(cmd["command"], "runJsx")
        self.assertEqual(Path(cmd["args"]["file"]).read_text(), "1+1")

    def test_busy_panel_is_refused(self):
        (self.root / "ae_command.json").write_text(json.dumps({"status": "running", "args": {"jobId": "x"}}))
        with self.assertRaises(BridgeBusy):
            self.bridge.submit("1")

    def test_panel_error_raises(self):
        fake_panel(self.root, None, status="error")
        with self.assertRaises(BridgeError):
            self.bridge.run("bad", timeout=3)

    def test_timeout(self):
        with self.assertRaisesRegex(BridgeTimeout, "still running"):
            self.bridge.run("slow", timeout=0.2)

    def test_replaced_command(self):
        job = self.bridge.submit("1")
        (self.root / "ae_command.json").write_text(json.dumps({"status": "pending", "args": {"jobId": "other"}}))
        with self.assertRaisesRegex(BridgeError, "replaced"):
            self.bridge.wait(job, timeout=1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_bridge -v`
Expected: ERROR `No module named 'aestudio.bridge'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/bridge.py`:

```python
"""Client for the After Effects MCP Bridge Auto panel (runJsx command, see bridge/runJsx.patch)."""
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("AESTUDIO_BRIDGE_DIR", "~/.ae-mcp-bridge")).expanduser()


class BridgeError(RuntimeError):
    pass


class BridgeBusy(BridgeError):
    pass


class BridgeTimeout(BridgeError):
    pass


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Bridge:
    def __init__(self, root: Path = DEFAULT_ROOT, poll: float = 0.25):
        self.root = Path(root)
        self.poll = poll

    @property
    def command_file(self) -> Path:
        return self.root / "ae_command.json"

    @property
    def result_file(self) -> Path:
        return self.root / "ae_mcp_result.json"

    def _command(self):
        try:
            return json.loads(self.command_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def status(self):
        cmd = self._command()
        return cmd.get("status") if cmd else None

    def submit(self, code: str) -> str:
        if self.status() in ("pending", "running"):
            raise BridgeBusy("After Effects is still working on another bridge job; wait for it to finish (never queue jobs in parallel).")
        jsx_dir = self.root / "jsx"
        jsx_dir.mkdir(parents=True, exist_ok=True)
        job_id = f"{int(time.time() * 1000)}-{secrets.token_hex(3)}"
        script = jsx_dir / f"{job_id}.jsx"
        script.write_text(code, encoding="utf-8")
        now = datetime.now(timezone.utc).isoformat()
        _write_atomic(self.result_file, {"status": "waiting", "message": "Waiting for new result from After Effects...", "timestamp": now})
        _write_atomic(self.command_file, {"command": "runJsx", "args": {"file": str(script), "jobId": job_id},
                                          "timestamp": now, "status": "pending"})
        return job_id

    def wait(self, job_id: str, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            cmd = self._command()
            if cmd:
                if cmd.get("args", {}).get("jobId") != job_id:
                    raise BridgeError(f"bridge command was replaced by another job before {job_id} finished")
                if cmd.get("status") in ("completed", "error"):
                    try:
                        res = json.loads(self.result_file.read_text(encoding="utf-8"))
                    except (OSError, ValueError) as e:
                        raise BridgeError(f"unreadable bridge result: {e}") from e
                    if cmd["status"] == "error" or res.get("status") == "error":
                        raise BridgeError(res.get("message") or json.dumps(res, ensure_ascii=False))
                    return res.get("result")
            time.sleep(self.poll)
        raise BridgeTimeout(f"job {job_id} is still running after {timeout}s; After Effects keeps working. "
                            "Wait until ae_command.json status is 'completed' before submitting anything else.")

    def run(self, code: str, timeout: float = 600):
        return self.wait(self.submit(code), timeout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_bridge -v`
Expected: 5 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/bridge.py engine/tests/test_bridge.py
git commit -m "feat(engine): bridge client with busy, error and timeout handling"
```

---

### Task 9: Context and base compiler (media, audio, fade)

**Files:**
- Create: `engine/aestudio/context.py`, `engine/aestudio/compiler.py`, `engine/aestudio/components/__init__.py`
- Create: `engine/tests/helpers.py`
- Test: `engine/tests/test_compiler.py`

**Interfaces:**
- Consumes: `Plan`, `Voice`… (Task 2), `load_transcript`, `voice_times`, `VoiceTimes` (Task 3), `duck_keys`, `sfx_fade_keys` (Task 4), `Design` (Task 5), `Ops`, `validate_ops` (Task 6), `r3` (Task 1).
- Produces:
  - `Context(design, ops, width, height, duration, voices: dict[str, VoiceTimes], grade: dict)` with `s` (width/3840), `px(v) -> float` (2 dp), `size(role, mult=1.0) -> float` (2 dp).
  - `REGISTRY: dict[tuple[str, str], Callable[[Context, dict, dict], None]]` and decorator `register(component: str, treatment: str)`.
  - `compile_plan(plan: Plan, design: Design) -> list[dict]` — op order: `comp`; one `footage` per shot (`SHOT_01`…, Lumetri = plan grade with `"20"` exposure added per shot); graphics in plan order via `REGISTRY[(type, treatment)]`; `audio` for voices (`VOICE_<id>`), `MUSIC` with ducking `levels` (+ `gain_db` added), `SFX_01`…; `FADE_OUT` solid last when `fade_out > 0`. Raises `KeyError`-derived `CompileError` for an unregistered treatment. Result is validated.
  - `engine/tests/helpers.py`: `make_ctx(design_id="notebook", voices=None, width=3840, height=2160, duration=40.0) -> Context` and `voice(id, at, words) -> VoiceTimes` (words relative, shifted by `at`).

- [ ] **Step 1: Write the failing test**

`engine/tests/helpers.py`:

```python
from aestudio.context import Context
from aestudio.design import load_design
from aestudio.ops import Ops
from aestudio.timing import VoiceTimes


def voice(vid, at, words):
    w = [(t, round(s + at, 3), round(e + at, 3)) for t, s, e in words]
    return VoiceTimes(vid, w[0][1], w[-1][2], w)


def make_ctx(design_id="notebook", voices=None, width=3840, height=2160, duration=40.0):
    ops = Ops()
    ops.add("comp", name="TEST", width=width, height=height, fps=23.976, duration=duration)
    return Context(load_design(design_id), ops, width, height, duration, voices or {}, {})
```

`engine/tests/test_compiler.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio.audio import duck_keys
from aestudio.compiler import CompileError, compile_plan
from aestudio.components import REGISTRY
from aestudio.design import load_design
from aestudio.plan import load_plan
from tests.helpers import make_ctx

WORDS_A = [["하나", 0.1, 0.5], ["둘", 0.6, 1.0]]
WORDS_B = [["셋", 0.2, 0.7]]


def build_plan(root: Path, graphics=()):
    for f in ("a.mp4", "b.mp4", "n1.wav", "n2.wav", "m.wav", "s.wav"):
        (root / f).write_text("x")
    (root / "n1.json").write_text(json.dumps({"words": WORDS_A}))
    (root / "n2.json").write_text(json.dumps({"words": WORDS_B}))
    plan = {
        "name": "UNIT", "format": {"duration": 20},
        "grade": {"lumetri": {"17": 104}},
        "shots": [{"clip": "a.mp4", "in": 0, "out": 10}, {"clip": "b.mp4", "in": 10, "out": 20, "src_in": 2, "exposure": 0.2}],
        "voices": [{"id": "N1", "file": "n1.wav", "at": 2, "transcript": "n1.json"},
                   {"id": "N2", "file": "n2.wav", "at": 9, "transcript": "n2.json", "gain_db": -2}],
        "music": {"file": "m.wav", "gain_db": -6, "duck": {"under_voice": -14}},
        "sfx": [{"file": "s.wav", "at": 7.5, "gain_db": -8, "fade_before_voice": True}, {"file": "s.wav", "at": 15, "gain_db": -3}],
        "graphics": list(graphics),
    }
    (root / "edit.json").write_text(json.dumps(plan))
    return load_plan(root / "edit.json")


class CompilerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_media_audio_and_fade(self):
        ops = compile_plan(build_plan(self.root), load_design("notebook"))
        by_id = {o.get("id"): o for o in ops}
        self.assertEqual(ops[0]["op"], "comp")
        self.assertEqual(by_id["SHOT_01"]["lumetri"], {"17": 104})
        self.assertEqual(by_id["SHOT_02"]["lumetri"], {"17": 104, "20": 0.2})
        self.assertEqual(by_id["SHOT_02"]["src_in"], 2.0)
        self.assertEqual(by_id["VOICE_N2"]["gain_db"], -2.0)
        self.assertEqual(by_id["VOICE_N1"]["end"], 3.5)
        expected = [[t, round(db - 6, 3)] for t, db in duck_keys([(2.1, 3.0), (9.2, 9.7)], 20.0, under_voice=-14)]
        self.assertEqual(by_id["MUSIC"]["levels"], expected)
        self.assertEqual(by_id["SFX_01"]["levels"], [[8.2, -8], [9.1, -25]])
        self.assertEqual(by_id["SFX_02"]["gain_db"], -3.0)
        self.assertEqual(ops[-1]["id"], "FADE_OUT")
        self.assertIn("so((time-19.25)/0.7)", ops[-1]["expr"]["opacity"])

    def test_unregistered_treatment(self):
        plan = build_plan(self.root, graphics=[{"type": "lower-third", "at": 3, "name": "A", "role": "B"}])
        design = load_design("notebook")
        design.components["lower-third"] = {"treatment": "does-not-exist"}
        with self.assertRaisesRegex(CompileError, "no treatment 'does-not-exist' for 'lower-third'"):
            compile_plan(plan, design)

    def test_dispatches_to_registry(self):
        calls = []
        REGISTRY[("lower-third", "unit-test")] = lambda ctx, g, opts: calls.append((g["name"], opts, ctx.s))
        try:
            plan = build_plan(self.root, graphics=[{"type": "lower-third", "at": 3, "name": "A", "role": "B"}])
            design = load_design("notebook")
            design.components["lower-third"] = {"treatment": "unit-test", "x": 1}
            compile_plan(plan, design)
        finally:
            del REGISTRY[("lower-third", "unit-test")]
        self.assertEqual(calls, [("A", {"x": 1}, 1.0)])

    def test_context_helpers(self):
        ctx = make_ctx(width=1920, height=1080)
        self.assertEqual(ctx.s, 0.5)
        self.assertEqual(ctx.px(100), 50.0)
        self.assertEqual(ctx.size("label"), 32.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_compiler -v`
Expected: ERROR `No module named 'aestudio.context'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/context.py`:

```python
"""What a design treatment receives."""
from dataclasses import dataclass, field


@dataclass
class Context:
    design: object
    ops: object
    width: int
    height: int
    duration: float
    voices: dict
    grade: dict = field(default_factory=dict)

    @property
    def s(self) -> float:
        return self.width / 3840

    def px(self, value) -> float:
        return round(value * self.s, 2)

    def size(self, role: str, mult: float = 1.0) -> float:
        return round(self.design.size(role) * mult * self.s, 2)
```

`engine/aestudio/components/__init__.py`:

```python
"""Treatment registry: (component type, treatment name) -> builder(ctx, graphic, options)."""
REGISTRY = {}


def register(component: str, treatment: str):
    def wrap(fn):
        REGISTRY[(component, treatment)] = fn
        return fn
    return wrap
```

`engine/aestudio/compiler.py`:

```python
"""edit plan + design -> ops."""
from .audio import duck_keys, sfx_fade_keys
from .components import REGISTRY
from .context import Context
from .ops import Ops, validate_ops
from .timing import load_transcript, voice_times
from .util import r3


class CompileError(KeyError):
    def __str__(self):
        return str(self.args[0])


def compile_plan(plan, design) -> list:
    f = plan.format
    ops = Ops()
    ops.add("comp", name=plan.name, width=f.width, height=f.height, fps=f.fps, duration=f.duration, bg=[0, 0, 0])
    voices = {v.id: voice_times(v, load_transcript(v.transcript)) for v in plan.voices}
    base_grade = {str(k): v for k, v in plan.grade.get("lumetri", {}).items()}

    for i, s in enumerate(plan.shots):
        lum = dict(base_grade)
        if s.exposure:
            lum["20"] = r3(float(lum.get("20", 0)) + s.exposure)
        ops.add("footage", id=f"SHOT_{i + 1:02d}", file=str(s.clip), start=r3(s.start), end=r3(s.end), src_in=r3(s.src_in),
                zoom=s.zoom if s.zoom != 1 else None, lumetri=lum or None)

    ctx = Context(design, ops, f.width, f.height, f.duration, voices, {"lumetri": base_grade})
    for g in plan.graphics:
        treatment, options = design.treatment(g["type"])
        builder = REGISTRY.get((g["type"], treatment))
        if builder is None:
            raise CompileError(f"no treatment '{treatment}' for '{g['type']}' (design {design.id}); registered: "
                               + ", ".join(sorted(f"{c}/{t}" for c, t in REGISTRY)))
        builder(ctx, g, options)

    for v in plan.voices:
        vt = voices[v.id]
        end = v.at + (v.src_out - v.src_in) if v.src_out is not None else min(vt.offset + 0.5, f.duration)
        ops.add("audio", id=f"VOICE_{v.id}", file=str(v.file), start=r3(v.at), end=r3(end), src_in=r3(v.src_in), gain_db=v.gain_db)

    spans = sorted((vt.onset, vt.offset) for vt in voices.values())
    if plan.music:
        keys = duck_keys(spans, f.duration, **plan.music.duck)
        ops.add("audio", id="MUSIC", file=str(plan.music.file), start=r3(plan.music.start), end=r3(f.duration),
                levels=[[t, round(db + plan.music.gain_db, 3)] for t, db in keys])
    onsets = [on for on, _ in spans]
    for i, sfx in enumerate(plan.sfx):
        keys = sfx_fade_keys(sfx.at, sfx.gain_db, onsets) if sfx.fade_before_voice else None
        ops.add("audio", id=f"SFX_{i + 1:02d}", file=str(sfx.file), start=r3(sfx.at), end=r3(f.duration),
                levels=keys, gain_db=None if keys else sfx.gain_db)

    if plan.fade_out > 0:
        start = r3(f.duration - plan.fade_out)
        ops.add("solid", id="FADE_OUT", color=[0, 0, 0], expr={"opacity": f"100*so((time-{start})/{r3(plan.fade_out - 0.05)})"})
    validate_ops(ops.items)
    return ops.items
```

Check against the test: voice N1 transcript onset/offset = 0.1/1.0 → absolute 2.1/3.0, `end = min(3.0 + 0.5, 20) = 3.5`; N2 → 9.2/9.7; SFX_01 next onset after 8.5 is 9.2 → keys `[[8.2, -8], [9.1, -25]]`; fade 0.75 → `so((time-19.25)/0.7)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_compiler -v`
Expected: 4 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/context.py engine/aestudio/compiler.py engine/aestudio/components engine/tests/helpers.py engine/tests/test_compiler.py
git commit -m "feat(engine): compile shots, voices, ducked music, sfx and fade-out into ops"
```

---
### Task 10: Shared layout helpers

**Files:**
- Create: `engine/aestudio/components/layout.py`
- Test: `engine/tests/test_layout.py`

**Interfaces:**
- Consumes: `align_words` (Task 3), `js`, `r3` (Task 1), `Context` (Task 9).
- Produces (all used by Tasks 11–13):
  - `class LayoutError(ValueError)`
  - `Segment(text: str, hl: bool, gap: float)`; `parse_line(line: list, space_px: float) -> list[Segment]` — a line is a list of strings and `{"hl": text}` items; whitespace at a segment edge becomes a horizontal gap of `space_px`, and no whitespace means the segments touch (Korean particles).
  - `segment_times(lines: list[list[Segment]], words) -> list[list[list[float]]]` — per line, per segment, the start time of each whitespace-separated word.
  - `schedule_times(lines, start: float, step: float, line_pause: float)` — same shape, for graphics with no voice.
  - `PLACES = ("bottom-left", "top-left", "bottom-right", "top-right", "lower-center", "top-center", "center")`; `place_block(place, n_lines, gap, width, height) -> (x, y_first, align)` with align `"left"` or `"center"`.
  - `fade_ref(group_id, mult=100) -> str` — `thisComp.layer("G").effect("FADE")(1)*mult/100`.
  - `Block(segments: list[list[str]], lines: list[str], ids: list[str])`
  - `text_block(ctx, *, prefix, parent, lines, times, x, y_first, gap, style, align, reveal, opacity=None, t_in=None, t_out=None) -> Block` — `style(line_index, segment) -> {"font","size","color", optional "tracking"}`; segment ids `f"{prefix}_L{i+1}S{k+1}"`; for `align="center"` one `group` per line (`f"{prefix}_L{i+1}"`) re-centred by an `expr` op after its segments exist.
  - `highlighter(ctx, *, id, parent, target, size, t0, dur, color, opacity=None, pad=14, band=(0.5, 0.46), rough=True, t_in=None, t_out=None)` — marker rect wiping left→right behind `target`, ordered directly under it.
  - `paper_card(ctx, *, id, parent, members, below, pad: tuple, color, radius, opacity=None, noise=0, shadow=True, t_in=None, t_out=None)` — rect sized to the union of `members` (same parent space) plus padding, ordered under all of `below`.
  - `span(t_in, t_out) -> dict` — `{"in": .., "out": ..}` without `None`s.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_layout.py`:

```python
import unittest

from aestudio.components.layout import (LayoutError, fade_ref, highlighter, paper_card, parse_line, place_block,
                                        schedule_times, segment_times, text_block)
from aestudio.ops import validate_ops
from tests.helpers import make_ctx

WORDS = [("모든", 0.10, 0.50), ("여정은", 0.50, 1.10), ("작은", 1.20, 1.60), ("한", 1.60, 1.80),
         ("걸음에서", 1.80, 2.60), ("시작됩니다.", 2.60, 3.50)]


class LayoutTest(unittest.TestCase):
    def test_parse_line_gaps(self):
        segs = parse_line(["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."], 30)
        self.assertEqual([(s.text, s.hl, s.gap) for s in segs],
                         [("작은", False, 0.0), ("한 걸음", True, 30.0), ("에서 시작됩니다.", False, 0.0)])
        self.assertEqual(parse_line(["a", " ", "b"], 10)[1].gap, 10.0)

    def test_parse_line_errors(self):
        for bad in ([], ["  "], [{"bold": "x"}], "text"):
            with self.assertRaises(LayoutError):
                parse_line(bad, 10)

    def test_segment_and_schedule_times(self):
        lines = [parse_line(["모든 여정은"], 30), parse_line(["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."], 30)]
        self.assertEqual(segment_times(lines, WORDS), [[[0.1, 0.5]], [[1.2], [1.6, 1.8], [2.2, 2.6]]])
        self.assertEqual(schedule_times(lines, 1.0, 0.1, 0.5), [[[1.0, 1.1]], [[1.7], [1.8, 1.9], [2.0, 2.1]]])

    def test_place_block(self):
        self.assertEqual(place_block("bottom-left", 2, 100, 3840, 2160), (345.6, 1736.0, "left"))
        self.assertEqual(place_block("top-center", 1, 100, 3840, 2160), (1920.0, 367.2, "center"))
        self.assertEqual(place_block("lower-center", 3, 100, 3840, 2160), (1920.0, 1636.0, "center"))
        with self.assertRaises(LayoutError):
            place_block("middle", 1, 100, 3840, 2160)

    def test_text_block_left_highlight_and_card(self):
        ctx = make_ctx()
        ctx.ops.add("group", id="G", fade="100")
        lines = [parse_line(["모든 여정은"], 30), parse_line(["작은 ", {"hl": "한 걸음"}, "에서"], 30)]
        times = [[[0.1, 0.5]], [[1.2], [1.6, 1.8], [2.2]]]
        style = lambda i, s: {"font": "F", "size": 100.0, "color": [0, 0, 0]}
        block = text_block(ctx, prefix="G", parent="G", lines=lines, times=times, x=300, y_first=1500, gap=130, style=style,
                           align="left", reveal={"dur": 0.35, "rise": 14, "blur": 6, "by": "words"}, opacity=fade_ref("G"), t_in=0, t_out=5)
        self.assertEqual(block.segments, [["G_L1S1"], ["G_L2S1", "G_L2S2", "G_L2S3"]])
        items = {o.get("id"): o for o in ctx.ops.items}
        self.assertEqual(items["G_L2S1"]["position"], [300, 1630])
        self.assertIn('thisComp.layer("G_L2S1")', items["G_L2S2"]["expr"]["position"])
        self.assertIn("+30.0,value[1]]", items["G_L2S2"]["expr"]["position"])
        self.assertEqual(items["G_L2S2"]["reveal"]["times"], [1.6, 1.8])
        self.assertEqual(items["G_L2S2"]["in"], 0)
        highlighter(ctx, id="HL", parent="G", target="G_L2S2", size=100, t0=1.65, dur=0.5, color=[1, 1, 0])
        self.assertIn("eio((time-1.65)/0.5)", items_of(ctx)["HL"]["rect_expr"]["size"])
        paper_card(ctx, id="CARD", parent="G", members=block.ids, below=block.ids + ["HL"], pad=(100, 60), color=[1, 1, 1], radius=18, noise=4)
        orders = [o for o in ctx.ops.items if o["op"] == "order"]
        self.assertEqual(orders[-1], {"op": "order", "layer": "CARD", "below": block.ids + ["HL"]})
        effects = [o["match"] for o in ctx.ops.items if o["op"] == "effect" and o["layer"] == "CARD"]
        self.assertEqual(effects, ["ADBE Noise", "ADBE Drop Shadow"])
        validate_ops(ctx.ops.items)

    def test_text_block_center_adds_line_groups(self):
        ctx = make_ctx()
        lines = [parse_line(["하나 ", "둘"], 30)]
        style = lambda i, s: {"font": "F", "size": 100.0, "color": [0, 0, 0]}
        block = text_block(ctx, prefix="C", parent=None, lines=lines, times=[[[0.0], [0.5]]], x=1920, y_first=1800, gap=130,
                           style=style, align="center", reveal={"dur": 0.5, "by": "words"})
        self.assertEqual(block.lines, ["C_L1"])
        items = ctx.ops.items
        self.assertEqual(items[1], {"op": "group", "id": "C_L1", "position": [1920, 1800]})
        self.assertEqual(items[2]["parent"], "C_L1")
        self.assertEqual(items[2]["position"], [0, 0])
        self.assertEqual(items[-1]["op"], "expr")
        self.assertIn("value[0]-(x0+x1)/2", items[-1]["exprs"]["position"])
        validate_ops(items)


def items_of(ctx):
    return {o.get("id"): o for o in ctx.ops.items}


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_layout -v`
Expected: ERROR `No module named 'aestudio.components.layout'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/components/layout.py`:

```python
"""Layout shared by treatments: segmented lines synced to speech, highlighter, paper card, placement."""
from dataclasses import dataclass

from ..timing import align_words
from ..util import js, r3

STATIC = "posterizeTime(0);"          # layout that never animates: evaluate once
T_END = "thisComp.duration-0.01"      # measure text after every reveal animator has finished
PLACES = ("bottom-left", "top-left", "bottom-right", "top-right", "lower-center", "top-center", "center")


class LayoutError(ValueError):
    pass


@dataclass
class Segment:
    text: str
    hl: bool
    gap: float


@dataclass
class Block:
    segments: list
    lines: list
    ids: list


def span(t_in=None, t_out=None) -> dict:
    out = {}
    if t_in is not None:
        out["in"] = r3(t_in)
    if t_out is not None:
        out["out"] = r3(t_out)
    return out


def parse_line(line, space_px):
    if not isinstance(line, list) or not line:
        raise LayoutError(f"a line must be a non-empty list of segments, got {line!r}")
    segs, pending = [], False
    for item in line:
        if isinstance(item, str):
            raw, hl = item, False
        elif isinstance(item, dict) and list(item) == ["hl"] and isinstance(item["hl"], str):
            raw, hl = item["hl"], True
        else:
            raise LayoutError(f'a segment must be a string or {{"hl": text}}, got {item!r}')
        text = raw.strip()
        if not text:
            pending = pending or bool(raw)
            continue
        gap = space_px if segs and (pending or raw[0].isspace()) else 0.0
        segs.append(Segment(text, hl, round(float(gap), 2)))
        pending = raw[-1].isspace()
    if not segs:
        raise LayoutError(f"line has no visible text: {line!r}")
    return segs


def _word_counts(lines):
    return [[len(s.text.split()) for s in segs] for segs in lines]


def segment_times(lines, words):
    flat = [w for segs in lines for s in segs for w in s.text.split()]
    times = align_words(flat, words)
    out, i = [], 0
    for counts in _word_counts(lines):
        row = []
        for n in counts:
            row.append([r3(t) for t in times[i:i + n]])
            i += n
        out.append(row)
    return out


def schedule_times(lines, start, step, line_pause):
    out, t = [], float(start)
    for counts in _word_counts(lines):
        row = []
        for n in counts:
            row.append([r3(t + k * step) for k in range(n)])
            t += n * step
        out.append(row)
        t += line_pause
    return out


def place_block(place, n_lines, gap, width, height):
    if place not in PLACES:
        raise LayoutError(f"unknown place '{place}' (expected one of {', '.join(PLACES)})")
    extent = (n_lines - 1) * gap
    horiz = "center" if place.endswith("center") else place.split("-")[1]
    vert = "center" if place == "center" else ("top" if place.startswith("top") else "bottom")
    x = {"left": 0.09, "right": 0.55, "center": 0.5}[horiz] * width
    y_first = {"top": 0.17 * height, "bottom": 0.85 * height - extent, "center": 0.5 * height - extent / 2}[vert]
    return round(x, 2), round(y_first, 2), ("center" if horiz == "center" else "left")


def fade_ref(group_id, mult=100):
    return f'thisComp.layer({js(group_id)}).effect("FADE")(1)*{mult}/100'


def text_block(ctx, *, prefix, parent, lines, times, x, y_first, gap, style, align, reveal, opacity=None, t_in=None, t_out=None):
    ops = ctx.ops
    block = Block([], [], [])
    for i, segs in enumerate(lines):
        y = r3(y_first + i * gap)
        seg_parent, origin = parent, [x, y]
        if align == "center":
            line_id = f"{prefix}_L{i + 1}"
            ops.add("group", id=line_id, parent=parent, position=[x, y])
            block.lines.append(line_id)
            seg_parent, origin = line_id, [0, 0]
        row = []
        for k, seg in enumerate(segs):
            sid = f"{prefix}_L{i + 1}S{k + 1}"
            st = style(i, seg)
            expr = {"opacity": opacity} if opacity else {}
            if k:
                expr["position"] = (STATIC + f"var P=thisComp.layer({js(row[-1])});var r=P.sourceRectAtTime({T_END},false);"
                                    f"[P.transform.position[0]+r.left+r.width+{seg.gap},value[1]]")
            ops.add("text", id=sid, parent=seg_parent, text=seg.text, font=st["font"], size=st["size"], color=st["color"],
                    tracking=st.get("tracking"), position=list(origin), reveal=dict(reveal, times=times[i][k]),
                    expr=expr or None, **span(t_in, t_out))
            row.append(sid)
        if align == "center":
            f, z = row[0], row[-1]
            ops.add("expr", layer=block.lines[-1], exprs={"position": (
                STATIC + f"var F=thisComp.layer({js(f)}),Z=thisComp.layer({js(z)});"
                f"var rf=F.sourceRectAtTime({T_END},false),rz=Z.sourceRectAtTime({T_END},false);"
                "var x0=F.transform.position[0]+rf.left,x1=Z.transform.position[0]+rz.left+rz.width;[value[0]-(x0+x1)/2,value[1]]")})
        block.segments.append(row)
        block.ids.extend(row)
    return block


def highlighter(ctx, *, id, parent, target, size, t0, dur, color, opacity=None, pad=14, band=(0.5, 0.46), rough=True, t_in=None, t_out=None):
    geo = (f"var L=thisComp.layer({js(target)});var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
           f"var x0=p[0]+r.left-{pad},w=r.width+{r3(2 * pad)},top=p[1]-{r3(size * band[0])},h={r3(size * band[1])};"
           f"var k=eio((time-{r3(t0)})/{dur});")
    ctx.ops.add("rect", id=id, parent=parent, color=color, rect_expr={"size": geo + "[w*k,h]", "center": geo + "[x0+w*k/2,top+h/2]"},
                expr={"opacity": opacity} if opacity else None, **span(t_in, t_out))
    if rough:
        ctx.ops.add("effect", layer=id, match="ADBE Roughen Edges", props={"3": ctx.px(5)})
    ctx.ops.add("order", layer=id, below=[target])


def paper_card(ctx, *, id, parent, members, below, pad, color, radius, opacity=None, noise=0, shadow=True, t_in=None, t_out=None):
    geo = (STATIC + f"var N={js(list(members))};var x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;"
           f"for(var i=0;i<N.length;i++){{var L=thisComp.layer(N[i]);var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
           "x0=Math.min(x0,p[0]+r.left);y0=Math.min(y0,p[1]+r.top);x1=Math.max(x1,p[0]+r.left+r.width);y1=Math.max(y1,p[1]+r.top+r.height);}")
    ctx.ops.add("rect", id=id, parent=parent, color=color, roundness=radius,
                rect_expr={"size": geo + f"[x1-x0+{r3(2 * pad[0])},y1-y0+{r3(2 * pad[1])}]", "center": geo + "[(x0+x1)/2,(y0+y1)/2]"},
                expr={"opacity": opacity} if opacity else None, **span(t_in, t_out))
    if noise:
        ctx.ops.add("effect", layer=id, match="ADBE Noise", props={"1": noise, "2": 0})
    if shadow:
        ctx.ops.add("effect", layer=id, match="ADBE Drop Shadow", props={"2": 60, "3": 180, "4": ctx.px(14), "5": ctx.px(40)})
    ctx.ops.add("order", layer=id, below=list(below))
```

Check against the test: `place_block("bottom-left", 2, 100, 3840, 2160)` → x = 0.09·3840 = 345.6, y_first = 0.85·2160 − 100 = 1736.0. `top-center` → y = 0.17·2160 = 367.2. `lower-center` with 3 lines → 1836 − 200 = 1636.0. Second-line segment position `[300, 1630]` = 1500 + 130 (`r3` gives `1630.0`, and `[300, 1630.0] == [300, 1630]` in Python). Schedule: line 1 words at 1.0, 1.1 → t = 1.2 + pause 0.5 = 1.7; line 2: `작은` 1.7, `한 걸음` 1.8/1.9, `에서 시작됩니다.` 2.0/2.1.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_layout -v`
Expected: 6 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/components/layout.py engine/tests/test_layout.py
git commit -m "feat(engine): segmented text layout, highlighter and paper card helpers"
```

---
### Task 11: Notebook treatments — caption, quote, lower third

**Files:**
- Create: `engine/aestudio/components/notebook.py`
- Modify: `engine/aestudio/components/__init__.py` (import the module at the bottom so treatments register)
- Test: `engine/tests/test_notebook.py`

**Interfaces:**
- Consumes: `register` (Task 9); `parse_line`, `segment_times`, `place_block`, `fade_ref`, `text_block`, `highlighter`, `paper_card`, `span` (Task 10); `Context` (`ctx.design`, `ctx.ops`, `ctx.voices`, `ctx.px`, `ctx.size`, `ctx.width`, `ctx.height`).
- Graphic contracts (see `docs/components.md`, Task 15):
  - `caption` / `quote`: `{"voice": id, "lines": [[segment, ...], ...], "place"?: PLACES item, "in"?: s, "out"?: s}`; defaults `in = voice onset − 0.3`, `out = voice offset + 0.5`; caption default place `bottom-left`, quote `top-right`.
  - `lower-third`: `{"at": s, "dur"?: 4.25, "name": str, "role": str}`.
- Produces: registered builders `("caption","paper-card")`, `("quote","paper-card")`, `("lower-third","paper-tab")`. Ids: `CAPTION_NN` / `QUOTE_NN` group with `_L{i}S{k}` segments, `_HL` highlighters, `_MARK` (quote), `_CARD`; `LOWER_THIRD_NN` with `_NAME`, `_ROLE`, `_PILL`, `_NAME_HL`, `_CARD`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_notebook.py`:

```python
import unittest

from aestudio.components import REGISTRY
from aestudio.ops import validate_ops
from tests.helpers import make_ctx, voice

WORDS = [("모든", 0.10, 0.50), ("여정은", 0.50, 1.10), ("작은", 1.20, 1.60), ("한", 1.60, 1.80),
         ("걸음에서", 1.80, 2.60), ("시작됩니다.", 2.60, 3.50)]
CAPTION = {"type": "caption", "voice": "N1", "lines": [["모든 여정은"], ["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]]}


def by_id(ctx):
    return {o.get("id"): o for o in ctx.ops.items}


class NotebookCaptionTest(unittest.TestCase):
    def build(self, graphic, width=3840):
        ctx = make_ctx("notebook", voices={"N1": voice("N1", 10.0, WORDS)}, width=width, height=width * 9 // 16)
        REGISTRY[(graphic["type"], "paper-card" if graphic["type"] in ("caption", "quote") else "paper-tab")](ctx, graphic, {})
        validate_ops(ctx.ops.items)
        return ctx

    def test_caption_timing_style_and_card(self):
        ctx = self.build(CAPTION)
        items = by_id(ctx)
        group = items["CAPTION_01"]
        self.assertIn("so((time-9.8)/0.35)", group["fade"])
        self.assertIn("(time-13.6)/0.4", group["fade"])         # out = offset 13.5 + 0.5 = 14.0; fade-out starts 0.4 s earlier
        seg = items["CAPTION_01_L2S2"]
        self.assertEqual(seg["text"], "한 걸음")
        self.assertEqual(seg["font"], "Paperlogy-7Bold")         # line with a highlight uses the emphasis role
        self.assertEqual(items["CAPTION_01_L1S1"]["font"], "Paperlogy-5Medium")
        self.assertEqual(seg["reveal"]["times"], [11.6, 11.8])
        self.assertIn("eio((time-11.65)/0.5)", items["CAPTION_01_L2S2_HL"]["rect_expr"]["size"])
        card = [o for o in ctx.ops.items if o["op"] == "order" and o["layer"] == "CAPTION_01_CARD"][0]
        self.assertIn("CAPTION_01_L2S2_HL", card["below"])
        self.assertEqual(items["CAPTION_01_CARD"]["color"], ctx.design.color("paper"))

    def test_quote_has_mark_and_default_place(self):
        g = dict(CAPTION, type="quote")
        items = by_id(self.build(g))
        self.assertEqual(items["QUOTE_01_MARK"]["text"], "“")
        self.assertEqual(items["QUOTE_01_L1S1"]["font"], "Paperlogy-6SemiBold")
        self.assertEqual(items["QUOTE_01"]["anchor"][0], 2112.0)   # top-right: 0.55 * 3840

    def test_scales_with_width(self):
        items = by_id(self.build(CAPTION, width=1920))
        self.assertEqual(items["CAPTION_01_L1S1"]["size"], 50.0)

    def test_lower_third(self):
        ctx = self.build({"type": "lower-third", "at": 5, "name": "이하늘", "role": "스튜디오 참가자"})
        items = by_id(ctx)
        self.assertIn("(time-8.8)/0.45", items["LOWER_THIRD_01"]["fade"])    # dur 4.25 → out 9.25; fade-out starts 0.45 s earlier
        self.assertEqual(items["LOWER_THIRD_01_NAME"]["text"], "이하늘")
        self.assertEqual(items["LOWER_THIRD_01_ROLE"]["color"], ctx.design.color("paper"))
        pill = items["LOWER_THIRD_01_PILL"]
        self.assertEqual(pill["color"], ctx.design.color("ink"))
        self.assertIn("bo((time-5.35)/0.45)", pill["expr"]["scale"])
        self.assertIn("eio((time-5.6)/0.55)", items["LOWER_THIRD_01_NAME_HL"]["rect_expr"]["size"])
        self.assertIn("LOWER_THIRD_01_CARD", items)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_notebook -v`
Expected: ERROR `KeyError: ('caption', 'paper-card')`

- [ ] **Step 3: Write the treatments**

`engine/aestudio/components/notebook.py`:

```python
"""Paper Notebook treatments: paper cards with marker highlights, paper-tab lower third,
notebook-page title and polaroid end card."""
from ..util import js, r3
from . import register
from .layout import STATIC, T_END, fade_ref, highlighter, paper_card, parse_line, place_block, segment_times, span, text_block


@register("caption", "paper-card")
@register("quote", "paper-card")
def caption_paper_card(ctx, g, opts):
    d, ops = ctx.design, ctx.ops
    quote = g["type"] == "quote"
    vt = ctx.voices[g["voice"]]
    t_in = r3(g.get("in", vt.onset - 0.3))
    t_out = r3(g.get("out", vt.offset + 0.5))
    lead, emph = ("quote", "quote") if quote else ("body", "emphasis")
    lines = [parse_line(line, ctx.size(lead, 0.28)) for line in g["lines"]]
    roles = [emph if any(s.hl for s in segs) else lead for segs in lines]
    gap = r3(max(ctx.size(r) for r in roles) * 1.3)
    x, y0, _ = place_block(g.get("place", "top-right" if quote else "bottom-left"), len(lines), gap, ctx.width, ctx.height)
    cid = ops.uid("QUOTE" if quote else "CAPTION")
    ops.add("group", id=cid, anchor=[x, y0], position=[x, y0],
            fade=f"100*so((time-{t_in})/0.35)*(1-si((time-{r3(t_out - 0.4)})/0.4))",
            expr={"position": f"var a=bo((time-{t_in})/{d.motion['in']});var b=si((time-{r3(t_out - 0.45)})/0.45);"
                              f"value+[0,{-ctx.px(40)}*(1-a)+{ctx.px(60)}*b]",
                  "rotation": f"-1.0+1.2*(1-bo((time-{t_in})/{d.motion['in']}))"})
    fade = fade_ref(cid)
    out = r3(t_out + 0.1)
    ink = d.color("ink")
    times = segment_times(lines, vt.words)
    block = text_block(ctx, prefix=cid, parent=cid, lines=lines, times=times, x=x, y_first=y0, gap=gap,
                       style=lambda i, s: {"font": d.font(roles[i]), "size": ctx.size(roles[i]), "color": ink}, align="left",
                       reveal={"dur": d.motion["word"], "rise": ctx.px(d.motion["rise"]), "blur": 6, "by": "words"},
                       opacity=fade, t_in=t_in, t_out=out)
    below = list(block.ids)
    if quote:
        mark = f"{cid}_MARK"
        ops.add("text", id=mark, parent=cid, text="“", font=d.font("scripture"), size=ctx.px(220), color=d.color("accent2"),
                position=[r3(x - ctx.px(150)), r3(y0 + ctx.px(90))], expr={"opacity": fade}, **span(t_in, out))
        below.append(mark)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                sid = block.segments[i][k]
                highlighter(ctx, id=f"{sid}_HL", parent=cid, target=sid, size=ctx.size(roles[i]), t0=times[i][k][0] + 0.05, dur=0.5,
                            color=d.color("accent"), opacity=fade_ref(cid, 88), pad=ctx.px(12), t_in=t_in, t_out=out)
                below.append(f"{sid}_HL")
    paper_card(ctx, id=f"{cid}_CARD", parent=cid, members=block.ids, below=below, pad=(ctx.px(90 if quote else 100), ctx.px(60)),
               color=d.color("paper"), radius=ctx.px(18), opacity=fade, noise=d.texture.get("noise", 0), t_in=t_in, t_out=out)


@register("lower-third", "paper-tab")
def lower_third_paper_tab(ctx, g, opts):
    d, ops, px = ctx.design, ctx.ops, ctx.px
    t_in = r3(g["at"])
    t_out = r3(t_in + g.get("dur", 4.25))
    x, y = r3(0.06 * ctx.width), r3(0.6 * ctx.height)
    lid = ops.uid("LOWER_THIRD")
    sp = span(t_in, t_out + 0.05)
    ops.add("group", id=lid, anchor=[x, y], position=[x, y],
            fade=f"100*so((time-{t_in})/0.3)*(1-si((time-{r3(t_out - 0.45)})/0.45))",
            expr={"position": f"var a=bo((time-{t_in})/0.65);var b=si((time-{r3(t_out - 0.5)})/0.5);value+[{-px(1100)}*(1-a)-{px(700)}*b,0]",
                  "rotation": f"-1.0-1.5*(1-bo((time-{t_in})/0.65))"})
    fade = fade_ref(lid)
    name, role, pill = f"{lid}_NAME", f"{lid}_ROLE", f"{lid}_PILL"
    name_size = ctx.size("headline", 0.9)
    ops.add("text", id=name, parent=lid, text=g["name"], font=d.font("headline"), size=name_size, color=d.color("ink"),
            position=[x, y], expr={"opacity": fade}, **sp)
    ops.add("text", id=role, parent=lid, text=g["role"], font=d.font("label"), size=ctx.size("label", 0.875), color=d.color("paper"),
            tracking=20, position=[r3(x + px(34)), r3(y - px(170))],
            expr={"opacity": f"100*so((time-{r3(t_in + 0.45)})/0.3)*{fade}/100"}, **sp)
    geo = (STATIC + f"var L=thisComp.layer({js(role)});var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
           f"var x0=p[0]+r.left-{px(34)},x1=p[0]+r.left+r.width+{px(34)},y0=p[1]+r.top-{px(18)},y1=p[1]+r.top+r.height+{px(18)};")
    center = geo + "[(x0+x1)/2,(y0+y1)/2]"
    ops.add("rect", id=pill, parent=lid, color=d.color("ink"), roundness=px(40), rect_expr={"size": geo + "[x1-x0,y1-y0]", "center": center},
            expr={"anchor": center, "position": center, "scale": f"var k=bo((time-{r3(t_in + 0.35)})/0.45);[100*k,100*k]", "opacity": fade}, **sp)
    ops.add("order", layer=pill, below=[role])
    highlighter(ctx, id=f"{name}_HL", parent=lid, target=name, size=name_size, t0=t_in + 0.6, dur=0.55, color=d.color("accent"),
                opacity=fade_ref(lid, 88), pad=px(14), t_in=t_in, t_out=t_out + 0.05)
    paper_card(ctx, id=f"{lid}_CARD", parent=lid, members=[name, role], below=[name, role, pill, f"{name}_HL"],
               pad=(px(80), px(60)), color=d.color("paper"), radius=px(18), opacity=fade, noise=d.texture.get("noise", 0),
               t_in=t_in, t_out=t_out + 0.05)
```

Append to `engine/aestudio/components/__init__.py`:

```python


from . import notebook  # noqa: E402,F401  (registers treatments)
```

Check against the test: voice words shifted by 10 → onset 10.1, offset 13.5; `t_in = 9.8`, `t_out = 14.0`; `한 걸음` → [11.6, 11.8]; highlight `t0 = 11.65`. Quote group anchor x = `place_block("top-right")` = 2112.0. At width 1920 the body size is 100 × 0.5 = 50.0. Lower third: pill scale starts at 5.35, highlight at 5.6.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_notebook -v`
Expected: 4 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/components engine/tests/test_notebook.py
git commit -m "feat(designs): notebook caption, quote and lower-third treatments"
```

---
### Task 12: Notebook treatments — title page and end card

**Files:**
- Modify: `engine/aestudio/components/notebook.py` (append two builders)
- Test: `engine/tests/test_notebook_pages.py`

**Interfaces:**
- Consumes: Task 10 helpers (`parse_line`, `schedule_times`, `text_block`, `highlighter`, `span`), `ctx.grade["lumetri"]`, `ctx.duration`.
- Graphic contracts:
  - `title-page`: `{"in": s, "out": s, "lines": [[segment, ...], ...], "ref"?: str}` — `out` is when the page starts leaving; layers end at `out + 0.75`.
  - `end-card`: `{"in": s, "title": str, "year"?: str|int, "tagline"?: str, "rows"?: [{"label": str, "values": [str, ...]}], "photo"?: {"clip": path, "src_in"?: s, "stretch"?: %}, "logo"?: {"file": path, "tint"?: true, "width"?: 4K px}}` — stays until the end of the comp.
- Produces: registered `("title-page","notebook-page")` and `("end-card","notebook-page")`. Ids: `TITLE_NN` with `_PAPER`, `_RULES`, `_L{i}S{k}`, `_HL`, `_REF`; `END_NN` with `_PAPER`, `_RULES`, `_POLAROID` (group), `_POLAROID_FRAME`, `_POLAROID_PHOTO`, `_YEAR`, `_YEAR_PILL`, `_TITLE`, `_TITLE_HL`, `_TAGLINE`, `_ROW{r}_LABEL`, `_ROW{r}_VALUE{v}`, `_LOGO`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_notebook_pages.py`:

```python
import unittest

from aestudio.components import REGISTRY
from aestudio.ops import validate_ops
from tests.helpers import make_ctx

TITLE = {"type": "title-page", "in": 0, "out": 6.5, "lines": [["함께 배우고,"], ["함께 ", {"hl": "자라는"}, " 시간"]], "ref": "OPEN DAY"}
END = {"type": "end-card", "in": 30, "title": "오픈 스튜디오", "year": 2027, "tagline": "누구나 시작할 수 있는 자리",
       "rows": [{"label": "신청 기간", "values": ["9월 1일 – 9월 20일"]}, {"label": "문의", "values": ["사무실", "010-0000-0000"]}],
       "photo": {"clip": "/tmp/c.mp4", "src_in": 2}, "logo": {"file": "/tmp/logo.png"}}


def items(ctx):
    return {o.get("id"): o for o in ctx.ops.items}


class NotebookPagesTest(unittest.TestCase):
    def test_title_page(self):
        ctx = make_ctx("notebook")
        REGISTRY[("title-page", "notebook-page")](ctx, TITLE, {})
        validate_ops(ctx.ops.items)
        it = items(ctx)
        self.assertIn("si((time-6.5)/0.7)", it["TITLE_01"]["expr"]["position"])
        self.assertEqual(it["TITLE_01_PAPER"]["out"], 7.25)
        self.assertEqual(it["TITLE_01_RULES"]["count"], 23)
        self.assertEqual(it["TITLE_01_L1S1"]["font"], "MaruBuri-Bold")
        self.assertEqual(it["TITLE_01_L1S1"]["reveal"]["times"], [1.0, 1.09])
        self.assertEqual(it["TITLE_01_L2S2"]["reveal"]["times"], [1.62])
        self.assertIn("eio((time-2.07)/0.6)", it["TITLE_01_L2S2_HL"]["rect_expr"]["size"])
        self.assertEqual(it["TITLE_01_REF"]["reveal"]["times"][0], 2.51)

    def test_end_card(self):
        ctx = make_ctx("notebook", duration=40.0)
        ctx.grade = {"lumetri": {"17": 104}}
        REGISTRY[("end-card", "notebook-page")](ctx, END, {})
        validate_ops(ctx.ops.items)
        it = items(ctx)
        photo = it["END_01_POLAROID_PHOTO"]
        self.assertEqual((photo["op"], photo["parent"], photo["start"], photo["end"], photo["src_in"]), ("footage", "END_01_POLAROID", 30.0, 40.0, 2))
        self.assertEqual(photo["lumetri"], {"17": 104})
        self.assertEqual(it["END_01_YEAR"]["text"], "2027")
        self.assertEqual(it["END_01_TITLE"]["reveal"]["by"], "chars")
        self.assertEqual(len(it["END_01_TITLE"]["reveal"]["times"]), len("오픈 스튜디오"))
        self.assertEqual(it["END_01_ROW2_VALUE2"]["text"], "010-0000-0000")
        self.assertAlmostEqual(it["END_01_ROW2_VALUE2"]["position"][1], it["END_01_ROW2_VALUE1"]["position"][1] + 92, places=2)
        self.assertEqual(it["END_01_LOGO"]["tint"], ctx.design.color("ink"))
        self.assertIn("so((time-33.9)/0.5)", it["END_01_LOGO"]["expr"]["opacity"])

    def test_end_card_minimal(self):
        ctx = make_ctx("notebook")
        REGISTRY[("end-card", "notebook-page")](ctx, {"type": "end-card", "in": 10, "title": "T"}, {})
        validate_ops(ctx.ops.items)
        self.assertNotIn("END_01_LOGO", items(ctx))
        self.assertNotIn("END_01_POLAROID_PHOTO", items(ctx))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_notebook_pages -v`
Expected: ERROR `KeyError: ('title-page', 'notebook-page')`

- [ ] **Step 3: Write the treatments**

Append to `engine/aestudio/components/notebook.py` (and add `schedule_times` to the `.layout` import list):

```python


def _page(ctx, pid, t_in, t_out, draw_at):
    """Full-frame paper with texture, soft shadow, ruled lines and a margin line drawn on from the left."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    paper = f"{pid}_PAPER"
    ops.add("rect", id=paper, parent=pid, color=d.color("paper"), size=[W, r3(H + px(40))], center=[r3(W / 2), r3(H / 2 - px(20))],
            **span(t_in, t_out))
    if d.texture.get("noise"):
        ops.add("effect", layer=paper, match="ADBE Noise", props={"1": d.texture["noise"], "2": 0})
    ops.add("effect", layer=paper, match="ADBE Drop Shadow", props={"2": 120, "3": 180, "4": px(14), "5": px(140)})
    spacing, y0 = px(90), px(135)
    ops.add("rules", id=f"{pid}_RULES", parent=pid, count=int((H - y0) // spacing) + 1, spacing=spacing, y0=y0,
            color=d.color("rule"), stroke=px(3), margin_x=r3(0.2 * W), margin_color=d.color("accent2"),
            expr={"scale": f"var k=so((time-{r3(draw_at)})/0.9);[100*k,100]"}, **span(t_in, t_out))


@register("title-page", "notebook-page")
def title_notebook_page(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.75)
    tid = ops.uid("TITLE")
    ops.add("group", id=tid, expr={"position": f"var k=si((time-{t_out})/0.7);value+[0,{-r3(H + px(140))}*k]"})
    _page(ctx, tid, t_in, end, t_in + 0.2)
    size = ctx.size("scripture")
    lines = [parse_line(line, ctx.size("scripture", 0.28)) for line in g["lines"]]
    gap = r3(size * 1.4)
    x, y_first = r3(0.263 * W), r3(0.45 * H - (len(lines) - 1) * gap / 2)
    times = schedule_times(lines, start=t_in + 1.0, step=0.09, line_pause=0.35)
    ink = d.color("ink")
    block = text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=x, y_first=y_first, gap=gap,
                       style=lambda i, s: {"font": d.font("scripture"), "size": size, "color": ink}, align="left",
                       reveal={"dur": 0.45, "rise": px(10), "blur": 6, "by": "words"}, t_in=t_in, t_out=end)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                sid = block.segments[i][k]
                highlighter(ctx, id=f"{sid}_HL", parent=tid, target=sid, size=size, t0=times[i][k][-1] + 0.45, dur=0.6,
                            color=d.color("accent"), pad=px(14), t_in=t_in, t_out=end)
    if g.get("ref"):
        start = times[-1][-1][-1] + 0.8
        ops.add("text", id=f"{tid}_REF", parent=tid, text=g["ref"], font=d.font("label"), size=ctx.size("label", 1.1),
                color=d.color("accent2"), tracking=40, position=[x, r3(y_first + len(lines) * gap)],
                reveal={"times": [r3(start + 0.04 * i) for i in range(len(g["ref"]))], "dur": 0.35, "rise": px(8), "blur": 4, "by": "chars"},
                **span(t_in, end))


@register("end-card", "notebook-page")
def end_card_notebook_page(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    E = r3(g["in"])
    eid = ops.uid("END")
    sp = span(E)
    ops.add("group", id=eid, expr={"position": f"var k=so((time-{E})/0.75);value+[0,{-r3(H + px(140))}*(1-k)]"})
    _page(ctx, eid, E, None, E + 0.55)

    # polaroid: white frame + moving photo, dropped in with a settle
    PX, PY, PW, PH = r3(0.294 * W), r3(0.5 * H), px(1560), px(1180)
    pol = f"{eid}_POLAROID"
    drop = r3(E + 0.75)
    ops.add("group", id=pol, parent=eid, anchor=[PX, PY], position=[PX, PY],
            expr={"position": f"var k=bo((time-{drop})/0.8);value+[0,{-px(260)}*(1-k)]",
                  "rotation": f"var k=bo((time-{drop})/0.8);3+5*(1-k)"})
    pop = f"100*so((time-{drop})/0.35)"
    ops.add("rect", id=f"{pol}_FRAME", parent=pol, color=[1, 1, 1], size=[PW, PH], center=[PX, PY], roundness=px(6),
            expr={"opacity": pop}, **sp)
    ops.add("effect", layer=f"{pol}_FRAME", match="ADBE Drop Shadow", props={"2": 95, "3": 180, "4": px(26), "5": px(90)})
    photo = g.get("photo")
    if photo:
        ops.add("footage", id=f"{pol}_PHOTO", parent=pol, file=photo["clip"], start=E, end=r3(ctx.duration),
                src_in=photo.get("src_in", 0), stretch=photo.get("stretch"), width=r3(PW - px(70)),
                position=[PX, r3(PY - px(60))], mask=[r3(PW - px(70)), r3(PH - px(200))],
                lumetri=dict(ctx.grade.get("lumetri", {})) or None, expr={"opacity": pop})

    RX = r3(0.542 * W)
    ink = d.color("ink")
    if g.get("year") is not None:
        year = f"{eid}_YEAR"
        ops.add("text", id=year, parent=eid, text=str(g["year"]), font=d.font("label"), size=px(70), color=d.color("paper"), tracking=60,
                position=[r3(RX + px(44)), r3(0.241 * H)], expr={"opacity": f"100*so((time-{r3(E + 1.2)})/0.3)"}, **sp)
        geo = (STATIC + f"var L=thisComp.layer({js(year)});var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
               f"var x0=p[0]+r.left-{px(44)},x1=p[0]+r.left+r.width+{px(44)},y0=p[1]+r.top-{px(20)},y1=p[1]+r.top+r.height+{px(20)};")
        c = geo + "[(x0+x1)/2,(y0+y1)/2]"
        ops.add("rect", id=f"{year}_PILL", parent=eid, color=ink, roundness=px(46), rect_expr={"size": geo + "[x1-x0,y1-y0]", "center": c},
                expr={"anchor": c, "position": c, "scale": f"var k=bo((time-{r3(E + 1.1)})/0.45);[100*k,100*k]"}, **sp)
        ops.add("order", layer=f"{year}_PILL", below=[year])
    title = f"{eid}_TITLE"
    tsize = ctx.size("headline", 1.93)
    ops.add("text", id=title, parent=eid, text=g["title"], font=d.font("headline"), size=tsize, color=ink, position=[RX, r3(0.421 * H)],
            reveal={"times": [r3(E + 1.25 + 0.09 * i) for i in range(len(g["title"]))], "dur": 0.5, "rise": px(30), "blur": 6, "by": "chars"}, **sp)
    highlighter(ctx, id=f"{title}_HL", parent=eid, target=title, size=tsize, t0=E + 1.8, dur=0.6, color=d.color("accent"), pad=px(18), t_in=E)
    if g.get("tagline"):
        ops.add("text", id=f"{eid}_TAGLINE", parent=eid, text=g["tagline"], font=d.font("body"), size=ctx.size("body", 0.82), color=ink,
                position=[r3(RX + px(6)), r3(0.502 * H)],
                reveal={"times": [r3(E + 2.2 + 0.12 * i) for i in range(len(g["tagline"].split()))], "dur": 0.4, "rise": px(14), "blur": 6, "by": "words"}, **sp)
    y = 0.597 * H
    for r_i, row in enumerate(g.get("rows", [])):
        t0 = E + 2.8 + r_i * 0.3
        ops.add("text", id=f"{eid}_ROW{r_i + 1}_LABEL", parent=eid, text=row["label"], font=d.font("label"), size=ctx.size("label"),
                color=d.color("accent2"), position=[r3(RX + px(6)), r3(y)],
                reveal={"times": [r3(t0)], "dur": 0.35, "rise": px(10), "blur": 3, "by": "words"}, **sp)
        for v_i, value in enumerate(row["values"]):
            ops.add("text", id=f"{eid}_ROW{r_i + 1}_VALUE{v_i + 1}", parent=eid, text=value, font=d.font("body"), size=ctx.size("body", 0.64),
                    color=ink, position=[r3(RX + px(390)), r3(y)],
                    reveal={"times": [r3(t0 + 0.12 + 0.06 * k) for k in range(len(value.split()))], "dur": 0.35, "rise": px(10), "blur": 3, "by": "words"}, **sp)
            y += px(92)
        y += px(40)
    logo = g.get("logo")
    if logo:
        t = r3(E + 3.9)
        ops.add("image", id=f"{eid}_LOGO", parent=eid, file=logo["file"], width=px(logo.get("width", 560)),
                position=[r3(W - px(430)), px(250)], tint=ink if logo.get("tint", True) else None,
                expr={"opacity": f"100*so((time-{t})/0.5)", "anchor": f"value+[0,-40*(1-so((time-{t})/0.6))]"}, **sp)
```

`_page(ctx, eid, E, None, …)` passes `t_out=None`, so the end-card paper runs to the end of the comp.

Check against the test: rules count `int((2160 − 135) // 90) + 1 = 23`. Title words: line 1 `함께`, `배우고,` at 1.0, 1.09 → t = 1.18 + 0.35 = 1.53; line 2 `함께` 1.53, `자라는` 1.62, `시간` 1.71 → last word 1.71 → ref starts 2.51. Highlight on `자라는`: 1.62 + 0.45 = 2.07. Row 2 value 2 sits 92 px below value 1. Logo fades in at 30 + 3.9 = 33.9.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_notebook_pages tests.test_notebook -v`
Expected: 7 tests OK

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/components/notebook.py engine/tests/test_notebook_pages.py
git commit -m "feat(designs): notebook title page and polaroid end card"
```

---
### Task 13: Cinematic-minimal treatments and registry coverage

**Files:**
- Create: `engine/aestudio/components/cinematic.py`
- Modify: `engine/aestudio/components/__init__.py` (import `cinematic` next to `notebook`)
- Test: `engine/tests/test_cinematic.py`

**Interfaces:**
- Consumes: same as Tasks 11–12; graphic contracts are identical (the edit plan never changes when the design changes).
- Produces: registered `("caption","line-fade")`, `("quote","line-fade")`, `("lower-third","rule-wipe")`, `("title-page","black-frame")`, `("end-card","centered-stack")`. Look: no backing cards; centred lines fading up word by word with soft blur and a drop shadow for legibility; highlights change colour to `accent` instead of a marker; quotes wrapped in “ ”; accent rule that wipes in above the lower-third name; title on a black frame that dips out; end card over blurred, darkened footage with a centred stack and info rows as columns.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_cinematic.py`:

```python
import unittest

from aestudio.components import REGISTRY
from aestudio.design import COMPONENTS, load_design
from aestudio.ops import validate_ops
from tests.helpers import make_ctx, voice

WORDS = [("모든", 0.10, 0.50), ("여정은", 0.50, 1.10), ("작은", 1.20, 1.60), ("한", 1.60, 1.80),
         ("걸음에서", 1.80, 2.60), ("시작됩니다.", 2.60, 3.50)]
LINES = [["모든 여정은"], ["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]]


def run(graphic, treatment, **ctx_kw):
    ctx = make_ctx("cinematic-minimal", voices={"N1": voice("N1", 10.0, WORDS)}, **ctx_kw)
    REGISTRY[(graphic["type"], treatment)](ctx, graphic, {})
    validate_ops(ctx.ops.items)
    return ctx, {o.get("id"): o for o in ctx.ops.items}


class CinematicTest(unittest.TestCase):
    def test_every_design_treatment_is_registered(self):
        for ref in ("notebook", "cinematic-minimal"):
            design = load_design(ref)
            for comp in COMPONENTS:
                self.assertIn((comp, design.treatment(comp)[0]), REGISTRY, f"{ref}: {comp}")

    def test_caption_line_fade(self):
        ctx, it = run({"type": "caption", "voice": "N1", "lines": LINES}, "line-fade")
        self.assertEqual(it["CAPTION_01_L1"]["position"], [1920.0, it["CAPTION_01_L1"]["position"][1]])
        hl = it["CAPTION_01_L2S2"]
        self.assertEqual(hl["color"], ctx.design.color("accent"))
        self.assertEqual(hl["font"], "NanumSquareNeoTTF-cBd")
        self.assertEqual(it["CAPTION_01_L1S1"]["color"], ctx.design.color("ink"))
        self.assertNotIn("CAPTION_01_CARD", it)
        shadows = [o for o in ctx.ops.items if o["op"] == "effect" and o["match"] == "ADBE Drop Shadow"]
        self.assertEqual(len(shadows), 4)
        self.assertIn("so((time-9.7)/0.5)", it["CAPTION_01"]["fade"])

    def test_quote_is_wrapped_in_marks(self):
        _, it = run({"type": "quote", "voice": "N1", "lines": LINES}, "line-fade")
        self.assertEqual(it["QUOTE_01_L1S1"]["text"], "“")
        last = [k for k in it if k and k.startswith("QUOTE_01_L2S")][-1]
        self.assertEqual(it[last]["text"], "”")

    def test_lower_third_rule_wipe(self):
        ctx, it = run({"type": "lower-third", "at": 5, "name": "이하늘", "role": "스튜디오 참가자"}, "rule-wipe")
        self.assertIn("eio((time-5.1)/0.6)", it["LOWER_THIRD_01_RULE"]["rect_expr"]["size"])
        self.assertEqual(it["LOWER_THIRD_01_NAME"]["reveal"]["by"], "chars")
        self.assertEqual(it["LOWER_THIRD_01_ROLE"]["tracking"], 120)

    def test_title_black_frame(self):
        _, it = run({"type": "title-page", "in": 0, "out": 6, "lines": [["함께 배우고,"]], "ref": "OPEN DAY"}, "black-frame")
        self.assertEqual(it["TITLE_01_BG"]["out"], 6.95)
        self.assertEqual(it["TITLE_01_L1"]["op"], "group")
        self.assertEqual(it["TITLE_01_REF"]["justify"], "center")

    def test_end_card_centered_stack(self):
        ctx, it = run({"type": "end-card", "in": 30, "title": "오픈 스튜디오", "year": 2027, "tagline": "누구나",
                       "rows": [{"label": "A", "values": ["1"]}, {"label": "B", "values": ["2", "3"]}, {"label": "C", "values": ["4"]}],
                       "photo": {"clip": "/tmp/c.mp4"}, "logo": {"file": "/tmp/l.png"}}, "centered-stack")
        self.assertEqual(it["END_01_BG"]["zoom"], 1.1)
        self.assertEqual([o["match"] for o in ctx.ops.items if o["op"] == "effect" and o["layer"] == "END_01_BG"], ["ADBE Gaussian Blur 2"])
        xs = [it[f"END_01_ROW{i}_LABEL"]["position"][0] for i in (1, 2, 3)]
        self.assertEqual(xs, [960.0, 1920.0, 2880.0])
        self.assertEqual(it["END_01_TITLE"]["justify"], "center")
        self.assertTrue(all(o["position"][1] < 2160 for o in ctx.ops.items if o["op"] == "text"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_cinematic -v`
Expected: FAIL `test_every_design_treatment_is_registered` (`('caption', 'line-fade')` not found) and `KeyError` in the others.

- [ ] **Step 3: Write the treatments**

`engine/aestudio/components/cinematic.py`:

```python
"""Cinematic Minimal treatments: centred lines that fade up, accent-colour emphasis, rule-wipe lower third,
black-frame title and a centred end card over blurred footage."""
from ..util import r3
from . import register
from .layout import fade_ref, parse_line, place_block, schedule_times, segment_times, span, text_block


def _shadow(ctx, layer_id):
    ctx.ops.add("effect", layer=layer_id, match="ADBE Drop Shadow", props={"2": 90, "3": 180, "4": 0, "5": ctx.px(36)})


@register("caption", "line-fade")
@register("quote", "line-fade")
def caption_line_fade(ctx, g, opts):
    d, ops = ctx.design, ctx.ops
    quote = g["type"] == "quote"
    vt = ctx.voices[g["voice"]]
    t_in = r3(g.get("in", vt.onset - 0.4))
    t_out = r3(g.get("out", vt.offset + 0.6))
    base = "quote" if quote else "body"
    raw = [list(line) for line in g["lines"]]
    if quote:
        raw[0] = ["“"] + raw[0]
        raw[-1] = raw[-1] + ["”"]
    lines = [parse_line(line, ctx.size(base, 0.3)) for line in raw]
    gap = r3(ctx.size(base) * 1.45)
    x, y0, align = place_block(g.get("place", "lower-center"), len(lines), gap, ctx.width, ctx.height)
    cid = ops.uid("QUOTE" if quote else "CAPTION")
    ops.add("group", id=cid, fade=f"100*so((time-{t_in})/0.5)*(1-so((time-{r3(t_out - 0.5)})/0.5))",
            expr={"position": f"value+[0,{ctx.px(24)}*(1-so((time-{t_in})/0.8))]"})

    def style(i, seg):
        return {"font": d.font("emphasis" if seg.hl and not quote else base), "size": ctx.size(base),
                "color": d.color("accent" if seg.hl else "ink")}

    block = text_block(ctx, prefix=cid, parent=cid, lines=lines, times=segment_times(lines, vt.words), x=x, y_first=y0, gap=gap,
                       style=style, align=align, reveal={"dur": d.motion["word"], "rise": ctx.px(d.motion["rise"]), "blur": 10, "by": "words"},
                       opacity=fade_ref(cid), t_in=t_in, t_out=r3(t_out + 0.1))
    for sid in block.ids:
        _shadow(ctx, sid)


@register("lower-third", "rule-wipe")
def lower_third_rule_wipe(ctx, g, opts):
    d, ops, px = ctx.design, ctx.ops, ctx.px
    t_in = r3(g["at"])
    t_out = r3(t_in + g.get("dur", 4.25))
    x, y = r3(0.07 * ctx.width), r3(0.8 * ctx.height)
    lid = ops.uid("LOWER_THIRD")
    sp = span(t_in, t_out + 0.05)
    ops.add("group", id=lid, fade=f"100*(1-so((time-{r3(t_out - 0.6)})/0.6))")
    fade = fade_ref(lid)
    name_size = ctx.size("headline", 0.62)
    rule_w, rule_h, rule_y = px(360), px(4), r3(y - name_size - px(40))
    k = f"var k=eio((time-{r3(t_in + 0.1)})/0.6);"
    ops.add("rect", id=f"{lid}_RULE", parent=lid, color=d.color("accent"),
            rect_expr={"size": k + f"[{rule_w}*k,{rule_h}]", "center": k + f"[{x}+{rule_w}*k/2,{rule_y}]"},
            expr={"opacity": fade}, **sp)
    name, role = f"{lid}_NAME", f"{lid}_ROLE"
    ops.add("text", id=name, parent=lid, text=g["name"], font=d.font("headline"), size=name_size, color=d.color("ink"), position=[x, y],
            reveal={"times": [r3(t_in + 0.35 + 0.03 * i) for i in range(len(g["name"]))], "dur": 0.5, "rise": px(12), "blur": 8, "by": "chars"},
            expr={"opacity": fade}, **sp)
    ops.add("text", id=role, parent=lid, text=g["role"], font=d.font("label"), size=ctx.size("label"), color=d.color("accent"),
            tracking=120, position=[x, r3(y + px(90))],
            reveal={"times": [r3(t_in + 0.7 + 0.08 * i) for i in range(len(g["role"].split()))], "dur": 0.5, "rise": px(8), "blur": 6, "by": "words"},
            expr={"opacity": fade}, **sp)
    _shadow(ctx, name)
    _shadow(ctx, role)


@register("title-page", "black-frame")
def title_black_frame(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.95)
    tid = ops.uid("TITLE")
    ops.add("group", id=tid, fade=f"100*(1-so((time-{t_out})/0.6))")
    ops.add("rect", id=f"{tid}_BG", parent=tid, color=d.color("shade"), size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": f"100*(1-so((time-{r3(t_out + 0.3)})/0.6))"}, **span(t_in, end))
    size = ctx.size("scripture")
    lines = [parse_line(line, ctx.size("scripture", 0.3)) for line in g["lines"]]
    gap = r3(size * 1.5)
    y_first = r3(0.47 * H - (len(lines) - 1) * gap / 2)
    times = schedule_times(lines, start=t_in + 0.8, step=0.14, line_pause=0.4)
    fade = fade_ref(tid)
    text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=r3(W / 2), y_first=y_first, gap=gap,
               style=lambda i, s: {"font": d.font("scripture"), "size": size, "color": d.color("accent" if s.hl else "ink")},
               align="center", reveal={"dur": 0.9, "rise": 0, "blur": 14, "by": "words"}, opacity=fade, t_in=t_in, t_out=end)
    if g.get("ref"):
        start = times[-1][-1][-1] + 0.6
        ops.add("text", id=f"{tid}_REF", parent=tid, text=g["ref"], font=d.font("label"), size=ctx.size("label"), color=d.color("accent"),
                tracking=300, justify="center", position=[r3(W / 2), r3(y_first + len(lines) * gap + px(20))],
                reveal={"times": [r3(start + 0.03 * i) for i in range(len(g["ref"]))], "dur": 0.6, "rise": 0, "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **span(t_in, end))


@register("end-card", "centered-stack")
def end_card_centered_stack(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    E = r3(g["in"])
    eid = ops.uid("END")
    sp = span(E)
    ops.add("group", id=eid, fade=f"100*so((time-{E})/0.8)")
    fade = fade_ref(eid)
    cx = r3(W / 2)
    photo = g.get("photo")
    if photo:
        bg = f"{eid}_BG"
        ops.add("footage", id=bg, parent=eid, file=photo["clip"], start=E, end=r3(ctx.duration), src_in=photo.get("src_in", 0),
                stretch=photo.get("stretch"), zoom=1.1, position=[cx, r3(H / 2)], lumetri=dict(ctx.grade.get("lumetri", {})) or None,
                expr={"opacity": fade})
        ops.add("effect", layer=bg, match="ADBE Gaussian Blur 2", props={"1": px(60)})
    ops.add("rect", id=f"{eid}_SHADE", parent=eid, color=d.color("shade"), size=[r3(W + px(20)), r3(H + px(20))], center=[cx, r3(H / 2)],
            expr={"opacity": f"72*{fade}/100"}, **sp)

    def ctext(key, text, role, mult, colour, y, times, by, tracking=0, x=cx):
        ops.add("text", id=f"{eid}_{key}", parent=eid, text=text, font=d.font(role), size=ctx.size(role, mult), color=d.color(colour),
                tracking=tracking, justify="center", position=[r3(x), r3(y)],
                reveal={"times": times, "dur": 0.7, "rise": px(16), "blur": 8, "by": by}, expr={"opacity": fade}, **sp)

    logo = g.get("logo")
    if logo:
        ops.add("image", id=f"{eid}_LOGO", parent=eid, file=logo["file"], width=px(logo.get("width", 420)), position=[cx, r3(0.14 * H)],
                tint=d.color("ink") if logo.get("tint", True) else None,
                expr={"opacity": f"100*so((time-{r3(E + 0.4)})/0.8)*{fade}/100"}, **sp)
    if g.get("year") is not None:
        year = str(g["year"])
        ctext("YEAR", year, "label", 1.0, "accent", 0.30 * H, [r3(E + 0.6 + 0.05 * i) for i in range(len(year))], "chars", tracking=300)
    ctext("TITLE", g["title"], "headline", 1.6, "ink", 0.43 * H, [r3(E + 0.9 + 0.06 * i) for i in range(len(g["title"]))], "chars")
    k = f"var k=eio((time-{r3(E + 1.4)})/0.8);"
    ops.add("rect", id=f"{eid}_RULE", parent=eid, color=d.color("accent"),
            rect_expr={"size": k + f"[{px(520)}*k,{px(3)}]", "center": f"[{cx},{r3(0.43 * H + px(70))}]"}, expr={"opacity": fade}, **sp)
    if g.get("tagline"):
        ctext("TAGLINE", g["tagline"], "body", 1.0, "ink", 0.52 * H, [r3(E + 1.8 + 0.12 * i) for i in range(len(g["tagline"].split()))], "words")
    rows = g.get("rows", [])
    for r_i, row in enumerate(rows):
        col_x = W * (r_i + 1) / (len(rows) + 1)
        t0 = E + 2.4 + r_i * 0.25
        ctext(f"ROW{r_i + 1}_LABEL", row["label"], "label", 1.0, "accent", 0.66 * H, [r3(t0)], "words", tracking=120, x=col_x)
        for v_i, value in enumerate(row["values"]):
            ctext(f"ROW{r_i + 1}_VALUE{v_i + 1}", value, "body", 0.9, "ink", 0.66 * H + px(100) + v_i * px(84),
                  [r3(t0 + 0.15 + 0.06 * k2) for k2 in range(len(value.split()))], "words", x=col_x)
```

Change the import line at the bottom of `engine/aestudio/components/__init__.py` to:

```python
from . import cinematic, notebook  # noqa: E402,F401  (registers treatments)
```

Check against the test: caption onset 10.1 − 0.4 = 9.7. Line groups sit at x = 1920. Emphasis segment uses `NanumSquareNeoTTF-cBd` in `accent`. Four segments → four shadows. Quote: `“` becomes segment 1 of line 1, `”` the last segment of line 2. Rule wipe starts at 5.1. Title background ends at 6 + 0.95 = 6.95. End-card columns for three rows: 3840·k/4 → 960, 1920, 2880. The lowest value line is 0.66·2160 + 100 + 84 = 1609.6 < 2160.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest discover -s tests -t . -v`
Expected: all tests OK (6 new)

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/components engine/tests/test_cinematic.py
git commit -m "feat(designs): cinematic-minimal treatments; every design treatment registered"
```

---
### Task 14: aerender wrapper and command-line interface

**Files:**
- Create: `engine/aestudio/render.py`, `engine/aestudio/__main__.py`
- Test: `engine/tests/test_render.py`, `engine/tests/test_cli.py`

**Interfaces:**
- Consumes: `load_plan`, `PlanError` (Task 2); `TimingError` (Task 3); `load_design`, `DesignError` (Task 5); `OpsError` (Task 6); `emit_script`, `still_script` (Task 7); `Bridge`, `BridgeError` (Task 8); `compile_plan`, `CompileError` (Task 9); `LayoutError` (Task 10).
- Produces:
  - `class RenderError(RuntimeError)`; `find_aerender(apps=Path("/Applications")) -> Path` (newest `Adobe After Effects */aerender`); `aerender_cmd(aerender, project, comp, output, rs="Best Settings", om="High Quality", mem=(50, 70)) -> list[str]`; `ae_ui_running() -> bool`; `render(project, comp, output, rs="Best Settings", om="High Quality", allow_running_ae=False, aerender=None) -> Path` (log written next to the output as `<output>.log`).
  - CLI `python3 -m aestudio` (run from `engine/`, or with `PYTHONPATH=<repo>/engine`):
    - `validate PLAN --design D`
    - `compile PLAN --design D [--name NAME] [--project AEP] [--out JSX]` → prints `{"jsx", "ops", "fonts"}`; default out `<plan dir>/build/<name>.jsx`
    - `run JSX [--timeout S]` → prints the report; exit 1 if `ok` is false or `error` is set
    - `build PLAN --design D [--name] [--project] [--out] [--timeout]` → compile then run
    - `still --comp NAME --time T --out PNG [--timeout]` → waits (≤ 60 s) for the PNG
    - `render --project AEP --comp NAME --out FILE [--rs] [--om] [--allow-running-ae]`
    - Known errors print `error: …` to stderr and exit 2.

- [ ] **Step 1: Write the failing tests**

`engine/tests/test_render.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aestudio import render as r


class RenderTest(unittest.TestCase):
    def test_find_aerender_picks_newest(self):
        with tempfile.TemporaryDirectory() as d:
            for year in ("2025", "2026"):
                p = Path(d) / f"Adobe After Effects {year}"
                p.mkdir()
                (p / "aerender").write_text("")
            self.assertEqual(r.find_aerender(Path(d)).parent.name, "Adobe After Effects 2026")
            with self.assertRaises(r.RenderError):
                r.find_aerender(Path(d) / "nothing")

    def test_cmd(self):
        cmd = r.aerender_cmd("/ae/aerender", "/p.aep", "DEMO", "/out/a.mov")
        self.assertEqual(cmd, ["/ae/aerender", "-project", "/p.aep", "-comp", "DEMO", "-RStemplate", "Best Settings",
                               "-OMtemplate", "High Quality", "-output", "/out/a.mov", "-mem_usage", "50", "70",
                               "-v", "ERRORS_AND_PROGRESS"])

    def test_refuses_when_after_effects_is_open(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "p.aep"
            project.write_text("x")
            with mock.patch.object(r, "ae_ui_running", return_value=True):
                with self.assertRaisesRegex(r.RenderError, "After Effects is open"):
                    r.render(project, "DEMO", Path(d) / "a.mov", aerender="/bin/true")

    def test_render_success_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            project, out = Path(d) / "p.aep", Path(d) / "exports" / "a.mov"
            project.write_text("x")
            fake = Path(d) / "fake_aerender.sh"
            fake.write_text('#!/bin/sh\nwhile [ "$1" != "-output" ]; do shift; done\necho rendered > "$2"\n')
            fake.chmod(0o755)
            with mock.patch.object(r, "ae_ui_running", return_value=False):
                self.assertEqual(r.render(project, "DEMO", out, aerender=str(fake)), out.resolve())
                self.assertTrue(out.with_name("a.mov.log").exists())
                with self.assertRaisesRegex(r.RenderError, "aerender failed"):
                    r.render(project, "DEMO", Path(d) / "b.mov", aerender="/usr/bin/false")


if __name__ == "__main__":
    unittest.main()
```

`engine/tests/test_cli.py`:

```python
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from aestudio.__main__ import main


def write_min_plan(root: Path) -> Path:
    for f in ("a.mp4", "n1.wav"):
        (root / f).write_text("x")
    (root / "n1.json").write_text(json.dumps({"words": [["모든", 0.1, 0.5], ["여정은", 0.5, 1.1]]}))
    plan = {"name": "CLI_DEMO", "format": {"duration": 10}, "shots": [{"clip": "a.mp4", "in": 0, "out": 10}],
            "voices": [{"id": "N1", "file": "n1.wav", "at": 1, "transcript": "n1.json"}],
            "graphics": [{"type": "caption", "voice": "N1", "lines": [["모든 여정은"]]}]}
    (root / "edit.json").write_text(json.dumps(plan))
    return root / "edit.json"


class CliTest(unittest.TestCase):
    def test_compile_writes_jsx(self):
        with tempfile.TemporaryDirectory() as d:
            plan = write_min_plan(Path(d))
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["compile", str(plan), "--design", "notebook"])
            self.assertEqual(code, 0)
            info = json.loads(out.getvalue())
            self.assertTrue(info["jsx"].endswith("build/CLI_DEMO.jsx"))
            self.assertIn("Paperlogy-5Medium", info["fonts"])
            self.assertIn("AES.build(", Path(info["jsx"]).read_text(encoding="utf-8"))

    def test_known_error_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["compile", "/nope/edit.json", "--design", "notebook"])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())

    def test_run_exit_code_follows_report(self):
        with tempfile.TemporaryDirectory() as d:
            jsx = Path(d) / "x.jsx"
            jsx.write_text("1")
            for report, expected in (({"ok": True}, 0), ({"ok": False, "expressionErrors": ["x"]}, 1)):
                with mock.patch("aestudio.__main__.Bridge") as bridge, redirect_stdout(io.StringIO()):
                    bridge.return_value.run.return_value = report
                    self.assertEqual(main(["run", str(jsx)]), expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python3 -m unittest tests.test_render tests.test_cli -v`
Expected: ERROR `cannot import name 'render'` / `No module named 'aestudio.__main__'`

- [ ] **Step 3: Write the implementation**

`engine/aestudio/render.py`:

```python
"""Final renders with aerender (After Effects' command-line renderer), never a scripted UI render."""
import subprocess
from pathlib import Path


class RenderError(RuntimeError):
    pass


def find_aerender(apps: Path = Path("/Applications")) -> Path:
    found = sorted(Path(apps).glob("Adobe After Effects */aerender"), reverse=True)
    if not found:
        raise RenderError(f"aerender not found under {apps}/Adobe After Effects */")
    return found[0]


def aerender_cmd(aerender, project, comp, output, rs="Best Settings", om="High Quality", mem=(50, 70)) -> list:
    return [str(aerender), "-project", str(project), "-comp", comp, "-RStemplate", rs, "-OMtemplate", om,
            "-output", str(output), "-mem_usage", str(mem[0]), str(mem[1]), "-v", "ERRORS_AND_PROGRESS"]


def ae_ui_running() -> bool:
    return subprocess.run(["pgrep", "-f", "MacOS/After Effects"], capture_output=True).returncode == 0


def render(project, comp, output, rs="Best Settings", om="High Quality", allow_running_ae=False, aerender=None) -> Path:
    project, output = Path(project).resolve(), Path(output).resolve()
    if not project.exists():
        raise RenderError(f"project not found: {project}")
    if not allow_running_ae and ae_ui_running():
        raise RenderError("After Effects is open. Save the project and quit After Effects first: aerender runs its own copy, "
                          "and a UI render can freeze. Use --allow-running-ae to override.")
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_name(output.name + ".log")
    cmd = aerender_cmd(aerender or find_aerender(), project, comp, output, rs, om)
    with open(log, "w", encoding="utf-8") as fh:
        result = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    if result.returncode != 0 or not output.exists():
        raise RenderError(f"aerender failed (exit {result.returncode}); see {log}")
    return output
```

`engine/aestudio/__main__.py`:

```python
"""ae-video-studio command line: python3 -m aestudio <command> ..."""
import argparse
import json
import sys
import time
from pathlib import Path

from .bridge import Bridge, BridgeError
from .compiler import CompileError, compile_plan
from .components.layout import LayoutError
from .design import DesignError, load_design
from .jsx import emit_script, still_script
from .ops import OpsError
from .plan import PlanError, load_plan
from .render import RenderError, render
from .timing import TimingError

KNOWN = (PlanError, DesignError, TimingError, LayoutError, OpsError, CompileError, BridgeError, RenderError, OSError)


def _compile(a) -> Path:
    plan = load_plan(a.plan)
    if a.name:
        plan.name = a.name
    design = load_design(a.design)
    ops = compile_plan(plan, design)
    project = str(Path(a.project).resolve()) if a.project else (str(plan.project) if plan.project else None)
    out = Path(a.out).resolve() if a.out else plan.root / "build" / f"{plan.name}.jsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(emit_script(ops, project=project), encoding="utf-8")
    print(json.dumps({"jsx": str(out), "ops": len(ops), "fonts": sorted(design.fonts())}, ensure_ascii=False))
    return out


def _report_ok(result) -> bool:
    return not (isinstance(result, dict) and (result.get("error") or result.get("ok") is False))


def cmd_validate(a):
    plan, design = load_plan(a.plan), load_design(a.design)
    print(json.dumps({"name": plan.name, "duration": plan.format.duration, "shots": len(plan.shots), "voices": len(plan.voices),
                      "graphics": len(plan.graphics), "design": design.id, "fonts": sorted(design.fonts())}, ensure_ascii=False))
    return 0


def cmd_compile(a):
    _compile(a)
    return 0


def cmd_run(a):
    result = Bridge().run(Path(a.jsx).read_text(encoding="utf-8"), timeout=a.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if _report_ok(result) else 1


def cmd_build(a):
    a.jsx = str(_compile(a))
    return cmd_run(a)


def cmd_still(a):
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    result = Bridge().run(still_script(a.comp, a.time, str(out)), timeout=a.timeout)
    if not _report_ok(result):
        print(json.dumps(result), file=sys.stderr)
        return 1
    deadline, last = time.monotonic() + 60, -1
    while time.monotonic() < deadline:            # saveFrameToPng returns before the file is written
        size = out.stat().st_size if out.exists() else -1
        if size > 0 and size == last:
            print(str(out))
            return 0
        last = size
        time.sleep(1)
    print(f"error: frame was not written to {out}", file=sys.stderr)
    return 1


def cmd_render(a):
    print(str(render(a.project, a.comp, a.out, rs=a.rs, om=a.om, allow_running_ae=a.allow_running_ae)))
    return 0


def parser():
    p = argparse.ArgumentParser(prog="aestudio")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("plan")
    v.add_argument("--design", required=True)
    v.set_defaults(fn=cmd_validate)
    for name, fn in (("compile", cmd_compile), ("build", cmd_build)):
        c = sub.add_parser(name)
        c.add_argument("plan")
        c.add_argument("--design", required=True)
        c.add_argument("--name")
        c.add_argument("--project")
        c.add_argument("--out")
        c.add_argument("--timeout", type=float, default=900)
        c.set_defaults(fn=fn)
    r = sub.add_parser("run")
    r.add_argument("jsx")
    r.add_argument("--timeout", type=float, default=900)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("still")
    s.add_argument("--comp", required=True)
    s.add_argument("--time", type=float, required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--timeout", type=float, default=120)
    s.set_defaults(fn=cmd_still)
    e = sub.add_parser("render")
    e.add_argument("--project", required=True)
    e.add_argument("--comp", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--rs", default="Best Settings")
    e.add_argument("--om", default="High Quality")
    e.add_argument("--allow-running-ae", action="store_true")
    e.set_defaults(fn=cmd_render)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.fn(args)
    except KNOWN as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python3 -m unittest discover -s tests -t . -v`
Expected: all tests OK (7 new)

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/render.py engine/aestudio/__main__.py engine/tests/test_render.py engine/tests/test_cli.py
git commit -m "feat(engine): aerender wrapper and aestudio CLI"
```

---
### Task 15: Fictional demo project and component contracts

**Files:**
- Create: `examples/demo/make_media.py`, `examples/demo/edit.json`
- Create: `docs/components.md`
- Modify: `.gitignore` (ignore generated demo media, transcripts and builds)
- Test: `engine/tests/test_demo.py`

**Interfaces:**
- Consumes: `load_plan`, `load_design`, `compile_plan`, `emit_script`.
- Produces: `python3 examples/demo/make_media.py` writes `examples/demo/media/{shot_a,shot_b,shot_c,shot_d}.mp4` (1920×1080, 24 fps, 14 s moving gradients), `narration-1.wav`, `interview-1.wav`, `narration-2.wav` (a tone burst per word, so sync is visible and audible), `music.wav` (45 s soft chord), `whoosh.wav` (0.8 s filtered noise) and matching `examples/demo/transcripts/*.json`. `edit.json` is a 40 s fictional promo using every graphic type and `examples/sample-logo-white.png`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_demo.py`:

```python
import subprocess
import sys
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.design import load_design
from aestudio.jsx import emit_script
from aestudio.plan import load_plan

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo"


class DemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEMO / "transcripts" / "narration-1.json").exists():
            subprocess.run([sys.executable, str(DEMO / "make_media.py")], check=True)

    def test_demo_compiles_with_both_designs(self):
        plan = load_plan(DEMO / "edit.json")
        self.assertEqual({g["type"] for g in plan.graphics}, {"title-page", "caption", "quote", "lower-third", "end-card"})
        for ref in ("notebook", "cinematic-minimal"):
            ops = compile_plan(plan, load_design(ref))
            self.assertIn("AES.build(", emit_script(ops))
            self.assertGreater(len(ops), 60, ref)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_demo -v`
Expected: ERROR — `examples/demo/make_media.py` does not exist

- [ ] **Step 3: Write the demo generator and plan**

`examples/demo/make_media.py`:

```python
"""Generate fictional demo media for ae-video-studio (needs ffmpeg). Output is git-ignored."""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEDIA, TRANSCRIPTS = HERE / "media", HERE / "transcripts"

VOICES = {
    "narration-1": "모든 여정은 작은 한 걸음에서 시작됩니다.",
    "interview-1": "처음에는 망설였지만 함께하니 용기가 생겼어요.",
    "narration-2": "이번 가을, 당신의 첫 걸음을 기다립니다.",
}
SHOTS = {"shot_a": ("0x2b4162", "0xfa9f42"), "shot_b": ("0x0b6e4f", "0xf2e8cf"),
         "shot_c": ("0x6a4c93", "0xffca3a"), "shot_d": ("0x1d3557", "0xe63946")}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def word_timings(text, lead=0.15):
    t, words = lead, []
    for w in text.split():
        dur = round(0.12 * len(w) + 0.1, 3)
        words.append([w, round(t, 3), round(t + dur, 3)])
        t += dur + 0.08
    return words


def main():
    MEDIA.mkdir(exist_ok=True)
    TRANSCRIPTS.mkdir(exist_ok=True)
    for name, (c0, c1) in SHOTS.items():
        ffmpeg("-f", "lavfi", "-i", f"gradients=s=1920x1080:r=24:d=14:c0={c0}:c1={c1}:speed=0.015",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(MEDIA / f"{name}.mp4"))
    for name, text in VOICES.items():
        words = word_timings(text)
        gate = "+".join(f"between(t,{s},{e})" for _, s, e in words)
        total = words[-1][2] + 0.4
        ffmpeg("-f", "lavfi", "-i", f"aevalsrc='0.35*({gate})*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*6*t))':s=48000:d={total}",
               "-ac", "2", str(MEDIA / f"{name}.wav"))
        (TRANSCRIPTS / f"{name}.json").write_text(
            json.dumps({"onset": words[0][1], "offset": words[-1][2], "words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
    ffmpeg("-f", "lavfi", "-i", "aevalsrc='0.08*sin(2*PI*220*t)+0.06*sin(2*PI*277.18*t)+0.05*sin(2*PI*329.63*t)':s=48000:d=45",
           "-af", "afade=t=in:d=2,afade=t=out:st=42:d=3", "-ac", "2", str(MEDIA / "music.wav"))
    ffmpeg("-f", "lavfi", "-i", "anoisesrc=color=pink:d=0.8:a=0.4", "-af", "lowpass=f=1800,afade=t=in:d=0.3,afade=t=out:st=0.4:d=0.4",
           "-ac", "2", "-ar", "48000", str(MEDIA / "whoosh.wav"))
    print(f"demo media written to {MEDIA}")


if __name__ == "__main__":
    main()
```

`examples/demo/edit.json`:

```json
{
  "name": "DEMO",
  "format": {"width": 3840, "height": 2160, "fps": 23.976, "duration": 40},
  "grade": {"lumetri": {"23": 10, "17": 104}},
  "shots": [
    {"clip": "media/shot_a.mp4", "in": 0, "out": 14},
    {"clip": "media/shot_b.mp4", "in": 14, "out": 21},
    {"clip": "media/shot_c.mp4", "in": 21, "out": 28, "exposure": 0.1},
    {"clip": "media/shot_d.mp4", "in": 28, "out": 40}
  ],
  "voices": [
    {"id": "N1", "file": "media/narration-1.wav", "at": 8.0, "transcript": "transcripts/narration-1.json"},
    {"id": "I1", "file": "media/interview-1.wav", "at": 15.2, "transcript": "transcripts/interview-1.json"},
    {"id": "N2", "file": "media/narration-2.wav", "at": 23.5, "transcript": "transcripts/narration-2.json"}
  ],
  "music": {"file": "media/music.wav", "gain_db": -6, "duck": {"under_voice": -14, "breath": -10, "swell": -5, "tail": -3}},
  "sfx": [
    {"file": "media/whoosh.wav", "at": 6.4, "gain_db": -8},
    {"file": "media/whoosh.wav", "at": 30.95, "gain_db": -6}
  ],
  "graphics": [
    {"type": "title-page", "in": 0, "out": 6.5, "lines": [["함께 배우고,"], ["함께 ", {"hl": "자라는"}, " 시간"]], "ref": "OPEN STUDIO DAY"},
    {"type": "caption", "voice": "N1", "lines": [["모든 여정은"], ["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]]},
    {"type": "lower-third", "at": 15.0, "name": "이하늘", "role": "스튜디오 참가자"},
    {"type": "quote", "voice": "I1", "lines": [["처음에는 ", {"hl": "망설였지만"}], ["함께하니 용기가 생겼어요."]]},
    {"type": "caption", "voice": "N2", "lines": [["이번 가을,"], ["당신의 ", {"hl": "첫 걸음"}, "을 기다립니다."]]},
    {"type": "end-card", "in": 31.0, "title": "오픈 스튜디오", "year": 2027, "tagline": "누구나 시작할 수 있는 자리",
     "rows": [{"label": "신청 기간", "values": ["9월 1일 – 9월 20일"]},
              {"label": "일정", "values": ["10월 매주 토요일 10시", "커뮤니티 홀"]},
              {"label": "문의", "values": ["사무실 · 010-0000-0000"]}],
     "photo": {"clip": "media/shot_c.mp4", "src_in": 2},
     "logo": {"file": "../sample-logo-white.png", "tint": true}}
  ],
  "fade_out": 0.75
}
```

Append to `.gitignore`:

```
# generated demo media and builds
examples/demo/media/
examples/demo/transcripts/
examples/demo/build/
```

Note on the caption `"이번 가을,"` line: the transcript word is `가을,`; alignment ignores punctuation, so both match.

- [ ] **Step 4: Write the component contracts**

`docs/components.md`:

````markdown
# Component contracts

Every design implements the same five components, so an edit plan works with any design.
Times are seconds on the timeline. Pixel values in designs are authored for 3840×2160 and scale with the comp width.

## Text segments

A line is a list of segments: plain strings, or `{"hl": "text"}` for the emphasised phrase.
Whitespace at a segment edge becomes a word gap; no whitespace means the segments touch, which is how
Korean particles attach to a highlighted word: `["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]`.
Word reveal times come from the voice transcript by matching letters, so caption text must follow the
spoken words (punctuation and extra spoken words are ignored).

## caption / quote

```json
{"type": "caption", "voice": "N1", "lines": [[...], [...]], "place": "bottom-left", "in": 9.7, "out": 14.0}
```

- `voice` (required): id from `voices`; words reveal as they are spoken.
- `place`: `bottom-left | top-left | bottom-right | top-right | lower-center | top-center | center`
  (caption default `bottom-left`; quote default `top-right`; treatments may override the default).
- `in` / `out`: default a little before the voice onset and after its offset.

## lower-third

```json
{"type": "lower-third", "at": 15.0, "dur": 4.25, "name": "Name", "role": "Role or title"}
```

## title-page

```json
{"type": "title-page", "in": 0, "out": 6.5, "lines": [[...]], "ref": "Reference or kicker"}
```

`out` is when the page starts leaving. There is no voice: words reveal on a schedule.

## end-card

```json
{"type": "end-card", "in": 31.0, "title": "Title", "year": 2027, "tagline": "One line",
 "rows": [{"label": "Label", "values": ["line 1", "line 2"]}],
 "photo": {"clip": "media/c.mp4", "src_in": 2, "stretch": 140},
 "logo": {"file": "logo.png", "tint": true, "width": 560}}
```

Runs until the end of the video. Keep 1–3 rows with 1–2 values each. `tint: true` recolours a
single-colour logo to the design's ink colour; use `false` for multi-colour logos.

## Treatments

| Component | notebook | cinematic-minimal |
|---|---|---|
| caption, quote | `paper-card` | `line-fade` |
| lower-third | `paper-tab` | `rule-wipe` |
| title-page | `notebook-page` | `black-frame` |
| end-card | `notebook-page` | `centered-stack` |

A new treatment is a function registered with `@register(component, treatment)` in
`engine/aestudio/components/`, built only from ops and the helpers in `layout.py`.
````

- [ ] **Step 5: Generate media and run the test**

Run: `python3 examples/demo/make_media.py && cd engine && python3 -m unittest tests.test_demo -v`
Expected: `demo media written to …/examples/demo/media`, then 1 test OK

- [ ] **Step 6: Commit**

```bash
git add examples/demo/make_media.py examples/demo/edit.json docs/components.md .gitignore engine/tests/test_demo.py
git commit -m "docs: component contracts and fictional demo project"
```

---
### Task 16: Live After Effects verification, `ae-build-render` skill and README

**Files:**
- Create: `engine/tests/ae/__init__.py`, `engine/tests/ae/test_demo_in_after_effects.py`
- Create: `skills/ae-build-render/SKILL.md`
- Modify: `README.md` (engine usage), remove `skills/.gitkeep`

**Interfaces:**
- Consumes: the CLI (Task 14) and demo (Task 15).
- Produces: an opt-in live test (`AESTUDIO_AE=1`) that builds the demo in both designs through the bridge and saves review stills; the first real skill of the plugin.

- [ ] **Step 1: Write the live test**

`engine/tests/ae/__init__.py` is empty. `engine/tests/ae/test_demo_in_after_effects.py`:

```python
"""Live test: needs After Effects open with the MCP Bridge Auto panel (Auto-run on) and a NEW, unsaved project.

Run from engine/:  AESTUDIO_AE=1 python3 -m unittest tests.ae.test_demo_in_after_effects -v
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from aestudio.__main__ import main

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "examples" / "demo"
STILLS = DEMO / "build" / "stills"
TIMES = (3.5, 10.5, 16.5, 25.0, 37.0)   # title, caption, lower third + quote, caption, end card


@unittest.skipUnless(os.environ.get("AESTUDIO_AE") == "1", "set AESTUDIO_AE=1 with After Effects open")
class DemoInAfterEffects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEMO / "media" / "shot_a.mp4").exists():
            subprocess.run([sys.executable, str(DEMO / "make_media.py")], check=True)

    def test_build_both_designs_and_save_stills(self):
        project = DEMO / "build" / "demo.aep"
        for ref in ("notebook", "cinematic-minimal"):
            comp = f"DEMO_{ref.upper().replace('-', '_')}"
            code = main(["build", str(DEMO / "edit.json"), "--design", ref, "--name", comp, "--project", str(project), "--timeout", "900"])
            self.assertEqual(code, 0, f"{ref}: build report not ok (see printed report)")
            for t in TIMES:
                out = STILLS / f"{ref}_{t:05.1f}.png"
                self.assertEqual(main(["still", "--comp", comp, "--time", str(t), "--out", str(out)]), 0)
                self.assertGreater(out.stat().st_size, 10_000)
        self.assertTrue(project.exists())
```

- [ ] **Step 2: Confirm it is skipped by default**

Run: `cd engine && python3 -m unittest discover -s tests -t . -v 2>&1 | tail -5`
Expected: all tests OK, `skipped=1` for `DemoInAfterEffects`

- [ ] **Step 3: Run it against After Effects (manual gate)**

Preconditions: After Effects open, **File → New → New Project** (unsaved), MCP Bridge Auto panel open with Auto-run on, Premiere Pro closed, fonts installed (Paperlogy, MaruBuri, NanumSquareNeo).

Run: `cd engine && AESTUDIO_AE=1 python3 -m unittest tests.ae.test_demo_in_after_effects -v`
Expected: 1 test OK; `examples/demo/build/demo.aep` saved; 10 PNGs in `examples/demo/build/stills/`.

If the report shows `expressionErrors`, `missingFonts` or an `error` naming an op, fix the treatment or runtime, add a unit test that reproduces the problem where possible, and re-run. Do not continue until the report is clean.

Then open the stills and check, for **each** design:
1. Title page: text readable, highlight sits behind the highlighted phrase only.
2. Captions: words appear left to right; card (notebook) wraps all lines with even padding; centred lines (cinematic) are centred.
3. Lower third and quote do not overlap each other at 16.5 s.
4. End card: nothing clipped at the frame edges; logo tinted; rows aligned.
5. The two designs look clearly different.

Show the stills to the user (this is a review gate) before Step 4.

- [ ] **Step 4: Render one review file with aerender**

Close After Effects (save the project first), then:

Run: `cd engine && python3 -m aestudio render --project ../examples/demo/build/demo.aep --comp DEMO_NOTEBOOK --out ../examples/demo/build/DEMO_NOTEBOOK.mov`
Expected: prints the output path; `ffprobe` shows 3840×2160 video with audio, duration ≈ 40 s. Listen for the music dipping before each voice.

- [ ] **Step 5: Write the skill**

`skills/ae-build-render/SKILL.md`:

````markdown
---
name: ae-build-render
description: Build an After Effects comp from an ae-video-studio edit plan (plan/edit.json) and a design, save review stills, and render with aerender. Use when a video's edit plan and design are approved and the user wants a test build, stills, a review render or the final master.
---

# Build and render in After Effects

The engine lives in `${CLAUDE_PLUGIN_ROOT}/engine`. Run commands with
`PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`.

## Before building

1. After Effects is open with the **MCP Bridge Auto** panel, Auto-run on.
2. The open project is either the video's own project (`--project` path) or a new unsaved one. The build refuses to touch any other project.
3. Premiere Pro is closed. Busy Premiere and After Effects can freeze each other.
4. `python3 -m aestudio validate plan/edit.json --design <design>` passes, and every font it lists is installed.

## Commands

| Goal | Command |
|---|---|
| Build the comp | `build plan/edit.json --design <id or path> --project build/<name>.aep` |
| Only generate the script | `compile plan/edit.json --design <id>` then `run build/<NAME>.jsx` |
| Review stills | `still --comp <NAME> --time <s> --out preview/<file>.png` (one per call) |
| Review or master render | quit After Effects, then `render --project build/<name>.aep --comp <NAME> --out exports/<file>.mov` |

## Rules

- One bridge job at a time. If a command reports the bridge is busy, wait; never submit in parallel.
- Read the build report. It is not done unless `ok` is true: fix `expressionErrors`, `missingFonts` or `error` first.
- Show stills to the user before any long render (docs/design.md gates 4–5).
- Renders always use `render` (aerender) with After Effects closed. Never script `renderQueue.render()` for long renders: it locks the After Effects UI and can freeze it.
- Tell the user before closing After Effects. A forced quit looks like a crash to them.
- `render` defaults to the "High Quality" output template (ProRes 422 on After Effects 2026). Make H.264 delivery copies from the master with ffmpeg.
````

- [ ] **Step 6: Update README**

Replace the `## Local development` section of `README.md` with:

````markdown
## Engine quick start

```bash
python3 examples/demo/make_media.py                    # fictional demo media (needs ffmpeg)
cd engine
python3 -m unittest discover -s tests -t . -v          # unit tests (no After Effects needed)
python3 -m aestudio validate ../examples/demo/edit.json --design notebook
# with After Effects + MCP Bridge Auto panel open and a new project:
python3 -m aestudio build ../examples/demo/edit.json --design cinematic-minimal --project ../examples/demo/build/demo.aep
```

See `docs/components.md` for the edit-plan graphics and `skills/ae-build-render/SKILL.md` for the full workflow.

## Local plugin install

```
/plugin marketplace add ~/github.com/Exotica0122/ae-video-studio
/plugin install ae-video-studio@ae-video-studio-dev
```
````

- [ ] **Step 7: Run all tests and commit**

Run: `cd engine && python3 -m unittest discover -s tests -t . -v`
Expected: all OK, 1 skipped

```bash
git rm -q --cached skills/.gitkeep; rm -f skills/.gitkeep
git add engine/tests/ae skills/ae-build-render README.md
git commit -m "feat: live After Effects demo test, ae-build-render skill and engine README"
```

---

## Out of scope for this milestone (later plans)

`audio-post` (voice cleanup, music editing), `footage-logging`, `color-grade` look previews, gate-2 style frames and font pairing previews (`design-system`), `video-director` orchestration, `studio-doctor`, bundling the MCP bridge in `.mcp.json`. The parity rebuild of the first real production happens locally after this milestone, with its edit plan kept outside the repo.
