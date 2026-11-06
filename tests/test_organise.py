import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import manage, organise, server, store

OLD_SCHEMA = """
CREATE TABLE projects (key TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE TABLE tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT NOT NULL REFERENCES projects(key), number INTEGER NOT NULL,
    title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', type TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
    assignee TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '[]', parent_id INTEGER REFERENCES tickets(id),
    due TEXT NOT NULL DEFAULT '', source TEXT UNIQUE, created REAL NOT NULL, updated REAL NOT NULL, closed REAL,
    UNIQUE (project_key, number)
);
"""


def workspace():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App")
    store.create_project(connection, "WEB", "Web")
    return connection


def titles(tickets):
    return sorted(ticket["title"] for ticket in tickets)


class TicketFieldTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.platform = organise.create_area(self.connection, "Platform")
        self.sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")

    def test_area_iteration_estimate_and_start_are_stored_and_logged(self):
        ticket = store.create_ticket(self.connection, "APP", "t", area="Platform", iteration="sprint 1", estimate="3", start="2026-11-10")
        self.assertEqual((ticket["area"], ticket["iteration"], ticket["estimate"], ticket["start"]), ("Platform", "Sprint 1", 3.0, "2026-11-10"))
        edited = store.update_ticket(self.connection, ticket["key"], {"area": "", "iteration": "", "estimate": 5})
        self.assertEqual((edited["area"], edited["iteration"], edited["estimate"]), ("", "", 5.0))
        logged = {event["field"]: (event["old"], event["new"]) for event in store.ticket_events(self.connection, ticket["key"])}
        self.assertEqual((logged["area"], logged["iteration"], logged["estimate"]), (("Platform", ""), ("Sprint 1", ""), ("3", "5")))

    def test_an_iteration_from_another_project_is_refused(self):
        with self.assertRaises(store.LedgerError):
            store.create_ticket(self.connection, "WEB", "t", iteration=self.sprint["id"])
        ticket = store.create_ticket(self.connection, "WEB", "t")
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, ticket["key"], {"iteration": self.sprint["id"]})

    def test_bad_values_are_refused(self):
        for fields in ({"estimate": "lots"}, {"estimate": -1}, {"estimate": True}, {"area": "Nope"}, {"area": 999}, {"start": "soon"},
                       {"iteration": "Nope"}, {"start": "2026-12-02", "due": "2026-12-01"}):
            with self.assertRaises(store.LedgerError, msg=str(fields)):
                store.create_ticket(self.connection, "APP", "t", **fields)
        ticket = store.create_ticket(self.connection, "APP", "t", due="2026-12-01")
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, ticket["key"], {"start": "2026-12-05"})

    def test_progress_rolls_up_all_descendants_and_skips_cancelled(self):
        epic = store.create_ticket(self.connection, "APP", "epic", type="epic")
        story = store.create_ticket(self.connection, "APP", "story", type="story", parent_key=epic["key"], estimate=5)
        done = store.create_ticket(self.connection, "APP", "task done", parent_key=story["key"], estimate=2, status="done")
        store.create_ticket(self.connection, "APP", "task open", parent_key=story["key"], estimate=3)
        store.create_ticket(self.connection, "APP", "dropped", parent_key=story["key"], estimate=8, status="cancelled")
        progress = store.get_ticket(self.connection, epic["key"])["progress"]
        self.assertEqual(progress, {"total": 3, "done": 1, "points": 10.0, "points_done": 2.0})
        self.assertEqual(store.get_ticket(self.connection, done["key"])["progress"]["total"], 0)

    def test_tree_nests_children_to_depth(self):
        epic = store.create_ticket(self.connection, "APP", "epic", type="epic")
        story = store.create_ticket(self.connection, "APP", "story", parent_key=epic["key"])
        store.create_ticket(self.connection, "APP", "task", parent_key=story["key"])
        tree = store.ticket_tree(self.connection, epic["key"])
        self.assertEqual([tree["title"], tree["children"][0]["title"], tree["children"][0]["children"][0]["title"]], ["epic", "story", "task"])
        self.assertEqual(store.ticket_tree(self.connection, epic["key"], depth=1)["children"][0]["children"], [])

    def test_filters_by_area_subtree_and_iteration(self):
        tools = organise.create_area(self.connection, "Tools", parent=self.platform["id"])
        store.create_ticket(self.connection, "APP", "in platform", area=self.platform["id"])
        store.create_ticket(self.connection, "APP", "in tools", area=tools["id"], iteration=self.sprint["id"])
        store.create_ticket(self.connection, "APP", "nowhere")
        self.assertEqual(titles(store.list_tickets(self.connection, area="Platform")), ["in platform", "in tools"])
        self.assertEqual(titles(store.list_tickets(self.connection, area="Platform / Tools")), ["in tools"])
        self.assertEqual(titles(store.list_tickets(self.connection, iteration=self.sprint["id"])), ["in tools"])
        with self.assertRaises(store.LedgerError):
            store.list_tickets(self.connection, iteration="sprint")

    def test_project_fields_and_update(self):
        project = store.update_project(self.connection, "APP", {"lead": "ann", "status": "archived", "start": "2026-01-01", "target": "2026-06-30"})
        self.assertEqual((project["lead"], project["status"], project["target"]), ("ann", "archived", "2026-06-30"))
        for changes in ({"status": "paused"}, {"start": "2026-07-01"}, {"key": "NEW"}, {"name": "  "}):
            with self.assertRaises(store.LedgerError, msg=str(changes)):
                store.update_project(self.connection, "APP", changes)

    def test_an_old_database_is_upgraded_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            old = sqlite3.connect(path)
            old.executescript(OLD_SCHEMA)
            old.execute("INSERT INTO projects VALUES ('OLD', 'Old', '', 1)")
            old.execute("INSERT INTO tickets (project_key, number, title, type, status, priority, created, updated) VALUES ('OLD', 1, 'kept', 'task', 'todo', 'low', 1, 1)")
            old.commit()
            old.close()
            upgraded = store.connect(path)
            ticket = store.get_ticket(upgraded, "OLD-1")
            self.assertEqual((ticket["title"], ticket["area"], ticket["iteration"], ticket["estimate"]), ("kept", "", "", None))
            self.assertEqual(store.get_project(upgraded, "OLD")["status"], "active")
            self.assertEqual(store.create_ticket(upgraded, "OLD", "next", estimate=1)["key"], "OLD-2")
            upgraded.close()


class AreaTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_area_tags_are_normalised_and_survive_other_edits(self):
        area = organise.create_area(self.connection, "Pazaak", tags="Resonite Research, games")
        self.assertEqual(area["tags"], ["games", "resonite-research"])
        renamed = organise.update_area(self.connection, area["id"], {"name": "Pazaak build"})
        self.assertEqual(renamed["tags"], ["games", "resonite-research"])
        cleared = organise.update_area(self.connection, area["id"], {"tags": ""})
        self.assertEqual(cleared["tags"], [])
        with self.assertRaises(store.LedgerError):
            organise.update_area(self.connection, area["id"], {"tags": "bad/tag"})

    def test_areas_nest_and_report_paths_and_counts(self):
        platform = organise.create_area(self.connection, "Platform")
        tools = organise.create_area(self.connection, "Tools", parent="Platform")
        store.create_ticket(self.connection, "APP", "a", area=tools["id"])
        store.create_ticket(self.connection, "APP", "b", area=platform["id"], status="done")
        organise.create_board(self.connection, "Platform", "Main")
        areas = {area["path"]: area for area in organise.list_areas(self.connection)}
        self.assertEqual(sorted(areas), ["Platform", "Platform / Tools"])
        self.assertEqual((areas["Platform"]["tickets"], areas["Platform"]["open_tickets"], areas["Platform"]["boards"]), (2, 1, 1))
        self.assertEqual((areas["Platform / Tools"]["depth"], areas["Platform / Tools"]["tickets"]), (1, 1))

    def test_names_are_checked(self):
        organise.create_area(self.connection, "Platform")
        for name in ("platform", "A / B", "  ", "x" * 81, 5):
            with self.assertRaises(store.LedgerError, msg=str(name)):
                organise.create_area(self.connection, name)
        organise.create_area(self.connection, "Platform", parent="Platform")

    def test_an_area_cannot_move_under_itself(self):
        platform = organise.create_area(self.connection, "Platform")
        tools = organise.create_area(self.connection, "Tools", parent=platform["id"])
        for parent in (platform["id"], tools["id"]):
            with self.assertRaises(store.LedgerError):
                organise.update_area(self.connection, platform["id"], {"parent": parent})
        moved = organise.update_area(self.connection, tools["id"], {"parent": "", "name": "Toolbox"})
        self.assertEqual(moved["path"], "Toolbox")

    def test_delete_refuses_children_and_boards_then_unassigns_tickets(self):
        platform = organise.create_area(self.connection, "Platform")
        child = organise.create_area(self.connection, "Child", parent=platform["id"])
        board = organise.create_board(self.connection, child["id"], "B")
        ticket = store.create_ticket(self.connection, "APP", "t", area=child["id"])
        for area_id in (platform["id"], child["id"]):
            with self.assertRaises(store.LedgerError):
                organise.delete_area(self.connection, area_id)
        organise.delete_board(self.connection, board["id"])
        organise.delete_area(self.connection, child["id"])
        self.assertEqual(store.get_ticket(self.connection, ticket["key"])["area"], "")
        with self.assertRaises(store.NotFound):
            organise.get_area(self.connection, child["id"])

    def test_the_organisation_has_a_name(self):
        self.assertEqual(organise.get_organisation(self.connection)["name"], organise.DEFAULT_ORGANISATION)
        self.assertEqual(organise.set_organisation(self.connection, "Acme Games")["name"], "Acme Games")
        with self.assertRaises(store.LedgerError):
            organise.set_organisation(self.connection, " ")


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.platform = organise.create_area(self.connection, "Platform")
        self.tools = organise.create_area(self.connection, "Tools", parent=self.platform["id"])
        self.web = organise.create_area(self.connection, "Web")
        self.sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")

    def add(self, title, **fields):
        return store.create_ticket(self.connection, fields.pop("project", "APP"), title, **fields)

    def test_an_area_board_holds_the_area_and_its_sub_areas(self):
        self.add("platform bug", area=self.platform["id"], type="bug")
        self.add("tools task", area=self.tools["id"])
        self.add("web task", area=self.web["id"])
        self.add("loose")
        board = organise.create_board(self.connection, self.platform["id"], "All")
        self.assertEqual(titles(organise.board_tickets(self.connection, board["id"])), ["platform bug", "tools task"])
        self.assertEqual(board["tickets"], 2)

    def test_rules_narrow_the_board(self):
        self.add("bug a", area=self.platform["id"], type="bug", labels="auth", assignee="Ann", priority="high", iteration=self.sprint["id"])
        self.add("bug b", area=self.platform["id"], type="bug", labels="ui", assignee="bob")
        self.add("task c", area=self.platform["id"], labels="auth")

        def held(rules):
            board = organise.create_board(self.connection, self.platform["id"], f"b{len(json.dumps(rules))}{abs(hash(json.dumps(rules))) % 999}", rules=rules)
            return titles(organise.board_tickets(self.connection, board["id"]))

        self.assertEqual(held({"types": ["bug"]}), ["bug a", "bug b"])
        self.assertEqual(held({"labels": ["auth"]}), ["bug a", "task c"])
        self.assertEqual(held({"labels": ["auth", "ui"], "types": ["bug"]}), ["bug a", "bug b"])
        self.assertEqual(held({"assignee": "ann"}), ["bug a"])
        self.assertEqual(held({"priorities": ["high"]}), ["bug a"])
        self.assertEqual(held({"iteration": self.sprint["id"]}), ["bug a"])

    def test_scope_all_ignores_the_area_and_a_parent_rule_takes_descendants(self):
        epic = self.add("epic", type="epic")
        story = self.add("story", parent_key=epic["key"])
        self.add("task", parent_key=story["key"])
        self.add("unrelated")
        self.add("other project", project="WEB")
        everything = organise.create_board(self.connection, self.web["id"], "Epic board", rules={"scope": "all", "parent": epic["key"]})
        self.assertEqual(titles(organise.board_tickets(self.connection, everything["id"])), ["story", "task"])
        one_project = organise.create_board(self.connection, self.web["id"], "APP everything", rules={"scope": "all", "project": "APP"})
        self.assertEqual(len(organise.board_tickets(self.connection, one_project["id"])), 4)

    def test_pinned_tickets_are_always_on_the_board(self):
        outside = self.add("outside", area=self.web["id"])
        board = organise.create_board(self.connection, self.platform["id"], "Pins", rules={"types": ["bug"]})
        self.assertEqual(organise.board_tickets(self.connection, board["id"]), [])
        pinned = organise.pin_ticket(self.connection, board["id"], outside["key"])
        self.assertEqual((pinned["pinned_keys"], pinned["pinned"]), ([outside["key"]], 1))
        organise.pin_ticket(self.connection, board["id"], outside["key"])
        self.assertEqual(organise.get_board(self.connection, board["id"])["pinned"], 1)
        self.assertEqual(organise.unpin_ticket(self.connection, board["id"], outside["key"])["tickets"], 0)

    def test_statuses_choose_the_columns_and_count_the_hidden(self):
        self.add("todo", area=self.platform["id"], status="todo")
        self.add("done", area=self.platform["id"], status="done")
        board = organise.create_board(self.connection, self.platform["id"], "Two columns", statuses=["todo", "in_progress"])
        loaded = organise.get_board(self.connection, board["id"])
        self.assertEqual((list(loaded["columns"]), loaded["hidden"], len(loaded["columns"]["todo"])), (["todo", "in_progress"], 1, 1))
        every = organise.create_board(self.connection, self.platform["id"], "Every column")
        self.assertEqual(every["statuses"], list(store.STATUSES))

    def test_bad_boards_are_refused(self):
        for arguments in ({"area": None, "name": "x"}, {"area": "Nope", "name": "x"}, {"area": "Platform", "name": " "},
                          {"area": "Platform", "name": "x", "rules": {"colour": "red"}}, {"area": "Platform", "name": "x", "rules": {"types": ["saga"]}},
                          {"area": "Platform", "name": "x", "rules": {"project": "NOPE"}}, {"area": "Platform", "name": "x", "rules": {"parent": "APP-99"}},
                          {"area": "Platform", "name": "x", "rules": {"iteration": 999}}, {"area": "Platform", "name": "x", "rules": []},
                          {"area": "Platform", "name": "x", "statuses": ["flying"]}):
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                organise.create_board(self.connection, **arguments)
        organise.create_board(self.connection, "Platform", "Same")
        with self.assertRaises(store.LedgerError):
            organise.create_board(self.connection, "Platform", "same")
        organise.create_board(self.connection, "Web", "Same")

    def test_update_and_delete(self):
        board = organise.create_board(self.connection, "Platform", "Old")
        ticket = self.add("t")
        organise.pin_ticket(self.connection, board["id"], ticket["key"])
        edited = organise.update_board(self.connection, board["id"], {"name": "New", "area": "Web", "rules": {"types": ["bug"]}, "statuses": ["todo"]})
        self.assertEqual((edited["name"], edited["area"], edited["rules"], edited["statuses"]), ("New", "Web", {"types": ["bug"]}, ["todo"]))
        organise.delete_board(self.connection, board["id"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM board_items").fetchone()[0], 0)
        with self.assertRaises(store.NotFound):
            organise.get_board(self.connection, board["id"])

    def test_deleting_a_ticket_unpins_it(self):
        board = organise.create_board(self.connection, "Platform", "B")
        ticket = self.add("t")
        organise.pin_ticket(self.connection, board["id"], ticket["key"])
        store.delete_ticket(self.connection, ticket["key"])
        self.assertEqual(organise.get_board(self.connection, board["id"])["pinned"], 0)


class IterationTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_validation(self):
        organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")
        for arguments in ({"name": "sprint 1"}, {"start": "2026-12-01", "end": "2026-11-01"}, {"start": ""}, {"end": "later"},
                          {"state": "paused"}, {"project": "NOPE"}, {"name": " "}):
            fields = {"project": "APP", "name": "Sprint 2", "start": "2026-11-23", "end": "2026-12-04", **arguments}
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                organise.create_iteration(self.connection, **fields)
        organise.create_iteration(self.connection, "WEB", "Sprint 1", "2026-11-09", "2026-11-20")

    def test_stats_count_tickets_and_points(self):
        sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")
        store.create_ticket(self.connection, "APP", "a", iteration=sprint["id"], estimate=3, status="done")
        store.create_ticket(self.connection, "APP", "b", iteration=sprint["id"], estimate=5)
        store.create_ticket(self.connection, "APP", "c", iteration=sprint["id"], estimate=8, status="cancelled")
        loaded = organise.get_iteration(self.connection, sprint["id"])
        self.assertEqual((loaded["tickets"], loaded["done"], loaded["points"], loaded["points_done"]), (2, 1, 8.0, 3.0))

    def test_update_and_delete_unassigns(self):
        sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")
        ticket = store.create_ticket(self.connection, "APP", "a", iteration=sprint["id"])
        started = organise.update_iteration(self.connection, sprint["id"], {"state": "active", "goal": "ship it"})
        self.assertEqual((started["state"], started["goal"]), ("active", "ship it"))
        with self.assertRaises(store.LedgerError):
            organise.update_iteration(self.connection, sprint["id"], {"end": "2026-11-01"})
        organise.delete_iteration(self.connection, sprint["id"])
        self.assertEqual(store.get_ticket(self.connection, ticket["key"])["iteration"], "")

    def test_the_plan_separates_backlog_from_iterations_and_hides_closed_work(self):
        sprint = organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")
        store.create_ticket(self.connection, "APP", "planned", iteration=sprint["id"], priority="high")
        store.create_ticket(self.connection, "APP", "finished", iteration=sprint["id"], status="done")
        store.create_ticket(self.connection, "APP", "waiting")
        store.create_ticket(self.connection, "APP", "old", status="cancelled")
        store.create_ticket(self.connection, "WEB", "other project")
        plan = organise.plan(self.connection, "APP")
        self.assertEqual([item["title"] for item in plan["iterations"][0]["items"]], ["planned"])
        self.assertEqual((plan["iterations"][0]["closed_items"], titles(plan["backlog"])), (1, ["waiting"]))

    def test_the_roadmap_lists_dated_epics_and_the_range(self):
        organise.create_iteration(self.connection, "APP", "Sprint 1", "2026-11-09", "2026-11-20")
        epic = store.create_ticket(self.connection, "APP", "dated epic", type="epic", start="2026-10-01", due="2026-12-31")
        store.create_ticket(self.connection, "APP", "child", parent_key=epic["key"], status="done", estimate=2)
        store.create_ticket(self.connection, "APP", "undated epic", type="epic")
        store.create_ticket(self.connection, "APP", "plain task", start="2027-01-01")
        roadmap = organise.roadmap(self.connection, "APP")
        self.assertEqual([item["title"] for item in roadmap["epics"]], ["dated epic"])
        self.assertEqual((roadmap["unscheduled_epics"], roadmap["range"]), (1, {"start": "2026-10-01", "end": "2026-12-31"}))
        self.assertEqual(roadmap["epics"][0]["progress"]["done"], 1)


class TagTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.platform = organise.create_area(self.connection, "Platform")

    def test_unregistered_labels_show_up_with_counts(self):
        store.create_ticket(self.connection, "APP", "a", labels="auth,ui")
        store.create_ticket(self.connection, "APP", "b", labels="auth", status="done")
        manage.create_tag(self.connection, "ui", color="#4CC2FF", description="Interface")
        tags = {tag["name"]: tag for tag in manage.list_tags(self.connection)}
        self.assertEqual((tags["auth"]["tickets"], tags["auth"]["open_tickets"], tags["auth"]["registered"]), (2, 1, False))
        self.assertEqual((tags["ui"]["color"], tags["ui"]["registered"]), ("#4cc2ff", True))

    def test_bad_tags_are_refused(self):
        manage.create_tag(self.connection, "auth")
        for arguments in ({"name": "auth"}, {"name": "a,b"}, {"name": " "}, {"name": "x" * 41}, {"name": "ok", "color": "red"}, {"name": "ok", "color": "#12"}):
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                manage.create_tag(self.connection, **arguments)
        with self.assertRaises(store.NotFound):
            manage.get_tag(self.connection, "nothing")

    def test_rename_rewrites_tickets_and_boards_and_logs_it(self):
        ticket = store.create_ticket(self.connection, "APP", "a", labels="auth,ui")
        board = organise.create_board(self.connection, "Platform", "B", rules={"labels": ["auth"]})
        renamed = manage.update_tag(self.connection, "auth", {"name": "login", "color": "#ff0000"}, actor="tester")
        self.assertEqual((renamed["name"], renamed["color"], renamed["tickets"], renamed["boards"]), ("login", "#ff0000", 1, 1))
        self.assertEqual(store.get_ticket(self.connection, ticket["key"])["labels"], ["login", "ui"])
        self.assertEqual(organise.get_board(self.connection, board["id"])["rules"]["labels"], ["login"])
        last = store.ticket_events(self.connection, ticket["key"])[-1]
        self.assertEqual((last["field"], last["actor"]), ("labels", "tester"))
        with self.assertRaises(store.NotFound):
            manage.get_tag(self.connection, "auth")
        with self.assertRaises(store.LedgerError):
            manage.update_tag(self.connection, "login", {"name": "ui"})

    def test_merge_joins_two_tags_without_duplicates(self):
        both = store.create_ticket(self.connection, "APP", "both", labels="a,b")
        only = store.create_ticket(self.connection, "APP", "only a", labels="a")
        merged = manage.merge_tags(self.connection, "a", "b")
        self.assertEqual((merged["name"], merged["tickets"]), ("b", 2))
        self.assertEqual(store.get_ticket(self.connection, both["key"])["labels"], ["b"])
        self.assertEqual(store.get_ticket(self.connection, only["key"])["labels"], ["b"])
        with self.assertRaises(store.LedgerError):
            manage.merge_tags(self.connection, "b", "b")

    def test_delete_removes_the_tag_from_tickets_and_board_rules(self):
        ticket = store.create_ticket(self.connection, "APP", "a", labels="gone,stay")
        board = organise.create_board(self.connection, "Platform", "B", rules={"labels": ["gone"], "types": ["bug"]})
        result = manage.delete_tag(self.connection, "gone")
        self.assertEqual((result["tickets_changed"], result["boards_changed"]), (1, 1))
        self.assertEqual(store.get_ticket(self.connection, ticket["key"])["labels"], ["stay"])
        self.assertEqual(organise.get_board(self.connection, board["id"])["rules"], {"types": ["bug"]})


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_create_list_and_scope(self):
        manage.create_template(self.connection, name="Bug", type="bug", priority="high", labels="bug", body="Steps:")
        manage.create_template(self.connection, name="App only", project="APP")
        manage.create_template(self.connection, name="Web only", project="WEB")
        self.assertEqual([t["name"] for t in manage.list_templates(self.connection, project="APP")], ["App only", "Bug"])
        self.assertEqual(len(manage.list_templates(self.connection)), 3)
        with self.assertRaises(store.LedgerError):
            manage.create_template(self.connection, name="bug")
        manage.create_template(self.connection, name="Bug", project="APP")

    def test_bad_templates_are_refused(self):
        for fields in ({"name": " "}, {"name": "x", "type": "saga"}, {"name": "x", "project": "NOPE"}, {"name": "x", "colour": "red"},
                       {"name": "x", "estimate": "lots"}, {"name": "x", "labels": 5}):
            with self.assertRaises(store.LedgerError, msg=str(fields)):
                manage.create_template(self.connection, **fields)

    def test_update_and_delete(self):
        template = manage.create_template(self.connection, name="Bug", type="bug")
        edited = manage.update_template(self.connection, template["id"], {"name": "Defect", "priority": "critical", "estimate": 2, "labels": ["a", "b"]})
        self.assertEqual((edited["name"], edited["priority"], edited["estimate"], edited["labels"], edited["type"]), ("Defect", "critical", 2.0, ["a", "b"], "bug"))
        manage.delete_template(self.connection, template["id"])
        with self.assertRaises(store.NotFound):
            manage.get_template(self.connection, template["id"])

    def test_applying_a_template_fills_blanks_and_keeps_overrides(self):
        template = manage.create_template(self.connection, name="Bug", type="bug", priority="high", labels="bug", body="Steps:", title="Bug: ", estimate=2)
        merged = manage.apply_template(self.connection, template["id"], {"project": "APP", "title": "Crash on start", "priority": "low", "template": template["id"]})
        ticket = store.create_ticket(self.connection, **{"project_key": merged.pop("project"), **{"title": merged.pop("title")}, **merged})
        self.assertEqual((ticket["title"], ticket["type"], ticket["priority"], ticket["labels"], ticket["body"], ticket["estimate"]),
                         ("Crash on start", "bug", "low", ["bug"], "Steps:", 2.0))

    def test_a_project_template_refuses_other_projects_and_a_shared_one_needs_a_project(self):
        tied = manage.create_template(self.connection, name="Tied", project="APP")
        shared = manage.create_template(self.connection, name="Shared")
        with self.assertRaises(store.LedgerError):
            manage.apply_template(self.connection, tied["id"], {"project": "WEB"})
        with self.assertRaises(store.LedgerError):
            manage.apply_template(self.connection, shared["id"], {})
        self.assertEqual(manage.apply_template(self.connection, tied["id"], {})["project"], "APP")

    def test_default_templates_are_added_once(self):
        first = manage.seed_default_templates(self.connection)
        self.assertEqual(len(first), len(manage.DEFAULT_TEMPLATES))
        self.assertEqual(manage.seed_default_templates(self.connection), [])
        self.assertIn("Bug report", [template["name"] for template in manage.list_templates(self.connection)])


class PlanningApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()

    def post(self, path, payload):
        return self.client.post(path, json=payload)

    def test_a_fresh_server_has_an_organisation_and_default_templates(self):
        self.assertEqual(self.client.get("/api/organisation").get_json()["name"], organise.DEFAULT_ORGANISATION)
        self.assertEqual(len(self.client.get("/api/templates").get_json()), len(manage.DEFAULT_TEMPLATES))

    def test_the_whole_hierarchy_through_http(self):
        self.post("/api/projects", {"key": "APP", "name": "App"})
        area = self.post("/api/areas", {"name": "Platform"}).get_json()
        sprint = self.post("/api/iterations", {"project": "APP", "name": "Sprint 1", "start": "2026-11-09", "end": "2026-11-20"}).get_json()
        board = self.post("/api/boards", {"area": area["id"], "name": "Bugs", "rules": {"types": ["bug"]}}).get_json()
        epic = self.post("/api/tickets", {"project": "APP", "title": "Epic", "type": "epic", "area": "Platform", "start": "2026-11-01", "due": "2026-12-01"}).get_json()
        bug = self.post("/api/tickets", {"project": "APP", "title": "Crash", "type": "bug", "area": "Platform", "iteration": sprint["id"],
                                         "estimate": 3, "parent": epic["key"]}).get_json()
        self.assertEqual((bug["area"], bug["iteration"], bug["estimate"], bug["parent_key"]), ("Platform", "Sprint 1", 3.0, epic["key"]))
        loaded = self.client.get(f"/api/boards/{board['id']}").get_json()
        self.assertEqual([t["key"] for t in loaded["columns"]["backlog"]], [bug["key"]])
        self.assertEqual(self.client.get(f"/api/tickets/{epic['key']}").get_json()["progress"]["total"], 1)
        self.assertEqual(self.client.get(f"/api/tickets/{epic['key']}/tree").get_json()["children"][0]["key"], bug["key"])
        self.assertEqual(len(self.client.get("/api/tickets?area=Platform").get_json()), 2)
        self.assertEqual(self.client.get("/api/plan?project=APP").get_json()["iterations"][0]["items"][0]["key"], bug["key"])
        self.assertEqual(self.client.get("/api/roadmap?project=APP").get_json()["epics"][0]["key"], epic["key"])
        overview = self.client.get("/api/overview").get_json()
        self.assertEqual((len(overview["areas"]), len(overview["boards"]), overview["projects"][0]["key"]), (1, 1, "APP"))
        self.assertEqual(self.client.patch("/api/projects/APP", json={"lead": "ann"}).get_json()["lead"], "ann")

    def test_tickets_can_be_created_from_a_template(self):
        self.post("/api/projects", {"key": "APP", "name": "App"})
        template = next(t for t in self.client.get("/api/templates").get_json() if t["name"] == "Bug report")
        ticket = self.post("/api/tickets", {"project": "APP", "title": "Crash", "template": template["id"]}).get_json()
        self.assertEqual((ticket["type"], ticket["priority"], ticket["labels"]), ("bug", "high", ["bug"]))
        self.assertIn("Steps to reproduce", ticket["body"])
        self.assertEqual(self.post("/api/tickets", {"project": "APP", "title": "x", "template": 999}).status_code, 404)

    def test_tags_through_http(self):
        self.post("/api/projects", {"key": "APP", "name": "App"})
        self.post("/api/tickets", {"project": "APP", "title": "t", "labels": "auth"})
        self.assertEqual(self.post("/api/tags", {"name": "ui", "color": "#112233"}).status_code, 201)
        self.assertEqual(self.client.patch("/api/tags/auth", json={"name": "login"}).get_json()["tickets"], 1)
        self.assertEqual(self.post("/api/tags/login/merge", {"into": "ui"}).get_json()["tickets"], 1)
        self.assertEqual(self.client.delete("/api/tags/ui").get_json()["tickets_changed"], 1)
        self.assertEqual(self.client.delete("/api/tags/ui").status_code, 404)

    def test_new_routes_refuse_with_json_errors(self):
        attempts = (
            self.post("/api/areas", {"name": ""}), self.post("/api/boards", {"area": 99, "name": "x"}), self.client.get("/api/areas/99"),
            self.client.delete("/api/boards/99"), self.post("/api/iterations", {"project": "NOPE"}), self.client.get("/api/plan"),
            self.post("/api/templates", {"name": "x", "type": "saga"}), self.post("/api/tags/none/merge", {"into": "other"}),
            self.client.patch("/api/projects/NOPE", json={}), self.client.get("/api/tickets?iteration=abc"),
        )
        for response in attempts:
            self.assertEqual(response.mimetype, "application/json")
            self.assertIn(response.status_code, (400, 404))
            self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
