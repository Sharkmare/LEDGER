"use strict";

const assert = require("assert");
const path = require("path");
const { renderMarkdown, mdSafeUrl } = require(path.join(__dirname, "..", "..", "ledger", "static", "markdown.js"));

const context = { ticket: (key) => key.startsWith("APP-"), wiki: { rollback: { id: 7, title: "Rollback" } } };
const html = (text) => renderMarkdown(text, context).html;
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("text is escaped, never passed through as markup", () => {
  for (const hostile of ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "**<b onmouseover=1>**", "[[<i>]]", "`<u>`", "# <h1 onclick=1>"]) {
    const out = html(hostile);
    assert(!/<script|<img src=x|<b onmouse|<i>|<u>|<h1 onclick/.test(out), `unescaped markup from ${hostile}: ${out}`);
  }
});

check("script style links and data images are refused", () => {
  assert(html("[x](javascript:alert(1))").includes('href="#"'));
  assert(!html("![i](data:image/png;base64,AAAA)").includes("<img"));
  assert(!html("[v](vbscript:x)").includes("vbscript:x\""));
  assert.strictEqual(mdSafeUrl("JavaScript:alert(1)"), "#");
  assert.strictEqual(mdSafeUrl("https://example.com/a"), "https://example.com/a");
  assert.strictEqual(mdSafeUrl("#section"), "#section");
  assert.strictEqual(mdSafeUrl("../other"), "../other");
});

check("external links open safely and images load lazily", () => {
  assert(html("[a](https://example.com)").includes('target="_blank" rel="noopener noreferrer"'));
  assert(html("![alt](https://example.com/a.png)").includes('loading="lazy"'));
  assert(!html("[a](#local)").includes("_blank"));
});

check("wiki links resolve or offer to create the page", () => {
  assert(html("[[Rollback]]").includes('data-kb-page="7"'));
  assert(html("[[rollback|go back]]").includes(">go back</a>"));
  const missing = html("[[Nowhere]]");
  assert(missing.includes("missing") && missing.includes('data-kb-create="Nowhere"'));
});

check("only real project keys become ticket links", () => {
  const out = html("APP-12 and ZZZ-5 and UTF-8");
  assert(out.includes('data-ticket="APP-12"'));
  assert(!out.includes('data-ticket="ZZZ-5"') && !out.includes('data-ticket="UTF-8"'));
});

check("tables keep alignment and escaped pipes", () => {
  const out = html("| a | b |\n|---|:-:|\n| 1 | 2 |\n| x \\| y | 4 |");
  assert(out.includes("<th>a</th>") && out.includes('<th style="text-align:center">b</th>'));
  assert(out.includes("<td>x | y</td>"));
  assert.strictEqual((out.match(/<tr>/g) || []).length, 3);
});

check("nested lists, ordered lists and tasks", () => {
  const out = html("- one\n- two\n  - nested\n    - deeper\n- [x] done\n- [ ] todo\n\n3. third\n4. fourth");
  assert.strictEqual((out.match(/<ul>/g) || []).length, 3);
  assert(out.includes('<ol start="3">'));
  assert(out.includes("checkbox\" disabled checked") && out.includes('checkbox" disabled>'));
});

check("callouts, quotes and rules", () => {
  assert(html("> [!WARNING]\n> Careful").includes("callout callout-warning"));
  assert(html("> [!note]\n> Hi").includes("callout-note"));
  assert(html("> plain\n> quote").includes("<blockquote>"));
  assert(html("above\n\n---\n\nbelow").includes("<hr>"));
});

check("code blocks keep their text and escape it", () => {
  const out = html("```js\nconst a = '<script>';\n```\n\n~~~\nplain\n~~~");
  assert(out.includes("&lt;script&gt;") && out.includes('data-lang="js"'));
  assert.strictEqual((out.match(/<pre>/g) || []).length, 2);
});

check("inline formatting nests and snake_case stays as written", () => {
  assert(html("**bold with `code`**").includes("<strong>bold with <code>code</code></strong>"));
  assert(html("**bold *and em***").includes("<strong>"));
  assert(html("a snake_case_name here").includes("snake_case_name") && !html("a snake_case_name here").includes("<em>"));
  assert(html("`` a`b ``").includes("<code>a`b</code>"));
  assert(html("~~gone~~").includes("<del>gone</del>"));
  assert(html("one\ntwo").includes("one<br>two"));
});

check("headings get unique anchors and are reported", () => {
  const result = renderMarkdown("# Setup\n\n## Setup\n\n## Other `code`\n", context);
  assert.deepStrictEqual(result.headings.map((h) => h.id), ["setup", "setup-1", "other-code"]);
  assert.deepStrictEqual(result.headings.map((h) => h.level), [1, 2, 2]);
  assert(result.html.includes('id="setup-1"'));
});

check("empty and odd input never throws", () => {
  for (const text of ["", "   ", "\n\n", "|", "| a |", "- ", "> ", "```", "[", "[[", "![", "**", "_", "#", "1.", "\u0000"]) assert.strictEqual(typeof html(text), "string");
  assert.strictEqual(html(null), "");
});

let failed = 0;
for (const [name, body] of checks) {
  try {
    body();
    console.log(`ok   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
