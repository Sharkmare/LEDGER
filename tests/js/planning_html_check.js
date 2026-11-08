"use strict";

const assert = require("assert");
const path = require("path");
const { ruleChips, progressBar } = require(path.join(__dirname, "..", "..", "ledger", "static", "planninghtml.js"));

const colorOf = (label) => `color-of-${label}`;
const chips = (rules) => [...ruleChips(rules, colorOf).matchAll(/<span class="chip(?: tint" style="--tint:[^"]*)?">([^<]*)<\/span>/g)].map((m) => m[1]);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("a board with no rules says it shows everything in the area", () => {
  assert.strictEqual(ruleChips({}, colorOf), '<span class="muted">Everything in the area</span>');
});

check("each rule becomes a chip in a fixed order", () => {
  const rules = { scope: "all", project: "LED", types: ["bug", "task"], priorities: ["high"], labels: ["ui"], assignee: "azazel", parent: "LED-1", iteration: "Sprint 3" };
  assert.deepStrictEqual(chips(rules), ["any area", "project LED", "types bug, task", "priority high", "ui", "@azazel", "under LED-1", "iteration Sprint 3"]);
});

check("only the scope all rule shows the any area chip", () => {
  assert.deepStrictEqual(chips({ scope: "area", project: "LED" }), ["project LED"]);
});

check("every tag gets a chip tinted by the colour function", () => {
  const html = ruleChips({ labels: ["ui", "tests"] }, colorOf);
  assert.ok(html.includes('style="--tint:color-of-ui">ui</span>'));
  assert.ok(html.includes('style="--tint:color-of-tests">tests</span>'));
});

check("rule values are escaped", () => {
  const html = ruleChips({ project: "<b>", types: ["<i>"], labels: ["<u>"], assignee: "<s>", parent: "<p>", iteration: "<q>" }, () => "red");
  for (const tag of ["<b>", "<i>", "<u>", "<s>", "<p>", "<q>"]) assert.ok(!html.includes(tag), tag);
});

const percentOf = (html) => ({ now: Number(html.match(/aria-valuenow="(\d+)"/)[1]), width: Number(html.match(/width:(\d+)%/)[1]) });

check("progress is the share done, rounded, and the bar is as wide as the number says", () => {
  assert.deepStrictEqual(percentOf(progressBar(1, 3)), { now: 33, width: 33 });
  assert.deepStrictEqual(percentOf(progressBar(2, 3)), { now: 67, width: 67 });
  assert.deepStrictEqual(percentOf(progressBar(4, 4)), { now: 100, width: 100 });
});

check("nothing to do is zero percent instead of an error", () => {
  assert.deepStrictEqual(percentOf(progressBar(0, 0)), { now: 0, width: 0 });
  assert.deepStrictEqual(percentOf(progressBar(5, 0)), { now: 0, width: 0 });
});

check("the bar is announced as a progress bar from zero to one hundred", () => {
  const html = progressBar(1, 2);
  assert.ok(html.includes('role="progressbar"') && html.includes('aria-valuemin="0"') && html.includes('aria-valuemax="100"'));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
