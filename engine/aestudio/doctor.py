"""Environment checks with fix instructions: is this machine able to build a video?

Nothing here touches After Effects unless the caller asks for a ping. The bridge takes one
job at a time, so a diagnostic that queued a job could stall whatever the user is rendering.
"""
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bridge import DEFAULT_ROOT, Bridge, BridgeError
from .fonts import installed_files, is_installed, load_catalogue

APPLICATIONS = Path("/Applications")
MIN_PYTHON = (3, 10)
STALE_RESULT_DAYS = 14


class DoctorError(RuntimeError):
    pass


@dataclass
class Check:
    name: str
    status: str          # "ok" | "warn" | "fail"
    detail: str
    fix: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class Report:
    checks: list = field(default_factory=list)

    @property
    def failures(self) -> list:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warnings(self) -> list:
        return [c for c in self.checks if c.status == "warn"]

    def as_dict(self) -> dict:
        return {"checks": [{"name": c.name, "status": c.status, "detail": c.detail, "fix": c.fix}
                           for c in self.checks],
                "failed": len(self.failures), "warned": len(self.warnings)}


def check_python(version=None) -> Check:
    v = tuple(version or sys.version_info[:2])
    shown = ".".join(str(n) for n in v)
    if v >= MIN_PYTHON:
        return Check("python", "ok", f"{shown}")
    return Check("python", "fail", f"{shown} is too old (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)",
                 "Run the engine with a newer interpreter, e.g. `brew install python@3.13`. "
                 "Note /usr/bin/python3 on macOS is 3.9 and cannot import this engine.")


def check_tool(name: str, why: str, fix: str, required=True, which=shutil.which) -> Check:
    path = which(name)
    if path:
        return Check(name, "ok", path)
    return Check(name, "fail" if required else "warn", f"not found — needed for {why}", fix)


def check_ffmpeg(which=shutil.which) -> list:
    fix = "brew install ffmpeg"
    return [check_tool("ffmpeg", "frames, contact sheets and share copies", fix, which=which),
            check_tool("ffprobe", "probing clips and audio", fix, which=which)]


def check_whisper(command=None, which=shutil.which) -> Check:
    """Whisper is optional: only transcripts (and therefore synced captions) need it."""
    cmd = command if command is not None else os.environ.get("AESTUDIO_WHISPER_CMD", "uvx mlx-whisper")
    head = cmd.split()[0] if cmd.strip() else ""
    if head and which(head):
        return Check("whisper", "ok", cmd)
    return Check("whisper", "warn", f"`{head or cmd}` not found — needed for word-timed captions",
                 "Install uv (`brew install uv`) for the default `uvx mlx-whisper`, or set "
                 "AESTUDIO_WHISPER_CMD to any Whisper build that emits word timestamps. "
                 "You can also transcribe elsewhere and use `import-transcript`.")


def find_after_effects(apps=APPLICATIONS) -> list:
    try:
        found = [p for p in Path(apps).iterdir() if p.name.startswith("Adobe After Effects")]
    except OSError:
        return []
    return sorted(found, key=lambda p: p.name)


def _version_of(app: Path):
    m = re.search(r"(\d{4})", app.name)
    return int(m.group(1)) if m else None


def check_after_effects(apps=APPLICATIONS, running=None) -> Check:
    found = find_after_effects(apps)
    if not found:
        return Check("after-effects", "fail", "no Adobe After Effects install found in /Applications",
                     "Install After Effects 2025 or newer; the engine builds and renders inside it.")
    newest = found[-1]
    year = _version_of(newest)
    live = _is_running() if running is None else running
    state = "running" if live else "not running"
    if year is not None and year < 2025:
        return Check("after-effects", "warn", f"{newest.name} ({state}) is older than 2025",
                     "The engine targets After Effects 2025+; older builds may not have the effects it uses.")
    return Check("after-effects", "ok", f"{newest.name} ({state})")


def _is_running() -> bool:
    try:
        out = subprocess.run(["pgrep", "-f", "Adobe After Effects"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out.stdout.strip())


BRIDGE_SRC = Path(os.environ.get("AESTUDIO_BRIDGE_SRC", "~/.ae-video-studio/after-effects-mcp")).expanduser()


def check_bridge_server(src=None, panel_active: bool = False) -> Check:
    """The MCP server this plugin talks to, built by bridge/install.sh.

    A build somewhere this check cannot see is not a failure when the panel has plainly been
    answering: telling someone to reinstall a bridge that works is worse than saying nothing.
    """
    src = Path(src) if src is not None else BRIDGE_SRC
    if (src / "build" / "index.js").exists():
        return Check("bridge-server", "ok", str(src))
    if panel_active:
        return Check("bridge-server", "warn",
                     f"no build at {src}, but the panel has been answering — it is installed elsewhere",
                     "Set AESTUDIO_BRIDGE_SRC to that folder so this check can find it. Nothing is "
                     "broken; only this check is blind.")
    if src.exists():
        return Check("bridge-server", "fail", f"{src} exists but has no build/index.js",
                     "Run `npm install && npm run build` in that folder, or delete it and re-run "
                     "bridge/install.sh.")
    return Check("bridge-server", "fail", f"the after-effects MCP server is not built at {src}",
                 "Run bridge/install.sh (clones upstream at the recorded commit, applies "
                 "runJsx.patch and builds), or set AESTUDIO_BRIDGE_SRC if it lives elsewhere.")


def panel_has_answered(root=None, now=None, within_days: float = STALE_RESULT_DAYS) -> bool:
    """Has the After Effects panel produced a result recently enough to count as alive?"""
    root = Path(root) if root is not None else DEFAULT_ROOT
    result = root / "ae_mcp_result.json"
    try:
        age_days = ((now or time.time()) - result.stat().st_mtime) / 86400
    except OSError:
        return False
    return age_days <= within_days


def check_bridge(root=None, now=None) -> list:
    root = Path(root) if root is not None else DEFAULT_ROOT
    if not root.exists():
        return [Check("bridge", "fail", f"{root} does not exist",
                      "Open the MCP Bridge Auto panel in After Effects (Window > mcp-bridge-auto.jsx) "
                      "and turn Auto-run on; it creates this folder on first run.")]
    bridge = Bridge(root)
    checks = []
    status = bridge.status()
    if status in ("pending", "running"):
        checks.append(Check("bridge", "warn", f"a job is {status} — After Effects is busy",
                            "Wait for it to finish. Never queue a second job; the panel runs one at a time."))
    else:
        checks.append(Check("bridge", "ok", f"idle at {root}" if status else f"ready at {root} (no job yet)"))
    result = root / "ae_mcp_result.json"
    if result.exists():
        age_days = ((now or time.time()) - result.stat().st_mtime) / 86400
        if age_days > STALE_RESULT_DAYS:
            checks.append(Check("bridge-panel", "warn",
                                f"last bridge result is {int(age_days)} days old",
                                "The panel may not be open. Check the MCP Bridge Auto panel is open with "
                                "Auto-run ticked, or run `doctor --ping` to prove it end to end."))
        else:
            checks.append(Check("bridge-panel", "ok", f"last result {age_days * 24:.1f}h ago"))
    return checks


def ping_bridge(root=None, timeout: float = 60) -> Check:
    """Prove the panel really executes scripts. Submits a trivial job, so it needs AE free."""
    bridge = Bridge(Path(root) if root is not None else DEFAULT_ROOT)
    script = 'JSON.stringify({ok: true, version: app.version});'
    try:
        result = bridge.run(script, timeout=timeout)
    except BridgeError as e:
        return Check("bridge-ping", "fail", str(e),
                     "Open the MCP Bridge Auto panel in After Effects and tick Auto-run, then try again.")
    return Check("bridge-ping", "ok", f"After Effects answered: {result}")


def check_fonts(catalogue=None, dirs=None, design=None) -> list:
    """Catalogue coverage, plus the fonts one design actually needs (the pre-build gate)."""
    kw = {"dirs": dirs} if dirs is not None else {}
    files = installed_files(**kw)
    entries = catalogue if catalogue is not None else load_catalogue()
    checks = []
    missing = sorted({f.family for f in entries if not is_installed(f, files=files)})
    if missing:
        checks.append(Check("fonts", "warn", f"{len(missing)} catalogue families not installed: {', '.join(missing)}",
                            "Only matters if a design picks one. `design-choose` re-checks and prints install notes."))
    else:
        checks.append(Check("fonts", "ok", f"all {len({f.family for f in entries})} catalogue families installed"))
    if design is not None:
        checks.append(_check_design_fonts(sorted(design), entries, files))
    return checks


def _check_design_fonts(wanted: list, entries: list, files: set) -> Check:
    """A design names PostScript names; the filesystem gives file stems, and the two differ
    (NanumSquareNeoTTF-bRg lives in NanumSquareNeo-bRg.ttf). Resolve through the catalogue,
    which records that mapping, and only guess for a font the catalogue has never heard of."""
    by_postscript = {ps.lower(): font for font in entries for ps in font.postscript.values()}
    absent, unknown = [], []
    for name in wanted:
        font = by_postscript.get(name.lower())
        if font is not None:
            if not is_installed(font, files=files):
                absent.append(name)
        elif name.lower() not in files:
            unknown.append(name)
    if absent or unknown:
        detail = []
        if absent:
            detail.append(f"not installed: {', '.join(absent)}")
        if unknown:
            detail.append(f"not in the catalogue and no matching font file: {', '.join(unknown)}")
        return Check("design-fonts", "fail", "the chosen design needs fonts that are missing — " + "; ".join(detail),
                     "Install them before building. After Effects silently substitutes a missing font, so the "
                     "render comes out looking wrong instead of failing.")
    return Check("design-fonts", "ok", f"all {len(wanted)} fonts of the chosen design are installed")


def run_checks(*, bridge_root=None, apps=APPLICATIONS, design=None, ping=False,
               which=shutil.which, catalogue=None, dirs=None) -> Report:
    checks = [check_python()]
    checks += check_ffmpeg(which=which)
    checks.append(check_whisper(which=which))
    checks.append(check_after_effects(apps=apps))
    checks.append(check_bridge_server(panel_active=panel_has_answered(bridge_root)))
    checks += check_bridge(root=bridge_root)
    checks += check_fonts(catalogue=catalogue, dirs=dirs, design=design)
    if ping:
        checks.append(ping_bridge(root=bridge_root))
    return Report(checks)


MARK = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}


def format_report(report: Report) -> str:
    lines = []
    for c in report.checks:
        lines.append(f"[{MARK[c.status]}] {c.name}: {c.detail}")
        if c.fix and c.status != "ok":
            lines.append(f"         → {c.fix}")
    if report.failures:
        lines.append(f"\n{len(report.failures)} check(s) failed; the engine cannot build a video until they pass.")
    elif report.warnings:
        lines.append(f"\nReady to build. {len(report.warnings)} warning(s) — fine unless the video needs that piece.")
    else:
        lines.append("\nEverything the engine needs is present.")
    return "\n".join(lines)
