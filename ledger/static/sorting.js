"use strict";

const SORT_FIELDS = [
  { id: "key", label: "Key" }, { id: "title", label: "Title" }, { id: "status", label: "Status" }, { id: "priority", label: "Priority" },
  { id: "type", label: "Type" }, { id: "assignee", label: "Assignee" }, { id: "estimate", label: "Estimate" }, { id: "updated", label: "Updated" },
];
const DESCENDING_FIRST = ["priority", "updated", "estimate"];

function naturalCompare(left, right) {
  const split = (text) => String(text).toLowerCase().match(/\d+|\D+/g) || [];
  const a = split(left);
  const b = split(right);
  for (let index = 0; index < Math.min(a.length, b.length); index++) {
    if (a[index] === b[index]) continue;
    if (/^\d/.test(a[index]) && /^\d/.test(b[index])) {
      const difference = Number(a[index]) - Number(b[index]);
      if (difference) return difference;
      if (a[index].length !== b[index].length) return a[index].length - b[index].length;
      continue;
    }
    return a[index] < b[index] ? -1 : 1;
  }
  return a.length - b.length;
}

function defaultSortDirection(field) {
  return DESCENDING_FIRST.includes(field) ? "desc" : "asc";
}

function sortValue(ticket, field, vocabulary) {
  if (field === "status") return vocabulary.statuses.indexOf(ticket.status);
  if (field === "priority") return vocabulary.priorities.indexOf(ticket.priority);
  if (field === "estimate") return ticket.estimate === null || ticket.estimate === undefined ? null : ticket.estimate;
  if (field === "updated") return ticket.updated;
  if (field === "key") return ticket.key;
  return String(ticket[field] ?? "");
}

function isBlank(value) {
  return value === null || value === "";
}

function sortTickets(tickets, sort, vocabulary) {
  if (!sort || !sort.field) return tickets;
  const direction = sort.direction === "desc" ? -1 : 1;
  const compareValues = (a, b) => (typeof a === "number" && typeof b === "number" ? a - b : naturalCompare(a, b));
  return [...tickets].sort((left, right) => {
    const a = sortValue(left, sort.field, vocabulary);
    const b = sortValue(right, sort.field, vocabulary);
    if (isBlank(a) !== isBlank(b)) return isBlank(a) ? 1 : -1;
    const primary = isBlank(a) ? 0 : compareValues(a, b) * direction;
    return primary || naturalCompare(left.key, right.key);
  });
}

function nextSort(current, field) {
  if (current && current.field === field) return { field, direction: current.direction === "asc" ? "desc" : "asc" };
  return { field, direction: defaultSortDirection(field) };
}

if (typeof module !== "undefined") module.exports = { naturalCompare, sortTickets, nextSort, defaultSortDirection, SORT_FIELDS };
