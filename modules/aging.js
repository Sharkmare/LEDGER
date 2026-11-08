registerDashboardModule("aging", {
  render(widget, data, h) {
    const oldest = data.oldest.map((item) => `<tr><td class="key"><span class="key">${h.escapeHtml(item.key)}</span></td><td>${h.ticketLink(item.key, item.title)}</td><td class="num">${item.age_days} d</td></tr>`);
    return `${h.hbars(data.buckets.map((b) => ({ name: b.label, value: b.value })), () => "var(--priority-medium)")}${oldest.length ? `<div class="kpi-sub">Oldest</div>${h.ticketTable(oldest)}` : ""}`;
  },
});
