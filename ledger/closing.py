from __future__ import annotations

import sqlite3

EVIDENCE_MESSAGE = "add a comment with the counts or the result before moving a ticket to done, or send it as `comment` with the status change"


def evidence_problem(connection: sqlite3.Connection, ticket_id: int, new_comment: str) -> str | None:
    if new_comment.strip():
        return None
    if connection.execute("SELECT 1 FROM comments WHERE ticket_id = ? LIMIT 1", (ticket_id,)).fetchone():
        return None
    return EVIDENCE_MESSAGE


def open_blocker_keys(connection: sqlite3.Connection, ticket_id: int) -> list[str]:
    return [f"{row['project_key']}-{row['number']}" for row in connection.execute(
        "SELECT t.project_key, t.number FROM links l JOIN tickets t ON t.id = l.ticket_id"
        " WHERE l.other_id = ? AND l.kind = 'blocks' AND t.status NOT IN ('done', 'cancelled')"
        " ORDER BY t.project_key, t.number", (ticket_id,))]


def blocker_problem(connection: sqlite3.Connection, ticket_id: int) -> str | None:
    blockers = open_blocker_keys(connection, ticket_id)
    if not blockers:
        return None
    return f"still blocked by {', '.join(blockers)}; finish or cancel them first"


def closing_problem(connection: sqlite3.Connection, ticket_id: int, new_comment: str) -> str | None:
    return blocker_problem(connection, ticket_id) or evidence_problem(connection, ticket_id, new_comment)
