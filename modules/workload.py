from ledger import modulekit

MODULE = {
    "id": "workload",
    "title": "Workload by person",
    "description": "Open tickets, points and overdue work per assignee",
    "order": 70,
    "filters": True,
    "settings": [
        {"name": "limit", "label": "Rows to show", "kind": "number", "default": 8, "min": 1, "max": 50},
    ],
}


def data(connection, settings, filters, now):
    limit = settings["limit"]
    today = modulekit.day(now).isoformat()
    people = {}
    for row in modulekit.ticket_rows(connection, {**filters, "open": True}, "assignee, estimate, due"):
        person = people.setdefault(row["assignee"], {"name": row["assignee"] or modulekit.UNASSIGNED, "tickets": 0, "points": 0.0, "overdue": 0})
        person["tickets"] += 1
        person["points"] += row["estimate"] or 0
        person["overdue"] += 1 if row["due"] and row["due"] < today else 0
    ordered = sorted(people.values(), key=lambda person: (-person["tickets"], person["name"]))
    return {"people": ordered[:limit], "more": max(0, len(ordered) - limit)}
