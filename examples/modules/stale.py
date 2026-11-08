from ledger import modulekit

MODULE = {
    "id": "stale",
    "title": "Stale work",
    "description": "Open tickets nobody has touched for a while, longest quiet first",
    "filters": True,
    "settings": [
        {"name": "days", "label": "Quiet for at least (days)", "kind": "number", "default": 14, "min": 1, "max": 365},
        {"name": "limit", "label": "Rows to show", "kind": "number", "default": 5, "min": 1, "max": 20},
    ],
}


def data(connection, settings, filters, now):
    cutoff = now - settings["days"] * modulekit.SECONDS_PER_DAY
    rows = modulekit.ticket_rows(connection, {**filters, "open": True}, "project_key, number, title, updated")
    quiet = sorted((row for row in rows if row["updated"] <= cutoff), key=lambda row: row["updated"])
    return {"total": len(quiet), "days": settings["days"],
            "items": [{"key": f"{row['project_key']}-{row['number']}", "title": row["title"],
                       "quiet_days": int((now - row["updated"]) / modulekit.SECONDS_PER_DAY)} for row in quiet[:settings["limit"]]]}
