import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from test_ledger import LiveServerCase


class PlanningCliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def data(self, *arguments):
        return json.loads(self.cli("--json", *arguments))

    def test_areas_boards_iterations_and_planning_from_the_command_line(self):
        self.cli("new-project", "PLN", "Planning")
        self.data("area", "add", "Platform", "--description", "Shared services")
        self.data("area", "add", "Tools", "--parent", "Platform")
        self.assertIn("Platform", self.cli("area", "list"))
        sprint = self.data("iteration", "add", "PLN", "Sprint 1", "2026-11-09", "2026-11-20", "--goal", "Ship")
        self.assertIn("Sprint 1", self.cli("iteration", "list", "--project", "PLN"))
        epic = self.data("add", "PLN", "Epic", "--type", "epic", "--area", "Platform", "--start", "2026-11-01", "--due", "2026-12-01")
        bug = self.data("add", "PLN", "Crash", "--type", "bug", "--area", "Platform / Tools", "--iteration", "Sprint 1",
                        "--estimate", "3", "--parent", epic["key"], "--labels", "auth")
        self.assertEqual((bug["area"], bug["iteration"], bug["estimate"]), ("Platform / Tools", "Sprint 1", 3.0))
        board = self.data("board", "add", "Platform", "Bugs", "--types", "bug", "--labels", "auth", "--statuses", "backlog,todo")
        self.assertEqual((board["rules"], board["statuses"], board["tickets"]), ({"types": ["bug"], "labels": ["auth"]}, ["backlog", "todo"], 1))
        shown = self.cli("board", "show", str(board["id"]))
        self.assertIn(bug["key"], shown)
        pinned = self.data("board", "pin", str(board["id"]), epic["key"])
        self.assertEqual(pinned["pinned_keys"], [epic["key"]])
        self.assertIn("(pinned)", self.cli("board", "show", str(board["id"])))
        self.assertEqual(self.data("board", "unpin", str(board["id"]), epic["key"])["pinned"], 0)
        self.assertIn(bug["key"], self.cli("list", "--area", "Platform", "--iteration", str(sprint["id"])))
        self.assertIn("Crash", self.cli("tree", epic["key"]))
        self.assertIn("Sprint 1", self.cli("plan", "PLN"))
        self.assertIn("Epic", self.cli("roadmap", "--project", "PLN"))
        self.assertIn("PLN", self.cli("overview"))
        started = self.data("iteration", "set", str(sprint["id"]), "--state", "active")
        self.assertEqual(started["state"], "active")
        edited = self.data("edit", bug["key"], "--estimate", "5", "--iteration", "", "--area", "Platform")
        self.assertEqual((edited["estimate"], edited["iteration"], edited["area"]), (5.0, "", "Platform"))

    def test_tags_and_templates_from_the_command_line(self):
        self.cli("new-project", "TAG", "Tags")
        self.data("add", "TAG", "t", "--labels", "tagauth,tagui")
        self.assertIn("unregistered", self.cli("tag", "list"))
        self.data("tag", "add", "docs", "--color", "#112233", "--description", "Documentation")
        self.data("tag", "set", "docs", "--color", "#445566")
        renamed = self.data("tag", "rename", "tagauth", "taglogin")
        self.assertEqual(renamed["tickets"], 1)
        merged = self.data("tag", "merge", "tagui", "taglogin")
        self.assertEqual(merged["tickets"], 1)
        self.assertEqual(self.data("tag", "rm", "taglogin")["tickets_changed"], 1)
        self.data("template", "defaults")
        template = self.data("template", "add", "Crash report", "--type", "bug", "--priority", "critical", "--labels", "crash", "--body", "Stack:")
        self.assertIn("Crash report", self.cli("template", "list"))
        ticket = self.data("add", "TAG", "App closes", "--template", str(template["id"]))
        self.assertEqual((ticket["type"], ticket["priority"], ticket["labels"], ticket["body"]), ("bug", "critical", ["crash"], "Stack:"))
        self.assertEqual(self.data("template", "show", str(template["id"]))["name"], "Crash report")
        self.data("template", "rm", str(template["id"]))
        with self.assertRaises(SystemExit):
            self.cli("template", "show", str(template["id"]))

    def test_project_settings_and_refusals(self):
        self.cli("new-project", "SET", "Settings")
        updated = self.data("project-set", "SET", "--lead", "ann", "--status", "archived")
        self.assertEqual((updated["lead"], updated["status"]), ("ann", "archived"))
        for arguments in (("project-set", "SET"), ("iteration", "set", "1"), ("tag", "set", "x"), ("edit", "SET-1"),
                          ("iteration", "add", "SET", "S", "2026-12-01", "2026-11-01"), ("board", "add", "Nowhere", "B")):
            with self.assertRaises(SystemExit, msg=str(arguments)):
                self.cli(*arguments)


if __name__ == "__main__":
    unittest.main()
