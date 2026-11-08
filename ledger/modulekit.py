from __future__ import annotations

import datetime
import sqlite3
from typing import Any

from . import store
from .store import LedgerError

FILTER_KEYS = ("project", "area", "iteration", "type", "status", "priority", "assignee", "label", "open")
SECONDS_PER_DAY = 86400
UNASSIGNED = "unassigned"


def ticket_rows(connection: sqlite3.Connection, filters: dict, columns: str = "*", include_closed: bool | None = None) -> list[sqlite3.Row]:
    open_only = filters.get("open") if include_closed is None else not include_closed
    where, parameters = store._filter_clause(
        filters.get("project"), filters.get("status"), filters.get("assignee"), filters.get("type"), filters.get("priority"),
        filters.get("label"), None, not open_only, None, filters.get("area"), filters.get("iteration"), connection)
    return connection.execute(f"SELECT {columns} FROM tickets {where}", parameters).fetchall()


def day(stamp: float) -> datetime.date:
    return datetime.date.fromtimestamp(stamp)


def bucketed(values: list[float], buckets: tuple) -> list[dict]:
    result = [{"label": label, "value": 0} for _, label in buckets]
    for value in values:
        for index, (limit, _) in enumerate(buckets):
            if limit is None or value <= limit:
                result[index]["value"] += 1
                break
    return result


def whole_number(field: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not (isinstance(value, int) or str(value).strip().lstrip("-").isdigit()):
        raise LedgerError(f"{field} must be a whole number")
    number = int(value)
    if not low <= number <= high:
        raise LedgerError(f"{field} must be between {low} and {high}")
    return number
