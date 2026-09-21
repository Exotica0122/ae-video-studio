---
name: studio-doctor
description: Check that this machine can build an ae-video-studio video — Python, ffmpeg, Whisper, After Effects, the MCP bridge panel and fonts — and print the exact fix for anything missing. Use before the first build on a machine, when a build or render fails for no obvious reason, or when the user asks why something will not run.
---

# Check the studio

```
PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio doctor [--design <project>/plan/design.json] [--json] [--ping]
```

Exit code is 0 when nothing failed, 1 when something did. Every failing check prints a `→` line with the fix;
give the user that line rather than inventing your own instructions.

## What it checks

| Check | Failing means |
|---|---|
| `python` | The interpreter is too old. `/usr/bin/python3` on macOS is 3.9 and cannot import the engine — use Homebrew's `python3`. |
| `ffmpeg`, `ffprobe` | No probing, frames, contact sheets or share copies. Hard requirement. |
| `whisper` | Warning only. Word-timed captions need it; everything else works without it, and `import-transcript` accepts a transcript made elsewhere. |
| `after-effects` | No 2025+ install found in /Applications. Also reports whether it is running. |
| `bridge` | `~/.ae-mcp-bridge` is missing (the panel has never run), or a job is in flight right now. |
| `bridge-panel` | The last result is very old, so the panel is probably closed or Auto-run is off. |
| `fonts` | Warning: catalogue families this machine lacks. Only matters if a design picks one. |
| `design-fonts` | Only with `--design`. **Failure here is serious**: After Effects silently substitutes a missing font, so the render comes out wrong rather than failing. Run this after the design gate and before any build. |

## Rules

- **The plain run never touches After Effects.** It only reads files, so it is always safe, even mid-render.
- `--ping` does touch it: it runs a one-line script through the bridge to prove the panel really executes.
  The bridge takes one job at a time, so only ping when After Effects is free — never while a render or another
  session's build is in flight. If `bridge` already warns that a job is running, do not ping.
- A `warn` is not a blocker. Say which one it is and whether this particular video needs that piece.
