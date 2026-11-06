import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from ledger import server, store
from test_ledger import LiveServerCase


def connection_with_one_of_each_type():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App work")
    for ticket_type in store.TICKET_TYPES:
        store.create_ticket(connection, "APP", f"a {ticket_type}", type=ticket_type)
    return connection


class ExcludeTypeStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = connection_with_one_of_each_type()
        self.addCleanup(self.connection.close)

    def types(self, **filters):
        return sorted(ticket["type"] for ticket in store.list_tickets(self.connection, **filters))

    def test_no_exclusion_lists_every_type(self):
        self.assertEqual(self.types(), sorted(store.TICKET_TYPES))
        self.assertEqual(self.types(exclude_types=""), sorted(store.TICKET_TYPES))
        self.assertEqual(self.types(exclude_types=None), sorted(store.TICKET_TYPES))

    def test_excluded_types_are_left_out_of_the_list_and_the_count(self):
        self.assertEqual(self.types(exclude_types="bug,chore"), sorted(set(store.TICKET_TYPES) - {"bug", "chore"}))
        self.assertEqual(store.count_tickets(self.connection, exclude_types="bug,chore"), len(store.TICKET_TYPES) - 2)

    def test_a_list_and_a_comma_string_mean_the_same(self):
        self.assertEqual(self.types(exclude_types=["bug", "epic"]), self.types(exclude_types="bug,epic"))

    def test_spacing_case_and_repeats_are_forgiven(self):
        self.assertEqual(self.types(exclude_types=" Bug , bug,,CHORE "), self.types(exclude_types="bug,chore"))

    def test_excluding_every_type_leaves_nothing(self):
        self.assertEqual(self.types(exclude_types=",".join(store.TICKET_TYPES)), [])

    def test_an_unknown_type_is_refused_with_the_valid_values(self):
        with self.assertRaises(store.LedgerError) as raised:
            self.types(exclude_types="bug,saga")
        self.assertIn("task", str(raised.exception))

    def test_other_filters_still_apply_alongside_an_exclusion(self):
        store.create_ticket(self.connection, "APP", "second bug", type="bug", priority="high")
        self.assertEqual(self.types(type="bug", exclude_types="chore"), ["bug", "bug"])
        self.assertEqual(self.types(priority="high", exclude_types="bug"), [])


class ExcludeTypeApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})
        for ticket_type in ("task", "bug", "chore"):
            self.client.post("/api/tickets", json={"project": "APP", "title": ticket_type, "type": ticket_type})

    def test_exclude_type_filters_the_list_and_the_total(self):
        response = self.client.get("/api/tickets?exclude_type=bug,chore")
        self.assertEqual([ticket["type"] for ticket in response.get_json()], ["task"])
        self.assertEqual(response.headers["X-Total-Count"], "1")

    def test_an_empty_exclude_type_changes_nothing(self):
        self.assertEqual(len(self.client.get("/api/tickets?exclude_type=").get_json()), 3)

    def test_an_unknown_type_is_a_400(self):
        self.assertEqual(self.client.get("/api/tickets?exclude_type=saga").status_code, 400)


class ExcludeTypeCliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def test_list_can_leave_types_out(self):
        self.cli("new-project", "EXT", "Exclude types")
        for ticket_type in ("task", "bug", "chore"):
            self.cli("add", "EXT", f"a {ticket_type}", "--type", ticket_type)
        shown = json.loads(self.cli("--json", "list", "--project", "EXT", "--exclude-type", "bug,chore"))
        self.assertEqual([ticket["type"] for ticket in shown], ["task"])
        self.assertEqual(len(json.loads(self.cli("--json", "list", "--project", "EXT"))), 3)


if __name__ == "__main__":
    unittest.main()
