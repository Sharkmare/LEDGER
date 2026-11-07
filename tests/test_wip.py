import contextlib
import io
import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from ledger import store, wip
from test_ledger import LiveServerCase, fresh_connection


class WipStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()

    def test_no_limits_by_default_and_counts_cover_every_status(self):
        store.create_ticket(self.connection, "APP", "a", status="blocked")
        overview = wip.overview(self.connection)
        self.assertEqual(overview["limits"], {})
        self.assertEqual(overview["over"], [])
        self.assertEqual(set(overview["counts"]), set(store.STATUSES))
        self.assertEqual(overview["counts"]["blocked"], 1)

    def test_a_limit_is_stored_and_reported_over_when_exceeded(self):
        wip.set_limit(self.connection, "in_progress", 1)
        store.create_ticket(self.connection, "APP", "a", status="in_progress")
        self.assertEqual(wip.overview(self.connection)["over"], [])
        store.create_ticket(self.connection, "APP", "b", status="in_progress")
        overview = wip.overview(self.connection)
        self.assertEqual((overview["limits"], overview["over"]), ({"in_progress": 1}, ["in_progress"]))

    def test_moves_are_never_refused_by_a_limit(self):
        wip.set_limit(self.connection, "in_review", 1)
        for title in ("a", "b", "c"):
            ticket = store.create_ticket(self.connection, "APP", title)
            self.assertEqual(store.update_ticket(self.connection, ticket["key"], {"status": "in_review"})["status"], "in_review")

    def test_zero_or_null_clears_and_a_new_value_replaces(self):
        wip.set_limit(self.connection, "blocked", 4)
        wip.set_limit(self.connection, "blocked", 2)
        self.assertEqual(wip.overview(self.connection)["limits"], {"blocked": 2})
        self.assertEqual(wip.set_limit(self.connection, "blocked", 0)["limits"], {})
        wip.set_limit(self.connection, "blocked", 2)
        self.assertEqual(wip.set_limit(self.connection, "blocked", None)["limits"], {})

    def test_other_statuses_and_bad_limits_are_refused(self):
        for status in ("todo", "done", "nonsense"):
            with self.assertRaises(store.LedgerError):
                wip.set_limit(self.connection, status, 3)
        for bad in (-1, "x", 1.5, True, 10 ** 6):
            with self.assertRaises(store.LedgerError, msg=repr(bad)):
                wip.set_limit(self.connection, "blocked", bad)


class WipHttpTests(LiveServerCase):
    def put(self, status, payload):
        request = urllib.request.Request(self.base + f"/api/wip/{status}", data=json.dumps(payload).encode(), method="PUT",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "wip-test", *arguments])
        return buffer.getvalue()

    def test_put_get_and_refusal(self):
        status, body = self.put("in_progress", {"limit": 2})
        self.assertEqual((status, body["limits"]), (200, {"in_progress": 2}))
        with urllib.request.urlopen(self.base + "/api/wip") as response:
            self.assertEqual(json.loads(response.read())["limits"], {"in_progress": 2})
        self.assertEqual(self.put("todo", {"limit": 2})[0], 400)
        self.assertEqual(self.put("in_progress", {"limit": 0})[1]["limits"], {})

    def test_cli_sets_and_shows_limits_with_an_over_flag(self):
        self.cli("new-project", "WIP", "Wip")
        for title in ("a", "b"):
            self.cli("add", "WIP", title, "--status", "blocked")
        self.assertIn("no limit", self.cli("wip"))
        self.cli("wip-set", "blocked", "1")
        shown = self.cli("wip")
        self.assertIn("blocked", shown)
        self.assertIn("2 / 1  OVER", shown)
        self.cli("wip-set", "blocked", "0")
        self.assertNotIn("OVER", self.cli("wip"))


if __name__ == "__main__":
    unittest.main()
