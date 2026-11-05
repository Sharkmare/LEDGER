import datetime
import http.client
import json
import os
import platform
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ledger import kb, manage, metrics, miniyaml, organise, server, store

SCALE = float(os.environ.get("LEDGER_PERF_SCALE", "1"))
BUDGET_FACTOR = float(os.environ.get("LEDGER_PERF_BUDGET_FACTOR", "6"))
REPORT_PATH = os.environ.get("LEDGER_PERF_REPORT")
REPEATS = 3
TICKETS = int(5000 * SCALE)
PAGES = int(1200 * SCALE)
NAMES = ("ann", "bob", "cy", "dee", "eli", "fay", "gus", "hal")
LABELS = ("auth", "ui", "api", "docs", "perf", "bug", "infra", "mobile")
RESULTS: list[dict] = []


def scaled(count: int) -> int:
    return max(1, int(count * SCALE))


def measure(name, operations, function, target_ms, hint, repeats=REPEATS):
    best = None
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        elapsed = (time.perf_counter() - started) * 1000
        best = elapsed if best is None else min(best, elapsed)
    entry = {"name": name, "operations": operations, "ms": round(best, 2), "per_operation_us": round(best * 1000 / operations, 1),
             "target_ms": target_ms, "budget_ms": target_ms * BUDGET_FACTOR, "hint": hint}
    entry["ratio"] = round(best / target_ms, 2)
    entry["status"] = "over target" if best > target_ms else "ok"
    RESULTS.append(entry)
    return entry


def verdict(entry):
    return "FAILS BUDGET" if entry["ms"] > entry["budget_ms"] else entry["status"]


def build_report(results):
    lines = [f"LEDGER performance report: scale {SCALE}, Python {platform.python_version()}, SQLite {store.sqlite3.sqlite_version}, {platform.system()}",
             f"{'operation':<34}{'ops':>7}{'total ms':>11}{'per op':>11}{'target ms':>11}{'x target':>10}  verdict"]
    for entry in sorted(results, key=lambda e: -e["ratio"]):
        per_op = f"{entry['per_operation_us']:.0f} us" if entry["per_operation_us"] < 10000 else f"{entry['per_operation_us'] / 1000:.1f} ms"
        lines.append(f"{entry['name']:<34}{entry['operations']:>7}{entry['ms']:>11.1f}{per_op:>11}{entry['target_ms']:>11.0f}{entry['ratio']:>10.2f}  {verdict(entry)}")
    slow = [e for e in sorted(results, key=lambda e: -e["ratio"]) if e["status"] != "ok"]
    lines.append("")
    if slow:
        lines.append(f"{len(slow)} of {len(results)} operations are over their interactive target. Best candidates for a rewrite or a compiled core, worst first:")
        for entry in slow:
            lines.append(f"  {entry['name']} ({entry['ratio']:.1f}x target): {entry['hint']}")
    else:
        lines.append(f"All {len(results)} operations are inside their interactive targets.")
    return "\n".join(lines)


def tearDownModule():
    if not RESULTS:
        return
    report = build_report(RESULTS)
    print("\n" + report, file=sys.stderr)
    if REPORT_PATH:
        Path(REPORT_PATH).write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")


def openapi_yaml(paths: int) -> tuple[str, dict]:
    lines = ["openapi: 3.0.3", "info:", "  title: Generated service", "  version: '1.0'", "paths:"]
    document = {"openapi": "3.0.3", "info": {"title": "Generated service", "version": "1.0"}, "paths": {}}
    for index in range(paths):
        route = f"/resource{index}/{{id}}"
        lines.append(f"  {route}:")
        document["paths"][route] = {}
        for method in ("get", "post", "delete"):
            lines += [f"    {method}:", f"      summary: {method.upper()} resource {index}", f"      operationId: {method}Resource{index}", "      tags:", "        - resources",
                      "      parameters:", "        - name: id", "          in: path", "          required: true", "          schema:", "            type: string",
                      "      responses:", "        200:", "          description: Success", "          content:", "            application/json:", "              schema:",
                      "                type: object", "                properties:", "                  id: {type: string}", "                  name: {type: string}",
                      "        '404':", "          description: \"Not found: no such resource\""]
            document["paths"][route][method] = {"summary": f"{method.upper()} resource {index}", "operationId": f"{method}Resource{index}", "tags": ["resources"],
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "Success", "content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}}}}},
                              "404": {"description": "Not found: no such resource"}}}
    return "\n".join(lines) + "\n", document


def bulk_tickets(connection, count):
    generator = random.Random(7)
    store.create_project(connection, "PRF", "Performance")
    area = organise.create_area(connection, "Platform")
    now = time.time()
    types, statuses, priorities = list(store.TICKET_TYPES), list(store.STATUSES), list(store.PRIORITIES)
    rows = []
    for number in range(1, count + 1):
        status = generator.choice(statuses)
        created = now - generator.randint(0, 90) * 86400
        closed = created + generator.randint(1, 20) * 86400 if status in store.CLOSED_STATUSES else None
        labels = json.dumps(sorted(generator.sample(LABELS, generator.randint(0, 3))))
        due = (datetime.date.today() + datetime.timedelta(days=generator.randint(-20, 40))).isoformat() if generator.random() < 0.3 else ""
        rows.append(("PRF", number, f"Ticket {number} about the {generator.choice(LABELS)} subsystem", "Body text " * 12, generator.choice(types), status,
                     generator.choice(priorities), generator.choice(NAMES + ("",)), labels, due, created, created, closed, float(generator.randint(1, 8)),
                     area["id"] if generator.random() < 0.7 else None))
    connection.executemany(
        "INSERT INTO tickets (project_key, number, title, body, type, status, priority, assignee, labels, due, created, updated, closed, estimate, area_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.execute("UPDATE projects SET next_number = ? WHERE key = 'PRF'", (count + 1,))
    connection.commit()
    return area


class PerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.connection = store.connect(Path(cls.directory.name) / "perf.db")
        cls.addClassCleanup(cls.connection.close)
        cls.area = bulk_tickets(cls.connection, TICKETS)
        cls.board = organise.create_board(cls.connection, cls.area["id"], "Bugs", rules={"types": ["bug"], "labels": ["auth", "api"]})
        kb.create_space(cls.connection, "DOC", "Documentation")
        words = ("deploy", "service", "rollback", "database", "cache", "queue", "release", "monitor", "alert", "index", "backup", "restore")
        generator = random.Random(11)
        cls.page_ids = []
        parent = None

        def create_pages():
            nonlocal parent
            for number in range(PAGES):
                body = " ".join(generator.choice(words) for _ in range(160)) + f"\n\nSee APP-{number % 50 + 1} and [[Page {max(number - 1, 0)}]]."
                page = kb.create_page(cls.connection, "DOC", f"Page {number}", body, parent=parent if number % 7 else None, labels=generator.choice(LABELS))
                cls.page_ids.append(page["id"])
                parent = page["id"] if number % 9 == 0 else parent

        measure("kb create page (with index)", PAGES, create_pages, PAGES * 2.5, "per page: insert, version, link scan and full-text index in separate statements; a native storage core could batch them", repeats=1)

    def test_yaml_reader_against_the_json_parser(self):
        text, document = openapi_yaml(scaled(250))
        as_json = json.dumps(document)
        baseline = measure("json.loads, same document", 1, lambda: json.loads(as_json), 20, "baseline: the C parser in the standard library", repeats=5)
        measure("miniyaml.loads, 750 operations", 1, lambda: miniyaml.loads(text), max(250, baseline["ms"] * 60),
                "pure Python text parser, the clearest candidate: a small C or Rust extension would be tens of times faster", repeats=3)
        self.assertEqual(miniyaml.loads(text), json.loads(as_json))
        self.assertLessEqual(RESULTS[-1]["ms"], RESULTS[-1]["budget_ms"], "YAML reading regressed badly")

    def test_http_layer_in_process(self):
        app = server.create_app(":memory:")
        client = app.test_client()
        count = scaled(2000)
        entry = measure("http route + json, in process", count, lambda: [client.get("/api/meta") for _ in range(count)], count * 0.3,
                        "route matching, hooks and JSON in pure Python on every request; a compiled router would remove most of it")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])

    def test_http_over_a_real_socket(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        app = server.create_app(":memory:")
        threading.Thread(target=lambda: app.run(host="127.0.0.1", port=port, threaded=True), daemon=True).start()
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        count = scaled(300)

        def requests():
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            for _ in range(count):
                connection.request("GET", "/api/meta")
                connection.getresponse().read()
            connection.close()

        entry = measure("http over a socket, keep-alive", count, requests, count * 3,
                        "http.server parses and writes each request in Python; a compiled server (Rust, Go, C#) answers in microseconds")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])

    def test_store_writes_and_reads(self):
        connection = store.connect(Path(self.directory.name) / "writes.db")
        self.addCleanup(connection.close)
        store.create_project(connection, "WRT", "Writes")
        count = scaled(500)
        entry = measure("create ticket on disk", count, lambda: [store.create_ticket(connection, "WRT", f"Ticket {n}", labels="a,b") for n in range(count)], count * 3,
                        "each create runs several queries and commits to disk; batch the commit or move the store into a native module", repeats=1)
        self.assertLessEqual(entry["ms"], entry["budget_ms"])
        entry = measure(f"list {TICKETS} tickets", TICKETS, lambda: store.list_tickets(self.connection, limit=TICKETS), 220,
                        "one extra query per ticket for parent, area and iteration names: join them in SQL, or build the rows in a native module")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])
        measure("get one ticket (full)", 200, lambda: [store.get_ticket(self.connection, "PRF-77") for _ in range(200)], 200, "several small queries per ticket: comments, children, links, progress")

    def test_filtering_boards_and_trees(self):
        entry = measure("board resolve over the tickets", 1, lambda: organise.get_board(self.connection, self.board["id"]), 300,
                        "rule query plus per ticket row conversion in Python")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])
        measure("list tickets with a label filter", 1, lambda: store.list_tickets(self.connection, label="auth", limit=TICKETS), 150, "json_each scan of every ticket's labels")
        space = kb.get_space(self.connection, "DOC")
        entry = measure("kb page tree", len(self.page_ids), lambda: kb.tree(self.connection, space["id"]), 200 * SCALE + 50, "builds a summary dict per page; a native tree builder would be quicker")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])

    def test_search(self):
        queries = ["deploy", "rollback service", "databa", "cache queue", "monitor alert release", "restore backup", "index", "zzzzqx"]
        count = scaled(160)
        entry = measure("kb search", count, lambda: [kb.search(self.connection, queries[n % len(queries)]) for n in range(count)], count * 8,
                        "SQLite's full-text engine does the work; only snippet and row conversion are Python")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])
        measure("find everything (pages, tools, tickets)", 60, lambda: [kb.find_everything(self.connection, "deploy") for _ in range(60)], 60 * 25, "three queries and row conversion per call")

    def test_metrics_over_many_tickets(self):
        now = time.time()
        for name, work, target in (
            ("metric: group by status", lambda: metrics.group_metric(self.connection, {}, "status"), 160),
            ("metric: group by tag", lambda: metrics.group_metric(self.connection, {}, "label"), 220),
            ("metric: trend, 60 days", lambda: metrics.trend_metric(self.connection, {}, 60, None, now), 200),
            ("metric: lead and cycle time", lambda: metrics.cycle_metric(self.connection, {}, 90, now), 400),
            ("metric: aging", lambda: metrics.aging_metric(self.connection, {}, 5, now), 160),
            ("metric: workload", lambda: metrics.workload_metric(self.connection, {}, 8, now), 160),
        ):
            entry = measure(name, 1, work, target, "loops over every row in Python; an aggregate query or a native pass would be faster")
            self.assertLessEqual(entry["ms"], entry["budget_ms"], name)
        manage.seed_default_templates(self.connection)
        dashboard = next(iter(metrics.seed_default_dashboards(self.connection)))
        entry = measure("dashboard: Overview, 10 widgets", 10, lambda: metrics.dashboard_data(self.connection, dashboard["id"], now), 1500,
                        "ten metrics, each scanning the tickets again; share one scan or compute in a native module")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])

    def test_tag_rename_and_page_diff(self):
        copy = Path(self.directory.name) / "rename.db"
        shutil.copyfile(Path(self.directory.name) / "perf.db", copy)
        connection = store.connect(copy)
        self.addCleanup(connection.close)
        entry = measure("rename a tag across tickets", 1, lambda: manage.update_tag(connection, "api", {"name": "interface"}), 1500,
                        "rewrites the label JSON of each ticket in a Python loop; a single SQL update or native pass would do it in one go", repeats=1)
        self.assertLessEqual(entry["ms"], entry["budget_ms"])
        page = kb.create_page(connection, "DOC", "Large page", "\n".join(f"line {n} of the original text" for n in range(scaled(3000))))
        kb.update_page(connection, page["id"], {"body": "\n".join(f"line {n} of the {'changed' if n % 40 == 0 else 'original'} text" for n in range(scaled(3000)))})
        entry = measure("diff two 3000 line versions", 1, lambda: kb.diff_versions(connection, page["id"], 1, 2), 400,
                        "difflib is quadratic in the worst case; a Myers diff in Rust or C stays linear")
        self.assertLessEqual(entry["ms"], entry["budget_ms"])

    @unittest.skipUnless(shutil.which("node"), "Node is not installed; the Markdown renderer runs in the browser")
    def test_markdown_renderer(self):
        sections = scaled(400)
        script = ROOT / "tests" / "js" / "markdown_perf.js"
        fastest = None
        for _ in range(REPEATS):
            result = subprocess.run(["node", str(script), str(sections)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            figures = json.loads(result.stdout)
            fastest = figures if fastest is None or figures["milliseconds"] < fastest["milliseconds"] else fastest
        RESULTS.append({"name": f"markdown render, {fastest['lines']} lines (JS)", "operations": 1, "ms": round(fastest["milliseconds"], 2),
                        "per_operation_us": round(fastest["milliseconds"] * 1000, 1), "target_ms": 250, "budget_ms": 250 * BUDGET_FACTOR,
                        "hint": "regular expressions per line in the browser's engine; a WebAssembly build of a native renderer would be quicker",
                        "ratio": round(fastest["milliseconds"] / 250, 2), "status": "over target" if fastest["milliseconds"] > 250 else "ok"})
        self.assertLessEqual(fastest["milliseconds"], 250 * BUDGET_FACTOR)


class ReportLogicTests(unittest.TestCase):
    def entry(self, ms, target):
        return {"name": "x", "operations": 1, "ms": ms, "per_operation_us": ms * 1000, "target_ms": target, "budget_ms": target * BUDGET_FACTOR,
                "hint": "h", "ratio": ms / target, "status": "over target" if ms > target else "ok"}

    def test_verdicts_separate_ok_slow_and_failing(self):
        self.assertEqual(verdict(self.entry(5, 10)), "ok")
        self.assertEqual(verdict(self.entry(15, 10)), "over target")
        self.assertEqual(verdict(self.entry(10 * BUDGET_FACTOR + 1, 10)), "FAILS BUDGET")

    def test_the_report_ranks_the_worst_first_and_names_candidates(self):
        slow = {**self.entry(50, 10), "name": "slow thing", "hint": "rewrite in Rust"}
        fine = {**self.entry(1, 10), "name": "fine thing"}
        report = build_report([fine, slow])
        self.assertLess(report.index("slow thing"), report.index("fine thing"))
        self.assertIn("slow thing (5.0x target): rewrite in Rust", report)
        self.assertIn("1 of 2 operations are over", report)
        self.assertIn("All 1 operations are inside", build_report([fine]))

    def test_measure_records_the_best_of_the_repeats(self):
        before = len(RESULTS)
        entry = measure("probe", 10, lambda: time.sleep(0.002), 1000, "none", repeats=2)
        RESULTS.pop()
        self.assertEqual(len(RESULTS), before)
        self.assertGreaterEqual(entry["ms"], 2)
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(measure("slow probe", 1, lambda: time.sleep(0.01), 1, "none", repeats=1)["status"], "over target")
        RESULTS.pop()


if __name__ == "__main__":
    unittest.main()
