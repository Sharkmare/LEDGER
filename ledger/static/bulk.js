"use strict";

const BULK_MAX_KEYS = 200;

function toggledKey(selected, key, on) {
  const rest = selected.filter((entry) => entry !== key);
  return on ? [...rest, key] : rest;
}

function rangeKeys(shownKeys, anchorKey, targetKey) {
  const from = shownKeys.indexOf(anchorKey);
  const to = shownKeys.indexOf(targetKey);
  if (to < 0) return [];
  if (from < 0) return [targetKey];
  return shownKeys.slice(Math.min(from, to), Math.max(from, to) + 1);
}

function withRange(selected, shownKeys, anchorKey, targetKey, on) {
  const range = rangeKeys(shownKeys, anchorKey, targetKey);
  const rest = selected.filter((entry) => !range.includes(entry));
  return on ? [...rest, ...range] : rest;
}

function withAll(selected, shownKeys, on) {
  const rest = selected.filter((entry) => !shownKeys.includes(entry));
  return on ? [...rest, ...shownKeys] : rest;
}

function selectAllState(selected, shownKeys) {
  const count = shownKeys.filter((key) => selected.includes(key)).length;
  if (!count) return "none";
  return count === shownKeys.length ? "all" : "some";
}

function prunedSelection(selected, shownKeys) {
  return selected.filter((key) => shownKeys.includes(key));
}

function bulkChanges(action, value) {
  const text = String(value ?? "").trim();
  if (action === "status") return { status: text };
  if (action === "priority") return { priority: text };
  if (action === "assignee") return { assignee: text };
  if (action === "tag") return { add_labels: [text.toLowerCase()] };
  if (action === "cancel") return { status: "cancelled" };
  throw new Error(`unknown bulk action ${action}`);
}

function buildBulkRequests(keys, action, value, comment = "") {
  const changes = bulkChanges(action, value);
  if (action !== "cancel" && !String(value ?? "").trim()) return [];
  const requests = [];
  for (let start = 0; start < keys.length; start += BULK_MAX_KEYS) {
    const request = { keys: keys.slice(start, start + BULK_MAX_KEYS), changes };
    if (comment && comment.trim()) request.comment = comment.trim();
    requests.push(request);
  }
  return requests;
}

function mergeBulkResults(results) {
  const merged = { updated: [], unchanged: [], failed: [] };
  for (const result of results) {
    merged.updated.push(...result.updated);
    merged.unchanged.push(...result.unchanged);
    merged.failed.push(...result.failed);
  }
  return merged;
}

function bulkSummary(result) {
  const parts = [`${result.updated.length} updated`];
  if (result.unchanged.length) parts.push(`${result.unchanged.length} unchanged`);
  if (result.failed.length) parts.push(`${result.failed.length} failed: ${result.failed.slice(0, 3).map((f) => `${f.key} ${f.error}`).join("; ")}`);
  return parts.join(", ");
}

const bulkState = { selected: [], anchor: null };

function bulkHeaderCell(shownKeys) {
  const mode = selectAllState(bulkState.selected, shownKeys);
  return `<th class="bulk-cell"><input type="checkbox" id="bulkSelectAll" aria-label="Select all shown tickets" ${mode === "all" ? "checked" : ""} data-indeterminate="${mode === "some"}"></th>`;
}

function bulkRowCell(key) {
  return `<td class="bulk-cell"><input type="checkbox" class="bulk-pick" data-pick="${key}" aria-label="Select ${key}" ${bulkState.selected.includes(key) ? "checked" : ""}></td>`;
}

function bulkBarHtml() {
  if (!bulkState.selected.length) return "";
  const options = (values, label) => values.map((value) => `<option value="${value}">${label(value)}</option>`).join("");
  return `<div class="bulk-bar" role="toolbar" aria-label="Bulk actions">
    <strong class="bulk-count">${bulkState.selected.length} selected</strong>
    <label>Move to <select id="bulkStatus"><option value="">Status</option>${options(state.meta.statuses, (s) => STATUS_LABELS[s] || s)}</select></label>
    <label>Priority <select id="bulkPriority"><option value="">Priority</option>${options(state.meta.priorities, (p) => p)}</select></label>
    <span class="bulk-field"><input id="bulkAssignee" placeholder="Assignee" aria-label="Assignee"><button type="button" id="bulkAssign">Assign</button></span>
    <span class="bulk-field"><input id="bulkTag" placeholder="Tag" aria-label="Tag"><button type="button" id="bulkAddTag">Add tag</button></span>
    <button type="button" id="bulkCancel" class="danger">Cancel</button>
    <button type="button" id="bulkClear">Clear</button></div>`;
}

async function runBulkAction(action, value, comment = "") {
  const requests = buildBulkRequests(bulkState.selected, action, value, comment);
  if (!requests.length) return;
  const results = [];
  for (const request of requests) {
    const result = await guarded(() => api("POST", "/api/tickets/bulk", request));
    if (result) results.push(result);
  }
  if (!results.length) return;
  const merged = mergeBulkResults(results);
  bulkState.selected = merged.failed.map((failure) => failure.key);
  bulkState.anchor = null;
  toast(bulkSummary(merged), merged.failed.length > 0);
  await refresh();
}

function attachBulkEvents(shownKeys) {
  bulkState.selected = prunedSelection(bulkState.selected, shownKeys);
  const all = byId("bulkSelectAll");
  if (all) {
    all.indeterminate = all.dataset.indeterminate === "true";
    all.addEventListener("keydown", (event) => event.stopPropagation());
    all.addEventListener("click", (event) => {
      event.stopPropagation();
      bulkState.selected = withAll(bulkState.selected, shownKeys, all.checked);
      renderBulkOnly();
    });
  }
  byId("main").querySelectorAll(".bulk-pick").forEach((box) => {
    box.addEventListener("keydown", (event) => event.stopPropagation());
    box.addEventListener("click", (event) => {
      event.stopPropagation();
      const key = box.dataset.pick;
      bulkState.selected = event.shiftKey && bulkState.anchor
        ? withRange(bulkState.selected, shownKeys, bulkState.anchor, key, box.checked)
        : toggledKey(bulkState.selected, key, box.checked);
      bulkState.anchor = key;
      renderBulkOnly();
    });
  });
  byId("main").querySelectorAll(".bulk-cell").forEach((cell) => cell.addEventListener("click", (event) => event.stopPropagation()));
  renderBulkOnly();
}

function renderBulkOnly() {
  const main = byId("main");
  const shownKeys = [...main.querySelectorAll("tr[data-key]")].map((row) => row.dataset.key);
  main.querySelectorAll(".bulk-pick").forEach((box) => { box.checked = bulkState.selected.includes(box.dataset.pick); });
  const all = byId("bulkSelectAll");
  if (all) {
    const mode = selectAllState(bulkState.selected, shownKeys);
    all.checked = mode === "all";
    all.indeterminate = mode === "some";
  }
  main.querySelectorAll("tr[data-key]").forEach((row) => row.classList.toggle("bulk-selected", bulkState.selected.includes(row.dataset.key)));
  const existing = main.querySelector(".bulk-bar");
  if (existing) existing.remove();
  main.insertAdjacentHTML("beforeend", bulkBarHtml());
  wireBulkBar();
}

function wireBulkBar() {
  const bar = byId("main").querySelector(".bulk-bar");
  if (!bar) return;
  bar.querySelector("#bulkStatus").addEventListener("change", (event) => runBulkAction("status", event.target.value));
  bar.querySelector("#bulkPriority").addEventListener("change", (event) => runBulkAction("priority", event.target.value));
  const field = (inputId, buttonId, action) => {
    const input = bar.querySelector(inputId);
    const run = () => runBulkAction(action, input.value);
    bar.querySelector(buttonId).addEventListener("click", run);
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") run(); });
  };
  field("#bulkAssignee", "#bulkAssign", "assignee");
  field("#bulkTag", "#bulkAddTag", "tag");
  bar.querySelector("#bulkCancel").addEventListener("click", () => {
    const reason = window.prompt(`Cancel ${bulkState.selected.length} tickets? Optional reason, added as a comment:`, "");
    if (reason !== null) runBulkAction("cancel", "", reason);
  });
  bar.querySelector("#bulkClear").addEventListener("click", () => {
    bulkState.selected = [];
    bulkState.anchor = null;
    renderBulkOnly();
  });
}

if (typeof module !== "undefined") module.exports = { toggledKey, rangeKeys, withRange, withAll, selectAllState, prunedSelection, bulkChanges, buildBulkRequests, mergeBulkResults, bulkSummary, BULK_MAX_KEYS };
