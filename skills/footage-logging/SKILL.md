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

Photos sitting beside the clips (JPEG, PNG, TIFF, WebP) are logged too, under `images`: size, mean brightness,
2×2 colours and a downscaled preview in `analysis/frames/`. They never appear in `clips` — a still has no duration,
so `style_frame_plan` can't build a timed shot from one — but design mockups fall back to image previews when a
shoot has fewer clip frames than design drafts, so a photo-only or photo-heavy shoot still gets real backgrounds.
RAW and HEIC files are not read (ffmpeg cannot reliably decode them on this machine). Camera sidecars — `.xml`,
`.thm`, `.lrv` — are ignored by design, not logged and not reported as errors.

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
