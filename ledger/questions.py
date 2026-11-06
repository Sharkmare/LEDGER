from __future__ import annotations

import sqlite3
import time
from typing import Any

from . import store
from .store import LedgerError, NotFound

MAX_QUESTION_CHARS = 2000
MAX_ANSWER_CHARS = 10000
QUESTION_STATES = ("open", "answered", "all")


def clean_text(field: str, value: Any, limit: int) -> str:
    text = store._require_text(field, value).strip()
    if not text:
        raise LedgerError(f"{field} is required")
    if len(text) > limit:
        raise LedgerError(f"{field} is at most {limit} characters")
    return text


def clean_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise LedgerError("questions must be a list of text")
    return [clean_text("question", item, MAX_QUESTION_CHARS) for item in value]


def _question_row(connection: sqlite3.Connection, question_id: Any) -> sqlite3.Row:
    if isinstance(question_id, bool) or not str(question_id).strip().isdigit():
        raise LedgerError("question id must be a whole number")
    row = connection.execute("SELECT * FROM questions WHERE id = ?", (int(question_id),)).fetchone()
    if not row:
        raise NotFound(f"no question {question_id}")
    return row


def _ticket_key_of_question(connection: sqlite3.Connection, row: sqlite3.Row) -> str:
    ticket = connection.execute("SELECT project_key, number FROM tickets WHERE id = ?", (row["ticket_id"],)).fetchone()
    return f"{ticket['project_key']}-{ticket['number']}"


def _log(connection: sqlite3.Connection, ticket_id: int, actor: str, field: str, old: str, new: str, now: float) -> None:
    connection.execute("INSERT INTO events (ticket_id, actor, field, old, new, created) VALUES (?, ?, ?, ?, ?, ?)", (ticket_id, actor, field, old, new, now))
    connection.execute("UPDATE tickets SET updated = ? WHERE id = ?", (now, ticket_id))


def _person(name: str) -> str:
    return str(name).strip() or "anonymous"


def ask(connection: sqlite3.Connection, ticket_key: str, asker: str, text: Any) -> dict:
    ticket = store._find_row(connection, ticket_key)
    text = clean_text("question", text, MAX_QUESTION_CHARS)
    now = time.time()
    asker = _person(asker)
    connection.execute("INSERT INTO questions (ticket_id, text, asker, created) VALUES (?, ?, ?, ?)", (ticket["id"], text, asker, now))
    _log(connection, ticket["id"], asker, "question", "", text, now)
    connection.commit()
    return store.get_ticket(connection, ticket_key)


def answer(connection: sqlite3.Connection, question_id: Any, answerer: str, text: Any) -> dict:
    row = _question_row(connection, question_id)
    if row["answered"] is not None:
        raise LedgerError("question is already answered; reopen it to answer again")
    text = clean_text("answer", text, MAX_ANSWER_CHARS)
    now = time.time()
    answerer = _person(answerer)
    connection.execute("UPDATE questions SET answer = ?, answerer = ?, answered = ? WHERE id = ?", (text, answerer, now, row["id"]))
    _log(connection, row["ticket_id"], answerer, "answer", row["text"], text, now)
    connection.commit()
    return store.get_ticket(connection, _ticket_key_of_question(connection, row))


def reopen(connection: sqlite3.Connection, question_id: Any, actor: str) -> dict:
    row = _question_row(connection, question_id)
    if row["answered"] is None:
        raise LedgerError("question is already open")
    connection.execute("UPDATE questions SET answer = '', answerer = '', answered = NULL WHERE id = ?", (row["id"],))
    _log(connection, row["ticket_id"], _person(actor), "question reopened", row["answer"], row["text"], time.time())
    connection.commit()
    return store.get_ticket(connection, _ticket_key_of_question(connection, row))


def remove(connection: sqlite3.Connection, question_id: Any, actor: str) -> dict:
    row = _question_row(connection, question_id)
    ticket_key = _ticket_key_of_question(connection, row)
    connection.execute("DELETE FROM questions WHERE id = ?", (row["id"],))
    _log(connection, row["ticket_id"], _person(actor), "question removed", row["text"], "", time.time())
    connection.commit()
    return store.get_ticket(connection, ticket_key)


def list_questions(connection: sqlite3.Connection, state: Any = "open", project_key: str | None = None, ticket_key: str | None = None, limit: int = 500) -> list[dict]:
    state = store._require_choice("state", state or "open", QUESTION_STATES)
    clauses, parameters = [], []
    if state == "open":
        clauses.append("questions.answered IS NULL")
    elif state == "answered":
        clauses.append("questions.answered IS NOT NULL")
    if project_key:
        store._check_project_exists(connection, project_key)
        clauses.append("tickets.project_key = ?")
        parameters.append(project_key.upper())
    if ticket_key:
        ticket = store._find_row(connection, ticket_key)
        clauses.append("tickets.id = ?")
        parameters.append(ticket["id"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        "SELECT questions.*, tickets.project_key, tickets.number, tickets.title AS ticket_title, tickets.status AS ticket_status"
        f" FROM questions JOIN tickets ON tickets.id = questions.ticket_id {where} ORDER BY questions.created, questions.id LIMIT ?",
        (*parameters, limit)).fetchall()
    return [{"id": row["id"], "ticket_key": f"{row['project_key']}-{row['number']}", "ticket_title": row["ticket_title"], "ticket_status": row["ticket_status"],
             "text": row["text"], "asker": row["asker"], "created": row["created"], "answer": row["answer"], "answerer": row["answerer"],
             "answered": row["answered"]} for row in rows]
