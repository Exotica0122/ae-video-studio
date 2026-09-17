"""Final renders with aerender (After Effects' command-line renderer), never a scripted UI render."""
import subprocess
from pathlib import Path


class RenderError(RuntimeError):
    pass


def find_aerender(apps: Path = Path("/Applications")) -> Path:
    found = sorted(Path(apps).glob("Adobe After Effects */aerender"), reverse=True)
    if not found:
        raise RenderError(f"aerender not found under {apps}/Adobe After Effects */")
    return found[0]


def aerender_cmd(aerender, project, comp, output, rs="Best Settings", om="High Quality", mem=(50, 70)) -> list:
    return [str(aerender), "-project", str(project), "-comp", comp, "-RStemplate", rs, "-OMtemplate", om,
            "-output", str(output), "-mem_usage", str(mem[0]), str(mem[1]), "-v", "ERRORS_AND_PROGRESS"]


def ae_ui_running() -> bool:
    return subprocess.run(["pgrep", "-f", "MacOS/After Effects"], capture_output=True).returncode == 0


def render(project, comp, output, rs="Best Settings", om="High Quality", allow_running_ae=False, aerender=None) -> Path:
    project, output = Path(project).resolve(), Path(output).resolve()
    if not project.exists():
        raise RenderError(f"project not found: {project}")
    if not allow_running_ae and ae_ui_running():
        raise RenderError("After Effects is open. Save the project and quit After Effects first: aerender runs its own copy, "
                          "and a UI render can freeze. Use --allow-running-ae to override.")
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_name(output.name + ".log")
    cmd = aerender_cmd(aerender or find_aerender(), project, comp, output, rs, om)
    with open(log, "w", encoding="utf-8") as fh:
        result = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    if result.returncode != 0 or not output.exists():
        raise RenderError(f"aerender failed (exit {result.returncode}); see {log}")
    return output
