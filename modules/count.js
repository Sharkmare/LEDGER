registerDashboardModule("count", {
  render(widget, data) {
    const sign = data.delta > 0 ? "+" : "";
    const direction = widget.measure === "closed" ? (data.delta > 0 ? "good" : data.delta < 0 ? "bad" : "") : "";
    const against = widget.measure === "total" ? `${data.days} days ago` : `the ${data.days} days before`;
    return `<div class="kpi">${data.value}</div><div class="kpi-sub"><span class="delta ${direction}">${sign}${data.delta}</span> against ${against} (${data.previous})</div>`;
  },
});
