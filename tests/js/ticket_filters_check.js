"use strict";

const assert = require("assert");
const path = require("path");
const { ticketFilters, ticketQuery } = require(path.join(__dirname, "..", "..", "ledger", "static", "ticketfilters.js"));

const NO_FILTERS = { assignee: "", status: "", type: "", priority: "", label: "", open: "" };
const filtersFor = (overrides = {}) => ticketFilters({ project: "", nav: "all", filters: NO_FILTERS, hiddenTypes: [], actor: "azazel", search: "", ...overrides });
const queryOf = (overrides) => ticketQuery(filtersFor(overrides)).toString();
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("all work sends nothing", () => {
  assert.strictEqual(queryOf(), "");
});

check("assigned to me filters on the person using the page", () => {
  assert.strictEqual(filtersFor({ nav: "mine" }).assignee, "azazel");
  assert.strictEqual(filtersFor({ nav: "mine", filters: { ...NO_FILTERS, assignee: "swarm" } }).assignee, "azazel");
});

check("another view uses the assignee picked in the filter bar", () => {
  assert.strictEqual(filtersFor({ filters: { ...NO_FILTERS, assignee: "swarm" } }).assignee, "swarm");
});

check("blocked work asks for the blocked status whatever status was picked", () => {
  assert.strictEqual(filtersFor({ nav: "blocked" }).status, "blocked");
  assert.strictEqual(filtersFor({ nav: "blocked", filters: { ...NO_FILTERS, status: "todo" } }).status, "blocked");
  assert.strictEqual(filtersFor({ filters: { ...NO_FILTERS, status: "todo" } }).status, "todo");
});

check("open questions asks for tickets with an open question", () => {
  assert.strictEqual(queryOf({ nav: "questions" }), "questions=open");
});

check("open work and the open toggle both ask for open tickets", () => {
  assert.strictEqual(queryOf({ nav: "open" }), "open=1");
  assert.strictEqual(queryOf({ filters: { ...NO_FILTERS, open: true } }), "open=1");
});

check("the project, type, priority and tag filters are passed along", () => {
  const query = new URLSearchParams(queryOf({ project: "LED", filters: { ...NO_FILTERS, type: "bug", priority: "high", label: "ui" } }));
  assert.deepStrictEqual([...query.entries()].sort(), [["label", "ui"], ["priority", "high"], ["project", "LED"], ["type", "bug"]]);
});

check("hidden types are sent as one comma separated list", () => {
  assert.strictEqual(filtersFor({ hiddenTypes: ["chore", "spike"] }).exclude_type, "chore,spike");
  assert.strictEqual(filtersFor().exclude_type, "");
});

check("the search text is trimmed and an all blank search is dropped", () => {
  assert.strictEqual(filtersFor({ search: "  fix it  " }).q, "fix it");
  assert.strictEqual(queryOf({ search: "   " }), "");
});

check("empty values never reach the address and others are encoded", () => {
  const query = ticketQuery({ project: "", q: "a&b c", open: "1", label: undefined });
  assert.strictEqual(query.toString(), "q=a%26b+c&open=1");
});

check("the person using the page is only read when the view needs it", () => {
  assert.strictEqual(queryOf({ actor: "someone else" }), "");
  assert.strictEqual(queryOf({ nav: "mine", actor: "someone else" }), "assignee=someone+else");
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
