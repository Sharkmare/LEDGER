import datetime

from ledger import modulekit, organise
from ledger.store import NotFound

MODULE = {
    "id": "burndown",
    "title": "Burndown",
    "description": "Work left in an iteration against the ideal line",
    "size": 2,
    "order": 40,
    "filters": ["project"],
    "settings": [
        {"name": "iteration", "label": "Iteration", "kind": "iteration", "empty_label": "The current one"},
    ],
}


def pick_iteration(connection, filters, iteration):
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


def data(connection, settings, filters, now):
    chosen = pick_iteration(connection, filters, settings.get("iteration"))
    members = connection.execute(
        "SELECT estimate, closed FROM tickets WHERE iteration_id = ? AND status != 'cancelled'", (chosen["id"],)).fetchall()
    points_total = sum(member["estimate"] or 0 for member in members)
    unit = "points" if points_total > 0 else "tickets"
    total = points_total if unit == "points" else len(members)

    def weight(member):
        return (member["estimate"] or 0) if unit == "points" else 1

    start, end = datetime.date.fromisoformat(chosen["starts"]), datetime.date.fromisoformat(chosen["ends"])
    today = modulekit.day(now)
    length = max((end - start).days, 1)
    days = []
    for offset in range((end - start).days + 1):
        date = start + datetime.timedelta(days=offset)
        remaining = None
        if date <= today:
            remaining = sum(weight(member) for member in members if member["closed"] is None or modulekit.day(member["closed"]) > date)
        days.append({"date": date.isoformat(), "remaining": remaining, "ideal": round(total * (1 - offset / length), 2)})
    return {"iteration": organise._iteration_dict(connection, chosen), "unit": unit, "total": total, "days": days}
