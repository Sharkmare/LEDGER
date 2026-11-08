registerDashboardModule("cycle", {
  render(widget, data, h) {
    if (!data.closed) return `<div class="widget-error">Nothing was finished in the last ${data.days} days.</div>`;
    const show = (value) => (value === null ? "-" : `${h.formatNumber(value)} d`);
    return `<div class="kpi">${show(data.lead.median)}</div><div class="kpi-sub">median lead time, ${data.closed} finished in ${data.days} days</div>
      <div class="kpi-sub">average ${show(data.lead.average)}, 85% within ${show(data.lead.p85)}. Cycle time (in progress to done): median ${show(data.cycle.median)}</div>
      ${h.hbars(data.histogram.map((b) => ({ name: b.label, value: b.value })), () => "var(--accent)")}`;
  },
});
