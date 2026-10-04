---
name: taste
description: Run the taste gate for an ae-video-studio video — collect reference images or clips the user likes (and ones they do not), measure their palette, contrast and warmth, look at each one and write down its traits, show a mood board the user ticks, and record the result as plan/taste.json for every later stage to follow. Use at gate 2, after the story and before design, or whenever the user shares a reference, a link or a "make it look like this".
---

# Taste (gate 2)

References the user gives are the most direct statement of what they want. Captured once here,
they are read by the design, grade and QA stages, so nobody has to say "use the reference photos
I gave you" twice.

Run commands with `PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio …`.

## The flow

1. **Ask for references**, one question at a time:
   - "Do you have images or videos whose look you want? Links or files both work."
   - "Anything you've seen that you do *not* want this to look like?" Avoid examples are as useful
     as wanted ones, so always ask.
   - If they have none, say that is fine and run `taste-choose --dir <project> --none`. The gate is
     recorded and later stages behave exactly as they do without references.

2. **Add them**. URLs are downloaded into `refs/`, never hotlinked; files are copied.

   ```
   taste-add --dir <project> <url-or-file> [<url-or-file> …]
   taste-add --dir <project> --avoid <url-or-file> …
   taste-add --dir <project> --at 2,6,11 <video-url-or-file>   # which seconds to sample from a video
   ```

   `refs/sources.json` records each original URL or path, the date and the role (`want` or `avoid`).
   A web page link fails unless yt-dlp is installed; ask the user for the image address instead.
   Video references are sampled into `refs/ref-NN-fK.jpg` frames.

3. **Measure**:

   ```
   taste-measure --dir <project>
   ```

   Writes `refs/taste.json`: per reference a 5-colour palette, mean luma, contrast (p95−p5 luma and
   its spread), warmth (R−B balance) and saturation; video adds cuts per minute. `targets` aggregates
   the `want` refs into ranges, with the `avoid` refs kept apart under `targets.avoid`.

4. **Look at every reference and write its traits.** Open each image or frame with the Read tool. The
   numbers cannot see type, layout or motion — you can. Add 3–6 short traits per ref to its `traits`
   list in `refs/taste.json`, each prefixed with its facet:

   ```json
   "traits": ["type: heavy condensed sans, all caps", "layout: text hugs the left third",
              "motion: slow push-ins, long holds", "mood: quiet, reverent", "color: one warm accent on near-black"]
   ```

   Facets: `type`, `layout`, `motion`, `mood`, `color`. Describe what is there, not what you would
   like to be there, and never write traits for an image you have not opened. `mood:` words are
   used like brief moods to rank design directions and looks. Re-running `taste-measure` keeps traits.

5. **Show the board**:

   ```
   taste-board --dir <project> --timeout 1800
   ```

   Writes `refs/board.html` and prints a `http://127.0.0.1:…/board.html` link, then waits. Each ref
   shows its swatches, numbers and traits; the user ticks ✓ what the video should have and ✗ what it
   must not, adds a note, and clicks Save. Ticks go back into `refs/taste.json`.

6. **Record the approval**:

   ```
   taste-choose --dir <project>
   decide --dir <project> --gate 2 --what "Taste: <2-3 approved traits>" --detail "<the note, avoid refs>"
   ```

   `taste-choose` refuses while any reference has no traits. It writes `plan/taste.json`, the only
   file later stages read.

## plan/taste.json

```json
{"version": 1,
 "refs": [{"id": "ref-01", "path": "refs/ref-01.jpg", "source": "https://…", "role": "want",
           "kind": "image", "added": "2026-10-04",
           "stats": {"palette": [{"hex": "#1E2A4F", "weight": 0.5}], "luma": 0.31, "contrast": 0.29,
                     "contrast_std": 0.15, "warmth": 0.22, "saturation": 0.71},
           "traits": ["type: …", "mood: …"]}],
 "approved_traits": ["mood: quiet, reverent"], "rejected_traits": ["layout: busy grid"],
 "targets": {"refs": ["ref-01"], "palette": [{"hex": "#…", "weight": 0.4}],
             "luma": {"min": 0.2, "max": 0.4, "mean": 0.3}, "contrast": {…}, "warmth": {…},
             "saturation": {…}, "cuts_per_min": {…}, "avoid": {…}},
 "note": "…", "approved_at": "…"}
```

## Rules

- Ask for avoid examples every time. "Not like this" is often clearer than "like this".
- The board is the decision. Do not tick traits for the user.
- Later stages must honour `approved_traits` and steer away from `rejected_traits`. When a design,
  layout, animation or grade choice is made, say which approved trait or reference it follows.
- Refs live in the video's own project folder. Do not delete `refs/` after approval.
