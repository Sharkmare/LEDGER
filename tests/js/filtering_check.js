"use strict";

const assert = require("assert");
const path = require("path");
const { FILTER_FIELDS, emptyFilters, activeFilters, toggledFilter, clearedFilter } = require(path.join(__dirname, "..", "..", "ledger", "static", "filtering.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

check("no filter is active by default", () => {
  assert.deepStrictEqual(activeFilters(emptyFilters()), []);
});

check("choosing a value activates it and choosing it again clears it", () => {
  const chosen = toggledFilter(emptyFilters(), "priority", "high");
  assert.deepStrictEqual(activeFilters(chosen), [{ id: "priority", label: "Priority", value: "high" }]);
  assert.deepStrictEqual(activeFilters(toggledFilter(chosen, "priority", "high")), []);
});

check("choosing another value replaces the first", () => {
  const second = toggledFilter(toggledFilter(emptyFilters(), "type", "bug"), "type", "task");
  assert.strictEqual(second.type, "task");
});

check("hide done toggles and lists last", () => {
  const filters = toggledFilter(toggledFilter(emptyFilters(), "open"), "assignee", "amy");
  assert.deepStrictEqual(activeFilters(filters).map((entry) => entry.id), ["assignee", "open"]);
  assert.strictEqual(toggledFilter(filters, "open").open, false);
});

check("clearing one filter leaves the others and the input untouched", () => {
  const filters = toggledFilter(toggledFilter(emptyFilters(), "label", "ui"), "status", "todo");
  const cleared = clearedFilter(filters, "label");
  assert.deepStrictEqual(activeFilters(cleared).map((entry) => entry.id), ["status"]);
  assert.strictEqual(filters.label, "ui");
  assert.strictEqual(clearedFilter(toggledFilter(emptyFilters(), "open"), "open").open, false);
});

check("every field the filter bar offered has a definition", () => {
  assert.deepStrictEqual(FILTER_FIELDS.map((field) => field.id), ["status", "priority", "type", "assignee", "label"]);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} filtering checks passed`);
process.exit(failed ? 1 : 0);
