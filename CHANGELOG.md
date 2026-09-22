# Changelog

Notable changes to ae-video-studio. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Until 1.0, a minor version may change the edit-plan
or design format.

## [Unreleased]

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
