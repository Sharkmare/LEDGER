import functools
import http.server
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from test_ledger import LiveServerCase

SPEC = {"openapi": "3.0.3", "info": {"title": "Slow", "version": "1"}, "paths": {"/x": {"get": {"summary": "x"}}}}
SLOW_SECONDS = 2.0


class SlowSpecHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(SLOW_SECONDS)
        body = json.dumps(SPEC).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return None


class SpecFetchWhileServingTests(LiveServerCase):
    def tool(self, title, openapi):
        return ledger_cli.call(self.base, "POST", "/api/kb/pages", "t", {"space": "TOOLS", "title": title, "meta": {"kind": "api", "openapi": openapi}})

    def test_a_tool_can_describe_the_server_it_runs_on(self):
        tool = self.tool("Self", {"source": "url", "url": f"{self.base}/api/openapi.json"})
        started = time.time()
        served = ledger_cli.call(self.base, "GET", f"/api/kb/pages/{tool['id']}/openapi", "t")
        self.assertLess(time.time() - started, 5)
        self.assertEqual(served["spec"]["info"]["title"], "LEDGER API")
        self.assertGreater(served["spec"]["paths"].__len__(), 50)

    def test_a_slow_description_does_not_block_other_requests(self):
        slow = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowSpecHandler)
        threading.Thread(target=slow.serve_forever, daemon=True).start()
        self.addCleanup(slow.server_close)
        self.addCleanup(slow.shutdown)
        tool = self.tool("Slow", {"source": "url", "url": f"http://127.0.0.1:{slow.server_address[1]}/spec.json"})
        outcome = {}

        def fetch():
            outcome["spec"] = ledger_cli.call(self.base, "GET", f"/api/kb/pages/{tool['id']}/openapi", "t")

        worker = threading.Thread(target=fetch)
        worker.start()
        time.sleep(0.3)
        started = time.time()
        with urllib.request.urlopen(self.base + "/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
        listed = ledger_cli.call(self.base, "GET", "/api/kb/spaces", "t")
        self.assertLess(time.time() - started, SLOW_SECONDS / 2)
        self.assertTrue(listed)
        worker.join(timeout=10)
        self.assertEqual(outcome["spec"]["spec"]["info"]["title"], "Slow")

    def test_a_file_that_appears_later_is_picked_up_on_refresh(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "later.json"
        tool = self.tool("Later", {"source": "file", "path": str(path)})
        with self.assertRaises(SystemExit):
            ledger_cli.call(self.base, "GET", f"/api/kb/pages/{tool['id']}/openapi", "t")
        path.write_text(json.dumps(SPEC), encoding="utf-8")
        served = ledger_cli.call(self.base, "GET", f"/api/kb/pages/{tool['id']}/openapi?refresh=1", "t")
        self.assertEqual(served["spec"]["info"]["title"], "Slow")


if __name__ == "__main__":
    unittest.main()
