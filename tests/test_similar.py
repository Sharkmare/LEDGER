import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ledger_cli
from ledger import similar, store
from test_ledger import LiveServerCase

FIND_BUDGET_MS = 100
BULK_TICKETS = 2000
SUBJECTS = ("auth", "ui", "api", "docs")


def seeded_connection():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App")
    store.create_project(connection, "OTH", "Other")
    return connection


def add(connection, project, title, status="backlog"):
    return store.create_ticket(connection, project, title, status=status)["key"]


class FindTests(unittest.TestCase):
    def setUp(self):
        self.connection = seeded_connection()

    def test_an_identical_title_scores_one(self):
        key = add(self.connection, "APP", "Login page crashes on submit")
        found = similar.find(self.connection, "APP", "Login page crashes on submit")
        self.assertEqual([(match["key"], match["score"]) for match in found], [(key, 1.0)])

    def test_the_result_carries_key_title_status_and_score(self):
        add(self.connection, "APP", "Login page crashes on submit", "in_progress")
        match = similar.find(self.connection, "APP", "login page crash on submit")[0]
        self.assertEqual(sorted(match), ["key", "score", "status", "title"])
        self.assertEqual((match["title"], match["status"]), ("Login page crashes on submit", "in_progress"))

    def test_word_order_and_punctuation_do_not_matter(self):
        add(self.connection, "APP", "Crash on submit: login page")
        found = similar.find(self.connection, "APP", "Login page, crash on submit!")
        self.assertEqual(found[0]["score"], 1.0)

    def test_unrelated_titles_are_dropped(self):
        add(self.connection, "APP", "Add dark mode to the settings page")
        self.assertEqual(similar.find(self.connection, "APP", "Fix database backup schedule"), [])

    def test_a_typo_still_matches_by_text_ratio(self):
        add(self.connection, "APP", "Dashboard exports broken")
        found = similar.find(self.connection, "APP", "Dashboard exports brokn")
        self.assertEqual(len(found), 1)
        self.assertGreaterEqual(found[0]["score"], similar.MIN_SCORE)

    def test_closed_tickets_are_ignored(self):
        add(self.connection, "APP", "Login page crashes on submit", "done")
        add(self.connection, "APP", "Login page crashes on submit again", "cancelled")
        self.assertEqual(similar.find(self.connection, "APP", "Login page crashes on submit"), [])

    def test_other_projects_are_ignored(self):
        add(self.connection, "OTH", "Login page crashes on submit")
        self.assertEqual(similar.find(self.connection, "APP", "Login page crashes on submit"), [])

    def test_best_match_comes_first_and_limit_applies(self):
        add(self.connection, "APP", "Login page crashes on submit button")
        exact = add(self.connection, "APP", "Login page crashes on submit")
        add(self.connection, "APP", "Login page crashes on submit click")
        add(self.connection, "APP", "Login page crashes on submit again")
        found = similar.find(self.connection, "APP", "Login page crashes on submit")
        self.assertEqual((found[0]["key"], len(found)), (exact, 3))
        self.assertGreater(found[0]["score"], found[1]["score"])
        self.assertEqual(len(similar.find(self.connection, "APP", "Login page crashes on submit", limit=1)), 1)

    def test_scores_stay_between_zero_and_one(self):
        for title in ("Login page crashes", "Login crashes page submit now", "Page"):
            add(self.connection, "APP", title)
        found = similar.find(self.connection, "APP", "Login page crashes on submit")
        self.assertTrue(found)
        for match in found:
            self.assertTrue(0 <= match["score"] <= 1)

    def test_a_title_of_only_stop_words_matches_nothing(self):
        add(self.connection, "APP", "The and of")
        self.assertEqual(similar.find(self.connection, "APP", "the of and"), [])

    def test_an_empty_title_matches_nothing(self):
        add(self.connection, "APP", "Login page crashes")
        self.assertEqual(similar.find(self.connection, "APP", ""), [])

    def test_tickets_sharing_no_word_are_never_compared(self):
        add(self.connection, "APP", "abcdefgh")
        self.assertEqual(similar.find(self.connection, "APP", "abcdefgx"), [])

    def test_the_project_key_is_case_insensitive(self):
        add(self.connection, "APP", "Login page crashes on submit")
        self.assertEqual(len(similar.find(self.connection, "app", "Login page crashes on submit")), 1)


class SimilarEndpointTests(LiveServerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ledger_cli.call(cls.base, "POST", "/api/projects", "t", {"key": "SIM", "name": "Similar"})
        cls.existing = ledger_cli.call(cls.base, "POST", "/api/tickets", "t", {"project": "SIM", "title": "Login page crashes on submit"})["key"]

    def get(self, path):
        return ledger_cli.call(self.base, "GET", path, "t")

    def test_the_endpoint_returns_matches_and_is_not_read_as_a_ticket_key(self):
        found = self.get("/api/tickets/similar?project=SIM&title=Login%20page%20crashes%20on%20submit")
        self.assertEqual(found[0]["key"], self.existing)

    def test_limit_is_applied(self):
        for number in range(3):
            ledger_cli.call(self.base, "POST", "/api/tickets", "t", {"project": "SIM", "title": f"Login page crashes on submit variant {number}"})
        found = self.get("/api/tickets/similar?project=SIM&title=Login%20page%20crashes%20on%20submit&limit=2")
        self.assertEqual(len(found), 2)

    def test_an_unknown_project_is_refused(self):
        with self.assertRaises(SystemExit) as raised:
            self.get("/api/tickets/similar?project=NOPE&title=Login%20page")
        self.assertIn("NOPE", str(raised.exception))

    def test_a_bad_limit_is_refused(self):
        with self.assertRaises(SystemExit):
            self.get("/api/tickets/similar?project=SIM&title=Login%20page&limit=x")

    def test_creating_a_duplicate_title_is_still_allowed(self):
        created = ledger_cli.call(self.base, "POST", "/api/tickets", "t", {"project": "SIM", "title": "Login page crashes on submit"})
        self.assertNotEqual(created["key"], self.existing)


class SimilarPerformanceTests(unittest.TestCase):
    def test_a_large_project_answers_inside_the_budget(self):
        connection = seeded_connection()
        rows = [("APP", number, f"Ticket {number} about the {SUBJECTS[number % 4]} subsystem and item {number * 7}",
                 "", "task", "backlog", "medium", "", "[]", "", 0.0, 0.0, None, 1.0, None) for number in range(1, BULK_TICKETS + 1)]
        connection.executemany(
            "INSERT INTO tickets (project_key, number, title, body, type, status, priority, assignee, labels, due, created, updated, closed, estimate, area_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        connection.commit()
        best = None
        for _ in range(3):
            started = time.perf_counter()
            found = similar.find(connection, "APP", "Ticket 77 about the ui subsystem and item 539")
            elapsed = (time.perf_counter() - started) * 1000
            best = elapsed if best is None else min(best, elapsed)
        self.assertEqual(found[0]["title"], "Ticket 77 about the ui subsystem and item 539")
        self.assertLess(best, FIND_BUDGET_MS)


if __name__ == "__main__":
    unittest.main()
