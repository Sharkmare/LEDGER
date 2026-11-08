from ledger import modulekit

MAX_OLDEST = 10
AGE_BUCKETS = ((7, "0 to 7 days"), (14, "8 to 14 days"), (30, "15 to 30 days"), (60, "31 to 60 days"), (None, "over 60 days"))

MODULE = {
    "id": "aging",
    "title": "Open ticket age",
    "description": "How long open tickets have existed, with the oldest listed",
    "order": 60,
    "filters": True,
    "settings": [
        {"name": "limit", "label": "Rows to show", "kind": "number", "default": 8, "min": 1, "max": 50},
    ],
}


def data(connection, settings, filters, now):
    limit = min(settings["limit"], MAX_OLDEST)
    rows = modulekit.ticket_rows(connection, {**filters, "open": True}, "project_key, number, title, created")
    ages = [(now - row["created"]) / modulekit.SECONDS_PER_DAY for row in rows]
    oldest = sorted(rows, key=lambda row: row["created"])[:limit]
    return {"total": len(rows), "buckets": modulekit.bucketed(ages, AGE_BUCKETS),
            "oldest": [{"key": f"{row['project_key']}-{row['number']}", "title": row["title"], "age_days": int((now - row["created"]) / modulekit.SECONDS_PER_DAY)}
                       for row in oldest]}
