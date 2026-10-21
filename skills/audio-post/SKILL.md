---
name: audio-post
description: Lay out the audio of an ae-video-studio video — measure each voice take, place them with natural pauses, set levels to a loudness target, and cut the music to length with voice-aware ducking. Use after the story gate and before building, or when narration timing, levels or music length need changing.
---

# Lay out the audio

```
PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/engine python3 -m aestudio audio-plan <spec.json> \
    [--out plan/audio.json | --merge plan/edit.json] [--root <project>] [--start 0] [--target -16]
```

The spec lists the takes in the order they are heard:

```json
{"takes": [{"id": "N1", "file": "voice/narration-1.wav", "speaker": "narrator",
            "words": "analysis/transcripts/narration-1.json"},
           {"id": "T1", "file": "voice/testimony-1.wav", "speaker": "김은혜", "gap_after": 1.6}],
 "music": {"file": "music/theme.wav"},
 "duration": 75.0}
```

### Two or more music tracks

`music` may also be a list of segments, one per track, each placed on the timeline. Track A from the
start to a line of narration, then track B overlapping it for the handoff:

```json
"music": [{"file": "music/a.mp3", "end": 55.5, "fade_out": 1.5},
          {"file": "music/b.mp3", "start": 54.0, "src_in": 3.2, "fade_in": 1.5, "gain_db": -2}]
```

`start`/`end` are timeline seconds (`end` defaults to the end of the video), `src_in` is where to start
in the file. Every segment ducks under the same voices, with its fades laid over the duck curve. A
segment is never looped, so audio-post refuses one whose file is too short. Mix nothing by hand into
one wav: the segments stay editable.

`--merge` splices `voices` and `music` into an existing `plan/edit.json` and touches nothing else —
shots and graphics belong to the story gate, so re-running this never rewrites an approved timeline.

## What it decides for you

- **Levels.** Each take is measured with `loudnorm` and gained to −16 LUFS, unless that would push its
  true peak past −1.5 dBFS — headroom wins, because a clipped peak is audible and a decibel under
  target is not. A file that measures as silence is refused rather than boosted 50 dB.
- **Placement.** Silence at the head and tail of a take is found with `silencedetect` and excluded, so
  the pause a viewer hears runs from the last word to the first word, not from file to file. Default
  gaps: **0.55 s** between takes from the same speaker, **1.10 s** across a change of speaker. Override
  per take with `gap_after`.
- **Music.** Cut to the video's length: trimmed if longer, looped if shorter, and a final loop shorter
  than ~1.2 s is dropped rather than clicking. `duck` defaults come with it; the builder turns
  `voice_spans` into the ducking curve.

## Rules

- Listen before trusting the numbers. Loudness targets make a mix consistent, not good.
- `gap_after` is the knob for pacing. If the user says the video feels rushed, raise the gaps around
  testimony rather than slowing anything down.
- The output records `speech` spans per take. Captions sync to words from the transcript, not to these,
  but the spans are what the music ducking is keyed from.
- Re-run freely: it only ever rewrites `voices` and `music`.

## Pronunciation lexicon (AI narration)

Before generating speech, check the script against `plan/lexicon.json`, the words this voice gets wrong:

```json
[{"text": "성과 가정", "say": "성꽈 가정",
  "note": "read as 성과 [result], not [성꽈]; reword, e.g. '성 정체성과 가정'"}]
```

```
lexicon-check plan/narration.md [more scripts] [--lexicon plan/lexicon.json]
```

It lists every line containing an entry. Re-spell it as `say` or reword the line, then generate. When
the user hears a new mispronunciation, add it to the lexicon so the next script is checked for it too.
