"use strict";

const assert = require("assert");
const path = require("path");
const { queuePerson, queueFromResponse, queueReasonsHtml, queueButtonView, updateQueueButton } = require(path.join(__dirname, "..", "..", "ledger", "static", "queue.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);
const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

check("the count is the number of tickets returned", () => {
  assert.deepStrictEqual(queueFromResponse({ person: "ann", count: 99, tickets: [{ key: "A-1" }, { key: "A-2" }] }).count, 2);
});

check("a failed or empty response gives an empty queue", () => {
  assert.deepStrictEqual(queueFromResponse(null), { count: 0, tickets: [] });
  assert.deepStrictEqual(queueFromResponse({}), { count: 0, tickets: [] });
});

check("each reason becomes a readable chip and unknown reasons are dropped", () => {
  const html = queueReasonsHtml(["assigned", "review", "question", "other"], escapeHtml);
  assert.ok(html.includes(">assigned<") && html.includes(">in review<") && html.includes(">open question<"));
  assert.strictEqual((html.match(/<span/g) || []).length, 3);
  assert.strictEqual(queueReasonsHtml(undefined, escapeHtml), "");
});

check("the button shows the count and goes quiet at zero", () => {
  assert.strictEqual(queueButtonView(3).text, "My queue 3");
  assert.strictEqual(queueButtonView(3).quiet, false);
  assert.strictEqual(queueButtonView(0).quiet, true);
  assert.strictEqual(queueButtonView(1).title, "1 ticket assigned to you");
  assert.strictEqual(queueButtonView(0).title, "Nothing assigned to you");
});

check("the queue person is the lowercased profile name", () => {
  assert.strictEqual(queuePerson(" Ann "), "ann");
  assert.strictEqual(queuePerson(""), "");
});

check("updating the button writes its text, title and quiet class", () => {
  const classes = new Set();
  const button = { textContent: "", title: "", classList: { toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)) } };
  updateQueueButton(button, 0);
  assert.strictEqual(button.textContent, "My queue 0");
  assert.ok(classes.has("quiet"));
  updateQueueButton(button, 4);
  assert.strictEqual(button.textContent, "My queue 4");
  assert.ok(!classes.has("quiet"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} queue view checks passed`);
process.exit(failed ? 1 : 0);
