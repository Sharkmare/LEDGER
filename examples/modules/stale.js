registerDashboardModule("stale", {
  render(widget, data, h) {
    const rows = data.items.map((item) => `<tr><td class="key"><span class="key">${h.escapeHtml(item.key)}</span></td><td>${h.ticketLink(item.key, item.title)}</td><td class="num">${item.quiet_days} d quiet</td></tr>`);
    return `<div class="kpi">${data.total}</div><div class="kpi-sub">open tickets untouched for ${data.days} days or more</div>${rows.length ? h.ticketTable(rows) : ""}`;
  },
});
