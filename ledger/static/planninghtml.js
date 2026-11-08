"use strict";

if (typeof escapeHtml === "undefined") globalThis.escapeHtml = require("./escape.js").escapeHtml;

function ruleChips(rules, tagColor) {
  const chips = [];
  const chip = (text) => chips.push(`<span class="chip">${escapeHtml(text)}</span>`);
  if (rules.scope === "all") chip("any area");
  if (rules.project) chip(`project ${rules.project}`);
  if (rules.types) chip(`types ${rules.types.join(", ")}`);
  if (rules.priorities) chip(`priority ${rules.priorities.join(", ")}`);
  (rules.labels || []).forEach((label) => chips.push(`<span class="chip tint" style="--tint:${tagColor(label)}">${escapeHtml(label)}</span>`));
  if (rules.assignee) chip(`@${rules.assignee}`);
  if (rules.parent) chip(`under ${rules.parent}`);
  if (rules.iteration) chip(`iteration ${rules.iteration}`);
  return chips.length ? chips.join("") : `<span class="muted">Everything in the area</span>`;
}

function progressBar(done, total) {
  const percent = total ? Math.round((done / total) * 100) : 0;
  return `<div class="progress" role="progressbar" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"><span style="width:${percent}%"></span></div>`;
}

if (typeof module !== "undefined") module.exports = { ruleChips, progressBar };
