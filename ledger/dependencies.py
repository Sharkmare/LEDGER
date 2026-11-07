from __future__ import annotations

import sqlite3
from collections import deque

from . import closing, store

CLOSED = store.CLOSED_STATUSES


def _key(row: sqlite3.Row) -> str:
    return f"{row['project_key']}-{row['number']}"


def _neighbours(connection: sqlite3.Connection, ticket_id: int, upstream: bool) -> list[sqlite3.Row]:
    near, far = ("other_id", "ticket_id") if upstream else ("ticket_id", "other_id")
    return connection.execute(
        f"SELECT t.id, t.project_key, t.number, t.title, t.status FROM links l JOIN tickets t ON t.id = l.{far}"
        f" WHERE l.{near} = ? AND l.kind = 'blocks' ORDER BY t.project_key, t.number", (ticket_id,)).fetchall()


def _chain(connection: sqlite3.Connection, start_id: int, upstream: bool) -> list[dict]:
    seen = {start_id}
    chain: list[dict] = []
    queue = deque([(start_id, 0)])
    while queue:
        ticket_id, depth = queue.popleft()
        for row in _neighbours(connection, ticket_id, upstream):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            chain.append({"key": _key(row), "title": row["title"], "status": row["status"], "depth": depth + 1})
            queue.append((row["id"], depth + 1))
    return chain


def for_ticket(connection: sqlite3.Connection, ticket_key: str) -> dict:
    row = store._find_row(connection, ticket_key)
    return {"key": _key(row), "blocked_by": _chain(connection, row["id"], True), "blocks": _chain(connection, row["id"], False),
            "open_blockers": len(closing.open_blocker_keys(connection, row["id"]))}


def _descendant_ids(connection: sqlite3.Connection, ticket_id: int) -> list[int]:
    found: list[int] = []
    pending = [ticket_id]
    while pending:
        children = [row["id"] for row in connection.execute(
            f"SELECT id FROM tickets WHERE parent_id IN ({','.join('?' * len(pending))})", pending)]
        found.extend(children)
        pending = children
    return found


def has_children(connection: sqlite3.Connection, ticket_key: str) -> bool:
    row = store._find_row(connection, ticket_key)
    return connection.execute("SELECT 1 FROM tickets WHERE parent_id = ?", (row["id"],)).fetchone() is not None


def _drop_back_edges(successors: dict[int, list[int]], order: list[int]) -> dict[int, list[int]]:
    kept: dict[int, list[int]] = {ticket_id: [] for ticket_id in successors}
    state: dict[int, int] = {}
    for start in order:
        if start in state:
            continue
        state[start] = 1
        stack = [(start, iter(successors[start]))]
        while stack:
            node, remaining = stack[-1]
            for nxt in remaining:
                if state.get(nxt) == 1:
                    continue
                kept[node].append(nxt)
                if nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(successors[nxt])))
                    break
            else:
                state[node] = 2
                stack.pop()
    return kept


def critical_path(connection: sqlite3.Connection, epic_key: str) -> list[str]:
    epic = store._find_row(connection, epic_key)
    ids = _descendant_ids(connection, epic["id"])
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    keys = {row["id"]: _key(row) for row in connection.execute(
        f"SELECT id, project_key, number FROM tickets WHERE id IN ({placeholders}) AND status NOT IN ('done', 'cancelled')", ids)}
    successors: dict[int, list[int]] = {ticket_id: [] for ticket_id in keys}
    for link in connection.execute(
            f"SELECT ticket_id, other_id FROM links WHERE kind = 'blocks' AND ticket_id IN ({placeholders}) AND other_id IN ({placeholders})", ids + ids):
        if link["ticket_id"] in keys and link["other_id"] in keys:
            successors[link["ticket_id"]].append(link["other_id"])
    ordered = sorted(keys, key=lambda candidate: keys[candidate])
    acyclic = _drop_back_edges(successors, ordered)
    longest: dict[int, list[int]] = {}

    def best_from(ticket_id: int) -> list[int]:
        if ticket_id not in longest:
            longest[ticket_id] = [ticket_id] + max((best_from(nxt) for nxt in acyclic[ticket_id]), key=len, default=[])
        return longest[ticket_id]

    best: list[int] = []
    for ticket_id in ordered:
        path = best_from(ticket_id)
        if len(path) > len(best):
            best = path
    return [keys[ticket_id] for ticket_id in best] if len(best) > 1 else []


def describe(connection: sqlite3.Connection, ticket_key: str) -> dict:
    result = for_ticket(connection, ticket_key)
    if has_children(connection, ticket_key):
        result["critical_path"] = critical_path(connection, ticket_key)
    return result
