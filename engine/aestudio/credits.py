"""assets/CREDITS.md: where every piece of media came from, and which plan media has no entry yet."""
import fnmatch
import re
from datetime import date
from pathlib import Path

from .plan import load_plan

CREDITS = "assets/CREDITS.md"
COLUMNS = ("File", "Source URL", "Author", "Licence", "Date", "Notes")
HEADER = "| " + " | ".join(COLUMNS) + " |"
TEMPLATE = """# Credits

Every file used in the video that was not made for it. Check the licence on the item's own page
before adding it, and record anything the licence asks of us in the notes.

## Media

{header}
|{rule}
"""


class CreditsError(RuntimeError):
    pass


def _cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _rel(path, root: Path) -> str:
    path = Path(path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def add(root, file, url, author, licence, notes="", when=None) -> Path:
    """Add or replace the entry for one file."""
    root = Path(root)
    if not licence:
        raise CreditsError("a credit needs a licence; ask the user which one applies")
    path = root / CREDITS
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else TEMPLATE.format(
        header=HEADER, rule="---|" * len(COLUMNS))
    rel = _rel(file, root)
    row = "| " + " | ".join(_cell(v) for v in (rel, url, author, licence, (when or date.today()).isoformat(), notes)) + " |"
    lines = text.splitlines()
    if HEADER not in lines:
        lines += ["", "## Media", "", HEADER, "|" + "---|" * len(COLUMNS)]
    start = lines.index(HEADER) + 2
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    rows = [r for r in lines[start:end] if _first_cell(r) != rel]
    lines[start:end] = rows + [row]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _first_cell(row: str) -> str:
    cells = re.split(r"(?<!\\)\|", row)
    return cells[1].strip() if len(cells) > 2 else ""


def credited_patterns(text: str) -> list:
    """Every file name or glob the credits mention, in a table's first column or in `backticks`."""
    found = []
    for line in text.splitlines():
        if line.startswith("|") and not re.fullmatch(r"\|[\s|:-]*", line):
            found += [p.strip().strip("`") for p in _first_cell(line).split(",")]
        found += re.findall(r"`([^`]+\.[A-Za-z0-9]{2,4})`", line)
    return [p for p in found if p and p.lower() not in ("file", "file(s)")]


def is_credited(rel: str, patterns: list) -> bool:
    name = rel.rsplit("/", 1)[-1]
    for p in patterns:
        # a bare name in a list ("pastor-cut.mov, pastor-cut.wav") matches by file name
        if fnmatch.fnmatch(rel, p) or ("/" not in p and fnmatch.fnmatch(name, p)):
            return True
    return False


def referenced_media(plan_path) -> list:
    """Shots, music, SFX and the clips, photos and logos inside graphics."""
    plan = load_plan(plan_path, check_files=False)
    files = [s.clip for s in plan.shots] + [m.file for m in plan.music] + [s.file for s in plan.sfx]
    for g in plan.graphics:
        if isinstance(g.get("photo"), dict):
            files.append(g["photo"].get("clip"))
        if isinstance(g.get("logo"), dict):
            files.append(g["logo"].get("file"))
        for key in ("photos", "panels", "items"):
            files += [x.get("clip") for x in g.get(key) or [] if isinstance(x, dict)]
    return list(dict.fromkeys(Path(f) for f in files if f))


def check(root, plan_path=None) -> dict:
    root = Path(root)
    plan_path = Path(plan_path) if plan_path else root / "plan" / "edit.json"
    path = root / CREDITS
    patterns = credited_patterns(path.read_text(encoding="utf-8")) if path.exists() else []
    media = [_rel(f, root) for f in referenced_media(plan_path)]
    return {"credits": str(path), "exists": path.exists(), "referenced": len(media),
            "missing": [m for m in media if not is_credited(m, patterns)]}
