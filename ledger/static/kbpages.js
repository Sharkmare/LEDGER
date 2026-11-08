"use strict";

if (typeof escapeHtml === "undefined") globalThis.escapeHtml = require("./escape.js").escapeHtml;
if (typeof ago === "undefined") globalThis.ago = require("./timeago.js").ago;

function kbLevelUrl(spaceId, key, offset, limit) {
  return `/api/kb/spaces/${spaceId}/children?parent=${key === "root" ? "" : key}&offset=${offset}&limit=${limit}`;
}

function snippetHtml(text) {
  return escapeHtml(text || "").replace(/\u0001/g, "<mark>").replace(/\u0002/g, "</mark>");
}

function reviewBadge(page) {
  if (page.verified_by && !page.stale) return `<span class="chip tint" style="--tint:var(--status-done)" title="Next review ${escapeHtml(page.review_by)}">verified by ${escapeHtml(page.verified_by)} ${ago(page.verified_at)}</span>`;
  if (page.stale) return `<span class="chip tint" style="--tint:var(--priority-high)">review was due ${escapeHtml(page.review_by)}</span>`;
  if (page.review_by) return `<span class="chip" title="Next review">review by ${escapeHtml(page.review_by)}</span>`;
  return "";
}

function tocHtml(headings) {
  const items = headings.filter((h) => h.level <= 3);
  if (items.length < 2) return "";
  return `<div class="kb-rail-block"><h4>On this page</h4><ul class="kb-toc">${items.map((h) => `<li style="padding-left:${(h.level - 1) * 12}px"><a href="#${h.id}" data-toc="${h.id}">${escapeHtml(h.text)}</a></li>`).join("")}</ul></div>`;
}

function recentsWith(recents, entry, limit) {
  return [entry, ...recents.filter((r) => !(r.kind === entry.kind && r.id === entry.id))].slice(0, limit);
}

if (typeof module !== "undefined") module.exports = { kbLevelUrl, snippetHtml, reviewBadge, tocHtml, recentsWith };
