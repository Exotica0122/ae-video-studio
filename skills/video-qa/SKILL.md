---
name: video-qa
description: Check a rendered ae-video-studio export with measurements rather than impressions — decode, loudness per section, music ducking before each voice, SFX audibility, colour contrast — and write qa/report-vNN.md with stills and a share copy. Use after any review or master render, or when the user asks whether a render is good.
---

# Check the render

```
PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio qa <export.mov> \
    [--plan plan/edit.json] [--design plan/design.json] [--sections sections.json] \
    [--out qa] [--stills 8.4,21.0,58.2] [--share exports/share-1080p.mp4]
```

Writes the next `qa/report-vNN.md` and exits 1 if anything failed. Run it as a **subagent that did not
build the video** — the point is a reader who has no stake in the render being fine.

## What it measures

| Check | Catches |
|---|---|
| `decode` | A render that finished but is broken. Decodes every frame and sample. |
| `video-stream` / `audio-stream` | An export with no audio at all — easy to miss, fatal to send. |
| `mix-loudness`, `true-peak` | Off target, or peaks above −1.5 dBFS that will clip on playback. |
| `section:<id>` | One passage far off target while the average looks fine. |
| `music-before-voice` | **The bed must already be down before a voice starts, not duck as it starts.** Compares the bed in the 0.3 s before each voice against the bed at full level in a voice-free window. |
| `sfx:<role>` | An SFX that is in the edit plan but inaudible in the mix. |
| `contrast:<a>-on-<b>` | A generated palette that came out pretty and unreadable (WCAG AA, 4.5:1). |

## Rules

- Report the numbers, not a verdict. "Bed only 1.2 dB down before N3" is actionable; "audio needs work" is not.
- A warning is not automatically a fix. Say what it means for this video and let the user decide.
- Measurement windows are cut with `atrim`, never by seeking — a fast seek lands on a packet boundary
  and can read the wrong side of a duck by tens of milliseconds. Keep it that way.
- Stills and the share copy are for the user to look at. Offer them; do not describe a frame you have not opened.
