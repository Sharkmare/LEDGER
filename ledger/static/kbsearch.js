"use strict";

function kbSearchTransition(kb, text) {
  if (text) {
    if (kb.view === "search") return { query: text };
    const scoped = kb.view === "space" || kb.view === "page";
    return {
      view: "search", query: text, searchSpaceId: scoped ? kb.spaceId : null, searchAll: false,
      back: { view: kb.view, spaceId: kb.spaceId, pageId: kb.pageId }, pageId: null,
    };
  }
  if (kb.view !== "search") return null;
  return { ...(kb.back || { view: "home", spaceId: null, pageId: null }), query: "", back: null };
}

if (typeof module !== "undefined") module.exports = { kbSearchTransition };
