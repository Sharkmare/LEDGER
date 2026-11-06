"use strict";

const assert = require("assert");
const path = require("path");
const { kbSearchTransition } = require(path.join(__dirname, "..", "..", "ledger", "static", "kbsearch.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

check("typing in a space searches that space and remembers where to return", () => {
  const next = kbSearchTransition({ view: "space", spaceId: 14, pageId: null }, "badges");
  assert.strictEqual(next.view, "search");
  assert.strictEqual(next.query, "badges");
  assert.strictEqual(next.searchSpaceId, 14);
  assert.deepStrictEqual(next.back, { view: "space", spaceId: 14, pageId: null });
});

check("typing on a page searches its space and returns to the page", () => {
  const next = kbSearchTransition({ view: "page", spaceId: 14, pageId: 99 }, "x");
  assert.strictEqual(next.searchSpaceId, 14);
  assert.deepStrictEqual(next.back, { view: "page", spaceId: 14, pageId: 99 });
  assert.strictEqual(next.pageId, null);
});

check("typing on the home or tools view searches every space", () => {
  assert.strictEqual(kbSearchTransition({ view: "home", spaceId: 3, pageId: null }, "x").searchSpaceId, null);
  assert.strictEqual(kbSearchTransition({ view: "tools", spaceId: 3, pageId: null }, "x").searchSpaceId, null);
});

check("typing more while searching only changes the query", () => {
  assert.deepStrictEqual(kbSearchTransition({ view: "search", spaceId: 14, pageId: null }, "more words"), { query: "more words" });
});

check("clearing the box returns to the saved view and forgets the search", () => {
  const kb = { view: "search", query: "x", back: { view: "page", spaceId: 14, pageId: 99 } };
  assert.deepStrictEqual(kbSearchTransition(kb, ""), { view: "page", spaceId: 14, pageId: 99, query: "", back: null });
});

check("clearing without a saved view goes home, and clearing outside a search does nothing", () => {
  assert.strictEqual(kbSearchTransition({ view: "search", query: "x", back: null }, "").view, "home");
  assert.strictEqual(kbSearchTransition({ view: "space", spaceId: 1, pageId: null }, ""), null);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} knowledge base search checks passed`);
process.exit(failed ? 1 : 0);
