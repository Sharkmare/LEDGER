"use strict";

const UNTAGGED = "untagged";

function tagGroups(projects) {
  if (!projects.some((p) => (p.tags || []).length)) return [{ tag: "", projects }];
  const groups = new Map();
  projects.forEach((p) => (p.tags && p.tags.length ? p.tags : [UNTAGGED]).forEach((tag) => groups.set(tag, [...(groups.get(tag) || []), p])));
  return [...groups.keys()].sort((a, b) => (a === UNTAGGED) - (b === UNTAGGED) || a.localeCompare(b)).map((tag) => ({ tag, projects: groups.get(tag) }));
}

if (typeof module !== "undefined") module.exports = { tagGroups, UNTAGGED };
