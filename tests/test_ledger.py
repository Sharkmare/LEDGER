import contextlib
import io
import json
import re
import socket
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from ledger import server, store


def fresh_connection():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App work")
    return connection


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = fresh_connection()

    def test_project_tags_are_normalised_filtered_and_editable(self):
        store.create_project(self.connection, "WEB", "Web", tags="Resonite Research, avatars,avatars")
        self.assertEqual(store.get_project(self.connection, "WEB")["tags"], ["avatars", "resonite-research"])
        self.assertEqual([p["key"] for p in store.list_projects(self.connection, tag="Resonite Research")], ["WEB"])
        self.assertEqual(store.list_projects(self.connection, tag="games"), [])
        store.update_project(self.connection, "WEB", {"tags": ["games"]})
        self.assertEqual(store.get_project(self.connection, "WEB")["tags"], ["games"])
        self.assertEqual(store.get_project(self.connection, "APP")["tags"], [])

    def test_bad_project_tag_is_refused(self):
        with self.assertRaises(store.LedgerError):
            store.update_project(self.connection, "APP", {"tags": "bad/tag"})

    def test_numbers_count_up_per_project(self):
        store.create_project(self.connection, "WEB", "Web")
        first = store.create_ticket(self.connection, "APP", "one")
        second = store.create_ticket(self.connection, "APP", "two")
        other = store.create_ticket(self.connection, "WEB", "three")
        self.assertEqual([first["key"], second["key"], other["key"]], ["APP-1", "APP-2", "WEB-1"])

    def test_numbers_are_not_reused_after_delete(self):
        store.create_ticket(self.connection, "APP", "one")
        second = store.create_ticket(self.connection, "APP", "two")
        store.delete_ticket(self.connection, second["key"])
        self.assertEqual(store.create_ticket(self.connection, "APP", "three")["key"], "APP-3")

    def test_old_database_gains_the_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            old = store.connect(path)
            store.create_project(old, "OLD", "Old")
            store.create_ticket(old, "OLD", "a")
            store.create_ticket(old, "OLD", "b")
            old.execute("ALTER TABLE projects DROP COLUMN next_number")
            old.commit()
            old.close()
            reopened = store.connect(path)
            self.assertEqual(store.create_ticket(reopened, "OLD", "c")["key"], "OLD-3")
            reopened.close()

    def test_bad_values_are_refused(self):
        for field, value in (("type", "saga"), ("status", "maybe"), ("priority", "urgent")):
            with self.assertRaises(store.LedgerError, msg=field):
                store.create_ticket(self.connection, "APP", "x", **{field: value})
        with self.assertRaises(store.LedgerError):
            store.create_ticket(self.connection, "APP", "   ")
        with self.assertRaises(store.NotFound):
            store.create_ticket(self.connection, "NOPE", "x")

    def test_free_form_fields_are_validated(self):
        for field, value in (("title", ["a", "b"]), ("title", 5), ("body", {"x": 1}), ("labels", 5), ("due", "next tuesday"),
                             ("assignee", ["x"])):
            with self.assertRaises(store.LedgerError, msg=f"{field}={value!r}"):
                store.create_ticket(self.connection, "APP", **{"title": "ok", field: value})
        with self.assertRaises(store.LedgerError):
            store.create_ticket(self.connection, "APP", "x" * (store.MAX_TITLE_CHARS + 1))
        ticket = store.create_ticket(self.connection, "APP", "line one\nline two", due="2026-12-01")
        self.assertEqual((ticket["title"], ticket["due"]), ("line one line two", "2026-12-01"))

    def test_project_key_rules(self):
        for bad in ("a", "1AB", "TOOLONGKEYYY", "HI VE"):
            with self.assertRaises(store.LedgerError, msg=bad):
                store.create_project(self.connection, bad, "x")
        with self.assertRaises(store.LedgerError):
            store.create_project(self.connection, "APP", "again")

    def test_update_logs_each_changed_field_only(self):
        ticket = store.create_ticket(self.connection, "APP", "t", priority="low")
        store.update_ticket(self.connection, ticket["key"], {"priority": "low", "status": "in_progress", "assignee": "ann"}, actor="tester")
        changed = [event["field"] for event in store.ticket_events(self.connection, ticket["key"]) if event["field"] != "created"]
        self.assertEqual(sorted(changed), ["assignee", "status"])
        self.assertEqual(store.ticket_events(self.connection, ticket["key"])[-1]["actor"], "tester")

    def test_closing_sets_and_reopening_clears_closed_time(self):
        ticket = store.create_ticket(self.connection, "APP", "t")
        self.assertIsNone(ticket["closed"])
        done = store.update_ticket(self.connection, ticket["key"], {"status": "done"})
        self.assertIsNotNone(done["closed"])
        reopened = store.update_ticket(self.connection, ticket["key"], {"status": "todo"})
        self.assertIsNone(reopened["closed"])

    def test_unknown_field_is_refused(self):
        ticket = store.create_ticket(self.connection, "APP", "t")
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, ticket["key"], {"project_key": "OTHER"})

    def test_parent_cycles_are_refused(self):
        parent = store.create_ticket(self.connection, "APP", "parent", type="epic")
        child = store.create_ticket(self.connection, "APP", "child", parent_key=parent["key"])
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, parent["key"], {"parent_key": child["key"]})
        with self.assertRaises(store.LedgerError):
            store.update_ticket(self.connection, parent["key"], {"parent_key": parent["key"]})
        self.assertEqual(store.get_ticket(self.connection, parent["key"])["children"][0]["key"], child["key"])

    def test_delete_blocks_on_children_and_removes_rows(self):
        parent = store.create_ticket(self.connection, "APP", "parent")
        child = store.create_ticket(self.connection, "APP", "child", parent_key=parent["key"])
        store.add_comment(self.connection, child["key"], "a", "note")
        with self.assertRaises(store.LedgerError):
            store.delete_ticket(self.connection, parent["key"])
        store.delete_ticket(self.connection, child["key"])
        with self.assertRaises(store.NotFound):
            store.get_ticket(self.connection, child["key"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM comments").fetchone()[0], 0)

    def test_list_filters_and_priority_order(self):
        store.create_ticket(self.connection, "APP", "low one", priority="low", labels="alpha")
        store.create_ticket(self.connection, "APP", "blocker", priority="blocker", assignee="Ann")
        store.create_ticket(self.connection, "APP", "finished", status="done")
        titles = [t["title"] for t in store.list_tickets(self.connection)]
        self.assertEqual(titles[0], "blocker")
        self.assertNotIn("finished", [t["title"] for t in store.list_tickets(self.connection, include_closed=False)])
        self.assertEqual([t["title"] for t in store.list_tickets(self.connection, assignee="ann")], ["blocker"])
        self.assertEqual([t["title"] for t in store.list_tickets(self.connection, label="alpha")], ["low one"])
        self.assertEqual([t["title"] for t in store.list_tickets(self.connection, query="BLOCK")], ["blocker"])

    def test_filters_refuse_unknown_values(self):
        for arguments in ({"status": "In Progress"}, {"type": "saga"}, {"priority": "urgent"}, {"project_key": "NOPE"}):
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                store.list_tickets(self.connection, **arguments)

    def test_label_filter_matches_whole_labels_only(self):
        store.create_ticket(self.connection, "APP", "data work", labels="data")
        store.create_ticket(self.connection, "APP", "cafe work", labels="café")
        self.assertEqual(store.list_tickets(self.connection, label="a"), [])
        self.assertEqual(store.list_tickets(self.connection, label="%"), [])
        self.assertEqual([t["title"] for t in store.list_tickets(self.connection, label="café")], ["cafe work"])

    def test_search_treats_wildcards_literally_and_matches_keys(self):
        store.create_ticket(self.connection, "APP", "plain title")
        store.create_ticket(self.connection, "APP", "100% done")
        self.assertEqual([t["title"] for t in store.list_tickets(self.connection, query="%")], ["100% done"])
        self.assertEqual(store.list_tickets(self.connection, query="_"), [])
        self.assertEqual([t["key"] for t in store.list_tickets(self.connection, query="APP-1")], ["APP-1"])

    def test_source_is_unique_and_filterable(self):
        first = store.create_ticket(self.connection, "APP", "imported", source="import:1")
        with self.assertRaises(store.LedgerError):
            store.create_ticket(self.connection, "APP", "again", source="import:1")
        self.assertEqual([t["key"] for t in store.list_tickets(self.connection, source="import:1")], [first["key"]])
        self.assertEqual(store.count_tickets(self.connection, source="import:2"), 0)

    def test_links_show_on_both_ends_and_self_link_refused(self):
        one = store.create_ticket(self.connection, "APP", "one")
        two = store.create_ticket(self.connection, "APP", "two")
        store.add_link(self.connection, one["key"], two["key"], "blocks")
        self.assertEqual(store.get_ticket(self.connection, two["key"])["links"][0]["direction"], "in")
        with self.assertRaises(store.LedgerError):
            store.add_link(self.connection, one["key"], one["key"], "blocks")

    def test_board_has_every_status_column(self):
        store.create_ticket(self.connection, "APP", "t", status="blocked")
        board = store.board(self.connection)
        self.assertEqual(board["statuses"], list(store.STATUSES))
        self.assertEqual(len(board["columns"]["blocked"]), 1)

    def test_stats_split_unassigned(self):
        store.create_ticket(self.connection, "APP", "a", assignee="ann")
        store.create_ticket(self.connection, "APP", "b")
        figures = store.stats(self.connection)
        self.assertEqual((figures["by_assignee"], figures["unassigned"], figures["open"]), ({"ann": 1}, 1, 2))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = server.create_app(":memory:", font_dir=self.directory.name).test_client()
        self.client.post("/api/projects", json={"key": "APP", "name": "App"})

    def test_create_read_edit_comment_with_actor(self):
        created = self.client.post("/api/tickets", json={"project": "APP", "title": "api ticket", "labels": "a,b"},
                                   headers={server.ACTOR_HEADER: "tester"})
        self.assertEqual(created.status_code, 201)
        key = created.get_json()["key"]
        self.client.patch(f"/api/tickets/{key}", json={"status": "in_review"}, headers={server.ACTOR_HEADER: "tester"})
        self.client.post(f"/api/tickets/{key}/comments", json={"body": "looks fine"}, headers={server.ACTOR_HEADER: "tester"})
        ticket = self.client.get(f"/api/tickets/{key}").get_json()
        self.assertEqual((ticket["status"], ticket["labels"]), ("in_review", ["a", "b"]))
        self.assertEqual(ticket["comments"][0]["author"], "tester")
        self.assertEqual(self.client.get(f"/api/tickets/{key}/events").get_json()[-1]["actor"], "tester")

    def test_errors_are_json_with_the_right_status(self):
        self.assertEqual(self.client.get("/api/tickets/APP-99").status_code, 404)
        bad = self.client.post("/api/tickets", json={"project": "APP", "title": "x", "type": "saga"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("type", bad.get_json()["error"])
        self.assertEqual(self.client.post("/api/tickets", data="not json").status_code, 400)

    def test_malformed_requests_never_return_html(self):
        attempts = (
            self.client.get("/api/tickets?limit=abc"),
            self.client.post("/api/tickets/APP-1/comments", json=["x"]),
            self.client.post("/api/tickets", json={"project": "APP", "title": "t", "labels": 5}),
            self.client.post("/api/tickets", json={"project": "APP", "title": "t", "body": {"x": 1}}),
            self.client.get("/api/tickets?status=In%20Progress"),
            self.client.get("/api/nothing-here"),
        )
        for response in attempts:
            self.assertEqual(response.mimetype, "application/json")
            self.assertLess(response.status_code, 500)
            self.assertIn("error", response.get_json())

    def test_list_reports_the_total_when_capped(self):
        for number in range(5):
            self.client.post("/api/tickets", json={"project": "APP", "title": f"t{number}"})
        response = self.client.get("/api/tickets?limit=2")
        self.assertEqual((len(response.get_json()), response.headers[server.TOTAL_HEADER]), (2, "5"))

    def test_help_and_meta_describe_the_service(self):
        self.assertIn("endpoints", self.client.get("/api").get_json())
        self.assertIn("in_progress", self.client.get("/api/meta").get_json()["statuses"])
        self.assertTrue(self.client.get("/healthz").get_json()["ok"])

    def test_page_and_font_routes(self):
        (Path(self.directory.name) / "x.woff2").write_bytes(b"font")
        with self.client.get("/fonts/x.woff2") as response:
            self.assertEqual(response.data, b"font")
        self.assertEqual(self.client.get("/fonts/missing.woff2").status_code, 404)
        self.assertEqual(self.client.get("/fonts/../secret").status_code, 404)
        with self.client.get("/") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-cache")


def undocumented_routes(app, spec):
    missing = []
    for rule in app.iter_rules():
        if not (rule.rule.startswith("/api") or rule.rule == "/healthz"):
            continue
        path = re.sub(r"<(?:\w+:)?(\w+)>", lambda match: "{" + match.group(1) + "}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if method.lower() not in spec["paths"].get(path, {}):
                missing.append(f"{method} {path}")
    return sorted(missing)


def unresolved_refs(node, schemas):
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and value.split("/")[-1] not in schemas:
                found.append(value)
            found += unresolved_refs(value, schemas)
    elif isinstance(node, list):
        for value in node:
            found += unresolved_refs(value, schemas)
    return found


class OpenApiTests(unittest.TestCase):
    def setUp(self):
        self.app = server.create_app(":memory:", font_dir=tempfile.gettempdir())
        self.client = self.app.test_client()
        self.spec = self.client.get("/api/openapi.json").get_json()

    def test_every_api_route_is_documented(self):
        self.assertEqual(undocumented_routes(self.app, self.spec), [])

    def test_the_route_check_can_fail(self):
        pruned = json.loads(json.dumps(self.spec))
        del pruned["paths"]["/api/board"]
        del pruned["paths"]["/api/tickets/{ticket_key}"]["patch"]
        self.assertEqual(undocumented_routes(self.app, pruned), ["GET /api/board", "PATCH /api/tickets/{ticket_key}"])

    def test_every_reference_resolves(self):
        self.assertEqual(unresolved_refs(self.spec, self.spec["components"]["schemas"]), [])
        broken = {"a": {"$ref": "#/components/schemas/Nope"}}
        self.assertEqual(unresolved_refs(broken, {}), ["#/components/schemas/Nope"])

    def test_enums_follow_the_store(self):
        schemas = self.spec["components"]["schemas"]
        self.assertEqual(schemas["TicketPatch"]["properties"]["status"]["enum"], list(store.STATUSES))
        self.assertEqual(schemas["NewTicket"]["properties"]["priority"]["enum"], list(store.PRIORITIES))
        self.assertEqual(schemas["Link"]["properties"]["kind"]["enum"], list(store.LINK_KINDS))

    def test_every_operation_has_an_id_tag_and_response(self):
        identifiers = []
        for path, item in self.spec["paths"].items():
            for method, operation in item.items():
                identifiers.append(operation["operationId"])
                self.assertTrue(operation["tags"] and operation["responses"], f"{method} {path}")
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_documentation_pages_are_served(self):
        for path in ("/docs", "/static/docs.js", "/static/docs.css"):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200, path)


class LiveServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        app = server.create_app(":memory:", font_dir=tempfile.gettempdir())
        cls.thread = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=cls.port, threaded=True), daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(50):
            try:
                ledger_cli.call(cls.base, "GET", "/healthz", "t")
                break
            except SystemExit:
                threading.Event().wait(0.1)


class ServerBehaviourTests(LiveServerCase):
    def test_an_idle_connection_does_not_block_other_requests(self):
        with socket.create_connection(("127.0.0.1", self.port)):
            with urllib.request.urlopen(self.base + "/healthz", timeout=3) as response:
                self.assertEqual(response.status, 200)

    def test_concurrent_writes_all_land(self):
        ledger_cli.call(self.base, "POST", "/api/projects", "t", {"key": "RACE", "name": "Race"})
        errors = []

        def add(number):
            try:
                ledger_cli.call(self.base, "POST", "/api/tickets", "t", {"project": "RACE", "title": f"t{number}"})
            except SystemExit as error:
                errors.append(str(error))

        workers = [threading.Thread(target=add, args=(number,)) for number in range(20)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        listed = ledger_cli.call(self.base, "GET", "/api/tickets?project=RACE", "t")
        self.assertEqual((errors, len(listed), len({t["key"] for t in listed})), ([], 20, 20))


class CliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def test_full_flow(self):
        self.cli("new-project", "CLI", "CLI test")
        created = json.loads(self.cli("--json", "add", "CLI", "made from the command line", "--type", "bug", "--priority", "high"))
        self.assertEqual(created["key"], "CLI-1")
        self.cli("move", "CLI-1", "in_progress")
        self.cli("assign", "CLI-1", "cli-test")
        self.cli("comment", "CLI-1", "working on it")
        self.assertIn("CLI-1", self.cli("mine"))
        shown = self.cli("show", "CLI-1")
        self.assertIn("in_progress", shown)
        self.assertIn("working on it", shown)
        self.assertIn("history", shown)
        self.assertIn("status", self.cli("history", "CLI-1"))
        self.cli("done", "CLI-1", "--comment", "finished")
        self.assertNotIn("CLI-1", self.cli("mine"))
        self.assertIn("CLI-1", self.cli("list", "--project", "CLI"))
        self.assertNotIn("CLI-1", self.cli("list", "--project", "CLI", "--open"))
        self.assertIn("CLI-1", self.cli("list", "-q", "command line"))
        self.assertIn("CLI-1", self.cli("list", "--text", "CLI-1"))

    def test_unicode_titles_print_and_store(self):
        self.cli("new-project", "UNI", "Unicode")
        self.assertIn("ünï", self.cli("add", "UNI", "ünï ✓"))
        self.assertEqual(json.loads(self.cli("--json", "show", "UNI-1"))["title"], "ünï ✓")

    def test_labels_can_be_added_and_removed(self):
        self.cli("new-project", "LAB", "Labels")
        self.cli("add", "LAB", "t", "--labels", "one,two")
        edited = json.loads(self.cli("--json", "edit", "LAB-1", "--add-label", "three", "--rm-label", "one"))
        self.assertEqual(edited["labels"], ["three", "two"])

    def test_a_refusal_exits_with_the_server_message(self):
        with self.assertRaises(SystemExit) as raised:
            self.cli("show", "NOPE-1")
        self.assertIn("no ticket", str(raised.exception))

    def test_a_filter_typo_is_reported(self):
        self.cli("new-project", "TYP", "Typos")
        with self.assertRaises(SystemExit) as raised:
            self.cli("list", "--project", "TYP", "--status", "inprogress")
        self.assertIn("status", str(raised.exception))

    def test_duplicate_source_is_refused(self):
        self.cli("new-project", "SRC", "Sources")
        self.cli("add", "SRC", "first", "--source", "ext:1")
        with self.assertRaises(SystemExit):
            self.cli("add", "SRC", "second", "--source", "ext:1")

    def test_unreachable_server_is_named(self):
        with self.assertRaises(SystemExit) as raised:
            ledger_cli.call("http://127.0.0.1:9", "GET", "/healthz", "t")
        self.assertIn("cannot reach", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
