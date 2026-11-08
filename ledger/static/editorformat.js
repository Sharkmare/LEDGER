"use strict";

const LIST_LINE = /^(\s*)([-*+]|\d+\.)\s(\[[ x]\]\s)?/;
const HEADING_OR_LIST_MARK = /^(#{1,6}\s+|[-*+]\s+(\[[ x]\]\s+)?|\d+\.\s+|>\s?)/;

function lineStartOf(value, position) { return value.lastIndexOf("\n", position - 1) + 1; }

function listContinuation(value, start, end) {
  const lineStart = lineStartOf(value, start);
  const line = value.slice(lineStart, start);
  const match = line.match(LIST_LINE);
  if (!match || start !== end) return null;
  if (line.trim() === match[0].trim()) return { from: lineStart, to: start, text: "\n" };
  const marker = /\d/.test(match[2]) ? `${parseInt(match[2], 10) + 1}.` : match[2];
  return { from: start, to: start, text: `\n${match[1]}${marker} ${match[3] ? "[ ] " : ""}` };
}

function formatEdit(value, start, end, kind) {
  const selected = value.slice(start, end);
  const lineStart = lineStartOf(value, start);
  const replace = (from, to, text, caretStart, caretEnd) => ({ from, to, text, caretStart, caretEnd });
  const wrap = (mark, placeholder) => {
    const text = selected || placeholder;
    return replace(start, end, `${mark}${text}${mark}`, start + mark.length, start + mark.length + text.length);
  };
  const prefix = (mark) => {
    const lines = value.slice(lineStart, end).split("\n");
    const out = lines.map((line, i) => (mark === "1. " ? `${i + 1}. ` : mark) + line.replace(HEADING_OR_LIST_MARK, "")).join("\n");
    return replace(lineStart, end, out, lineStart, lineStart + out.length);
  };
  const insert = (text, caret) => replace(start, end, text, start + caret, start + caret);
  if (kind === "bold") return wrap("**", "bold text");
  if (kind === "italic") return wrap("*", "italic text");
  if (kind === "code") return wrap("`", "code");
  if (kind === "h2") return prefix("## ");
  if (kind === "h3") return prefix("### ");
  if (kind === "ul") return prefix("- ");
  if (kind === "ol") return prefix("1. ");
  if (kind === "task") return prefix("- [ ] ");
  if (kind === "quote") return prefix("> ");
  if (kind === "link") {
    const isUrl = /^https?:\/\//.test(selected);
    const text = isUrl ? "link text" : selected || "link text";
    const url = isUrl ? selected : "https://";
    return replace(start, end, `[${text}](${url})`, isUrl ? start + 1 : start + text.length + 3, isUrl ? start + 1 + text.length : start + text.length + 3 + url.length);
  }
  if (kind === "table") return insert("\n| Column | Column |\n|---|---|\n|  |  |\n", 3);
  if (kind === "fence") return insert("\n```\n" + selected + "\n```\n", 5);
  if (kind === "callout") return insert("\n> [!NOTE]\n> " + (selected || "Something worth noticing."), 12);
  if (kind === "wiki") {
    const text = selected || "Page title";
    return replace(start, end, `[[${text}]]`, start + 2, start + 2 + text.length);
  }
  return null;
}

if (typeof module !== "undefined") module.exports = { listContinuation, formatEdit };
