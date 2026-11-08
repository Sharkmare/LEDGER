"use strict";

const WIKI_LINK = /\[\[([^\]\n|]+)(?:\|[^\]\n]*)?\]\]/g;
const OPEN_WIKI_LINK = /\[\[([^\]\n|]*)$/;
const WIKI_SUGGESTION_LIMIT = 7;

function wikiMap(text, titles) {
  const map = {};
  for (const match of text.matchAll(WIKI_LINK)) {
    const title = match[1].trim().toLowerCase();
    const found = titles.find((t) => t.title.toLowerCase() === title);
    map[title] = found ? { id: found.id, title: found.title } : null;
  }
  return map;
}

function openWikiQuery(textBeforeCaret) {
  const match = textBeforeCaret.match(OPEN_WIKI_LINK);
  return match ? match[1] : null;
}

function wikiSuggestions(titles, query) {
  const needle = query.toLowerCase();
  return titles.filter((t) => t.title.toLowerCase().includes(needle)).slice(0, WIKI_SUGGESTION_LIMIT);
}

if (typeof module !== "undefined") module.exports = { wikiMap, openWikiQuery, wikiSuggestions };
