registerDashboardModule("overdue", {
  render(widget, data, h) {
    const rows = data.items.map((item) => `<tr><td class="key"><span class="key">${h.escapeHtml(item.key)}</span></td><td>${h.ticketLink(item.key, item.title)}</td><td class="num">${item.days_late} d late</td></tr>`);
    return `<div class="kpi">${data.total}</div><div class="kpi-sub">open tickets past their due date</div>${rows.length ? h.ticketTable(rows) : ""}`;
  },
});
