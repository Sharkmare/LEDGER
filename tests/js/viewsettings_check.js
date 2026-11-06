"use strict";

const assert = require("assert");
const path = require("path");
const { parseHiddenTypes, toggledHiddenType, visibleTickets, hiddenTypesParameter, hiddenTypesLabel, shownColumns, hiddenColumnsLabel } = require(path.join(__dirname, "..", "..", "ledger", "static", "viewsettings.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

const TYPES = ["task", "bug", "feature", "epic", "story", "spike", "chore"];

check("a saved list is read back in the order of the known types", () => {
  assert.deepStrictEqual(parseHiddenTypes('["chore", "bug"]', TYPES), ["bug", "chore"]);
});

check("anything unusable in storage means nothing is hidden", () => {
  assert.deepStrictEqual(parseHiddenTypes("not json", TYPES), []);
  assert.deepStrictEqual(parseHiddenTypes('{"bug": true}', TYPES), []);
  assert.deepStrictEqual(parseHiddenTypes("null", TYPES), []);
  assert.deepStrictEqual(parseHiddenTypes("[]", TYPES), []);
});

check("a type that no longer exists is dropped from a saved list", () => {
  assert.deepStrictEqual(parseHiddenTypes('["saga", "bug", 7]', TYPES), ["bug"]);
});

check("toggling hides a shown type and shows a hidden one, keeping the known order", () => {
  assert.deepStrictEqual(toggledHiddenType([], "chore", TYPES), ["chore"]);
  assert.deepStrictEqual(toggledHiddenType(["chore"], "bug", TYPES), ["bug", "chore"]);
  assert.deepStrictEqual(toggledHiddenType(["bug", "chore"], "bug", TYPES), ["chore"]);
  assert.deepStrictEqual(toggledHiddenType(["bug"], "bug", TYPES), []);
});

check("tickets of hidden types are left out and the rest keep their order", () => {
  const tickets = [{ key: "A-1", type: "bug" }, { key: "A-2", type: "task" }, { key: "A-3", type: "chore" }, { key: "A-4", type: "task" }];
  assert.deepStrictEqual(visibleTickets(tickets, ["bug", "chore"]).map((t) => t.key), ["A-2", "A-4"]);
  assert.deepStrictEqual(visibleTickets(tickets, []).map((t) => t.key), ["A-1", "A-2", "A-3", "A-4"]);
  assert.strictEqual(visibleTickets(tickets, []), tickets);
});

check("hiding every type shows no tickets", () => {
  assert.deepStrictEqual(visibleTickets([{ key: "A-1", type: "bug" }], ["bug"]), []);
});

check("the API parameter and the chip label list the hidden types", () => {
  assert.strictEqual(hiddenTypesParameter(["bug", "chore"]), "bug,chore");
  assert.strictEqual(hiddenTypesParameter([]), "");
  assert.strictEqual(hiddenTypesLabel(["bug", "chore"]), "Hiding bug, chore");
  assert.strictEqual(hiddenTypesLabel([]), "");
});

const STATUSES = ["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"];

check("hidden statuses are read back and toggled in the order of the known statuses", () => {
  assert.deepStrictEqual(parseHiddenTypes('["cancelled", "done", "gone"]', STATUSES), ["done", "cancelled"]);
  assert.deepStrictEqual(toggledHiddenType(["cancelled"], "done", STATUSES), ["done", "cancelled"]);
  assert.deepStrictEqual(toggledHiddenType(["done", "cancelled"], "done", STATUSES), ["cancelled"]);
});

check("hidden board columns are left out and the rest keep their order", () => {
  assert.deepStrictEqual(shownColumns(STATUSES, ["done", "cancelled"]), ["backlog", "todo", "in_progress", "in_review", "blocked"]);
  assert.strictEqual(shownColumns(STATUSES, []), STATUSES);
  assert.deepStrictEqual(shownColumns(STATUSES, STATUSES), []);
});

check("a board that does not use a hidden status is unchanged", () => {
  assert.deepStrictEqual(shownColumns(["todo", "done"], ["cancelled"]), ["todo", "done"]);
});

check("the hidden columns chip names them with their labels", () => {
  assert.strictEqual(hiddenColumnsLabel(["done", "cancelled"]), "Hiding done, cancelled");
  assert.strictEqual(hiddenColumnsLabel(["in_review"], (s) => s.replace("_", " ")), "Hiding in review");
  assert.strictEqual(hiddenColumnsLabel([]), "");
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} view setting checks passed`);
process.exit(failed ? 1 : 0);
