"use strict";

const assert = require("assert");
const path = require("path");
const { toggledKey, rangeKeys, withRange, withAll, selectAllState, prunedSelection, bulkChanges, buildBulkRequests, mergeBulkResults, bulkSummary, BULK_MAX_KEYS } = require(path.join(__dirname, "..", "..", "ledger", "static", "bulk.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

const SHOWN = ["A-1", "A-2", "A-3", "A-4", "A-5"];

check("toggling adds a key once and removes it again", () => {
  assert.deepStrictEqual(toggledKey([], "A-1", true), ["A-1"]);
  assert.deepStrictEqual(toggledKey(["A-1"], "A-1", true), ["A-1"]);
  assert.deepStrictEqual(toggledKey(["A-1", "A-2"], "A-1", false), ["A-2"]);
});

check("a range covers both ends in either direction", () => {
  assert.deepStrictEqual(rangeKeys(SHOWN, "A-2", "A-4"), ["A-2", "A-3", "A-4"]);
  assert.deepStrictEqual(rangeKeys(SHOWN, "A-4", "A-2"), ["A-2", "A-3", "A-4"]);
  assert.deepStrictEqual(rangeKeys(SHOWN, "A-3", "A-3"), ["A-3"]);
});

check("a range with an unknown anchor is just the target, and an unknown target is nothing", () => {
  assert.deepStrictEqual(rangeKeys(SHOWN, "Z-9", "A-2"), ["A-2"]);
  assert.deepStrictEqual(rangeKeys(SHOWN, "A-2", "Z-9"), []);
});

check("shift selecting keeps earlier picks and does not duplicate", () => {
  assert.deepStrictEqual(withRange(["A-1", "A-3"], SHOWN, "A-3", "A-5", true).sort(), ["A-1", "A-3", "A-4", "A-5"]);
});

check("shift unselecting clears only the range", () => {
  assert.deepStrictEqual(withRange(["A-1", "A-2", "A-3", "A-4"], SHOWN, "A-2", "A-3", false), ["A-1", "A-4"]);
});

check("select all takes the shown rows and keeps picks that are not shown", () => {
  assert.deepStrictEqual(withAll(["Z-1"], SHOWN, true), ["Z-1", ...SHOWN]);
  assert.deepStrictEqual(withAll(["Z-1", ...SHOWN], SHOWN, false), ["Z-1"]);
});

check("the select all box is none, some or all of the shown rows", () => {
  assert.strictEqual(selectAllState([], SHOWN), "none");
  assert.strictEqual(selectAllState(["A-2", "Z-1"], SHOWN), "some");
  assert.strictEqual(selectAllState(SHOWN, SHOWN), "all");
});

check("rows that are no longer shown drop out of the selection", () => {
  assert.deepStrictEqual(prunedSelection(["A-1", "Z-1", "A-3"], SHOWN), ["A-1", "A-3"]);
});

check("each action builds its change", () => {
  assert.deepStrictEqual(bulkChanges("status", "done"), { status: "done" });
  assert.deepStrictEqual(bulkChanges("priority", "high"), { priority: "high" });
  assert.deepStrictEqual(bulkChanges("assignee", " ann "), { assignee: "ann" });
  assert.deepStrictEqual(bulkChanges("tag", " UI "), { add_labels: ["ui"] });
  assert.deepStrictEqual(bulkChanges("cancel", ""), { status: "cancelled" });
  assert.throws(() => bulkChanges("explode", "x"));
});

check("a request carries the keys, the change and a trimmed comment only when given", () => {
  assert.deepStrictEqual(buildBulkRequests(["A-1"], "status", "done"), [{ keys: ["A-1"], changes: { status: "done" } }]);
  assert.deepStrictEqual(buildBulkRequests(["A-1"], "cancel", "", "  not needed "), [{ keys: ["A-1"], changes: { status: "cancelled" }, comment: "not needed" }]);
  assert.strictEqual(buildBulkRequests(["A-1"], "cancel", "", "   ")[0].comment, undefined);
});

check("an empty value builds no request, but cancel needs none", () => {
  assert.deepStrictEqual(buildBulkRequests(["A-1"], "status", ""), []);
  assert.deepStrictEqual(buildBulkRequests(["A-1"], "tag", "  "), []);
  assert.strictEqual(buildBulkRequests(["A-1"], "cancel", "").length, 1);
});

check("more than the limit is split into requests of at most the limit", () => {
  const keys = Array.from({ length: BULK_MAX_KEYS * 2 + 1 }, (_, n) => `A-${n + 1}`);
  const requests = buildBulkRequests(keys, "priority", "low");
  assert.deepStrictEqual(requests.map((r) => r.keys.length), [BULK_MAX_KEYS, BULK_MAX_KEYS, 1]);
  assert.deepStrictEqual(requests.flatMap((r) => r.keys), keys);
});

check("results from several requests merge and summarise", () => {
  const merged = mergeBulkResults([
    { updated: ["A-1"], unchanged: [], failed: [] },
    { updated: ["A-2"], unchanged: ["A-3"], failed: [{ key: "A-4", error: "no such ticket" }] },
  ]);
  assert.deepStrictEqual(merged, { updated: ["A-1", "A-2"], unchanged: ["A-3"], failed: [{ key: "A-4", error: "no such ticket" }] });
  assert.strictEqual(bulkSummary(merged), "2 updated, 1 unchanged, 1 failed: A-4 no such ticket");
  assert.strictEqual(bulkSummary({ updated: ["A-1"], unchanged: [], failed: [] }), "1 updated");
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} bulk selection checks passed`);
process.exit(failed ? 1 : 0);
