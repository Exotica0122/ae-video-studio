# Milestone 2a — Footage logging and design previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the plugin look at a folder of footage and voice recordings, propose 2–3 genuinely different design directions built from that footage, show them as browser mockups you click to choose, and confirm the winner with a real After Effects still — producing the `plan/design.json` and `analysis/*` files the Milestone 1 engine already consumes.

**Architecture:** Two new skills over four new pure-Python modules. `media.py` wraps ffprobe/ffmpeg (frames, contact sheets, mean luma, average colour — no Pillow, stdlib only). `footage.py` walks source folders and writes `analysis/footage.json`, frames and sheets. `transcribe.py` turns Whisper output into the engine's transcript format. `fonts.py` + `designs/fonts.json` hold a licence-checked font catalogue and report what is installed. `designgen.py` composes design drafts from archetypes × a palette sampled from the footage × a font pairing, writes the chosen draft as `plan/design.json`, and can emit a short "style frame" edit plan the Milestone 1 builder renders in After Effects. `styleframe.py` renders the drafts as self-contained HTML, and `preview.py` serves that page on localhost and records the click.

**Tech Stack:** Python 3.10+ standard library only (`unittest`, `http.server`, `subprocess`), ffmpeg/ffprobe, the Milestone 1 engine (`aestudio.plan/compiler/jsx/bridge/__main__`), After Effects only for the final style-frame confirmation.

**Spec:** `docs/design.md` (sections 3 gate 1–2, 4, 7) and `docs/components.md`.

## Global Constraints

- Python standard library only; target 3.10+; run tests from `engine/` with `python3 -m unittest discover -s tests -t . -v`.
- No Pillow: image work goes through ffmpeg (`scale`, `tile`, rawvideo pixel dumps).
- Nothing in `engine/`, `designs/` or `skills/` may contain content from a specific video (no real names, dates, phone numbers, church/organisation names). Test fixtures use the generated demo media in `examples/demo/`.
- Design drafts must only use treatments registered in `engine/aestudio/components/` (`paper-card`/`paper-tab`/`notebook-page`, or `line-fade`/`rule-wipe`/`black-frame`/`centered-stack`). Milestone 2a varies palette, fonts and treatment set; brand-new treatments are a later milestone, and the skill must say so.
- A design draft is only ever offered with fonts the catalogue lists as installed, or with an explicit "install this first" note carrying the licence and download URL.
- The preview server binds to `127.0.0.1` only, serves files from one directory, never writes outside it, and exits when it has a choice or times out.
- Default format stays 3840×2160 @ 23.976; token pixel values are authored for 4K.
- Never run After Effects, aerender, `AESTUDIO_AE=1` or touch `~/.ae-mcp-bridge` inside tests.
- Transcription never assumes a Whisper build: the command is configurable and failure must tell the user how to transcribe manually and import the result.

## File Structure

```
engine/aestudio/
  media.py        ffprobe/ffmpeg: probe, extract_frame, contact_sheet, mean_luma, average_color
  footage.py      log_footage(): footage.json + frames/ + sheets/ + luma
  transcribe.py   whisper command + JSON → engine transcript format
  fonts.py        catalogue loading, installed check, pairings
  designgen.py    archetypes × palette × fonts → drafts; save_design(); style_frame_plan()
  styleframe.py   drafts → self-contained preview HTML
  preview.py      localhost server that serves the page and records the choice
  __main__.py     + log-footage, transcribe, import-transcript, design-propose, design-preview, design-confirm
designs/
  fonts.json      font catalogue (family, PostScript names, scripts, moods, licence, url)
  archetypes/*.json  paper-notebook, cinematic-minimal, editorial-press
engine/tests/
  test_media.py test_footage.py test_transcribe.py test_fonts.py
  test_designgen.py test_styleframe.py test_preview.py test_cli_design.py
skills/
  footage-logging/SKILL.md
  design-system/SKILL.md
```

---

### Task 1: ffmpeg/ffprobe media helpers

**Files:**
- Create: `engine/aestudio/media.py`
- Test: `engine/tests/test_media.py`

**Interfaces:**
- Produces:
  - `class MediaError(RuntimeError)`
  - `MediaInfo(path: Path, width: int, height: int, fps: float, duration: float, has_audio: bool, has_video: bool)`
  - `probe(path) -> MediaInfo`
  - `extract_frame(src, at: float, out, width: int = 1280) -> Path`
  - `contact_sheet(frames: list[Path], out, cols: int = 4, tile_width: int = 480) -> Path`
  - `mean_luma(src, at: float) -> float` — 0..1, one pixel average of that frame
  - `average_color(src, at: float, grid: int = 1) -> list[tuple[int, int, int]]` — `grid*grid` average colours, row-major
  - `run(args: list[str], what: str) -> str` — subprocess wrapper raising `MediaError` with the tail of stderr
- All helpers take a missing binary as `MediaError` ("ffmpeg not found — install it with `brew install ffmpeg`").

- [ ] **Step 1: Write the failing test**

`engine/tests/test_media.py`:

```python
import tempfile
import unittest
from pathlib import Path

from aestudio import media

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo" / "media"
CLIP, WAV = DEMO / "shot_a.mp4", DEMO / "narration-1.wav"


@unittest.skipUnless(CLIP.exists(), "run examples/demo/make_media.py first")
class MediaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe_video(self):
        info = media.probe(CLIP)
        self.assertEqual((info.width, info.height), (1920, 1080))
        self.assertAlmostEqual(info.fps, 24.0, places=2)
        self.assertGreater(info.duration, 13)
        self.assertTrue(info.has_video)
        self.assertFalse(info.has_audio)

    def test_probe_audio(self):
        info = media.probe(WAV)
        self.assertTrue(info.has_audio)
        self.assertFalse(info.has_video)
        self.assertEqual((info.width, info.height), (0, 0))

    def test_probe_missing_file(self):
        with self.assertRaises(media.MediaError):
            media.probe(self.out / "nope.mp4")

    def test_extract_frame_and_contact_sheet(self):
        frames = [media.extract_frame(CLIP, t, self.out / f"f{i}.jpg", width=320) for i, t in enumerate((1.0, 5.0, 9.0))]
        for f in frames:
            self.assertTrue(f.exists() and f.stat().st_size > 1000)
        self.assertEqual(media.probe(frames[0]).width, 320)
        sheet = media.contact_sheet(frames, self.out / "sheet.jpg", cols=2, tile_width=160)
        info = media.probe(sheet)
        self.assertEqual(info.width, 320)          # 2 columns × 160
        self.assertEqual(info.height, 180)         # 2 rows × 90 (16:9)

    def test_mean_luma_and_average_color(self):
        luma = media.mean_luma(CLIP, 2.0)
        self.assertTrue(0.0 <= luma <= 1.0)
        one = media.average_color(CLIP, 2.0)
        self.assertEqual(len(one), 1)
        self.assertEqual(len(one[0]), 3)
        self.assertTrue(all(0 <= c <= 255 for c in one[0]))
        grid = media.average_color(CLIP, 2.0, grid=2)
        self.assertEqual(len(grid), 4)
        self.assertNotEqual(grid[0], grid[3])       # the demo clips are gradients


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_media -v`
Expected: ERROR `cannot import name 'media' from 'aestudio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/media.py`:

```python
"""ffprobe/ffmpeg helpers: probing, frames, contact sheets and pixel statistics.

Image work goes through ffmpeg (no Pillow): a scaled rawvideo dump gives averaged pixels.
"""
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    path: Path
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    has_video: bool


def _binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} not found — install it with `brew install ffmpeg`")
    return found


def run(args: list, what: str) -> str:
    result = subprocess.run([_binary(args[0])] + [str(a) for a in args[1:]], capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise MediaError(f"{what} failed: " + " / ".join(tail))
    return result.stdout


def _fraction(value, default=0.0) -> float:
    try:
        if isinstance(value, str) and "/" in value:
            num, den = value.split("/", 1)
            return float(num) / float(den) if float(den) else default
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return default


def probe(path) -> MediaInfo:
    path = Path(path)
    if not path.exists():
        raise MediaError(f"file not found: {path}")
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path], f"probing {path.name}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise MediaError(f"unreadable ffprobe output for {path.name}: {e}") from e
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = _fraction(data.get("format", {}).get("duration"), 0.0)
    if video and not duration:
        duration = _fraction(video.get("duration"), 0.0)
    return MediaInfo(path=path,
                     width=int(video.get("width", 0)) if video else 0,
                     height=int(video.get("height", 0)) if video else 0,
                     fps=_fraction(video.get("r_frame_rate"), 0.0) if video else 0.0,
                     duration=round(duration, 3),
                     has_audio=audio is not None,
                     has_video=video is not None)


def extract_frame(src, at: float, out, width: int = 1280) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-ss", max(0.0, float(at)), "-i", src,
         "-frames:v", 1, "-vf", f"scale={int(width)}:-2", "-q:v", 3, out], f"extracting a frame from {Path(src).name}")
    if not out.exists():
        raise MediaError(f"no frame written at {at}s of {Path(src).name} (is the clip shorter than that?)")
    return out


def contact_sheet(frames: list, out, cols: int = 4, tile_width: int = 480) -> Path:
    frames = [Path(f) for f in frames]
    if not frames:
        raise MediaError("contact_sheet needs at least one frame")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = max(1, min(cols, len(frames)))
    rows = (len(frames) + cols - 1) // cols
    args = ["ffmpeg", "-v", "error", "-y"]
    for f in frames:
        args += ["-i", f]
    scaled = "".join(f"[{i}:v]scale={int(tile_width)}:-2,setsar=1[t{i}];" for i in range(len(frames)))
    joined = "".join(f"[t{i}]" for i in range(len(frames)))
    args += ["-filter_complex", f"{scaled}{joined}xstack=inputs={len(frames)}:layout={_layout(len(frames), cols)}[v]"
             if len(frames) > 1 else f"{scaled}[t0]copy[v]",
             "-map", "[v]", "-frames:v", 1, "-q:v", 3, out]
    run(args, "building a contact sheet")
    if rows and not out.exists():
        raise MediaError(f"no contact sheet written to {out}")
    return out


def _layout(count: int, cols: int) -> str:
    cells = []
    for i in range(count):
        col, row = i % cols, i // cols
        x = "0" if col == 0 else "+".join(f"w{c}" for c in range(col))
        y = "0" if row == 0 else "+".join(f"h{r * cols}" for r in range(row))
        cells.append(f"{x}_{y}")
    return "|".join(cells)


def _raw(src, at: float, size: str, pix_fmt: str, what: str) -> bytes:
    args = [_binary("ffmpeg"), "-v", "error", "-ss", str(max(0.0, float(at))), "-i", str(src),
            "-frames:v", "1", "-vf", f"scale={size}", "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"]
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        tail = (result.stderr.decode("utf-8", "replace") or "").strip().splitlines()[-3:]
        raise MediaError(f"{what} failed: " + " / ".join(tail))
    return result.stdout


def mean_luma(src, at: float) -> float:
    data = _raw(src, at, "1:1", "gray", f"reading brightness of {Path(src).name}")
    return round(data[0] / 255, 4)


def average_color(src, at: float, grid: int = 1) -> list:
    grid = max(1, int(grid))
    data = _raw(src, at, f"{grid}:{grid}", "rgb24", f"reading colours of {Path(src).name}")
    if len(data) < grid * grid * 3:
        raise MediaError(f"short colour dump for {Path(src).name}")
    return [tuple(data[i * 3:i * 3 + 3]) for i in range(grid * grid)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python3 -m unittest tests.test_media -v`
Expected: 6 tests OK. If `xstack` layout maths is off, the failing assertion is the sheet's width/height — fix `_layout`, do not change the test.

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/media.py engine/tests/test_media.py
git commit -m "feat(engine): ffmpeg media helpers for probing, frames, sheets and pixel stats"
```

---

### Task 2: Footage log

**Files:**
- Create: `engine/aestudio/footage.py`
- Modify: `engine/aestudio/__main__.py` (add the `log-footage` subcommand)
- Test: `engine/tests/test_footage.py`

**Interfaces:**
- Consumes: `media.probe/extract_frame/contact_sheet/mean_luma/average_color/MediaError` (Task 1).
- Produces:
  - `VIDEO_SUFFIXES = (".mp4", ".mov", ".mxf", ".m4v", ".avi")`, `AUDIO_SUFFIXES = (".wav", ".m4a", ".mp3", ".aif", ".aiff")`
  - `log_footage(sources: list, out_dir, every: float = 4.0, max_frames: int = 6, sheet_cols: int = 4, frame_width: int = 640) -> dict` — walks files and folders (non-recursive into hidden dirs, skips `._*`), probes each, extracts up to `max_frames` frames spaced `every` seconds apart (always skipping the first 0.5 s), measures mean luma and a 2×2 colour grid per frame, writes one contact sheet per clip, and returns/writes `analysis/footage.json`:
    ```jsonc
    {"generated": "<iso>", "clips": [{"path": "...", "name": "shot_a.mp4", "width": 1920, "height": 1080,
      "fps": 24.0, "duration": 14.0, "has_audio": false, "luma": 0.52,
      "frames": [{"at": 0.5, "file": "frames/shot_a_0.5.jpg", "luma": 0.5, "colors": [[r,g,b], ...]}],
      "sheet": "sheets/shot_a.jpg"}],
     "audio": [{"path": "...", "name": "narration-1.wav", "duration": 3.9}],
     "errors": ["shot_x.mp4: ..."]}
    ```
    Paths inside the JSON are relative to `out_dir`; `path` stays absolute. A clip that fails to probe lands in `errors` and does not abort the run.
  - CLI: `python3 -m aestudio log-footage SRC [SRC ...] --out analysis [--every 4] [--max-frames 6]` printing a one-line JSON summary `{"clips": n, "audio": n, "errors": n, "out": "..."}`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_footage.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio import footage

DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo" / "media"


@unittest.skipUnless((DEMO / "shot_a.mp4").exists(), "run examples/demo/make_media.py first")
class FootageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_logs_clips_frames_and_audio(self):
        log = footage.log_footage([DEMO / "shot_a.mp4", DEMO / "narration-1.wav"], self.out, every=4.0, max_frames=3)
        self.assertEqual([c["name"] for c in log["clips"]], ["shot_a.mp4"])
        self.assertEqual([a["name"] for a in log["audio"]], ["narration-1.wav"])
        self.assertEqual(log["errors"], [])
        clip = log["clips"][0]
        self.assertEqual(len(clip["frames"]), 3)
        self.assertEqual([f["at"] for f in clip["frames"]], [0.5, 4.5, 8.5])
        self.assertTrue(0 < clip["luma"] < 1)
        self.assertEqual(len(clip["frames"][0]["colors"]), 4)
        for rel in [f["file"] for f in clip["frames"]] + [clip["sheet"]]:
            self.assertTrue((self.out / rel).exists(), rel)
        written = json.loads((self.out / "footage.json").read_text(encoding="utf-8"))
        self.assertEqual(written["clips"][0]["name"], "shot_a.mp4")

    def test_walks_a_folder_and_reports_bad_files(self):
        broken = self.out / "src" / "broken.mp4"
        broken.parent.mkdir(parents=True)
        broken.write_text("not a video")
        (broken.parent / "._shot_a.mp4").write_text("apple double")
        (broken.parent / "notes.txt").write_text("ignored")
        log = footage.log_footage([broken.parent], self.out / "analysis")
        self.assertEqual(log["clips"], [])
        self.assertEqual(len(log["errors"]), 1)
        self.assertIn("broken.mp4", log["errors"][0])

    def test_frames_stay_inside_the_clip(self):
        log = footage.log_footage([DEMO / "shot_a.mp4"], self.out, every=10.0, max_frames=6)
        ats = [f["at"] for f in log["clips"][0]["frames"]]
        self.assertTrue(all(a < log["clips"][0]["duration"] for a in ats), ats)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_footage -v`
Expected: ERROR `cannot import name 'footage' from 'aestudio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/footage.py`:

```python
"""Log a folder of footage: probe every clip, sample frames, measure brightness and colour."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .media import MediaError, average_color, contact_sheet, extract_frame, mean_luma, probe

VIDEO_SUFFIXES = (".mp4", ".mov", ".mxf", ".m4v", ".avi")
AUDIO_SUFFIXES = (".wav", ".m4a", ".mp3", ".aif", ".aiff")


def _candidates(sources) -> list:
    files = []
    for source in sources:
        source = Path(source).expanduser()
        if source.is_dir():
            files += sorted(p for p in source.iterdir() if p.is_file())
        else:
            files.append(source)
    keep, seen = [], set()
    for f in files:
        if f.name.startswith("._") or f.suffix.lower() not in VIDEO_SUFFIXES + AUDIO_SUFFIXES:
            continue
        if f.resolve() not in seen:
            seen.add(f.resolve())
            keep.append(f)
    return keep


def _frame_times(duration: float, every: float, max_frames: int) -> list:
    times, t = [], 0.5
    while len(times) < max_frames and t < max(duration - 0.2, 0.5):
        times.append(round(t, 3))
        t += every
    return times or [0.0]


def log_footage(sources, out_dir, every: float = 4.0, max_frames: int = 6, sheet_cols: int = 4,
                frame_width: int = 640) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    (out_dir / "sheets").mkdir(parents=True, exist_ok=True)
    log = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "clips": [], "audio": [], "errors": []}

    for path in _candidates(sources):
        try:
            info = probe(path)
        except MediaError as e:
            log["errors"].append(f"{path.name}: {e}")
            continue
        if not info.has_video:
            log["audio"].append({"path": str(path), "name": path.name, "duration": info.duration})
            continue
        frames, lumas = [], []
        for at in _frame_times(info.duration, every, max_frames):
            rel = f"frames/{path.stem}_{at}.jpg"
            try:
                extract_frame(path, at, out_dir / rel, width=frame_width)
                luma = mean_luma(path, at)
                colors = [list(c) for c in average_color(path, at, grid=2)]
            except MediaError as e:
                log["errors"].append(f"{path.name} at {at}s: {e}")
                continue
            lumas.append(luma)
            frames.append({"at": at, "file": rel, "luma": luma, "colors": colors})
        entry = {"path": str(path), "name": path.name, "width": info.width, "height": info.height,
                 "fps": info.fps, "duration": info.duration, "has_audio": info.has_audio,
                 "luma": round(sum(lumas) / len(lumas), 4) if lumas else None, "frames": frames}
        if frames:
            sheet = f"sheets/{path.stem}.jpg"
            try:
                contact_sheet([out_dir / f["file"] for f in frames], out_dir / sheet, cols=sheet_cols,
                              tile_width=max(160, frame_width // 2))
                entry["sheet"] = sheet
            except MediaError as e:
                log["errors"].append(f"{path.name} sheet: {e}")
        log["clips"].append(entry)

    (out_dir / "footage.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return log
```

- [ ] **Step 4: Add the CLI subcommand**

In `engine/aestudio/__main__.py`: import `log_footage` from `.footage` and `MediaError` from `.media`, add `MediaError` to the `KNOWN` tuple, add

```python
def cmd_log_footage(a):
    log = log_footage(a.sources, a.out, every=a.every, max_frames=a.max_frames)
    print(json.dumps({"clips": len(log["clips"]), "audio": len(log["audio"]), "errors": len(log["errors"]),
                      "out": str(Path(a.out).resolve())}, ensure_ascii=False))
    return 0
```

and in `parser()`:

```python
    lf = sub.add_parser("log-footage")
    lf.add_argument("sources", nargs="+")
    lf.add_argument("--out", required=True)
    lf.add_argument("--every", type=float, default=4.0)
    lf.add_argument("--max-frames", type=int, default=6, dest="max_frames")
    lf.set_defaults(fn=cmd_log_footage)
```

- [ ] **Step 5: Run the tests and the CLI**

Run: `cd engine && python3 -m unittest tests.test_footage -v && python3 -m aestudio log-footage ../examples/demo/media --out /tmp/aestudio-footage-check`
Expected: 3 tests OK, then a JSON line with `"clips": 4, "audio": 5, "errors": 0`.

- [ ] **Step 6: Commit**

```bash
git add engine/aestudio/footage.py engine/aestudio/__main__.py engine/tests/test_footage.py
git commit -m "feat(engine): footage log with sampled frames, brightness and contact sheets"
```

---

### Task 3: Transcripts from Whisper

**Files:**
- Create: `engine/aestudio/transcribe.py`
- Modify: `engine/aestudio/__main__.py` (add `transcribe` and `import-transcript`)
- Test: `engine/tests/test_transcribe.py`

**Interfaces:**
- Consumes: `timing.load_transcript` (Milestone 1) for the round-trip test; `media.probe`.
- Produces:
  - `class TranscribeError(RuntimeError)`
  - `DEFAULT_CMD = "uvx mlx-whisper {audio} --model mlx-community/whisper-large-v3-turbo --word-timestamps True --output-dir {outdir} --output-format json"` — overridable with the `AESTUDIO_WHISPER_CMD` environment variable; `{audio}` and `{outdir}` are substituted.
  - `whisper_command(audio, outdir, template=None) -> list[str]` (shell-split, substituted)
  - `to_engine(data: dict) -> dict` — converts either Whisper shape (`{"segments": [{"words": [{"word": "…", "start": s, "end": e}]}]}` or a flat `{"words": [...]}`) into `{"onset": s, "offset": s, "words": [[word, start, end], ...]}`, stripping leading/trailing spaces from each word and dropping words with no text. Raises `TranscribeError` when no words are found.
  - `import_transcript(src_json, out_json) -> dict` — read, convert, write, return.
  - `transcribe(audio, out_json, template=None) -> dict` — runs the command in a temp dir, picks the single `.json` it produced, converts and writes. On a non-zero exit or missing output, raises `TranscribeError` whose message includes the command and: "transcribe it yourself (any Whisper build with word timestamps) and run `python3 -m aestudio import-transcript <json> --out <out>`".
  - CLI: `transcribe AUDIO --out JSON [--cmd TEMPLATE]`, `import-transcript SRC --out JSON`; both print `{"out": path, "words": n, "onset": s, "offset": s}`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_transcribe.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio import transcribe
from aestudio.timing import load_transcript

WHISPER = {"text": " 모든 여정은", "segments": [
    {"words": [{"word": " 모든", "start": 0.1, "end": 0.5}, {"word": " 여정은", "start": 0.5, "end": 1.1}]},
    {"words": [{"word": " 작은", "start": 1.2, "end": 1.6}, {"word": " ", "start": 1.6, "end": 1.6}]}]}


class TranscribeTest(unittest.TestCase):
    def test_to_engine_from_segments(self):
        out = transcribe.to_engine(WHISPER)
        self.assertEqual(out["words"], [["모든", 0.1, 0.5], ["여정은", 0.5, 1.1], ["작은", 1.2, 1.6]])
        self.assertEqual((out["onset"], out["offset"]), (0.1, 1.6))

    def test_to_engine_from_flat_words(self):
        out = transcribe.to_engine({"words": [{"word": "hello", "start": 1.0, "end": 1.4}]})
        self.assertEqual(out["words"], [["hello", 1.0, 1.4]])

    def test_to_engine_rejects_empty(self):
        with self.assertRaises(transcribe.TranscribeError):
            transcribe.to_engine({"segments": []})

    def test_import_transcript_round_trips_through_the_engine(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "w.json", Path(d) / "t.json"
            src.write_text(json.dumps(WHISPER, ensure_ascii=False), encoding="utf-8")
            transcribe.import_transcript(src, out)
            tr = load_transcript(out)
        self.assertEqual([w[0] for w in tr.words], ["모든", "여정은", "작은"])
        self.assertEqual(tr.onset, 0.1)

    def test_whisper_command_substitutes(self):
        cmd = transcribe.whisper_command("/a/b c.wav", "/tmp/out", template="mywhisper {audio} --out {outdir}")
        self.assertEqual(cmd, ["mywhisper", "/a/b c.wav", "--out", "/tmp/out"])

    def test_transcribe_failure_explains_the_manual_route(self):
        with tempfile.TemporaryDirectory() as d:
            audio, out = Path(d) / "a.wav", Path(d) / "t.json"
            audio.write_text("x")
            with self.assertRaises(transcribe.TranscribeError) as cm:
                transcribe.transcribe(audio, out, template="/usr/bin/false {audio} {outdir}")
        self.assertIn("import-transcript", str(cm.exception))

    def test_transcribe_uses_the_command_output(self):
        with tempfile.TemporaryDirectory() as d:
            audio, out = Path(d) / "a.wav", Path(d) / "t.json"
            audio.write_text("x")
            fake = Path(d) / "fake_whisper.py"       # stands in for a Whisper build
            fake.write_text("import json, pathlib, sys\n"
                            "pathlib.Path(sys.argv[2], 'out.json').write_text(pathlib.Path(sys.argv[3]).read_text())\n",
                            encoding="utf-8")
            payload = Path(d) / "payload.json"
            payload.write_text(json.dumps(WHISPER, ensure_ascii=False), encoding="utf-8")
            result = transcribe.transcribe(audio, out, template=f"python3 {fake} {{audio}} {{outdir}} {payload}")
        self.assertEqual(len(result["words"]), 3)
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_transcribe -v`
Expected: ERROR `cannot import name 'transcribe' from 'aestudio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/transcribe.py`:

```python
"""Turn Whisper output into the engine's transcript format (word start/end times)."""
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

DEFAULT_CMD = ("uvx mlx-whisper {audio} --model mlx-community/whisper-large-v3-turbo "
               "--word-timestamps True --output-dir {outdir} --output-format json")
MANUAL = ("transcribe it yourself (any Whisper build with word timestamps) and run "
          "`python3 -m aestudio import-transcript <json> --out <out>`")


class TranscribeError(RuntimeError):
    pass


def whisper_command(audio, outdir, template=None) -> list:
    template = template or os.environ.get("AESTUDIO_WHISPER_CMD") or DEFAULT_CMD
    parts = shlex.split(template)
    return [str(audio) if p == "{audio}" else str(outdir) if p == "{outdir}" else p for p in parts]


def _words(data: dict) -> list:
    raw = []
    for segment in data.get("segments") or []:
        raw += list(segment.get("words") or [])
    raw += list(data.get("words") or [])
    words = []
    for item in raw:
        text = str(item.get("word", item.get("text", ""))).strip()
        if not text:
            continue
        try:
            start, end = round(float(item["start"]), 3), round(float(item["end"]), 3)
        except (KeyError, TypeError, ValueError) as e:
            raise TranscribeError(f"word {text!r} has no usable start/end: {e}") from e
        words.append([text, start, end])
    return words


def to_engine(data: dict) -> dict:
    words = _words(data)
    if not words:
        raise TranscribeError("no words with timings in this transcript; " + MANUAL)
    return {"onset": words[0][1], "offset": words[-1][2], "words": words}


def import_transcript(src_json, out_json) -> dict:
    src, out = Path(src_json), Path(out_json)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TranscribeError(f"cannot read {src}: {e}") from e
    result = to_engine(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def transcribe(audio, out_json, template=None) -> dict:
    audio = Path(audio)
    if not audio.exists():
        raise TranscribeError(f"audio not found: {audio}")
    with tempfile.TemporaryDirectory() as work:
        cmd = whisper_command(audio, work, template)
        result = subprocess.run(cmd, capture_output=True, text=True)
        produced = sorted(Path(work).glob("*.json"))
        if result.returncode != 0 or not produced:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
            raise TranscribeError("transcription command failed: " + " ".join(cmd) + "\n  "
                                  + " / ".join(tail) + f"\n  {MANUAL}")
        return import_transcript(produced[0], out_json)
```

- [ ] **Step 4: Add the CLI subcommands**

In `engine/aestudio/__main__.py`: import `TranscribeError, import_transcript, transcribe as run_transcribe` from `.transcribe`, add `TranscribeError` to `KNOWN`, and add

```python
def _print_transcript(out, result):
    print(json.dumps({"out": str(Path(out).resolve()), "words": len(result["words"]),
                      "onset": result["onset"], "offset": result["offset"]}, ensure_ascii=False))
    return 0


def cmd_transcribe(a):
    return _print_transcript(a.out, run_transcribe(a.audio, a.out, template=a.cmd))


def cmd_import_transcript(a):
    return _print_transcript(a.out, import_transcript(a.src, a.out))
```

with parsers:

```python
    tr = sub.add_parser("transcribe")
    tr.add_argument("audio")
    tr.add_argument("--out", required=True)
    tr.add_argument("--cmd")
    tr.set_defaults(fn=cmd_transcribe)
    it = sub.add_parser("import-transcript")
    it.add_argument("src")
    it.add_argument("--out", required=True)
    it.set_defaults(fn=cmd_import_transcript)
```

- [ ] **Step 5: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_transcribe -v && python3 -m unittest discover -s tests -t .`
Expected: 7 new tests OK; full suite OK with the earlier skips.

- [ ] **Step 6: Commit**

```bash
git add engine/aestudio/transcribe.py engine/aestudio/__main__.py engine/tests/test_transcribe.py
git commit -m "feat(engine): whisper transcripts converted to the engine format"
```

---
### Task 4: Font catalogue

**Files:**
- Create: `designs/fonts.json`, `engine/aestudio/fonts.py`
- Test: `engine/tests/test_fonts.py`

**Interfaces:**
- Produces:
  - `class FontError(ValueError)`
  - `CATALOGUE = Path(__file__).resolve().parents[2] / "designs" / "fonts.json"`
  - `FONT_DIRS = (Path("~/Library/Fonts").expanduser(), Path("/Library/Fonts"), Path("/System/Library/Fonts"))`
  - `Font(id, family, postscript: dict[str, str], scripts: list[str], style: str, moods: list[str], licence: str, url: str)` — `postscript` maps a role weight (`"regular"`, `"medium"`, `"semibold"`, `"bold"`, `"extrabold"`, `"light"`) to a PostScript name.
  - `load_catalogue(path=CATALOGUE) -> list[Font]` (validates every field; raises `FontError` listing all problems)
  - `installed_files() -> set[str]` — lowercase stems of every font file in `FONT_DIRS` (missing dirs ignored)
  - `is_installed(font: Font, files=None) -> bool` — True when every PostScript name it offers has a matching file stem
  - `pairings(moods, scripts=("ko",), catalogue=None, installed_only=True) -> list[dict]` — up to 3 pairings `{"headline": Font, "body": Font, "quote": Font, "installed": bool, "notes": [str]}`; headline and body must differ in `style` when possible (serif vs sans vs hand), and every font must support every requested script. With `installed_only=False`, uninstalled fonts are allowed and each gets a note "install <family> first: <licence>, <url>".
  - `fonts_for(pairing, weights) -> dict[str, str]` — role → PostScript name for the design's `type` block, e.g. `{"headline": "Paperlogy-8ExtraBold", ...}` picking the closest available weight for each role (`headline`→extrabold/bold, `emphasis`→bold/semibold, `body`→medium/regular, `label`→bold/semibold, `quote`→semibold/regular, `scripture`→light/regular from the quote font).
- `designs/fonts.json` ships at least these families, all free for commercial use, with real PostScript names and licence/url: **Paperlogy** (SIL OFL, sans, moods warm/friendly/presentation), **MaruBuri** (Naver, serif, moods calm/literary/scripture), **NanumSquareNeo** (Naver, sans, moods modern/neutral), **NanumGothic** (Naver, sans, moods plain/legible), **NotoSerifKR** (SIL OFL, serif, moods editorial/formal), plus two not-installed-here suggestions: **Pretendard** (SIL OFL, sans, moods modern/clean) and **GowunBatang** (SIL OFL, serif, moods soft/gentle). Latin-only extras are allowed but must set `"scripts": ["latin"]`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_fonts.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio import fonts


class FontsTest(unittest.TestCase):
    def test_catalogue_loads_and_is_valid(self):
        catalogue = fonts.load_catalogue()
        ids = [f.id for f in catalogue]
        self.assertIn("paperlogy", ids)
        self.assertIn("maruburi", ids)
        self.assertEqual(len(ids), len(set(ids)))
        for font in catalogue:
            self.assertTrue(font.licence and font.url, font.id)
            self.assertTrue(font.postscript, font.id)
            self.assertIn(font.style, ("sans", "serif", "hand", "display"), font.id)
            self.assertTrue(set(font.scripts) <= {"ko", "latin", "ja"}, font.id)

    def test_installed_detection_matches_this_machine(self):
        catalogue = {f.id: f for f in fonts.load_catalogue()}
        files = fonts.installed_files()
        self.assertTrue(fonts.is_installed(catalogue["paperlogy"], files))
        self.assertTrue(fonts.is_installed(catalogue["maruburi"], files))
        self.assertFalse(fonts.is_installed(catalogue["pretendard"], files))

    def test_pairings_prefer_installed_and_mix_styles(self):
        pairs = fonts.pairings(["warm", "friendly"], scripts=("ko",))
        self.assertTrue(pairs)
        for pair in pairs:
            self.assertTrue(pair["installed"])
            self.assertEqual(pair["notes"], [])
            for role in ("headline", "body", "quote"):
                self.assertIn("ko", pair[role].scripts)
        self.assertTrue(any(p["headline"].style != p["body"].style for p in pairs))

    def test_pairings_can_include_uninstalled_with_a_note(self):
        pairs = fonts.pairings(["modern", "clean"], scripts=("ko",), installed_only=False)
        notes = [n for p in pairs for n in p["notes"]]
        self.assertTrue(any("install" in n.lower() for n in notes), notes)

    def test_fonts_for_fills_every_role(self):
        pair = fonts.pairings(["warm"], scripts=("ko",))[0]
        roles = fonts.fonts_for(pair, ("headline", "body", "emphasis", "quote", "label", "scripture"))
        self.assertEqual(set(roles), {"headline", "body", "emphasis", "quote", "label", "scripture"})
        for name in roles.values():
            self.assertRegex(name, r"^[A-Za-z0-9\-]+$")

    def test_bad_catalogue_reports_every_problem(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fonts.json"
            path.write_text(json.dumps([{"id": "x", "family": "X", "postscript": {}, "scripts": ["klingon"],
                                         "style": "wobbly", "moods": [], "licence": "", "url": ""}]), encoding="utf-8")
            with self.assertRaises(fonts.FontError) as cm:
                fonts.load_catalogue(path)
        message = str(cm.exception)
        for expected in ("postscript", "scripts", "style", "licence"):
            self.assertIn(expected, message)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_fonts -v`
Expected: ERROR `cannot import name 'fonts' from 'aestudio'`

- [ ] **Step 3: Write the catalogue**

`designs/fonts.json` — a JSON array. Use exactly these PostScript names (they match the files installed on this machine for the first five):

```json
[
 {"id": "paperlogy", "family": "Paperlogy", "style": "sans", "scripts": ["ko", "latin"],
  "moods": ["warm", "friendly", "presentation", "hand-made"],
  "postscript": {"light": "Paperlogy-3Light", "regular": "Paperlogy-4Regular", "medium": "Paperlogy-5Medium",
                 "semibold": "Paperlogy-6SemiBold", "bold": "Paperlogy-7Bold", "extrabold": "Paperlogy-8ExtraBold"},
  "licence": "SIL Open Font License 1.1 — free for commercial use, redistribute with the licence",
  "url": "https://noonnu.cc/font_page/1456"},
 {"id": "maruburi", "family": "MaruBuri", "style": "serif", "scripts": ["ko", "latin"],
  "moods": ["calm", "literary", "scripture", "restrained"],
  "postscript": {"light": "MaruBuri-Light", "regular": "MaruBuri-Regular", "semibold": "MaruBuri-SemiBold",
                 "bold": "MaruBuri-Bold"},
  "licence": "Naver Maru Buri licence — free for commercial use, redistribution allowed with the licence",
  "url": "https://hangeul.naver.com/font/maru"},
 {"id": "nanumsquareneo", "family": "NanumSquareNeo", "style": "sans", "scripts": ["ko", "latin"],
  "moods": ["modern", "neutral", "clean", "premium"],
  "postscript": {"light": "NanumSquareNeoTTF-aLt", "regular": "NanumSquareNeoTTF-bRg",
                 "bold": "NanumSquareNeoTTF-cBd", "extrabold": "NanumSquareNeoTTF-dEb"},
  "licence": "Naver Nanum font licence — free for commercial use, redistribution allowed with the licence",
  "url": "https://hangeul.naver.com/font"},
 {"id": "nanumgothic", "family": "NanumGothic", "style": "sans", "scripts": ["ko", "latin"],
  "moods": ["plain", "legible", "neutral"],
  "postscript": {"regular": "NanumGothic", "bold": "NanumGothicBold", "extrabold": "NanumGothicExtraBold"},
  "licence": "SIL Open Font License 1.1", "url": "https://hangeul.naver.com/font"},
 {"id": "notoserifkr", "family": "Noto Serif KR", "style": "serif", "scripts": ["ko", "latin"],
  "moods": ["editorial", "formal", "authoritative"],
  "postscript": {"light": "NotoSerifKR-ExtraLight", "regular": "NotoSerifKR-Regular",
                 "bold": "NotoSerifKR-Bold", "extrabold": "NotoSerifKR-ExtraBold"},
  "licence": "SIL Open Font License 1.1", "url": "https://fonts.google.com/noto/specimen/Noto+Serif+KR"},
 {"id": "pretendard", "family": "Pretendard", "style": "sans", "scripts": ["ko", "latin"],
  "moods": ["modern", "clean", "product", "premium"],
  "postscript": {"light": "Pretendard-Light", "regular": "Pretendard-Regular", "medium": "Pretendard-Medium",
                 "semibold": "Pretendard-SemiBold", "bold": "Pretendard-Bold"},
  "licence": "SIL Open Font License 1.1", "url": "https://github.com/orioncactus/pretendard"},
 {"id": "gowunbatang", "family": "Gowun Batang", "style": "serif", "scripts": ["ko", "latin"],
  "moods": ["soft", "gentle", "handwritten", "calm"],
  "postscript": {"regular": "GowunBatang-Regular", "bold": "GowunBatang-Bold"},
  "licence": "SIL Open Font License 1.1", "url": "https://fonts.google.com/specimen/Gowun+Batang"}
]
```

- [ ] **Step 4: Write the module**

`engine/aestudio/fonts.py`:

```python
"""Font catalogue: what is installed, which pairings suit a mood, and licences to pass on."""
import json
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
        catalogue.append(Font(id=fid, family=entry.get("family", fid), postscript=entry.get("postscript", {}),
                              scripts=list(entry.get("scripts", [])), style=entry.get("style", ""),
                              moods=list(entry.get("moods", [])), licence=entry.get("licence", ""),
                              url=entry.get("url", "")))
    if errors:
        raise FontError(f"{path}:\n  " + "\n  ".join(errors))
    return catalogue


def installed_files() -> set:
    stems = set()
    for directory in FONT_DIRS:
        try:
            for f in directory.iterdir():
                if f.is_file() and f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    stems.add(f.stem.lower())
        except OSError:
            continue
    return stems


def is_installed(font: Font, files=None) -> bool:
    files = installed_files() if files is None else files
    names = list(font.postscript.values())
    return bool(names) and all(name.lower() in files for name in names)


def _score(font: Font, moods) -> int:
    return len(set(m.lower() for m in moods) & set(m.lower() for m in font.moods))


def pairings(moods, scripts=("ko",), catalogue=None, installed_only=True) -> list:
    catalogue = catalogue or load_catalogue()
    files = installed_files()
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
        for font in dict.fromkeys((headline, body, quote)):
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
```

- [ ] **Step 5: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_fonts -v`
Expected: 6 tests OK. If `test_installed_detection_matches_this_machine` fails on a family that *is* installed, the PostScript names in the catalogue must match the installed file stems — check with `ls ~/Library/Fonts | grep -i <family>` and fix `designs/fonts.json`, not the test.

- [ ] **Step 6: Commit**

```bash
git add designs/fonts.json engine/aestudio/fonts.py engine/tests/test_fonts.py
git commit -m "feat(designs): licence-checked font catalogue with installed detection and pairings"
```

---

### Task 5: Design drafts from archetypes, footage colour and fonts

**Files:**
- Create: `designs/archetypes/paper-notebook.json`, `designs/archetypes/cinematic-minimal.json`, `designs/archetypes/editorial-press.json`
- Create: `engine/aestudio/designgen.py`
- Test: `engine/tests/test_designgen.py`

**Interfaces:**
- Consumes: `fonts.pairings/fonts_for/load_catalogue` (Task 4), `design.load_design/Design/ROLES/COMPONENTS/PALETTE_KEYS` and `util.hex_rgb` (Milestone 1), `footage.log_footage` output shape (Task 2).
- Produces:
  - `class DesignGenError(ValueError)`
  - `ARCHETYPES = Path(__file__).resolve().parents[2] / "designs" / "archetypes"`
  - `Draft(id, name, mood: list, recipe: dict, fonts: dict, notes: list)` — `recipe` is a complete design recipe in the Milestone 1 format (`id/name/mood/tokens{palette,type,motion,texture}/components/grade_hint/sfx_hint`), so `design.load_design` accepts it once written.
  - `load_archetypes(path=ARCHETYPES) -> list[dict]`
  - `accent_from_footage(log: dict, fallback="#C9A46A") -> str` — picks the most saturated, mid-bright colour among the logged frame colours and returns it as `#RRGGBB`; falls back when the log has no colours.
  - `propose(brief_moods, log=None, scripts=("ko",), installed_only=True, archetypes=None, limit=3) -> list[Draft]` — one draft per archetype (ranked by mood overlap), each with a font pairing from Task 4, the archetype's palette with its `accent` replaced by `accent_from_footage` when the archetype sets `"accent_from_footage": true`, and `type` sizes from the archetype scaled by its own `type_scale`. Never proposes two drafts with the same `(archetype, headline font)`. Raises `DesignGenError` if no archetype survives.
  - `save_design(draft: Draft, out_path) -> Path` — writes `draft.recipe` (pretty JSON) and verifies it loads with `design.load_design`.
  - `style_frame_plan(draft, log, out_dir, script_lines=None, duration=6.0) -> Path` — writes a tiny `edit.json` next to the drafts using the two brightest logged clips, one caption, one lower third and an end card, with no voices (caption/lower-third/end-card times are explicit), so the Milestone 1 builder can render a real style frame. Returns the plan path.
- Each archetype JSON holds: `id`, `name`, `moods`, `treatments` (a component→treatment map using registered treatments only), `palette` (with `#RRGGBB` values), `accent_from_footage` (bool), `type_scale` (float), `motion`, `texture`, `grade_hint`, `sfx_hint`, and `font_moods` (moods passed to `fonts.pairings`).

- [ ] **Step 1: Write the failing test**

`engine/tests/test_designgen.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio import designgen
from aestudio.design import COMPONENTS, ROLES, load_design
from aestudio.components import REGISTRY

LOG = {"clips": [
    {"name": "a.mp4", "path": "/tmp/a.mp4", "duration": 14.0, "luma": 0.62, "width": 1920, "height": 1080,
     "frames": [{"at": 0.5, "file": "frames/a_0.5.jpg", "luma": 0.62, "colors": [[240, 170, 60], [30, 40, 70], [200, 150, 90], [20, 20, 25]]}]},
    {"name": "b.mp4", "path": "/tmp/b.mp4", "duration": 12.0, "luma": 0.41, "width": 1920, "height": 1080,
     "frames": [{"at": 0.5, "file": "frames/b_0.5.jpg", "luma": 0.41, "colors": [[60, 110, 90], [40, 60, 55], [70, 120, 100], [30, 50, 45]]}]}],
    "audio": [], "errors": []}


class DesignGenTest(unittest.TestCase):
    def test_archetypes_are_valid_and_use_registered_treatments(self):
        archetypes = designgen.load_archetypes()
        self.assertGreaterEqual(len(archetypes), 3)
        for arch in archetypes:
            self.assertEqual(set(arch["treatments"]), set(COMPONENTS), arch["id"])
            for component, treatment in arch["treatments"].items():
                self.assertIn((component, treatment), REGISTRY, f"{arch['id']}: {component}/{treatment}")

    def test_accent_from_footage_picks_a_saturated_colour(self):
        accent = designgen.accent_from_footage(LOG)
        self.assertRegex(accent, r"^#[0-9A-Fa-f]{6}$")
        self.assertNotEqual(accent.lower(), "#c9a46a")          # not the fallback
        self.assertEqual(designgen.accent_from_footage({"clips": []}), "#C9A46A")

    def test_propose_returns_distinct_complete_drafts(self):
        drafts = designgen.propose(["warm", "friendly"], log=LOG)
        self.assertGreaterEqual(len(drafts), 2)
        self.assertEqual(len({d.id for d in drafts}), len(drafts))
        for draft in drafts:
            recipe = draft.recipe
            self.assertEqual(set(recipe["tokens"]["type"]), set(ROLES), draft.id)
            self.assertEqual(set(recipe["components"]), set(COMPONENTS), draft.id)
            for role, spec in recipe["tokens"]["type"].items():
                self.assertTrue(spec["font"] and spec["size"] > 0, f"{draft.id}/{role}")
            self.assertEqual(draft.notes, [], draft.id)         # installed_only=True by default

    def test_saved_draft_loads_as_a_design(self):
        draft = designgen.propose(["calm"], log=LOG)[0]
        with tempfile.TemporaryDirectory() as d:
            path = designgen.save_design(draft, Path(d) / "design.json")
            design = load_design(path)
        self.assertEqual(design.id, draft.id)
        self.assertEqual(set(design.components), set(COMPONENTS))
        self.assertTrue(design.fonts())

    def test_style_frame_plan_is_a_valid_edit_plan(self):
        from aestudio.plan import load_plan
        draft = designgen.propose(["warm"], log=LOG)[0]
        with tempfile.TemporaryDirectory() as d:
            for name in ("a.mp4", "b.mp4"):
                (Path(d) / name).write_text("x")
            log = json.loads(json.dumps(LOG).replace("/tmp/", str(Path(d)) + "/"))
            plan_path = designgen.style_frame_plan(draft, log, Path(d) / "style", duration=6.0)
            plan = load_plan(plan_path)
        self.assertEqual(plan.format.duration, 6.0)
        self.assertEqual(plan.voices, [])
        self.assertEqual({g["type"] for g in plan.graphics}, {"caption", "lower-third", "end-card"})
        self.assertTrue(plan.shots)

    def test_propose_without_a_log_still_works(self):
        drafts = designgen.propose(["modern"], log=None)
        self.assertTrue(drafts)
        self.assertEqual(drafts[0].recipe["tokens"]["palette"]["accent"][:1], "#")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_designgen -v`
Expected: ERROR `cannot import name 'designgen' from 'aestudio'`

- [ ] **Step 3: Write the archetypes**

`designs/archetypes/paper-notebook.json`:

```json
{"id": "paper-notebook", "name": "Paper Notebook",
 "moods": ["warm", "friendly", "hand-made", "hopeful", "community"],
 "font_moods": ["warm", "friendly", "presentation"],
 "treatments": {"caption": "paper-card", "quote": "paper-card", "lower-third": "paper-tab",
                "title-page": "notebook-page", "end-card": "notebook-page"},
 "palette": {"paper": "#FBF7EF", "ink": "#22304A", "accent": "#FFD84D", "accent2": "#EE7860",
             "rule": "#DCD3C3", "shade": "#101418"},
 "accent_from_footage": false, "type_scale": 1.0,
 "motion": {"in": 0.6, "out": 0.45, "word": 0.35, "rise": 14}, "texture": {"noise": 4},
 "grade_hint": "warm-airy", "sfx_hint": ["paper-slide", "page-turn", "marker"]}
```

`designs/archetypes/cinematic-minimal.json`:

```json
{"id": "cinematic-minimal", "name": "Cinematic Minimal",
 "moods": ["restrained", "emotional", "premium", "modern", "clean"],
 "font_moods": ["modern", "neutral", "premium"],
 "treatments": {"caption": "line-fade", "quote": "line-fade", "lower-third": "rule-wipe",
                "title-page": "black-frame", "end-card": "centered-stack"},
 "palette": {"paper": "#0E0F12", "ink": "#F4F1EA", "accent": "#C9A46A", "accent2": "#8FA3B8",
             "rule": "#3A3D44", "shade": "#0E0F12"},
 "accent_from_footage": true, "type_scale": 1.0,
 "motion": {"in": 0.8, "out": 0.6, "word": 0.6, "rise": 0}, "texture": {"noise": 0},
 "grade_hint": "soft-contrast-warm", "sfx_hint": ["low-whoosh", "soft-hit"]}
```

`designs/archetypes/editorial-press.json`:

```json
{"id": "editorial-press", "name": "Editorial Press",
 "moods": ["editorial", "formal", "calm", "literary", "authoritative"],
 "font_moods": ["editorial", "calm", "literary"],
 "treatments": {"caption": "paper-card", "quote": "paper-card", "lower-third": "paper-tab",
                "title-page": "notebook-page", "end-card": "notebook-page"},
 "palette": {"paper": "#F3F1EC", "ink": "#1B1B1B", "accent": "#B8452F", "accent2": "#7C7A73",
             "rule": "#D6D2C8", "shade": "#111111"},
 "accent_from_footage": true, "type_scale": 0.92,
 "motion": {"in": 0.5, "out": 0.4, "word": 0.3, "rise": 8}, "texture": {"noise": 2},
 "grade_hint": "neutral-crisp", "sfx_hint": ["paper-slide", "soft-hit"]}
```

- [ ] **Step 4: Write the module**

`engine/aestudio/designgen.py`:

```python
"""Compose design drafts: archetype × palette sampled from the footage × a font pairing.

Milestone 2a varies palette, fonts and treatment set. New treatments (a genuinely new look
for captions or end cards) are a later milestone — drafts may only use registered treatments.
"""
import colorsys
import json
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
    type_block = {}
    for role, name in fontlib.fonts_for(pairing, ROLES).items():
        type_block[role] = {"font": name, "size": round(BASE_SIZES[role] * scale, 1)}
    palette = dict(arch["palette"])
    if arch.get("accent_from_footage"):
        palette["accent"] = accent
    return {"id": f"{arch['id']}-{pairing['headline'].id}", "name": f"{arch['name']} · {pairing['headline'].family}",
            "mood": list(arch.get("moods", [])),
            "tokens": {"palette": palette, "type": type_block, "motion": dict(arch.get("motion", {})),
                       "texture": dict(arch.get("texture", {}))},
            "components": {c: {"treatment": t} for c, t in arch["treatments"].items()},
            "grade_hint": arch.get("grade_hint", ""), "sfx_hint": list(arch.get("sfx_hint", []))}


def propose(brief_moods, log=None, scripts=("ko",), installed_only=True, archetypes=None, limit=3) -> list:
    archetypes = archetypes or load_archetypes()
    moods = [m.lower() for m in brief_moods or []]
    ranked = sorted(archetypes, key=lambda a: (-len(set(moods) & {m.lower() for m in a.get("moods", [])}), a["id"]))
    accent = accent_from_footage(log)
    drafts, used = [], set()
    for arch in ranked:
        pairs = fontlib.pairings(arch.get("font_moods") or arch.get("moods", []), scripts=scripts,
                                 installed_only=installed_only)
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
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(draft.recipe, ensure_ascii=False, indent=1), encoding="utf-8")
    load_design(out_path)          # fails loudly if the draft is not a valid design
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
```

Note: the style-frame caption has no voice, so **Task 6 depends on a small engine change** — see Task 6, Step 3: `caption`/`quote` must accept `"voice": null` by falling back to schedule-based word times. Do that change in Task 6 and keep this plan file as written.

- [ ] **Step 5: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_designgen -v`
Expected: 6 tests OK, except `test_style_frame_plan_is_a_valid_edit_plan`, which fails on `load_plan` rejecting `"voice": null` until Task 6 lands. If it fails only for that reason, note it in your report and continue — Task 6 fixes it.

- [ ] **Step 6: Commit**

```bash
git add designs/archetypes engine/aestudio/designgen.py engine/tests/test_designgen.py
git commit -m "feat(designs): design drafts from archetypes, footage colour and font pairings"
```

---
### Task 6: Captions without a voice (engine change)

**Files:**
- Modify: `engine/aestudio/plan.py` (allow `"voice": null` on caption/quote when `in` and `out` are given)
- Modify: `engine/aestudio/components/notebook.py` (`caption_paper_card`), `engine/aestudio/components/cinematic.py` (`caption_line_fade`)
- Test: `engine/tests/test_voiceless.py`

**Interfaces:**
- Consumes: `layout.schedule_times`, `layout.segment_times` (Milestone 1).
- Produces: a caption or quote graphic may set `"voice": null` (or omit `voice`) if it also sets `in` and `out`; its words then reveal on a schedule (`in + 0.35`, 0.12 s per word, 0.3 s between lines) instead of from a transcript. With a voice, behaviour is unchanged. `load_plan` still rejects a caption whose `voice` names an id that does not exist, and rejects a voiceless caption missing `in` or `out`.
- Style frames (Task 5) and any future design preview rely on this; nothing else changes.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_voiceless.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio.compiler import compile_plan
from aestudio.design import load_design
from aestudio.plan import PlanError, load_plan

LINES = [["이 화면의 글자 크기와"], ["색이 ", {"hl": "잘 보이는지"}, " 확인해 주세요."]]


def write(root: Path, graphic: dict) -> Path:
    (root / "a.mp4").write_text("x")
    plan = {"name": "STYLE", "format": {"duration": 6},
            "shots": [{"clip": "a.mp4", "in": 0, "out": 6}], "voices": [], "graphics": [graphic]}
    (root / "edit.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return root / "edit.json"


class VoicelessCaptionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_accepts_a_voiceless_caption_with_times(self):
        plan = load_plan(write(self.root, {"type": "caption", "voice": None, "lines": LINES, "in": 0.3, "out": 3.2}))
        self.assertIsNone(plan.graphics[0]["voice"])

    def test_plan_rejects_a_voiceless_caption_without_times(self):
        with self.assertRaisesRegex(PlanError, "needs 'in' and 'out'"):
            load_plan(write(self.root, {"type": "caption", "lines": LINES}))

    def test_plan_still_rejects_an_unknown_voice(self):
        with self.assertRaisesRegex(PlanError, "unknown voice 'N9'"):
            load_plan(write(self.root, {"type": "caption", "voice": "N9", "lines": LINES, "in": 0, "out": 3}))

    def test_both_designs_compile_a_voiceless_caption_on_a_schedule(self):
        path = write(self.root, {"type": "caption", "voice": None, "lines": LINES, "in": 0.3, "out": 3.2})
        plan = load_plan(path)
        for ref in ("notebook", "cinematic-minimal"):
            ops = compile_plan(plan, load_design(ref))
            texts = [o for o in ops if o["op"] == "text"]
            self.assertTrue(texts, ref)
            first = texts[0]["reveal"]["times"]
            self.assertEqual(first[0], 0.65, ref)                      # in + 0.35
            self.assertEqual(first[1], 0.77, ref)                      # + 0.12 per word
            later = texts[-1]["reveal"]["times"]
            self.assertGreater(later[0], first[-1], ref)               # later lines come after
            highlights = [o for o in ops if o["op"] == "rect" and o["id"].endswith("_HL")]
            if ref == "notebook":
                self.assertTrue(highlights)                            # marker still keyed to its word


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_voiceless -v`
Expected: `test_plan_rejects_a_voiceless_caption_without_times` and the compile test fail — `load_plan` currently reports `unknown voice 'None'`.

- [ ] **Step 3: Loosen plan validation**

In `engine/aestudio/plan.py`, replace the caption/quote check inside the graphics loop:

```python
        if gtype in ("caption", "quote"):
            voice = g.get("voice")
            if voice is None:
                if g.get("in") is None or g.get("out") is None:
                    c.errors.append(f"{where}: a caption without a voice needs 'in' and 'out'")
            elif voice not in seen:
                c.errors.append(f"{where}: unknown voice '{voice}'")
```

- [ ] **Step 4: Schedule the words when there is no voice**

In `engine/aestudio/components/notebook.py`, add `schedule_times` to the `.layout` import (if Task 12 of Milestone 1 already added it, leave it) and change the first lines of `caption_paper_card`:

```python
    quote = g["type"] == "quote"
    vt = ctx.voices.get(g["voice"]) if g.get("voice") else None
    t_in = r3(g["in"]) if g.get("in") is not None else r3(vt.onset - 0.3)
    t_out = r3(g["out"]) if g.get("out") is not None else r3(vt.offset + 0.5)
```

and replace `times = segment_times(lines, vt.words)` with:

```python
    times = segment_times(lines, vt.words) if vt else schedule_times(lines, t_in + 0.35, 0.12, 0.3)
```

In `engine/aestudio/components/cinematic.py`, add `schedule_times` to its `.layout` import and make the same three changes in `caption_line_fade`, keeping its own defaults when a voice is present (`vt.onset - 0.4`, `vt.offset + 0.6`), and passing the scheduled times into `text_block` instead of `segment_times(lines, vt.words)`.

- [ ] **Step 5: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_voiceless tests.test_designgen tests.test_notebook tests.test_cinematic tests.test_plan -v`
Expected: all OK, including `test_style_frame_plan_is_a_valid_edit_plan` from Task 5.

- [ ] **Step 6: Commit**

```bash
git add engine/aestudio/plan.py engine/aestudio/components engine/tests/test_voiceless.py
git commit -m "feat(engine): captions without a voice reveal on a schedule"
```

---

### Task 7: Design mockups as HTML

**Files:**
- Create: `engine/aestudio/styleframe.py`
- Test: `engine/tests/test_styleframe.py`

**Interfaces:**
- Consumes: `designgen.Draft` (Task 5), the footage log shape (Task 2), `util.hex_rgb` only if needed.
- Produces:
  - `render_mockups(drafts, log, out_dir, script_lines=None, title="Design directions") -> Path` — writes `out_dir/index.html` plus copies of the frames it uses into `out_dir/frames/`, and returns the index path. Self-contained: CSS inline, no external requests, fonts referenced by family name so an installed font renders.
  - Each draft becomes one `<section class="draft" data-id="…">` with: the draft name, its mood words, the font families used, any install notes, and **two mockup frames** — a caption frame (a logged frame as the background, the caption's lines with the highlighted phrase marked, and the lower third) and an end-card frame (the draft's paper/shade background with year, title, tagline and two info rows). Colours and fonts come from the draft's recipe tokens; the notebook treatment set draws a paper card behind the caption, the cinematic set draws centred text with a shadow.
  - A **"Choose this" button** per draft posting to `/choose` (`{"id": draft id}`), and a text box posting a free-text note with it; when the page is opened as a file (no server) the buttons say "open via the preview server to click" and the page still reads fine.
  - `mockup_css(draft) -> str` and `caption_html(draft, lines) -> str` are separate helpers so the tests can assert on them.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_styleframe.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from aestudio import designgen, styleframe

LOG = json.loads(json.dumps({
    "clips": [{"name": "a.mp4", "path": "/tmp/a.mp4", "duration": 14.0, "luma": 0.6, "width": 1920, "height": 1080,
               "frames": [{"at": 0.5, "file": "frames/a_0.5.jpg", "luma": 0.6,
                           "colors": [[240, 170, 60], [30, 40, 70], [200, 150, 90], [20, 20, 25]]}]}],
    "audio": [], "errors": []}))


class StyleFrameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analysis = self.root / "analysis"
        (self.analysis / "frames").mkdir(parents=True)
        (self.analysis / "frames" / "a_0.5.jpg").write_bytes(b"\xff\xd8\xff\xd9")     # stand-in JPEG
        self.log = json.loads(json.dumps(LOG))
        self.log["root"] = str(self.analysis)
        self.drafts = designgen.propose(["warm", "modern"], log=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_has_one_section_per_draft_with_frames_and_buttons(self):
        index = styleframe.render_mockups(self.drafts, self.log, self.root / "preview")
        html = index.read_text(encoding="utf-8")
        for draft in self.drafts:
            self.assertIn(f'data-id="{draft.id}"', html)
            self.assertIn(draft.name, html)
        self.assertEqual(html.count('class="draft"'), len(self.drafts))
        self.assertEqual(html.count("Choose this"), len(self.drafts))
        self.assertIn("/choose", html)
        self.assertIn("frames/a_0.5.jpg", html)
        self.assertTrue((self.root / "preview" / "frames" / "a_0.5.jpg").exists())
        self.assertNotIn("http://", html.replace("http://localhost", ""))   # no external requests

    def test_tokens_drive_the_css(self):
        draft = self.drafts[0]
        css = styleframe.mockup_css(draft)
        self.assertIn(draft.recipe["tokens"]["palette"]["accent"], css)
        self.assertIn(draft.recipe["tokens"]["type"]["headline"]["font"].split("-")[0], css)

    def test_caption_html_marks_the_highlight(self):
        html = styleframe.caption_html(self.drafts[0], [["작은 "], [{"hl": "한 걸음"}], ["에서"]])
        self.assertIn("한 걸음", html)
        self.assertIn("class=\"hl\"", html)
        self.assertNotIn("{", html)

    def test_install_notes_are_shown(self):
        drafts = designgen.propose(["modern", "clean"], log=self.log, installed_only=False)
        index = styleframe.render_mockups(drafts, self.log, self.root / "preview2")
        html = index.read_text(encoding="utf-8")
        notes = [n for d in drafts for n in d.notes]
        for note in notes:
            self.assertIn(note.split(":")[0], html)

    def test_missing_frames_do_not_crash(self):
        log = json.loads(json.dumps(LOG))
        log["root"] = str(self.analysis)
        log["clips"][0]["frames"][0]["file"] = "frames/missing.jpg"
        index = styleframe.render_mockups(self.drafts, log, self.root / "preview3")
        self.assertTrue(index.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_styleframe -v`
Expected: ERROR `cannot import name 'styleframe' from 'aestudio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/styleframe.py`:

```python
"""Render design drafts as a self-contained HTML page of mockup frames.

The mockups approximate the After Effects treatments closely enough to choose between
directions: real frames from the footage, the draft's palette, and the installed fonts by
family name. The chosen direction is always confirmed with a real After Effects still.
"""
import html
import json
import shutil
from pathlib import Path

DEFAULT_LINES = [["이 화면의 글자 크기와"], ["색이 ", {"hl": "잘 보이는지"}, " 확인해 주세요."]]
END_ROWS = [("안내", ["첫째 줄", "둘째 줄"]), ("문의", ["예시 · 000-0000-0000"])]


def _family(postscript: str) -> str:
    """'Paperlogy-7Bold' -> 'Paperlogy' — browsers match installed fonts by family name."""
    return postscript.split("-")[0]


def _tokens(draft):
    tokens = draft.recipe["tokens"]
    return tokens["palette"], tokens["type"]


def _is_paper(draft) -> bool:
    return draft.recipe["components"]["caption"]["treatment"] == "paper-card"


def mockup_css(draft) -> str:
    palette, type_block = _tokens(draft)
    head, body, quote = (_family(type_block[r]["font"]) for r in ("headline", "body", "quote"))
    return f"""
.d-{draft.id} {{ --paper: {palette['paper']}; --ink: {palette['ink']}; --accent: {palette['accent']};
  --accent2: {palette['accent2']}; --rule: {palette['rule']}; --shade: {palette['shade']};
  --head: '{head}', system-ui, sans-serif; --body: '{body}', system-ui, sans-serif;
  --quote: '{quote}', Georgia, serif; }}
.d-{draft.id} .cap {{ font-family: var(--body); color: var(--ink); }}
.d-{draft.id} .cap .hl {{ background: var(--accent); padding: 0 .12em; border-radius: .06em; }}
.d-{draft.id} .card {{ background: var(--paper); box-shadow: 0 10px 30px rgba(0,0,0,.25); }}
.d-{draft.id} .lt {{ font-family: var(--head); color: var(--ink); background: var(--paper); }}
.d-{draft.id} .lt .role {{ font-family: var(--body); color: var(--paper); background: var(--ink); }}
.d-{draft.id} .end {{ background: var(--paper); color: var(--ink); font-family: var(--body); }}
.d-{draft.id} .end h3 {{ font-family: var(--head); }}
.d-{draft.id} .end .year {{ background: var(--ink); color: var(--paper); }}
.d-{draft.id} .end .label {{ color: var(--accent2); }}
.d-{draft.id} .rule {{ background: var(--accent); }}
""".strip()


def caption_html(draft, lines=None) -> str:
    out = []
    for line in (lines or DEFAULT_LINES):
        parts = []
        for segment in line:
            if isinstance(segment, dict):
                parts.append(f'<span class="hl">{html.escape(segment["hl"])}</span>')
            else:
                parts.append(html.escape(segment))
        out.append('<span class="line">' + "".join(parts) + "</span>")
    return "".join(out)


def _frames(log, out_dir) -> list:
    root = Path(log.get("root") or ".")
    copied = []
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    for clip in log.get("clips", []):
        for frame in clip.get("frames", []):
            src = root / frame["file"]
            if not src.exists():
                continue
            dest = out_dir / "frames" / Path(frame["file"]).name
            shutil.copyfile(src, dest)
            copied.append(f"frames/{dest.name}")
            break
    return copied


def _draft_section(draft, frame_rel, lines) -> str:
    palette, type_block = _tokens(draft)
    paper = _is_paper(draft)
    background = (f'<img class="bg" src="{html.escape(frame_rel)}" alt="">' if frame_rel
                  else '<div class="bg placeholder"></div>')
    caption_block = (f'<div class="card cap">{caption_html(draft, lines)}</div>' if paper
                     else f'<div class="cap centered">{caption_html(draft, lines)}</div>')
    rows = "".join(f'<div class="row"><span class="label">{html.escape(label)}</span>'
                   f'<span class="values">{"<br>".join(html.escape(v) for v in values)}</span></div>'
                   for label, values in END_ROWS)
    notes = "".join(f'<li>{html.escape(n)}</li>' for n in draft.notes)
    fonts_used = ", ".join(dict.fromkeys(_family(spec["font"]) for spec in type_block.values()))
    return f"""
<section class="draft d-{html.escape(draft.id)}" data-id="{html.escape(draft.id)}">
  <header>
    <h2>{html.escape(draft.name)}</h2>
    <p class="mood">{html.escape(" · ".join(draft.mood[:5]))}</p>
    <p class="fonts">{html.escape(fonts_used)}</p>
    {f'<ul class="notes">{notes}</ul>' if notes else ''}
  </header>
  <div class="frames">
    <figure class="frame">{background}<div class="overlay {'paper' if paper else 'cine'}">{caption_block}
      <div class="lt"><span class="role">역할 예시</span><span class="name">이름 예시</span></div></div>
      <figcaption>caption + lower third</figcaption></figure>
    <figure class="frame"><div class="end">
      <span class="year">2027</span><h3>제목 예시</h3><div class="rule"></div>
      <p class="tag">한 줄 설명이 들어갑니다</p>{rows}</div><figcaption>end card</figcaption></figure>
  </div>
  <footer>
    <input class="note" type="text" placeholder="바꾸고 싶은 점 (선택)">
    <button class="choose" data-id="{html.escape(draft.id)}">Choose this</button>
  </footer>
</section>""".strip()


PAGE_CSS = """
:root { color-scheme: light dark; }
body { margin: 0; padding: 24px; font: 15px/1.5 system-ui, sans-serif; background: #14161a; color: #e8e6e1; }
h1 { font-size: 20px; margin: 0 0 4px; }
.lede { color: #a9a6a0; margin: 0 0 20px; }
.draft { border: 1px solid #2a2d33; border-radius: 10px; padding: 16px; margin-bottom: 20px; }
.draft h2 { font-size: 17px; margin: 0; }
.mood, .fonts { color: #a9a6a0; margin: 2px 0; font-size: 13px; }
.notes { color: #ffcf6b; font-size: 13px; margin: 6px 0 0; padding-left: 18px; }
.frames { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; margin-top: 12px; }
.frame { margin: 0; position: relative; }
.frame figcaption { color: #7e7b76; font-size: 12px; margin-top: 4px; }
.bg, .end { width: 100%; aspect-ratio: 16 / 9; display: block; object-fit: cover; border-radius: 6px; }
.bg.placeholder { background: linear-gradient(135deg, #2b2f36, #14161a); }
.overlay { position: absolute; inset: 0; padding: 5%; box-sizing: border-box; }
.overlay .cap { position: absolute; left: 6%; bottom: 12%; max-width: 62%; font-size: clamp(13px, 2.1vw, 22px); }
.overlay .card { padding: .5em .7em; border-radius: .25em; }
.overlay.cine .cap { left: 50%; transform: translateX(-50%); text-align: center; color: #fff;
  text-shadow: 0 2px 12px rgba(0,0,0,.6); }
.cap .line { display: block; }
.overlay .lt { position: absolute; left: 6%; top: 14%; padding: .4em .6em; border-radius: .25em; font-size: clamp(11px, 1.6vw, 16px); }
.overlay .lt .role { display: inline-block; padding: 0 .5em; border-radius: 1em; font-size: .8em; }
.overlay .lt .name { display: block; font-weight: 700; }
.end { padding: 6% 7%; box-sizing: border-box; }
.end .year { display: inline-block; padding: .1em .7em; border-radius: 1em; font-size: .8em; }
.end h3 { font-size: clamp(18px, 3vw, 34px); margin: .2em 0 .1em; }
.end .rule { width: 28%; height: 3px; margin: .2em 0 .5em; }
.end .row { display: flex; gap: 10px; font-size: clamp(11px, 1.4vw, 14px); margin-top: .25em; }
.end .label { min-width: 5em; }
footer { display: flex; gap: 8px; margin-top: 12px; }
.note { flex: 1; padding: 8px; border-radius: 6px; border: 1px solid #2a2d33; background: #0f1114; color: inherit; }
button { padding: 8px 14px; border-radius: 6px; border: 0; background: #e8e6e1; color: #14161a; font-weight: 600; cursor: pointer; }
button:disabled { opacity: .45; cursor: default; }
.picked { outline: 2px solid #7fd1a8; }
"""

PAGE_JS = """
const offline = location.protocol === 'file:';
document.querySelectorAll('button.choose').forEach(function (b) {
  if (offline) { b.disabled = true; b.textContent = 'open via the preview server to click'; return; }
  b.addEventListener('click', async function () {
    const section = b.closest('.draft');
    const note = section.querySelector('.note').value;
    b.disabled = true;
    try {
      await fetch('/choose', {method: 'POST', headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify({id: b.dataset.id, note: note})});
      document.querySelectorAll('.draft').forEach(function (d) { d.classList.remove('picked'); });
      section.classList.add('picked');
      b.textContent = 'Chosen — you can close this tab';
    } catch (e) { b.disabled = false; b.textContent = 'Choose this (retry)'; }
  });
});
"""


def render_mockups(drafts, log, out_dir, script_lines=None, title="Design directions") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = _frames(log, out_dir)
    sections, css = [], []
    for i, draft in enumerate(drafts):
        sections.append(_draft_section(draft, frames[i % len(frames)] if frames else None, script_lines))
        css.append(mockup_css(draft))
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{PAGE_CSS}\n{chr(10).join(css)}</style></head>
<body><h1>{html.escape(title)}</h1>
<p class="lede">Mockups from your own footage. Pick one, or type what you would change.
The chosen direction is confirmed with a real After Effects still before anything is built.</p>
{chr(10).join(sections)}
<script>{PAGE_JS}</script></body></html>
"""
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    (out_dir / "drafts.json").write_text(json.dumps([d.recipe for d in drafts], ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    return index
```

Note: `render_mockups` reads frame paths relative to `log["root"]`, which `footage.log_footage` does not set. Task 9's CLI sets `log["root"]` to the analysis folder after loading `footage.json`; the tests set it directly.

- [ ] **Step 4: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_styleframe -v`
Expected: 5 tests OK.

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/styleframe.py engine/tests/test_styleframe.py
git commit -m "feat(designs): self-contained HTML mockups for design drafts"
```

---
### Task 8: Preview server with click-to-choose

**Files:**
- Create: `engine/aestudio/preview.py`
- Test: `engine/tests/test_preview.py`

**Interfaces:**
- Produces:
  - `class PreviewError(RuntimeError)`
  - `CHOICE_FILE = "choice.json"`
  - `serve(directory, port: int = 0, host: str = "127.0.0.1") -> tuple[ThreadingHTTPServer, str]` — a server bound to `host` only, serving files from `directory` (no directory listings outside it, no symlink escape), plus `POST /choose` (JSON body `{"id": str, "note": str|None}`) which writes `directory/choice.json` as `{"id": …, "note": …, "at": "<iso>"}` and replies `{"ok": true}`, and `GET /choice` returning the recorded choice or `{}`. Returns the server (already serving in a background thread) and its base URL.
  - `wait_for_choice(server, directory, timeout: float = 1800.0, poll: float = 0.5) -> dict | None` — returns the choice dict once written, or `None` on timeout; always shuts the server down.
  - `read_choice(directory) -> dict | None`
  - A `POST /choose` with an unknown id (not present in `directory/drafts.json`, when that file exists) is refused with 400 and does not write the file.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_preview.py`:

```python
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from aestudio import preview


def post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read()


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "index.html").write_text("<h1>designs</h1>", encoding="utf-8")
        (self.dir / "drafts.json").write_text(json.dumps([{"id": "paper-notebook-paperlogy"}]), encoding="utf-8")
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.tmp.cleanup()

    def test_serves_the_page_and_records_a_choice(self):
        self.server, url = preview.serve(self.dir)
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        status, body = get(url + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"designs", body)
        status, reply = post(url + "/choose", {"id": "paper-notebook-paperlogy", "note": "bigger type"})
        self.assertEqual((status, reply["ok"]), (200, True))
        choice = preview.read_choice(self.dir)
        self.assertEqual(choice["id"], "paper-notebook-paperlogy")
        self.assertEqual(choice["note"], "bigger type")
        self.assertIn("at", choice)
        status, reply = get(url + "/choice")
        self.assertEqual(json.loads(reply)["id"], "paper-notebook-paperlogy")

    def test_unknown_id_is_refused(self):
        self.server, url = preview.serve(self.dir)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(url + "/choose", {"id": "nope"})
        self.assertEqual(cm.exception.code, 400)
        self.assertIsNone(preview.read_choice(self.dir))

    def test_files_outside_the_directory_are_refused(self):
        self.server, url = preview.serve(self.dir)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            get(url + "/../../etc/hosts")
        self.assertIn(cm.exception.code, (400, 403, 404))

    def test_wait_for_choice_returns_the_choice_then_stops(self):
        server, url = preview.serve(self.dir)
        threading.Timer(0.2, lambda: post(url + "/choose", {"id": "paper-notebook-paperlogy"})).start()
        choice = preview.wait_for_choice(server, self.dir, timeout=5, poll=0.05)
        self.assertEqual(choice["id"], "paper-notebook-paperlogy")
        with self.assertRaises(urllib.error.URLError):
            get(url + "/")                      # the server is closed

    def test_wait_for_choice_times_out(self):
        server, _ = preview.serve(self.dir)
        self.assertIsNone(preview.wait_for_choice(server, self.dir, timeout=0.3, poll=0.05))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_preview -v`
Expected: ERROR `cannot import name 'preview' from 'aestudio'`

- [ ] **Step 3: Write minimal implementation**

`engine/aestudio/preview.py`:

```python
"""Serve the design mockups on localhost and record which direction was clicked."""
import json
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHOICE_FILE = "choice.json"


class PreviewError(RuntimeError):
    pass


def read_choice(directory):
    path = Path(directory) / CHOICE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _known_ids(directory) -> set:
    try:
        drafts = json.loads((Path(directory) / "drafts.json").read_text(encoding="utf-8"))
        return {d.get("id") for d in drafts if isinstance(d, dict)}
    except (OSError, ValueError):
        return set()


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        self._root = Path(directory).resolve()
        super().__init__(*args, directory=str(self._root), **kwargs)

    def log_message(self, *args):
        pass                                    # keep the terminal clean

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/choice":
            return self._json(200, read_choice(self._root) or {})
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/choose":
            return self._json(404, {"ok": False, "error": "unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "body must be JSON"})
        draft_id = payload.get("id")
        known = _known_ids(self._root)
        if not isinstance(draft_id, str) or not draft_id or (known and draft_id not in known):
            return self._json(400, {"ok": False, "error": f"unknown draft id {draft_id!r}"})
        choice = {"id": draft_id, "note": payload.get("note") or None,
                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (self._root / CHOICE_FILE).write_text(json.dumps(choice, ensure_ascii=False, indent=1), encoding="utf-8")
        return self._json(200, {"ok": True})


def serve(directory, port: int = 0, host: str = "127.0.0.1"):
    directory = Path(directory).resolve()
    if not (directory / "index.html").exists():
        raise PreviewError(f"no index.html in {directory} — render the mockups first")
    (directory / CHOICE_FILE).unlink(missing_ok=True)
    handler = partial(_Handler, directory=str(directory))
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        raise PreviewError(f"cannot serve on {host}:{port}: {e}") from e
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{server.server_address[1]}"


def wait_for_choice(server, directory, timeout: float = 1800.0, poll: float = 0.5):
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            choice = read_choice(directory)
            if choice:
                return choice
            time.sleep(poll)
        return None
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 4: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_preview -v`
Expected: 5 tests OK. `SimpleHTTPRequestHandler` already refuses `..` traversal; if the traversal test fails, do not weaken it — fix the handler.

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/preview.py engine/tests/test_preview.py
git commit -m "feat(designs): localhost preview server that records the chosen direction"
```

---

### Task 9: Design CLI commands

**Files:**
- Modify: `engine/aestudio/__main__.py`
- Test: `engine/tests/test_cli_design.py`

**Interfaces:**
- Consumes: Tasks 2, 5, 7, 8 and the Milestone 1 `_compile`/`cmd_run`/`cmd_still`.
- Produces three subcommands, all printing one JSON line:
  - `design-propose --analysis DIR --out PREVIEW_DIR [--mood WORD ...] [--scripts ko latin] [--allow-uninstalled-fonts] [--limit 3]` — loads `DIR/footage.json`, sets `log["root"] = DIR`, proposes drafts, renders the mockups into `PREVIEW_DIR`, prints `{"drafts": [ids], "index": path, "notes": [...]}`.
  - `design-preview --dir PREVIEW_DIR [--timeout 1800] [--port 0] [--no-wait]` — serves the directory, prints `{"url": ..., "waiting": true}` immediately (flushed), then blocks until a choice or the timeout; on a choice prints `{"chosen": id, "note": note}` and exits 0; on timeout prints the URL again with `{"chosen": null}` and exits 1. With `--no-wait` it prints the URL and exits 0 without blocking (for a human to open later).
  - `design-choose --dir PREVIEW_DIR --out plan/design.json [--id DRAFT_ID]` — takes the recorded choice (or `--id`), finds that recipe in `PREVIEW_DIR/drafts.json`, writes it with `designgen.save_design`, prints `{"design": path, "id": id, "note": note}`. Fails with a clear error when there is no choice yet.
  - `design-styleplan --dir PREVIEW_DIR --analysis DIR --out STYLE_DIR [--id DRAFT_ID]` — writes the style-frame edit plan for the chosen draft, prints `{"plan": path, "name": comp_name}`, so the operator can then run `build`/`still` from Milestone 1.
- `KNOWN` gains `DesignGenError`, `PreviewError`, `FontError`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_cli_design.py`:

```python
import io
import json
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from aestudio.__main__ import main

LOG = {"clips": [{"name": "a.mp4", "path": "", "duration": 14.0, "luma": 0.6, "width": 1920, "height": 1080,
                  "frames": [{"at": 0.5, "file": "frames/a_0.5.jpg", "luma": 0.6,
                              "colors": [[240, 170, 60], [30, 40, 70], [200, 150, 90], [20, 20, 25]]}]}],
       "audio": [], "errors": []}


class CliDesignTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.analysis = self.root / "analysis"
        (self.analysis / "frames").mkdir(parents=True)
        (self.analysis / "frames" / "a_0.5.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        clip = self.root / "a.mp4"
        clip.write_text("x")
        log = json.loads(json.dumps(LOG))
        log["clips"][0]["path"] = str(clip)
        (self.analysis / "footage.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        self.preview = self.root / "preview"

    def tearDown(self):
        self.tmp.cleanup()

    def _propose(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-propose", "--analysis", str(self.analysis), "--out", str(self.preview),
                         "--mood", "warm", "--mood", "modern"])
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_propose_renders_mockups(self):
        info = self._propose()
        self.assertTrue(info["drafts"])
        self.assertTrue(Path(info["index"]).exists())
        self.assertTrue((self.preview / "drafts.json").exists())

    def test_choose_writes_a_design(self):
        info = self._propose()
        design_path = self.root / "plan" / "design.json"
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-choose", "--dir", str(self.preview), "--out", str(design_path),
                         "--id", info["drafts"][0]])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["id"], info["drafts"][0])
        recipe = json.loads(design_path.read_text(encoding="utf-8"))
        self.assertEqual(recipe["id"], info["drafts"][0])

    def test_choose_without_a_choice_fails(self):
        self._propose()
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = main(["design-choose", "--dir", str(self.preview), "--out", str(self.root / "d.json")])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())

    def test_preview_no_wait_prints_a_url(self):
        self._propose()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-preview", "--dir", str(self.preview), "--no-wait"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["url"].startswith("http://127.0.0.1:"))

    def test_preview_waits_for_a_click(self):
        info = self._propose()

        def click():
            url = json.loads((self.preview / "url.json").read_text(encoding="utf-8"))["url"]
            request = urllib.request.Request(url + "/choose", method="POST",
                                             data=json.dumps({"id": info["drafts"][0]}).encode("utf-8"),
                                             headers={"Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=5).read()

        timer = threading.Timer(0.6, click)
        timer.start()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-preview", "--dir", str(self.preview), "--timeout", "8", "--poll", "0.1"])
        timer.cancel()
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in out.getvalue().strip().splitlines()]
        self.assertEqual(lines[-1]["chosen"], info["drafts"][0])

    def test_styleplan_writes_an_edit_plan(self):
        from aestudio.plan import load_plan
        info = self._propose()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["design-styleplan", "--dir", str(self.preview), "--analysis", str(self.analysis),
                         "--out", str(self.root / "style"), "--id", info["drafts"][0]])
        self.assertEqual(code, 0)
        plan = load_plan(json.loads(out.getvalue())["plan"])
        self.assertTrue(plan.name.startswith("STYLE_"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python3 -m unittest tests.test_cli_design -v`
Expected: `argument cmd: invalid choice: 'design-propose'`

- [ ] **Step 3: Write the subcommands**

In `engine/aestudio/__main__.py`, add imports (`from .designgen import DesignGenError, Draft, propose, save_design, style_frame_plan`, `from .fonts import FontError`, `from .preview import PreviewError, read_choice, serve, wait_for_choice`, `from .styleframe import render_mockups`), extend `KNOWN` with `DesignGenError, PreviewError, FontError`, and add:

```python
def _load_log(analysis):
    analysis = Path(analysis).resolve()
    log = json.loads((analysis / "footage.json").read_text(encoding="utf-8"))
    log["root"] = str(analysis)
    return log


def _drafts_from_dir(directory):
    recipes = json.loads((Path(directory) / "drafts.json").read_text(encoding="utf-8"))
    return [Draft(id=r["id"], name=r.get("name", r["id"]), mood=r.get("mood", []), recipe=r) for r in recipes]


def _pick(directory, draft_id):
    drafts = _drafts_from_dir(directory)
    choice = read_choice(directory) or {}
    wanted = draft_id or choice.get("id")
    if not wanted:
        raise DesignGenError(f"no design chosen yet — run `design-preview --dir {directory}` and click one, "
                             "or pass --id")
    for draft in drafts:
        if draft.id == wanted:
            return draft, choice.get("note")
    raise DesignGenError(f"draft '{wanted}' is not in {Path(directory) / 'drafts.json'}")


def cmd_design_propose(a):
    log = _load_log(a.analysis)
    drafts = propose(a.mood, log=log, scripts=tuple(a.scripts), installed_only=not a.allow_uninstalled_fonts,
                     limit=a.limit)
    index = render_mockups(drafts, log, a.out)
    print(json.dumps({"drafts": [d.id for d in drafts], "index": str(index),
                      "notes": [n for d in drafts for n in d.notes]}, ensure_ascii=False))
    return 0


def cmd_design_preview(a):
    server, url = serve(a.dir, port=a.port)
    (Path(a.dir) / "url.json").write_text(json.dumps({"url": url}), encoding="utf-8")
    print(json.dumps({"url": url, "waiting": not a.no_wait}, ensure_ascii=False), flush=True)
    if a.no_wait:
        return 0
    choice = wait_for_choice(server, a.dir, timeout=a.timeout, poll=a.poll)
    print(json.dumps({"chosen": (choice or {}).get("id"), "note": (choice or {}).get("note"), "url": url},
                     ensure_ascii=False))
    return 0 if choice else 1


def cmd_design_choose(a):
    draft, note = _pick(a.dir, a.id)
    path = save_design(draft, a.out)
    print(json.dumps({"design": str(path), "id": draft.id, "note": note}, ensure_ascii=False))
    return 0


def cmd_design_styleplan(a):
    draft, _ = _pick(a.dir, a.id)
    plan_path = style_frame_plan(draft, _load_log(a.analysis), a.out)
    print(json.dumps({"plan": str(plan_path),
                      "name": json.loads(Path(plan_path).read_text(encoding="utf-8"))["name"]}, ensure_ascii=False))
    return 0
```

and in `parser()`:

```python
    dp = sub.add_parser("design-propose")
    dp.add_argument("--analysis", required=True)
    dp.add_argument("--out", required=True)
    dp.add_argument("--mood", action="append", default=[])
    dp.add_argument("--scripts", nargs="+", default=["ko"])
    dp.add_argument("--allow-uninstalled-fonts", action="store_true", dest="allow_uninstalled_fonts")
    dp.add_argument("--limit", type=int, default=3)
    dp.set_defaults(fn=cmd_design_propose)
    dv = sub.add_parser("design-preview")
    dv.add_argument("--dir", required=True)
    dv.add_argument("--timeout", type=float, default=1800)
    dv.add_argument("--poll", type=float, default=0.5)
    dv.add_argument("--port", type=int, default=0)
    dv.add_argument("--no-wait", action="store_true", dest="no_wait")
    dv.set_defaults(fn=cmd_design_preview)
    dc = sub.add_parser("design-choose")
    dc.add_argument("--dir", required=True)
    dc.add_argument("--out", required=True)
    dc.add_argument("--id")
    dc.set_defaults(fn=cmd_design_choose)
    ds = sub.add_parser("design-styleplan")
    ds.add_argument("--dir", required=True)
    ds.add_argument("--analysis", required=True)
    ds.add_argument("--out", required=True)
    ds.add_argument("--id")
    ds.set_defaults(fn=cmd_design_styleplan)
```

- [ ] **Step 4: Run the tests**

Run: `cd engine && python3 -m unittest tests.test_cli_design -v && python3 -m unittest discover -s tests -t .`
Expected: 6 new tests OK; the whole suite OK.

- [ ] **Step 5: Commit**

```bash
git add engine/aestudio/__main__.py engine/tests/test_cli_design.py
git commit -m "feat(cli): design-propose, design-preview, design-choose and design-styleplan"
```

---

### Task 10: The two skills and the docs

**Files:**
- Create: `skills/footage-logging/SKILL.md`, `skills/design-system/SKILL.md`
- Modify: `README.md` (layout + quick start), `docs/design.md` (§9 build order: mark Milestone 2a done, note what is left), `docs/components.md` (voiceless captions)
- Test: none (documentation); verified by the commands in Step 4

**Interfaces:**
- `footage-logging` covers: what it produces (`analysis/footage.json`, frames, sheets, transcripts), the commands (`log-footage`, `transcribe`, `import-transcript`), when to use it (before any design or build work), and the rules: never guess timings by ear when a transcript exists; if Whisper is unavailable, ask the user to transcribe and use `import-transcript`; audio files are logged but not framed.
- `design-system` covers: the gate-2 flow (propose → preview → choose → style-frame confirm in After Effects), the exact command sequence, that the mockups are approximations and the After Effects still is the real check, that only installed fonts are offered unless the user accepts an install note, that Milestone 2a varies palette/fonts/treatment set (new treatments come later), and how to handle "mix A's type with B's colours" (edit the chosen `plan/design.json` and re-run the style frame).

- [ ] **Step 1: Write `skills/footage-logging/SKILL.md`**

````markdown
---
name: footage-logging
description: Review a folder of footage and voice recordings for ae-video-studio — probe clips, sample frames and contact sheets, measure brightness, and turn Whisper output into the engine's transcript format. Use before designing or building a video, or when the user asks what footage they have.
---

# Log the footage

Run commands with `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`. ffmpeg must be installed.

## Log clips and frames

```
log-footage <folder-or-file> [more …] --out <project>/analysis [--every 4] [--max-frames 6]
```

Writes `analysis/footage.json` (one entry per clip: size, fps, duration, audio, mean brightness, sampled frames with
their own brightness and 2×2 colours), `analysis/frames/*.jpg` and one contact sheet per clip in `analysis/sheets/`.
Audio files are listed under `audio` with their duration. Unreadable files land in `errors` and never stop the run.

Look at the contact sheets before proposing a story or a design: they are the fastest way to see what the footage
actually contains.

## Transcripts

```
transcribe <audio> --out <project>/analysis/transcripts/<name>.json
import-transcript <whisper.json> --out <project>/analysis/transcripts/<name>.json
```

`transcribe` runs a Whisper command (default `uvx mlx-whisper …`, override with `--cmd` or `AESTUDIO_WHISPER_CMD`).
If it fails, say so plainly and ask the user to transcribe the file with any Whisper build that emits word timestamps,
then use `import-transcript`. Both write `{"onset", "offset", "words": [[word, start, end], …]}`, which is what
captions sync to.

## Rules

- Never estimate word timings by ear or by guessing: captions come from a transcript.
- Every voice in an edit plan needs its own transcript file.
- Keep `analysis/` inside the video's own project folder, never in this plugin.
````

- [ ] **Step 2: Write `skills/design-system/SKILL.md`**

````markdown
---
name: design-system
description: Propose 2-3 design directions for an ae-video-studio video from its own footage, show them as clickable browser mockups with font pairings, record the choice as plan/design.json, and confirm it with a real After Effects still. Use at the design checkpoint, before any build, or when the user asks to see design or font options.
---

# Design directions (gate 2)

Run commands with `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`.
Needs `analysis/footage.json` from the `footage-logging` skill.

## The flow

1. **Propose** — mood words come from the brief (e.g. warm, hopeful, modern, restrained):

   ```
   design-propose --analysis <project>/analysis --out <project>/preview --mood warm --mood hopeful
   ```

   Writes `<project>/preview/index.html` (mockups built from the video's own frames) and `drafts.json`.

2. **Preview and let the user click**:

   ```
   design-preview --dir <project>/preview --timeout 1800
   ```

   It prints a `http://127.0.0.1:…` URL, then waits. Give the user that link and say what to look for: readability
   over their footage, the highlight colour, and the fonts. They click "Choose this" (and may type a note).

3. **Record the choice**:

   ```
   design-choose --dir <project>/preview --out <project>/plan/design.json
   ```

4. **Confirm in After Effects** — the mockups are approximations, so always confirm the winner:

   ```
   design-styleplan --dir <project>/preview --analysis <project>/analysis --out <project>/style
   build <project>/style/edit.json --design <project>/plan/design.json --project <project>/build/style.aep
   still --comp STYLE_<ID> --time 1.2 --out <project>/preview/style-caption.png
   still --comp STYLE_<ID> --time 4.5 --out <project>/preview/style-endcard.png
   ```

   Show both stills. Check the text is readable over the real footage, nothing is clipped, and the Korean line breaks
   fall between words. Only then move on to the story and the full edit plan.

## Rules

- Only fonts the catalogue reports as installed are offered. With `--allow-uninstalled-fonts`, each draft carries an
  install note with its licence and link — pass that note to the user and let them decide.
- Milestone 2a varies palette, fonts and which treatment set is used (paper-card family or line-fade family).
  A genuinely new caption or end-card treatment is a code change, not a draft — say so rather than promising it.
- "Mix A's type with B's colours" is a normal request: run `design-choose` for the base, then edit
  `plan/design.json` (tokens only) and re-run the style frame to confirm.
- The mockups never replace the After Effects still. Do not start a full build from mockups alone.
- Keep `preview/`, `plan/` and `analysis/` in the video's own project folder.
````

- [ ] **Step 3: Update the docs**

- `README.md`: in the layout block add `engine/aestudio/{media,footage,transcribe,fonts,designgen,styleframe,preview}.py`
  one-liners and the two new skill folders; in the quick start add a "look at footage and pick a design" block:
  `log-footage ../examples/demo/media --out /tmp/demo-analysis`, `design-propose --analysis /tmp/demo-analysis --out /tmp/demo-preview --mood warm`, `design-preview --dir /tmp/demo-preview`.
- `docs/design.md` §9: mark steps for `footage-logging` and `design-system` as done for Milestone 2a, and add a line
  saying what remains (grade previews, audio-post, video-qa, video-director, studio-doctor).
- `docs/components.md`: under caption/quote, document `"voice": null` with required `in`/`out` and scheduled word
  reveals (0.35 s after `in`, 0.12 s per word, 0.3 s between lines).

- [ ] **Step 4: Verify the documented commands run**

Run, from `engine/`:

```
python3 -m aestudio log-footage ../examples/demo/media --out /tmp/aestudio-2a/analysis
python3 -m aestudio design-propose --analysis /tmp/aestudio-2a/analysis --out /tmp/aestudio-2a/preview --mood warm --mood modern
python3 -m aestudio design-preview --dir /tmp/aestudio-2a/preview --no-wait
python3 -m aestudio design-choose --dir /tmp/aestudio-2a/preview --out /tmp/aestudio-2a/plan/design.json --id <first draft id>
python3 -m aestudio design-styleplan --dir /tmp/aestudio-2a/preview --analysis /tmp/aestudio-2a/analysis --out /tmp/aestudio-2a/style --id <same id>
python3 -m unittest discover -s tests -t .
```

Expected: every command prints its JSON line and exits 0; the full suite passes. Report the printed draft ids and the
index path in your report; do not open a browser or run After Effects.

- [ ] **Step 5: Commit**

```bash
git add skills/footage-logging skills/design-system README.md docs/design.md docs/components.md
git commit -m "docs: footage-logging and design-system skills"
```

---

### Task 11: Live checkpoint (controller runs this with the user)

**Files:** none — this is a review gate, not code.

The controller runs these with the user and does not delegate them:

1. `log-footage` over a real footage folder the user names, then show two or three contact sheets.
2. `design-propose` with mood words from the user, `design-preview`, and give them the URL to click.
3. `design-choose`, then `design-styleplan` + `build` + `still` with After Effects open on a new project, and show
   both stills.
4. Ask the user whether a mockup matched its After Effects still closely enough to trust the previews next time;
   record the answer in the plan's ledger and, if not, note which part drifted (fonts, sizes, card padding, colour).

Only after that does Milestone 2a count as verified.

---

## Out of scope for Milestone 2a (later plans)

Grade look previews (`color-grade`), `audio-post` (voice cleanup, music editing, ducking application), `video-qa`,
the `video-director` orchestration of all seven gates, `studio-doctor`, bundling the MCP bridge in `.mcp.json`, and
new component treatments beyond the two registered sets.

Also deferred: the spec's automated legibility guardrails (contrast measured against the frames a caption sits on, safe-zone and hold-time checks). Milestone 2a shows the mockups and the After Effects still and asks the user to judge; `video-qa` gets the measurements.
