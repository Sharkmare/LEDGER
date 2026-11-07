import sqlite3
import unittest

from ledger import bulk, people, store
from tests.test_ledger import LiveServerCase
import ledger_cli


def fresh():
    connection = store.connect(":memory:")
    store.create_project(connection, "BLK", "Bulk")
    keys = [store.create_ticket(connection, "BLK", f"t{n}")["key"] for n in range(5)]
    return connection, keys


class BulkUpdateTests(unittest.TestCase):
    def test_changes_apply_to_every_key(self):
        connection, keys = fresh()
        result = bulk.update(connection, keys[:3], {"priority": "high"}, "tester")
        self.assertEqual((result["updated"], result["failed"], result["unchanged"]), (keys[:3], [], []))
        self.assertEqual([store.get_ticket(connection, k)["priority"] for k in keys], ["high"] * 3 + ["medium"] * 2)

    def test_events_record_the_actor(self):
        connection, keys = fresh()
        bulk.update(connection, keys[:1], {"status": "in_review"}, "ann")
        self.assertIn("ann", [e["actor"] for e in store.ticket_events(connection, keys[0])])

    def test_a_failing_ticket_does_not_stop_the_rest(self):
        connection, keys = fresh()
        result = bulk.update(connection, [keys[0], "BLK-99", keys[1]], {"status": "in_review"}, "t")
        self.assertEqual(result["updated"], [keys[0], keys[1]])
        self.assertEqual([f["key"] for f in result["failed"]], ["BLK-99"])
        self.assertTrue(result["failed"][0]["error"])

    def test_an_invalid_value_fails_each_ticket_without_raising(self):
        connection, keys = fresh()
        result = bulk.update(connection, keys[:2], {"status": "nonsense"}, "t")
        self.assertEqual((result["updated"], len(result["failed"])), ([], 2))

    def test_tickets_already_at_the_value_are_unchanged(self):
        connection, keys = fresh()
        bulk.update(connection, keys[:1], {"priority": "high"}, "t")
        result = bulk.update(connection, keys[:2], {"priority": "high"}, "t")
        self.assertEqual((result["updated"], result["unchanged"]), ([keys[1]], [keys[0]]))

    def test_duplicates_and_case_are_deduped(self):
        connection, keys = fresh()
        result = bulk.update(connection, [keys[0], keys[0].lower(), keys[0]], {"priority": "low"}, "t")
        self.assertEqual(result["updated"], [keys[0]])
        self.assertEqual([e["field"] for e in store.ticket_events(connection, keys[0])].count("priority"), 1)

    def test_refusals(self):
        connection, keys = fresh()
        for bad_keys, changes, comment in (([], {"priority": "low"}, ""), (["BLK-%d" % n for n in range(1, 202)], {"priority": "low"}, ""),
                                           (keys, {}, ""), (keys, None, "  "), ("BLK-1", {"priority": "low"}, ""), ([5], {"priority": "low"}, ""),
                                           (keys, {"nonsense": 1}, ""), (keys, ["a"], "")):
            with self.assertRaises(store.LedgerError, msg=repr((bad_keys, changes, comment))):
                bulk.update(connection, bad_keys, changes, "t", comment)

    def test_exactly_two_hundred_keys_are_allowed(self):
        connection, keys = fresh()
        result = bulk.update(connection, ["BLK-%d" % n for n in range(1, 201)], {"priority": "low"}, "t")
        self.assertEqual(len(result["failed"]) + len(result["updated"]), 200)

    def test_comment_lands_on_every_touched_ticket_including_unchanged(self):
        connection, keys = fresh()
        bulk.update(connection, keys[:1], {"priority": "high"}, "t")
        result = bulk.update(connection, keys[:2], {"priority": "high"}, "t", "why not")
        self.assertEqual(result["unchanged"], [keys[0]])
        for key in keys[:2]:
            self.assertEqual([c["body"] for c in store.get_ticket(connection, key)["comments"]], ["why not"])
        self.assertEqual(store.get_ticket(connection, keys[2])["comments"], [])

    def test_comment_alone_is_allowed_and_failed_tickets_get_no_comment(self):
        connection, keys = fresh()
        result = bulk.update(connection, [keys[0]], {}, "t", "note")
        self.assertEqual(result["unchanged"], [keys[0]])
        failing = bulk.update(connection, [keys[1]], {"status": "nonsense"}, "t", "note")
        self.assertEqual(store.get_ticket(connection, keys[1])["comments"], [])
        self.assertEqual(len(failing["failed"]), 1)

    def test_label_additions_and_removals_are_per_ticket(self):
        connection, keys = fresh()
        store.update_ticket(connection, keys[0], {"labels": ["a", "b"]})
        store.update_ticket(connection, keys[1], {"labels": ["b"]})
        bulk.update(connection, keys[:2], {"add_labels": ["c"], "remove_labels": ["b"]}, "t")
        self.assertEqual([store.get_ticket(connection, k)["labels"] for k in keys[:2]], [["a", "c"], ["c"]])

    def test_non_label_fields_pass_through(self):
        connection, keys = fresh()
        people.add(connection, "ann")
        bulk.update(connection, keys[1:3], {"parent_key": keys[0], "assignee": "ann"}, "t")
        child = store.get_ticket(connection, keys[1])
        self.assertEqual((child["parent_key"], child["assignee"]), (keys[0], "ann"))


class BulkApiTests(LiveServerCase):
    def test_route_returns_the_result(self):
        ledger_cli.call(self.base, "POST", "/api/projects", "t", {"key": "BAPI", "name": "Bulk api"})
        keys = [ledger_cli.call(self.base, "POST", "/api/tickets", "t", {"project": "BAPI", "title": f"t{n}"})["key"] for n in range(3)]
        result = ledger_cli.call(self.base, "POST", "/api/tickets/bulk", "ann",
                                 {"keys": keys + ["BAPI-99"], "changes": {"status": "done"}, "comment": "closing"})
        self.assertEqual((result["updated"], [f["key"] for f in result["failed"]], result["unchanged"]), (keys, ["BAPI-99"], []))
        shown = ledger_cli.call(self.base, "GET", f"/api/tickets/{keys[0]}", "t")
        self.assertEqual((shown["status"], shown["comments"][0]["body"], shown["comments"][0]["author"]), ("done", "closing", "ann"))

    def test_route_refuses_bad_requests_with_400(self):
        for payload in ({"keys": [], "changes": {"status": "done"}}, {"keys": ["BAPI-1"]}, {"keys": ["BAPI-1"], "changes": {"x": 1}}):
            with self.assertRaises(SystemExit):
                ledger_cli.call(self.base, "POST", "/api/tickets/bulk", "t", payload)


if __name__ == "__main__":
    unittest.main()
