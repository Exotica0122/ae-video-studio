---
name: design-system
description: Propose 2-3 design directions for an ae-video-studio video from its own footage, show them as clickable browser mockups with font pairings, record the choice as plan/design.json, and confirm it with a real After Effects still. Use at the design checkpoint, before any build, or when the user asks to see design or font options.
---

# Design directions (gate 2)

Run commands with `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`.
Needs `analysis/footage.json` from the `footage-logging` skill.

## The flow

1. **Propose** — mood words come from the brief (e.g. warm, hopeful, modern, restrained):

   ```
   design-propose --analysis <project>/analysis --out <project>/preview --mood warm --mood hopeful \
     --lines <project>/plan/lines.json
   ```

   Writes `<project>/preview/index.html` (mockups built from the video's own frames) and `drafts.json`.

   `--limit` sets how many **directions** to propose (default 3); `--pairings` how many typefaces
   each direction is offered with (default 2, the spec asks for 2–3). Every pairing is its own card
   with its own Choose button, so three directions at two typefaces is six cards — say that to the
   user before they scroll, and point out which cards are the same direction in different type.

   `--lines` is a JSON array of caption lines in the `lines` format from `docs/components.md`, e.g.
   `[["작은 "], [{"hl": "한 걸음"}, "에서 시작합니다"]]`. Use a real line from the script: placeholder text
   is the wrong length and the wrong words, so the readability check only means something with the
   user's own sentence.

2. **Preview and let the user click**:

   ```
   design-preview --dir <project>/preview --timeout 1800
   ```

   It prints a `http://127.0.0.1:…` URL, then waits. Give the user that link and say what to look for: readability
   over their footage, the highlight colour, and the fonts. They click "Choose this" (and may type a note).

3. **Record the choice**:

   ```
   design-choose --dir <project>/preview --out <project>/plan/design.json
   ```

4. **Confirm in After Effects** — the mockups are approximations, so always confirm the winner:

   ```
   design-styleplan --dir <project>/preview --analysis <project>/analysis --out <project>/style \
     --lines <project>/plan/lines.json
   build <project>/style/edit.json --design <project>/plan/design.json --project <project>/build/style.aep
   still --comp <name> --time 1.2 --out <project>/preview/style-caption.png
   still --comp <name> --time 4.5 --out <project>/preview/style-endcard.png
   ```

   `<name>` is the `name` printed by `design-styleplan`.

   Show both stills. Check the text is readable over the real footage, nothing is clipped, and the Korean line breaks
   fall between words. Only then move on to the story and the full edit plan.

## Rules

- Only fonts the catalogue reports as installed are offered. With `--allow-uninstalled-fonts`, each draft carries an
  install note with its licence and link — pass that note to the user and let them decide. `design-choose` repeats
  those notes and re-checks the chosen design's fonts, printing a `warning:` line for anything not installed;
  After Effects would otherwise substitute the font silently.
- Milestone 2a varies palette, fonts and which treatment set is used (paper-card family or line-fade family).
  A genuinely new caption or end-card treatment is a code change, not a draft — say so rather than promising it.
- "Mix A's type with B's colours" is a normal request: run `design-choose` for the base, then edit
  `plan/design.json` (tokens only) and re-run the style frame to confirm.
- The mockups never replace the After Effects still. Do not start a full build from mockups alone.
- Keep `preview/`, `plan/` and `analysis/` in the video's own project folder.
