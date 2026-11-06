"use strict";

const assert = require("assert");
const path = require("path");
const { parseHiddenTypes, toggledHiddenType, visibleTickets, hiddenTypesParameter, hiddenTypesLabel } = require(path.join(__dirname, "..", "..", "ledger", "static", "viewsettings.js"));

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

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} view setting checks passed`);
process.exit(failed ? 1 : 0);
