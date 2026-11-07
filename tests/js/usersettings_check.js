"use strict";

const assert = require("assert");
const path = require("path");
const { cachedTextsFor, cleanSetting, parseStoredSetting, resolveSetting, planSettings } = require(path.join(__dirname, "..", "..", "ledger", "static", "usersettings.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

const VOCABULARY = {
  types: ["task", "bug", "feature", "epic", "story", "spike", "chore"],
  statuses: ["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"],
  sortFields: ["key", "title", "status", "priority", "type", "assignee", "estimate", "updated"],
};
const NO_LOCAL = { hidden_types: "", hidden_statuses: "", sort: "" };

check("the server value wins over a different local value", () => {
  assert.deepStrictEqual(resolveSetting("hidden_statuses", ["done"], ["blocked"]), { value: ["done"], source: "server", upload: false });
});

check("an empty list on the server still wins, so clearing on one browser reaches the others", () => {
  assert.deepStrictEqual(resolveSetting("hidden_types", [], ["bug"]), { value: [], source: "server", upload: false });
  assert.strictEqual(resolveSetting("sort", { field: "", direction: "asc" }, { field: "key", direction: "asc" }).source, "server");
});

check("without a server value the local choice is used and marked for upload", () => {
  assert.deepStrictEqual(resolveSetting("hidden_types", null, ["bug"]), { value: ["bug"], source: "local", upload: true });
  assert.deepStrictEqual(resolveSetting("sort", undefined, { field: "priority", direction: "desc" }),
    { value: { field: "priority", direction: "desc" }, source: "local", upload: true });
});

check("with neither the default is used and nothing is uploaded", () => {
  assert.deepStrictEqual(resolveSetting("hidden_statuses", null, null), { value: [], source: "default", upload: false });
  assert.deepStrictEqual(resolveSetting("sort", null, null), { value: { field: "", direction: "asc" }, source: "default", upload: false });
  assert.deepStrictEqual(resolveSetting("hidden_types", null, []), { value: [], source: "default", upload: false });
  assert.strictEqual(resolveSetting("sort", null, { field: "", direction: "asc" }).upload, false);
});

check("stored text that is unusable counts as no choice", () => {
  assert.strictEqual(parseStoredSetting("hidden_types", "not json", VOCABULARY), null);
  assert.strictEqual(parseStoredSetting("hidden_types", '{"bug":true}', VOCABULARY), null);
  assert.strictEqual(parseStoredSetting("sort", '{"field":"colour","direction":"asc"}', VOCABULARY), null);
  assert.strictEqual(parseStoredSetting("sort", "", VOCABULARY), null);
});

check("lists keep the known order and drop names that no longer exist", () => {
  assert.deepStrictEqual(cleanSetting("hidden_types", ["chore", "saga", "bug"], VOCABULARY), ["bug", "chore"]);
  assert.deepStrictEqual(cleanSetting("sort", { field: "key", direction: "sideways" }, VOCABULARY), { field: "key", direction: "asc" });
});

check("the plan mirrors the server and uploads only what the server lacks", () => {
  const plan = planSettings({ hidden_statuses: ["done"] }, { hidden_types: '["bug"]', hidden_statuses: '["blocked"]', sort: "" }, VOCABULARY);
  assert.deepStrictEqual(plan.values, { hidden_types: ["bug"], hidden_statuses: ["done"], sort: { field: "", direction: "asc" } });
  assert.deepStrictEqual(plan.uploads, ["hidden_types"]);
  assert.strictEqual(plan.reachable, true);
});

check("an unreachable server falls back to local values and uploads nothing", () => {
  const plan = planSettings(null, { hidden_types: '["bug"]', hidden_statuses: "", sort: '{"field":"key","direction":"desc"}' }, VOCABULARY);
  assert.deepStrictEqual(plan.values, { hidden_types: ["bug"], hidden_statuses: [], sort: { field: "key", direction: "desc" } });
  assert.deepStrictEqual(plan.uploads, []);
  assert.strictEqual(plan.reachable, false);
});

check("a person with nothing anywhere gets the defaults", () => {
  const plan = planSettings({}, NO_LOCAL, VOCABULARY);
  assert.deepStrictEqual(plan.values, { hidden_types: [], hidden_statuses: [], sort: { field: "", direction: "asc" } });
  assert.deepStrictEqual(plan.uploads, []);
});

check("a browser copy that belongs to another name is never uploaded for this one", () => {
  const texts = { hidden_types: '["bug"]', hidden_statuses: '["done"]', sort: "" };
  assert.deepStrictEqual(cachedTextsFor("Ann", "bob", texts), NO_LOCAL);
  assert.deepStrictEqual(cachedTextsFor("Ann", " ANN ", texts), texts);
  assert.deepStrictEqual(cachedTextsFor("", "bob", texts), texts);
  assert.deepStrictEqual(cachedTextsFor(null, "bob", texts), texts);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} user setting checks passed`);
process.exit(failed ? 1 : 0);
