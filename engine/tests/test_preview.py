import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from aestudio import preview


def post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read()


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "index.html").write_text("<h1>designs</h1>", encoding="utf-8")
        (self.dir / "drafts.json").write_text(json.dumps([{"id": "paper-notebook-paperlogy"}]), encoding="utf-8")
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.tmp.cleanup()

    def test_serves_the_page_and_records_a_choice(self):
        self.server, url = preview.serve(self.dir)
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        status, body = get(url + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"designs", body)
        status, reply = post(url + "/choose", {"id": "paper-notebook-paperlogy", "note": "bigger type"})
        self.assertEqual((status, reply["ok"]), (200, True))
        choice = preview.read_choice(self.dir)
        self.assertEqual(choice["id"], "paper-notebook-paperlogy")
        self.assertEqual(choice["note"], "bigger type")
        self.assertIn("at", choice)
        status, reply = get(url + "/choice")
        self.assertEqual(json.loads(reply)["id"], "paper-notebook-paperlogy")

    def test_unknown_id_is_refused(self):
        self.server, url = preview.serve(self.dir)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(url + "/choose", {"id": "nope"})
        self.assertEqual(cm.exception.code, 400)
        self.assertIsNone(preview.read_choice(self.dir))

    def test_files_outside_the_directory_are_refused(self):
        self.server, url = preview.serve(self.dir)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            get(url + "/../../etc/hosts")
        self.assertIn(cm.exception.code, (400, 403, 404))

    def test_wait_for_choice_returns_the_choice_then_stops(self):
        server, url = preview.serve(self.dir)
        threading.Timer(0.2, lambda: post(url + "/choose", {"id": "paper-notebook-paperlogy"})).start()
        choice = preview.wait_for_choice(server, self.dir, timeout=5, poll=0.05)
        self.assertEqual(choice["id"], "paper-notebook-paperlogy")
        with self.assertRaises(urllib.error.URLError):
            get(url + "/")                      # the server is closed

    def test_wait_for_choice_times_out(self):
        server, _ = preview.serve(self.dir)
        self.assertIsNone(preview.wait_for_choice(server, self.dir, timeout=0.3, poll=0.05))


if __name__ == "__main__":
    unittest.main()
