"use strict";

const assert = require("assert");
const path = require("path");
const { naturalCompare, sortTickets, nextSort } = require(path.join(__dirname, "..", "..", "ledger", "static", "sorting.js"));

const vocabulary = {
  statuses: ["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"],
  priorities: ["lowest", "low", "medium", "high", "critical", "blocker"],
};
const ticket = (key, fields = {}) => ({ key, title: key, status: "todo", priority: "medium", type: "task", assignee: "", estimate: null, updated: 0, ...fields });
const keys = (tickets) => tickets.map((t) => t.key);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("keys sort in number order, not text order", () => {
  const sorted = sortTickets([ticket("REO-10"), ticket("REO-2"), ticket("REO-1"), ticket("REO-20")], { field: "key", direction: "asc" }, vocabulary);
  assert.deepStrictEqual(keys(sorted), ["REO-1", "REO-2", "REO-10", "REO-20"]);
});

check("zero padded keys stay in order", () => {
  const sorted = sortTickets([ticket("REO-03"), ticket("REO-01"), ticket("REO-02")], { field: "key", direction: "asc" }, vocabulary);
  assert.deepStrictEqual(keys(sorted), ["REO-01", "REO-02", "REO-03"]);
});

check("projects sort by name before number", () => {
  const sorted = sortTickets([ticket("EXL-2"), ticket("CHAOS-11"), ticket("EXL-1"), ticket("CHAOS-2")], { field: "key", direction: "asc" }, vocabulary);
  assert.deepStrictEqual(keys(sorted), ["CHAOS-2", "CHAOS-11", "EXL-1", "EXL-2"]);
});

check("descending reverses the order", () => {
  const sorted = sortTickets([ticket("A-1"), ticket("A-3"), ticket("A-2")], { field: "key", direction: "desc" }, vocabulary);
  assert.deepStrictEqual(keys(sorted), ["A-3", "A-2", "A-1"]);
});

check("status follows the workflow, not the alphabet", () => {
  const tickets = [ticket("A-1", { status: "done" }), ticket("A-2", { status: "backlog" }), ticket("A-3", { status: "in_progress" }), ticket("A-4", { status: "blocked" })];
  assert.deepStrictEqual(keys(sortTickets(tickets, { field: "status", direction: "asc" }, vocabulary)), ["A-2", "A-3", "A-4", "A-1"]);
});

check("priority follows its ranking and a tie falls back to key order", () => {
  const tickets = [ticket("A-10", { priority: "high" }), ticket("A-2", { priority: "high" }), ticket("A-3", { priority: "blocker" }), ticket("A-4", { priority: "low" })];
  assert.deepStrictEqual(keys(sortTickets(tickets, { field: "priority", direction: "desc" }, vocabulary)), ["A-3", "A-2", "A-10", "A-4"]);
});

check("blank assignees and estimates come last in both directions", () => {
  const tickets = [ticket("A-1"), ticket("A-2", { assignee: "zed", estimate: 5 }), ticket("A-3", { assignee: "amy", estimate: 2 })];
  for (const direction of ["asc", "desc"]) {
    assert.strictEqual(keys(sortTickets(tickets, { field: "assignee", direction }, vocabulary)).pop(), "A-1");
    assert.strictEqual(keys(sortTickets(tickets, { field: "estimate", direction }, vocabulary)).pop(), "A-1");
  }
});

check("no field keeps the given order and the input is not modified", () => {
  const tickets = [ticket("A-2"), ticket("A-1")];
  assert.strictEqual(sortTickets(tickets, { field: "", direction: "asc" }, vocabulary), tickets);
  sortTickets(tickets, { field: "key", direction: "asc" }, vocabulary);
  assert.deepStrictEqual(keys(tickets), ["A-2", "A-1"]);
});

check("a new column starts in its natural direction and the same column flips", () => {
  assert.deepStrictEqual(nextSort({ field: "key", direction: "asc" }, "priority"), { field: "priority", direction: "desc" });
  assert.deepStrictEqual(nextSort({ field: "priority", direction: "desc" }, "priority"), { field: "priority", direction: "asc" });
  assert.deepStrictEqual(nextSort(null, "key"), { field: "key", direction: "asc" });
});

check("natural compare orders text and numbers inside titles", () => {
  assert(naturalCompare("Stage 2", "Stage 10") < 0);
  assert(naturalCompare("alpha", "Beta") < 0);
  assert.strictEqual(naturalCompare("same", "same"), 0);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} sorting checks passed`);
process.exit(failed ? 1 : 0);
