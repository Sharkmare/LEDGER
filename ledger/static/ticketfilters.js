"use strict";

if (typeof hiddenTypesParameter === "undefined") globalThis.hiddenTypesParameter = require("./viewsettings.js").hiddenTypesParameter;

function ticketFilters({ project, nav, filters, hiddenTypes, actor, search }) {
  return {
    project,
    assignee: nav === "mine" ? actor : filters.assignee,
    status: nav === "blocked" ? "blocked" : filters.status,
    questions: nav === "questions" ? "open" : "",
    exclude_type: hiddenTypesParameter(hiddenTypes),
    type: filters.type, priority: filters.priority, label: filters.label,
    q: search.trim(), open: nav === "open" || filters.open ? "1" : "",
  };
}

function ticketQuery(filters) {
  const parameters = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) if (value) parameters.set(name, value);
  return parameters;
}

if (typeof module !== "undefined") module.exports = { ticketFilters, ticketQuery };
