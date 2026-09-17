import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aestudio.bridge import Bridge, BridgeBusy, BridgeError, BridgeTimeout


def fake_panel(root: Path, result, status="completed", delay=0.2):
    """Mimic the MCP Bridge Auto panel: pick up a pending runJsx command and write a result."""
    def work():
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                cmd = json.loads((root / "ae_command.json").read_text())
            except (OSError, ValueError):
                time.sleep(0.02)
                continue
            if cmd.get("status") == "pending":
                assert Path(cmd["args"]["file"]).parent == root / "jsx"
                cmd["status"] = "running"
                (root / "ae_command.json").write_text(json.dumps(cmd))
                time.sleep(delay)
                panel_status = "error" if status == "error" else "success"
                (root / "ae_mcp_result.json").write_text(json.dumps({"status": panel_status, "jobId": cmd["args"]["jobId"], "result": result}))
                cmd["status"] = status
                (root / "ae_command.json").write_text(json.dumps(cmd))
                return
            time.sleep(0.02)
    t = threading.Thread(target=work, daemon=True)
    t.start()
    return t


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bridge = Bridge(self.root, poll=0.02)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_returns_result_and_writes_job_file(self):
        fake_panel(self.root, {"ok": True, "layers": 3})
        self.assertEqual(self.bridge.run("1+1", timeout=3), {"ok": True, "layers": 3})
        cmd = json.loads((self.root / "ae_command.json").read_text())
        self.assertEqual(cmd["command"], "runJsx")
        self.assertEqual(Path(cmd["args"]["file"]).read_text(), "1+1")

    def test_busy_panel_is_refused(self):
        (self.root / "ae_command.json").write_text(json.dumps({"status": "running", "args": {"jobId": "x"}}))
        with self.assertRaises(BridgeBusy):
            self.bridge.submit("1")

    def test_panel_error_raises(self):
        fake_panel(self.root, None, status="error")
        with self.assertRaises(BridgeError):
            self.bridge.run("bad", timeout=3)

    def test_timeout(self):
        with self.assertRaisesRegex(BridgeTimeout, "still running"):
            self.bridge.run("slow", timeout=0.2)

    def test_replaced_command(self):
        job = self.bridge.submit("1")
        (self.root / "ae_command.json").write_text(json.dumps({"status": "pending", "args": {"jobId": "other"}}))
        with self.assertRaisesRegex(BridgeError, "replaced"):
            self.bridge.wait(job, timeout=1)


if __name__ == "__main__":
    unittest.main()
