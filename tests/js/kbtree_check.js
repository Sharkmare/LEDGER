"use strict";

const assert = require("assert");
const path = require("path");
const { kbExpandedKey, kbParseExpanded, kbWithExpanded, kbWithoutExpanded, kbAncestorsToReveal, kbIsServerRejection } = require(path.join(__dirname, "..", "..", "ledger", "static", "kbtree.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

check("each space keeps its own list of open folders", () => {
  assert.notStrictEqual(kbExpandedKey(6), kbExpandedKey(14));
  assert.strictEqual(kbExpandedKey(6), kbExpandedKey(6));
});

check("a saved list is read back and anything unusable becomes empty", () => {
  assert.deepStrictEqual(kbParseExpanded("[3, 9]"), [3, 9]);
  assert.deepStrictEqual(kbParseExpanded("[]"), []);
  assert.deepStrictEqual(kbParseExpanded("not json"), []);
  assert.deepStrictEqual(kbParseExpanded('{"a": 1}'), []);
  assert.deepStrictEqual(kbParseExpanded('[1, "x", null, 2.5, 4]'), [1, 4]);
});

check("opening folders adds each id once", () => {
  assert.deepStrictEqual(kbWithExpanded([3, 9], [9, 12]), [3, 9, 12]);
  assert.deepStrictEqual(kbWithExpanded([], []), []);
});

check("closing or dropping a folder removes only that id", () => {
  assert.deepStrictEqual(kbWithoutExpanded([3, 9, 12], 9), [3, 12]);
  assert.deepStrictEqual(kbWithoutExpanded([3], 99), [3]);
});

check("ancestors open only when a different page is shown, so a refresh never re-opens a folder the reader closed", () => {
  assert.deepStrictEqual(kbAncestorsToReveal(null, 18, [3, 9]), [3, 9]);
  assert.deepStrictEqual(kbAncestorsToReveal(5, 18, [3, 9]), [3, 9]);
  assert.deepStrictEqual(kbAncestorsToReveal(18, 18, [3, 9]), []);
});

check("only a refusal from the server drops a remembered folder, not a network failure", () => {
  assert.strictEqual(kbIsServerRejection(new Error("a page and its parent must be in the same space")), true);
  assert.strictEqual(kbIsServerRejection(new TypeError("Failed to fetch")), false);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} knowledge base tree checks passed`);
process.exit(failed ? 1 : 0);
