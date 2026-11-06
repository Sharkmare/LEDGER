"use strict";

const KB_EXPANDED_PREFIX = "ledger.kbExpanded.";

function kbExpandedKey(spaceId) {
  return KB_EXPANDED_PREFIX + spaceId;
}

function kbParseExpanded(text) {
  try {
    const ids = JSON.parse(text);
    return Array.isArray(ids) ? ids.filter(Number.isInteger) : [];
  } catch (_) { return []; }
}

function kbWithExpanded(open, ids) {
  return [...new Set([...open, ...ids])];
}

function kbWithoutExpanded(open, id) {
  return open.filter((openId) => openId !== id);
}

if (typeof module !== "undefined") module.exports = { kbExpandedKey, kbParseExpanded, kbWithExpanded, kbWithoutExpanded };
