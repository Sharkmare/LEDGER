import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import server

SPEC = {"openapi": "3.0.3", "info": {"title": "Pets", "version": "2"}, "paths": {"/pets": {"get": {"summary": "List pets"}}}}


class KnowledgeApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})
        self.space = self.client.post("/api/kb/spaces", json={"key": "ENG", "name": "Engineering"}).get_json()

    def page(self, title="Guide", **fields):
        return self.client.post("/api/kb/pages", json={"space": "ENG", "title": title, **fields}, headers={server.ACTOR_HEADER: "ann"}).get_json()

    def test_a_fresh_server_has_the_tools_space(self):
        keys = [space["key"] for space in self.client.get("/api/kb/spaces").get_json()]
        self.assertEqual(keys, ["TOOLS", "ENG"])
        self.assertEqual(self.client.delete("/api/kb/spaces/1").status_code, 400)

    def test_pages_templates_and_the_tree(self):
        templates = self.client.get("/api/kb/templates").get_json()
        self.assertIn("runbook", [t["id"] for t in templates])
        runbook = self.page("Deploy runbook", template="runbook")
        self.assertIn("## Symptoms", runbook["body"])
        child = self.page("Rollback", parent=runbook["id"])
        tree = self.client.get(f"/api/kb/spaces/{self.space['id']}/tree").get_json()
        self.assertEqual((tree[0]["title"], tree[0]["children"][0]["title"], child["breadcrumbs"][0]["title"]), ("Deploy runbook", "Rollback", "Deploy runbook"))
        self.assertEqual(self.client.post("/api/kb/pages", json={"space": "ENG", "title": "x", "template": "nope"}).status_code, 404)

    def test_translations_are_created_through_the_api_and_listed_only_on_request(self):
        base = self.page("Basic controls")
        japanese = self.page("Basic controls/ja", translation_of=base["id"], locale="ja")
        self.assertEqual((japanese["translation_of"], japanese["locale"]), (base["id"], "ja"))
        self.assertEqual([p["title"] for p in self.client.get("/api/kb/pages?space=ENG").get_json()], ["Basic controls"])
        self.assertEqual(len(self.client.get("/api/kb/pages?space=ENG&translations=1").get_json()), 2)
        self.assertEqual(self.client.get(f"/api/kb/pages/{base['id']}").get_json()["languages"][1]["title"], "Basic controls/ja")
        refused = self.client.post("/api/kb/pages", json={"space": "ENG", "title": "x", "translation_of": base["id"]})
        self.assertEqual(refused.status_code, 400)

    def test_children_are_paged_by_level_and_a_page_reports_its_neighbours(self):
        folder = self.page("Folder")
        leaves = [self.page(f"Leaf {n}", parent=folder["id"]) for n in range(5)]
        top = self.client.get(f"/api/kb/spaces/{self.space['id']}/children").get_json()
        self.assertEqual((top["total"], top["items"][0]["title"], top["items"][0]["child_count"]), (1, "Folder", 5))
        page = self.client.get(f"/api/kb/spaces/{self.space['id']}/children?parent={folder['id']}&offset=1&limit=2").get_json()
        self.assertEqual((page["total"], [i["title"] for i in page["items"]]), (5, ["Leaf 1", "Leaf 2"]))
        self.assertEqual(self.client.get(f"/api/kb/spaces/{self.space['id']}/children?limit=x").status_code, 400)
        detail = self.client.get(f"/api/kb/pages/{leaves[2]['id']}").get_json()
        self.assertEqual((detail["siblings"]["previous"]["title"], detail["siblings"]["next"]["title"], detail["children_total"]), ("Leaf 1", "Leaf 3", 0))

    def test_editing_keeps_history_with_comments_and_can_restore(self):
        page = self.page("Guide", body="one\ntwo")
        edited = self.client.patch(f"/api/kb/pages/{page['id']}", json={"body": "one\ntwo\nthree", "comment": "added three"}, headers={server.ACTOR_HEADER: "bob"}).get_json()
        self.assertEqual(edited["version"], 2)
        versions = self.client.get(f"/api/kb/pages/{page['id']}/versions").get_json()
        self.assertEqual([(v["version"], v["author"], v["comment"]) for v in versions], [(2, "bob", "added three"), (1, "ann", "Created")])
        diff = self.client.get(f"/api/kb/pages/{page['id']}/diff?from=1&to=2").get_json()
        self.assertEqual((diff["added"], diff["removed"]), (1, 0))
        self.assertEqual(self.client.get(f"/api/kb/pages/{page['id']}/versions/1").get_json()["body"], "one\ntwo")
        restored = self.client.post(f"/api/kb/pages/{page['id']}/restore", json={"version": 1}).get_json()
        self.assertEqual((restored["body"], restored["version"]), ("one\ntwo", 3))

    def test_viewing_feedback_favourites_and_verification(self):
        page = self.page("Policy", review_days=10)
        self.client.get(f"/api/kb/pages/{page['id']}?view=1")
        self.client.get(f"/api/kb/pages/{page['id']}")
        self.assertEqual(self.client.get(f"/api/kb/pages/{page['id']}").get_json()["views"], 1)
        voted = self.client.post(f"/api/kb/pages/{page['id']}/feedback", json={"helpful": False, "comment": "out of date"}, headers={server.ACTOR_HEADER: "bob"})
        self.assertEqual((voted.status_code, voted.get_json()["unhelpful"], voted.get_json()["my_feedback"]), (201, 1, False))
        self.assertEqual(self.client.get(f"/api/kb/pages/{page['id']}/feedback").get_json()[0]["comment"], "out of date")
        self.client.post(f"/api/kb/pages/{page['id']}/favourite", headers={server.ACTOR_HEADER: "bob"})
        mine = self.client.get("/api/kb/pages?favourite=1", headers={server.ACTOR_HEADER: "bob"}).get_json()
        others = self.client.get("/api/kb/pages?favourite=1", headers={server.ACTOR_HEADER: "cy"}).get_json()
        self.assertEqual(([p["title"] for p in mine], others), (["Policy"], []))
        verified = self.client.post(f"/api/kb/pages/{page['id']}/verify", json={"days": 30}, headers={server.ACTOR_HEADER: "ann"}).get_json()
        self.assertEqual(verified["verified_by"], "ann")
        self.assertEqual(self.client.post(f"/api/kb/pages/{page['id']}/verify").get_json()["verified_by"], "anonymous")

    def test_search_and_the_everything_finder(self):
        self.client.post("/api/tickets", json={"project": "APP", "title": "Deploy is slow"})
        self.page("Deploying safely", body="Roll out in stages")
        self.client.post("/api/kb/pages", json={"space": "TOOLS", "title": "Deploy tool", "meta": {"invoke": "deploy --go"}})
        hits = self.client.get("/api/kb/search?q=deploy").get_json()
        self.assertEqual(sorted(h["title"] for h in hits), ["Deploy tool", "Deploying safely"])
        self.assertEqual([h["title"] for h in self.client.get("/api/kb/search?q=deploy&type=tool").get_json()], ["Deploy tool"])
        found = self.client.get("/api/search?q=deploy").get_json()
        self.assertEqual(([p["title"] for p in found["pages"]], [t["title"] for t in found["tools"]], [t["title"] for t in found["tickets"]]),
                         (["Deploying safely"], ["Deploy tool"], ["Deploy is slow"]))

    def test_the_tools_category_and_its_openapi_description(self):
        created = self.client.post("/api/kb/pages", json={"space": "TOOLS", "title": "Pet service", "meta": {
            "kind": "api", "location": "external", "url": "https://pets.example.com", "openapi": {"source": "inline", "spec": SPEC}}}).get_json()
        self.client.post("/api/kb/pages", json={"space": "TOOLS", "title": "Packer", "meta": {"kind": "cli", "invoke": "packer"}})
        served = self.client.get(f"/api/kb/pages/{created['id']}/openapi").get_json()
        self.assertEqual((served["source"], served["spec"]["info"]["title"]), ("inline", "Pets"))
        self.assertEqual([t["title"] for t in self.client.get("/api/kb/tools?kind=api").get_json()], ["Pet service"])
        self.assertEqual([t["title"] for t in self.client.get("/api/kb/tools?location=machine").get_json()], ["Packer"])
        self.assertEqual([t["title"] for t in self.client.get("/api/kb/tools?q=packer").get_json()], ["Packer"])
        self.assertEqual(len(self.client.get("/api/kb/tools").get_json()), 2)

    def test_the_overview_and_deletion(self):
        parent = self.page("Parent")
        self.page("Child", parent=parent["id"])
        overview = self.client.get("/api/kb/overview").get_json()
        self.assertEqual((overview["counts"]["pages"], [s["key"] for s in overview["spaces"]]), (2, ["TOOLS", "ENG"]))
        self.assertEqual(self.client.delete(f"/api/kb/pages/{parent['id']}").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/kb/pages/{parent['id']}?cascade=1").get_json()["pages_removed"], 2)

    def test_bad_requests_get_json_errors(self):
        page = self.page()
        attempts = (
            self.client.get("/api/kb/pages/999"), self.client.patch("/api/kb/pages/999", json={}), self.client.get(f"/api/kb/pages/{page['id']}/diff"),
            self.client.get(f"/api/kb/pages/{page['id']}/diff?from=a&to=2"), self.client.get(f"/api/kb/pages/{page['id']}/versions/9"),
            self.client.post(f"/api/kb/pages/{page['id']}/feedback", json={"helpful": "yes"}), self.client.post("/api/kb/pages", json={"space": "NOPE", "title": "x"}),
            self.client.post("/api/kb/spaces", json={"key": "x", "name": "x"}), self.client.get(f"/api/kb/pages/{page['id']}/openapi"),
            self.client.get("/api/kb/pages?limit=many"), self.client.get("/api/kb/pages?order=random"), self.client.get("/api/kb/spaces/999/tree"),
            self.client.post(f"/api/kb/pages/{page['id']}/restore", json={"version": 77}),
        )
        for response in attempts:
            self.assertEqual(response.mimetype, "application/json")
            self.assertIn(response.status_code, (400, 404))
            self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
