from ledger import modulekit

MODULE = {
    "id": "count",
    "title": "Count with change",
    "description": "One number, compared with the period before",
    "order": 10,
    "filters": True,
    "settings": [
        {"name": "measure", "label": "Measure", "kind": "select", "default": "total",
         "options": [{"value": "total", "label": "Tickets that exist"}, {"value": "created", "label": "Created in the period"},
                     {"value": "closed", "label": "Closed in the period"}]},
        {"name": "days", "label": "Period in days", "kind": "number", "default": 7, "min": 1, "max": 365},
    ],
}


def data(connection, settings, filters, now):
    measure, days = settings["measure"], settings["days"]
    cutoff, earlier = now - days * modulekit.SECONDS_PER_DAY, now - 2 * days * modulekit.SECONDS_PER_DAY
    rows = modulekit.ticket_rows(connection, filters, "created, closed", include_closed=True)
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
