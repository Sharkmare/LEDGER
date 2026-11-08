"use strict";

const assert = require("assert");
const path = require("path");
const staticDir = path.join(__dirname, "..", "..", "ledger", "static");
const { statsFrom, filterValues } = require(path.join(staticDir, "ticketstats.js"));
const { nameColor } = require(path.join(staticDir, "namecolor.js"));

const CLOSED = ["done", "cancelled"];
const META = { statuses: ["todo", "done"], priorities: ["low", "high"], types: ["bug", "task"] };
const STATUS_LABELS = { todo: "To do", done: "Done" };
const ticket = (status, overrides = {}) => ({ status, type: "task", priority: "low", assignee: "", ...overrides });
const options = (fieldId, overrides = {}) => filterValues(fieldId, { meta: META, tagList: [], stats: null, assignee: "", statusLabels: STATUS_LABELS, ...overrides });
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("open counts the tickets whose status is not closed", () => {
  const stats = statsFrom([ticket("todo"), ticket("done"), ticket("cancelled"), ticket("in_progress")], CLOSED);
  assert.strictEqual(stats.open, 2);
});

check("unassigned counts tickets with no assignee, whether empty or missing", () => {
  const stats = statsFrom([ticket("todo"), ticket("todo", { assignee: null }), ticket("todo", { assignee: "azazel" }), ticket("todo", { assignee: undefined })], CLOSED);
  assert.strictEqual(stats.unassigned, 3);
});

check("tickets are tallied by status, type, priority and assignee", () => {
  const stats = statsFrom([ticket("todo", { type: "bug", priority: "high", assignee: "azazel" }), ticket("todo", { assignee: "azazel" }), ticket("done", { type: "bug" })], CLOSED);
  assert.deepStrictEqual(stats.by_status, { todo: 2, done: 1 });
  assert.deepStrictEqual(stats.by_type, { bug: 2, task: 1 });
  assert.deepStrictEqual(stats.by_priority, { high: 1, low: 2 });
  assert.deepStrictEqual(stats.by_assignee, { azazel: 2 });
});

check("no tickets give zero counts and empty tallies", () => {
  assert.deepStrictEqual(statsFrom([], CLOSED), { open: 0, unassigned: 0, by_status: {}, by_type: {}, by_priority: {}, by_assignee: {} });
});

check("status choices keep the server order and use the display labels", () => {
  assert.deepStrictEqual(options("status"), [{ value: "todo", label: "To do" }, { value: "done", label: "Done" }]);
});

check("priority and type choices are the allowed values as they are", () => {
  assert.deepStrictEqual(options("priority"), [{ value: "low", label: "low" }, { value: "high", label: "high" }]);
  assert.deepStrictEqual(options("type").map((o) => o.value), ["bug", "task"]);
});

check("tag choices come from the tag list", () => {
  assert.deepStrictEqual(options("label", { tagList: [{ name: "tests" }, { name: "ui" }] }).map((o) => o.value), ["tests", "ui"]);
});

check("assignee choices are the people in the stats, sorted, without blanks", () => {
  const stats = { by_assignee: { swarm: 1, azazel: 2, "": 4 } };
  assert.deepStrictEqual(options("assignee", { stats }).map((o) => o.value), ["azazel", "swarm"]);
});

check("an assignee being filtered on stays in the list even when nobody has tickets left", () => {
  const stats = { by_assignee: { azazel: 2 } };
  assert.deepStrictEqual(options("assignee", { stats, assignee: "ghost" }).map((o) => o.value), ["azazel", "ghost"]);
  assert.deepStrictEqual(options("assignee", { stats, assignee: "azazel" }).map((o) => o.value), ["azazel"]);
  assert.deepStrictEqual(options("assignee", { stats: null, assignee: "ghost" }).map((o) => o.value), ["ghost"]);
  assert.deepStrictEqual(options("assignee"), []);
});

check("a name always gets the same colour, whatever its case", () => {
  assert.strictEqual(nameColor("Azazel"), nameColor("azazel"));
  assert.strictEqual(nameColor("swarm"), nameColor("swarm"));
});

check("the colour formula is pinned so existing avatars and tiles keep their colours", () => {
  assert.strictEqual(nameColor("a"), "hsl(97 62% 62%)");
  assert.strictEqual(nameColor("ab"), "hsl(225 62% 62%)");
  assert.strictEqual(nameColor("\u{1F600}"), "hsl(352 62% 62%)");
});

check("the hue stays inside the colour wheel and different names differ", () => {
  for (const name of ["azazel", "swarm", "lathe", "ledger-daily", "x".repeat(400)]) {
    const hue = Number(nameColor(name).match(/^hsl\((\d+) /)[1]);
    assert.ok(hue >= 0 && hue < 360, `${name}: ${hue}`);
  }
  assert.notStrictEqual(nameColor("azazel"), nameColor("swarm"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
