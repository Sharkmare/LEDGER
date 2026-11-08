"use strict";

const assert = require("assert");
const path = require("path");
const { descendantsOf, treeMovePlan } = require(path.join(__dirname, "..", "..", "ledger", "static", "treemoves.js"));

const page = (id, parentId, position) => ({ id, parent_id: parentId, position });
const FLAT = [page(1, null, 1), page(2, null, 2), page(3, null, 3), page(4, 1, 1), page(5, 1, 2)];
const target = (id) => FLAT.find((p) => p.id === id);
const area = (id, parentId) => ({ id, parent_id: parentId });
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("dropping before a page puts the dragged page first and pushes the rest down", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 3, target(1), "before"), { parent: "", position: 1, renumber: [{ id: 1, position: 2 }, { id: 2, position: 3 }] });
});

check("dropping after a page only renumbers the pages that come later", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 3, target(1), "after"), { parent: "", position: 2, renumber: [{ id: 2, position: 3 }] });
});

check("dropping inside a page with no children makes it the only child", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 3, target(2), "inside"), { parent: 2, position: 1, renumber: [] });
});

check("dropping inside a page with children adds it last without touching the others", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 3, target(1), "inside"), { parent: 1, position: 3, renumber: [] });
});

check("moving a page within its own level leaves it out of the sibling list first", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 1, target(2), "after"), { parent: "", position: 2, renumber: [{ id: 2, position: 1 }] });
});

check("dropping next to a child sends the page to that child's parent", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 3, target(5), "before"), { parent: 1, position: 2, renumber: [{ id: 5, position: 3 }] });
});

check("dropping next to a top level page after being a child sends the page to the top", () => {
  assert.deepStrictEqual(treeMovePlan(FLAT, 4, target(2), "before"), { parent: "", position: 2, renumber: [{ id: 2, position: 3 }, { id: 3, position: 4 }] });
});

check("gaps and repeated positions are closed up into one, two, three", () => {
  const messy = [page(1, null, 5), page(2, null, 5), page(3, null, 9), page(4, null, 1)];
  const plan = treeMovePlan(messy, 4, messy[2], "after");
  assert.strictEqual(plan.position, 4);
  assert.deepStrictEqual(plan.renumber, [{ id: 1, position: 1 }, { id: 2, position: 2 }, { id: 3, position: 3 }]);
});

check("pages with the same position keep a stable order by id", () => {
  const tied = [page(7, null, 1), page(6, null, 1), page(9, null, 2)];
  const plan = treeMovePlan(tied, 9, tied[0], "before");
  assert.strictEqual(plan.position, 2);
  assert.deepStrictEqual(plan.renumber, [{ id: 7, position: 3 }]);
});

check("siblings are ordered by position first, not by id", () => {
  const flat = [page(1, null, 2), page(2, null, 1), page(3, null, 3)];
  assert.deepStrictEqual(treeMovePlan(flat, 3, flat[0], "before"), { parent: "", position: 2, renumber: [{ id: 1, position: 3 }] });
});

check("a page's descendants include itself first and every page below it", () => {
  const tree = [area(1, null), area(2, 1), area(3, 2), area(4, 1), area(5, null)];
  const sorted = (ids) => [...ids].sort((a, b) => a - b);
  assert.strictEqual(descendantsOf(tree, 1)[0], 1);
  assert.deepStrictEqual(sorted(descendantsOf(tree, 1)), [1, 2, 3, 4]);
  assert.deepStrictEqual(sorted(descendantsOf(tree, 2)), [2, 3]);
});

check("an area with nothing below it has only itself", () => {
  assert.deepStrictEqual(descendantsOf([area(1, null), area(2, 1)], 2), [2]);
});

check("a sibling branch is not a descendant", () => {
  assert.deepStrictEqual(descendantsOf([area(1, null), area(2, 1), area(3, 1)], 2), [2]);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
