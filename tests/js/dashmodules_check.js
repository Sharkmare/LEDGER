"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..", "..");
const { registerDashboardModule, widgetBody, loadModuleScripts, moduleById, moduleChoices, moduleFailureLines, dashboardModuleRenderers } = require(path.join(root, "ledger", "static", "dashmodules.js"));
const charts = require(path.join(root, "ledger", "static", "charts.js"));
const { escapeHtml } = require(path.join(root, "ledger", "static", "escape.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

const helpers = {
  ...charts, escapeHtml,
  ticketTable: (rows) => `<table>${rows.join("")}</table>`,
  ticketLink: (key, title) => `<a data-open-ticket="${escapeHtml(key)}">${escapeHtml(title)}</a>`,
  bucketColor: () => "red", nameColor: () => "blue",
};

check("a widget without data says it is loading, and a data error is shown as text", () => {
  assert.ok(widgetBody({ kind: "x" }, null, helpers, {}).includes("Loading"));
  assert.ok(widgetBody({ kind: "x" }, { error: "bad <b>" }, helpers, {}).includes("bad &lt;b&gt;"));
});

check("a module with no renderer shows its data as escaped text instead of failing", () => {
  const html = widgetBody({ kind: "plain" }, { note: "<script>" }, helpers, {});
  assert.ok(html.includes("widget-raw") && html.includes("&lt;script&gt;") && !html.includes("<script>"));
});

check("the renderer receives the widget, the data and the helpers", () => {
  let seen = null;
  const renderers = { demo: { render: (widget, data, given) => { seen = [widget, data, given]; return "<p>drawn</p>"; } } };
  assert.strictEqual(widgetBody({ kind: "demo", id: "w1" }, { n: 1 }, helpers, renderers), "<p>drawn</p>");
  assert.deepStrictEqual([seen[0].id, seen[1].n, seen[2] === helpers], ["w1", 1, true]);
});

check("a renderer that throws only breaks its own widget", () => {
  const renderers = { demo: { render: () => { throw new Error("no field"); } } };
  const html = widgetBody({ kind: "demo" }, { n: 1 }, helpers, renderers);
  assert.ok(html.includes("widget-error") && html.includes("demo module could not draw") && html.includes("no field"));
});

check("registering a module makes its renderer the one used by default", () => {
  registerDashboardModule("registered", { render: () => "ok" });
  assert.strictEqual(widgetBody({ kind: "registered" }, { a: 1 }, helpers), "ok");
  assert.ok(dashboardModuleRenderers.registered);
});

check("scripts load once per module, only for modules that have one, and a failure is reported without stopping the rest", async () => {
  const loadedUrls = [];
  const loader = async (url) => { if (url.includes("bad")) throw new Error(`could not load ${url}`); loadedUrls.push(url); };
  const descriptors = [{ id: "a", script: "/a.js" }, { id: "bad", script: "/bad.js" }, { id: "none", script: null }, { id: "c", script: "/c.js" }];
  const loaded = new Set();
  const failures = await loadModuleScripts(descriptors, loader, loaded);
  assert.deepStrictEqual(failures, [{ id: "bad", error: "could not load /bad.js" }]);
  assert.deepStrictEqual(loadedUrls.sort(), ["/a.js", "/c.js"]);
  await loadModuleScripts(descriptors, loader, loaded);
  assert.deepStrictEqual(loadedUrls.sort(), ["/a.js", "/c.js"]);
});

check("module lookups and the add widget choices follow the listing", () => {
  const descriptors = [{ id: "a", title: "Alpha" }, { id: "b", title: "Beta" }];
  assert.strictEqual(moduleById(descriptors, "b").title, "Beta");
  assert.strictEqual(moduleById(descriptors, "z"), null);
  assert.deepStrictEqual(moduleChoices(descriptors), [{ value: "a", label: "Alpha" }, { value: "b", label: "Beta" }]);
});

check("failures are shown by file, falling back to the folder", () => {
  assert.deepStrictEqual(moduleFailureLines([{ folder: "/m", file: "x.py", error: "bad" }, { folder: "/gone", file: "", error: "missing" }]), ["x.py: bad", "/gone: missing"]);
});

const SAMPLES = {
  count: [{ measure: "closed" }, { value: 12, previous: 9, delta: 3, measure: "closed", days: 7 }, ["12", "+3", "the 7 days before (9)", "delta good"]],
  group: [{ chart: "bar" }, { field: "status", total: 3, buckets: [{ name: "todo", key: "todo", value: 2, points: 0 }, { name: "done", key: "done", value: 1, points: 0 }] }, ["hbars", "todo", "done"]],
  trend: [{}, { days: 2, interval: "day", created: 3, closed: 1, series: [{ date: "2026-11-01", created: 1, closed: 0, open: 1 }, { date: "2026-11-02", created: 2, closed: 1, open: 2 }] }, ["3 created, 1 closed in 2 days, by day", "Created", "Closed"]],
  burndown: [{}, { iteration: { name: "Sprint 1", start: "2026-11-01", end: "2026-11-03" }, unit: "points", total: 10, days: [{ date: "2026-11-01", remaining: 10, ideal: 10 }, { date: "2026-11-02", remaining: 6, ideal: 5 }, { date: "2026-11-03", remaining: null, ideal: 0 }] }, ["Sprint 1", "6 of 10 points left", "Ideal", "Remaining"]],
  cycle: [{}, { days: 30, closed: 4, lead: { average: 3.5, median: 3, p85: 6 }, cycle: { average: null, median: null, p85: null }, histogram: [{ label: "1 day or less", value: 4 }] }, ["3 d", "median lead time, 4 finished in 30 days", "85% within 6 d", "median -"]],
  aging: [{}, { total: 2, buckets: [{ label: "0 to 7 days", value: 2 }], oldest: [{ key: "APP-1", title: "Old <one>", age_days: 40 }] }, ["0 to 7 days", "APP-1", "Old &lt;one&gt;", "40 d"]],
  workload: [{}, { people: [{ name: "ann", tickets: 3, points: 5, overdue: 1 }], more: 2 }, ["ann", "5 points, 1 overdue", "and 2 more"]],
  velocity: [{}, { iterations: [{ name: "S1", committed: 8, completed: 6, tickets: 4, tickets_done: 3 }], average: 6 }, ["S1", "Average 6 points per iteration", "Committed", "Completed"]],
  overdue: [{}, { total: 1, items: [{ key: "APP-2", title: "Late", due: "2026-10-01", assignee: "ann", priority: "high", days_late: 9 }] }, ["kpi\">1<", "past their due date", "APP-2", "9 d late"]],
  stale: [{}, { total: 1, days: 14, items: [{ key: "APP-3", title: "Quiet", quiet_days: 20 }] }, ["untouched for 14 days", "APP-3", "20 d quiet"]],
};

const moduleScripts = [];
for (const folder of [path.join(root, "modules"), path.join(root, "examples", "modules")]) {
  for (const file of fs.readdirSync(folder).filter((name) => name.endsWith(".js"))) moduleScripts.push(path.join(folder, file));
}

for (const script of moduleScripts) {
  const id = path.basename(script, ".js");
  check(`the ${id} module script registers its renderer and draws sample data`, () => {
    const registered = {};
    vm.runInNewContext(fs.readFileSync(script, "utf8"), { registerDashboardModule: (name, definition) => { registered[name] = definition; } }, { filename: script });
    assert.deepStrictEqual(Object.keys(registered), [id]);
    assert.ok(SAMPLES[id], `add sample data for ${id} to this check`);
    const [widget, data, expected] = SAMPLES[id];
    const html = widgetBody({ kind: id, ...widget }, data, helpers, registered);
    for (const text of expected) assert.ok(html.includes(text), `${id} output lacks ${JSON.stringify(text)}:\n${html}`);
    assert.ok(!html.includes("widget-error"), html);
  });
}

check("every builtin module has a script and every script has sample data", () => {
  const ids = fs.readdirSync(path.join(root, "modules")).filter((name) => name.endsWith(".py")).map((name) => path.basename(name, ".py"));
  const scripts = moduleScripts.map((file) => path.basename(file, ".js"));
  for (const id of ids) assert.ok(scripts.includes(id), `${id} has no script`);
  for (const id of scripts) assert.ok(SAMPLES[id], id);
});

(async () => {
  let failed = 0;
  for (const [name, body] of checks) {
    try { await body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
  }
  console.log(`${checks.length - failed} of ${checks.length} passed`);
  process.exit(failed ? 1 : 0);
})();
