"use strict";

function wipCountHtml(shown, status, wip) {
  const limit = wip && wip.limits ? wip.limits[status] : 0;
  if (!limit) return `<span class="count">${shown}</span>`;
  const total = wip.counts[status] ?? shown;
  const over = total > limit;
  const title = over ? `${total} tickets, over the limit of ${limit}` : `${total} of ${limit} allowed`;
  return `<span class="count wip${over ? " wip-over" : ""}" title="${title}">${total} / ${limit}</span>`;
}

if (typeof module !== "undefined") module.exports = { wipCountHtml };
