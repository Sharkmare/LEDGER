"use strict";

const assert = require("assert");
const path = require("path");
const { wipCountHtml } = require(path.join(__dirname, "..", "..", "ledger", "static", "wip.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);
const wip = { limits: { in_progress: 3 }, counts: { in_progress: 2, blocked: 9, in_review: 4 } };

check("a status without a limit shows the plain shown count", () => {
  assert.strictEqual(wipCountHtml(5, "blocked", wip), '<span class="count">5</span>');
  assert.strictEqual(wipCountHtml(5, "blocked", null), '<span class="count">5</span>');
});

check("a limited status shows count / limit without a warning while within it", () => {
  const html = wipCountHtml(1, "in_progress", wip);
  assert.ok(html.includes("2 / 3"));
  assert.ok(!html.includes("wip-over"));
});

check("the limit itself is not over, one more is", () => {
  assert.ok(!wipCountHtml(0, "in_progress", { limits: { in_progress: 3 }, counts: { in_progress: 3 } }).includes("wip-over"));
  const html = wipCountHtml(0, "in_progress", { limits: { in_progress: 3 }, counts: { in_progress: 4 } });
  assert.ok(html.includes("wip-over") && html.includes("4 / 3") && html.includes("over the limit of 3"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n" + error.message); }
}
console.log(failed ? `${failed} failed` : `${checks.length} passed`);
process.exit(failed ? 1 : 0);
