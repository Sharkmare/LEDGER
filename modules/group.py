import json

from ledger import modulekit
from ledger.store import PRIORITIES, STATUSES, TICKET_TYPES, _area_path

GROUP_FIELDS = ("status", "type", "priority", "assignee", "label", "project", "project_tag", "area", "iteration")

MODULE = {
    "id": "group",
    "title": "Breakdown",
    "description": "Tickets counted by status, type, priority, person, tag, project, area or iteration",
    "order": 20,
    "filters": True,
    "settings": [
        {"name": "group_by", "label": "Group by", "kind": "select", "default": "status", "options": list(GROUP_FIELDS)},
        {"name": "chart", "label": "Chart", "kind": "select", "default": "bar", "options": [{"value": "bar", "label": "Bars"}, {"value": "donut", "label": "Donut"}]},
        {"name": "limit", "label": "Most common to show", "kind": "number", "default": 8, "min": 1, "max": 50},
    ],
}


def bucket_names(connection, field, row):
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


def data(connection, settings, filters, now):
    field, limit = settings["group_by"], settings["limit"]
    rows = modulekit.ticket_rows(connection, filters)
    counts = {}
    for row in rows:
        for name in bucket_names(connection, field, row):
            bucket = counts.setdefault(name, {"name": name or ("none" if field != "assignee" else modulekit.UNASSIGNED), "key": name, "value": 0, "points": 0.0})
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
