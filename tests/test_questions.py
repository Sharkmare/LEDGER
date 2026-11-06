import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from ledger import questions, server, store
from test_ledger import LiveServerCase

ASKER = {server.ACTOR_HEADER: "asker"}
ANSWERER = {server.ACTOR_HEADER: "answerer"}


def fresh_connection():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App work")
    store.create_ticket(connection, "APP", "needs input")
    return connection


class QuestionStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()
        self.addCleanup(self.connection.close)

    def test_a_new_ticket_has_no_questions(self):
        ticket = store.get_ticket(self.connection, "APP-1")
        self.assertEqual((ticket["questions"], ticket["open_questions"]), ([], 0))

    def test_asking_adds_an_open_question_with_its_asker(self):
        ticket = questions.ask(self.connection, "APP-1", "ann", "  Which provider?  ")
        question = ticket["questions"][0]
        self.assertEqual((question["text"], question["asker"], question["answered"], question["answer"]), ("Which provider?", "ann", None, ""))
        self.assertEqual(ticket["open_questions"], 1)

    def test_answering_closes_the_question_and_records_who_answered(self):
        question_id = questions.ask(self.connection, "APP-1", "ann", "Which provider?")["questions"][0]["id"]
        ticket = questions.answer(self.connection, question_id, "bob", "Stripe")
        question = ticket["questions"][0]
        self.assertEqual((question["answer"], question["answerer"]), ("Stripe", "bob"))
        self.assertIsNotNone(question["answered"])
        self.assertEqual(ticket["open_questions"], 0)

    def test_an_answered_question_is_not_answered_twice(self):
        question_id = questions.ask(self.connection, "APP-1", "ann", "Which provider?")["questions"][0]["id"]
        questions.answer(self.connection, question_id, "bob", "Stripe")
        with self.assertRaises(store.LedgerError):
            questions.answer(self.connection, question_id, "cy", "Adyen")
        self.assertEqual(store.get_ticket(self.connection, "APP-1")["questions"][0]["answer"], "Stripe")

    def test_reopening_clears_the_answer_so_it_can_be_answered_again(self):
        question_id = questions.ask(self.connection, "APP-1", "ann", "Which provider?")["questions"][0]["id"]
        questions.answer(self.connection, question_id, "bob", "Stripe")
        reopened = questions.reopen(self.connection, question_id, "ann")
        self.assertEqual((reopened["open_questions"], reopened["questions"][0]["answer"], reopened["questions"][0]["answered"]), (1, "", None))
        self.assertEqual(questions.answer(self.connection, question_id, "cy", "Adyen")["questions"][0]["answer"], "Adyen")

    def test_reopening_an_open_question_is_refused(self):
        question_id = questions.ask(self.connection, "APP-1", "ann", "Which provider?")["questions"][0]["id"]
        with self.assertRaises(store.LedgerError):
            questions.reopen(self.connection, question_id, "ann")

    def test_removing_deletes_the_question(self):
        question_id = questions.ask(self.connection, "APP-1", "ann", "Which provider?")["questions"][0]["id"]
        ticket = questions.remove(self.connection, question_id, "ann")
        self.assertEqual((ticket["questions"], ticket["open_questions"]), ([], 0))

    def test_every_step_is_written_to_the_history(self):
        question_id = questions.ask(self.connection, "APP-1", "ann", "Which provider?")["questions"][0]["id"]
        questions.answer(self.connection, question_id, "bob", "Stripe")
        questions.reopen(self.connection, question_id, "ann")
        questions.remove(self.connection, question_id, "ann")
        events = [(event["actor"], event["field"], event["old"], event["new"]) for event in store.ticket_events(self.connection, "APP-1")[1:]]
        self.assertEqual(events, [
            ("ann", "question", "", "Which provider?"),
            ("bob", "answer", "Which provider?", "Stripe"),
            ("ann", "question reopened", "Stripe", "Which provider?"),
            ("ann", "question removed", "Which provider?", ""),
        ])

    def test_asking_updates_the_ticket_so_it_sorts_as_recently_changed(self):
        self.connection.execute("UPDATE tickets SET updated = 0")
        self.assertGreater(questions.ask(self.connection, "APP-1", "ann", "Which provider?")["updated"], 0)

    def test_bad_input_is_refused(self):
        for text in ("", "   ", 5, None, "x" * (questions.MAX_QUESTION_CHARS + 1)):
            with self.assertRaises(store.LedgerError, msg=repr(text)[:30]):
                questions.ask(self.connection, "APP-1", "ann", text)
        question_id = questions.ask(self.connection, "APP-1", "ann", "ok")["questions"][0]["id"]
        for text in ("", "  ", 5, "x" * (questions.MAX_ANSWER_CHARS + 1)):
            with self.assertRaises(store.LedgerError, msg=repr(text)[:30]):
                questions.answer(self.connection, question_id, "bob", text)

    def test_unknown_tickets_and_questions_are_not_found(self):
        with self.assertRaises(store.NotFound):
            questions.ask(self.connection, "APP-99", "ann", "hello")
        with self.assertRaises(store.NotFound):
            questions.answer(self.connection, 999, "bob", "x")
        for bad_id in ("abc", True, ""):
            with self.assertRaises(store.LedgerError, msg=repr(bad_id)):
                questions.answer(self.connection, bad_id, "bob", "x")

    def test_a_blank_actor_is_stored_as_anonymous(self):
        self.assertEqual(questions.ask(self.connection, "APP-1", "  ", "hello")["questions"][0]["asker"], "anonymous")

    def test_deleting_a_ticket_deletes_its_questions(self):
        questions.ask(self.connection, "APP-1", "ann", "hello")
        store.delete_ticket(self.connection, "APP-1")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 0)

    def test_the_list_filters_by_state_project_and_ticket(self):
        store.create_project(self.connection, "OTH", "Other")
        store.create_ticket(self.connection, "OTH", "elsewhere")
        first = questions.ask(self.connection, "APP-1", "ann", "first")["questions"][0]["id"]
        questions.ask(self.connection, "APP-1", "ann", "second")
        questions.ask(self.connection, "OTH-1", "ann", "third")
        questions.answer(self.connection, first, "bob", "done")
        texts = lambda **filters: [q["text"] for q in questions.list_questions(self.connection, **filters)]
        self.assertEqual(texts(), ["second", "third"])
        self.assertEqual(texts(state="answered"), ["first"])
        self.assertEqual(texts(state="all"), ["first", "second", "third"])
        self.assertEqual(texts(state="all", project_key="oth"), ["third"])
        self.assertEqual(texts(state="all", ticket_key="APP-1"), ["first", "second"])
        listing = questions.list_questions(self.connection, state="all", ticket_key="APP-1")[0]
        self.assertEqual((listing["ticket_key"], listing["ticket_title"], listing["answerer"]), ("APP-1", "needs input", "bob"))
        with self.assertRaises(store.LedgerError):
            questions.list_questions(self.connection, state="maybe")
        with self.assertRaises(store.NotFound):
            questions.list_questions(self.connection, project_key="NOPE")

    def test_tickets_can_be_filtered_to_those_with_an_open_question(self):
        store.create_ticket(self.connection, "APP", "quiet")
        question_id = questions.ask(self.connection, "APP-1", "ann", "hello")["questions"][0]["id"]
        keys = lambda **filters: [t["key"] for t in store.list_tickets(self.connection, **filters)]
        self.assertEqual(keys(has_open_questions=True), ["APP-1"])
        self.assertEqual(store.count_tickets(self.connection, has_open_questions=True), 1)
        questions.answer(self.connection, question_id, "bob", "yes")
        self.assertEqual(keys(has_open_questions=True), [])
        self.assertEqual(sorted(keys()), ["APP-1", "APP-2"])

    def test_listed_tickets_carry_their_open_question_count(self):
        questions.ask(self.connection, "APP-1", "ann", "one")
        questions.ask(self.connection, "APP-1", "ann", "two")
        self.assertEqual(store.list_tickets(self.connection)[0]["open_questions"], 2)

    def test_a_database_from_before_questions_gains_the_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            old = store.connect(path)
            store.create_project(old, "OLD", "Old")
            store.create_ticket(old, "OLD", "a")
            old.execute("DROP TABLE questions")
            old.commit()
            old.close()
            reopened = store.connect(path)
            try:
                self.assertEqual(questions.ask(reopened, "OLD-1", "ann", "still works")["open_questions"], 1)
                self.assertEqual(reopened.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 1)
            finally:
                reopened.close()


class QuestionApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})
        self.client.post("/api/tickets", json={"project": "APP", "title": "needs input"})

    def ask(self, text="Which provider?"):
        return self.client.post("/api/tickets/APP-1/questions", json={"text": text}, headers=ASKER)

    def test_ask_answer_reopen_remove_over_http(self):
        asked = self.ask()
        self.assertEqual(asked.status_code, 201)
        question_id = asked.get_json()["questions"][0]["id"]
        answered = self.client.post(f"/api/questions/{question_id}/answer", json={"answer": "Stripe"}, headers=ANSWERER)
        self.assertEqual(answered.status_code, 200)
        question = answered.get_json()["questions"][0]
        self.assertEqual((question["asker"], question["answerer"], question["answer"]), ("asker", "answerer", "Stripe"))
        self.assertEqual(self.client.post(f"/api/questions/{question_id}/reopen", headers=ASKER).get_json()["open_questions"], 1)
        removed = self.client.delete(f"/api/questions/{question_id}", headers=ASKER)
        self.assertEqual(removed.get_json()["questions"], [])

    def test_a_ticket_can_be_created_with_questions(self):
        created = self.client.post("/api/tickets", json={"project": "APP", "title": "with questions", "questions": ["one?", "two?"]}, headers=ASKER)
        ticket = created.get_json()
        self.assertEqual((created.status_code, [q["text"] for q in ticket["questions"]], ticket["open_questions"]), (201, ["one?", "two?"], 2))

    def test_a_bad_question_list_creates_no_ticket(self):
        before = len(self.client.get("/api/tickets").get_json())
        for bad in ("one?", ["ok", ""], [5]):
            response = self.client.post("/api/tickets", json={"project": "APP", "title": "never", "questions": bad})
            self.assertEqual(response.status_code, 400, bad)
        self.assertEqual(len(self.client.get("/api/tickets").get_json()), before)

    def test_listing_questions_and_filtering_tickets(self):
        self.ask("first?")
        self.client.post("/api/tickets", json={"project": "APP", "title": "quiet"})
        listed = self.client.get("/api/questions").get_json()
        self.assertEqual([(q["ticket_key"], q["text"]) for q in listed], [("APP-1", "first?")])
        self.assertEqual(self.client.get("/api/questions?state=answered").get_json(), [])
        self.assertEqual([t["key"] for t in self.client.get("/api/tickets?questions=open").get_json()], ["APP-1"])
        self.assertEqual(self.client.get("/api/tickets?questions=open").headers["X-Total-Count"], "1")
        self.assertEqual(len(self.client.get("/api/tickets").get_json()), 2)

    def test_errors_use_the_right_status(self):
        self.assertEqual(self.client.post("/api/tickets/APP-99/questions", json={"text": "x"}).status_code, 404)
        self.assertEqual(self.ask("").status_code, 400)
        self.assertEqual(self.client.post("/api/questions/999/answer", json={"answer": "x"}).status_code, 404)
        self.assertEqual(self.client.post("/api/questions/abc/answer", json={"answer": "x"}).status_code, 400)
        self.assertEqual(self.client.get("/api/questions?state=maybe").status_code, 400)
        question_id = self.ask().get_json()["questions"][0]["id"]
        self.assertEqual(self.client.post(f"/api/questions/{question_id}/reopen").status_code, 400)
        self.client.post(f"/api/questions/{question_id}/answer", json={"answer": "yes"})
        self.assertEqual(self.client.post(f"/api/questions/{question_id}/answer", json={"answer": "again"}).status_code, 400)


class QuestionCliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def data(self, *arguments):
        return json.loads(self.cli("--json", *arguments))

    def test_ask_answer_list_reopen_remove(self):
        self.cli("new-project", "QCL", "Question CLI")
        self.cli("add", "QCL", "needs input")
        asked = self.cli("question", "ask", "QCL-1", "Which provider?")
        self.assertIn("question 1 open", asked)
        question_id = self.data("question", "list", "QCL-1")[0]["id"]
        self.assertIn("Which provider?", self.cli("question", "list", "--project", "QCL"))
        self.assertIn("?1", self.cli("list", "--project", "QCL"))
        self.assertIn("QCL-1", self.cli("list", "--project", "QCL", "--questions"))
        answered = self.cli("question", "answer", str(question_id), "Stripe")
        self.assertIn("answered", answered)
        self.assertIn("Stripe", answered)
        self.assertNotIn("?1", self.cli("list", "--project", "QCL"))
        self.assertNotIn("QCL-1", self.cli("list", "--project", "QCL", "--questions"))
        self.assertIn("0 questions", self.cli("question", "list", "--project", "QCL"))
        self.assertIn("Stripe", self.cli("question", "list", "--project", "QCL", "--state", "answered"))
        self.assertIn("open", self.cli("question", "reopen", str(question_id)))
        self.assertEqual(self.data("question", "rm", str(question_id))["questions"], [])

    def test_show_lists_questions_and_add_can_ask_them(self):
        self.cli("new-project", "QSH", "Question show")
        created = self.data("add", "QSH", "with questions", "--question", "first?", "--question", "second?")
        self.assertEqual([q["text"] for q in created["questions"]], ["first?", "second?"])
        shown = self.cli("show", "QSH-1")
        self.assertIn("first?", shown)
        self.assertIn("second?", shown)
        self.assertIn("question", self.cli("history", "QSH-1"))


if __name__ == "__main__":
    unittest.main()
