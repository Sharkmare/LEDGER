"use strict";

const assert = require("assert");
const path = require("path");
const { parseDay, monthStarts, roadmapLayout } = require(path.join(__dirname, "..", "..", "ledger", "static", "roadmap.js"));

const day = (year, month, date) => new Date(year, month - 1, date).getTime();
const near = (actual, expected, label) => assert.ok(Math.abs(actual - expected) < 1e-6, `${label}: expected ${expected}, got ${actual}`);
const iteration = (overrides) => ({ name: "I1", project: "LED", state: "active", start: "2026-05-10", end: "2026-05-19", points: 0, points_done: 0, tickets: 0, done: 0, ...overrides });
const epic = (overrides) => ({ key: "LED-1", title: "E", status: "in_progress", start: "2026-05-10", due: "2026-05-24", progress: { done: 0, total: 0 }, ...overrides });
const roadmap = (overrides = {}) => ({ range: { start: "2026-05-10", end: "2026-06-09" }, iterations: [], epics: [], ...overrides });
const NOW = day(2026, 5, 20);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("a day is read as local midnight", () => {
  assert.strictEqual(parseDay("2026-05-10"), day(2026, 5, 10));
  assert.strictEqual(parseDay("2026-12-31"), day(2026, 12, 31));
});

check("month starts run from the month of the first day to the month of the last", () => {
  const months = monthStarts(day(2026, 1, 15), day(2026, 3, 3));
  assert.deepStrictEqual(months.map((m) => m.at), [day(2026, 1, 1), day(2026, 2, 1), day(2026, 3, 1)]);
});

check("a month starting exactly on the last day is included and the next one is not", () => {
  assert.strictEqual(monthStarts(day(2026, 1, 15), day(2026, 3, 1)).length, 3);
  assert.strictEqual(monthStarts(day(2026, 1, 15), day(2026, 2, 28)).length, 2);
});

check("month starts cross a year end", () => {
  const months = monthStarts(day(2026, 11, 20), day(2027, 2, 2));
  assert.deepStrictEqual(months.map((m) => m.at), [day(2026, 11, 1), day(2026, 12, 1), day(2027, 1, 1), day(2027, 2, 1)]);
  assert.ok(months.every((m) => m.label.length > 0));
});

check("a bar is placed by its start and spans its last day too", () => {
  const [row] = roadmapLayout(roadmap({ iterations: [iteration({})] }), NOW).iterations;
  near(row.left, 20, "left");
  near(row.width, 20, "width");
});

check("a bar that ends before it starts still gets the minimum width", () => {
  const [row] = roadmapLayout(roadmap({ iterations: [iteration({ start: "2026-05-20", end: "2026-05-19" })] }), NOW).iterations;
  near(row.width, 0.6, "width");
});

check("iteration progress uses points when it has them, tickets otherwise, and is zero when empty", () => {
  const percents = roadmapLayout(roadmap({ iterations: [iteration({ points: 10, points_done: 4, tickets: 3, done: 3 }), iteration({ tickets: 3, done: 1 }), iteration({})] }), NOW).iterations.map((r) => r.percent);
  assert.deepStrictEqual(percents, [40, 33, 0]);
});

check("an epic with only a due date starts fourteen days earlier", () => {
  const [row] = roadmapLayout(roadmap({ epics: [epic({ start: null, due: "2026-05-24" })] }), NOW).epics;
  near(row.left, 20, "left");
  near(row.width, (15 / 50) * 100, "width");
});

check("an epic with only a start date ends fourteen days later", () => {
  const [row] = roadmapLayout(roadmap({ epics: [epic({ start: "2026-05-10", due: null })] }), NOW).epics;
  near(row.left, 20, "left");
  near(row.width, (15 / 50) * 100, "width");
});

check("epic progress is done over total, a finished epic with no children shows full, anything else empty", () => {
  const percents = roadmapLayout(roadmap({ epics: [epic({ progress: { done: 2, total: 3 } }), epic({ status: "done" }), epic({})] }), NOW).epics.map((r) => r.percent);
  assert.deepStrictEqual(percents, [67, 100, 0]);
});

check("the today marker is a fraction of the padded range and absent outside it", () => {
  near(roadmapLayout(roadmap({ iterations: [iteration({})] }), day(2026, 5, 20)).todayOffset, 20 / 50, "inside");
  assert.strictEqual(roadmapLayout(roadmap(), day(2026, 4, 29)).todayOffset, null);
  assert.strictEqual(roadmapLayout(roadmap(), day(2026, 6, 20)).todayOffset, null);
  assert.strictEqual(roadmapLayout(roadmap(), day(2026, 4, 30)).todayOffset, 0);
  assert.strictEqual(roadmapLayout(roadmap(), day(2026, 6, 19)).todayOffset, 1);
});

check("month labels are placed as a percentage of the padded range", () => {
  const months = roadmapLayout(roadmap(), NOW).months;
  assert.strictEqual(months.length, 3);
  near(months[1].left, 2, "May");
  near(months[2].left, 64, "June");
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
