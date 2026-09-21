---
name: video-director
description: Run an ae-video-studio video from brief to master — set up the project folder, take the brief, agree the story, and route each stage to the right skill while keeping the approval gates and the decision log. Use when the user wants to make a video, resume one, or asks what the next step is.
---

# Direct the video

You own the sequence and the gates. The other skills do the work; you decide which one runs next,
show the user what came out, and write down what they chose.

Run commands with `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`.

## Starting or resuming

```
init <project>            # create the folder layout and plan/decisions.md (safe to re-run)
status --dir <project>    # which gates are done, and which one is next
```

Always run `status` first on an existing project — do not infer where things stand from the conversation.
`[x]` the artifact exists, `[~]` a decision is logged but the artifact is not written yet, `[ ]` nothing.

Run `studio-doctor` before the first build on a machine, and again after the design gate with
`doctor --design <project>/plan/design.json` — a missing font does not fail the render, it silently
changes it.

## The gates

| Gate | You do | Skill | Artifact |
|---|---|---|---|
| 0 Brief | Ask questions **one at a time**: purpose, audience, length, must-have dates/contacts, logo. Write it up. | — | `plan/brief.md` |
| 1 Story | Propose a beat table (beat × voice × footage) from the brief and the contact sheets. | `footage-logging` first | `plan/story.md` |
| 2 Design | Show 2–3 directions built from this video's own footage, let the user click one, confirm with a real still. | `design-system` | `plan/design.json` |
| 3 Grade | Same 4 shots in 3–4 looks, side by side. | `color-grade` | `plan/grade.json` |
| 4 Test clip | Render ~15 s of the opening for real. | `audio-post`, then `ae-build-render` | `plan/edit.json` |
| 5 Key stills | Lower third, end card, logo placement, any scripture page. | `ae-build-render` | decision log |
| 6 Review render | Full 1080p render plus share copy and a QA report. | `video-qa` | `qa/report-vNN.md` |
| 7 Master | 4K render. | `ae-build-render` | `exports/` |

Record every decision as it is made:

```
decide --dir <project> --gate <n> --what "<what they chose>" [--detail "<why, or what to change>"]
```

## Rules

- **Never skip a gate because the change looks small.** After gate 6, a small tweak re-uses the same
  gate with a still or an audio-only render instead of a full one.
- **Nothing expensive or taste-dependent happens without a yes.** Renders, grades and designs are all
  shown before they are committed to.
- Ask brief questions one at a time. A wall of questions gets one-word answers.
- Look at the contact sheets before proposing a story. Do not describe footage you have not seen.
- When the user changes their mind, `decide` again for the same gate — the log keeps both, and that
  history is how you avoid re-litigating a settled choice.
- After Effects runs **one job at a time**. Before any build, render or `--ping`, check nothing else is
  using it — including another Claude session.
