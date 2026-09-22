# Component contracts

Every design implements the same five components, so an edit plan works with any design.
Times are seconds on the timeline. Pixel values in designs are authored for 3840×2160 and scale with the comp width.

## Text segments

A line is a list of segments: plain strings, or `{"hl": "text"}` for the emphasised phrase.
Whitespace at a segment edge becomes a word gap; no whitespace means the segments touch, which is how
Korean particles attach to a highlighted word: `["작은 ", {"hl": "한 걸음"}, "에서 시작됩니다."]`.
Word reveal times come from the voice transcript by matching letters, so caption text must follow the
spoken words (punctuation and extra spoken words are ignored).

## caption / quote

```json
{"type": "caption", "voice": "N1", "lines": [[...], [...]], "place": "bottom-left", "in": 9.7, "out": 14.0}
```

- `voice` (required): id from `voices`; words reveal as they are spoken. `null` for a voiceless caption
  (no matching narration) — then `in` and `out` are required (no onset/offset to default from), and
  words reveal on a schedule: the first word 0.35 s after `in`, then 0.12 s per word, with 0.3 s between lines.
- `place`: `bottom-left | top-left | bottom-right | top-right | lower-center | top-center | center`.
- `in` / `out`: default a little before the voice onset and after its offset.

`place` and the `in`/`out` defaults depend on the design's treatment:

| Design (treatment) | caption `place` | quote `place` | `in` default | `out` default |
|---|---|---|---|---|
| notebook (`paper-card`) | `bottom-left` | `top-right` | onset − 0.3 | offset + 0.5 |
| cinematic-minimal (`line-fade`) | `lower-center` | `lower-center` | onset − 0.4 | offset + 0.6 |

## lower-third

```json
{"type": "lower-third", "at": 15.0, "dur": 4.25, "name": "Name", "role": "Role or title"}
```

## title-page

```json
{"type": "title-page", "in": 0, "out": 6.5, "lines": [[...]], "ref": "Reference or kicker"}
```

`out` is when the page starts leaving. There is no voice: words reveal on a schedule.

## end-card

```json
{"type": "end-card", "in": 31.0, "title": "Title", "year": 2027, "tagline": "One line",
 "rows": [{"label": "Label", "values": ["line 1", "line 2"]}],
 "photo": {"clip": "media/c.mp4", "src_in": 2, "stretch": 140},
 "logo": {"file": "logo.png", "tint": true, "width": 560}}
```

Runs until the end of the video. Keep 1–3 rows with 1–2 values each. `tint: true` recolours a
single-colour logo to the design's ink colour; use `false` for multi-colour logos.

## Treatments

| Component | notebook | cinematic-minimal |
|---|---|---|
| caption, quote | `paper-card` | `line-fade` |
| lower-third | `paper-tab` | `rule-wipe` |
| title-page | `notebook-page` | `black-frame` |
| end-card | `notebook-page` | `centered-stack` |

### editorial

A third family, `editorial`, sets type directly on full-bleed footage with a vertical gradient
scrim darkening only the band the type sits on. It covers `title-page`, `caption`, `quote` and
`end-card`, plus `opening`, `inset` and `layout`. Two things to know before choosing it:

- There is **no editorial `lower-third`**, so a design using editorial must take its lower third
  from another family (`rule-wipe` or `paper-tab`).
- The editorial `end-card` is a **closing statement built from `lines`**, not the info card with
  `title`/`year`/`tagline`/`rows`. Feeding it an info end card raises an error naming a treatment
  that does render rows.

A new treatment is a function registered with `@register(component, treatment)` in
`engine/aestudio/components/`, built only from ops and the helpers in `layout.py`.
