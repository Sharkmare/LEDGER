"use strict";

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

function dashboardHelpers() {
  return { escapeHtml, formatNumber, hbars, donut, lineChart, chartLegend, barPairs, ticketTable, ticketLink, bucketColor,
    statusColor, priorityColor, typeColor, tagColor, nameColor };
}

function widgetHtml(widget, data, editing, index, total) {
  const known = !!moduleById(dashboardState.listing.modules, widget.kind);
  const controls = editing ? `<button data-widget-move="-1" ${index === 0 ? "disabled" : ""} title="Move earlier" aria-label="Move earlier">&#8592;</button>
    <button data-widget-move="1" ${index === total - 1 ? "disabled" : ""} title="Move later" aria-label="Move later">&#8594;</button>
    <button data-widget-edit title="Edit widget" ${known ? "" : "disabled"}>Edit</button><button data-widget-remove class="danger" title="Remove widget">Remove</button>` : "";
  return `<section class="widget span-${widget.size}" data-widget="${escapeHtml(widget.id)}" data-module="${escapeHtml(widget.kind)}"><header><h3>${escapeHtml(widget.title)}</h3>${controls}</header>${widgetBody(widget, data, dashboardHelpers())}</section>`;
}

const dashboardState = { editing: false, loadedFor: null, scriptsLoaded: new Set(), scriptFailures: [], listing: { folders: [], modules: [], failures: [] } };

function loadScriptTag(url) {
  return new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = url;
    tag.onload = resolve;
    tag.onerror = () => reject(new Error(`could not load ${url}`));
    document.head.appendChild(tag);
  });
}

async function loadModules() {
  if (dashboardState.listingLoaded) return;
  const listing = await guarded(() => api("GET", "/api/modules"));
  if (!listing) return;
  dashboardState.listing = listing;
  dashboardState.listingLoaded = true;
  const failed = await loadModuleScripts(listing.modules, loadScriptTag, dashboardState.scriptsLoaded);
  dashboardState.scriptFailures = failed.length ? failed : dashboardState.scriptFailures.filter((item) => !dashboardState.scriptsLoaded.has(item.id));
}

async function loadDashboards() {
  await loadModules();
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

async function editWidget(existing, moduleId) {
  const descriptor = moduleById(dashboardState.listing.modules, moduleId);
  if (!descriptor) { toast(`The ${moduleId} module is not loaded`, true); return; }
  state.iterationsAll = (await guarded(() => api("GET", "/api/iterations"))) || [];
  const dashboard = currentDashboard();
  const isNew = !existing;
  const choices = {
    iterations: state.iterationsAll, projects: state.projects.map((p) => ({ value: p.key, label: `${p.key} ${p.name}` })),
    areas: state.areas.map((a) => ({ value: String(a.id), label: a.path })),
    types: state.meta.types.map((v) => ({ value: v, label: v })), priorities: state.meta.priorities.map((v) => ({ value: v, label: v })),
  };
  openForm({
    title: isNew ? `Add ${descriptor.title.toLowerCase()} widget` : "Edit widget", intro: descriptor.description || undefined, fields: moduleFormFields(descriptor, choices),
    values: widgetValues(descriptor, existing || newWidgetDefaults(descriptor)),
    submitLabel: isNew ? "Add widget" : "Save widget",
    onSubmit: async (values) => {
      const widget = widgetFromValues(descriptor, values, existing);
      const widgets = isNew ? [...dashboard.widgets, widget] : dashboard.widgets.map((w) => (w.id === existing.id ? widget : w));
      const saved = await api("PATCH", `/api/dashboards/${dashboard.id}`, { widgets });
      state.dashboards = state.dashboards.map((d) => (d.id === saved.id ? saved : d));
      await refresh();
    },
  });
}

function chooseWidgetKind() {
  const modules = dashboardState.listing.modules;
  if (!modules.length) { toast("No dashboard modules are loaded", true); return; }
  openForm({
    title: "Add widget", intro: "Pick what the widget measures. You set the details next.",
    fields: [{ name: "kind", label: "Widget", kind: "select", options: moduleChoices(modules) }],
    values: { kind: modules[0].id }, submitLabel: "Next",
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

function moduleProblemsHtml() {
  const lines = [...moduleFailureLines(dashboardState.listing.failures), ...dashboardState.scriptFailures.map((item) => `${item.id}: ${item.error}`)];
  if (!lines.length) return "";
  return `<details class="module-problems"><summary>${lines.length} dashboard module${lines.length === 1 ? "" : "s"} could not be used</summary>
    <ul>${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul></details>`;
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
    ${moduleProblemsHtml()}
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
