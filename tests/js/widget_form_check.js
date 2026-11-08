"use strict";

const assert = require("assert");
const path = require("path");
const { widgetFromValues, widgetValues } = require(path.join(__dirname, "..", "..", "ledger", "static", "widgetform.js"));

const blankValues = (overrides = {}) => ({ title: "T", size: "1", ...overrides });
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("a new widget gets the kind, a trimmed title and a numeric width, and no id", () => {
  const widget = widgetFromValues("count", blankValues({ title: "  Closed lately  ", size: "2" }));
  assert.deepStrictEqual(widget, { kind: "count", title: "Closed lately", size: 2, filters: {} });
});

check("an edited widget keeps its id", () => {
  assert.strictEqual(widgetFromValues("count", blankValues(), { id: 41 }).id, 41);
  assert.strictEqual("id" in widgetFromValues("count", blankValues(), {}), false);
});

check("choice fields are copied only when one was chosen", () => {
  const widget = widgetFromValues("trend", blankValues({ group_by: "status", chart: "donut", measure: "", interval: "" }));
  assert.strictEqual(widget.group_by, "status");
  assert.strictEqual(widget.chart, "donut");
  assert.strictEqual("measure" in widget, false);
  assert.strictEqual("interval" in widget, false);
});

check("number fields become numbers, and blank or missing ones are left out", () => {
  const widget = widgetFromValues("cycle", blankValues({ days: "30", limit: "", iteration: undefined }));
  assert.strictEqual(widget.days, 30);
  assert.strictEqual("limit" in widget, false);
  assert.strictEqual("iteration" in widget, false);
});

check("a number field set to zero is kept, whether it arrives as text or as a number", () => {
  assert.strictEqual(widgetFromValues("cycle", blankValues({ days: "0" })).days, 0);
  assert.strictEqual(widgetFromValues("cycle", blankValues({ days: 0 })).days, 0);
});

check("only filled filters are stored and the open flag is a boolean", () => {
  const widget = widgetFromValues("group", blankValues({ f_project: "LED", f_area: "", f_type: "bug", f_priority: "", f_assignee: "azazel", f_label: "", f_open: true }));
  assert.deepStrictEqual(widget.filters, { project: "LED", type: "bug", assignee: "azazel", open: true });
});

check("an unchecked open box leaves no open filter", () => {
  assert.deepStrictEqual(widgetFromValues("group", blankValues({ f_open: false })).filters, {});
});

check("the form values show the width as text and blank what is not set", () => {
  const values = widgetValues({ title: "A", size: 2, kind: "count" });
  assert.strictEqual(values.size, "2");
  assert.deepStrictEqual([values.interval, values.iteration, values.f_project, values.f_area, values.f_type, values.f_priority, values.f_assignee, values.f_label, values.f_open], ["", "", "", "", "", "", "", "", false]);
});

check("the form values turn the area and iteration numbers into text", () => {
  const values = widgetValues({ title: "A", size: 1, iteration: 7, filters: { area: 12, open: true } });
  assert.strictEqual(values.iteration, "7");
  assert.strictEqual(values.f_area, "12");
  assert.strictEqual(values.f_open, true);
});

const WIDGETS = [
  { id: 1, kind: "group", title: "By status", size: 1, group_by: "status", chart: "donut", limit: 8, filters: {} },
  { id: 2, kind: "count", title: "Closed", size: 1, measure: "closed", days: 7, filters: { project: "LED", open: true } },
  { id: 3, kind: "trend", title: "Created", size: 2, days: 30, interval: "week", filters: { type: "bug", priority: "high", assignee: "azazel", label: "tests", area: "12" } },
  { id: 4, kind: "burndown", title: "Sprint", size: 2, iteration: 9, filters: {} },
];

check("editing a widget without touching it gives the same widget back", () => {
  for (const widget of WIDGETS) assert.deepStrictEqual(widgetFromValues(widget.kind, widgetValues(widget), widget), widget, widget.title);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
