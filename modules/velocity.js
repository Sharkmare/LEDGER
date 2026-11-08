registerDashboardModule("velocity", {
  render(widget, data, h) {
    return `${h.barPairs(data.iterations)}${h.chartLegend([{ name: "Committed", color: "var(--muted)" }, { name: "Completed", color: "var(--status-done)" }])}
      <div class="kpi-sub">${data.average === null ? "No average yet" : `Average ${h.formatNumber(data.average)} points per iteration`}</div>`;
  },
});
