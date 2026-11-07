"use strict";

const assert = require("assert");
const path = require("path");
const { SIMILAR_DEBOUNCE_MS, shouldCheckSimilar, similarRequestPath, isCurrentSimilarAnswer, similarEntryText, renderSimilarHtml, debounced } = require(path.join(__dirname, "..", "..", "ledger", "static", "similar.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);
const escape = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

check("a check needs a project and at least eight characters of title", () => {
  assert.strictEqual(shouldCheckSimilar("APP", "1234567"), false);
  assert.strictEqual(shouldCheckSimilar("APP", "12345678"), true);
  assert.strictEqual(shouldCheckSimilar("", "a long enough title"), false);
  assert.strictEqual(shouldCheckSimilar("APP", "   short   "), false);
  assert.strictEqual(shouldCheckSimilar("APP", undefined), false);
});

check("the request path encodes the title and carries the limit", () => {
  assert.strictEqual(similarRequestPath("APP", " Fix & go #1 "), "/api/tickets/similar?project=APP&title=Fix+%26+go+%231&limit=3");
  assert.strictEqual(similarRequestPath("APP", "title here", 5), "/api/tickets/similar?project=APP&title=title+here&limit=5");
});

check("an answer is current only for the same project and title", () => {
  assert.strictEqual(isCurrentSimilarAnswer({ project: "APP", title: "abc " }, { project: "APP", title: "abc" }), true);
  assert.strictEqual(isCurrentSimilarAnswer({ project: "APP", title: "abc" }, { project: "APP", title: "abcd" }), false);
  assert.strictEqual(isCurrentSimilarAnswer({ project: "APP", title: "abc" }, { project: "OTH", title: "abc" }), false);
});

check("no matches render nothing so the list stays hidden", () => {
  assert.strictEqual(renderSimilarHtml([], escape), "");
  assert.strictEqual(renderSimilarHtml(undefined, escape), "");
});

check("matches render key, title and status, each linking to the ticket, with text escaped", () => {
  const html = renderSimilarHtml([{ key: "APP-3", title: "Fix <b>login</b>", status: "in_progress", score: 0.9 }], escape);
  assert.ok(html.includes('href="/#APP-3"'));
  assert.ok(html.includes("APP-3"));
  assert.ok(html.includes("Fix &lt;b&gt;login&lt;/b&gt;"));
  assert.ok(html.includes("in progress"));
  assert.ok(!html.includes("<b>login"));
  assert.ok(html.includes("Similar open tickets"));
});

check("the entry text names key, title and status", () => {
  assert.strictEqual(similarEntryText({ key: "APP-3", title: "Fix login", status: "in_review" }), "APP-3 Fix login (in review)");
});

check("the debounce waits for quiet and then runs once with the last values", () => {
  const scheduled = [];
  let nextId = 1;
  const timers = {
    set: (callback, delay) => { scheduled.push({ id: nextId, callback, delay, live: true }); return nextId++; },
    clear: (id) => { scheduled.find((entry) => entry.id === id).live = false; },
  };
  const fire = () => scheduled.filter((entry) => entry.live).forEach((entry) => { entry.live = false; entry.callback(); });
  const calls = [];
  const run = debounced((value) => calls.push(value), SIMILAR_DEBOUNCE_MS, timers);
  run("a");
  run("b");
  run("c");
  assert.deepStrictEqual(scheduled.map((entry) => [entry.live, entry.delay]), [[false, 300], [false, 300], [true, 300]]);
  fire();
  assert.deepStrictEqual(calls, ["c"]);
  run("d");
  fire();
  assert.deepStrictEqual(calls, ["c", "d"]);
});

check("the default timers are plain functions, so they work when called as methods of another object", () => {
  const original = global.setTimeout;
  global.setTimeout = function (callback, wait) { if (this !== undefined && this !== global) throw new TypeError("Illegal invocation"); return original(callback, wait); };
  try {
    const run = debounced(() => {}, 1);
    run();
  } finally { global.setTimeout = original; }
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} similar ticket checks passed`);
process.exit(failed ? 1 : 0);
