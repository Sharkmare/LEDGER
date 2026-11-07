from __future__ import annotations

import difflib
import re
import sqlite3
import time
from typing import Any

from . import store
from .store import LedgerError, NotFound

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,39}$")
NEAREST_LIMIT = 3
NEAREST_CUTOFF = 0.5
QUEUE_REASONS = ("assigned", "review", "question")
REVIEW_STATUS = "in_review"

PEOPLE_SCHEMA = "CREATE TABLE IF NOT EXISTS people (name TEXT PRIMARY KEY, created REAL NOT NULL)"
OPEN_QUESTION_SQL = "EXISTS (SELECT 1 FROM questions WHERE questions.ticket_id = tickets.id AND questions.answered IS NULL)"


def normalise(value: Any, field: str = "assignee") -> str:
    return store._require_text(field, value).strip().lower()


def ensure(connection: sqlite3.Connection) -> None:
    created_now = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'people'").fetchone() is None
    connection.execute(PEOPLE_SCHEMA)
    if created_now:
        connection.execute("UPDATE tickets SET assignee = lower(trim(assignee)) WHERE assignee != lower(trim(assignee))")
        connection.execute("UPDATE ticket_templates SET assignee = lower(trim(assignee)) WHERE assignee != lower(trim(assignee))")
        connection.execute("INSERT OR IGNORE INTO people (name, created) SELECT DISTINCT assignee, ? FROM tickets WHERE assignee != ''", (time.time(),))
    connection.commit()


def names(connection: sqlite3.Connection) -> list[str]:
    return [row["name"] for row in connection.execute("SELECT name FROM people ORDER BY name")]


def resolve(connection: sqlite3.Connection, value: Any) -> str:
    name = normalise(value)
    if not name or connection.execute("SELECT 1 FROM people WHERE name = ?", (name,)).fetchone():
        return name
    close = difflib.get_close_matches(name, names(connection), n=NEAREST_LIMIT, cutoff=NEAREST_CUTOFF)
    hint = f"nearest registered names: {', '.join(close)}" if close else f"registered names: {', '.join(names(connection))}"
    raise LedgerError(f"{name!r} is not a registered person; {hint}. Register a new one with: ledger_cli.py person-add {name}")


def add(connection: sqlite3.Connection, value: Any) -> dict:
    name = normalise(value, "name")
    if not NAME_PATTERN.match(name):
        raise LedgerError(f"person name {name!r} must be 1 to 40 characters of letters, digits, dot, dash or underscore")
    if connection.execute("SELECT 1 FROM people WHERE name = ?", (name,)).fetchone():
        raise LedgerError(f"{name!r} is already registered")
    connection.execute("INSERT INTO people (name, created) VALUES (?, ?)", (name, time.time()))
    connection.commit()
    return _describe(connection, name)


def remove(connection: sqlite3.Connection, value: Any) -> dict:
    name = normalise(value, "name")
    person = _describe(connection, name)
    if person["open_tickets"]:
        raise LedgerError(f"{name!r} still has {person['open_tickets']} open ticket(s); reassign them first")
    connection.execute("DELETE FROM people WHERE name = ?", (name,))
    connection.commit()
    return person


def _describe(connection: sqlite3.Connection, name: str) -> dict:
    row = connection.execute("SELECT name, created FROM people WHERE name = ?", (name,)).fetchone()
    if not row:
        raise NotFound(f"no person {name!r}")
    open_tickets = connection.execute("SELECT COUNT(*) FROM tickets WHERE assignee = ? AND closed IS NULL", (name,)).fetchone()[0]
    return {"name": row["name"], "created": row["created"], "open_tickets": open_tickets}


def list_people(connection: sqlite3.Connection) -> list[dict]:
    return [_describe(connection, name) for name in names(connection)]


def queue(connection: sqlite3.Connection, person: Any, limit: int = 500) -> dict:
    name = normalise(person, "person") if person else ""
    if not name or not connection.execute("SELECT 1 FROM people WHERE name = ?", (name,)).fetchone():
        return {"person": name, "count": 0, "tickets": []}
    review = f"tickets.status = '{REVIEW_STATUS}'"
    question = OPEN_QUESTION_SQL
    priority_order = "CASE priority " + " ".join(f"WHEN '{p}' THEN {i + 1}" for i, p in enumerate(store.PRIORITIES)) + " END"
    rows = connection.execute(
        f"SELECT *, 1 AS r_assigned, ({review}) AS r_review, ({question}) AS r_question FROM tickets"
        f" WHERE closed IS NULL AND assignee = ? ORDER BY {priority_order} DESC, updated DESC LIMIT ?",
        (name, limit)).fetchall()
    tickets = []
    for row in rows:
        ticket = store._row_to_ticket(connection, row)
        for extra in ("r_assigned", "r_review", "r_question"):
            ticket.pop(extra, None)
        ticket["reasons"] = [reason for reason, flag in zip(QUEUE_REASONS, (row["r_assigned"], row["r_review"], row["r_question"])) if flag]
        tickets.append(ticket)
    return {"person": name, "count": len(tickets), "tickets": tickets}
