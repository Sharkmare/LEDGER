registerDashboardModule("burndown", {
  render(widget, data, h) {
    const labels = data.days.map((d) => d.date);
    const ideal = { name: "Ideal", color: "var(--muted)", values: data.days.map((d) => d.ideal) };
    const remaining = { name: "Remaining", color: "var(--status-in_progress)", values: data.days.map((d) => d.remaining) };
    const left = [...data.days].reverse().find((d) => d.remaining !== null);
    return `<div class="kpi-sub"><strong>${h.escapeHtml(data.iteration.name)}</strong> ${data.iteration.start} to ${data.iteration.end}, ${left ? h.formatNumber(left.remaining) : "-"} of ${h.formatNumber(data.total)} ${data.unit} left</div>
      ${h.lineChart(labels, [ideal, remaining], { dashed: [0] })}${h.chartLegend([ideal, remaining])}`;
  },
});
