registerDashboardModule("trend", {
  render(widget, data, h) {
    const labels = data.series.map((p) => p.date);
    const created = { name: "Created", color: "var(--accent)", values: data.series.map((p) => p.created) };
    const closed = { name: "Closed", color: "var(--status-done)", values: data.series.map((p) => p.closed) };
    return `${h.lineChart(labels, [created, closed])}${h.chartLegend([created, closed])}
      <div class="kpi-sub">${data.created} created, ${data.closed} closed in ${data.days} days, by ${data.interval}</div>`;
  },
});
