"""Client for the After Effects MCP Bridge Auto panel (runJsx command, see bridge/runJsx.patch)."""
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("AESTUDIO_BRIDGE_DIR", "~/.ae-mcp-bridge")).expanduser()


class BridgeError(RuntimeError):
    pass


class BridgeBusy(BridgeError):
    pass


class BridgeTimeout(BridgeError):
    pass


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Bridge:
    def __init__(self, root: Path = DEFAULT_ROOT, poll: float = 0.25):
        self.root = Path(root)
        self.poll = poll

    @property
    def command_file(self) -> Path:
        return self.root / "ae_command.json"

    @property
    def result_file(self) -> Path:
        return self.root / "ae_mcp_result.json"

    def _command(self):
        try:
            return json.loads(self.command_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def status(self):
        cmd = self._command()
        return cmd.get("status") if cmd else None

    def submit(self, code: str) -> str:
        if self.status() in ("pending", "running"):
            raise BridgeBusy("After Effects is still working on another bridge job; wait for it to finish (never queue jobs in parallel).")
        jsx_dir = self.root / "jsx"
        jsx_dir.mkdir(parents=True, exist_ok=True)
        job_id = f"{int(time.time() * 1000)}-{secrets.token_hex(3)}"
        script = jsx_dir / f"{job_id}.jsx"
        script.write_text(code, encoding="utf-8")
        now = datetime.now(timezone.utc).isoformat()
        _write_atomic(self.result_file, {"status": "waiting", "message": "Waiting for new result from After Effects...", "timestamp": now})
        _write_atomic(self.command_file, {"command": "runJsx", "args": {"file": str(script), "jobId": job_id},
                                          "timestamp": now, "status": "pending"})
        return job_id

    def wait(self, job_id: str, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            cmd = self._command()
            if cmd:
                if cmd.get("args", {}).get("jobId") != job_id:
                    raise BridgeError(f"bridge command was replaced by another job before {job_id} finished")
                if cmd.get("status") in ("completed", "error"):
                    try:
                        res = json.loads(self.result_file.read_text(encoding="utf-8"))
                    except (OSError, ValueError) as e:
                        raise BridgeError(f"unreadable bridge result: {e}") from e
                    if cmd["status"] == "error" or res.get("status") == "error":
                        raise BridgeError(res.get("message") or json.dumps(res, ensure_ascii=False))
                    return res.get("result")
            time.sleep(self.poll)
        raise BridgeTimeout(f"job {job_id} is still running after {timeout}s; After Effects keeps working. "
                            "Wait until ae_command.json status is 'completed' before submitting anything else.")

    def run(self, code: str, timeout: float = 600):
        return self.wait(self.submit(code), timeout)
