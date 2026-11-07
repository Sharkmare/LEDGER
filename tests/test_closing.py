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
from ledger import store
from test_ledger import LiveServerCase, fresh_connection


class DoneNeedsEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()
        self.ticket = store.create_ticket(self.connection, "APP", "work")

    def test_done_without_any_comment_is_refused(self):
        with self.assertRaises(store.LedgerError) as raised:
            store.update_ticket(self.connection, self.ticket["key"], {"status": "done"})
        self.assertIn("comment", str(raised.exception))
        self.assertEqual(store.get_ticket(self.connection, self.ticket["key"])["status"], "backlog")

    def test_a_blank_comment_does_not_count(self):
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, self.ticket["key"], {"status": "done", "comment": "   "})

    def test_an_existing_comment_is_enough(self):
        store.add_comment(self.connection, self.ticket["key"], "ann", "tested")
        self.assertEqual(store.update_ticket(self.connection, self.ticket["key"], {"status": "done"})["status"], "done")

    def test_a_comment_in_the_same_call_is_added(self):
        closed = store.update_ticket(self.connection, self.ticket["key"], {"status": "done", "comment": "12 tests pass"}, actor="ann")
        self.assertEqual([(c["author"], c["body"]) for c in closed["comments"]], [("ann", "12 tests pass")])
        self.assertEqual(closed["status"], "done")

    def test_cancelling_and_creating_done_need_no_comment(self):
        self.assertEqual(store.update_ticket(self.connection, self.ticket["key"], {"status": "cancelled"})["status"], "cancelled")
        self.assertEqual(store.create_ticket(self.connection, "APP", "born done", status="done")["status"], "done")

    def test_comment_alone_on_other_changes_is_not_stored(self):
        changed = store.update_ticket(self.connection, self.ticket["key"], {"priority": "high", "comment": "ignored"})
        self.assertEqual(changed["comments"], [])

    def test_comment_must_be_text(self):
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, self.ticket["key"], {"status": "done", "comment": 5})


class BlockersStopDoneTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()
        self.target = store.create_ticket(self.connection, "APP", "target")
        self.blocker = store.create_ticket(self.connection, "APP", "blocker")
        store.add_link(self.connection, self.blocker["key"], self.target["key"], "blocks")

    def close_target(self):
        return store.update_ticket(self.connection, self.target["key"], {"status": "done", "comment": "ok"})

    def test_an_open_blocker_refuses_done_and_is_named(self):
        with self.assertRaises(store.LedgerError) as raised:
            self.close_target()
        self.assertIn(self.blocker["key"], str(raised.exception))
        self.assertEqual(store.get_ticket(self.connection, self.target["key"])["comments"], [])

    def test_every_open_blocker_is_listed(self):
        second = store.create_ticket(self.connection, "APP", "second blocker")
        store.add_link(self.connection, second["key"], self.target["key"], "blocks")
        with self.assertRaises(store.LedgerError) as raised:
            self.close_target()
        self.assertIn(f"{self.blocker['key']}, {second['key']}", str(raised.exception))

    def test_done_and_cancelled_blockers_do_not_block(self):
        second = store.create_ticket(self.connection, "APP", "second blocker")
        store.add_link(self.connection, second["key"], self.target["key"], "blocks")
        store.update_ticket(self.connection, self.blocker["key"], {"status": "done", "comment": "ok"})
        store.update_ticket(self.connection, second["key"], {"status": "cancelled"})
        self.assertEqual(self.close_target()["status"], "done")

    def test_a_ticket_that_only_blocks_others_can_close(self):
        self.assertEqual(store.update_ticket(self.connection, self.blocker["key"], {"status": "done", "comment": "ok"})["status"], "done")

    def test_relates_links_do_not_block(self):
        other = store.create_ticket(self.connection, "APP", "other")
        store.add_link(self.connection, other["key"], self.target["key"], "relates")
        store.update_ticket(self.connection, self.blocker["key"], {"status": "cancelled"})
        self.assertEqual(self.close_target()["status"], "done")

    def test_cancelling_a_blocked_ticket_is_allowed(self):
        self.assertEqual(store.update_ticket(self.connection, self.target["key"], {"status": "cancelled"})["status"], "cancelled")


class DoneOverHttpTests(LiveServerCase):
    def patch(self, key, payload):
        request = urllib.request.Request(self.base + f"/api/tickets/{key}", data=json.dumps(payload).encode(), method="PATCH",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "closer", *arguments])
        return buffer.getvalue()

    def test_patch_refuses_then_accepts_with_a_comment(self):
        self.cli("new-project", "CLS", "Closing")
        self.cli("add", "CLS", "one")
        status, body = self.patch("CLS-1", {"status": "done"})
        self.assertEqual(status, 400)
        self.assertIn("comment", body["error"])
        status, body = self.patch("CLS-1", {"status": "done", "comment": "3 of 3 pass"})
        self.assertEqual((status, body["status"], body["comments"][0]["body"]), (200, "done", "3 of 3 pass"))

    def test_cli_done_prints_the_refusal_and_accepts_a_comment(self):
        self.cli("new-project", "CLD", "Closing CLI")
        self.cli("add", "CLD", "one")
        with self.assertRaises(SystemExit) as raised:
            self.cli("done", "CLD-1")
        self.assertIn("comment", str(raised.exception))
        self.cli("done", "CLD-1", "--comment", "shipped")
        self.assertEqual(json.loads(self.cli("--json", "show", "CLD-1"))["status"], "done")


if __name__ == "__main__":
    unittest.main()
