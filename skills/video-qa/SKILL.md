---
name: video-qa
description: Check a rendered ae-video-studio export with measurements rather than impressions — decode, loudness per section, music ducking before each voice, SFX audibility, colour contrast, text over people, and what changed since the previous render — and write qa/report-vNN.md with stills and a share copy. Use after any review or master render, or when the user asks whether a render is good.
---

# Check the render

```
PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio qa <export.mov> \
    [--plan plan/edit.json] [--design plan/design.json] [--sections sections.json] \
    [--out qa] [--stills 8.4,21.0,58.2] [--share exports/share-1080p.mp4] \
    [--diff exports/<previous-render>.mp4] [--no-people] [--taste plan/taste.json]
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
| `text-over-people:<still>` | Text covering more than 15 % of a face or person box in a still. |
| `diff:picture`, `diff:sound`, `diff:duration` | With `--diff`: what changed since the previous render, and whether its length changed. |
| `taste:palette`, `taste:luma`, `taste:contrast`, `taste:warmth`, `taste:saturation` | A render that drifted from the approved references. Measured on the stills (20/50/80 % if `--stills` is not given). |
| `taste:avoid` | Stills whose palette sits closer to the avoid refs than to the wanted ones. |

## Changes vs previous (`--diff PREV`)

When the user asks for a specific fix ("only adjust what I tell you to"), prove the fix touched
nothing else: run QA with `--diff` pointing at the render before the change. The report gets a
**Changes vs previous** section listing every changed range, for example `Picture 0:30.41–0:30.78`.

- Picture: both renders are sampled at 10 fps and 320 px wide. A frame counts as changed when more
  than 0.1 % of its pixels moved by more than 24 luma levels, which is above encoder noise. Changed
  frames less than a frame apart merge into one range.
- Sound: per-0.5 s RMS, flagged where the two differ by more than 1 dB (silence below −70 dB is ignored).
- Different lengths are reported as `diff:duration`, and the shared span is still compared.
- Stills at each range's midpoint are saved as `prev-<t>.jpg` and `still-<t>.jpg`. Open both before
  saying what changed.
- Any range you did not intend is the finding. Report it, and do not explain it away.

## Text over people

The user's most repeated note was "text must not cover the people". On macOS, every still QA takes
(`--stills` and the changed-range stills from `--diff`) goes through Apple Vision with a small
Swift script (`engine/aestudio/vision_detect.swift`, run with `swift`). Vision finds face and body
rectangles and recognised-text boxes. A still warns when text covers more than 15 % of a face or
person box, and the detail quotes the words. Without macOS or Swift, the check reports `skipped`.
It never reports a pass it did not measure.

Vision often loses a person once text sits on them, which would hide exactly the case this check
is for. So when `qa` has `--plan` and `--design`, it also takes the same moment from the source
shot, before any graphics, and finds people there. Text is taken from the render, and people from
both frames. Moments under a full-frame graphic, or in a zoomed, pushed or different-aspect shot,
use the render alone. With `text-cover`, pass the clean frames yourself with `--clean`, in the same
order as the images.

Run it on any stills, for example style frames or AE review stills:

```
PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio text-cover stills/*.jpg [--limit 0.15] [--clean clean/*.jpg]
```

Vision also reads text that is part of the footage, such as signs or shirts. Check the quoted
words before you call it a graphics problem. The first run compiles the script, which takes a few
seconds.

Pass `--taste` whenever the project has a `plan/taste.json`. Then open the stills beside the
references in `refs/` and check the `approved_traits` the numbers cannot see — type, layout, motion.

## Rules

- Report the numbers, not a verdict. "Bed only 1.2 dB down before N3" is actionable; "audio needs work" is not.
- A warning is not automatically a fix. Say what it means for this video and let the user decide.
- Measurement windows are cut with `atrim`, never by seeking — a fast seek lands on a packet boundary
  and can read the wrong side of a duck by tens of milliseconds. Keep it that way.
- Stills and the share copy are for the user to look at. Offer them; do not describe a frame you have not opened.
