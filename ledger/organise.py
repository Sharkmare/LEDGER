from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from . import store
from .store import (CLOSED_STATUSES, ITERATION_STATES, PRIORITIES, STATUSES, TICKET_TYPES, LedgerError, NotFound, _area_path,
                    _clean_date, _find_row, _require_choice, _require_order, _require_text)

DEFAULT_ORGANISATION = "My organisation"
MAX_NAME_CHARS = 80
BOARD_SCOPES = ("area", "all")
BOARD_RULE_KEYS = ("scope", "project", "types", "priorities", "labels", "assignee", "parent", "iteration")


def _clean_name(field: str, value: Any) -> str:
    name = " ".join(_require_text(field, value).split())
    if not name:
        raise LedgerError(f"{field} is required")
    if len(name) > MAX_NAME_CHARS:
        raise LedgerError(f"{field} is {len(name)} characters, the limit is {MAX_NAME_CHARS}")
    return name


def get_organisation(connection: sqlite3.Connection) -> dict:
    row = connection.execute("SELECT name FROM organisation WHERE id = 1").fetchone()
    return {"name": row["name"] if row else DEFAULT_ORGANISATION}


def set_organisation(connection: sqlite3.Connection, name: Any) -> dict:
    cleaned = _clean_name("name", name)
    connection.execute("INSERT INTO organisation (id, name) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET name = excluded.name", (cleaned,))
    connection.commit()
    return get_organisation(connection)


def _area_row(connection: sqlite3.Connection, area_id: Any) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM areas WHERE id = ?", (area_id,)).fetchone()
    if not row:
        raise NotFound(f"no area {area_id}")
    return row


def area_subtree_ids(connection: sqlite3.Connection, area_id: int) -> list[int]:
    rows = connection.execute(
        "WITH RECURSIVE sub(id) AS (SELECT id FROM areas WHERE id = ? UNION SELECT a.id FROM areas a JOIN sub ON a.parent_id = sub.id)"
        " SELECT id FROM sub", (area_id,)).fetchall()
    return [row["id"] for row in rows]


def _area_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    area = dict(row)
    area["tags"] = [tag for tag in area.get("tags", "").split(",") if tag]
    area["path"] = _area_path(connection, row["id"])
    area["depth"] = area["path"].count(" / ")
    area["boards"] = connection.execute("SELECT COUNT(*) FROM boards WHERE area_id = ?", (row["id"],)).fetchone()[0]
    subtree = area_subtree_ids(connection, row["id"])
    placeholders = ",".join("?" * len(subtree))
    area["tickets"] = connection.execute(f"SELECT COUNT(*) FROM tickets WHERE area_id IN ({placeholders})", subtree).fetchone()[0]
    area["open_tickets"] = connection.execute(
        f"SELECT COUNT(*) FROM tickets WHERE area_id IN ({placeholders}) AND closed IS NULL", subtree).fetchone()[0]
    return area


def list_areas(connection: sqlite3.Connection) -> list[dict]:
    areas = [_area_dict(connection, row) for row in connection.execute("SELECT * FROM areas")]
    return sorted(areas, key=lambda area: area["path"].lower())


def get_area(connection: sqlite3.Connection, area_id: Any) -> dict:
    area = _area_dict(connection, _area_row(connection, area_id))
    area["boards_list"] = list_boards(connection, area=area["id"])
    return area


def _check_sibling_name(connection: sqlite3.Connection, parent_id: int | None, name: str, own_id: int | None) -> None:
    for row in connection.execute("SELECT id, name FROM areas WHERE parent_id IS ?", (parent_id,)):
        if row["id"] != own_id and row["name"].lower() == name.lower():
            raise LedgerError(f"there is already an area named {name!r} here")


def _clean_area_name(value: Any) -> str:
    name = _clean_name("name", value)
    if "/" in name:
        raise LedgerError("an area name cannot contain a slash; nest areas with a parent instead")
    return name


def create_area(connection: sqlite3.Connection, name: Any, description: Any = "", parent: Any = None, tags: Any = "") -> dict:
    name = _clean_area_name(name)
    description = _require_text("description", description)
    parent_id = store._resolve_area_id(connection, parent)
    _check_sibling_name(connection, parent_id, name, None)
    cursor = connection.execute("INSERT INTO areas (name, description, parent_id, created, tags) VALUES (?, ?, ?, ?, ?)",
                                (name, description, parent_id, time.time(), store.clean_project_tags(tags)))
    connection.commit()
    return get_area(connection, cursor.lastrowid)


def update_area(connection: sqlite3.Connection, area_id: Any, changes: dict) -> dict:
    row = _area_row(connection, area_id)
    unknown = sorted(set(changes) - {"name", "description", "parent", "tags"})
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are name, description, parent, tags")
    tags = store.clean_project_tags(changes["tags"]) if "tags" in changes else row["tags"]
    name = _clean_area_name(changes["name"]) if "name" in changes else row["name"]
    description = _require_text("description", changes["description"]) if "description" in changes else row["description"]
    parent_id = store._resolve_area_id(connection, changes["parent"]) if "parent" in changes else row["parent_id"]
    if parent_id is not None and parent_id in area_subtree_ids(connection, row["id"]):
        raise LedgerError("an area cannot be moved under itself or one of its own sub-areas")
    _check_sibling_name(connection, parent_id, name, row["id"])
    connection.execute("UPDATE areas SET name = ?, description = ?, parent_id = ?, tags = ? WHERE id = ?",
                       (name, description, parent_id, tags, row["id"]))
    connection.commit()
    return get_area(connection, row["id"])


def delete_area(connection: sqlite3.Connection, area_id: Any) -> None:
    row = _area_row(connection, area_id)
    if connection.execute("SELECT 1 FROM areas WHERE parent_id = ?", (row["id"],)).fetchone():
        raise LedgerError("area has sub-areas; move or delete them first")
    if connection.execute("SELECT 1 FROM boards WHERE area_id = ?", (row["id"],)).fetchone():
        raise LedgerError("area has boards; move or delete them first")
    connection.execute("UPDATE tickets SET area_id = NULL WHERE area_id = ?", (row["id"],))
    connection.execute("DELETE FROM areas WHERE id = ?", (row["id"],))
    connection.commit()


def _string_list(field: str, value: Any, allowed: tuple[str, ...] | None = None, lower: bool = True) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise LedgerError(f"{field} must be a list of text")
    items = []
    for item in value:
        cleaned = item.strip().lower() if lower else item.strip()
        if not cleaned:
            continue
        if allowed is not None and cleaned not in allowed:
            raise LedgerError(f"{field} {item!r} is not one of {', '.join(allowed)}")
        if cleaned not in items:
            items.append(cleaned)
    return items


def _clean_rules(connection: sqlite3.Connection, rules: Any) -> dict:
    if rules is None or rules == "":
        return {}
    if not isinstance(rules, dict):
        raise LedgerError("rules must be an object")
    unknown = sorted(set(rules) - set(BOARD_RULE_KEYS))
    if unknown:
        raise LedgerError(f"unknown rule {', '.join(unknown)}; rules are {', '.join(BOARD_RULE_KEYS)}")
    cleaned: dict[str, Any] = {}
    if rules.get("scope"):
        cleaned["scope"] = _require_choice("scope", rules["scope"], BOARD_SCOPES)
    if rules.get("project"):
        cleaned["project"] = store.get_project(connection, _require_text("project", rules["project"]))["key"]
    if rules.get("types"):
        cleaned["types"] = _string_list("types", rules["types"], TICKET_TYPES)
    if rules.get("priorities"):
        cleaned["priorities"] = _string_list("priorities", rules["priorities"], PRIORITIES)
    if rules.get("labels"):
        cleaned["labels"] = _string_list("labels", rules["labels"])
    if rules.get("assignee"):
        cleaned["assignee"] = _require_text("assignee", rules["assignee"]).strip()
    if rules.get("parent"):
        row = _find_row(connection, _require_text("parent", rules["parent"]))
        cleaned["parent"] = f"{row['project_key']}-{row['number']}"
    if rules.get("iteration") not in (None, ""):
        iteration = rules["iteration"]
        if isinstance(iteration, bool) or not (isinstance(iteration, int) or str(iteration).strip().isdigit()):
            raise LedgerError("the iteration rule is an iteration id")
        _iteration_row(connection, int(iteration))
        cleaned["iteration"] = int(iteration)
    return {key: value for key, value in cleaned.items() if value}


def _clean_statuses(statuses: Any) -> list[str]:
    if statuses is None or statuses == "":
        return []
    items = _string_list("statuses", statuses, STATUSES)
    return [] if items == list(STATUSES) else items


def _board_row(connection: sqlite3.Connection, board_id: Any) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    if not row:
        raise NotFound(f"no board {board_id}")
    return row


def _board_where(connection: sqlite3.Connection, board: sqlite3.Row) -> tuple[str, list]:
    rules = json.loads(board["rules"])
    clauses, parameters = [], []
    if rules.get("scope", "area") == "area":
        subtree = area_subtree_ids(connection, board["area_id"])
        clauses.append(f"area_id IN ({','.join('?' * len(subtree))})")
        parameters += subtree
    if rules.get("project"):
        clauses.append("project_key = ?")
        parameters.append(rules["project"])
    for column, field in (("type", "types"), ("priority", "priorities")):
        if rules.get(field):
            clauses.append(f"{column} IN ({','.join('?' * len(rules[field]))})")
            parameters += rules[field]
    if rules.get("labels"):
        clauses.append(f"EXISTS (SELECT 1 FROM json_each(tickets.labels) WHERE json_each.value IN ({','.join('?' * len(rules['labels']))}))")
        parameters += rules["labels"]
    if rules.get("assignee"):
        clauses.append("assignee = ? COLLATE NOCASE")
        parameters.append(rules["assignee"])
    if rules.get("parent"):
        parent = _find_row(connection, rules["parent"])
        clauses.append("id IN (WITH RECURSIVE sub(id) AS (SELECT id FROM tickets WHERE parent_id = ? UNION SELECT t.id FROM tickets t"
                       " JOIN sub ON t.parent_id = sub.id) SELECT id FROM sub)")
        parameters.append(parent["id"])
    if rules.get("iteration"):
        clauses.append("iteration_id = ?")
        parameters.append(rules["iteration"])
    matching = " AND ".join(clauses) or "1 = 1"
    return f"({matching}) OR id IN (SELECT ticket_id FROM board_items WHERE board_id = ?)", [*parameters, board["id"]]


def _board_ticket_rows(connection: sqlite3.Connection, board: sqlite3.Row, limit: int = 5000) -> list[sqlite3.Row]:
    where, parameters = _board_where(connection, board)
    priority_order = "CASE priority " + " ".join(f"WHEN '{name}' THEN {index + 1}" for index, name in enumerate(PRIORITIES)) + " END"
    return connection.execute(
        f"SELECT * FROM tickets WHERE {where} ORDER BY {priority_order} DESC, updated DESC LIMIT ?", (*parameters, limit)).fetchall()


def _board_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    stored = json.loads(row["columns"])
    where, parameters = _board_where(connection, row)
    return {
        "id": row["id"], "area_id": row["area_id"], "area": _area_path(connection, row["area_id"]), "name": row["name"],
        "description": row["description"], "rules": json.loads(row["rules"]), "statuses": stored or list(STATUSES),
        "pinned": connection.execute("SELECT COUNT(*) FROM board_items WHERE board_id = ?", (row["id"],)).fetchone()[0],
        "tickets": connection.execute(f"SELECT COUNT(*) FROM tickets WHERE {where}", parameters).fetchone()[0],
        "created": row["created"],
    }


def list_boards(connection: sqlite3.Connection, area: Any = None) -> list[dict]:
    if area in (None, ""):
        rows = connection.execute("SELECT * FROM boards ORDER BY id").fetchall()
    else:
        area_id = store._resolve_area_id(connection, area)
        rows = connection.execute("SELECT * FROM boards WHERE area_id = ? ORDER BY id", (area_id,)).fetchall()
    return sorted((_board_dict(connection, row) for row in rows), key=lambda board: (board["area"].lower(), board["name"].lower()))


def create_board(connection: sqlite3.Connection, area: Any, name: Any, description: Any = "", rules: Any = None, statuses: Any = None) -> dict:
    area_id = store._resolve_area_id(connection, area)
    if area_id is None:
        raise LedgerError("a board belongs to an area; give an area id or name")
    name = _clean_name("name", name)
    description = _require_text("description", description)
    cleaned_rules = _clean_rules(connection, rules)
    cleaned_statuses = _clean_statuses(statuses)
    for row in connection.execute("SELECT name FROM boards WHERE area_id = ?", (area_id,)):
        if row["name"].lower() == name.lower():
            raise LedgerError(f"this area already has a board named {name!r}")
    cursor = connection.execute(
        "INSERT INTO boards (area_id, name, description, rules, columns, created) VALUES (?, ?, ?, ?, ?, ?)",
        (area_id, name, description, json.dumps(cleaned_rules), json.dumps(cleaned_statuses), time.time()))
    connection.commit()
    return get_board(connection, cursor.lastrowid)


def update_board(connection: sqlite3.Connection, board_id: Any, changes: dict) -> dict:
    row = _board_row(connection, board_id)
    unknown = sorted(set(changes) - {"name", "description", "area", "rules", "statuses"})
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are name, description, area, rules, statuses")
    name = _clean_name("name", changes["name"]) if "name" in changes else row["name"]
    description = _require_text("description", changes["description"]) if "description" in changes else row["description"]
    area_id = store._resolve_area_id(connection, changes["area"]) if "area" in changes else row["area_id"]
    if area_id is None:
        raise LedgerError("a board belongs to an area")
    rules = json.dumps(_clean_rules(connection, changes["rules"])) if "rules" in changes else row["rules"]
    statuses = json.dumps(_clean_statuses(changes["statuses"])) if "statuses" in changes else row["columns"]
    for other in connection.execute("SELECT id, name FROM boards WHERE area_id = ?", (area_id,)):
        if other["id"] != row["id"] and other["name"].lower() == name.lower():
            raise LedgerError(f"this area already has a board named {name!r}")
    connection.execute("UPDATE boards SET name = ?, description = ?, area_id = ?, rules = ?, columns = ? WHERE id = ?",
                       (name, description, area_id, rules, statuses, row["id"]))
    connection.commit()
    return get_board(connection, row["id"])


def delete_board(connection: sqlite3.Connection, board_id: Any) -> None:
    row = _board_row(connection, board_id)
    connection.execute("DELETE FROM board_items WHERE board_id = ?", (row["id"],))
    connection.execute("DELETE FROM boards WHERE id = ?", (row["id"],))
    connection.commit()


def get_board(connection: sqlite3.Connection, board_id: Any) -> dict:
    row = _board_row(connection, board_id)
    board = _board_dict(connection, row)
    columns = {status: [] for status in board["statuses"]}
    hidden = 0
    pinned_keys = []
    pinned_ids = {entry["ticket_id"] for entry in connection.execute("SELECT ticket_id FROM board_items WHERE board_id = ?", (row["id"],))}
    for ticket_row in _board_ticket_rows(connection, row):
        ticket = store._row_to_ticket(connection, ticket_row)
        ticket["pinned"] = ticket_row["id"] in pinned_ids
        if ticket["pinned"]:
            pinned_keys.append(ticket["key"])
        if ticket["status"] in columns:
            columns[ticket["status"]].append(ticket)
        else:
            hidden += 1
    board["columns"] = columns
    board["hidden"] = hidden
    board["pinned_keys"] = pinned_keys
    return board


def board_tickets(connection: sqlite3.Connection, board_id: Any) -> list[dict]:
    row = _board_row(connection, board_id)
    return [store._row_to_ticket(connection, ticket_row) for ticket_row in _board_ticket_rows(connection, row)]


def pin_ticket(connection: sqlite3.Connection, board_id: Any, ticket_key: str) -> dict:
    row, ticket = _board_row(connection, board_id), _find_row(connection, ticket_key)
    connection.execute("INSERT OR IGNORE INTO board_items (board_id, ticket_id, added) VALUES (?, ?, ?)", (row["id"], ticket["id"], time.time()))
    connection.commit()
    return get_board(connection, row["id"])


def unpin_ticket(connection: sqlite3.Connection, board_id: Any, ticket_key: str) -> dict:
    row, ticket = _board_row(connection, board_id), _find_row(connection, ticket_key)
    connection.execute("DELETE FROM board_items WHERE board_id = ? AND ticket_id = ?", (row["id"], ticket["id"]))
    connection.commit()
    return get_board(connection, row["id"])


def _iteration_row(connection: sqlite3.Connection, iteration_id: Any) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM iterations WHERE id = ?", (iteration_id,)).fetchone()
    if not row:
        raise NotFound(f"no iteration {iteration_id}")
    return row


def _iteration_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    members = connection.execute(
        "SELECT status, estimate FROM tickets WHERE iteration_id = ? AND status != 'cancelled'", (row["id"],)).fetchall()
    done = [member for member in members if member["status"] == "done"]
    return {
        "id": row["id"], "project": row["project_key"], "name": row["name"], "start": row["starts"], "end": row["ends"],
        "goal": row["goal"], "state": row["state"], "created": row["created"],
        "tickets": len(members), "done": len(done),
        "points": sum(member["estimate"] or 0 for member in members), "points_done": sum(member["estimate"] or 0 for member in done),
    }


def _clean_required_date(field: str, value: Any) -> str:
    text = _clean_date(field, value)
    if not text:
        raise LedgerError(f"{field} is required, use YYYY-MM-DD")
    return text


def create_iteration(connection: sqlite3.Connection, project: Any, name: Any, start: Any, end: Any, goal: Any = "",
                     state: Any = "planned") -> dict:
    project_key = store.get_project(connection, _require_text("project", project))["key"]
    name = _clean_name("name", name)
    start, end = _clean_required_date("start", start), _clean_required_date("end", end)
    _require_order("start", start, "end", end)
    state = _require_choice("state", state, ITERATION_STATES)
    for row in connection.execute("SELECT name FROM iterations WHERE project_key = ?", (project_key,)):
        if row["name"].lower() == name.lower():
            raise LedgerError(f"project {project_key} already has an iteration named {name!r}")
    cursor = connection.execute(
        "INSERT INTO iterations (project_key, name, starts, ends, goal, state, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_key, name, start, end, _require_text("goal", goal), state, time.time()))
    connection.commit()
    return get_iteration(connection, cursor.lastrowid)


def get_iteration(connection: sqlite3.Connection, iteration_id: Any) -> dict:
    return _iteration_dict(connection, _iteration_row(connection, iteration_id))


def list_iterations(connection: sqlite3.Connection, project: Any = None, state: Any = None) -> list[dict]:
    clauses, parameters = [], []
    if project:
        clauses.append("project_key = ?")
        parameters.append(store.get_project(connection, project)["key"])
    if state:
        clauses.append("state = ?")
        parameters.append(_require_choice("state", state, ITERATION_STATES))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(f"SELECT * FROM iterations {where} ORDER BY starts, id", parameters).fetchall()
    return [_iteration_dict(connection, row) for row in rows]


def update_iteration(connection: sqlite3.Connection, iteration_id: Any, changes: dict) -> dict:
    row = _iteration_row(connection, iteration_id)
    unknown = sorted(set(changes) - {"name", "start", "end", "goal", "state"})
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are name, start, end, goal, state")
    name = _clean_name("name", changes["name"]) if "name" in changes else row["name"]
    start = _clean_required_date("start", changes["start"]) if "start" in changes else row["starts"]
    end = _clean_required_date("end", changes["end"]) if "end" in changes else row["ends"]
    _require_order("start", start, "end", end)
    goal = _require_text("goal", changes["goal"]) if "goal" in changes else row["goal"]
    state = _require_choice("state", changes["state"], ITERATION_STATES) if "state" in changes else row["state"]
    for other in connection.execute("SELECT id, name FROM iterations WHERE project_key = ?", (row["project_key"],)):
        if other["id"] != row["id"] and other["name"].lower() == name.lower():
            raise LedgerError(f"project {row['project_key']} already has an iteration named {name!r}")
    connection.execute("UPDATE iterations SET name = ?, starts = ?, ends = ?, goal = ?, state = ? WHERE id = ?",
                       (name, start, end, goal, state, row["id"]))
    connection.commit()
    return get_iteration(connection, row["id"])


def delete_iteration(connection: sqlite3.Connection, iteration_id: Any) -> None:
    row = _iteration_row(connection, iteration_id)
    connection.execute("UPDATE tickets SET iteration_id = NULL WHERE iteration_id = ?", (row["id"],))
    connection.execute("DELETE FROM iterations WHERE id = ?", (row["id"],))
    connection.commit()


def plan(connection: sqlite3.Connection, project: Any) -> dict:
    project_key = store.get_project(connection, _require_text("project", project))["key"]
    priority_order = "CASE priority " + " ".join(f"WHEN '{name}' THEN {index + 1}" for index, name in enumerate(PRIORITIES)) + " END"

    def tickets_where(clause: str, parameters: tuple) -> list[dict]:
        rows = connection.execute(
            f"SELECT * FROM tickets WHERE project_key = ? AND {clause} AND closed IS NULL ORDER BY {priority_order} DESC, number", (project_key, *parameters)).fetchall()
        return [store._row_to_ticket(connection, row) for row in rows]

    iterations = []
    for iteration in list_iterations(connection, project_key):
        iteration["items"] = tickets_where("iteration_id = ?", (iteration["id"],))
        iteration["closed_items"] = connection.execute(
            "SELECT COUNT(*) FROM tickets WHERE iteration_id = ? AND closed IS NOT NULL", (iteration["id"],)).fetchone()[0]
        iterations.append(iteration)
    return {"project": project_key, "iterations": iterations, "backlog": tickets_where("iteration_id IS NULL", ())}


def roadmap(connection: sqlite3.Connection, project: Any = None) -> dict:
    project_key = store.get_project(connection, project)["key"] if project else None
    iterations = list_iterations(connection, project_key)
    clauses, parameters = ["type = 'epic'", "(start != '' OR due != '')"], []
    if project_key:
        clauses.append("project_key = ?")
        parameters.append(project_key)
    epics = []
    for row in connection.execute(f"SELECT * FROM tickets WHERE {' AND '.join(clauses)} ORDER BY COALESCE(NULLIF(start, ''), due), number", parameters):
        ticket = store._row_to_ticket(connection, row)
        ticket["progress"] = store._progress_of(connection, row["id"])
        epics.append(ticket)
    unscheduled = connection.execute(
        "SELECT COUNT(*) FROM tickets WHERE type = 'epic' AND start = '' AND due = ''" + (" AND project_key = ?" if project_key else ""),
        parameters[-1:] if project_key else []).fetchone()[0]
    dates = [date for iteration in iterations for date in (iteration["start"], iteration["end"])]
    dates += [date for epic in epics for date in (epic["start"], epic["due"]) if date]
    return {"project": project_key, "iterations": iterations, "epics": epics, "unscheduled_epics": unscheduled,
            "range": {"start": min(dates) if dates else "", "end": max(dates) if dates else ""}}


def overview(connection: sqlite3.Connection) -> dict:
    return {"organisation": get_organisation(connection), "areas": list_areas(connection), "boards": list_boards(connection),
            "projects": store.list_projects(connection)}
