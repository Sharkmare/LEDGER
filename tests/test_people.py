import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from ledger import manage, people, server, store
from test_ledger import LiveServerCase


def workspace():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App")
    return connection


class AssigneeNameTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        people.add(self.connection, "ann")
        people.add(self.connection, "owner")

    def test_names_are_lowercased_and_trimmed_on_create_and_update(self):
        created = store.create_ticket(self.connection, "APP", "a", assignee="  Ann ")
        self.assertEqual(created["assignee"], "ann")
        other = store.create_ticket(self.connection, "APP", "b")
        self.assertEqual(store.update_ticket(self.connection, other["key"], {"assignee": "ANN"})["assignee"], "ann")

    def test_template_assignee_is_lowercased_and_checked(self):
        template = manage.create_template(self.connection, name="t", title="x", assignee=" ANN")
        self.assertEqual(template["assignee"], "ann")
        with self.assertRaises(store.LedgerError):
            manage.create_template(self.connection, name="u", title="x", assignee="nobody")

    def test_unknown_name_is_refused_with_the_nearest_names_and_the_command(self):
        people.add(self.connection, "annabel")
        with self.assertRaises(store.LedgerError) as raised:
            store.create_ticket(self.connection, "APP", "a", assignee="anna")
        message = str(raised.exception)
        self.assertIn("ann", message)
        self.assertIn("annabel", message)
        self.assertIn("person-add anna", message)
        self.assertEqual(store.list_tickets(self.connection), [])

    def test_unknown_name_with_no_near_match_lists_everyone_registered(self):
        with self.assertRaises(store.LedgerError) as raised:
            store.create_ticket(self.connection, "APP", "a", assignee="zzzzzz")
        self.assertIn("registered names: ann, owner", str(raised.exception))

    def test_update_to_an_unknown_name_changes_nothing(self):
        ticket = store.create_ticket(self.connection, "APP", "a", assignee="ann")
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, ticket["key"], {"assignee": "bob"})
        self.assertEqual(store.get_ticket(self.connection, ticket["key"])["assignee"], "ann")

    def test_clearing_the_assignee_needs_no_registration(self):
        ticket = store.create_ticket(self.connection, "APP", "a", assignee="ann")
        self.assertEqual(store.update_ticket(self.connection, ticket["key"], {"assignee": ""})["assignee"], "")


class MigrationTests(unittest.TestCase):
    def test_split_names_merge_and_the_registry_is_seeded_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            old = store.connect(path)
            store.create_project(old, "OLD", "Old")
            for title in ("a", "b", "c", "d"):
                store.create_ticket(old, "OLD", title)
            for number, name in ((1, "Owner"), (2, "owner"), (3, " Swarm "), (4, "")):
                old.execute("UPDATE tickets SET assignee = ? WHERE number = ?", (name, number))
            old.execute("INSERT INTO events (ticket_id, actor, field, old, new, created) VALUES (1, 'x', 'assignee', '', 'Owner', 1)")
            old.execute("DROP TABLE people")
            old.commit()
            old.close()
            migrated = store.connect(path)
            self.assertEqual([t["assignee"] for t in store.list_tickets(migrated, project_key="OLD")][::-1].count("owner"), 2)
            self.assertEqual(sorted(people.names(migrated)), ["owner", "swarm"])
            self.assertEqual(migrated.execute("SELECT new FROM events WHERE field = 'assignee'").fetchone()[0], "Owner")
            self.assertEqual(store.get_ticket(migrated, "OLD-3")["assignee"], "swarm")
            people.add(migrated, "late")
            people.remove(migrated, "late")
            migrated.close()
            again = store.connect(path)
            self.assertEqual(sorted(people.names(again)), ["owner", "swarm"])
            again.close()

    def test_a_new_database_has_nobody_registered(self):
        self.assertEqual(people.names(store.connect(":memory:")), [])


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_adding_normalises_and_refuses_duplicates_and_bad_names(self):
        self.assertEqual(people.add(self.connection, " Ann ")["name"], "ann")
        for bad in ("ann", "Ann", "has space", "", "-x", "x" * 41):
            with self.assertRaises(store.LedgerError):
                people.add(self.connection, bad)

    def test_removing_is_refused_while_open_tickets_use_the_name(self):
        people.add(self.connection, "ann")
        ticket = store.create_ticket(self.connection, "APP", "a", assignee="ann")
        with self.assertRaises(store.LedgerError) as raised:
            people.remove(self.connection, "ann")
        self.assertIn("1 open", str(raised.exception))
        store.add_comment(self.connection, ticket["key"], "t", "finished")
        store.update_ticket(self.connection, ticket["key"], {"status": "done"})
        self.assertEqual(people.remove(self.connection, "ann")["name"], "ann")
        self.assertNotIn("ann", people.names(self.connection))

    def test_unknown_names_are_not_found(self):
        with self.assertRaises(store.NotFound):
            people.remove(self.connection, "ghost")

    def test_listing_counts_open_tickets_only(self):
        people.add(self.connection, "ann")
        store.create_ticket(self.connection, "APP", "open", assignee="ann")
        store.create_ticket(self.connection, "APP", "shipped", assignee="ann", status="done")
        listed = {person["name"]: person["open_tickets"] for person in people.list_people(self.connection)}
        self.assertEqual(listed, {"ann": 1})


class StatsTests(unittest.TestCase):
    def test_unassigned_counts_only_open_tickets(self):
        connection = workspace()
        store.create_ticket(connection, "APP", "open")
        store.create_ticket(connection, "APP", "shipped", status="done")
        store.create_ticket(connection, "APP", "dropped", status="cancelled")
        figures = store.stats(connection)
        self.assertEqual((figures["open"], figures["unassigned"]), (1, 1))
        self.assertLessEqual(figures["unassigned"], figures["open"])

    def test_unassigned_respects_the_project_filter(self):
        connection = workspace()
        store.create_project(connection, "WEB", "Web")
        store.create_ticket(connection, "APP", "a")
        store.create_ticket(connection, "WEB", "b")
        store.create_ticket(connection, "WEB", "c", status="done")
        self.assertEqual(store.stats(connection, "WEB")["unassigned"], 1)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        people.add(self.connection, "ann")
        people.add(self.connection, "ben")

    def keys_and_reasons(self, person="ann"):
        return {ticket["title"]: ticket["reasons"] for ticket in people.queue(self.connection, person)["tickets"]}

    def test_queue_holds_only_assigned_tickets_and_labels_review_and_question(self):
        from ledger import questions
        store.create_ticket(self.connection, "APP", "mine", assignee="ann")
        store.create_ticket(self.connection, "APP", "reviewing", assignee="ann", status="in_review")
        asked = store.create_ticket(self.connection, "APP", "asked", assignee="ann")
        questions.ask(self.connection, asked["key"], "ben", "which one?")
        everything = store.create_ticket(self.connection, "APP", "everything", assignee="ann", status="in_review")
        questions.ask(self.connection, everything["key"], "ben", "and this?")
        store.create_ticket(self.connection, "APP", "his", assignee="ben")
        store.create_ticket(self.connection, "APP", "plain")
        self.assertEqual(self.keys_and_reasons(), {
            "mine": ["assigned"], "reviewing": ["assigned", "review"], "asked": ["assigned", "question"],
            "everything": ["assigned", "review", "question"]})
        self.assertEqual(people.queue(self.connection, "ann")["count"], 4)

    def test_review_and_question_tickets_assigned_to_someone_else_are_not_in_my_queue(self):
        from ledger import questions
        store.create_ticket(self.connection, "APP", "his review", assignee="ben", status="in_review")
        store.create_ticket(self.connection, "APP", "nobody's review", status="in_review")
        questions.ask(self.connection, store.create_ticket(self.connection, "APP", "his question", assignee="ben")["key"], "ann", "q?")
        questions.ask(self.connection, store.create_ticket(self.connection, "APP", "nobody's question")["key"], "ann", "q?")
        self.assertEqual(self.keys_and_reasons("ann"), {})
        self.assertEqual(set(self.keys_and_reasons("ben")), {"his review", "his question"})

    def test_closed_tickets_and_answered_questions_leave_the_queue_labels(self):
        from ledger import questions
        ticket = store.create_ticket(self.connection, "APP", "t", assignee="ann")
        questions.ask(self.connection, ticket["key"], "ben", "q?")
        answer_id = self.connection.execute("SELECT id FROM questions").fetchone()[0]
        questions.answer(self.connection, answer_id, "ann", "yes")
        self.assertEqual(self.keys_and_reasons(), {"t": ["assigned"]})
        store.add_comment(self.connection, ticket["key"], "t", "finished")
        store.update_ticket(self.connection, ticket["key"], {"status": "done"})
        self.assertEqual(self.keys_and_reasons(), {})

    def test_person_names_are_normalised(self):
        store.create_ticket(self.connection, "APP", "hers", assignee="ann")
        self.assertEqual(self.keys_and_reasons(" Ann "), {"hers": ["assigned"]})

    def test_unregistered_or_missing_person_has_an_empty_queue(self):
        store.create_ticket(self.connection, "APP", "reviewing", status="in_review")
        self.assertEqual(people.queue(self.connection, "ghost"), {"person": "ghost", "count": 0, "tickets": []})
        self.assertEqual(people.queue(self.connection, ""), {"person": "", "count": 0, "tickets": []})

    def test_highest_priority_comes_first(self):
        store.create_ticket(self.connection, "APP", "low", assignee="ann", priority="low")
        store.create_ticket(self.connection, "APP", "urgent", assignee="ann", priority="blocker")
        self.assertEqual([t["title"] for t in people.queue(self.connection, "ann")["tickets"]], ["urgent", "low"])


class PeopleApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})

    def test_register_assign_queue_and_remove(self):
        self.assertEqual([p["name"] for p in self.client.get("/api/people").get_json()], [])
        refused = self.client.post("/api/tickets", json={"project": "APP", "title": "t", "assignee": "Ann"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("person-add ann", refused.get_json()["error"])
        added = self.client.post("/api/people", json={"name": "Ann"})
        self.assertEqual((added.status_code, added.get_json()["name"]), (201, "ann"))
        ticket = self.client.post("/api/tickets", json={"project": "APP", "title": "t", "assignee": "Ann"}).get_json()
        self.assertEqual(ticket["assignee"], "ann")
        self.assertEqual(self.client.delete("/api/people/ann").status_code, 400)
        queue = self.client.get("/api/queue?person=ANN").get_json()
        self.assertEqual((queue["person"], queue["count"], queue["tickets"][0]["reasons"]), ("ann", 1, ["assigned"]))
        self.assertEqual(self.client.get("/api/queue").get_json(), {"person": "anonymous", "count": 0, "tickets": []})
        self.client.post(f"/api/tickets/{ticket['key']}/comments", json={"body": "finished"})
        self.client.patch(f"/api/tickets/{ticket['key']}", json={"status": "done"})
        self.assertEqual(self.client.delete("/api/people/ann").status_code, 200)
        self.assertEqual(self.client.get("/api/queue?person=ann").get_json()["count"], 0)
        self.assertEqual(self.client.post("/api/people", json={"name": "bad name"}).status_code, 400)

    def test_the_queue_defaults_to_the_requesting_actor(self):
        self.client.post("/api/people", json={"name": "ann"})
        self.client.post("/api/tickets", json={"project": "APP", "title": "t", "assignee": "ann"})
        mine = self.client.get("/api/queue", headers={"X-Ledger-Actor": "Ann"}).get_json()
        self.assertEqual((mine["person"], mine["count"]), ("ann", 1))

    def test_every_new_route_is_in_the_api_description(self):
        spec = self.client.get("/api/openapi.json").get_json()
        for path in ("/api/people", "/api/people/{person_name}", "/api/queue"):
            self.assertIn(path, spec["paths"])
        endpoints = "\n".join(server.API_HELP["endpoints"])
        self.assertIn("/api/people", endpoints)
        self.assertIn("/api/queue", endpoints)


class PeopleCliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def test_register_assign_queue_and_remove(self):
        self.cli("new-project", "PQ", "People queue")
        self.cli("person-add", "cli-test")
        self.assertIn("ann registered", self.cli("person-add", "Ann"))
        self.assertIn("ann", self.cli("people"))
        self.cli("add", "PQ", "needs a look", "--assignee", "cli-test")
        self.cli("add", "PQ", "hers", "--assignee", "ann")
        shown = self.cli("queue")
        self.assertIn("needs a look", shown)
        self.assertIn("[assigned]", shown)
        self.assertNotIn("hers", shown)
        self.assertIn("1 tickets need cli-test", shown)
        self.assertIn("hers", self.cli("queue", "--person", "ann"))
        self.assertEqual(json.loads(self.cli("--json", "queue"))["count"], 1)
        with self.assertRaises(SystemExit):
            self.cli("person-rm", "ann")
        self.cli("done", "PQ-2", "--comment", "x")
        self.assertIn("ann removed", self.cli("person-rm", "ann"))


if __name__ == "__main__":
    unittest.main()
