# Component contracts

Every design implements the same five components, so an edit plan works with any design.
Times are seconds on the timeline. Pixel values in designs are authored for 3840×2160 and scale with the comp width.

Pixel values in a plan (layout `panels` `x`/`y`/`w`/`h`, CRT `bar_top`/`bar_bottom` above 1) are comp pixels.
Set `"design_size": [1920, 1080]` at the top of the plan to author them for that frame instead: they are scaled
to `format` on load, so the same plan renders a 1080p review and a 4K master by changing only `format`.

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

`line-fade` and `rule-wipe` fade a soft dark scrim in behind the type (`scrim-bottom`, `-top` or
`-center.png` beside the design, chosen by `place`), so pale type stays legible on light footage.
Scrims sit beneath every graphic layer, so one graphic's scrim never dims another's type.

### editorial

A third family, `editorial`, sets type directly on full-bleed footage with a vertical gradient
scrim darkening only the band the type sits on. It covers `title-page`, `caption`, `quote` and
`end-card`, plus `opening`, `inset` and `layout`. Two things to know before choosing it:

- There is **no editorial `lower-third`**, so a design using editorial must take its lower third
  from another family (`rule-wipe` or `paper-tab`).
- The editorial `end-card` is a **closing statement built from `lines`**, not the info card with
  `title`/`year`/`tagline`/`rows`. Feeding it an info end card raises an error naming a treatment
  that does render rows.

### blocks

`engine/aestudio/components/blocks.py` adds four graphic types that work in any design (the design does
not need to name them; each has a default treatment) and four treatments a design can pick. Colours are
palette tokens; where a field takes a colour it also accepts `"white"`, `"black"` or `"#RRGGBB"`.
`x`, `y`, `cx` are fractions of the frame; `width`, `cell`, `row_h`, `value_x` are 4K px and scale with the comp.

| Type | Default treatment | Fields |
|---|---|---|
| `block` | `positioned` | `x`, `y`, `align` (`left`/`right`), `scrim` (`left`/`right`/`bottom`), `kicker`, `rule`, `rays`, `ray_color`, `width`, `items`, `rows`, `line_at`, `schedule`, `delay`, `step`, `line_pause`, `row_h`, `key_mult`, `value_x` |
| `chips` | `divided` | `words`, `y`, `cx`, `cell`, `role`, `mult`, `hl` (indices), `scrim`, `delay`, `step` |
| `subtitle` | `whole-line` | `lines`, `cx`, `y` (last line), `scale`, `fade`, `whole` |
| `fade-in` | `solid` | `in`, `out`, `color` (default black) |

```json
{"type": "block", "voice": "N1", "x": 0.06, "y": 0.1, "scrim": "left", "kicker": "Question",
 "items": [{"lines": [["우리 아이들이 가장 오래 머무는 곳,"]], "role": "body", "mult": 0.82},
           {"lines": [["학교."]], "role": "headline", "mult": 1.9, "gap": 1.0}]}
{"type": "block", "in": 31, "out": 41.8, "x": 0.07, "y": 0.26, "kicker": "Topics", "width": 1050,
 "rows": [{"at": 32.7, "n": "01", "key": "Evolution"}, {"at": 37.6, "key": "Life", "key_color": "accent"}]}
{"type": "chips", "in": 72, "out": 75.6, "y": 0.885, "cell": 620, "scrim": "bottom", "words": ["one", "two", "three"]}
{"type": "subtitle", "in": 13.3, "out": 15.5, "lines": [["Whole line, no word reveal"]], "y": 0.955, "fade": 0.12}
{"type": "fade-in", "in": 0.4, "out": 1.8}
```

- `block` items are `{lines, role, mult, gap, after, color}`; rows are `{at, key, value, n, key_color}`.
  Words follow the `voice`, or a schedule when there is none (or `schedule: true`); `line_at` gives each
  line its own start time instead.
- `subtitle` shows each line whole when there is no voice; with a voice and `whole: false` it reveals word by word.

Treatments a design can choose:

| Component | Treatment | What it adds |
|---|---|---|
| caption, quote | `label-scrim` | `line-fade` over `scrim-caption.png`, optional `tint` (paper %), a spaced `label` above and `by` below. A caption carrying `black_in`, `sub`, `block` or `chips` renders as `fade-in`, `subtitle`, `block` or `chips` with those fields. |
| title-page | `light-rays` | Scripture lines over a paper tint and slow diagonal rays (`ray_color`, `tint`, `photo`, `voice`, `ref`). |
| end-card | `date-row` | Logo, `kicker`, `title`, optional `dates: [{num, label, sub}]` between rules, `contact` and `contact_label`. `logo.color` tints the mark with a token or `"white"`; `logo.tint: false` keeps its colours. |
| layout | `accent-band` | Editorial panels over an accent `band` (`{y, h}` or `false`), `kicker`, `title`. `crt: true` turns the first panel into a black-and-white CRT with `bar_top` / `bar_bottom` bars (≤ 1 is a fraction of the height, larger is px); `split: true` adds right-hand pull `quotes: [{in, out, lines: [{text, hl}], note}]`. |

These treatments read their scrims from beside the design.json: `scrim-left.png`, `scrim-right.png`,
`scrim-caption.png`, `scrim-split.png` and `crt-vignette.png`, each only when a graphic uses it.

A new treatment is a function registered with `@register(component, treatment)` in
`engine/aestudio/components/`, built only from ops and the helpers in `layout.py`.
