from ledger import organise

MODULE = {
    "id": "velocity",
    "title": "Velocity",
    "description": "Points committed and completed in the most recent finished iterations",
    "size": 2,
    "order": 80,
    "filters": ["project"],
    "settings": [
        {"name": "days", "label": "Iterations to show", "kind": "number", "default": 6, "min": 1, "max": 365, "help": "Counts the most recent finished iterations"},
    ],
}


def data(connection, settings, filters, now):
    clauses, parameters = ["state = 'done'"], []
    if filters.get("project"):
        clauses.append("project_key = ?")
        parameters.append(filters["project"])
    rows = connection.execute(f"SELECT * FROM iterations WHERE {' AND '.join(clauses)} ORDER BY ends DESC, id DESC LIMIT ?", (*parameters, settings["days"])).fetchall()
    sprints = [organise._iteration_dict(connection, row) for row in reversed(rows)]
    items = [{"name": f"{sprint['project']} {sprint['name']}" if not filters.get("project") else sprint["name"], "committed": sprint["points"],
              "completed": sprint["points_done"], "tickets": sprint["tickets"], "tickets_done": sprint["done"]} for sprint in sprints]
    completed = [item["completed"] for item in items]
    return {"iterations": items, "average": round(sum(completed) / len(completed), 1) if completed else None}
