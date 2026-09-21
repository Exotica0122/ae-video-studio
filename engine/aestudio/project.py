"""The per-video project folder: create it, see which gates are done, record decisions.

Everything the plugin generates is reproducible from plan/ and analysis/, so this module
only ever creates folders and appends to the decision log. It never overwrites a file a
gate has already produced — losing an approved design to a re-run would be unforgivable.
"""
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FOLDERS = ("plan", "analysis", "analysis/transcripts", "analysis/frames", "analysis/sheets",
           "preview", "build", "exports", "qa")

DECISIONS = "plan/decisions.md"

# gate number, label, and the artifact that proves it happened (see docs/design.md section 3)
GATES = ((0, "brief", "plan/brief.md"),
         (1, "story", "plan/story.md"),
         (2, "design", "plan/design.json"),
         (3, "grade", "plan/grade.json"),
         (4, "test clip", "plan/edit.json"),
         (5, "key stills", None),
         (6, "review render", None),
         (7, "master", None))


class ProjectError(RuntimeError):
    pass


@dataclass
class Gate:
    number: int
    label: str
    artifact: str
    done: bool
    recorded: bool = False   # a decision is in the log, whether or not the artifact exists

    @property
    def state(self) -> str:
        """done = downstream can read it; recorded = decided but the artifact is not written yet."""
        if self.done:
            return "done"
        return "recorded" if self.recorded else "todo"


def init_project(root) -> list:
    """Create the layout. Idempotent: existing folders and files are left exactly as they are."""
    root = Path(root).expanduser()
    if root.exists() and not root.is_dir():
        raise ProjectError(f"{root} exists and is not a folder")
    created = []
    for name in FOLDERS:
        path = root / name
        if not path.exists():
            path.mkdir(parents=True)
            created.append(name)
    log = root / DECISIONS
    if not log.exists():
        log.write_text(f"# Decisions\n\nProject: {root.name}\nStarted: {date.today().isoformat()}\n\n"
                       "Every gate's decision is appended here, newest last.\n", encoding="utf-8")
        created.append(DECISIONS)
    return created


def gates(root) -> list:
    """Which gates have left evidence on disk. Gates 5-7 have no single artifact, so they are
    read from the decision log instead of guessed from files in exports/."""
    root = Path(root).expanduser()
    recorded = _recorded_gates(root)
    out = []
    for number, label, artifact in GATES:
        logged = number in recorded
        done = (root / artifact).exists() if artifact else logged
        out.append(Gate(number, label, artifact or f"{DECISIONS} entry", done, logged))
    return out


def next_gate(root):
    """The first gate without evidence — where the director should pick the work up."""
    for gate in gates(root):
        if not gate.done:
            return gate
    return None


def _recorded_gates(root) -> set:
    try:
        text = (root / DECISIONS).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {int(n) for n in re.findall(r"^## Gate (\d+)", text, re.MULTILINE)}


def record_decision(root, gate: int, what: str, detail: str = "", today=None) -> Path:
    """Append one decision. Appending (never rewriting) keeps the history of a changed mind."""
    root = Path(root).expanduser()
    log = root / DECISIONS
    if not log.exists():
        raise ProjectError(f"{log} does not exist — run `init` on this project first")
    if not any(g == gate for g, _, _ in GATES):
        raise ProjectError(f"gate {gate} is not one of {[g for g, _, _ in GATES]}")
    if not what.strip():
        raise ProjectError("a decision needs a description of what was decided")
    label = next(l for g, l, _ in GATES if g == gate)
    stamp = (today or date.today()).isoformat()
    entry = f"\n## Gate {gate} — {label} ({stamp})\n\n{what.strip()}\n"
    if detail.strip():
        entry += f"\n{detail.strip()}\n"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return log
