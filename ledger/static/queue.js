"use strict";

const QUEUE_LABEL = "My queue";
const QUEUE_REASON_TEXT = { assigned: "assigned", review: "in review", question: "open question" };

const queueState = { count: 0, tickets: [] };

function queueFromResponse(response) {
  const tickets = response && Array.isArray(response.tickets) ? response.tickets : [];
  return { count: tickets.length, tickets };
}

function queueReasonsHtml(reasons, escapeHtml) {
  return (reasons || []).filter((reason) => QUEUE_REASON_TEXT[reason])
    .map((reason) => `<span class="chip queue-chip" title="${escapeHtml(QUEUE_LABEL)}: ${QUEUE_REASON_TEXT[reason]}">${QUEUE_REASON_TEXT[reason]}</span>`).join("");
}

function queuePerson(profileName) {
  return String(profileName || "").trim().toLowerCase();
}

function queueButtonView(count) {
  return { text: `${QUEUE_LABEL} ${count}`, title: count ? `${count} ticket${count === 1 ? "" : "s"} assigned to you` : "Nothing assigned to you", quiet: count === 0 };
}

function updateQueueButton(button, count) {
  const view = queueButtonView(count);
  button.textContent = view.text;
  button.title = view.title;
  button.classList.toggle("quiet", view.quiet);
}

if (typeof module !== "undefined") module.exports = { queuePerson, queueFromResponse, queueReasonsHtml, queueButtonView, updateQueueButton };
