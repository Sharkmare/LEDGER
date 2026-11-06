from __future__ import annotations

import datetime
import json
import math
import sqlite3
import statistics
import time
from typing import Any

from . import organise, store
from .store import (CLOSED_STATUSES, PRIORITIES, STATUSES, TICKET_TYPES, LedgerError, NotFound, _area_path, _require_choice, _require_text)

METRIC_KINDS = ("count", "group", "trend", "burndown", "cycle", "aging", "workload", "velocity", "overdue")
GROUP_FIELDS = ("status", "type", "priority", "assignee", "label", "project", "project_tag", "area", "iteration")
COUNT_MEASURES = ("total", "created", "closed")
CHART_STYLES = ("bar", "donut")
INTERVALS = ("day", "week")
FILTER_KEYS = ("project", "area", "iteration", "type", "status", "priority", "assignee", "label", "open")
WIDGET_KEYS = ("id", "title", "kind", "size", "filters", "group_by", "measure", "days", "interval", "iteration", "limit", "chart")
SECONDS_PER_DAY = 86400
MAX_DAYS = 365
MAX_WIDGETS = 24
MAX_LIMIT = 50
UNASSIGNED = "unassigned"
AGE_BUCKETS = ((7, "0 to 7 days"), (14, "8 to 14 days"), (30, "15 to 30 days"), (60, "31 to 60 days"), (None, "over 60 days"))
LEAD_BUCKETS = ((1, "1 day or less"), (3, "2 to 3 days"), (7, "4 to 7 days"), (14, "8 to 14 days"), (30, "15 to 30 days"), (None, "over 30 days"))
DEFAULT_DAYS = {"count": 7, "trend": 30, "cycle": 30, "velocity": 6}
DEFAULT_SIZE = {"trend": 2, "burndown": 2, "velocity": 2, "cycle": 2}
DEFAULT_TITLES = {
    "count": "Tickets", "group": "Tickets by field", "trend": "Created and closed", "burndown": "Burndown", "cycle": "Lead and cycle time",
    "aging": "Open ticket age", "workload": "Workload", "velocity": "Velocity", "overdue": "Overdue",
}


def _clean_filters(connection: sqlite3.Connection, filters: Any) -> dict:
    if filters is None or filters == "":
        return {}
    if not isinstance(filters, dict):
        raise LedgerError("filters must be an object")
    unknown = sorted(set(filters) - set(FILTER_KEYS))
    if unknown:
        raise LedgerError(f"unknown filter {', '.join(unknown)}; filters are {', '.join(FILTER_KEYS)}")
    cleaned: dict[str, Any] = {}
    for key, value in filters.items():
        if value in (None, "", False):
            continue
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


def _rows(connection: sqlite3.Connection, filters: dict, columns: str = "*", include_closed: bool | None = None) -> list[sqlite3.Row]:
    open_only = filters.get("open") if include_closed is None else not include_closed
    where, parameters = store._filter_clause(
        filters.get("project"), filters.get("status"), filters.get("assignee"), filters.get("type"), filters.get("priority"),
        filters.get("label"), None, not open_only, None, filters.get("area"), filters.get("iteration"), connection)
    return connection.execute(f"SELECT {columns} FROM tickets {where}", parameters).fetchall()


def _day(stamp: float) -> datetime.date:
    return datetime.date.fromtimestamp(stamp)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def count_metric(connection: sqlite3.Connection, filters: dict, measure: str = "total", days: int = 7, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cutoff, earlier = now - days * SECONDS_PER_DAY, now - 2 * days * SECONDS_PER_DAY
    rows = _rows(connection, filters, "created, closed", include_closed=True)
    if measure == "total":
        value = len([row for row in rows if row["closed"] is None]) if filters.get("open") else len(rows)
        previous = len([row for row in rows if row["created"] <= cutoff and (row["closed"] is None or row["closed"] > cutoff)])
        if not filters.get("open"):
            previous = len([row for row in rows if row["created"] <= cutoff])
    else:
        column = "created" if measure == "created" else "closed"
        stamps = [row[column] for row in rows if row[column] is not None]
        value = len([stamp for stamp in stamps if cutoff < stamp <= now])
        previous = len([stamp for stamp in stamps if earlier < stamp <= cutoff])
    return {"value": value, "previous": previous, "delta": value - previous, "measure": measure, "days": days}


def _bucket_names(connection: sqlite3.Connection, field: str, row: sqlite3.Row) -> list[str]:
    if field == "label":
        return json.loads(row["labels"]) or [""]
    if field == "area":
        return [_area_path(connection, row["area_id"])]
    if field == "iteration":
        name = connection.execute("SELECT name FROM iterations WHERE id = ?", (row["iteration_id"],)).fetchone() if row["iteration_id"] else None
        return [name["name"] if name else ""]
    if field == "project":
        return [row["project_key"]]
    if field == "project_tag":
        project = connection.execute("SELECT tags FROM projects WHERE key = ?", (row["project_key"],)).fetchone()
        return [tag for tag in (project["tags"] if project else "").split(",") if tag] or [""]
    return [row[field]]


def group_metric(connection: sqlite3.Connection, filters: dict, field: str, limit: int = 8) -> dict:
    rows = _rows(connection, filters)
    counts: dict[str, dict] = {}
    for row in rows:
        for name in _bucket_names(connection, field, row):
            bucket = counts.setdefault(name, {"name": name or ("none" if field != "assignee" else UNASSIGNED), "key": name, "value": 0, "points": 0.0})
            bucket["value"] += 1
            bucket["points"] += row["estimate"] or 0
    if field in ("status", "priority", "type"):
        order = {"status": STATUSES, "priority": PRIORITIES, "type": TICKET_TYPES}[field]
        buckets = [counts[name] for name in order if name in counts]
    else:
        buckets = sorted(counts.values(), key=lambda bucket: (-bucket["value"], bucket["name"]))
    other = buckets[limit:]
    buckets = buckets[:limit]
    if other:
        buckets.append({"name": "other", "key": None, "value": sum(b["value"] for b in other), "points": sum(b["points"] for b in other)})
    return {"field": field, "total": len(rows), "buckets": buckets}


def trend_metric(connection: sqlite3.Connection, filters: dict, days: int = 30, interval: str | None = None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    step = 7 if (interval == "week" or (interval is None and days > 60)) else 1
    today = _day(now)
    start = today - datetime.timedelta(days=days - 1)
    rows = _rows(connection, filters, "created, closed", include_closed=True)
    count = (days + step - 1) // step
    series = [{"date": (start + datetime.timedelta(days=index * step)).isoformat(), "created": 0, "closed": 0, "open": 0} for index in range(count)]

    def slot(stamp: float) -> int | None:
        offset = (_day(stamp) - start).days
        return None if offset < 0 or offset >= count * step else offset // step

    before_open = 0
    for row in rows:
        created_slot = slot(row["created"])
        if created_slot is not None:
            series[created_slot]["created"] += 1
        closed_slot = slot(row["closed"]) if row["closed"] is not None else None
        if closed_slot is not None:
            series[closed_slot]["closed"] += 1
        created_before = _day(row["created"]) < start
        closed_before = row["closed"] is not None and _day(row["closed"]) < start
        if created_before and not closed_before:
            before_open += 1
    running = before_open
    for point in series:
        running += point["created"] - point["closed"]
        point["open"] = running
    return {"days": days, "interval": "week" if step == 7 else "day", "series": series,
            "created": sum(p["created"] for p in series), "closed": sum(p["closed"] for p in series)}


def _pick_iteration(connection: sqlite3.Connection, filters: dict, iteration: int | None) -> sqlite3.Row:
    if iteration:
        return organise._iteration_row(connection, iteration)
    clauses, parameters = [], []
    if filters.get("project"):
        clauses.append("project_key = ?")
        parameters.append(filters["project"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(f"SELECT * FROM iterations {where} ORDER BY starts DESC, id DESC", parameters).fetchall()
    for state in ("active", "planned", "done"):
        for row in rows:
            if row["state"] == state:
                return row
    raise NotFound("there is no iteration to chart; create one first")


def burndown_metric(connection: sqlite3.Connection, filters: dict, iteration: int | None = None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    chosen = _pick_iteration(connection, filters, iteration)
    members = connection.execute(
        "SELECT estimate, closed FROM tickets WHERE iteration_id = ? AND status != 'cancelled'", (chosen["id"],)).fetchall()
    points_total = sum(member["estimate"] or 0 for member in members)
    unit = "points" if points_total > 0 else "tickets"
    total = points_total if unit == "points" else len(members)

    def weight(member: sqlite3.Row) -> float:
        return (member["estimate"] or 0) if unit == "points" else 1

    start, end = datetime.date.fromisoformat(chosen["starts"]), datetime.date.fromisoformat(chosen["ends"])
    today = _day(now)
    length = max((end - start).days, 1)
    days = []
    for offset in range((end - start).days + 1):
        date = start + datetime.timedelta(days=offset)
        remaining = None
        if date <= today:
            remaining = sum(weight(member) for member in members if member["closed"] is None or _day(member["closed"]) > date)
        days.append({"date": date.isoformat(), "remaining": remaining, "ideal": round(total * (1 - offset / length), 2)})
    return {"iteration": organise._iteration_dict(connection, chosen), "unit": unit, "total": total, "days": days}


def _lead_days(row: sqlite3.Row) -> float:
    return (row["closed"] - row["created"]) / SECONDS_PER_DAY


def _summary(values: list[float]) -> dict:
    if not values:
        return {"average": None, "median": None, "p85": None}
    return {"average": round(sum(values) / len(values), 1), "median": round(statistics.median(values), 1), "p85": round(_percentile(values, 0.85), 1)}


def _bucketed(values: list[float], buckets: tuple) -> list[dict]:
    result = [{"label": label, "value": 0} for _, label in buckets]
    for value in values:
        for index, (limit, _) in enumerate(buckets):
            if limit is None or value <= limit:
                result[index]["value"] += 1
                break
    return result


def cycle_metric(connection: sqlite3.Connection, filters: dict, days: int = 30, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cutoff = now - days * SECONDS_PER_DAY
    rows = [row for row in _rows(connection, filters, "id, created, closed, status", include_closed=True)
            if row["status"] == "done" and row["closed"] is not None and row["closed"] >= cutoff]
    lead = [_lead_days(row) for row in rows]
    cycle = []
    for row in rows:
        started = connection.execute(
            "SELECT MIN(created) AS at FROM events WHERE ticket_id = ? AND field = 'status' AND new = 'in_progress'", (row["id"],)).fetchone()["at"]
        if started is not None and row["closed"] >= started:
            cycle.append((row["closed"] - started) / SECONDS_PER_DAY)
    return {"days": days, "closed": len(rows), "lead": _summary(lead), "cycle": _summary(cycle), "histogram": _bucketed(lead, LEAD_BUCKETS)}


def aging_metric(connection: sqlite3.Connection, filters: dict, limit: int = 5, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    rows = _rows(connection, {**filters, "open": True}, "project_key, number, title, created")
    ages = [(now - row["created"]) / SECONDS_PER_DAY for row in rows]
    oldest = sorted(rows, key=lambda row: row["created"])[:limit]
    return {"total": len(rows), "buckets": _bucketed(ages, AGE_BUCKETS),
            "oldest": [{"key": f"{row['project_key']}-{row['number']}", "title": row["title"], "age_days": int((now - row["created"]) / SECONDS_PER_DAY)}
                       for row in oldest]}


def workload_metric(connection: sqlite3.Connection, filters: dict, limit: int = 8, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    today = _day(now).isoformat()
    people: dict[str, dict] = {}
    for row in _rows(connection, {**filters, "open": True}, "assignee, estimate, due"):
        person = people.setdefault(row["assignee"], {"name": row["assignee"] or UNASSIGNED, "tickets": 0, "points": 0.0, "overdue": 0})
        person["tickets"] += 1
        person["points"] += row["estimate"] or 0
        person["overdue"] += 1 if row["due"] and row["due"] < today else 0
    ordered = sorted(people.values(), key=lambda person: (-person["tickets"], person["name"]))
    return {"people": ordered[:limit], "more": max(0, len(ordered) - limit)}


def velocity_metric(connection: sqlite3.Connection, filters: dict, limit: int = 6) -> dict:
    clauses, parameters = ["state = 'done'"], []
    if filters.get("project"):
        clauses.append("project_key = ?")
        parameters.append(filters["project"])
    rows = connection.execute(f"SELECT * FROM iterations WHERE {' AND '.join(clauses)} ORDER BY ends DESC, id DESC LIMIT ?", (*parameters, limit)).fetchall()
    sprints = [organise._iteration_dict(connection, row) for row in reversed(rows)]
    items = [{"name": f"{sprint['project']} {sprint['name']}" if not filters.get("project") else sprint["name"], "committed": sprint["points"],
              "completed": sprint["points_done"], "tickets": sprint["tickets"], "tickets_done": sprint["done"]} for sprint in sprints]
    completed = [item["completed"] for item in items]
    return {"iterations": items, "average": round(sum(completed) / len(completed), 1) if completed else None}


def overdue_metric(connection: sqlite3.Connection, filters: dict, limit: int = 8, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    today = _day(now).isoformat()
    rows = [row for row in _rows(connection, {**filters, "open": True}, "project_key, number, title, due, assignee, priority") if row["due"] and row["due"] < today]
    rows.sort(key=lambda row: row["due"])
    return {"total": len(rows), "items": [{"key": f"{row['project_key']}-{row['number']}", "title": row["title"], "due": row["due"],
                                           "assignee": row["assignee"], "priority": row["priority"],
                                           "days_late": (_day(now) - datetime.date.fromisoformat(row["due"])).days} for row in rows[:limit]]}


def _int_in_range(field: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not (isinstance(value, int) or str(value).strip().lstrip("-").isdigit()):
        raise LedgerError(f"{field} must be a whole number")
    number = int(value)
    if not low <= number <= high:
        raise LedgerError(f"{field} must be between {low} and {high}")
    return number


def _given(widget: dict, key: str, default: Any) -> Any:
    value = widget.get(key)
    return default if value is None or value == "" else value


def clean_widget(connection: sqlite3.Connection, widget: Any) -> dict:
    if not isinstance(widget, dict):
        raise LedgerError("a widget must be an object")
    unknown = sorted(set(widget) - set(WIDGET_KEYS))
    if unknown:
        raise LedgerError(f"unknown widget field {', '.join(unknown)}; fields are {', '.join(WIDGET_KEYS)}")
    kind = _require_choice("kind", widget.get("kind", ""), METRIC_KINDS)
    title = " ".join(_require_text("title", widget.get("title") or DEFAULT_TITLES[kind]).split())
    if not title:
        raise LedgerError("title is required")
    cleaned: dict[str, Any] = {
        "kind": kind, "title": title[:80], "size": _int_in_range("size", _given(widget, "size", DEFAULT_SIZE.get(kind, 1)), 1, 3),
        "filters": _clean_filters(connection, widget.get("filters")),
        "days": _int_in_range("days", _given(widget, "days", DEFAULT_DAYS.get(kind, 30)), 1, MAX_DAYS),
        "limit": _int_in_range("limit", _given(widget, "limit", 8), 1, MAX_LIMIT),
    }
    if widget.get("id"):
        cleaned["id"] = _require_text("id", widget["id"]).strip()
    if kind == "group":
        cleaned["group_by"] = _require_choice("group_by", widget.get("group_by") or "status", GROUP_FIELDS)
        cleaned["chart"] = _require_choice("chart", widget.get("chart") or "bar", CHART_STYLES)
    if kind == "count":
        cleaned["measure"] = _require_choice("measure", widget.get("measure") or "total", COUNT_MEASURES)
    if kind == "trend" and widget.get("interval"):
        cleaned["interval"] = _require_choice("interval", widget["interval"], INTERVALS)
    if kind == "burndown" and widget.get("iteration"):
        cleaned["iteration"] = _int_in_range("iteration", widget["iteration"], 1, 10**9)
    return cleaned


def evaluate(connection: sqlite3.Connection, widget: Any, now: float | None = None) -> dict:
    config = clean_widget(connection, widget)
    kind, filters = config["kind"], config["filters"]
    if kind == "count":
        result = count_metric(connection, filters, config["measure"], config["days"], now)
    elif kind == "group":
        result = group_metric(connection, filters, config["group_by"], config["limit"])
    elif kind == "trend":
        result = trend_metric(connection, filters, config["days"], config.get("interval"), now)
    elif kind == "burndown":
        result = burndown_metric(connection, filters, config.get("iteration"), now)
    elif kind == "cycle":
        result = cycle_metric(connection, filters, config["days"], now)
    elif kind == "aging":
        result = aging_metric(connection, filters, min(config["limit"], 10), now)
    elif kind == "workload":
        result = workload_metric(connection, filters, config["limit"], now)
    elif kind == "velocity":
        result = velocity_metric(connection, filters, config["days"])
    else:
        result = overdue_metric(connection, filters, config["limit"], now)
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
        exists = connection.execute("SELECT 1 FROM dashboards WHERE name = ? COLLATE NOCASE", (dashboard["name"],)).fetchone()
        if not exists:
            created.append(create_dashboard(connection, dashboard["name"], dashboard["description"], dashboard["widgets"]))
    return created
