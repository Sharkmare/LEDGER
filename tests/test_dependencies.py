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
from ledger import dependencies, store
from test_ledger import LiveServerCase, fresh_connection


def make(connection, title, **fields):
    return store.create_ticket(connection, "APP", title, **fields)["key"]


def blocks(connection, blocker, blocked):
    store.add_link(connection, blocker, blocked, "blocks")


class ForTicketTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()
        self.a, self.b, self.c, self.d = (make(self.connection, name) for name in "abcd")
        blocks(self.connection, self.a, self.b)
        blocks(self.connection, self.b, self.c)

    def test_chains_are_transitive_with_depth_in_both_directions(self):
        middle = dependencies.for_ticket(self.connection, self.b)
        self.assertEqual([(e["key"], e["depth"]) for e in middle["blocked_by"]], [(self.a, 1)])
        self.assertEqual([(e["key"], e["depth"]) for e in middle["blocks"]], [(self.c, 1)])
        last = dependencies.for_ticket(self.connection, self.c)
        self.assertEqual([(e["key"], e["depth"]) for e in last["blocked_by"]], [(self.b, 1), (self.a, 2)])
        first = dependencies.for_ticket(self.connection, self.a)
        self.assertEqual([(e["key"], e["depth"]) for e in first["blocks"]], [(self.b, 1), (self.c, 2)])

    def test_entries_carry_title_and_status(self):
        entry = dependencies.for_ticket(self.connection, self.b)["blocked_by"][0]
        self.assertEqual((entry["title"], entry["status"]), ("a", "backlog"))

    def test_open_blockers_counts_direct_open_blockers_only(self):
        blocks(self.connection, self.d, self.c)
        self.assertEqual(dependencies.for_ticket(self.connection, self.c)["open_blockers"], 2)
        store.update_ticket(self.connection, self.d, {"status": "cancelled"})
        self.assertEqual(dependencies.for_ticket(self.connection, self.c)["open_blockers"], 1)
        self.assertEqual(dependencies.for_ticket(self.connection, self.a)["open_blockers"], 0)

    def test_relates_links_are_ignored(self):
        store.add_link(self.connection, self.d, self.a, "relates")
        self.assertEqual(dependencies.for_ticket(self.connection, self.a)["blocked_by"], [])

    def test_a_cycle_terminates(self):
        blocks(self.connection, self.c, self.a)
        result = dependencies.for_ticket(self.connection, self.a)
        self.assertEqual(sorted(e["key"] for e in result["blocked_by"]), sorted([self.b, self.c]))
        self.assertEqual(sorted(e["key"] for e in result["blocks"]), sorted([self.b, self.c]))

    def test_unknown_ticket_is_not_found(self):
        with self.assertRaises(store.NotFound):
            dependencies.for_ticket(self.connection, "APP-99")


class CriticalPathTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()
        self.epic = make(self.connection, "epic", type="epic")

    def child(self, title, **fields):
        return make(self.connection, title, parent_key=self.epic, **fields)

    def test_the_longest_chain_wins(self):
        a, b, c, d = (self.child(name) for name in "abcd")
        blocks(self.connection, a, b)
        blocks(self.connection, b, c)
        blocks(self.connection, a, d)
        self.assertEqual(dependencies.critical_path(self.connection, self.epic), [a, b, c])

    def test_no_chain_gives_an_empty_path(self):
        self.child("a")
        self.child("b")
        self.assertEqual(dependencies.critical_path(self.connection, self.epic), [])
        self.assertEqual(dependencies.critical_path(self.connection, self.child("c")), [])

    def test_closed_tickets_break_the_chain(self):
        a, b, c = self.child("a"), self.child("b"), self.child("c")
        blocks(self.connection, a, b)
        blocks(self.connection, b, c)
        store.update_ticket(self.connection, b, {"status": "cancelled"})
        self.assertEqual(dependencies.critical_path(self.connection, self.epic), [])

    def test_nested_children_count_and_outside_tickets_do_not(self):
        story = self.child("story", type="story")
        inner = make(self.connection, "inner", parent_key=story)
        outside = make(self.connection, "outside")
        a = self.child("a")
        blocks(self.connection, a, inner)
        blocks(self.connection, inner, outside)
        self.assertEqual(dependencies.critical_path(self.connection, self.epic), [a, inner])

    def test_a_cycle_does_not_hang_and_still_gives_a_path(self):
        a, b, c = self.child("a"), self.child("b"), self.child("c")
        blocks(self.connection, a, b)
        blocks(self.connection, b, c)
        blocks(self.connection, c, a)
        path = dependencies.critical_path(self.connection, self.epic)
        self.assertEqual(len(path), 3)
        self.assertEqual(len(set(path)), 3)

    def test_a_diamond_ladder_is_fast(self):
        previous = [self.child("start")]
        for level in range(14):
            row = [self.child(f"l{level}x"), self.child(f"l{level}y")]
            for blocker in previous:
                for blocked in row:
                    blocks(self.connection, blocker, blocked)
            previous = row
        self.assertEqual(len(dependencies.critical_path(self.connection, self.epic)), 15)


class DependenciesHttpTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "deps-test", *arguments])
        return buffer.getvalue()

    def fetch(self, key):
        with urllib.request.urlopen(self.base + f"/api/tickets/{key}/dependencies") as response:
            return json.loads(response.read())

    def test_api_and_cli(self):
        self.cli("new-project", "DEP", "Deps")
        self.cli("add", "DEP", "epic", "--type", "epic")
        for title in ("one", "two", "three"):
            self.cli("add", "DEP", title, "--parent", "DEP-1")
        self.cli("link", "DEP-2", "DEP-3", "--kind", "blocks")
        self.cli("link", "DEP-3", "DEP-4", "--kind", "blocks")
        child = self.fetch("DEP-3")
        self.assertEqual((child["open_blockers"], [e["key"] for e in child["blocked_by"]], [e["key"] for e in child["blocks"]]),
                         (1, ["DEP-2"], ["DEP-4"]))
        self.assertNotIn("critical_path", child)
        self.assertEqual(self.fetch("DEP-1")["critical_path"], ["DEP-2", "DEP-3", "DEP-4"])
        shown = self.cli("deps", "DEP-3")
        self.assertIn("1 open blockers", shown)
        self.assertIn("blocked by", shown)
        self.assertIn("DEP-4", shown)
        self.assertIn("DEP-2 -> DEP-3 -> DEP-4", self.cli("deps", "DEP-1"))

    def test_unknown_ticket_is_a_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch("NOPE-1")
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
