from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from . import dashmodules, modulekit, organise, store
from .store import LedgerError, NotFound, PRIORITIES, STATUSES, TICKET_TYPES, _require_choice, _require_text

COMMON_WIDGET_KEYS = ("id", "title", "kind", "size", "filters")
DROPPED_WIDGET_KEYS = ("days", "limit")
MAX_WIDGETS = 24

log = logging.getLogger("ledger.modules")


def _clean_filters(connection: sqlite3.Connection, filters: Any, allowed: tuple = modulekit.FILTER_KEYS, kind: str = "") -> dict:
    if filters is None or filters == "":
        return {}
    if not isinstance(filters, dict):
        raise LedgerError("filters must be an object")
    unknown = sorted(set(filters) - set(modulekit.FILTER_KEYS))
    if unknown:
        raise LedgerError(f"unknown filter {', '.join(unknown)}; filters are {', '.join(modulekit.FILTER_KEYS)}")
    cleaned: dict[str, Any] = {}
    for key, value in filters.items():
        if value in (None, "", False):
            continue
        if key not in allowed:
            raise LedgerError(f"the {kind} widget does not use the {key} filter; it uses {', '.join(allowed) or 'no filters'}")
        if key == "open":
            cleaned[key] = True
        elif key == "project":
            cleaned[key] = store.get_project(connection, _require_text(key, value))["key"]
        elif key == "type":
            cleaned[key] = _require_choice(key, value, TICKET_TYPES)
        elif key == "status":
            cleaned[key] = _require_choice(key, value, STATUSES)
        elif key == "priority":
            cleaned[key] = _require_choice(key, value, PRIORITIES)
        elif key in ("area", "iteration"):
            if isinstance(value, bool) or not (isinstance(value, int) or str(value).strip().isdigit() or key == "area"):
                raise LedgerError(f"the {key} filter is an id")
            cleaned[key] = value if key == "area" else int(value)
        else:
            cleaned[key] = _require_text(key, value).strip()
    return cleaned


def clean_widget(connection: sqlite3.Connection, widget: Any) -> dict:
    if not isinstance(widget, dict):
        raise LedgerError("a widget must be an object")
    module = dashmodules.current().get(widget.get("kind", ""))
    settings_names = [setting["name"] for setting in module.settings]
    allowed_keys = (*COMMON_WIDGET_KEYS, *settings_names)
    unknown = sorted(set(widget) - set(allowed_keys) - set(DROPPED_WIDGET_KEYS))
    if unknown:
        raise LedgerError(f"unknown widget field {', '.join(unknown)}; fields are {', '.join(allowed_keys)}")
    title = " ".join(_require_text("title", widget.get("title") or module.title).split())
    if not title:
        raise LedgerError("title is required")
    given_size = widget.get("size")
    cleaned: dict[str, Any] = {
        "kind": module.id, "title": title[:80],
        "size": modulekit.whole_number("size", module.size if given_size in (None, "") else given_size, 1, dashmodules.MAX_SIZE),
        "filters": _clean_filters(connection, widget.get("filters"), module.filters, module.id),
    }
    if widget.get("id"):
        cleaned["id"] = _require_text("id", widget["id"]).strip()
    cleaned.update(dashmodules.clean_settings(module, widget))
    return cleaned


def evaluate(connection: sqlite3.Connection, widget: Any, now: float | None = None) -> dict:
    config = clean_widget(connection, widget)
    module = dashmodules.current().get(config["kind"])
    settings = {key: value for key, value in config.items() if key not in COMMON_WIDGET_KEYS}
    result = module.data(connection, settings, config["filters"], time.time() if now is None else now)
    return {"widget": config, "data": result}


def _dashboard_dict(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "name": row["name"], "description": row["description"], "widgets": json.loads(row["widgets"]), "created": row["created"]}


def _dashboard_row(connection: sqlite3.Connection, dashboard_id: Any) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM dashboards WHERE id = ?", (dashboard_id,)).fetchone()
    if not row:
        raise NotFound(f"no dashboard {dashboard_id}")
    return row


def _clean_widgets(connection: sqlite3.Connection, widgets: Any) -> list[dict]:
    if widgets is None:
        return []
    if not isinstance(widgets, list):
        raise LedgerError("widgets must be a list")
    if len(widgets) > MAX_WIDGETS:
        raise LedgerError(f"a dashboard holds at most {MAX_WIDGETS} widgets")
    cleaned, used = [], set()
    for widget in widgets:
        item = clean_widget(connection, widget)
        identifier = item.pop("id", "")
        while not identifier or identifier in used:
            identifier = f"w{len(used) + 1}"
            while identifier in used:
                identifier += "x"
        used.add(identifier)
        cleaned.append({"id": identifier, **item})
    return cleaned


def create_dashboard(connection: sqlite3.Connection, name: Any, description: Any = "", widgets: Any = None) -> dict:
    name = organise._clean_name("name", name)
    for row in connection.execute("SELECT name FROM dashboards"):
        if row["name"].lower() == name.lower():
            raise LedgerError(f"there is already a dashboard named {name!r}")
    cursor = connection.execute("INSERT INTO dashboards (name, description, widgets, created) VALUES (?, ?, ?, ?)",
                                (name, _require_text("description", description), json.dumps(_clean_widgets(connection, widgets)), time.time()))
    connection.commit()
    return get_dashboard(connection, cursor.lastrowid)


def get_dashboard(connection: sqlite3.Connection, dashboard_id: Any) -> dict:
    return _dashboard_dict(_dashboard_row(connection, dashboard_id))


def list_dashboards(connection: sqlite3.Connection) -> list[dict]:
    return [_dashboard_dict(row) for row in connection.execute("SELECT * FROM dashboards ORDER BY id")]


def update_dashboard(connection: sqlite3.Connection, dashboard_id: Any, changes: dict) -> dict:
    row = _dashboard_row(connection, dashboard_id)
    unknown = sorted(set(changes) - {"name", "description", "widgets"})
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are name, description, widgets")
    name = organise._clean_name("name", changes["name"]) if "name" in changes else row["name"]
    description = _require_text("description", changes["description"]) if "description" in changes else row["description"]
    widgets = json.dumps(_clean_widgets(connection, changes["widgets"])) if "widgets" in changes else row["widgets"]
    for other in connection.execute("SELECT id, name FROM dashboards"):
        if other["id"] != row["id"] and other["name"].lower() == name.lower():
            raise LedgerError(f"there is already a dashboard named {name!r}")
    connection.execute("UPDATE dashboards SET name = ?, description = ?, widgets = ? WHERE id = ?", (name, description, widgets, row["id"]))
    connection.commit()
    return get_dashboard(connection, row["id"])


def delete_dashboard(connection: sqlite3.Connection, dashboard_id: Any) -> None:
    row = _dashboard_row(connection, dashboard_id)
    connection.execute("DELETE FROM dashboards WHERE id = ?", (row["id"],))
    connection.commit()


def dashboard_data(connection: sqlite3.Connection, dashboard_id: Any, now: float | None = None) -> dict:
    dashboard = get_dashboard(connection, dashboard_id)
    results = {}
    for widget in dashboard["widgets"]:
        try:
            results[widget["id"]] = evaluate(connection, widget, now)["data"]
        except LedgerError as error:
            results[widget["id"]] = {"error": str(error)}
        except Exception as error:
            log.exception("dashboard module %s failed", widget.get("kind"))
            results[widget["id"]] = {"error": f"the {widget.get('kind')} module failed: {type(error).__name__}: {error}"}
    return {"dashboard": dashboard, "results": results}


DEFAULT_DASHBOARDS = (
    {"name": "Overview", "description": "Where the work stands today", "widgets": [
        {"kind": "count", "title": "Open tickets", "filters": {"open": True}},
        {"kind": "count", "title": "Created, last 7 days", "measure": "created", "days": 7},
        {"kind": "count", "title": "Closed, last 7 days", "measure": "closed", "days": 7},
        {"kind": "overdue", "title": "Overdue"},
        {"kind": "trend", "title": "Created and closed, 30 days", "days": 30},
        {"kind": "group", "title": "By status", "group_by": "status", "chart": "donut"},
        {"kind": "group", "title": "Open by priority", "group_by": "priority", "filters": {"open": True}},
        {"kind": "group", "title": "Open by type", "group_by": "type", "filters": {"open": True}},
        {"kind": "workload", "title": "Workload"},
        {"kind": "aging", "title": "How old the open work is"},
    ]},
    {"name": "Delivery", "description": "How fast work moves and how plans hold", "widgets": [
        {"kind": "burndown", "title": "Current iteration"},
        {"kind": "velocity", "title": "Velocity"},
        {"kind": "cycle", "title": "Lead and cycle time, 30 days", "days": 30},
        {"kind": "count", "title": "Closed, last 30 days", "measure": "closed", "days": 30},
        {"kind": "group", "title": "Open by area", "group_by": "area", "filters": {"open": True}},
        {"kind": "group", "title": "Open by project tag", "group_by": "project_tag", "filters": {"open": True}},
        {"kind": "group", "title": "Open by tag", "group_by": "label", "filters": {"open": True}},
    ]},
)


def seed_default_dashboards(connection: sqlite3.Connection) -> list[dict]:
    created = []
    for dashboard in DEFAULT_DASHBOARDS:
        if connection.execute("SELECT 1 FROM dashboards WHERE name = ? COLLATE NOCASE", (dashboard["name"],)).fetchone():
            continue
        loaded = dashmodules.current().modules
        widgets = [widget for widget in dashboard["widgets"] if widget["kind"] in loaded]
        if len(widgets) < len(dashboard["widgets"]):
            log.warning("the %s dashboard is missing widgets whose modules are not loaded", dashboard["name"])
        if widgets:
            created.append(create_dashboard(connection, dashboard["name"], dashboard["description"], widgets))
    return created
