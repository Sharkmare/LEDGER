"use strict";

const path = require("path");
const { renderMarkdown } = require(path.join(__dirname, "..", "..", "ledger", "static", "markdown.js"));

const SECTIONS = Number(process.argv[2] || 400);
const context = { ticket: (key) => key.startsWith("APP-"), wiki: { rollback: { id: 1, title: "Rollback" } } };
const block = [
  "## Section heading with `code` and **bold**",
  "",
  "A paragraph with *emphasis*, a [link](https://example.com), APP-12, [[Rollback]] and ~~strikethrough~~. More words follow here to give the line some length.",
  "",
  "- first item with `inline code`",
  "- second item",
  "  - nested item with **bold**",
  "- [x] a finished task",
  "",
  "| Name | Meaning |",
  "|---|---|",
  "| alpha | first |",
  "| beta | second |",
  "",
  "```js",
  "const value = compute(1, 2, 3);",
  "```",
  "",
  "> [!NOTE]",
  "> A callout with a sentence in it.",
  "",
].join("\n");
const text = Array.from({ length: SECTIONS }, () => block).join("\n");
const started = process.hrtime.bigint();
const result = renderMarkdown(text, context);
const milliseconds = Number(process.hrtime.bigint() - started) / 1e6;
console.log(JSON.stringify({ lines: text.split("\n").length, characters: text.length, headings: result.headings.length, milliseconds }));
