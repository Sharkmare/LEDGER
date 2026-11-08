"use strict";

const assert = require("assert");
const path = require("path");
const { kbLevelUrl, snippetHtml, reviewBadge, tocHtml, recentsWith } = require(path.join(__dirname, "..", "..", "ledger", "static", "kbpages.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

check("the address for a level lists the children of a page, or of the space itself for the root", () => {
  assert.strictEqual(kbLevelUrl(3, "root", 0, 200), "/api/kb/spaces/3/children?parent=&offset=0&limit=200");
  assert.strictEqual(kbLevelUrl(3, "41", 200, 50), "/api/kb/spaces/3/children?parent=41&offset=200&limit=50");
});

check("search markers become highlights", () => {
  assert.strictEqual(snippetHtml("a \u0001hit\u0002 here"), "a <mark>hit</mark> here");
  assert.strictEqual(snippetHtml("\u0001a\u0002 and \u0001b\u0002"), "<mark>a</mark> and <mark>b</mark>");
});

check("everything else in a snippet is escaped, including markup that looks like a highlight", () => {
  assert.strictEqual(snippetHtml("<b>x</b> <mark>"), "&lt;b&gt;x&lt;/b&gt; &lt;mark&gt;");
  assert.strictEqual(snippetHtml("\u0001<img src=x>\u0002"), "<mark>&lt;img src=x&gt;</mark>");
});

check("a missing snippet is empty", () => {
  assert.strictEqual(snippetHtml(undefined), "");
  assert.strictEqual(snippetHtml(""), "");
});

const NOW_SECONDS = Date.now() / 1000;

check("a verified page says who verified it and how long ago, with the next review date", () => {
  const html = reviewBadge({ verified_by: "azazel", verified_at: NOW_SECONDS - 7200, review_by: "2027-01-01", stale: false });
  assert.ok(html.includes("verified by azazel 2 hours ago"));
  assert.ok(html.includes('title="Next review 2027-01-01"'));
});

check("a stale page says its review was due, even when someone once verified it", () => {
  const html = reviewBadge({ verified_by: "azazel", verified_at: NOW_SECONDS, review_by: "2026-01-01", stale: true });
  assert.ok(html.includes("review was due 2026-01-01"));
  assert.ok(!html.includes("verified by"));
});

check("a page with only a review date shows when it is due", () => {
  assert.ok(reviewBadge({ review_by: "2027-02-02" }).includes("review by 2027-02-02"));
});

check("a page with no review information shows nothing", () => {
  assert.strictEqual(reviewBadge({}), "");
});

check("names and dates in the badge are escaped", () => {
  const verified = reviewBadge({ verified_by: "<i>x</i>", verified_at: NOW_SECONDS, review_by: "<b>", stale: false });
  const stale = reviewBadge({ review_by: "<b>", stale: true });
  const plain = reviewBadge({ review_by: "<b>" });
  for (const html of [verified, stale, plain]) assert.ok(!html.includes("<i>") && !html.includes("<b>"), html);
});

const heading = (level, text, id = text.toLowerCase()) => ({ level, text, id });

check("a contents list needs at least two headings", () => {
  assert.strictEqual(tocHtml([]), "");
  assert.strictEqual(tocHtml([heading(1, "One")]), "");
});

check("headings below level three are left out, so one level three heading plus one deep one is not enough", () => {
  assert.strictEqual(tocHtml([heading(2, "A"), heading(4, "Deep")]), "");
  const html = tocHtml([heading(2, "A"), heading(3, "B"), heading(4, "Deep")]);
  assert.ok(html.includes(">A<") && html.includes(">B<") && !html.includes("Deep"));
});

check("each heading links to its anchor and is indented by its level", () => {
  const html = tocHtml([heading(1, "Top"), heading(2, "Mid"), heading(3, "Low")]);
  assert.ok(html.includes('padding-left:0px"><a href="#top" data-toc="top">Top</a>'));
  assert.ok(html.includes('padding-left:12px"><a href="#mid"'));
  assert.ok(html.includes('padding-left:24px"><a href="#low"'));
});

check("heading text is escaped", () => {
  assert.ok(!tocHtml([heading(1, "<b>a</b>", "a"), heading(2, "b")]).includes("<b>"));
});

check("a new recent page goes first and an older copy of it is dropped", () => {
  const recents = [{ kind: "page", id: 1, title: "A" }, { kind: "page", id: 2, title: "B" }];
  assert.deepStrictEqual(recentsWith(recents, { kind: "page", id: 2, title: "B2" }, 8).map((r) => r.title), ["B2", "A"]);
});

check("the same number as a different kind is a different recent entry", () => {
  const recents = [{ kind: "tool", id: 2, title: "T" }];
  assert.strictEqual(recentsWith(recents, { kind: "page", id: 2, title: "P" }, 8).length, 2);
});

check("only the newest entries up to the limit are kept and the old list is left alone", () => {
  const recents = Array.from({ length: 8 }, (_, i) => ({ kind: "page", id: i, title: String(i) }));
  const next = recentsWith(recents, { kind: "page", id: 99, title: "new" }, 8);
  assert.strictEqual(next.length, 8);
  assert.strictEqual(next[0].id, 99);
  assert.strictEqual(next[7].id, 6);
  assert.strictEqual(recents.length, 8);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
