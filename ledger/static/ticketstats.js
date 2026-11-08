"use strict";

function statsFrom(tickets, closedStatuses) {
  const tally = (pick) => tickets.reduce((counts, t) => { const key = pick(t); if (key) counts[key] = (counts[key] || 0) + 1; return counts; }, {});
  return { open: tickets.filter((t) => !closedStatuses.includes(t.status)).length, unassigned: tickets.filter((t) => !t.assignee).length,
    by_status: tally((t) => t.status), by_type: tally((t) => t.type), by_priority: tally((t) => t.priority), by_assignee: tally((t) => t.assignee) };
}

function filterValues(fieldId, { meta, tagList, stats, assignee, statusLabels }) {
  const plain = (values) => values.map((value) => ({ value, label: value }));
  if (fieldId === "status") return meta.statuses.map((value) => ({ value, label: statusLabels[value] }));
  if (fieldId === "priority") return plain(meta.priorities);
  if (fieldId === "type") return plain(meta.types);
  if (fieldId === "label") return plain(tagList.map((tag) => tag.name));
  const names = Object.keys((stats && stats.by_assignee) || {}).filter(Boolean).sort((a, b) => a.localeCompare(b));
  if (assignee && !names.includes(assignee)) names.push(assignee);
  return plain(names);
}

if (typeof module !== "undefined") module.exports = { statsFrom, filterValues };
