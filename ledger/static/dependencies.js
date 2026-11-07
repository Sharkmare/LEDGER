"use strict";

function dependencyRowHtml(entry, { escapeHtml, statusColor, statusLabel }) {
  return `<div class="rowlink dep-row" tabindex="0" role="link" data-open="${entry.key}" style="padding-left:${(entry.depth - 1) * 16 + 8}px">
    <span class="pill" style="--pill-color:${statusColor(entry.status)}">${escapeHtml(statusLabel(entry.status))}</span><span class="key">${entry.key}</span><span>${escapeHtml(entry.title)}</span></div>`;
}

function dependenciesHtml(dependencies, helpers) {
  if (!dependencies) return "";
  const blockedBy = dependencies.blocked_by || [];
  const blocks = dependencies.blocks || [];
  const path = dependencies.critical_path || [];
  if (!blockedBy.length && !blocks.length && !path.length) return "";
  const group = (heading, entries) => entries.length ? `<div class="dep-group"><div class="event">${heading}</div>${entries.map((entry) => dependencyRowHtml(entry, helpers)).join("")}</div>` : "";
  const openNote = dependencies.open_blockers ? `<div class="event dep-warn">${dependencies.open_blockers} open blocker${dependencies.open_blockers === 1 ? "" : "s"}, so this cannot move to done yet</div>` : "";
  const pathHtml = path.length ? `<div class="dep-path"><div class="event">Critical path</div><div>${path.map((key) => `<a href="#${key}" data-open="${key}">${key}</a>`).join(" -&gt; ")}</div></div>` : "";
  return `<h4>Dependencies</h4>${openNote}${group("Blocked by", blockedBy)}${group("Blocks", blocks)}${pathHtml}`;
}

if (typeof module !== "undefined") module.exports = { dependenciesHtml };
