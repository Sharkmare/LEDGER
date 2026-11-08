import math
import statistics

from ledger import modulekit

LEAD_BUCKETS = ((1, "1 day or less"), (3, "2 to 3 days"), (7, "4 to 7 days"), (14, "8 to 14 days"), (30, "15 to 30 days"), (None, "over 30 days"))

MODULE = {
    "id": "cycle",
    "title": "Lead and cycle time",
    "description": "How long finished tickets took, from creation and from the start of work",
    "size": 2,
    "order": 50,
    "filters": True,
    "settings": [
        {"name": "days", "label": "Look back in days", "kind": "number", "default": 30, "min": 1, "max": 365},
    ],
}


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summary(values):
    if not values:
        return {"average": None, "median": None, "p85": None}
    return {"average": round(sum(values) / len(values), 1), "median": round(statistics.median(values), 1), "p85": round(percentile(values, 0.85), 1)}


def data(connection, settings, filters, now):
    days = settings["days"]
    cutoff = now - days * modulekit.SECONDS_PER_DAY
    rows = [row for row in modulekit.ticket_rows(connection, filters, "id, created, closed, status", include_closed=True)
            if row["status"] == "done" and row["closed"] is not None and row["closed"] >= cutoff]
    lead = [(row["closed"] - row["created"]) / modulekit.SECONDS_PER_DAY for row in rows]
    cycle = []
    for row in rows:
        started = connection.execute(
            "SELECT MIN(created) AS at FROM events WHERE ticket_id = ? AND field = 'status' AND new = 'in_progress'", (row["id"],)).fetchone()["at"]
        if started is not None and row["closed"] >= started:
            cycle.append((row["closed"] - started) / modulekit.SECONDS_PER_DAY)
    return {"days": days, "closed": len(rows), "lead": summary(lead), "cycle": summary(cycle), "histogram": modulekit.bucketed(lead, LEAD_BUCKETS)}
