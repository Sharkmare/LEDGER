"use strict";

const assert = require("assert");
const path = require("path");
const { listContinuation, formatEdit } = require(path.join(__dirname, "..", "..", "ledger", "static", "editorformat.js"));

const splice = (value, edit) => value.slice(0, edit.from) + edit.text + value.slice(edit.to);
const selectedAfter = (value, edit) => splice(value, edit).slice(edit.caretStart, edit.caretEnd);
const atEnd = (value) => listContinuation(value, value.length, value.length);
const format = (value, start, end, kind) => formatEdit(value, start, end, kind);
const formatAll = (value, kind) => format(value, 0, value.length, kind);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("enter after a bullet starts the next bullet with the same marker", () => {
  for (const marker of ["-", "*", "+"]) assert.strictEqual(splice(`${marker} item`, atEnd(`${marker} item`)), `${marker} item\n${marker} `);
});

check("enter after a numbered item counts on", () => {
  assert.strictEqual(splice("1. a", atEnd("1. a")), "1. a\n2. ");
  assert.strictEqual(splice("9. a", atEnd("9. a")), "9. a\n10. ");
});

check("enter after a checked task starts an unchecked one", () => {
  assert.strictEqual(splice("- [x] done", atEnd("- [x] done")), "- [x] done\n- [ ] ");
  assert.strictEqual(splice("- [ ] todo", atEnd("- [ ] todo")), "- [ ] todo\n- [ ] ");
});

check("enter keeps the indentation of a nested item", () => {
  assert.strictEqual(splice("  - nested", atEnd("  - nested")), "  - nested\n  - ");
});

check("enter on an empty item removes the marker and leaves a blank line", () => {
  for (const [value, expected] of [["a\n- ", "a\n\n"], ["a\n1. ", "a\n\n"], ["a\n- [ ] ", "a\n\n"], ["  - ", "\n"]]) assert.strictEqual(splice(value, atEnd(value)), expected, JSON.stringify(value));
});

check("enter in the middle of an item carries the rest of the line to the new item", () => {
  const value = "- item here";
  assert.strictEqual(splice(value, listContinuation(value, 6, 6)), "- item\n-  here");
});

check("enter does nothing special outside a list or with a selection", () => {
  assert.strictEqual(atEnd("hello"), null);
  assert.strictEqual(atEnd("-no space"), null);
  assert.strictEqual(atEnd(""), null);
  assert.strictEqual(listContinuation("- item more", 6, 11), null);
});

check("only the line holding the caret counts", () => {
  assert.strictEqual(atEnd("- a\nplain"), null);
  assert.strictEqual(splice("- a\nplain", listContinuation("- a\nplain", 3, 3)), "- a\n- \nplain");
});

check("bold, italic and code wrap the selection and keep it selected", () => {
  for (const [kind, mark] of [["bold", "**"], ["italic", "*"], ["code", "`"]]) {
    const edit = format("hello world", 6, 11, kind);
    assert.strictEqual(splice("hello world", edit), `hello ${mark}world${mark}`);
    assert.strictEqual(selectedAfter("hello world", edit), "world");
  }
});

check("wrapping with nothing selected inserts a placeholder and selects it", () => {
  const edit = format("", 0, 0, "bold");
  assert.strictEqual(splice("", edit), "**bold text**");
  assert.strictEqual(selectedAfter("", edit), "bold text");
});

check("heading, list, task and quote prefix every selected line from the start of the first", () => {
  assert.strictEqual(splice("a\nb", formatAll("a\nb", "ul")), "- a\n- b");
  assert.strictEqual(splice("a\nb", formatAll("a\nb", "task")), "- [ ] a\n- [ ] b");
  assert.strictEqual(splice("a\nb", formatAll("a\nb", "quote")), "> a\n> b");
  assert.strictEqual(splice("a\nb", formatAll("a\nb", "h3")), "### a\n### b");
});

check("numbered lists count from one down the selection", () => {
  assert.strictEqual(splice("a\nb\nc", formatAll("a\nb\nc", "ol")), "1. a\n2. b\n3. c");
});

check("a prefix replaces the mark a line already has instead of stacking", () => {
  assert.strictEqual(splice("# Title", formatAll("# Title", "h2")), "## Title");
  assert.strictEqual(splice("1. a\n2. b", formatAll("1. a\n2. b", "ul")), "- a\n- b");
  assert.strictEqual(splice("- [x] a", formatAll("- [x] a", "quote")), "> a");
});

check("a prefix starts at the beginning of the line even when the selection starts inside it", () => {
  const value = "first\nsecond line";
  assert.strictEqual(splice(value, format(value, 9, 12, "ul")), "first\n- second line");
});

check("a link around selected text puts the caret on the address", () => {
  const edit = format("see docs", 4, 8, "link");
  assert.strictEqual(splice("see docs", edit), "see [docs](https://)");
  assert.strictEqual(selectedAfter("see docs", edit), "https://");
});

check("a link around a selected address puts the caret on the link text", () => {
  const edit = format("https://example.com", 0, 19, "link");
  assert.strictEqual(splice("https://example.com", edit), "[link text](https://example.com)");
  assert.strictEqual(selectedAfter("https://example.com", edit), "link text");
});

check("a link with nothing selected inserts a template", () => {
  assert.strictEqual(splice("", format("", 0, 0, "link")), "[link text](https://)");
});

check("table, fence and callout insert their blocks and place the caret", () => {
  assert.strictEqual(splice("", format("", 0, 0, "table")), "\n| Column | Column |\n|---|---|\n|  |  |\n");
  assert.strictEqual(splice("code", formatAll("code", "fence")), "\n```\ncode\n```\n");
  assert.strictEqual(splice("", format("", 0, 0, "callout")), "\n> [!NOTE]\n> Something worth noticing.");
  assert.strictEqual(format("", 0, 0, "table").caretStart, 3);
  assert.strictEqual(format("", 0, 0, "fence").caretStart, 5);
  assert.strictEqual(format("", 0, 0, "callout").caretStart, 12);
});

check("a wiki link wraps the selection or a placeholder title", () => {
  const edit = format("go to Home", 6, 10, "wiki");
  assert.strictEqual(splice("go to Home", edit), "go to [[Home]]");
  assert.strictEqual(selectedAfter("go to Home", edit), "Home");
  assert.strictEqual(splice("", format("", 0, 0, "wiki")), "[[Page title]]");
});

check("an unknown format does nothing", () => {
  assert.strictEqual(format("x", 0, 1, "nonsense"), null);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
