"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { moduleFormFields, widgetFromValues, widgetValues, newWidgetDefaults, usableFilterFields } = require(path.join(__dirname, "..", "..", "ledger", "static", "widgetform.js"));

const listing = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const byId = Object.fromEntries(listing.modules.map((item) => [item.id, item]));
const blankValues = (overrides = {}) => ({ title: "T", size: "1", ...overrides });
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("a new widget gets the module id, a trimmed title and a numeric width, and no id", () => {
  const widget = widgetFromValues(byId.count, blankValues({ title: "  Closed lately  ", size: "2", measure: "", days: "" }));
  assert.deepStrictEqual(widget, { kind: "count", title: "Closed lately", size: 2, filters: {} });
});

check("an edited widget keeps its id", () => {
  assert.strictEqual(widgetFromValues(byId.count, blankValues(), { id: 41 }).id, 41);
  assert.strictEqual("id" in widgetFromValues(byId.count, blankValues(), {}), false);
});

check("choice settings are copied only when one was chosen", () => {
  const widget = widgetFromValues(byId.trend, blankValues({ interval: "week", group_by: "status" }));
  assert.strictEqual(widget.interval, "week");
  assert.strictEqual("group_by" in widget, false);
  assert.strictEqual("interval" in widgetFromValues(byId.trend, blankValues({ interval: "" })), false);
});

check("number settings become numbers, and blank or missing ones are left out", () => {
  const widget = widgetFromValues(byId.cycle, blankValues({ days: "30" }));
  assert.strictEqual(widget.days, 30);
  assert.strictEqual("days" in widgetFromValues(byId.cycle, blankValues({ days: "" })), false);
  assert.strictEqual("days" in widgetFromValues(byId.cycle, blankValues()), false);
});

check("a number set to zero is kept, whether it arrives as text or as a number", () => {
  assert.strictEqual(widgetFromValues(byId.cycle, blankValues({ days: "0" })).days, 0);
  assert.strictEqual(widgetFromValues(byId.cycle, blankValues({ days: 0 })).days, 0);
});

check("only filled filters are stored and the open flag is a boolean", () => {
  const widget = widgetFromValues(byId.group, blankValues({ f_project: "LED", f_area: "", f_type: "bug", f_priority: "", f_assignee: "azazel", f_label: "", f_open: true }));
  assert.deepStrictEqual(widget.filters, { project: "LED", type: "bug", assignee: "azazel", open: true });
  assert.deepStrictEqual(widgetFromValues(byId.group, blankValues({ f_open: false })).filters, {});
});

check("a module that honours only some filters ignores the others", () => {
  assert.deepStrictEqual(widgetFromValues(byId.burndown, blankValues({ f_project: "LED", f_type: "bug" })).filters, { project: "LED" });
  assert.deepStrictEqual(usableFilterFields(byId.burndown).map((f) => f.filter), ["project"]);
});

check("the iteration setting is a select whose blank choice says what blank means", () => {
  const fields = moduleFormFields(byId.burndown, { iterations: [{ id: 9, project: "LED", name: "Sprint 9" }] });
  const iteration = fields.find((f) => f.name === "iteration");
  assert.strictEqual(iteration.kind, "select");
  assert.deepStrictEqual(iteration.options, [{ value: "", label: "The current one" }, { value: "9", label: "LED Sprint 9" }]);
  assert.strictEqual(widgetFromValues(byId.burndown, blankValues({ iteration: "9" })).iteration, 9);
});

check("the form lists title, width, the module settings, then the filters it uses", () => {
  const names = moduleFormFields(byId.count, {}).map((f) => f.name || f.group);
  assert.deepStrictEqual(names, ["title", "size", "measure", "days", "Which tickets", "f_project", "f_area", "f_type", "f_priority", "f_assignee", "f_label", "f_open"]);
  assert.deepStrictEqual(moduleFormFields(byId.burndown, {}).map((f) => f.name || f.group), ["title", "size", "iteration", "Which tickets", "f_project"]);
});

check("filter choices come from the lists the page supplies, led by an any option", () => {
  const fields = moduleFormFields(byId.group, { projects: [{ value: "LED", label: "LED Ledger" }], types: [{ value: "bug", label: "bug" }] });
  assert.deepStrictEqual(fields.find((f) => f.name === "f_project").options, [{ value: "", label: "All" }, { value: "LED", label: "LED Ledger" }]);
  assert.deepStrictEqual(fields.find((f) => f.name === "f_type").options, [{ value: "", label: "Any" }, { value: "bug", label: "bug" }]);
});

check("a module setting with a minimum puts it on the number field", () => {
  const days = moduleFormFields(byId.count, {}).find((f) => f.name === "days");
  assert.deepStrictEqual([days.kind, days.min], ["number", 1]);
});

check("the form values show the width as text and blank what is not set", () => {
  const values = widgetValues(byId.trend, { title: "A", size: 2, kind: "trend", days: 30 });
  assert.deepStrictEqual([values.size, values.days, values.interval, values.f_project, values.f_open], ["2", 30, "", "", false]);
});

check("the form values turn area and iteration numbers into text", () => {
  assert.strictEqual(widgetValues(byId.burndown, { title: "A", size: 1, iteration: 7, filters: {} }).iteration, "7");
  const values = widgetValues(byId.group, { title: "A", size: 1, filters: { area: 12, open: true } });
  assert.deepStrictEqual([values.f_area, values.f_open], ["12", true]);
});

check("a new widget starts from the defaults the module declares", () => {
  assert.deepStrictEqual(newWidgetDefaults(byId.count), { title: "", size: 1, filters: {}, measure: "total", days: 7 });
  assert.strictEqual(newWidgetDefaults(byId.trend).size, 2);
  assert.strictEqual("interval" in newWidgetDefaults(byId.trend), false);
});

const WIDGETS = [
  { id: 1, kind: "group", title: "By status", size: 1, group_by: "status", chart: "donut", limit: 8, filters: {} },
  { id: 2, kind: "count", title: "Closed", size: 1, measure: "closed", days: 7, filters: { project: "LED", open: true } },
  { id: 3, kind: "trend", title: "Created", size: 2, days: 30, interval: "week", filters: { type: "bug", priority: "high", assignee: "azazel", label: "tests", area: "12" } },
  { id: 4, kind: "burndown", title: "Sprint", size: 2, iteration: 9, filters: {} },
];

check("editing a widget without touching it gives the same widget back", () => {
  for (const widget of WIDGETS) assert.deepStrictEqual(widgetFromValues(byId[widget.kind], widgetValues(byId[widget.kind], widget), widget), widget, widget.title);
});

check("a custom module with a checkbox and a text setting round trips", () => {
  const custom = { id: "note", title: "Note", size: 1, filters: [], settings: [
    { name: "loud", label: "Loud", kind: "checkbox" }, { name: "text", label: "Text", kind: "text" }] };
  const widget = widgetFromValues(custom, widgetValues(custom, { title: "N", size: 1, loud: true, text: " hi ", filters: {} }));
  assert.deepStrictEqual(widget, { kind: "note", title: "N", size: 1, loud: true, text: "hi", filters: {} });
  assert.deepStrictEqual(moduleFormFields(custom, {}).map((f) => f.name || f.group), ["title", "size", "loud", "text"]);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
