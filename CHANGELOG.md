# Changelog

Notable changes to ae-video-studio. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Until 1.0, a minor version may change the edit-plan
or design format.

## [Unreleased]

Lessons from a full church promo edit: 18 renders and 10 QA rounds.

### Added

- **Taste gate (new gate 2):** collect reference images or clips (`taste-add`, including ones to
  avoid), measure their palette, contrast, warmth and pace (`taste-measure`), then approve traits on
  a mood board (`taste-board`, `taste-choose`). Design proposals, grade looks and QA all read
  `plan/taste.json`. Later gates move up by one; existing decision logs still read correctly.
- **Timing lint in `validate`:** flash frames (a shot visible for a moment between full-frame
  graphics), text that overlaps in the same region, text too short to read, and captions that
  leave before their voice. `--strict` fails on any warning.
- **`qa --diff PREV`:** lists the time ranges where picture or sound changed since a previous
  render, with before and after stills.
- **Text over people:** `qa` (and `text-cover`) uses the macOS Vision framework to flag text
  covering faces or people.
- **`deliver`:** H.264 copies at 4K and 1080p with loudness normalised to −16 LUFS and −2 dBTP,
  checked after encoding. Previous deliveries move to `previous-vNN/`.
- **Music segments:** `music` can be a list of tracks, each with its own fades. Ducking applies to all.
- **`credits add` / `credits check`:** keep `assets/CREDITS.md` and flag media that has no credit.
- **`lexicon-check`:** scans narration scripts for words that TTS mispronounces.
- **Block components:** positioned text blocks, word chips, whole-line subtitles, a fade from
  black, label-scrim captions, a light-rays title page, a date-row end card with a tinted logo,
  and an accent-band layout with CRT and split variants.
- **`design_size`:** one plan renders at any resolution.
- **Named grade keys:** `"contrast"` and `"temperature"` instead of numeric Lumetri indices, plus
  `"grade": {"file": "grade.json"}`.
- **`build --next-version`:** builds into the next free `name-vNN.aep`, closes the open project,
  and keeps a copy of the plan beside the build.

### Fixed

- **Whisper:** the default command now runs the `mlx_whisper` executable.
- **Stale transcripts:** transcripts record a hash of their audio. Compile refuses a transcript
  whose audio has changed, instead of cutting the voice short.
- **Trimmed voices:** a word that straddles `src_in` is clamped rather than dropped, so captions
  after it stay aligned.

## [0.2.0] - 2026-09-22

First public release. The flow runs end to end, from footage and a brief to a 4K master,
with a preview you approve at each gate.

### Skills

- **video-director**: runs a video from brief to master. Sets up the project folder, agrees
  the story, routes each stage to the right skill and keeps a decision log.
- **studio-doctor**: checks Python, ffmpeg, Whisper, After Effects, the MCP bridge panel
  and fonts, and prints the exact fix for anything missing.
- **footage-logging**: probes clips and photos, samples frames, builds contact sheets,
  measures brightness, and turns Whisper output into word-timed transcripts.
- **design-system**: proposes 2–3 design directions from the video's own footage, each with
  2–3 licence-checked font pairings, as clickable browser mockups and a style frame.
- **color-grade**: matches exposure across shots and previews 3 looks on the video's own frames.
- **audio-post**: measures and places voice takes with natural pauses, levels them to a
  loudness target, and ducks the music under voice.
- **ae-build-render**: builds the After Effects comp from the edit plan and design, saves
  review stills, and renders with aerender.
- **video-qa**: measures the render instead of trusting it: loudness per section, music ducking
  before each voice, SFX against a clear baseline.

### Engine (`python3 -m aestudio`)

- Edit-plan validation and compilation to ExtendScript, with builds run through the MCP bridge:
  `validate`, `compile`, `build`, `run`, `still`, `render`.
- Project and gate tracking: `init`, `status`, `decide`.
- Footage and transcripts: `log-footage`, `transcribe`, `import-transcript`.
- Designs: `design-propose`, `design-preview`, `design-choose`, `design-styleplan`.
- Grade, audio and QA: `grade-propose`, `grade-choose`, `audio-plan`, `qa`.
- Environment check: `doctor`, with `--ping` to test the bridge end to end.

### Designs

- Saved designs `notebook` and `cinematic-minimal`, with title pages, word-timed captions with
  highlight sweeps, lower thirds, pull quotes and end cards.
- Archetypes for new designs: paper notebook, cinematic minimal, editorial press.
- A catalogue of seven Korean and Latin typefaces with licence notes.

### Bridge

- `bridge/install.sh` builds after-effects-mcp at a pinned commit with the `runJsx` patch,
  which only runs scripts from the bridge's own folder.

### Project

- MIT license, security policy, issue forms, and CI running the engine tests and demo
  validation on every pull request.

[Unreleased]: https://github.com/Exotica0122/ae-video-studio/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Exotica0122/ae-video-studio/releases/tag/v0.2.0
