from __future__ import annotations

import datetime
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

TICKET_TYPES = ("task", "bug", "feature", "epic", "story", "spike", "chore")
STATUSES = ("backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled")
CLOSED_STATUSES = ("done", "cancelled")
PRIORITIES = ("lowest", "low", "medium", "high", "critical", "blocker")
LINK_KINDS = ("blocks", "relates", "duplicates")
PROJECT_STATUSES = ("active", "archived")
ITERATION_STATES = ("planned", "active", "done")
MAX_ESTIMATE = 10000
EDITABLE_FIELDS = ("title", "body", "type", "status", "priority", "assignee", "labels", "parent_key", "due", "start", "estimate",
                   "area", "iteration")
PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
PROJECT_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TICKET_KEY_PATTERN = re.compile(r"^([A-Z][A-Z0-9]{1,9})-(\d+)$")
MAX_TITLE_CHARS = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    next_number INTEGER NOT NULL DEFAULT 1,
    lead TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    start TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL REFERENCES projects(key),
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    assignee TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '[]',
    parent_id INTEGER REFERENCES tickets(id),
    due TEXT NOT NULL DEFAULT '',
    start TEXT NOT NULL DEFAULT '',
    estimate REAL,
    area_id INTEGER REFERENCES areas(id),
    iteration_id INTEGER REFERENCES iterations(id),
    source TEXT UNIQUE,
    created REAL NOT NULL,
    updated REAL NOT NULL,
    closed REAL,
    UNIQUE (project_key, number)
);
CREATE TABLE IF NOT EXISTS organisation (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id INTEGER REFERENCES areas(id),
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES areas(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    rules TEXT NOT NULL DEFAULT '{}',
    columns TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS board_items (
    board_id INTEGER NOT NULL REFERENCES boards(id),
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    added REAL NOT NULL,
    PRIMARY KEY (board_id, ticket_id)
);
CREATE TABLE IF NOT EXISTS iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_key TEXT NOT NULL REFERENCES projects(key),
    name TEXT NOT NULL,
    starts TEXT NOT NULL,
    ends TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'planned',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    name TEXT PRIMARY KEY,
    color TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    project_key TEXT REFERENCES projects(key),
    type TEXT NOT NULL DEFAULT 'task',
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'backlog',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '[]',
    estimate REAL,
    assignee TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dashboards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    widgets TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kb_spaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'docs',
    color TEXT NOT NULL DEFAULT '#4cc2ff',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kb_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id INTEGER NOT NULL REFERENCES kb_spaces(id),
    parent_id INTEGER REFERENCES kb_pages(id),
    position INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    page_type TEXT NOT NULL DEFAULT 'article',
    meta TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'published',
    labels TEXT NOT NULL DEFAULT '[]',
    author TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    updated REAL NOT NULL,
    review_by TEXT NOT NULL DEFAULT '',
    verified_by TEXT NOT NULL DEFAULT '',
    verified_at REAL,
    views INTEGER NOT NULL DEFAULT 0,
    helpful INTEGER NOT NULL DEFAULT 0,
    unhelpful INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    source TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS kb_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES kb_pages(id),
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    author TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    UNIQUE (page_id, version)
);
CREATE TABLE IF NOT EXISTS kb_links (
    page_id INTEGER NOT NULL REFERENCES kb_pages(id),
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    PRIMARY KEY (page_id, kind, target)
);
CREATE TABLE IF NOT EXISTS kb_feedback (
    page_id INTEGER NOT NULL REFERENCES kb_pages(id),
    actor TEXT NOT NULL,
    helpful INTEGER NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    PRIMARY KEY (page_id, actor)
);
CREATE TABLE IF NOT EXISTS kb_favourites (
    actor TEXT NOT NULL,
    page_id INTEGER NOT NULL REFERENCES kb_pages(id),
    created REAL NOT NULL,
    PRIMARY KEY (actor, page_id)
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    actor TEXT NOT NULL,
    field TEXT NOT NULL,
    old TEXT NOT NULL DEFAULT '',
    new TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    other_id INTEGER NOT NULL REFERENCES tickets(id),
    kind TEXT NOT NULL,
    PRIMARY KEY (ticket_id, other_id, kind)
);
CREATE INDEX IF NOT EXISTS tickets_status ON tickets(project_key, status);
CREATE INDEX IF NOT EXISTS comments_ticket ON comments(ticket_id);
CREATE INDEX IF NOT EXISTS events_ticket ON events(ticket_id);
"""

INDEX_SCRIPT = """
CREATE INDEX IF NOT EXISTS tickets_area ON tickets(area_id);
CREATE INDEX IF NOT EXISTS tickets_iteration ON tickets(iteration_id);
CREATE INDEX IF NOT EXISTS tickets_parent ON tickets(parent_id);
CREATE INDEX IF NOT EXISTS boards_area ON boards(area_id);
CREATE INDEX IF NOT EXISTS iterations_project ON iterations(project_key);
CREATE INDEX IF NOT EXISTS kb_pages_tree ON kb_pages(space_id, parent_id, position);
CREATE INDEX IF NOT EXISTS kb_pages_updated ON kb_pages(updated);
CREATE INDEX IF NOT EXISTS kb_pages_parent ON kb_pages(parent_id, position, id);
CREATE INDEX IF NOT EXISTS kb_pages_title ON kb_pages(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS kb_links_target ON kb_links(kind, target);
CREATE INDEX IF NOT EXISTS kb_versions_page ON kb_versions(page_id, version);
"""

COLUMN_ADDITIONS = {
    "projects": {
        "lead": "TEXT NOT NULL DEFAULT ''", "status": "TEXT NOT NULL DEFAULT 'active'",
        "start": "TEXT NOT NULL DEFAULT ''", "target": "TEXT NOT NULL DEFAULT ''",
        "tags": "TEXT NOT NULL DEFAULT ''",
    },
    "areas": {"tags": "TEXT NOT NULL DEFAULT ''"},
    "kb_pages": {"translation_of": "INTEGER REFERENCES kb_pages(id)", "locale": "TEXT NOT NULL DEFAULT ''"},
    "tickets": {
        "start": "TEXT NOT NULL DEFAULT ''", "estimate": "REAL",
        "area_id": "INTEGER REFERENCES areas(id)", "iteration_id": "INTEGER REFERENCES iterations(id)",
    },
}


class LedgerError(ValueError):
    pass


class NotFound(LedgerError):
    pass


def connect(database_path: str | Path) -> sqlite3.Connection:
    if str(database_path) != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    _migrate(connection)
    connection.executescript(INDEX_SCRIPT)
    _ensure_search_index(connection)
    return connection


def _ensure_search_index(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(title, body, labels, extra, tokenize = 'porter unicode61')")
    except sqlite3.OperationalError:
        return
    connection.commit()


def _migrate(connection: sqlite3.Connection) -> None:
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(projects)")]
    if "next_number" not in columns:
        connection.execute("ALTER TABLE projects ADD COLUMN next_number INTEGER NOT NULL DEFAULT 1")
        connection.execute(
            "UPDATE projects SET next_number = (SELECT COALESCE(MAX(number), 0) + 1 FROM tickets WHERE project_key = projects.key)")
        connection.commit()
    for table, additions in COLUMN_ADDITIONS.items():
        present = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, definition in additions.items():
            if name not in present:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    connection.execute("CREATE INDEX IF NOT EXISTS kb_pages_translation ON kb_pages(translation_of)")
    connection.commit()


def parse_ticket_key(ticket_key: str) -> tuple[str, int]:
    match = TICKET_KEY_PATTERN.match(str(ticket_key).strip().upper())
    if not match:
        raise LedgerError(f"bad ticket key {ticket_key!r}, expected PROJECT-NUMBER such as APP-12")
    return match.group(1), int(match.group(2))


def _require_choice(field: str, value: str, allowed: Iterable[str]) -> str:
    cleaned = str(value).strip().lower()
    if cleaned not in allowed:
        raise LedgerError(f"{field} {value!r} is not one of {', '.join(allowed)}")
    return cleaned


def _require_text(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise LedgerError(f"{field} must be text")
    return value


def _clean_title(value: Any) -> str:
    title = " ".join(_require_text("title", value).split())
    if not title:
        raise LedgerError("title is required")
    if len(title) > MAX_TITLE_CHARS:
        raise LedgerError(f"title is {len(title)} characters, the limit is {MAX_TITLE_CHARS}; put detail in the description")
    return title


def _clean_date(field: str, value: Any) -> str:
    text = _require_text(field, value).strip()
    if text:
        try:
            datetime.date.fromisoformat(text)
        except ValueError:
            raise LedgerError(f"{field} {text!r} is not a date, use YYYY-MM-DD or leave it empty") from None
    return text


def _clean_due(value: Any) -> str:
    return _clean_date("due", value)


def _require_order(first_name: str, first: str, last_name: str, last: str) -> None:
    if first and last and first > last:
        raise LedgerError(f"{first_name} {first} is after {last_name} {last}")


def _clean_estimate(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise LedgerError("estimate must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LedgerError(f"estimate {value!r} is not a number") from None
    if not 0 <= number <= MAX_ESTIMATE:
        raise LedgerError(f"estimate must be between 0 and {MAX_ESTIMATE}")
    return round(number, 2)


def _area_path(connection: sqlite3.Connection, area_id: int | None) -> str:
    parts, seen = [], set()
    while area_id and area_id not in seen:
        seen.add(area_id)
        row = connection.execute("SELECT name, parent_id FROM areas WHERE id = ?", (area_id,)).fetchone()
        if not row:
            break
        parts.append(row["name"])
        area_id = row["parent_id"]
    return " / ".join(reversed(parts))


def _resolve_area_id(connection: sqlite3.Connection, value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise LedgerError("area must be an id or a name")
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        if not connection.execute("SELECT 1 FROM areas WHERE id = ?", (int(value),)).fetchone():
            raise NotFound(f"no area {value}")
        return int(value)
    text = str(value).strip().lower()
    for row in connection.execute("SELECT id FROM areas"):
        if _area_path(connection, row["id"]).lower() == text:
            return row["id"]
    raise NotFound(f"no area {str(value).strip()!r}")


def _resolve_iteration_id(connection: sqlite3.Connection, value: Any, project_key: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise LedgerError("iteration must be an id or a name")
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        row = connection.execute("SELECT id, project_key FROM iterations WHERE id = ?", (int(value),)).fetchone()
        if not row:
            raise NotFound(f"no iteration {value}")
        if row["project_key"] != project_key:
            raise LedgerError(f"iteration {value} belongs to project {row['project_key']}, not {project_key}")
        return row["id"]
    row = connection.execute(
        "SELECT id FROM iterations WHERE project_key = ? AND name = ? COLLATE NOCASE", (project_key, str(value).strip())).fetchone()
    if not row:
        raise NotFound(f"no iteration {str(value).strip()!r} in project {project_key}")
    return row["id"]


def _clean_labels(labels: Any) -> list[str]:
    if labels is None:
        return []
    if isinstance(labels, str):
        labels = labels.split(",")
    if not isinstance(labels, (list, tuple)) or not all(isinstance(label, str) for label in labels):
        raise LedgerError("labels must be comma separated text or a list of text")
    cleaned = sorted({str(label).strip().lower() for label in labels if str(label).strip()})
    return cleaned


def clean_project_tags(raw: Any) -> str:
    items = raw.split(",") if isinstance(raw, str) else list(raw or [])
    cleaned = set()
    for item in items:
        tag = "-".join(str(item).lower().split())
        if not tag:
            continue
        if not PROJECT_TAG_PATTERN.match(tag):
            raise LedgerError(f"bad project tag {item!r}: use letters, digits and hyphens")
        cleaned.add(tag)
    return ",".join(sorted(cleaned))


def _project_view(row: sqlite3.Row) -> dict:
    project = dict(row)
    project["tags"] = [tag for tag in project.get("tags", "").split(",") if tag]
    return project


def create_project(connection: sqlite3.Connection, key: str, name: str, description: str = "", lead: str = "",
                   start: str = "", target: str = "", tags: Any = "") -> dict:
    key = str(key).strip().upper()
    if not PROJECT_KEY_PATTERN.match(key):
        raise LedgerError("project key is 2 to 10 capital letters or digits and starts with a letter")
    if not str(name).strip():
        raise LedgerError("project name is required")
    if connection.execute("SELECT 1 FROM projects WHERE key = ?", (key,)).fetchone():
        raise LedgerError(f"project {key} already exists")
    description = _require_text("description", description)
    lead = _require_text("lead", lead).strip()
    start, target = _clean_date("start", start), _clean_date("target", target)
    _require_order("start", start, "target", target)
    tags = clean_project_tags(tags)
    connection.execute(
        "INSERT INTO projects (key, name, description, created, lead, start, target, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (key, str(name).strip(), description, time.time(), lead, start, target, tags),
    )
    connection.commit()
    return get_project(connection, key)


def update_project(connection: sqlite3.Connection, key: str, changes: dict) -> dict:
    project = get_project(connection, key)
    allowed = ("name", "description", "lead", "status", "start", "target", "tags")
    unknown = sorted(set(changes) - set(allowed))
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are {', '.join(allowed)}")
    values = {}
    for field, raw in changes.items():
        if field == "status":
            values[field] = _require_choice("status", raw, PROJECT_STATUSES)
        elif field in ("start", "target"):
            values[field] = _clean_date(field, raw)
        elif field == "tags":
            values[field] = clean_project_tags(raw)
        elif field == "name":
            values[field] = " ".join(_require_text("name", raw).split())
            if not values[field]:
                raise LedgerError("project name is required")
        else:
            values[field] = _require_text(field, raw).strip() if field == "lead" else _require_text(field, raw)
    _require_order("start", values.get("start", project["start"]), "target", values.get("target", project["target"]))
    if values:
        columns = ", ".join(f"{column} = ?" for column in values)
        connection.execute(f"UPDATE projects SET {columns} WHERE key = ?", (*values.values(), project["key"]))
        connection.commit()
    return get_project(connection, key)


def get_project(connection: sqlite3.Connection, key: str) -> dict:
    row = connection.execute("SELECT * FROM projects WHERE key = ?", (str(key).upper(),)).fetchone()
    if not row:
        raise NotFound(f"no project {key}")
    return _project_view(row)


def list_projects(connection: sqlite3.Connection, tag: str | None = None) -> list[dict]:
    wanted = clean_project_tags(tag) if tag else ""
    projects = []
    for row in connection.execute("SELECT * FROM projects ORDER BY key"):
        project = _project_view(row)
        if wanted and wanted not in project["tags"]:
            continue
        counts = connection.execute(
            "SELECT status, COUNT(*) AS n FROM tickets WHERE project_key = ? GROUP BY status", (row["key"],)
        ).fetchall()
        project["counts"] = {entry["status"]: entry["n"] for entry in counts}
        projects.append(project)
    return projects


def _ticket_key_of(row: sqlite3.Row) -> str:
    return f"{row['project_key']}-{row['number']}"


def _row_to_ticket(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    ticket = dict(row)
    ticket["key"] = _ticket_key_of(row)
    ticket["labels"] = json.loads(row["labels"])
    parent_key = None
    if row["parent_id"]:
        parent = connection.execute("SELECT project_key, number FROM tickets WHERE id = ?", (row["parent_id"],)).fetchone()
        parent_key = _ticket_key_of(parent) if parent else None
    ticket["parent_key"] = parent_key
    ticket["area"] = _area_path(connection, row["area_id"])
    iteration = connection.execute("SELECT name FROM iterations WHERE id = ?", (row["iteration_id"],)).fetchone() if row["iteration_id"] else None
    ticket["iteration"] = iteration["name"] if iteration else ""
    return ticket


def _find_row(connection: sqlite3.Connection, ticket_key: str) -> sqlite3.Row:
    project_key, number = parse_ticket_key(ticket_key)
    row = connection.execute(
        "SELECT * FROM tickets WHERE project_key = ? AND number = ?", (project_key, number)
    ).fetchone()
    if not row:
        raise NotFound(f"no ticket {project_key}-{number}")
    return row


def _resolve_parent_id(connection: sqlite3.Connection, parent_key: str | None, own_id: int | None) -> int | None:
    if not parent_key:
        return None
    parent = _find_row(connection, parent_key)
    if own_id is not None and parent["id"] == own_id:
        raise LedgerError("a ticket cannot be its own parent")
    cursor = parent
    while cursor["parent_id"]:
        if own_id is not None and cursor["parent_id"] == own_id:
            raise LedgerError("that parent would make a cycle")
        cursor = connection.execute("SELECT * FROM tickets WHERE id = ?", (cursor["parent_id"],)).fetchone()
    return parent["id"]


def create_ticket(
    connection: sqlite3.Connection,
    project_key: str,
    title: str,
    body: str = "",
    type: str = "task",
    status: str = "backlog",
    priority: str = "medium",
    assignee: str = "",
    labels: Any = None,
    parent_key: str | None = None,
    due: str = "",
    source: str | None = None,
    actor: str = "system",
    start: str = "",
    estimate: Any = None,
    area: Any = None,
    iteration: Any = None,
) -> dict:
    project = get_project(connection, project_key)
    title = _clean_title(title)
    body = _require_text("body", body)
    due = _clean_due(due)
    start = _clean_date("start", start)
    _require_order("start", start, "due", due)
    estimate = _clean_estimate(estimate)
    area_id = _resolve_area_id(connection, area)
    iteration_id = _resolve_iteration_id(connection, iteration, project["key"])
    type = _require_choice("type", type, TICKET_TYPES)
    status = _require_choice("status", status, STATUSES)
    priority = _require_choice("priority", priority, PRIORITIES)
    parent_id = _resolve_parent_id(connection, parent_key, None)
    number = project["next_number"]
    connection.execute("UPDATE projects SET next_number = ? WHERE key = ?", (number + 1, project["key"]))
    now = time.time()
    closed = now if status in CLOSED_STATUSES else None
    if source is not None:
        existing = find_by_source(connection, source)
        if existing:
            raise LedgerError(f"source {source!r} is already ticket {existing['key']}")
    cursor = connection.execute(
        "INSERT INTO tickets (project_key, number, title, body, type, status, priority, assignee, labels, parent_id, due, source,"
        " created, updated, closed, start, estimate, area_id, iteration_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project["key"], number, title, body, type, status, priority, _require_text("assignee", assignee).strip(),
         json.dumps(_clean_labels(labels), ensure_ascii=False), parent_id, due, source, now, now, closed,
         start, estimate, area_id, iteration_id),
    )
    connection.execute(
        "INSERT INTO events (ticket_id, actor, field, old, new, created) VALUES (?, ?, 'created', '', ?, ?)",
        (cursor.lastrowid, actor, title, now),
    )
    connection.commit()
    return get_ticket(connection, f"{project['key']}-{number}")


def get_ticket(connection: sqlite3.Connection, ticket_key: str) -> dict:
    row = _find_row(connection, ticket_key)
    ticket = _row_to_ticket(connection, row)
    ticket["comments"] = [dict(entry) for entry in connection.execute(
        "SELECT id, author, body, created FROM comments WHERE ticket_id = ? ORDER BY id", (row["id"],))]
    ticket["children"] = [
        {"key": _ticket_key_of(child), "title": child["title"], "status": child["status"]}
        for child in connection.execute("SELECT * FROM tickets WHERE parent_id = ? ORDER BY number", (row["id"],))
    ]
    ticket["links"] = _links_of(connection, row["id"])
    ticket["progress"] = _progress_of(connection, row["id"])
    return ticket


def _progress_of(connection: sqlite3.Connection, ticket_id: int) -> dict:
    rows = connection.execute(
        "WITH RECURSIVE sub(id) AS (SELECT id FROM tickets WHERE parent_id = ? UNION SELECT t.id FROM tickets t JOIN sub ON t.parent_id = sub.id)"
        " SELECT status, estimate FROM tickets WHERE id IN (SELECT id FROM sub) AND status != 'cancelled'", (ticket_id,)).fetchall()
    done = [row for row in rows if row["status"] == "done"]
    return {"total": len(rows), "done": len(done), "points": sum(row["estimate"] or 0 for row in rows),
            "points_done": sum(row["estimate"] or 0 for row in done)}


def ticket_tree(connection: sqlite3.Connection, ticket_key: str, depth: int = 8) -> dict:
    row = _find_row(connection, ticket_key)

    def build(entry: sqlite3.Row, remaining: int) -> dict:
        children = []
        if remaining:
            children = [build(child, remaining - 1) for child in connection.execute(
                "SELECT * FROM tickets WHERE parent_id = ? ORDER BY number", (entry["id"],))]
        return {"key": _ticket_key_of(entry), "title": entry["title"], "type": entry["type"], "status": entry["status"],
                "estimate": entry["estimate"], "children": children}

    return build(row, depth)


def _links_of(connection: sqlite3.Connection, ticket_id: int) -> list[dict]:
    links = []
    for entry in connection.execute(
        "SELECT l.kind, t.project_key, t.number, t.title, t.status FROM links l JOIN tickets t ON t.id = l.other_id"
        " WHERE l.ticket_id = ?", (ticket_id,)):
        links.append({"kind": entry["kind"], "key": f"{entry['project_key']}-{entry['number']}",
                      "title": entry["title"], "status": entry["status"], "direction": "out"})
    for entry in connection.execute(
        "SELECT l.kind, t.project_key, t.number, t.title, t.status FROM links l JOIN tickets t ON t.id = l.ticket_id"
        " WHERE l.other_id = ?", (ticket_id,)):
        links.append({"kind": entry["kind"], "key": f"{entry['project_key']}-{entry['number']}",
                      "title": entry["title"], "status": entry["status"], "direction": "in"})
    return links


def update_ticket(connection: sqlite3.Connection, ticket_key: str, changes: dict, actor: str = "system") -> dict:
    row = _find_row(connection, ticket_key)
    unknown = sorted(set(changes) - set(EDITABLE_FIELDS))
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are {', '.join(EDITABLE_FIELDS)}")
    current = _row_to_ticket(connection, row)
    assignments: dict[str, Any] = {}
    event_rows: list[tuple[str, str, str]] = []
    for field, raw_value in changes.items():
        if field == "type":
            value = _require_choice("type", raw_value, TICKET_TYPES)
        elif field == "status":
            value = _require_choice("status", raw_value, STATUSES)
        elif field == "priority":
            value = _require_choice("priority", raw_value, PRIORITIES)
        elif field == "labels":
            value = _clean_labels(raw_value)
        elif field == "title":
            value = _clean_title(raw_value)
        elif field == "due":
            value = _clean_due(raw_value)
        elif field == "body":
            value = _require_text("body", raw_value)
        elif field == "assignee":
            value = _require_text("assignee", raw_value).strip()
        elif field == "parent_key":
            value = (str(raw_value).strip().upper() or None) if raw_value else None
            assignments["parent_id"] = _resolve_parent_id(connection, value, row["id"])
        elif field == "start":
            value = _clean_date("start", raw_value)
        elif field == "estimate":
            estimate = _clean_estimate(raw_value)
            if estimate != row["estimate"]:
                assignments["estimate"] = estimate
                event_rows.append(("estimate", "" if row["estimate"] is None else f"{row['estimate']:g}",
                                   "" if estimate is None else f"{estimate:g}"))
            continue
        elif field == "area":
            area_id = _resolve_area_id(connection, raw_value)
            if area_id != row["area_id"]:
                assignments["area_id"] = area_id
                event_rows.append(("area", current["area"], _area_path(connection, area_id)))
            continue
        elif field == "iteration":
            iteration_id = _resolve_iteration_id(connection, raw_value, row["project_key"])
            if iteration_id != row["iteration_id"]:
                assignments["iteration_id"] = iteration_id
                name = connection.execute("SELECT name FROM iterations WHERE id = ?", (iteration_id,)).fetchone() if iteration_id else None
                event_rows.append(("iteration", current["iteration"], name["name"] if name else ""))
            continue
        else:
            raise LedgerError(f"cannot edit {field}")
        if value == current[field]:
            continue
        if field != "parent_key":
            assignments[field] = json.dumps(value, ensure_ascii=False) if field == "labels" else value
        old_text = json.dumps(current[field], ensure_ascii=False) if field == "labels" else str(current[field] or "")
        new_text = json.dumps(value, ensure_ascii=False) if field == "labels" else str(value or "")
        event_rows.append((field, old_text, new_text))
    _require_order("start", assignments.get("start", row["start"]), "due", assignments.get("due", row["due"]))
    if not event_rows:
        return get_ticket(connection, ticket_key)
    now = time.time()
    if "status" in assignments:
        assignments["closed"] = now if assignments["status"] in CLOSED_STATUSES else None
    assignments["updated"] = now
    columns = ", ".join(f"{column} = ?" for column in assignments)
    connection.execute(f"UPDATE tickets SET {columns} WHERE id = ?", (*assignments.values(), row["id"]))
    for field, old_text, new_text in event_rows:
        connection.execute(
            "INSERT INTO events (ticket_id, actor, field, old, new, created) VALUES (?, ?, ?, ?, ?, ?)",
            (row["id"], actor, field, old_text, new_text, now),
        )
    connection.commit()
    return get_ticket(connection, ticket_key)


def delete_ticket(connection: sqlite3.Connection, ticket_key: str) -> None:
    row = _find_row(connection, ticket_key)
    if connection.execute("SELECT 1 FROM tickets WHERE parent_id = ?", (row["id"],)).fetchone():
        raise LedgerError("ticket has sub-tickets; move or delete them first")
    for table, column in (("comments", "ticket_id"), ("events", "ticket_id"), ("links", "ticket_id"), ("links", "other_id"),
                          ("board_items", "ticket_id")):
        connection.execute(f"DELETE FROM {table} WHERE {column} = ?", (row["id"],))
    connection.execute("DELETE FROM tickets WHERE id = ?", (row["id"],))
    connection.commit()


def add_comment(connection: sqlite3.Connection, ticket_key: str, author: str, body: str) -> dict:
    row = _find_row(connection, ticket_key)
    if not _require_text("comment body", body).strip():
        raise LedgerError("comment body is required")
    now = time.time()
    connection.execute(
        "INSERT INTO comments (ticket_id, author, body, created) VALUES (?, ?, ?, ?)",
        (row["id"], str(author).strip() or "anonymous", body, now),
    )
    connection.execute("UPDATE tickets SET updated = ? WHERE id = ?", (now, row["id"]))
    connection.commit()
    return get_ticket(connection, ticket_key)


def add_link(connection: sqlite3.Connection, ticket_key: str, other_key: str, kind: str) -> dict:
    kind = _require_choice("link kind", kind, LINK_KINDS)
    row, other = _find_row(connection, ticket_key), _find_row(connection, other_key)
    if row["id"] == other["id"]:
        raise LedgerError("a ticket cannot link to itself")
    connection.execute("INSERT OR IGNORE INTO links (ticket_id, other_id, kind) VALUES (?, ?, ?)", (row["id"], other["id"], kind))
    connection.commit()
    return get_ticket(connection, ticket_key)


def ticket_events(connection: sqlite3.Connection, ticket_key: str) -> list[dict]:
    row = _find_row(connection, ticket_key)
    return [dict(entry) for entry in connection.execute(
        "SELECT actor, field, old, new, created FROM events WHERE ticket_id = ? ORDER BY id", (row["id"],))]


LIKE_ESCAPE = "!"


def _escape_like(text: str) -> str:
    return text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")


def _filter_clause(project_key, status, assignee, type, priority, label, query, include_closed, source=None, area=None,
                   iteration=None, connection=None) -> tuple[str, list]:
    clauses, parameters = [], []
    if project_key:
        clauses.append("project_key = ?")
        parameters.append(project_key.upper())
    for column, value, allowed in (("status", status, STATUSES), ("type", type, TICKET_TYPES), ("priority", priority, PRIORITIES)):
        if value:
            clauses.append(f"{column} = ?")
            parameters.append(_require_choice(column, value, allowed))
    if source:
        clauses.append("source = ?")
        parameters.append(source)
    if area not in (None, ""):
        area_id = _resolve_area_id(connection, area)
        clauses.append("area_id IN (WITH RECURSIVE sub(id) AS (SELECT id FROM areas WHERE id = ? UNION SELECT a.id FROM areas a JOIN sub ON a.parent_id = sub.id) SELECT id FROM sub)")
        parameters.append(area_id)
    if iteration not in (None, ""):
        if not str(iteration).strip().isdigit():
            raise LedgerError("iteration filter is an iteration id")
        clauses.append("iteration_id = ?")
        parameters.append(int(iteration))
    if assignee:
        clauses.append("assignee = ? COLLATE NOCASE")
        parameters.append(assignee)
    if not include_closed:
        clauses.append("closed IS NULL")
    if query:
        like = f"%{_escape_like(query)}%"
        clauses.append(f"(title LIKE ? ESCAPE '{LIKE_ESCAPE}' OR body LIKE ? ESCAPE '{LIKE_ESCAPE}' OR (project_key || '-' || number) LIKE ? ESCAPE '{LIKE_ESCAPE}')")
        parameters.extend([like, like, like])
    if label:
        clauses.append("EXISTS (SELECT 1 FROM json_each(tickets.labels) WHERE json_each.value = ?)")
        parameters.append(label.strip().lower())
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), parameters


def _check_project_exists(connection: sqlite3.Connection, project_key: str | None) -> None:
    if project_key:
        get_project(connection, project_key)


def count_tickets(connection: sqlite3.Connection, project_key=None, status=None, assignee=None, type=None, priority=None,
                  label=None, query=None, include_closed=True, source=None, area=None, iteration=None) -> int:
    _check_project_exists(connection, project_key)
    where, parameters = _filter_clause(project_key, status, assignee, type, priority, label, query, include_closed, source,
                                       area, iteration, connection)
    return connection.execute(f"SELECT COUNT(*) FROM tickets {where}", parameters).fetchone()[0]


def list_tickets(
    connection: sqlite3.Connection,
    project_key: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    type: str | None = None,
    priority: str | None = None,
    label: str | None = None,
    query: str | None = None,
    include_closed: bool = True,
    limit: int = 500,
    source: str | None = None,
    area: Any = None,
    iteration: Any = None,
) -> list[dict]:
    _check_project_exists(connection, project_key)
    where, parameters = _filter_clause(project_key, status, assignee, type, priority, label, query, include_closed, source,
                                       area, iteration, connection)
    priority_order = "CASE priority " + " ".join(f"WHEN '{name}' THEN {index + 1}" for index, name in enumerate(PRIORITIES)) + " END"
    rows = connection.execute(
        f"SELECT * FROM tickets {where} ORDER BY {priority_order} DESC, updated DESC LIMIT ?", (*parameters, limit)
    ).fetchall()
    return [_row_to_ticket(connection, row) for row in rows]


def board(connection: sqlite3.Connection, project_key: str | None = None, hide_empty_closed: bool = False) -> dict:
    columns = {status: [] for status in STATUSES}
    for ticket in list_tickets(connection, project_key=project_key):
        columns[ticket["status"]].append(ticket)
    if hide_empty_closed:
        columns = {status: items for status, items in columns.items() if items or status not in CLOSED_STATUSES}
    return {"statuses": list(columns), "columns": columns}


def stats(connection: sqlite3.Connection, project_key: str | None = None) -> dict:
    where, parameters = ("WHERE project_key = ?", (project_key.upper(),)) if project_key else ("", ())
    def grouped(column: str) -> dict:
        return {entry[0]: entry[1] for entry in connection.execute(
            f"SELECT {column}, COUNT(*) FROM tickets {where} GROUP BY {column}", parameters)}
    open_count = connection.execute(
        f"SELECT COUNT(*) FROM tickets {where + ' AND' if where else 'WHERE'} closed IS NULL", parameters).fetchone()[0]
    by_assignee = grouped("assignee")
    unassigned = by_assignee.pop("", 0)
    return {"open": open_count, "by_status": grouped("status"), "by_type": grouped("type"),
            "by_priority": grouped("priority"), "by_assignee": by_assignee, "unassigned": unassigned}


def find_by_source(connection: sqlite3.Connection, source: str) -> dict | None:
    row = connection.execute("SELECT * FROM tickets WHERE source = ?", (source,)).fetchone()
    return _row_to_ticket(connection, row) if row else None
