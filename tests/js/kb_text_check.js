"use strict";

const assert = require("assert");
const path = require("path");
const staticDir = path.join(__dirname, "..", "..", "ledger", "static");
const { ago } = require(path.join(staticDir, "timeago.js"));
const { wikiMap, openWikiQuery, wikiSuggestions } = require(path.join(staticDir, "wikilinks.js"));

const NOW = 1_800_000_000;
const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;
const WEEK = 7 * DAY;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;
const agoBy = (seconds) => ago(NOW - seconds, NOW);
const TITLES = [{ id: 1, title: "Rollback", space: "Runbooks" }, { id: 2, title: "Deploy Steps", space: "Runbooks" }, { id: 3, title: "Rollout plan", space: "Plans" }];
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("no time at all reads as never", () => {
  for (const stamp of [0, null, undefined]) assert.strictEqual(ago(stamp, NOW), "never");
});

check("under a minute and times in the future read as just now", () => {
  assert.strictEqual(agoBy(0), "just now");
  assert.strictEqual(agoBy(59), "just now");
  assert.strictEqual(agoBy(-500), "just now");
});

check("each unit starts exactly at its size and says one in the singular", () => {
  const expected = [[MINUTE, "1 minute ago"], [HOUR, "1 hour ago"], [DAY, "1 day ago"], [WEEK, "1 week ago"], [MONTH, "1 month ago"], [YEAR, "1 year ago"]];
  for (const [seconds, text] of expected) assert.strictEqual(agoBy(seconds), text, String(seconds));
});

check("one second short of a unit stays in the smaller unit", () => {
  const expected = [[HOUR - 1, "59 minutes ago"], [DAY - 1, "23 hours ago"], [WEEK - 1, "6 days ago"], [MONTH - 1, "4 weeks ago"], [YEAR - 1, "12 months ago"]];
  for (const [seconds, text] of expected) assert.strictEqual(agoBy(seconds), text, String(seconds));
});

check("more than one is plural and the count rounds down", () => {
  assert.strictEqual(agoBy(2 * MINUTE + 59), "2 minutes ago");
  assert.strictEqual(agoBy(5 * HOUR), "5 hours ago");
  assert.strictEqual(agoBy(2 * YEAR + 10 * DAY), "2 years ago");
});

check("without a given clock it measures from now", () => {
  assert.strictEqual(ago(Date.now() / 1000 - 2 * HOUR), "2 hours ago");
});

check("a wiki link is matched to a page title ignoring case and surrounding spaces", () => {
  assert.deepStrictEqual(wikiMap("see [[ rollback ]] now", TITLES), { rollback: { id: 1, title: "Rollback" } });
});

check("a link to a page that does not exist maps to null", () => {
  assert.deepStrictEqual(wikiMap("[[Missing page]]", TITLES), { "missing page": null });
});

check("a label after the bar does not change which page is meant", () => {
  assert.deepStrictEqual(wikiMap("[[Deploy Steps|the steps]]", TITLES), { "deploy steps": { id: 2, title: "Deploy Steps" } });
});

check("every link in the text is mapped and repeats collapse", () => {
  const map = wikiMap("[[Rollback]] then [[Rollout plan]] then [[rollback]]", TITLES);
  assert.deepStrictEqual(Object.keys(map).sort(), ["rollback", "rollout plan"]);
});

check("empty, unterminated and multi-line brackets are not links", () => {
  assert.deepStrictEqual(wikiMap("[[]] and [[open and [[a\nb]]", TITLES), {});
});

check("an open link under the caret gives the text typed so far", () => {
  assert.strictEqual(openWikiQuery("see [[Ro"), "Ro");
  assert.strictEqual(openWikiQuery("[["), "");
  assert.strictEqual(openWikiQuery("a [[x]] b [[Dep"), "Dep");
});

check("a closed link, a label, a new line or no brackets give no query", () => {
  for (const text of ["see [[Rollback]] and", "[[Rollback|la", "[[Roll\nback", "plain text", "[ [x"]) assert.strictEqual(openWikiQuery(text), null, JSON.stringify(text));
});

check("suggestions match anywhere in the title ignoring case, in the given order", () => {
  assert.deepStrictEqual(wikiSuggestions(TITLES, "ROLL").map((t) => t.id), [1, 3]);
  assert.deepStrictEqual(wikiSuggestions(TITLES, "steps").map((t) => t.id), [2]);
  assert.deepStrictEqual(wikiSuggestions(TITLES, "zzz"), []);
});

check("an empty query offers the first seven pages and no more", () => {
  const many = Array.from({ length: 12 }, (_, i) => ({ id: i, title: `Page ${i}` }));
  assert.deepStrictEqual(wikiSuggestions(many, "").map((t) => t.id), [0, 1, 2, 3, 4, 5, 6]);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
