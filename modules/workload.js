registerDashboardModule("workload", {
  render(widget, data, h) {
    if (!data.people.length) return `<div class="widget-error">No open work.</div>`;
    const bars = h.hbars(data.people.map((p) => ({ name: p.name, value: p.tickets, points: p.points, overdue: p.overdue })), (b) => h.nameColor(b.name),
      (b) => `${b.value}`);
    const detail = data.people.filter((p) => p.points || p.overdue).map((p) => `${h.escapeHtml(p.name)}: ${h.formatNumber(p.points)} points${p.overdue ? `, ${p.overdue} overdue` : ""}`);
    return bars + (detail.length ? `<div class="kpi-sub">${detail.join("  |  ")}</div>` : "") + (data.more ? `<div class="kpi-sub">and ${data.more} more</div>` : "");
  },
});
