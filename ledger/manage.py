from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any

from . import store
from .organise import _clean_name
from .store import PRIORITIES, STATUSES, TICKET_TYPES, LedgerError, NotFound, _require_choice, _require_text

TAG_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_TAG_CHARS = 40
TEMPLATE_FIELDS = ("name", "description", "project", "type", "priority", "status", "title", "body", "labels", "estimate", "assignee")
DEFAULT_TEMPLATES = (
    {"name": "Bug report", "type": "bug", "priority": "high", "labels": ["bug"], "description": "Something that worked and no longer does",
     "body": "What happened:\n\nWhat should have happened:\n\nSteps to reproduce:\n1. \n2. \n\nVersion and environment:\n"},
    {"name": "Feature request", "type": "feature", "priority": "medium", "description": "A new capability and why it is needed",
     "body": "Problem to solve:\n\nProposed behaviour:\n\nAlternatives considered:\n"},
    {"name": "Task", "type": "task", "priority": "medium", "description": "A small piece of planned work",
     "body": "Goal:\n\nDone when:\n"},
    {"name": "Spike", "type": "spike", "priority": "low", "estimate": 2, "description": "A time-boxed investigation",
     "body": "Question to answer:\n\nTime box:\n\nOutcome:\n"},
    {"name": "Chore", "type": "chore", "priority": "low", "description": "Maintenance with no user-visible change",
     "body": "What needs doing:\n"},
)


def _clean_tag_name(value: Any) -> str:
    name = " ".join(_require_text("name", value).split()).lower()
    if not name:
        raise LedgerError("tag name is required")
    if "," in name:
        raise LedgerError("a tag name cannot contain a comma")
    if len(name) > MAX_TAG_CHARS:
        raise LedgerError(f"tag name is {len(name)} characters, the limit is {MAX_TAG_CHARS}")
    return name


def _clean_color(value: Any) -> str:
    color = _require_text("color", value).strip()
    if color and not TAG_COLOR_PATTERN.match(color):
        raise LedgerError(f"color {color!r} is not a hex colour like #4cc2ff; leave it empty for an automatic colour")
    return color.lower()


def _boards_using(connection: sqlite3.Connection, name: str) -> list[sqlite3.Row]:
    return [row for row in connection.execute("SELECT id, rules FROM boards") if name in json.loads(row["rules"]).get("labels", [])]


def _rewrite_label(connection: sqlite3.Connection, old: str, new: str | None, actor: str) -> int:
    changed = 0
    now = time.time()
    rows = connection.execute(
        "SELECT DISTINCT tickets.id, tickets.labels FROM tickets, json_each(tickets.labels) WHERE json_each.value = ?", (old,)).fetchall()
    for row in rows:
        before = json.loads(row["labels"])
        after = sorted({(new if label == old else label) for label in before} - {None})
        if after == before:
            continue
        connection.execute("UPDATE tickets SET labels = ?, updated = ? WHERE id = ?", (json.dumps(after, ensure_ascii=False), now, row["id"]))
        connection.execute("INSERT INTO events (ticket_id, actor, field, old, new, created) VALUES (?, ?, 'labels', ?, ?, ?)",
                           (row["id"], actor, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), now))
        changed += 1
    for board in _boards_using(connection, old):
        rules = json.loads(board["rules"])
        replaced = [new if label == old else label for label in rules["labels"]]
        rules["labels"] = list(dict.fromkeys(label for label in replaced if label))
        if not rules["labels"]:
            del rules["labels"]
        connection.execute("UPDATE boards SET rules = ? WHERE id = ?", (json.dumps(rules), board["id"]))
    return changed


def list_tags(connection: sqlite3.Connection) -> list[dict]:
    tags = {row["name"]: {"name": row["name"], "color": row["color"], "description": row["description"], "registered": True}
            for row in connection.execute("SELECT * FROM tags")}
    counts = {row[0]: row[1] for row in connection.execute(
        "SELECT json_each.value, COUNT(*) FROM tickets, json_each(tickets.labels) GROUP BY json_each.value")}
    open_counts = {row[0]: row[1] for row in connection.execute(
        "SELECT json_each.value, COUNT(*) FROM tickets, json_each(tickets.labels) WHERE tickets.closed IS NULL GROUP BY json_each.value")}
    for name in counts:
        tags.setdefault(name, {"name": name, "color": "", "description": "", "registered": False})
    board_counts: dict[str, int] = {}
    for row in connection.execute("SELECT rules FROM boards"):
        for label in json.loads(row["rules"]).get("labels", []):
            board_counts[label] = board_counts.get(label, 0) + 1
    for name, tag in tags.items():
        tag["tickets"] = counts.get(name, 0)
        tag["open_tickets"] = open_counts.get(name, 0)
        tag["boards"] = board_counts.get(name, 0)
    return sorted(tags.values(), key=lambda tag: tag["name"])


def get_tag(connection: sqlite3.Connection, name: Any) -> dict:
    wanted = _clean_tag_name(name)
    for tag in list_tags(connection):
        if tag["name"] == wanted:
            return tag
    raise NotFound(f"no tag {wanted!r}")


def create_tag(connection: sqlite3.Connection, name: Any, color: Any = "", description: Any = "") -> dict:
    name = _clean_tag_name(name)
    if connection.execute("SELECT 1 FROM tags WHERE name = ?", (name,)).fetchone():
        raise LedgerError(f"tag {name!r} already exists")
    connection.execute("INSERT INTO tags (name, color, description, created) VALUES (?, ?, ?, ?)",
                       (name, _clean_color(color), _require_text("description", description), time.time()))
    connection.commit()
    return get_tag(connection, name)


def update_tag(connection: sqlite3.Connection, name: Any, changes: dict, actor: str = "tags") -> dict:
    current = get_tag(connection, name)
    unknown = sorted(set(changes) - {"name", "color", "description"})
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are name, color, description")
    color = _clean_color(changes["color"]) if "color" in changes else current["color"]
    description = _require_text("description", changes["description"]) if "description" in changes else current["description"]
    target = _clean_tag_name(changes["name"]) if "name" in changes else current["name"]
    if target != current["name"]:
        if any(tag["name"] == target for tag in list_tags(connection)):
            raise LedgerError(f"tag {target!r} already exists; merge into it instead")
        _rewrite_label(connection, current["name"], target, actor)
        connection.execute("DELETE FROM tags WHERE name = ?", (current["name"],))
    connection.execute(
        "INSERT INTO tags (name, color, description, created) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(name) DO UPDATE SET color = excluded.color, description = excluded.description",
        (target, color, description, time.time()))
    connection.commit()
    return get_tag(connection, target)


def merge_tags(connection: sqlite3.Connection, source: Any, into: Any, actor: str = "tags") -> dict:
    source, target = _clean_tag_name(source), _clean_tag_name(into)
    if source == target:
        raise LedgerError("a tag cannot be merged into itself")
    get_tag(connection, source)
    _rewrite_label(connection, source, target, actor)
    connection.execute("DELETE FROM tags WHERE name = ?", (source,))
    connection.execute("INSERT OR IGNORE INTO tags (name, color, description, created) VALUES (?, '', '', ?)", (target, time.time()))
    connection.commit()
    return get_tag(connection, target)


def delete_tag(connection: sqlite3.Connection, name: Any, actor: str = "tags") -> dict:
    tag = get_tag(connection, name)
    changed = _rewrite_label(connection, tag["name"], None, actor)
    connection.execute("DELETE FROM tags WHERE name = ?", (tag["name"],))
    connection.commit()
    return {"deleted": tag["name"], "tickets_changed": changed, "boards_changed": tag["boards"]}


def _template_dict(row: sqlite3.Row) -> dict:
    template = dict(row)
    template["labels"] = json.loads(row["labels"])
    template["project"] = template.pop("project_key") or ""
    return template


def _template_row(connection: sqlite3.Connection, template_id: Any) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM ticket_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise NotFound(f"no template {template_id}")
    return row


def get_template(connection: sqlite3.Connection, template_id: Any) -> dict:
    return _template_dict(_template_row(connection, template_id))


def list_templates(connection: sqlite3.Connection, project: Any = None) -> list[dict]:
    if project:
        key = store.get_project(connection, project)["key"]
        rows = connection.execute(
            "SELECT * FROM ticket_templates WHERE project_key IS NULL OR project_key = ? ORDER BY name COLLATE NOCASE", (key,))
    else:
        rows = connection.execute("SELECT * FROM ticket_templates ORDER BY name COLLATE NOCASE")
    return [_template_dict(row) for row in rows]


def _template_values(connection: sqlite3.Connection, fields: dict, base: dict) -> dict:
    unknown = sorted(set(fields) - set(base))
    if unknown:
        raise LedgerError(f"unknown template field {', '.join(unknown)}; fields are {', '.join(TEMPLATE_FIELDS)}")
    values = {**base, **fields}
    values["name"] = _clean_name("name", values["name"])
    values["description"] = _require_text("description", values["description"])
    values["project"] = store.get_project(connection, values["project"])["key"] if values["project"] else ""
    values["type"] = _require_choice("type", values["type"], TICKET_TYPES)
    values["priority"] = _require_choice("priority", values["priority"], PRIORITIES)
    values["status"] = _require_choice("status", values["status"], STATUSES)
    values["title"] = " ".join(_require_text("title", values["title"]).split())
    values["body"] = _require_text("body", values["body"])
    values["labels"] = store._clean_labels(values["labels"])
    values["estimate"] = store._clean_estimate(values["estimate"])
    from . import people
    values["assignee"] = people.resolve(connection, values["assignee"])
    return values


BLANK_TEMPLATE = {"name": "", "description": "", "project": "", "type": "task", "priority": "medium", "status": "backlog", "title": "",
                  "body": "", "labels": [], "estimate": None, "assignee": ""}


def _store_template(connection: sqlite3.Connection, values: dict, template_id: int | None) -> int:
    parameters = (values["name"], values["description"], values["project"] or None, values["type"], values["priority"], values["status"],
                  values["title"], values["body"], json.dumps(values["labels"], ensure_ascii=False), values["estimate"], values["assignee"])
    duplicate = connection.execute(
        "SELECT id FROM ticket_templates WHERE name = ? COLLATE NOCASE AND project_key IS ?", (values["name"], values["project"] or None)).fetchone()
    if duplicate and duplicate["id"] != template_id:
        raise LedgerError(f"there is already a template named {values['name']!r} here")
    if template_id is None:
        cursor = connection.execute(
            "INSERT INTO ticket_templates (name, description, project_key, type, priority, status, title, body, labels, estimate, assignee,"
            " created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*parameters, time.time()))
        template_id = cursor.lastrowid
    else:
        connection.execute(
            "UPDATE ticket_templates SET name = ?, description = ?, project_key = ?, type = ?, priority = ?, status = ?, title = ?, body = ?,"
            " labels = ?, estimate = ?, assignee = ? WHERE id = ?", (*parameters, template_id))
    connection.commit()
    return template_id


def create_template(connection: sqlite3.Connection, **fields: Any) -> dict:
    values = _template_values(connection, fields, BLANK_TEMPLATE)
    return get_template(connection, _store_template(connection, values, None))


def update_template(connection: sqlite3.Connection, template_id: Any, changes: dict) -> dict:
    current = get_template(connection, template_id)
    base = {key: current[key] for key in TEMPLATE_FIELDS}
    values = _template_values(connection, changes, base)
    return get_template(connection, _store_template(connection, values, current["id"]))


def delete_template(connection: sqlite3.Connection, template_id: Any) -> None:
    row = _template_row(connection, template_id)
    connection.execute("DELETE FROM ticket_templates WHERE id = ?", (row["id"],))
    connection.commit()


def apply_template(connection: sqlite3.Connection, template_id: Any, payload: dict) -> dict:
    template = get_template(connection, template_id)
    project = payload.get("project") or template["project"]
    if not project:
        raise LedgerError("give a project for this ticket; the template is not tied to one")
    if template["project"] and template["project"] != str(project).upper():
        raise LedgerError(f"template {template['name']!r} belongs to project {template['project']}")
    merged = {"project": project, "title": template["title"], "body": template["body"], "type": template["type"],
              "priority": template["priority"], "status": template["status"], "labels": template["labels"],
              "estimate": template["estimate"], "assignee": template["assignee"]}
    for key, value in payload.items():
        if key != "template" and value not in (None, "", []):
            merged[key] = value
    return merged


def seed_default_templates(connection: sqlite3.Connection) -> list[dict]:
    created = []
    for template in DEFAULT_TEMPLATES:
        exists = connection.execute(
            "SELECT 1 FROM ticket_templates WHERE name = ? COLLATE NOCASE AND project_key IS NULL", (template["name"],)).fetchone()
        if not exists:
            created.append(create_template(connection, **template))
    return created
