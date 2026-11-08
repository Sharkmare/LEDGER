import datetime

from ledger import modulekit

MODULE = {
    "id": "trend",
    "title": "Created and closed",
    "description": "Tickets created and closed per day or week, with the open count running underneath",
    "size": 2,
    "order": 30,
    "filters": True,
    "settings": [
        {"name": "days", "label": "Days to show", "kind": "number", "default": 30, "min": 1, "max": 365},
        {"name": "interval", "label": "Step", "kind": "select",
         "options": [{"value": "", "label": "Automatic"}, {"value": "day", "label": "Day"}, {"value": "week", "label": "Week"}]},
    ],
}


def data(connection, settings, filters, now):
    days, interval = settings["days"], settings.get("interval")
    step = 7 if (interval == "week" or (not interval and days > 60)) else 1
    today = modulekit.day(now)
    start = today - datetime.timedelta(days=days - 1)
    rows = modulekit.ticket_rows(connection, filters, "created, closed", include_closed=True)
    count = (days + step - 1) // step
    series = [{"date": (start + datetime.timedelta(days=index * step)).isoformat(), "created": 0, "closed": 0, "open": 0} for index in range(count)]

    def slot(stamp):
        offset = (modulekit.day(stamp) - start).days
        return None if offset < 0 or offset >= count * step else offset // step

    before_open = 0
    for row in rows:
        created_slot = slot(row["created"])
        if created_slot is not None:
            series[created_slot]["created"] += 1
        closed_slot = slot(row["closed"]) if row["closed"] is not None else None
        if closed_slot is not None:
            series[closed_slot]["closed"] += 1
        created_before = modulekit.day(row["created"]) < start
        closed_before = row["closed"] is not None and modulekit.day(row["closed"]) < start
        if created_before and not closed_before:
            before_open += 1
    running = before_open
    for point in series:
        running += point["created"] - point["closed"]
        point["open"] = running
    return {"days": days, "interval": "week" if step == 7 else "day", "series": series,
            "created": sum(p["created"] for p in series), "closed": sum(p["closed"] for p in series)}
