"""Serve the design mockups on localhost and record which direction was clicked."""
import json
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHOICE_FILE = "choice.json"


class PreviewError(RuntimeError):
    pass


def read_choice(directory):
    path = Path(directory) / CHOICE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _known_ids(directory) -> set:
    try:
        drafts = json.loads((Path(directory) / "drafts.json").read_text(encoding="utf-8"))
        return {d.get("id") for d in drafts if isinstance(d, dict)}
    except (OSError, ValueError):
        return set()


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        self._root = Path(directory).resolve()
        super().__init__(*args, directory=str(self._root), **kwargs)

    def log_message(self, *args):
        pass                                    # keep the terminal clean

    def translate_path(self, path):
        candidate = Path(super().translate_path(path))
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self._root)
        except (OSError, ValueError):
            # escapes the served directory (e.g. via a symlink) — make it 404, no body leak
            return str(self._root / ".aestudio-preview-denied")
        return str(candidate)

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/choice":
            return self._json(200, read_choice(self._root) or {})
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/choose":
            return self._json(404, {"ok": False, "error": "unknown endpoint"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "body must be JSON"})
        if not isinstance(payload, dict):
            return self._json(400, {"ok": False, "error": "body must be a JSON object"})
        draft_id = payload.get("id")
        known = _known_ids(self._root)
        if not isinstance(draft_id, str) or not draft_id or (known and draft_id not in known):
            return self._json(400, {"ok": False, "error": f"unknown draft id {draft_id!r}"})
        choice = {"id": draft_id, "note": payload.get("note") or None,
                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (self._root / CHOICE_FILE).write_text(json.dumps(choice, ensure_ascii=False, indent=1), encoding="utf-8")
        return self._json(200, {"ok": True})


def serve(directory, port: int = 0, host: str = "127.0.0.1"):
    directory = Path(directory).resolve()
    if not (directory / "index.html").exists():
        raise PreviewError(f"no index.html in {directory} — render the mockups first")
    (directory / CHOICE_FILE).unlink(missing_ok=True)
    handler = partial(_Handler, directory=str(directory))
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        raise PreviewError(f"cannot serve on {host}:{port}: {e}") from e
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{server.server_address[1]}"


def wait_for_choice(server, directory, timeout: float = 1800.0, poll: float = 0.5):
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            choice = read_choice(directory)
            if choice:
                return choice
            time.sleep(poll)
        return None
    finally:
        server.shutdown()
        server.server_close()
