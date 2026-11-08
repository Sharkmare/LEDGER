"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const staticDir = path.join(__dirname, "..", "..", "ledger", "static");
const { escapeHtml } = require(path.join(staticDir, "escape.js"));
const { renderMarkdown } = require(path.join(staticDir, "markdown.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

check("the five markup characters are replaced", () => {
  assert.strictEqual(escapeHtml(`<a href="x" title='y'>&</a>`), "&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
});

check("an ampersand is escaped once, never into an entity of another escape", () => {
  assert.strictEqual(escapeHtml("&lt;"), "&amp;lt;");
  assert.strictEqual(escapeHtml("<&>"), "&lt;&amp;&gt;");
});

check("nothing, null and numbers become safe text", () => {
  assert.strictEqual(escapeHtml(undefined), "");
  assert.strictEqual(escapeHtml(null), "");
  assert.strictEqual(escapeHtml(0), "0");
  assert.strictEqual(escapeHtml(false), "false");
});

check("plain text and other punctuation pass through untouched", () => {
  assert.strictEqual(escapeHtml("Fix list limit parsing (#12), 100% sure; a/b `c`"), "Fix list limit parsing (#12), 100% sure; a/b `c`");
});

check("the escaped text is safe inside an attribute and inside an element", () => {
  const hostile = `"><img src=x onerror=alert(1)>`;
  const escaped = escapeHtml(hostile);
  assert.ok(!/[<>"']/.test(escaped), escaped);
});

check("the markdown renderer escapes with the same function", () => {
  const hostile = `<b onmouseover="x">&'`;
  assert.ok(renderMarkdown(hostile, {}).html.includes(escapeHtml(hostile)));
});

check("no other script carries its own copy of the escape table", () => {
  const copies = fs.readdirSync(staticDir).filter((name) => name.endsWith(".js") && name !== "escape.js")
    .filter((name) => /"&": "&amp;"|&amp;.*&lt;.*&gt;.*&quot;/.test(fs.readFileSync(path.join(staticDir, name), "utf8")));
  assert.deepStrictEqual(copies, []);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
