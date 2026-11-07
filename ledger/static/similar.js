"use strict";

const SIMILAR_MIN_TITLE_LENGTH = 8;
const SIMILAR_DEBOUNCE_MS = 300;
const SIMILAR_LIMIT = 3;

function shouldCheckSimilar(project, title) {
  return Boolean(project) && String(title || "").trim().length >= SIMILAR_MIN_TITLE_LENGTH;
}

function similarRequestPath(project, title, limit = SIMILAR_LIMIT) {
  const query = new URLSearchParams({ project, title: String(title).trim(), limit: String(limit) });
  return `/api/tickets/similar?${query.toString()}`;
}

function isCurrentSimilarAnswer(asked, current) {
  return asked.project === current.project && asked.title.trim() === current.title.trim();
}

function similarEntryText(match) {
  return `${match.key} ${match.title} (${String(match.status).replace(/_/g, " ")})`;
}

function renderSimilarHtml(matches, escape) {
  if (!Array.isArray(matches) || !matches.length) return "";
  const items = matches.map((match) =>
    `<li><a href="/#${escape(match.key)}" target="_blank" rel="noopener"><span class="similar-key">${escape(match.key)}</span> ${escape(match.title)} <span class="similar-status">${escape(String(match.status).replace(/_/g, " "))}</span></a></li>`);
  return `<p class="similar-heading">Similar open tickets</p><ul>${items.join("")}</ul>`;
}

function debounced(action, delay, timers = { set: (callback, wait) => setTimeout(callback, wait), clear: (id) => clearTimeout(id) }) {
  let pending = null;
  return (...values) => {
    if (pending !== null) timers.clear(pending);
    pending = timers.set(() => { pending = null; action(...values); }, delay);
  };
}

function setupSimilarCheck() {
  const box = byId("newSimilar");
  const clear = () => { box.hidden = true; box.innerHTML = ""; };
  const check = debounced(async () => {
    const asked = { project: byId("newProject").value, title: byId("newTitle").value };
    if (!shouldCheckSimilar(asked.project, asked.title)) { clear(); return; }
    let matches;
    try { matches = await api("GET", similarRequestPath(asked.project, asked.title)); } catch (_) { return; }
    if (!isCurrentSimilarAnswer(asked, { project: byId("newProject").value, title: byId("newTitle").value })) return;
    const html = renderSimilarHtml(matches, escapeHtml);
    box.innerHTML = html;
    box.hidden = !html;
  }, SIMILAR_DEBOUNCE_MS);
  byId("newTitle").addEventListener("input", () => { if (!shouldCheckSimilar(byId("newProject").value, byId("newTitle").value)) clear(); check(); });
  byId("newProject").addEventListener("change", check);
  byId("newDialog").addEventListener("close", clear);
  clear();
}

if (typeof module !== "undefined") module.exports = { SIMILAR_MIN_TITLE_LENGTH, SIMILAR_DEBOUNCE_MS, shouldCheckSimilar, similarRequestPath, isCurrentSimilarAnswer, similarEntryText, renderSimilarHtml, debounced };
