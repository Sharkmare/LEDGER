"use strict";

const assert = require("assert");
const path = require("path");
const { dependenciesHtml } = require(path.join(__dirname, "..", "..", "ledger", "static", "dependencies.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);
const helpers = {
  escapeHtml: (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
  statusColor: () => "#888",
  statusLabel: (status) => status.toUpperCase(),
};

check("nothing to show gives no section at all", () => {
  assert.strictEqual(dependenciesHtml(null, helpers), "");
  assert.strictEqual(dependenciesHtml({ blocked_by: [], blocks: [], open_blockers: 0 }, helpers), "");
});

check("blockers and blocked tickets are links, indented by depth, with status pills", () => {
  const html = dependenciesHtml({
    blocked_by: [{ key: "A-1", title: "first", status: "todo", depth: 1 }, { key: "A-0", title: "root", status: "done", depth: 2 }],
    blocks: [{ key: "A-9", title: "<b>later</b>", status: "backlog", depth: 1 }], open_blockers: 1,
  }, helpers);
  assert.ok(html.includes("<h4>Dependencies</h4>") && html.includes("Blocked by") && html.includes("Blocks"));
  assert.ok(html.includes('data-open="A-1"') && html.includes('data-open="A-0"') && html.includes('data-open="A-9"'));
  assert.ok(html.includes("padding-left:8px") && html.includes("padding-left:24px"));
  assert.ok(html.includes(">TODO<") && html.includes("&lt;b&gt;later"));
  assert.ok(html.includes("1 open blocker,"));
});

check("an epic shows its critical path joined with arrows even without other links", () => {
  const html = dependenciesHtml({ blocked_by: [], blocks: [], open_blockers: 0, critical_path: ["A-2", "A-3", "A-4"] }, helpers);
  assert.ok(html.includes("Critical path"));
  assert.ok(html.replace(/<[^>]+>/g, "").includes("A-2 -&gt; A-3 -&gt; A-4"));
  assert.ok(!html.includes("Blocked by"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n" + error.message); }
}
console.log(failed ? `${failed} failed` : `${checks.length} passed`);
process.exit(failed ? 1 : 0);
