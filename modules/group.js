registerDashboardModule("group", {
  render(widget, data, h) {
    const colorOf = (bucket) => h.bucketColor(data.field, bucket);
    return widget.chart === "donut" ? h.donut(data.buckets, colorOf) : h.hbars(data.buckets, colorOf);
  },
});
