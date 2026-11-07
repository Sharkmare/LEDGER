from __future__ import annotations

import sqlite3
from typing import Any

from . import store

LIMITED_STATUSES = ("in_progress", "in_review", "blocked")
MAX_LIMIT = 10000

TABLE = """
CREATE TABLE IF NOT EXISTS wip_limits (
    status TEXT PRIMARY KEY,
    "limit" INTEGER NOT NULL
)
"""


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(TABLE)


def _clean_limit(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise store.LedgerError("limit must be a whole number, or 0 or null to clear it")
    try:
        number = int(value)
    except ValueError:
        raise store.LedgerError("limit must be a whole number, or 0 or null to clear it") from None
    if number < 0 or number > MAX_LIMIT:
        raise store.LedgerError(f"limit must be between 0 and {MAX_LIMIT}")
    return number or None


def overview(connection: sqlite3.Connection) -> dict:
    _ensure_table(connection)
    limits = {row["status"]: row["limit"] for row in connection.execute('SELECT status, "limit" FROM wip_limits')}
    counts = {status: 0 for status in store.STATUSES}
    for row in connection.execute("SELECT status, COUNT(*) AS total FROM tickets GROUP BY status"):
        counts[row["status"]] = row["total"]
    return {"limited_statuses": list(LIMITED_STATUSES), "limits": limits, "counts": counts,
            "over": [status for status, limit in limits.items() if counts.get(status, 0) > limit]}


def set_limit(connection: sqlite3.Connection, status: str, value: Any) -> dict:
    if status not in LIMITED_STATUSES:
        raise store.LedgerError(f"only {', '.join(LIMITED_STATUSES)} may have a limit")
    limit = _clean_limit(value)
    _ensure_table(connection)
    if limit is None:
        connection.execute("DELETE FROM wip_limits WHERE status = ?", (status,))
    else:
        connection.execute('INSERT INTO wip_limits (status, "limit") VALUES (?, ?) ON CONFLICT(status) DO UPDATE SET "limit" = excluded."limit"',
                           (status, limit))
    connection.commit()
    return overview(connection)
