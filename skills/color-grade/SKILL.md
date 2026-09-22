---
name: color-grade
description: Run the grade gate for an ae-video-studio video — match exposure across shots that were filmed under different light, show 3 looks on the video's own footage side by side, and record the choice as plan/grade.json. Use at gate 3, after the design is chosen and before building, or when shots do not cut together.
---

# Choose the look

```
PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio grade-propose \
    --analysis <project>/analysis --out <project>/preview/grade --mood warm hopeful
PYTHONPATH=... python3 -m aestudio design-preview --dir <project>/preview/grade   # serve + wait for a click
PYTHONPATH=... python3 -m aestudio grade-choose --dir <project>/preview/grade \
    --analysis <project>/analysis --out <project>/plan/grade.json
```

`design-preview` is the same click-to-choose server the design gate uses; the grade page follows the
same contract, so there is no second server to learn.

## The two halves of a grade

**Matching** evens out shots filmed under different light so a cut does not flash. Each clip's mean
brightness from `analysis/footage.json` is corrected towards the median shot, in stops. A clip needing
more than **0.75 stops** is clamped and reported rather than pushed — that far off is a different
lighting situation, and pushing it turns noise into the subject. Show the user that list; the answer is
usually to drop the shot or to accept it as is.

**The look** is the taste on top: `neutral`, `warm-airy`, `cool-clean`, `filmic`. The previews are
ffmpeg approximations rendered on **4 shots spread across the brightness range of the real footage**, so
a look is judged on the hard shots and not only on the flattering one. `plan/grade.json` carries
neutral parameters (exposure, contrast, temperature, tint, saturation, shadows, highlights) that the
builder applies for real in After Effects.

## Rules

- Always keep a `neutral` option on the page. "Do nothing" is a legitimate choice and the user should
  be able to make it without arguing.
- Propose looks from the brief's moods, and say why each one is there.
- The preview reuses frames already sampled by `footage-logging`, so this gate works with the footage
  drive unplugged. If a clip has no sampled frame and the source is gone, it says so — do not silently
  drop that shot from the comparison.
- Exposure matching is not a fix for bad footage. If many clips land in `beyond_match`, say so plainly.
