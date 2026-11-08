"use strict";

const WIDGET_KINDS = {
  count: "Count with change", group: "Breakdown", trend: "Created and closed", burndown: "Burndown", cycle: "Lead and cycle time",
  aging: "Age of open work", workload: "Workload by person", velocity: "Velocity", overdue: "Overdue work",
};
const GROUP_LABELS = { status: "Status", type: "Type", priority: "Priority", assignee: "Assignee", label: "Tag", project: "Project", area: "Area", iteration: "Iteration" };

function bucketColor(field, bucket) {
  if (field === "status") return statusColor(bucket.key);
  if (field === "priority") return priorityColor(bucket.key);
  if (field === "type") return typeColor(bucket.key);
  if (field === "label") return tagColor(bucket.key || bucket.name);
  return bucket.key === null ? "var(--muted)" : nameColor(bucket.name);
}

function ticketTable(rows) {
  return `<table class="mini-table"><tbody>${rows.join("")}</tbody></table>`;
}

function ticketLink(key, title) {
  return `<a data-open-ticket="${escapeHtml(key)}">${escapeHtml(title)}</a>`;
}

const WIDGET_RENDERERS = {
  count(widget, data) {
    const sign = data.delta > 0 ? "+" : "";
    const direction = widget.measure === "closed" ? (data.delta > 0 ? "good" : data.delta < 0 ? "bad" : "") : "";
    const against = widget.measure === "total" ? `${data.days} days ago` : `the ${data.days} days before`;
    return `<div class="kpi">${data.value}</div><div class="kpi-sub"><span class="delta ${direction}">${sign}${data.delta}</span> against ${against} (${data.previous})</div>`;
  },
  group(widget, data) {
    const colorOf = (bucket) => bucketColor(data.field, bucket);
    return widget.chart === "donut" ? donut(data.buckets, colorOf) : hbars(data.buckets, colorOf);
  },
  trend(widget, data) {
    const labels = data.series.map((p) => p.date);
    const created = { name: "Created", color: "var(--accent)", values: data.series.map((p) => p.created) };
    const closed = { name: "Closed", color: "var(--status-done)", values: data.series.map((p) => p.closed) };
    return `${lineChart(labels, [created, closed])}${chartLegend([created, closed])}
      <div class="kpi-sub">${data.created} created, ${data.closed} closed in ${data.days} days, by ${data.interval}</div>`;
  },
  burndown(widget, data) {
    const labels = data.days.map((d) => d.date);
    const ideal = { name: "Ideal", color: "var(--muted)", values: data.days.map((d) => d.ideal) };
    const remaining = { name: "Remaining", color: "var(--status-in_progress)", values: data.days.map((d) => d.remaining) };
    const left = [...data.days].reverse().find((d) => d.remaining !== null);
    return `<div class="kpi-sub"><strong>${escapeHtml(data.iteration.name)}</strong> ${data.iteration.start} to ${data.iteration.end}, ${left ? formatNumber(left.remaining) : "-"} of ${formatNumber(data.total)} ${data.unit} left</div>
      ${lineChart(labels, [ideal, remaining], { dashed: [0] })}${chartLegend([ideal, remaining])}`;
  },
  cycle(widget, data) {
    if (!data.closed) return `<div class="widget-error">Nothing was finished in the last ${data.days} days.</div>`;
    const show = (value) => (value === null ? "-" : `${formatNumber(value)} d`);
    return `<div class="kpi">${show(data.lead.median)}</div><div class="kpi-sub">median lead time, ${data.closed} finished in ${data.days} days</div>
      <div class="kpi-sub">average ${show(data.lead.average)}, 85% within ${show(data.lead.p85)}. Cycle time (in progress to done): median ${show(data.cycle.median)}</div>
      ${hbars(data.histogram.map((b) => ({ name: b.label, value: b.value })), () => "var(--accent)")}`;
  },
  aging(widget, data) {
    const oldest = data.oldest.map((item) => `<tr><td class="key"><span class="key">${escapeHtml(item.key)}</span></td><td>${ticketLink(item.key, item.title)}</td><td class="num">${item.age_days} d</td></tr>`);
    return `${hbars(data.buckets.map((b) => ({ name: b.label, value: b.value })), () => "var(--priority-medium)")}${oldest.length ? `<div class="kpi-sub">Oldest</div>${ticketTable(oldest)}` : ""}`;
  },
  workload(widget, data) {
    if (!data.people.length) return `<div class="widget-error">No open work.</div>`;
    const bars = hbars(data.people.map((p) => ({ name: p.name, value: p.tickets, points: p.points, overdue: p.overdue })), (b) => nameColor(b.name),
      (b) => `${b.value}`);
    const detail = data.people.filter((p) => p.points || p.overdue).map((p) => `${escapeHtml(p.name)}: ${formatNumber(p.points)} points${p.overdue ? `, ${p.overdue} overdue` : ""}`);
    return bars + (detail.length ? `<div class="kpi-sub">${detail.join("  |  ")}</div>` : "") + (data.more ? `<div class="kpi-sub">and ${data.more} more</div>` : "");
  },
  velocity(widget, data) {
    return `${barPairs(data.iterations)}${chartLegend([{ name: "Committed", color: "var(--muted)" }, { name: "Completed", color: "var(--status-done)" }])}
      <div class="kpi-sub">${data.average === null ? "No average yet" : `Average ${formatNumber(data.average)} points per iteration`}</div>`;
  },
  overdue(widget, data) {
    const rows = data.items.map((item) => `<tr><td class="key"><span class="key">${escapeHtml(item.key)}</span></td><td>${ticketLink(item.key, item.title)}</td><td class="num">${item.days_late} d late</td></tr>`);
    return `<div class="kpi">${data.total}</div><div class="kpi-sub">open tickets past their due date</div>${rows.length ? ticketTable(rows) : ""}`;
  },
};

function widgetBody(widget, data) {
  if (!data) return `<div class="widget-error">Loading</div>`;
  if (data.error) return `<div class="widget-error">${escapeHtml(data.error)}</div>`;
  return WIDGET_RENDERERS[widget.kind](widget, data);
}

function widgetHtml(widget, data, editing, index, total) {
  const controls = editing ? `<button data-widget-move="-1" ${index === 0 ? "disabled" : ""} title="Move earlier" aria-label="Move earlier">&#8592;</button>
    <button data-widget-move="1" ${index === total - 1 ? "disabled" : ""} title="Move later" aria-label="Move later">&#8594;</button>
    <button data-widget-edit title="Edit widget">Edit</button><button data-widget-remove class="danger" title="Remove widget">Remove</button>` : "";
  return `<section class="widget span-${widget.size}" data-widget="${escapeHtml(widget.id)}"><header><h3>${escapeHtml(widget.title)}</h3>${controls}</header>${widgetBody(widget, data)}</section>`;
}

const dashboardState = { editing: false, loadedFor: null };

async function loadDashboards() {
  state.dashboards = (await guarded(() => api("GET", "/api/dashboards"))) || [];
  if (!state.dashboards.some((d) => d.id === state.dashboardId)) state.dashboardId = state.dashboards.length ? state.dashboards[0].id : null;
  state.dashboardData = null;
  if (state.dashboardId) state.dashboardData = await guarded(() => api("GET", `/api/dashboards/${state.dashboardId}/data`));
}

function currentDashboard() { return state.dashboards.find((d) => d.id === state.dashboardId) || null; }

async function saveWidgets(widgets) {
  const dashboard = currentDashboard();
  if (!dashboard) return;
  if (await guarded(() => api("PATCH", `/api/dashboards/${dashboard.id}`, { widgets }))) { await refresh(); }
}

function widgetFields(kind, values) {
  const fields = [{ name: "title", label: "Title", kind: "text", placeholder: WIDGET_KINDS[kind] }];
  fields.push({ name: "size", label: "Width", kind: "select", row: "a", options: [{ value: "1", label: "One column" }, { value: "2", label: "Two columns" }, { value: "3", label: "Three columns" }] });
  if (kind === "group") {
    fields.push({ name: "group_by", label: "Group by", kind: "select", row: "a", options: Object.entries(GROUP_LABELS).map(([value, label]) => ({ value, label })) });
    fields.push({ name: "chart", label: "Chart", kind: "select", row: "a", options: [{ value: "bar", label: "Bars" }, { value: "donut", label: "Donut" }] });
  }
  if (kind === "count") {
    fields.push({ name: "measure", label: "Measure", kind: "select", row: "b", options: [{ value: "total", label: "Tickets that exist" }, { value: "created", label: "Created in the period" }, { value: "closed", label: "Closed in the period" }] });
    fields.push({ name: "days", label: "Period in days", kind: "number", min: 1, row: "b" });
  }
  if (kind === "trend") {
    fields.push({ name: "days", label: "Days to show", kind: "number", min: 1, row: "b" });
    fields.push({ name: "interval", label: "Step", kind: "select", row: "b", options: [{ value: "", label: "Automatic" }, { value: "day", label: "Day" }, { value: "week", label: "Week" }] });
  }
  if (kind === "cycle") fields.push({ name: "days", label: "Look back in days", kind: "number", min: 1 });
  if (kind === "velocity") fields.push({ name: "days", label: "Iterations to show", kind: "number", min: 1, help: "Counts the most recent finished iterations" });
  if (["workload", "overdue", "aging", "group"].includes(kind)) fields.push({ name: "limit", label: kind === "group" ? "Most common to show" : "Rows to show", kind: "number", min: 1 });
  if (kind === "burndown") {
    fields.push({ name: "iteration", label: "Iteration", kind: "select", options: [{ value: "", label: "The current one" }, ...state.iterationsAll.map((i) => ({ value: String(i.id), label: `${i.project} ${i.name}` }))] });
  }
  if (kind !== "burndown") {
    fields.push({ group: "Which tickets" });
    fields.push({ name: "f_project", label: "Project", kind: "select", row: "f1", options: [{ value: "", label: "All" }, ...state.projects.map((p) => ({ value: p.key, label: `${p.key} ${p.name}` }))] });
    fields.push({ name: "f_area", label: "Area", kind: "select", row: "f1", options: [{ value: "", label: "All" }, ...state.areas.map((a) => ({ value: String(a.id), label: a.path }))] });
    fields.push({ name: "f_type", label: "Type", kind: "select", row: "f2", options: [{ value: "", label: "Any" }, ...state.meta.types.map((v) => ({ value: v, label: v }))] });
    fields.push({ name: "f_priority", label: "Priority", kind: "select", row: "f2", options: [{ value: "", label: "Any" }, ...state.meta.priorities.map((v) => ({ value: v, label: v }))] });
    fields.push({ name: "f_assignee", label: "Assignee", kind: "text", row: "f3" });
    fields.push({ name: "f_label", label: "Tag", kind: "text", row: "f3" });
    fields.push({ name: "f_open", label: "Only open tickets", kind: "checkbox" });
  }
  return fields;
}

async function editWidget(existing, kind) {
  state.iterationsAll = (await guarded(() => api("GET", "/api/iterations"))) || [];
  const dashboard = currentDashboard();
  const isNew = !existing;
  openForm({
    title: isNew ? `Add ${WIDGET_KINDS[kind].toLowerCase()} widget` : "Edit widget", fields: widgetFields(kind),
    values: widgetValues(existing || { title: "", size: { trend: 2, burndown: 2, velocity: 2, cycle: 2 }[kind] || 1, group_by: "status", chart: "bar", measure: "total",
      days: { count: 7, trend: 30, cycle: 30, velocity: 6 }[kind] || "", limit: 8, filters: {} }),
    submitLabel: isNew ? "Add widget" : "Save widget",
    onSubmit: async (values) => {
      const widget = widgetFromValues(kind, values, existing);
      const widgets = isNew ? [...dashboard.widgets, widget] : dashboard.widgets.map((w) => (w.id === existing.id ? widget : w));
      const saved = await api("PATCH", `/api/dashboards/${dashboard.id}`, { widgets });
      state.dashboards = state.dashboards.map((d) => (d.id === saved.id ? saved : d));
      await refresh();
    },
  });
}

function chooseWidgetKind() {
  openForm({
    title: "Add widget", intro: "Pick what the widget measures. You set the details next.",
    fields: [{ name: "kind", label: "Widget", kind: "select", options: Object.entries(WIDGET_KINDS).map(([value, label]) => ({ value, label })) }],
    values: { kind: "count" }, submitLabel: "Next",
    onSubmit: async (values) => { setTimeout(() => editWidget(null, values.kind), 0); },
  });
}

function newDashboard() {
  openForm({
    title: "New dashboard", fields: [{ name: "name", label: "Name", kind: "text", required: true }, { name: "description", label: "Description", kind: "text" }],
    values: {}, submitLabel: "Create",
    onSubmit: async (values) => {
      const created = await api("POST", "/api/dashboards", { name: values.name, description: values.description });
      state.dashboardId = created.id;
      dashboardState.editing = true;
      await refresh();
    },
  });
}

function dashboardActions() {
  const dashboard = currentDashboard();
  const select = `<select id="dashboardSelect" aria-label="Dashboard">${state.dashboards.map((d) => `<option value="${d.id}"${d.id === state.dashboardId ? " selected" : ""}>${escapeHtml(d.name)}</option>`).join("")}</select>`;
  const editing = dashboardState.editing;
  return `${state.dashboards.length ? select : ""}
    ${dashboard ? `<button id="dashEdit" class="${editing ? "primary" : "ghost"}">${editing ? "Done" : "Edit dashboard"}</button>` : ""}
    ${editing ? `<button id="dashAdd" class="ghost">Add widget</button><button id="dashRename" class="ghost">Rename</button><button id="dashDelete" class="ghost danger">Delete</button>` : ""}
    <button id="dashNew" class="ghost">New dashboard</button>`;
}

function wireDashboardActions() {
  const dashboard = currentDashboard();
  const on = (id, handler) => { const element = byId(id); if (element) element.addEventListener("click", handler); };
  const select = byId("dashboardSelect");
  if (select) select.addEventListener("change", () => { state.dashboardId = Number(select.value); remember(STORAGE.dashboard, String(state.dashboardId)); dashboardState.editing = false; refresh(); });
  on("dashNew", newDashboard);
  on("dashEdit", () => { dashboardState.editing = !dashboardState.editing; render(); });
  on("dashAdd", chooseWidgetKind);
  on("dashRename", () => openForm({
    title: "Rename dashboard", fields: [{ name: "name", label: "Name", kind: "text", required: true }, { name: "description", label: "Description", kind: "text" }],
    values: { name: dashboard.name, description: dashboard.description }, submitLabel: "Save",
    onSubmit: async (values) => { await api("PATCH", `/api/dashboards/${dashboard.id}`, { name: values.name, description: values.description }); await refresh(); },
  }));
  on("dashDelete", async () => {
    if (!confirm(`Delete the dashboard ${dashboard.name}? Tickets are not affected.`)) return;
    if (await guarded(() => api("DELETE", `/api/dashboards/${dashboard.id}`))) { dashboardState.editing = false; await refresh(); }
  });
}

function renderDashboardsPage() {
  const dashboard = currentDashboard();
  if (!dashboard) {
    byId("main").innerHTML = `<div class="empty"><h2>No dashboards yet</h2><p>A dashboard is a set of widgets that measure your tickets.</p>
      <button class="primary" id="dashDefaults">Add the standard dashboards</button> <button class="ghost" id="dashStart">Start a blank one</button></div>`;
    byId("dashDefaults").addEventListener("click", async () => { if (await guarded(() => api("POST", "/api/dashboards/defaults", {}))) refresh(); });
    byId("dashStart").addEventListener("click", newDashboard);
    return;
  }
  const results = state.dashboardData ? state.dashboardData.results : {};
  const editing = dashboardState.editing;
  byId("main").innerHTML = `${dashboard.description ? `<p class="page-intro">${escapeHtml(dashboard.description)}</p>` : ""}
    ${dashboard.widgets.length ? `<div class="dash-grid${editing ? " edit-mode" : ""}">${dashboard.widgets.map((w, i) => widgetHtml(w, results[w.id], editing, i, dashboard.widgets.length)).join("")}</div>`
      : `<div class="empty"><p>This dashboard has no widgets. Choose Edit dashboard, then Add widget.</p></div>`}`;
  byId("main").querySelectorAll("[data-open-ticket]").forEach((link) => link.addEventListener("click", () => openTicket(link.dataset.openTicket)));
  byId("main").querySelectorAll("[data-widget]").forEach((element) => {
    const id = element.dataset.widget;
    const widget = dashboard.widgets.find((w) => w.id === id);
    const move = (step) => {
      const widgets = [...dashboard.widgets];
      const index = widgets.findIndex((w) => w.id === id);
      const target = index + step;
      if (target < 0 || target >= widgets.length) return;
      [widgets[index], widgets[target]] = [widgets[target], widgets[index]];
      saveWidgets(widgets);
    };
    element.querySelectorAll("[data-widget-move]").forEach((button) => button.addEventListener("click", () => move(Number(button.dataset.widgetMove))));
    const edit = element.querySelector("[data-widget-edit]");
    if (edit) edit.addEventListener("click", () => editWidget(widget, widget.kind));
    const remove = element.querySelector("[data-widget-remove]");
    if (remove) remove.addEventListener("click", () => { if (confirm(`Remove the widget ${widget.title}?`)) saveWidgets(dashboard.widgets.filter((w) => w.id !== id)); });
  });
}
