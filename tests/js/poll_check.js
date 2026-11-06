"use strict";

const assert = require("assert");
const path = require("path");
const { pollBlocker, createChangeTracker } = require(path.join(__dirname, "..", "..", "ledger", "static", "poll.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

const idle = { hidden: false, typing: false, dialogOpen: false, editing: false, dragging: false, selecting: false };

check("an idle page lets the refresh run", () => {
  assert.strictEqual(pollBlocker(idle), null);
});

check("each busy state blocks the refresh and names itself", () => {
  for (const name of Object.keys(idle)) assert.strictEqual(pollBlocker({ ...idle, [name]: true }), name);
});

check("a drag or a text selection blocks the refresh", () => {
  assert.strictEqual(pollBlocker({ ...idle, dragging: true }), "dragging");
  assert.strictEqual(pollBlocker({ ...idle, selecting: true }), "selecting");
});

check("the first reading counts as a change, an identical one does not", () => {
  const tracker = createChangeTracker();
  assert.strictEqual(tracker.changed("page", { a: [1, 2] }), true);
  assert.strictEqual(tracker.changed("page", { a: [1, 2] }), false);
});

check("any difference in the data counts as a change and is then remembered", () => {
  const tracker = createChangeTracker();
  tracker.changed("page", { a: [1, 2] });
  assert.strictEqual(tracker.changed("page", { a: [1, 3] }), true);
  assert.strictEqual(tracker.changed("page", { a: [1, 3] }), false);
});

check("names are tracked separately", () => {
  const tracker = createChangeTracker();
  tracker.changed("page", 1);
  assert.strictEqual(tracker.changed("drawer", 1), true);
  assert.strictEqual(tracker.changed("page", 1), false);
});

check("forgetting a name makes its next reading a change", () => {
  const tracker = createChangeTracker();
  tracker.changed("page", 1);
  tracker.forget("page");
  assert.strictEqual(tracker.changed("page", 1), true);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} refresh checks passed`);
process.exit(failed ? 1 : 0);
