---
name: ae-build-render
description: Build an After Effects comp from an ae-video-studio edit plan (plan/edit.json) and a design, save review stills, and render with aerender. Use when a video's edit plan and design are approved and the user wants a test build, stills, a review render or the final master.
---

# Build and render in After Effects

The engine lives in `${CLAUDE_PLUGIN_ROOT}/engine`. Run commands with
`PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`.

## Before building

1. After Effects is open with the **MCP Bridge Auto** panel, Auto-run on.
2. The open project is either the video's own project (`--project`, or `plan.project`, or by default `build/<NAME>.aep` next to the plan) or a new, unsaved one. The build checks, before it removes, replaces or saves anything:
   - a different saved project is open: refused;
   - no project path in the script and a saved project is open: refused (open a new, unsaved project);
   - the project file already exists but an unsaved project is open: refused, so a re-run never saves over an existing `.aep`. Open that `.aep` in After Effects first (or delete it), then build again;
   - a comp with the build's name exists outside the `ae-video-studio` build folder: refused (rename it or the plan). Only the comp, solids and nulls inside the build folder are replaced.
3. Premiere Pro is closed. Busy Premiere and After Effects can freeze each other.
4. `python3 -m aestudio validate plan/edit.json --design <design>` passes, and every font it lists is installed.

## Commands

| Goal | Command |
|---|---|
| Build the comp | `build plan/edit.json --design <id or path> --project build/<name>.aep` |
| Only generate the script | `compile plan/edit.json --design <id> --project build/<name>.aep` then `run build/<NAME>.jsx` |
| Review stills | `still --comp <NAME> --time <s> --out preview/<file>.png` (one per call) |
| Review or master render | quit After Effects, then `render --project build/<name>.aep --comp <NAME> --out exports/<file>.mov` |

## Rules

- One bridge job at a time. If a command reports the bridge is busy, wait; never submit in parallel.
- Read the build report. It is not done unless `ok` is true: fix `expressionErrors`, `missingFonts` or `error` first.
- Show stills to the user before any long render (docs/design.md gates 4–5).
- Renders always use `render` (aerender) with After Effects closed. Never script `renderQueue.render()` for long renders: it locks the After Effects UI and can freeze it.
- Tell the user before closing After Effects. A forced quit looks like a crash to them.
- `render` defaults to the "High Quality" output template (ProRes 422 on After Effects 2026). Make H.264 delivery copies from the master with ffmpeg.
