import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import dashmodules, openapi, server
from tests.test_dashmodules import BUILTIN_IDS, restore_builtin_modules

CUSTOM = """
MODULE = {"id": "pulse", "title": "Pulse", "description": "Ticket total", "settings": [{"name": "days", "kind": "number", "default": 3, "min": 1, "max": 9}]}

def data(connection, settings, filters, now):
    return {"tickets": connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], "days": settings["days"]}
"""


class ModuleApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(restore_builtin_modules)
        self.extra = Path(self.directory.name) / "extra"
        self.extra.mkdir()
        (self.extra / "pulse.py").write_text(CUSTOM, encoding="utf-8")
        (self.extra / "pulse.js").write_text("registerDashboardModule('pulse', { render: () => 'ok' });", encoding="utf-8")
        (self.extra / "broken.py").write_text("MODULE = {", encoding="utf-8")
        self.client = self.start([dashmodules.DEFAULT_FOLDER, self.extra])
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})

    def start(self, folders):
        with mock.patch.object(dashmodules.log, "warning"):
            return server.create_app(":memory:", font_dir=self.directory.name, module_folders=folders).test_client()

    def test_the_listing_names_every_loaded_module_and_every_failure(self):
        listing = self.client.get("/api/modules").get_json()
        self.assertEqual([module["id"] for module in listing["modules"]], [*BUILTIN_IDS, "pulse"])
        self.assertEqual([(f["file"], bool(f["error"])) for f in listing["failures"]], [("broken.py", True)])
        self.assertEqual(listing["folders"], [str(dashmodules.DEFAULT_FOLDER), str(self.extra)])
        pulse = listing["modules"][-1]
        self.assertEqual((pulse["title"], pulse["script"], pulse["settings"][0]["default"]), ("Pulse", "/api/modules/pulse/script", 3))

    def test_a_fresh_server_loads_only_the_folders_it_was_given(self):
        listing = self.start([self.extra]).get("/api/modules").get_json()
        self.assertEqual([module["id"] for module in listing["modules"]], ["pulse"])

    def test_a_server_without_the_builtin_modules_still_starts_and_adds_dashboards_later(self):
        client = self.start([self.extra])
        self.assertEqual(client.get("/api/dashboards").get_json(), [])
        with mock.patch.object(dashmodules.log, "warning") as warned:
            self.assertEqual(client.post("/api/dashboards/defaults", json={}).get_json(), [])
        self.assertEqual(warned.call_count, 2)

    def test_a_broken_module_does_not_stop_the_server_starting(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboards").status_code, 200)

    def test_the_script_route_serves_the_modules_javascript(self):
        response = self.client.get("/api/modules/pulse/script")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/javascript")
        self.assertIn("registerDashboardModule('pulse'", response.data.decode("utf-8"))
        self.assertTrue(self.client.get("/api/modules/count/script").data.decode("utf-8").startswith('registerDashboardModule("count"'))

    def test_the_script_route_refuses_unknown_modules_and_traversal(self):
        for name in ("nope", "broken", "..%2Fserver", "%2e%2e"):
            self.assertEqual(self.client.get(f"/api/modules/{name}/script").status_code, 404, name)

    def test_a_custom_module_works_as_a_metric_and_in_a_dashboard(self):
        self.client.post("/api/tickets", json={"project": "APP", "title": "one"})
        metric = self.client.post("/api/metrics", json={"kind": "pulse", "days": 5}).get_json()
        self.assertEqual(metric["data"], {"tickets": 1, "days": 5})
        created = self.client.post("/api/dashboards", json={"name": "Mine", "widgets": [{"kind": "pulse"}]}).get_json()
        values = self.client.get(f"/api/dashboards/{created['id']}/data").get_json()
        self.assertEqual(values["results"]["w1"], {"tickets": 1, "days": 3})
        refused = self.client.post("/api/metrics", json={"kind": "pulse", "days": 10})
        self.assertEqual(refused.status_code, 400)

    def test_an_unknown_kind_names_the_loaded_modules(self):
        response = self.client.post("/api/metrics", json={"kind": "pie"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("pulse", response.get_json()["error"])

    def test_the_default_dashboards_are_built_from_the_modules(self):
        names = [dashboard["name"] for dashboard in self.client.get("/api/dashboards").get_json()]
        self.assertEqual(names, ["Overview", "Delivery"])
        first = self.client.get("/api/dashboards/1/data").get_json()
        self.assertFalse([key for key, value in first["results"].items() if "error" in value and "burndown" not in value["error"] and "iteration" not in value["error"]])

    def test_the_routes_are_described_in_the_openapi_document_and_help(self):
        spec = openapi.build_spec()
        self.assertIn("/api/modules", spec["paths"])
        self.assertIn("/api/modules/{module_id}/script", spec["paths"])
        self.assertIn("ModuleListing", spec["components"]["schemas"])
        help_text = " ".join(self.client.get("/api").get_json()["endpoints"])
        self.assertIn("/api/modules ", help_text)
        self.assertIn("/api/modules/<id>/script", help_text)


if __name__ == "__main__":
    unittest.main()
