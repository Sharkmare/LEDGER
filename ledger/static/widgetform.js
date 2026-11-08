"use strict";

function widgetFromValues(kind, values, existing) {
  const widget = { kind, title: values.title.trim(), size: Number(values.size) };
  if (existing && existing.id) widget.id = existing.id;
  for (const name of ["group_by", "chart", "measure", "interval"]) if (values[name]) widget[name] = values[name];
  for (const name of ["days", "limit", "iteration"]) if (values[name] !== undefined && values[name] !== "") widget[name] = Number(values[name]);
  const filters = {};
  for (const [name, value] of Object.entries({ project: values.f_project, area: values.f_area, type: values.f_type, priority: values.f_priority, assignee: values.f_assignee, label: values.f_label })) {
    if (value) filters[name] = value;
  }
  if (values.f_open) filters.open = true;
  widget.filters = filters;
  return widget;
}

function widgetValues(widget) {
  const filters = widget.filters || {};
  return { title: widget.title, size: String(widget.size), group_by: widget.group_by, chart: widget.chart, measure: widget.measure, days: widget.days, limit: widget.limit,
    interval: widget.interval || "", iteration: widget.iteration ? String(widget.iteration) : "", f_project: filters.project || "", f_area: filters.area ? String(filters.area) : "",
    f_type: filters.type || "", f_priority: filters.priority || "", f_assignee: filters.assignee || "", f_label: filters.label || "", f_open: !!filters.open };
}

if (typeof module !== "undefined") module.exports = { widgetFromValues, widgetValues };
