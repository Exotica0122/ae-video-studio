# ae-video-studio — design

Status: draft for review · 2026-09-17

A Claude Code plugin that turns raw footage, voice recordings and a short brief into a
polished, motion-designed video built and rendered in **Adobe After Effects**. It is
general-purpose: promos, testimonies/interviews, event recaps, announcements, explainers.

The workflow was first proven on a real production. That project's files live with its own
footage, **not in this repo**; the repo only holds reusable code, design packages, docs and
fictional examples (`examples/`).

## 1. Scope

**In scope**
- Story structure from footage, narration and interview/testimony audio.
- Audio post: voice cleanup and levels, natural pauses, music edit, voice-aware ducking, SFX.
- Colour grade with per-shot brightness matching.
- Motion graphics from a chosen design system: captions, quotes, lower thirds, title/scripture pages, end card, logo.
- Build and render entirely in After Effects via script; review and 4K master deliverables.
- Preview-and-approve gates before every expensive or taste-dependent step.

**Out of scope**
- Premiere Pro. Nothing in this flow needs it. An editable-Premiere handoff could be a separate add-on later without changing this plugin.
- Stock footage/music sourcing, uploading and publishing.

## 2. Dependencies

| Need | Why | Checked by |
|---|---|---|
| After Effects 2025+ | build + render | `studio-doctor` |
| after-effects-mcp with `runJsx` | run generated ExtendScript, get JSON back | `studio-doctor` (bridge ping) |
| MCP Bridge Auto panel open, Auto-run on | executes queued jobs | `studio-doctor` |
| ffmpeg / ffprobe | probing, loudness, audio edits, share copies | `studio-doctor` |
| Python 3.10+ (+ Pillow) | generators, analysis | `studio-doctor` |
| mlx-whisper (Apple Silicon) or faster-whisper | word timestamps for synced reveals | `studio-doctor` |
| Fonts chosen at the design gate | typography | checked after the design gate, before any build |

The `runJsx` change to the upstream after-effects-mcp is preserved in
`bridge/runJsx.patch` (base commit in `bridge/base-commit.txt`). The plugin should ship
the bridge itself (fork or vendored build) and register it in `.mcp.json`, so installing the
plugin is the only setup step besides installing the AE panel.

## 3. The flow and its approval gates

Nothing expensive or taste-dependent happens without the user's OK. Each gate produces a
preview the user can look at, and records the decision in the project's `plan/` folder.

| Gate | Stage | User sees | User decides | Recorded in |
|---|---|---|---|---|
| 0 | Brief | questions, one at a time | purpose, audience, length, must-have info (dates, contacts), logo | `plan/brief.md` |
| 1 | Story | story table: beats × voice × footage | structure, what's in/out, testimony lines | `plan/story.md` |
| 2 | Design | 2–3 style frames made from the real footage and real text, each with its own palette **and 2–3 font pairings** | design direction + fonts | `plan/design.json` |
| 3 | Grade | same 4 representative shots in 3–4 looks, real AE renders, side by side | look (optionally "push it further") | `plan/grade.json` |
| 4 | Test clip | real ~15 s render of the opening | "finish it" or adjust | notes in `plan/decisions.md` |
| 5 | Key stills | lower third, end card, logo placement, any scripture page | details before the long render | `plan/decisions.md` |
| 6 | Review render | full 1080p render + share copy + QA report | notes → fix → re-render | `qa/report-vNN.md` |
| 7 | Master | final 4K render | done | `exports/` |

Rules:
- A gate is never skipped because the change "looks small". Small tweaks after gate 6 can
  reuse the same gate with a still or an audio-only render instead of a full render.
- Previews are shown on a self-contained local comparison page (`preview/index.html`,
  click to pick) that the plugin generates. No dependency on other plugins.
- Rendered clips and stills open straight from the project folder.

## 4. Skills

Split by stage of work, each with a clear input and output artifact, so a single stage can
be re-run ("re-grade", "move the logo") without touching the others.

| Skill | Responsibility | Reads | Writes |
|---|---|---|---|
| `video-director` | Entry point. Runs the brief, owns the gate sequence, routes to the other skills, keeps `plan/decisions.md` | everything in `plan/` | `plan/brief.md`, `plan/story.md` |
| `studio-doctor` | Environment + bridge + font checks with fix instructions | — | console report |
| `footage-logging` | Probe clips, contact sheets, per-shot luma, transcripts with word timings | source folders | `analysis/footage.json`, `analysis/luma.json`, `analysis/transcripts/*.json`, `analysis/sheets/*.png` |
| `audio-post` | Trim/normalise voices, place voices with natural breaths, cut music to length, voice-aware ducking, SFX placement, loudness targets | `plan/story.md`, transcripts | `plan/edit.json` (voices, music, sfx sections) |
| `color-grade` | Build look previews (gate 3), per-shot exposure matching, selective wall/colour calming | `analysis/luma.json` | `plan/grade.json` |
| `design-system` | Creates 2–3 distinct design directions per video from primitives (gate 2), style frames, font pairings; saves reusable designs | brief, `plan/story.md`, footage | `plan/design.json`, `preview/` |
| `ae-build-render` | Compile `plan/edit.json` + design package into ExtendScript; build comp; test clip, stills, review render, 4K master; render polling | all of `plan/` | AE project, `exports/*` |
| `video-qa` | Decode check, per-section loudness, music-before-voice check, SFX audibility, stills, share copy | exports, `plan/edit.json` | `qa/report-vNN.md`, share copy |

Subagents are used only where they pay off:
- **footage-logging** — many clips, parallelisable, would flood the main context.
- **video-qa** — an independent reviewer that did not build the video.

## 5. Per-video project layout

Created by `video-director` inside a folder the user picks (usually next to the footage):

```
<project>/
  plan/        brief.md  story.md  design.json  grade.json  edit.json  decisions.md
  analysis/    footage.json  luma.json  transcripts/  sheets/
  preview/     index.html + style frames, grade looks, stills
  build/       generated .jsx, AE project (.aep)
  exports/     test clip, review renders, share copies, 4K master
  qa/          report-vNN.md
```

Everything the plugin generates is reproducible from `plan/` + `analysis/`, so the AE
project can always be rebuilt.

## 6. The edit plan (`plan/edit.json`)

A one-off generator script hard-codes shots, card text and timings. The plugin separates
**what** (data, per video) from **how** (builder + design package, shared):

```jsonc
{
  "format": { "width": 3840, "height": 2160, "fps": 23.976 },
  "design": "plan/design.json",               // recipe chosen at gate 2 (or a saved design id)
  "voices": [
    { "id": "N1", "file": "voice/narration-1.wav", "at": 8.40, "gain_db": -2.5,
      "words": "analysis/transcripts/narration-1.json" }
  ],
  "music":  { "file": "music/theme.wav", "edit": [[0, 75.89], [245.58, 258.29]],
              "duck": { "under_voice": -8, "breath": -5, "swell": -1, "lead": 0.25 } },
  "sfx":    [ { "file": "sfx/paper-slide.mp3", "at": 6.82, "gain_db": -1, "role": "page-out" } ],
  "shots":  [ { "clip": "footage/C0012.MP4", "in": 6.80, "out": 9.90, "src_in": 0.30 } ],
  "graphics": [
    { "type": "title-page", "in": 0, "out": 8.2, "kicker": "Opening quote", "text": "...", "highlight": ["key phrase"] },
    { "type": "caption", "voice": "N1", "lines": [["Every great team"], ["starts with", {"hl": "one small step"}, "."]], "place": "bottom-left" },
    { "type": "quote", "voice": "I1", "lines": [...] },
    { "type": "lower-third", "at": 13.85, "name": "Jordan Lee", "role": "Volunteer, 3 years" },
    { "type": "end-card", "title": "Open Day", "year": "2027", "tagline": "...", "rows": [...], "photo": {...},
      "logo": { "file": "examples/sample-logo-white.png", "tint": "ink" } }
  ]
}
```

Words are referenced by text, not by index; the builder resolves each word's time from the
transcript, so re-recording a narration only needs a new transcript.

## 7. Design system: generating designs, not picking a template

The plugin must be able to create **new, varied designs** for each video, such as paper
notebook, cinematic minimal, bold kinetic type, editorial magazine, hand-drawn, retro film,
clean corporate or playful kids, not only reuse one look. Paper notebook is one design among
many and has no special status in the code.

### 7.1 Three layers

| Layer | What it is | Changes per design? |
|---|---|---|
| **Primitives** (`lib/primitives/`) | Small, well-tested ExtendScript building blocks: text layer with reveal (by char / word / line, synced to word times), shape box / pill / rule / underline / strike, mask wipe, texture (noise, paper, grain), shadow / glow / blur, image/footage frame, track-matte, parallax, light leak, easing + settle curves, 3D card flip | no — shared by all designs |
| **Component contracts** (`lib/components.md`) | What each on-screen element receives and must respect: `caption`, `quote`, `lower-third`, `title-page`, `section-break`, `kinetic-phrase`, `end-card`, `logo`, `transition` — text, word timings, highlights, placement safe zones (faces, subtitles), in/out times | no — the same edit plan works with any design |
| **Designs** (`designs/<id>/`) | A *recipe*: tokens + one treatment per component that composes primitives | yes — this is what gets created |

Because designs are **data composed of primitives**, Claude can author a brand-new design at
gate 2 without writing new engine code. A design may add a custom component in JSX when a
look truly needs something the primitives can't express; if that proves reusable, it is
promoted into a primitive.

### 7.2 A design (`designs/<id>/design.json`)

```jsonc
{
  "id": "cinematic-minimal",
  "mood": ["restrained", "emotional", "premium"],
  "tokens": {
    "palette": { "ink": "#F4F1EA", "accent": "#C9A46A", "shade": "#0E0F12" },
    "type":    { "headline": "<font>", "body": "<font>", "quote": "<font>" },   // filled at gate 2
    "motion":  { "ease": "expo-out", "in": 0.8, "out": 0.5, "settle": false },
    "texture": { "grain": 0.08 }
  },
  "components": {
    "caption":     { "layout": "lower-center", "reveal": "line-fade-up", "emphasis": "accent-color", "backing": "none" },
    "quote":       { "layout": "side-of-speaker", "marks": "thin-serif", "reveal": "word-fade", "backing": "vignette-scrim" },
    "lower-third": { "style": "rule-and-text", "enter": "mask-wipe-right" },
    "title-page":  { "background": "black-frame", "reveal": "letter-track-in" },
    "end-card":    { "layout": "centered-stack", "media": "blurred-footage", "logo": "tint-ink" },
    "transition":  { "default": "cut", "section": "dip-to-black" }
  },
  "grade_hint": "soft-contrast-warm",       // suggested starting look for gate 3
  "sfx_hint":   ["low-whoosh", "soft-hit"]  // suggested sound palette for audio-post
}
```

Built-in designs are just saved recipes in the same format; they serve as starting points and
as regression tests. A design created for one video can be saved into `designs/` with
"save this design" (without any video-specific text or assets).

### 7.3 How gate 2 creates options

1. Read the brief and story: purpose, audience, tone, footage character (bright rooms,
   night event, phone testimony), brand colours and logo.
2. Propose **2–3 clearly different directions**, not variations of one idea: at most one
   based on an existing built-in design, the others newly composed. Each direction gets a
   name, a one-line rationale and 2–3 font pairings suited to the language(s) in the video.
3. Render style frames for each direction from the **real footage and real script lines**:
   one caption, one quote/lower third, one title or end card. Quick HTML mockups are fine for
   the first round; the chosen direction is confirmed with real AE stills before gate 3.
4. The user can pick, mix ("A's type with B's colours"), or ask for another round.
5. The chosen recipe is written to `plan/design.json`; fonts are checked before building.

Guardrails for every design: text legible on any shot (contrast check against the frames
it sits on), never covers faces, respects subtitle/safe zones, readable hold times based on
text length, and Korean/CJK line-breaking by word, not by character.

### 7.4 Logos

Handled by the `logo` component per design: single-colour logos are recoloured to a design
token with an AE Fill effect (original file untouched); multi-colour logos are placed as-is,
on a backing (chip, scrim, clear space) chosen by the design. `examples/sample-logo-white.png`
is a fictional logo for testing.

## 8. Rules learned in production

Audio
- Voices at natural speed; ~1 s breath at each change of speaker; longer "music breath"
  moments are allowed. Longer video is preferred over a cramped one.
- Voices ≈ −16 LUFS; whole mix ≈ −16/−17 LUFS integrated; peaks ≤ −1.5 dBFS.
- Ducking is keyed from voice **onsets and offsets** (fully down 0.25 s before each onset),
  never from beat positions. Gaps < 0.8 s stay down, < 2 s get a small lift, longer gaps swell.
- Long SFX (e.g. 6 s harp sweep) must be faded out before the next voice onset.
- QA measures music RMS in the 0.3 s before every voice onset, not just integrated loudness.
- SFX levels are verified in the mix; a sound that doesn't raise the local RMS is inaudible.

After Effects scripting
- Never queue a job while the bridge status is `running`; run jobs sequentially.
- Scripted renders block the AE UI (Stop button unresponsive); long renders exceed tool
  timeouts, so poll `ae_command.json` in the background.
- Adding a property to a shape group invalidates earlier references; re-fetch.
- Parenting to an animated null adds compensating rotation/position; reset after parenting.
- `saveFrameToPng` is asynchronous; wait for the file.
- Wrap save/export in `app.beginSuppressDialogs()`.
- Text layout expressions: `sourceRectAtTime(...)` + `posterizeTime(0)` for stable, cached geometry.
- Word-synced reveals: Expressible text selector, Based On Words.
- Lumetri property indices: 15 Temperature, 16 Tint, 17 Saturation, 20 Exposure, 21 Contrast,
  22 Highlights, 23 Shadows, 24 Whites, 25 Blacks, 41 Faded Film, 42 Sharpen, 43 Vibrance.
- Audio-only check: render with the "AIFF 48kHz" output template (~15 s vs ~10 min).

Grade
- Per-shot exposure offset from measured luma toward a target; cap offsets on already-bright shots.
- Calm strong wall colours with Change Color (hue match, small saturation drop); heavy
  settings turn walls grey.

## 9. Build order

1. **Repo skeleton** — manifest, README, this doc, bridge patch, sample logo. *(done)*
2. **Primitives + component contracts** — generalised from the first production's
   generator; bridge client (queue job, poll, fetch result).
3. **`ae-build-render` core** — `edit.json` + design recipe → JSX for shots, voices, music, SFX, graphics.
4. **Two contrasting designs at once** — `notebook` and a deliberately different one
   (e.g. `cinematic-minimal`), so nothing paper-specific leaks into the engine.
5. **Parity test (local only)** — rebuild the first production from an `edit.json` kept with
   that project (outside the repo); compare stills and per-section loudness with its approved
   render. Then re-render the same edit with the second design, changing only `design`.
   Add a small fictional example under `examples/` for anyone else to test with.
6. **`audio-post`** and **`video-qa`** scripts (ducking, placement, loudness, legibility checks).
7. **`footage-logging`** *(done, Milestone 2a)* — `color-grade` (luma matching, look previews) is not
   part of this milestone.
8. **`design-system`** gate 2: generating new directions, style frames, font pairings,
   `preview/index.html`, "save this design". *(done, Milestone 2a)*
9. **`video-director`** orchestration + `studio-doctor`.

Milestone 2a shipped `footage-logging` and `design-system` (steps 7–8, minus `color-grade`). What
remains: grade previews, `audio-post`, `video-qa`, `video-director`, `studio-doctor`.
10. Try on a second, different kind of video; fix what doesn't generalise.

## 10. Open questions

- Ship the AE bridge as a fork of Dakkshin/after-effects-mcp or vendor a minimal bridge?
- Whisper backend: mlx-whisper only (Apple Silicon), or also faster-whisper for Windows?
- Should the plugin bundle a small CC0/Mixkit SFX pack, or download on demand?
- Which 3–4 built-in designs should ship first besides `notebook`?
