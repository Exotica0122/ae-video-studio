"""plan/lexicon.json: words AI narration mispronounces, and the script lines that contain them."""
import json
import re
from pathlib import Path


class LexiconError(ValueError):
    pass


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_lexicon(path) -> list:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise LexiconError(f"cannot read {path}: {e}") from e
    if not isinstance(data, list):
        raise LexiconError(f"{path}: expected a list of {{\"text\", \"say\", \"note\"}} entries")
    errors = [f"[{i}]: 'text' must be a non-empty string" for i, e in enumerate(data)
              if not isinstance(e, dict) or not isinstance(e.get("text"), str) or not e["text"].strip()]
    if errors:
        raise LexiconError(f"{path}:\n  " + "\n  ".join(errors))
    return data


def scan(lexicon: list, scripts) -> list:
    """Every script line containing a lexicon entry, whitespace-insensitive."""
    hits = []
    for script in scripts:
        for n, line in enumerate(Path(script).read_text(encoding="utf-8").splitlines(), start=1):
            flat = _squash(line)
            for entry in lexicon:
                if _squash(entry["text"]) in flat:
                    hits.append({"file": str(script), "line": n, "text": entry["text"], "say": entry.get("say", ""),
                                 "note": entry.get("note", ""), "context": line.strip()})
    return hits
