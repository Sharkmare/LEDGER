import datetime
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import metrics, organise, people, server, store

DAY = 86400
NOW = datetime.datetime(2026, 11, 5, 12, 0).timestamp()


def ago(days: float) -> float:
    return NOW - days * DAY


def workspace():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App")
    store.create_project(connection, "WEB", "Web")
    for name in ("ann", "bob", *(f"person{number}" for number in range(5))):
        people.add(connection, name)
    return connection


def make(connection, title="t", created=0, closed=None, project="APP", **fields):
    status = fields.pop("status", "done" if closed is not None else "todo")
    ticket = store.create_ticket(connection, project, title, status=status, **fields)
    connection.execute("UPDATE tickets SET created = ?, closed = ?, updated = ? WHERE project_key = ? AND number = ?",
                       (ago(created), None if closed is None else ago(closed), ago(created), project, ticket["number"]))
    connection.commit()
    return ticket


def started(connection, ticket, days_ago):
    connection.execute("INSERT INTO events (ticket_id, actor, field, old, new, created) VALUES (?, 'x', 'status', 'todo', 'in_progress', ?)",
                       (ticket["id"], ago(days_ago)))
    connection.commit()


class CountTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_created_and_closed_compare_with_the_previous_window(self):
        make(self.connection, created=2)
        make(self.connection, created=3)
        make(self.connection, created=10, closed=1)
        make(self.connection, created=20, closed=9)
        created = metrics.count_metric(self.connection, {}, "created", 7, NOW)
        self.assertEqual((created["value"], created["previous"], created["delta"]), (2, 1, 1))
        closed = metrics.count_metric(self.connection, {}, "closed", 7, NOW)
        self.assertEqual((closed["value"], closed["previous"]), (1, 1))

    def test_total_counts_what_exists_now_against_what_existed_then(self):
        make(self.connection, created=2)
        make(self.connection, created=10, closed=3)
        make(self.connection, created=20)
        total = metrics.count_metric(self.connection, {}, "total", 7, NOW)
        self.assertEqual((total["value"], total["previous"]), (3, 2))
        open_now = metrics.count_metric(self.connection, {"open": True}, "total", 7, NOW)
        self.assertEqual((open_now["value"], open_now["previous"]), (2, 2))

    def test_filters_apply(self):
        make(self.connection, created=1, type="bug")
        make(self.connection, created=1, type="task")
        make(self.connection, created=1, project="WEB", type="bug")
        self.assertEqual(metrics.count_metric(self.connection, {"type": "bug"}, "total", 7, NOW)["value"], 2)
        self.assertEqual(metrics.count_metric(self.connection, {"type": "bug", "project": "APP"}, "total", 7, NOW)["value"], 1)


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_status_buckets_follow_the_workflow_order(self):
        make(self.connection, status="done", closed=1)
        make(self.connection, status="todo")
        make(self.connection, status="todo")
        result = metrics.group_metric(self.connection, {}, "status")
        self.assertEqual([(b["name"], b["value"]) for b in result["buckets"]], [("todo", 2), ("done", 1)])
        self.assertEqual(result["total"], 3)

    def test_project_tag_groups_tickets_by_their_projects_tags(self):
        connection = workspace()
        store.update_project(connection, "APP", {"tags": "resonite-research, games"})
        make(connection, "one", project="APP")
        make(connection, "two", project="APP")
        make(connection, "three", project="WEB")
        buckets = {bucket["key"]: bucket["value"] for bucket in metrics.group_metric(connection, {}, "project_tag")["buckets"]}
        self.assertEqual(buckets, {"resonite-research": 2, "games": 2, "": 1})

    def test_tags_are_unnested_and_unassigned_is_named(self):
        make(self.connection, labels="a,b", assignee="ann", estimate=3)
        make(self.connection, labels="a")
        tags = {b["name"]: b["value"] for b in metrics.group_metric(self.connection, {}, "label")["buckets"]}
        self.assertEqual(tags, {"a": 2, "b": 1})
        people = {b["name"]: (b["value"], b["points"]) for b in metrics.group_metric(self.connection, {}, "assignee")["buckets"]}
        self.assertEqual(people, {"ann": (1, 3.0), "unassigned": (1, 0.0)})

    def test_area_and_iteration_use_names_and_the_tail_is_folded_into_other(self):
        organise.create_area(self.connection, "Platform")
        sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-02", "2026-11-13")
        make(self.connection, area="Platform", iteration=sprint["id"])
        make(self.connection)
        areas = {b["name"] for b in metrics.group_metric(self.connection, {}, "area")["buckets"]}
        self.assertEqual(areas, {"Platform", "none"})
        iterations = {b["name"] for b in metrics.group_metric(self.connection, {}, "iteration")["buckets"]}
        self.assertEqual(iterations, {"Sprint 1", "none"})
        for number in range(5):
            make(self.connection, assignee=f"person{number}")
        folded = metrics.group_metric(self.connection, {}, "assignee", limit=2)["buckets"]
        self.assertEqual((len(folded), folded[-1]["name"]), (3, "other"))


class TrendTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_daily_series_counts_created_closed_and_running_open(self):
        make(self.connection, created=3, closed=1)
        make(self.connection, created=10)
        make(self.connection, created=2)
        trend = metrics.trend_metric(self.connection, {}, 7, None, NOW)
        series = trend["series"]
        self.assertEqual((len(series), series[0]["date"], series[-1]["date"]), (7, "2026-10-30", "2026-11-05"))
        by_date = {point["date"]: point for point in series}
        self.assertEqual((by_date["2026-11-02"]["created"], by_date["2026-11-03"]["created"], by_date["2026-11-04"]["closed"]), (1, 1, 1))
        self.assertEqual([point["open"] for point in series], [1, 1, 1, 2, 3, 2, 2])
        self.assertEqual((trend["created"], trend["closed"], trend["interval"]), (2, 1, "day"))

    def test_long_windows_switch_to_weeks(self):
        make(self.connection, created=5)
        trend = metrics.trend_metric(self.connection, {}, 90, None, NOW)
        self.assertEqual((trend["interval"], len(trend["series"])), ("week", 13))
        self.assertEqual(sum(point["created"] for point in trend["series"]), 1)


class BurndownTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-02", "2026-11-06", state="active")

    def test_remaining_points_fall_when_work_closes_and_stop_at_today(self):
        make(self.connection, iteration=self.sprint["id"], estimate=3, created=5, closed=2)
        make(self.connection, iteration=self.sprint["id"], estimate=2, created=5)
        make(self.connection, iteration=self.sprint["id"], estimate=9, created=5, status="cancelled")
        result = metrics.burndown_metric(self.connection, {"project": "APP"}, None, NOW)
        self.assertEqual((result["unit"], result["total"]), ("points", 5.0))
        self.assertEqual([day["remaining"] for day in result["days"]], [5.0, 2.0, 2.0, 2.0, None])
        self.assertEqual([day["ideal"] for day in result["days"]], [5.0, 3.75, 2.5, 1.25, 0.0])

    def test_without_estimates_it_counts_tickets(self):
        make(self.connection, iteration=self.sprint["id"], created=5, closed=1)
        make(self.connection, iteration=self.sprint["id"], created=5)
        result = metrics.burndown_metric(self.connection, {}, self.sprint["id"], NOW)
        self.assertEqual((result["unit"], result["total"], result["days"][0]["remaining"], result["days"][-2]["remaining"]), ("tickets", 2, 2, 1))

    def test_the_active_iteration_is_preferred_and_none_is_an_error(self):
        organise.create_iteration(self.connection, "APP", "Sprint 0", "2026-10-01", "2026-10-14", state="done")
        self.assertEqual(metrics.burndown_metric(self.connection, {"project": "APP"}, None, NOW)["iteration"]["name"], "Sprint 1")
        with self.assertRaises(store.NotFound):
            metrics.burndown_metric(self.connection, {"project": "WEB"}, None, NOW)


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_lead_and_cycle_times_and_the_histogram(self):
        first = make(self.connection, created=5, closed=3)
        started(self.connection, first, 4)
        make(self.connection, created=12, closed=2)
        make(self.connection, created=9, closed=1, status="cancelled")
        make(self.connection, created=60, closed=40)
        result = metrics.cycle_metric(self.connection, {}, 30, NOW)
        self.assertEqual(result["closed"], 2)
        self.assertEqual((result["lead"]["average"], result["lead"]["median"]), (6.0, 6.0))
        self.assertEqual((result["cycle"]["average"], result["cycle"]["median"]), (1.0, 1.0))
        counts = {bucket["label"]: bucket["value"] for bucket in result["histogram"]}
        self.assertEqual((counts["2 to 3 days"], counts["8 to 14 days"], counts["over 30 days"]), (1, 1, 0))

    def test_nothing_closed_gives_empty_figures(self):
        result = metrics.cycle_metric(self.connection, {}, 30, NOW)
        self.assertEqual((result["closed"], result["lead"]["average"], result["cycle"]["median"]), (0, None, None))


class AgingWorkloadTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_aging_buckets_and_the_oldest_first(self):
        for age in (3, 10, 20, 50, 90):
            make(self.connection, title=f"age {age}", created=age)
        make(self.connection, title="closed", created=100, closed=1)
        result = metrics.aging_metric(self.connection, {}, 2, NOW)
        self.assertEqual([bucket["value"] for bucket in result["buckets"]], [1, 1, 1, 1, 1])
        self.assertEqual(([item["title"] for item in result["oldest"]], result["total"]), (["age 90", "age 50"], 5))

    def test_workload_counts_open_work_per_person(self):
        make(self.connection, assignee="ann", estimate=3, due="2026-11-01")
        make(self.connection, assignee="ann")
        make(self.connection, assignee="bob")
        make(self.connection)
        make(self.connection, assignee="ann", closed=1)
        result = metrics.workload_metric(self.connection, {}, 2, NOW)
        self.assertEqual([(p["name"], p["tickets"], p["points"], p["overdue"]) for p in result["people"]], [("ann", 2, 3.0, 1), ("bob", 1, 0.0, 0)])
        self.assertEqual(result["more"], 1)


class VelocityOverdueTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_velocity_uses_finished_iterations_in_date_order(self):
        old = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-09-01", "2026-09-12", state="done")
        recent = organise.create_iteration(self.connection, "APP", "Sprint 2", "2026-09-14", "2026-09-26", state="done")
        organise.create_iteration(self.connection, "APP", "Sprint 3", "2026-11-02", "2026-11-13", state="active")
        make(self.connection, iteration=old["id"], estimate=5, closed=60)
        make(self.connection, iteration=old["id"], estimate=3)
        make(self.connection, iteration=recent["id"], estimate=8, closed=40)
        result = metrics.velocity_metric(self.connection, {"project": "APP"})
        self.assertEqual([(i["name"], i["committed"], i["completed"]) for i in result["iterations"]], [("Sprint 1", 8.0, 5.0), ("Sprint 2", 8.0, 8.0)])
        self.assertEqual(result["average"], 6.5)

    def test_overdue_lists_open_late_work_worst_first(self):
        make(self.connection, title="yesterday", due="2026-11-04", assignee="ann")
        make(self.connection, title="long ago", due="2026-10-26")
        make(self.connection, title="tomorrow", due="2026-11-06")
        make(self.connection, title="finished late", due="2026-10-01", closed=1)
        make(self.connection, title="no date")
        result = metrics.overdue_metric(self.connection, {}, 8, NOW)
        self.assertEqual((result["total"], [item["title"] for item in result["items"]]), (2, ["long ago", "yesterday"]))
        self.assertEqual(result["items"][0]["days_late"], 10)


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_widgets_are_normalised(self):
        widget = metrics.clean_widget(self.connection, {"kind": "group", "filters": {"project": "app", "open": True, "type": "bug"}})
        self.assertEqual((widget["group_by"], widget["chart"], widget["size"], widget["filters"]), ("status", "bar", 1, {"project": "APP", "open": True, "type": "bug"}))
        self.assertEqual(metrics.clean_widget(self.connection, {"kind": "trend"})["size"], 2)
        self.assertEqual(metrics.clean_widget(self.connection, {"kind": "count"})["days"], 7)

    def test_bad_widgets_are_refused(self):
        for widget in ({"kind": "pie"}, {}, {"kind": "count", "colour": "red"}, {"kind": "group", "group_by": "mood"}, {"kind": "count", "size": 4},
                       {"kind": "trend", "days": 0}, {"kind": "trend", "days": 400}, {"kind": "count", "filters": {"mood": "x"}},
                       {"kind": "count", "filters": {"project": "NOPE"}}, {"kind": "count", "filters": {"type": "saga"}},
                       {"kind": "count", "filters": []}, {"kind": "count", "measure": "weight"}, {"kind": "trend", "interval": "year"},
                       {"kind": "group", "chart": "radar"}, {"kind": "count", "filters": {"iteration": "x"}}, "count"):
            with self.assertRaises(store.LedgerError, msg=str(widget)):
                metrics.clean_widget(self.connection, widget)

    def test_evaluate_returns_the_widget_and_its_data(self):
        make(self.connection, created=1)
        result = metrics.evaluate(self.connection, {"kind": "count", "measure": "created", "days": 7}, NOW)
        self.assertEqual((result["widget"]["kind"], result["data"]["value"]), ("count", 1))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_widgets_get_unique_ids_and_defaults(self):
        dashboard = metrics.create_dashboard(self.connection, "Mine", "d", [{"kind": "count"}, {"kind": "count", "id": "x"}, {"kind": "count", "id": "x"}])
        ids = [widget["id"] for widget in dashboard["widgets"]]
        self.assertEqual((len(set(ids)), ids[1]), (3, "x"))

    def test_bad_dashboards_are_refused(self):
        metrics.create_dashboard(self.connection, "Mine")
        for arguments in ({"name": "mine"}, {"name": " "}, {"name": "x", "widgets": "no"}, {"name": "x", "widgets": [{"kind": "pie"}]},
                          {"name": "x", "widgets": [{"kind": "count"}] * (metrics.MAX_WIDGETS + 1)}):
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                metrics.create_dashboard(self.connection, **arguments)

    def test_update_delete_and_unknown_fields(self):
        dashboard = metrics.create_dashboard(self.connection, "Mine", widgets=[{"kind": "count"}])
        edited = metrics.update_dashboard(self.connection, dashboard["id"], {"name": "Ours", "widgets": [{"kind": "overdue"}, {"kind": "aging"}]})
        self.assertEqual((edited["name"], [w["kind"] for w in edited["widgets"]]), ("Ours", ["overdue", "aging"]))
        with self.assertRaises(store.LedgerError):
            metrics.update_dashboard(self.connection, dashboard["id"], {"colour": "red"})
        metrics.delete_dashboard(self.connection, dashboard["id"])
        with self.assertRaises(store.NotFound):
            metrics.get_dashboard(self.connection, dashboard["id"])

    def test_one_failing_widget_does_not_spoil_the_rest(self):
        dashboard = metrics.create_dashboard(self.connection, "Mixed", widgets=[{"kind": "burndown"}, {"kind": "count"}])
        results = metrics.dashboard_data(self.connection, dashboard["id"], NOW)["results"]
        self.assertIn("error", results["w1"])
        self.assertEqual(results["w2"]["value"], 0)

    def test_default_dashboards_are_added_once_and_evaluate(self):
        created = metrics.seed_default_dashboards(self.connection)
        self.assertEqual([d["name"] for d in created], ["Overview", "Delivery"])
        self.assertEqual(metrics.seed_default_dashboards(self.connection), [])
        make(self.connection, created=2, assignee="ann", labels="a", due="2026-11-01", estimate=2)
        overview = metrics.dashboard_data(self.connection, created[0]["id"], NOW)["results"]
        self.assertTrue(all("error" not in result for result in overview.values()))
        delivery = metrics.dashboard_data(self.connection, created[1]["id"], NOW)["results"]
        self.assertEqual([widget["kind"] for widget in created[1]["widgets"] if "error" in delivery[widget["id"]]], ["burndown"])


class MetricsApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})
        self.client.post("/api/people", json={"name": "ann"})
        self.client.post("/api/tickets", json={"project": "APP", "title": "t", "labels": "a", "assignee": "ann"})

    def test_a_fresh_server_has_the_default_dashboards(self):
        names = [d["name"] for d in self.client.get("/api/dashboards").get_json()]
        self.assertEqual(names, ["Overview", "Delivery"])

    def test_metric_endpoint(self):
        result = self.client.post("/api/metrics", json={"kind": "group", "group_by": "assignee"}).get_json()
        self.assertEqual(result["data"]["buckets"][0]["name"], "ann")
        count = self.client.post("/api/metrics", json={"kind": "count", "measure": "created"}).get_json()
        self.assertEqual(count["data"]["value"], 1)

    def test_dashboard_crud_and_data(self):
        created = self.client.post("/api/dashboards", json={"name": "Mine", "widgets": [{"kind": "count", "filters": {"open": True}}]})
        self.assertEqual(created.status_code, 201)
        identifier = created.get_json()["id"]
        data = self.client.get(f"/api/dashboards/{identifier}/data").get_json()
        self.assertEqual(data["results"]["w1"]["value"], 1)
        edited = self.client.patch(f"/api/dashboards/{identifier}", json={"description": "x"}).get_json()
        self.assertEqual(edited["description"], "x")
        self.assertEqual(self.client.delete(f"/api/dashboards/{identifier}").get_json()["deleted"], identifier)
        self.assertEqual(self.client.get(f"/api/dashboards/{identifier}").status_code, 404)
        self.assertEqual(self.client.post("/api/dashboards/defaults", json={}).get_json(), [])

    def test_bad_requests_get_json_errors(self):
        for response in (self.client.post("/api/metrics", json={"kind": "pie"}), self.client.post("/api/metrics", json={"kind": "burndown"}),
                         self.client.post("/api/dashboards", json={"name": ""}), self.client.get("/api/dashboards/99/data"),
                         self.client.patch("/api/dashboards/99", json={}), self.client.post("/api/metrics", json=[])):
            self.assertEqual(response.mimetype, "application/json")
            self.assertIn(response.status_code, (400, 404))
            self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
