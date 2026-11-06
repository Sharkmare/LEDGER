"use strict";

const FILTER_FIELDS = [
  { id: "status", label: "Status" }, { id: "priority", label: "Priority" }, { id: "type", label: "Type" },
  { id: "assignee", label: "Assignee" }, { id: "label", label: "Tag" },
];

function emptyFilters() {
  return { status: "", priority: "", type: "", assignee: "", label: "", open: false };
}

function activeFilters(filters) {
  const chosen = FILTER_FIELDS.filter((field) => filters[field.id]).map((field) => ({ id: field.id, label: field.label, value: filters[field.id] }));
  return filters.open ? [...chosen, { id: "open", label: "Hide done", value: "" }] : chosen;
}

function toggledFilter(filters, id, value) {
  if (id === "open") return { ...filters, open: !filters.open };
  return { ...filters, [id]: filters[id] === value ? "" : value };
}

function clearedFilter(filters, id) {
  return { ...filters, [id]: id === "open" ? false : "" };
}

if (typeof module !== "undefined") module.exports = { FILTER_FIELDS, emptyFilters, activeFilters, toggledFilter, clearedFilter };
