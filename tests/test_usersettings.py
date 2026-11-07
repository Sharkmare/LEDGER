import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ledger_cli
from ledger import server, usersettings
from test_ledger import LiveServerCase

ANN = {server.ACTOR_HEADER: "Ann"}
BOB = {server.ACTOR_HEADER: "bob"}


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = server.create_app(":memory:", font_dir=tempfile.gettempdir()).test_client()

    def put(self, key, value, headers=ANN):
        return self.client.put(f"/api/settings/{key}", json={"value": value}, headers=headers)

    def test_nothing_is_set_at_first(self):
        self.assertEqual(self.client.get("/api/settings", headers=ANN).get_json(), {})

    def test_each_key_round_trips(self):
        self.put("hidden_types", ["chore", "bug"])
        self.put("hidden_statuses", ["done", "cancelled"])
        saved = self.put("sort", {"field": "priority", "direction": "desc"}).get_json()
        self.assertEqual(saved, {"hidden_types": ["bug", "chore"], "hidden_statuses": ["done", "cancelled"],
                                 "sort": {"field": "priority", "direction": "desc"}})
        self.assertEqual(self.client.get("/api/settings", headers=ANN).get_json(), saved)

    def test_a_second_put_replaces_the_first(self):
        self.put("hidden_types", ["bug"])
        self.assertEqual(self.put("hidden_types", ["chore"]).get_json(), {"hidden_types": ["chore"]})

    def test_names_are_compared_in_lowercase_and_people_do_not_share(self):
        self.put("hidden_statuses", ["done"], {server.ACTOR_HEADER: "ANN"})
        self.assertEqual(self.client.get("/api/settings", headers=ANN).get_json(), {"hidden_statuses": ["done"]})
        self.assertEqual(self.client.get("/api/settings", headers=BOB).get_json(), {})

    def test_delete_clears_one_key_only_for_that_person(self):
        self.put("hidden_types", ["bug"])
        self.put("sort", {"field": "key", "direction": "asc"})
        self.put("hidden_types", ["bug"], BOB)
        left = self.client.delete("/api/settings/hidden_types", headers=ANN).get_json()
        self.assertEqual(left, {"sort": {"field": "key", "direction": "asc"}})
        self.assertEqual(self.client.get("/api/settings", headers=BOB).get_json(), {"hidden_types": ["bug"]})

    def test_the_anonymous_actor_is_refused_with_a_hint(self):
        for response in (self.client.get("/api/settings"), self.put("sort", {"field": "", "direction": "asc"}, {}),
                         self.client.delete("/api/settings/sort"), self.client.get("/api/settings", headers={server.ACTOR_HEADER: " Anonymous "})):
            self.assertEqual(response.status_code, 400)
            self.assertIn("set your name", response.get_json()["error"])

    def test_bad_requests_are_refused_with_a_message(self):
        attempts = {
            "unknown key": self.put("theme", "dark"),
            "unknown type": self.put("hidden_types", ["saga"]),
            "unknown status": self.put("hidden_statuses", ["In Progress"]),
            "not a list": self.put("hidden_types", "bug"),
            "list of numbers": self.put("hidden_types", [1]),
            "sort not an object": self.put("sort", "priority"),
            "sort field": self.put("sort", {"field": "colour", "direction": "asc"}),
            "sort direction": self.put("sort", {"field": "key", "direction": "up"}),
            "missing value": self.client.put("/api/settings/sort", json={}, headers=ANN),
            "delete unknown key": self.client.delete("/api/settings/theme", headers=ANN),
        }
        for name, response in attempts.items():
            self.assertEqual(response.status_code, 400, name)
            self.assertTrue(response.get_json()["error"], name)
        self.assertEqual(self.client.get("/api/settings", headers=ANN).get_json(), {})

    def test_an_empty_sort_field_and_an_empty_list_are_valid(self):
        self.assertEqual(self.put("sort", {"field": "", "direction": "asc"}).status_code, 200)
        self.assertEqual(self.put("hidden_types", []).get_json()["hidden_types"], [])

    def test_the_sort_fields_match_the_interface(self):
        source = (ROOT / "ledger" / "static" / "sorting.js").read_text(encoding="utf-8")
        interface_fields = tuple(re.findall(r'\{ id: "(\w+)", label', source))
        self.assertEqual(interface_fields, usersettings.SORT_FIELDS)

    def test_the_api_help_lists_the_routes(self):
        self.assertTrue(any("/api/settings" in line for line in self.client.get("/api").get_json()["endpoints"]))


class SettingsCliTests(LiveServerCase):
    def cli(self, actor, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", actor, "--json", *arguments])
        return json.loads(buffer.getvalue())

    def test_set_list_and_clear(self):
        self.assertEqual(self.cli("cli-ann", "settings"), {})
        self.cli("cli-ann", "setting-set", "hidden_statuses", '["done"]')
        self.cli("cli-ann", "setting-set", "sort", '{"field":"priority","direction":"desc"}')
        self.assertEqual(self.cli("cli-ann", "settings"), {"hidden_statuses": ["done"], "sort": {"field": "priority", "direction": "desc"}})
        self.assertEqual(self.cli("cli-bob", "settings"), {})
        self.assertEqual(self.cli("cli-ann", "setting-clear", "hidden_statuses"), {"sort": {"field": "priority", "direction": "desc"}})

    def test_bad_values_stop_with_a_message(self):
        with self.assertRaisesRegex(SystemExit, "must be JSON"):
            self.cli("cli-ann", "setting-set", "sort", "{nope")
        with self.assertRaisesRegex(SystemExit, "unknown values"):
            self.cli("cli-ann", "setting-set", "hidden_types", '["saga"]')


if __name__ == "__main__":
    unittest.main()
