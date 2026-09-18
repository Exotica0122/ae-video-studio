"""Turn Whisper output into the engine's transcript format (word start/end times)."""
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

DEFAULT_CMD = ("uvx mlx-whisper {audio} --model mlx-community/whisper-large-v3-turbo "
               "--word-timestamps True --output-dir {outdir} --output-format json")
MANUAL = ("transcribe it yourself (any Whisper build with word timestamps) and run "
          "`python3 -m aestudio import-transcript <json> --out <out>`")


class TranscribeError(RuntimeError):
    pass


def whisper_command(audio, outdir, template=None) -> list:
    template = template or os.environ.get("AESTUDIO_WHISPER_CMD") or DEFAULT_CMD
    parts = shlex.split(template)
    return [str(audio) if p == "{audio}" else str(outdir) if p == "{outdir}" else p for p in parts]


def _words(data: dict) -> list:
    segment_words = []
    for segment in data.get("segments") or []:
        segment_words += list(segment.get("words") or [])
    # The two shapes are alternatives: a build emitting both would otherwise duplicate every word.
    raw = segment_words or list(data.get("words") or [])
    words = []
    for item in raw:
        text = str(item.get("word", item.get("text", ""))).strip()
        if not text:
            continue
        try:
            start, end = round(float(item["start"]), 3), round(float(item["end"]), 3)
        except (KeyError, TypeError, ValueError) as e:
            raise TranscribeError(f"word {text!r} has no usable start/end: {e}") from e
        words.append([text, start, end])
    return words


def to_engine(data: dict) -> dict:
    words = _words(data)
    if not words:
        raise TranscribeError("no words with timings in this transcript; " + MANUAL)
    return {"onset": words[0][1], "offset": words[-1][2], "words": words}


def import_transcript(src_json, out_json) -> dict:
    src, out = Path(src_json), Path(out_json)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TranscribeError(f"cannot read {src}: {e}") from e
    result = to_engine(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def transcribe(audio, out_json, template=None) -> dict:
    audio = Path(audio)
    if not audio.exists():
        raise TranscribeError(f"audio not found: {audio}")
    with tempfile.TemporaryDirectory() as work:
        cmd = whisper_command(audio, work, template)
        result = subprocess.run(cmd, capture_output=True, text=True)
        produced = sorted(Path(work).glob("*.json"))
        if result.returncode != 0 or not produced:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
            raise TranscribeError("transcription command failed: " + " ".join(cmd) + "\n  "
                                  + " / ".join(tail) + f"\n  {MANUAL}")
        return import_transcript(produced[0], out_json)
