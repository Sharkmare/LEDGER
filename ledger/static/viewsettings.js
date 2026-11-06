"use strict";

function parseHiddenTypes(text, validTypes) {
  try {
    const stored = JSON.parse(text);
    return Array.isArray(stored) ? validTypes.filter((type) => stored.includes(type)) : [];
  } catch (_) { return []; }
}

function toggledHiddenType(hidden, type, validTypes) {
  const next = hidden.includes(type) ? hidden.filter((name) => name !== type) : [...hidden, type];
  return validTypes.filter((name) => next.includes(name));
}

function visibleTickets(tickets, hidden) {
  return hidden.length ? tickets.filter((ticket) => !hidden.includes(ticket.type)) : tickets;
}

function hiddenTypesParameter(hidden) {
  return hidden.join(",");
}

function hiddenTypesLabel(hidden) {
  return hidden.length ? `Hiding ${hidden.join(", ")}` : "";
}

if (typeof module !== "undefined") module.exports = { parseHiddenTypes, toggledHiddenType, visibleTickets, hiddenTypesParameter, hiddenTypesLabel };
