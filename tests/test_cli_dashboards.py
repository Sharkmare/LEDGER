import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from test_ledger import LiveServerCase


class DashboardCliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def data(self, *arguments):
        return json.loads(self.cli("--json", *arguments))

    def test_metrics_print_numbers(self):
        self.cli("new-project", "MET", "Metrics")
        self.cli("add", "MET", "a", "--assignee", "ann", "--labels", "x", "--due", "2020-01-01", "--estimate", "3")
        self.cli("add", "MET", "b", "--assignee", "bob")
        self.assertIn("2  (", self.cli("metric", "count", "--project", "MET", "--measure", "created"))
        grouped = self.cli("metric", "group", "--project", "MET", "--group-by", "assignee")
        self.assertIn("ann", grouped)
        self.assertIn("2 tickets", grouped)
        self.assertIn("1 overdue", self.cli("metric", "overdue", "--project", "MET"))
        self.assertIn("ann", self.cli("metric", "workload", "--project", "MET", "--open"))
        self.assertIn("created", self.cli("metric", "trend", "--project", "MET", "--days", "3"))
        self.assertIn("0 to 7 days", self.cli("metric", "aging", "--project", "MET"))
        self.assertIn("lead time", self.cli("metric", "cycle", "--project", "MET"))
        self.assertIn("average", self.cli("metric", "velocity", "--project", "MET"))
        with self.assertRaises(SystemExit):
            self.cli("metric", "burndown", "--project", "MET")

    def test_dashboards_from_the_command_line(self):
        self.assertIn("Overview", self.cli("dashboard", "list"))
        created = self.data("dashboard", "add", "Mine", "--widgets", json.dumps([{"kind": "count", "title": "Open", "filters": {"open": True}}]))
        shown = self.cli("dashboard", "show", str(created["id"]))
        self.assertIn("Open", shown)
        values = self.cli("dashboard", "data", str(created["id"]))
        self.assertIn("Open", values)
        self.assertEqual(self.data("dashboard", "defaults"), [])
        self.cli("dashboard", "rm", str(created["id"]))
        with self.assertRaises(SystemExit):
            self.cli("dashboard", "show", str(created["id"]))


if __name__ == "__main__":
    unittest.main()
