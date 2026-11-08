import datetime

from ledger import modulekit

MODULE = {
    "id": "overdue",
    "title": "Overdue work",
    "description": "Open tickets past their due date, most late first",
    "order": 90,
    "filters": True,
    "settings": [
        {"name": "limit", "label": "Rows to show", "kind": "number", "default": 8, "min": 1, "max": 50},
    ],
}


def data(connection, settings, filters, now):
    today = modulekit.day(now).isoformat()
    rows = [row for row in modulekit.ticket_rows(connection, {**filters, "open": True}, "project_key, number, title, due, assignee, priority")
            if row["due"] and row["due"] < today]
    rows.sort(key=lambda row: row["due"])
    return {"total": len(rows), "items": [{"key": f"{row['project_key']}-{row['number']}", "title": row["title"], "due": row["due"],
                                           "assignee": row["assignee"], "priority": row["priority"],
                                           "days_late": (modulekit.day(now) - datetime.date.fromisoformat(row["due"])).days} for row in rows[:settings["limit"]]]}
