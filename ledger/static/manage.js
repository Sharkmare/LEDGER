"use strict";

const MANAGE_TABS = [
  { id: "organisation", label: "Organisation" }, { id: "projects", label: "Projects" }, { id: "areas", label: "Areas" }, { id: "boards", label: "Boards" },
  { id: "iterations", label: "Iterations" }, { id: "tags", label: "Tags" }, { id: "templates", label: "Templates" },
];

function collectForm(fields) {
  const values = {};
  for (const field of fields) {
    if (field.group) continue;
    const element = byId(`form_${field.name}`);
    values[field.name] = field.kind === "checkbox" ? element.checked : element.value;
  }
  return values;
}

function openForm(spec) {
  const dialog = byId("formDialog");
  const form = byId("formForm");
  byId("formHeading").textContent = spec.title;
  const intro = byId("formIntro");
  intro.textContent = spec.intro || "";
  intro.hidden = !spec.intro;
  dialog.classList.toggle("wide", !!spec.wide);
  byId("formFields").innerHTML = formBodyHtml(spec.fields, spec.values || {});
  byId("formExtra").innerHTML = "";
  if (spec.extra) spec.extra(byId("formExtra"));
  byId("formActions").innerHTML = `${(spec.buttons || []).map((b, i) => `<button type="button" class="ghost${b.danger ? " danger" : ""}" data-extra-button="${i}">${escapeHtml(b.label)}</button>`).join("")}
    <span style="flex:1"></span><button type="button" class="ghost" id="formCancel">Cancel</button><button type="submit" class="primary" id="formSubmit">${escapeHtml(spec.submitLabel || "Save")}</button>`;
  byId("formCancel").addEventListener("click", () => dialog.close());
  byId("formActions").querySelectorAll("[data-extra-button]").forEach((button) => button.addEventListener("click", () => spec.buttons[Number(button.dataset.extraButton)].onClick(dialog)));
  byId("formFields").querySelectorAll("[data-color-for]").forEach((picker) => picker.addEventListener("input", () => { byId(picker.dataset.colorFor).value = picker.value; }));
  form.onsubmit = async (event) => {
    event.preventDefault();
    try {
      await spec.onSubmit(collectForm(spec.fields));
      dialog.close();
    } catch (error) {
      toast(error.message, true);
    }
  };
  form.onkeydown = (event) => { if (event.ctrlKey && event.key === "Enter") form.requestSubmit(); };
  dialog.showModal();
  const first = byId("formFields").querySelector("input:not([type=color]):not(:disabled), select:not(:disabled), textarea");
  if (first) first.focus();
}

const splitList = (text) => String(text || "").split(",").map((s) => s.trim()).filter(Boolean);
const optionsOf = (items, valueOf, labelOf, blank = null) => [...(blank === null ? [] : [{ value: "", label: blank }]), ...items.map((item) => ({ value: valueOf(item), label: labelOf(item) }))];
const areaOptions = (blank, skip = []) => optionsOf(state.areas.filter((a) => !skip.includes(a.id)), (a) => String(a.id), (a) => a.path, blank);
const projectOptions = (blank) => optionsOf(state.projects, (p) => p.key, (p) => `${p.key} ${p.name}`, blank);
const typeOptions = (blank) => optionsOf(state.meta.types, (v) => v, (v) => v, blank);
const priorityOptions = (blank) => optionsOf(state.meta.priorities, (v) => v, (v) => v, blank);
const statusOptions = (blank) => optionsOf(state.meta.statuses, (v) => v, (v) => STATUS_LABELS[v], blank);

async function afterChange(message) {
  if (message) toast(message);
  await refresh();
}

function projectForm(existing) {
  openForm({
    title: existing ? `Edit project ${existing.key}` : "Create project",
    fields: [
      { name: "key", label: "Key", kind: "text", required: true, disabled: !!existing, row: "a", placeholder: "APP", help: existing ? "The key cannot change" : "2 to 10 capitals or digits, used in ticket names such as APP-1" },
      { name: "name", label: "Name", kind: "text", required: true, row: "a" },
      { name: "description", label: "Description", kind: "textarea", rows: 3 },
      { name: "tags", label: "Tags", kind: "text", placeholder: "resonite-research", help: "Comma separated. Projects with the same tag are grouped in the navigator." },
      { name: "lead", label: "Lead", kind: "text", row: "b" },
      ...(existing ? [{ name: "status", label: "Status", kind: "select", row: "b", options: [{ value: "active", label: "Active" }, { value: "archived", label: "Archived" }] }] : []),
      { name: "start", label: "Start", kind: "text", row: "c", placeholder: "YYYY-MM-DD" },
      { name: "target", label: "Target date", kind: "text", row: "c", placeholder: "YYYY-MM-DD" },
    ],
    values: existing ? { ...existing, tags: (existing.tags || []).join(", ") } : { status: "active" }, submitLabel: existing ? "Save" : "Create",
    onSubmit: async (values) => {
      const details = { name: values.name, description: values.description, lead: values.lead, start: values.start, target: values.target, tags: values.tags || "" };
      if (existing) {
        await api("PATCH", `/api/projects/${existing.key}`, { ...details, status: values.status });
        await afterChange("Project saved");
      } else {
        const created = await api("POST", "/api/projects", { key: values.key, ...details });
        state.project = created.key;
        remember(STORAGE.project, created.key);
        await afterChange(`Created ${created.key}`);
      }
    },
  });
}

function areaForm(existing, parentId) {
  const skip = existing ? descendantsOf(state.areas, existing.id) : [];
  openForm({
    title: existing ? `Edit area ${existing.name}` : "Create area",
    intro: existing ? "" : "An area groups related work, such as a product, a team or a subsystem. Boards live inside areas.",
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "description", label: "Description", kind: "textarea", rows: 3 },
      { name: "parent", label: "Inside", kind: "select", options: areaOptions("Nothing, a top-level area", skip) },
      { name: "tags", label: "Tags", kind: "text", placeholder: "resonite-research", help: "Comma separated. Top-level areas with the same tag are grouped, and the group can be folded." },
    ],
    values: existing ? { name: existing.name, description: existing.description, parent: existing.parent_id ? String(existing.parent_id) : "", tags: (existing.tags || []).join(", ") } : { parent: parentId ? String(parentId) : "" },
    submitLabel: existing ? "Save" : "Create",
    buttons: existing ? [{ label: "Delete", danger: true, onClick: async (dialog) => {
      if (!confirm(`Delete the area ${existing.name}? Its tickets keep existing and just lose this area.`)) return;
      if (await guarded(() => api("DELETE", `/api/areas/${existing.id}`))) { dialog.close(); if (state.page === "area") state.page = "tickets"; await afterChange("Area deleted"); }
    } }] : [],
    onSubmit: async (values) => {
      const payload = { name: values.name, description: values.description, parent: values.parent, tags: values.tags || "" };
      if (existing) await api("PATCH", `/api/areas/${existing.id}`, payload);
      else { const created = await api("POST", "/api/areas", payload); state.areaId = created.id; state.page = "area"; }
      await afterChange(existing ? "Area saved" : "Area created");
    },
  });
}

function boardValues(board) {
  const rules = board.rules || {};
  return { area: String(board.area_id), name: board.name, description: board.description, scope: rules.scope || "area", project: rules.project || "", types: (rules.types || []).join(", "),
    priorities: (rules.priorities || []).join(", "), labels: (rules.labels || []).join(", "), assignee: rules.assignee || "", parent: rules.parent || "",
    iteration: rules.iteration ? String(rules.iteration) : "", statuses: board.statuses.length === state.meta.statuses.length ? "" : board.statuses.join(", ") };
}

function pinnedList(board, container) {
  const tickets = Object.values(board.columns).flat().filter((t) => t.pinned);
  container.innerHTML = `<h3 class="group-title">Pinned tickets</h3>${tickets.length ? `<div class="pin-list">${tickets.map((t) => `<div class="pin-item"><span class="key">${t.key}</span><span class="title">${escapeHtml(t.title)}</span><button type="button" data-unpin="${t.key}">Unpin</button></div>`).join("")}</div>` : `<div class="empty-line">Nothing is pinned. Pin a ticket to show it here whatever the rules say.</div>`}`;
  container.querySelectorAll("[data-unpin]").forEach((button) => button.addEventListener("click", async () => {
    if (await guarded(() => api("DELETE", `/api/boards/${board.id}/items/${button.dataset.unpin}`))) { button.closest(".pin-item").remove(); refresh(); }
  }));
}

async function boardForm(existing, areaId) {
  const iterations = (await guarded(() => api("GET", "/api/iterations"))) || [];
  openForm({
    title: existing ? `Edit board ${existing.name}` : "Create board", wide: true,
    intro: "A board shows the tickets of its area (and sub-areas) that match the rules, plus any ticket pinned to it. Leave a rule empty to ignore it.",
    fields: [
      { name: "area", label: "Area", kind: "select", row: "a", options: areaOptions(null) },
      { name: "name", label: "Name", kind: "text", required: true, row: "a" },
      { name: "description", label: "Description", kind: "text" },
      { group: "Which tickets" },
      { name: "scope", label: "Scope", kind: "select", row: "b", options: [{ value: "area", label: "Only this area and its sub-areas" }, { value: "all", label: "Any ticket that matches, in any area" }] },
      { name: "project", label: "Project", kind: "select", row: "b", options: projectOptions("Any project") },
      { name: "types", label: "Types", kind: "text", row: "c", help: "Comma separated, for example bug, task" },
      { name: "priorities", label: "Priorities", kind: "text", row: "c", help: "For example high, critical" },
      { name: "labels", label: "Tags", kind: "text", row: "d", help: "Any of these tags" },
      { name: "assignee", label: "Assignee", kind: "text", row: "d" },
      { name: "parent", label: "Under ticket", kind: "text", row: "e", placeholder: "APP-1", help: "Only its sub-tickets, at any depth" },
      { name: "iteration", label: "Iteration", kind: "select", row: "e", options: optionsOf(iterations, (i) => String(i.id), (i) => `${i.project} ${i.name}`, "Any") },
      { group: "Columns" },
      { name: "statuses", label: "Statuses to show", kind: "text", help: "Comma separated, in order. Empty shows every status." },
    ],
    values: existing ? boardValues(existing) : { area: areaId ? String(areaId) : state.areas[0] ? String(state.areas[0].id) : "", scope: "area" },
    submitLabel: existing ? "Save" : "Create",
    extra: existing ? (container) => pinnedList(existing, container) : null,
    buttons: existing ? [{ label: "Delete", danger: true, onClick: async (dialog) => {
      if (!confirm(`Delete the board ${existing.name}? The tickets on it are not touched.`)) return;
      if (await guarded(() => api("DELETE", `/api/boards/${existing.id}`))) { dialog.close(); if (state.page === "board") { state.page = "area"; state.areaId = existing.area_id; } await afterChange("Board deleted"); }
    } }] : [],
    onSubmit: async (values) => {
      const rules = { scope: values.scope, project: values.project, types: splitList(values.types), priorities: splitList(values.priorities), labels: splitList(values.labels),
        assignee: values.assignee, parent: values.parent, iteration: values.iteration };
      const payload = { area: values.area, name: values.name, description: values.description, rules, statuses: splitList(values.statuses) };
      if (existing) await api("PATCH", `/api/boards/${existing.id}`, payload);
      else { const created = await api("POST", "/api/boards", payload); state.boardId = created.id; state.page = "board"; state.view = "board"; }
      await afterChange(existing ? "Board saved" : "Board created");
    },
  });
}

function pinForm(board) {
  openForm({
    title: `Pin a ticket to ${board.name}`, intro: "A pinned ticket stays on this board whatever its area or the rules.",
    fields: [{ name: "ticket", label: "Ticket key", kind: "text", required: true, placeholder: "APP-12" }], values: {}, submitLabel: "Pin",
    onSubmit: async (values) => { await api("POST", `/api/boards/${board.id}/items`, { ticket: values.ticket.trim() }); await afterChange("Pinned"); },
  });
}

function iterationForm(existing, project) {
  openForm({
    title: existing ? `Edit ${existing.name}` : "Create iteration",
    intro: existing ? "" : "An iteration is a time box such as a sprint. Tickets are planned into it from the Plan view.",
    fields: [
      { name: "project", label: "Project", kind: "select", disabled: !!existing, row: "a", options: projectOptions(null) },
      { name: "name", label: "Name", kind: "text", required: true, row: "a", placeholder: "Sprint 1" },
      { name: "start", label: "Starts", kind: "text", required: true, row: "b", placeholder: "YYYY-MM-DD" },
      { name: "end", label: "Ends", kind: "text", required: true, row: "b", placeholder: "YYYY-MM-DD" },
      { name: "goal", label: "Goal", kind: "textarea", rows: 2 },
      { name: "state", label: "State", kind: "select", options: [{ value: "planned", label: "Planned" }, { value: "active", label: "Active" }, { value: "done", label: "Done" }] },
    ],
    values: existing ? { ...existing, project: existing.project } : { project: project || (state.projects[0] || {}).key || "", state: "planned" },
    submitLabel: existing ? "Save" : "Create",
    buttons: existing ? [{ label: "Delete", danger: true, onClick: async (dialog) => {
      if (!confirm(`Delete ${existing.name}? Its tickets go back to the backlog.`)) return;
      if (await guarded(() => api("DELETE", `/api/iterations/${existing.id}`))) { dialog.close(); await afterChange("Iteration deleted"); }
    } }] : [],
    onSubmit: async (values) => {
      const payload = { name: values.name, start: values.start, end: values.end, goal: values.goal, state: values.state };
      if (existing) await api("PATCH", `/api/iterations/${existing.id}`, payload);
      else await api("POST", "/api/iterations", { project: values.project, ...payload });
      await afterChange("Iteration saved");
    },
  });
}

function mergeForm(tag) {
  const others = state.tagList.filter((t) => t.name !== tag.name);
  openForm({
    title: `Merge ${tag.name}`, intro: `Every ticket and board that uses ${tag.name} will use the tag you pick instead, and ${tag.name} goes away.`,
    fields: [{ name: "into", label: "Merge into", kind: "select", options: optionsOf(others, (t) => t.name, (t) => `${t.name} (${t.tickets})`) }], values: {}, submitLabel: "Merge",
    onSubmit: async (values) => { await api("POST", `/api/tags/${encodeURIComponent(tag.name)}/merge`, { into: values.into }); await afterChange("Tags merged"); },
  });
}

function tagForm(existing) {
  openForm({
    title: existing ? `Edit tag ${existing.name}` : "Create tag",
    intro: existing && existing.tickets ? `Renaming changes the tag on ${existing.tickets} tickets and ${existing.boards} boards.` : "",
    fields: [
      { name: "name", label: "Name", kind: "text", required: true },
      { name: "color", label: "Colour", kind: "color", help: "Leave empty for a colour picked from the name" },
      { name: "description", label: "Description", kind: "text" },
    ],
    values: existing || {}, submitLabel: existing ? "Save" : "Create",
    buttons: existing ? [
      { label: "Merge into...", onClick: (dialog) => { dialog.close(); mergeForm(existing); } },
      { label: "Delete", danger: true, onClick: async (dialog) => {
        if (!confirm(`Delete the tag ${existing.name}? It is removed from ${existing.tickets} tickets and ${existing.boards} boards.`)) return;
        if (await guarded(() => api("DELETE", `/api/tags/${encodeURIComponent(existing.name)}`))) { dialog.close(); await afterChange("Tag deleted"); }
      } }] : [],
    onSubmit: async (values) => {
      if (existing) await api("PATCH", `/api/tags/${encodeURIComponent(existing.name)}`, { name: values.name, color: values.color, description: values.description });
      else await api("POST", "/api/tags", { name: values.name, color: values.color, description: values.description });
      await afterChange("Tag saved");
    },
  });
}

function templateForm(existing) {
  openForm({
    title: existing ? `Edit template ${existing.name}` : "Create template", wide: true,
    intro: "A template pre-fills the Create ticket dialog. Anything you type there wins over the template.",
    fields: [
      { name: "name", label: "Name", kind: "text", required: true, row: "a" },
      { name: "project", label: "For project", kind: "select", row: "a", options: projectOptions("Every project") },
      { name: "description", label: "What it is for", kind: "text" },
      { name: "type", label: "Type", kind: "select", row: "b", options: typeOptions(null) },
      { name: "priority", label: "Priority", kind: "select", row: "b", options: priorityOptions(null) },
      { name: "status", label: "Status", kind: "select", row: "b", options: statusOptions(null) },
      { name: "title", label: "Title start", kind: "text", help: "Prefix the title, for example Bug: " },
      { name: "body", label: "Description text", kind: "textarea", rows: 6 },
      { name: "labels", label: "Tags", kind: "text", row: "c", help: "Comma separated" },
      { name: "assignee", label: "Assignee", kind: "text", row: "c" },
      { name: "estimate", label: "Estimate", kind: "number", min: 0, row: "c" },
    ],
    values: existing ? { ...existing, labels: existing.labels.join(", "), estimate: existing.estimate === null ? "" : existing.estimate } : { type: "task", priority: "medium", status: "backlog" },
    submitLabel: existing ? "Save" : "Create",
    buttons: existing ? [{ label: "Delete", danger: true, onClick: async (dialog) => {
      if (!confirm(`Delete the template ${existing.name}?`)) return;
      if (await guarded(() => api("DELETE", `/api/templates/${existing.id}`))) { dialog.close(); await afterChange("Template deleted"); }
    } }] : [],
    onSubmit: async (values) => {
      const payload = { name: values.name, project: values.project, description: values.description, type: values.type, priority: values.priority, status: values.status,
        title: values.title, body: values.body, labels: splitList(values.labels), assignee: values.assignee, estimate: values.estimate === "" ? null : Number(values.estimate) };
      if (existing) await api("PATCH", `/api/templates/${existing.id}`, payload);
      else await api("POST", "/api/templates", payload);
      await afterChange("Template saved");
    },
  });
}

async function loadManage() {
  const tab = state.manageTab;
  const data = {};
  if (tab === "iterations") data.iterations = await guarded(() => api("GET", "/api/iterations" + (state.manageProject ? `?project=${state.manageProject}` : "")));
  if (tab === "tags") { state.tagList = (await guarded(() => api("GET", "/api/tags"))) || []; data.tags = state.tagList; }
  if (tab === "templates") data.templates = await guarded(() => api("GET", "/api/templates"));
  if (tab === "boards") data.boards = await guarded(() => api("GET", "/api/boards"));
  state.pageData = data;
}

function table(columns, rows, emptyText) {
  if (!rows.length) return `<div class="empty-line">${emptyText}</div>`;
  return `<table class="data-table"><thead><tr>${columns.map((c) => `<th>${c.label}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((c) => `<td class="${c.cls || ""}">${c.render(row)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

const rowButton = (action, id, label = "Edit") => `<button type="button" data-act="${action}" data-id="${escapeHtml(id)}">${label}</button>`;

function renderManageTab() {
  const tab = state.manageTab;
  const data = state.pageData;
  if (tab === "organisation") {
    const totals = state.projects.reduce((sum, p) => sum + Object.values(p.counts).reduce((a, b) => a + b, 0), 0);
    return `<p class="page-intro">The organisation is the top of the hierarchy. It holds projects, which hold tickets, and areas, which hold boards.</p>
      <div class="toolbar"><label>Name <input id="orgName" value="${escapeHtml(state.org.name)}" autocomplete="off"></label><button id="orgSave" class="primary">Save</button></div>
      <div class="cards-grid"><div class="panel-card"><h3>${state.projects.length}</h3><span class="muted">projects</span></div><div class="panel-card"><h3>${state.areas.length}</h3><span class="muted">areas</span></div>
      <div class="panel-card"><h3>${state.boards.length}</h3><span class="muted">boards</span></div><div class="panel-card"><h3>${totals}</h3><span class="muted">tickets</span></div></div>`;
  }
  if (tab === "projects") {
    return `<div class="toolbar"><span class="grow"></span><button class="primary" data-act="project-new">New project</button></div>${table([
      { label: "Key", render: (p) => `<span class="key">${escapeHtml(p.key)}</span>` }, { label: "Name", render: (p) => escapeHtml(p.name) }, { label: "Lead", render: (p) => escapeHtml(p.lead) },
      { label: "Status", render: (p) => `<span class="chip tint" style="--tint:${p.status === "active" ? "var(--status-done)" : "var(--muted)"}">${p.status}</span>` },
      { label: "Dates", render: (p) => (p.start || p.target ? `${p.start || "?"} to ${p.target || "?"}` : "") },
      { label: "Tickets", cls: "num", render: (p) => Object.values(p.counts).reduce((a, b) => a + b, 0) }, { label: "", cls: "actions", render: (p) => rowButton("project-edit", p.key) },
    ], state.projects, "No projects yet.")}`;
  }
  if (tab === "areas") {
    return `<div class="toolbar"><span class="grow"></span><button class="primary" data-act="area-new">New area</button></div>${table([
      { label: "Area", render: (a) => `<span style="padding-left:${a.depth * 18}px">${escapeHtml(a.name)}</span>` }, { label: "Description", render: (a) => escapeHtml(a.description) },
      { label: "Boards", cls: "num", render: (a) => a.boards }, { label: "Open", cls: "num", render: (a) => a.open_tickets }, { label: "All tickets", cls: "num", render: (a) => a.tickets },
      { label: "", cls: "actions", render: (a) => `${rowButton("area-open", a.id, "Open")}${rowButton("area-edit", a.id)}` },
    ], state.areas, "No areas yet. Create one to start organising boards.")}`;
  }
  if (tab === "boards") {
    return `<div class="toolbar"><span class="grow"></span><button class="primary" data-act="board-new">New board</button></div>${table([
      { label: "Area", render: (b) => escapeHtml(b.area) }, { label: "Board", render: (b) => escapeHtml(b.name) }, { label: "Rules", render: (b) => `<div class="rule-row">${ruleChips(b.rules, tagColor)}</div>` },
      { label: "Tickets", cls: "num", render: (b) => b.tickets }, { label: "Pinned", cls: "num", render: (b) => b.pinned },
      { label: "", cls: "actions", render: (b) => `${rowButton("board-open", b.id, "Open")}${rowButton("board-edit", b.id)}` },
    ], data.boards || [], "No boards yet. Create an area first, then a board inside it.")}`;
  }
  if (tab === "iterations") {
    return `<div class="toolbar"><label>Project <select id="manageProject">${projectOptions("All projects").map((o) => `<option value="${escapeHtml(o.value)}"${o.value === state.manageProject ? " selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}</select></label>
      <span class="grow"></span><button class="primary" data-act="iteration-new">New iteration</button></div>${table([
      { label: "Project", render: (i) => `<span class="key">${escapeHtml(i.project)}</span>` }, { label: "Name", render: (i) => escapeHtml(i.name) }, { label: "Dates", render: (i) => `${i.start} to ${i.end}` },
      { label: "State", render: (i) => iterationStateChip(i) }, { label: "Tickets", cls: "num", render: (i) => `${i.done}/${i.tickets}` }, { label: "Points", cls: "num", render: (i) => `${formatNumber(i.points_done)}/${formatNumber(i.points)}` },
      { label: "", cls: "actions", render: (i) => rowButton("iteration-edit", i.id) },
    ], data.iterations || [], "No iterations yet.")}`;
  }
  if (tab === "tags") {
    return `<p class="page-intro">Tags are free text on tickets. Register one here to give it a colour and a description, rename it everywhere, or merge two into one.</p>
      <div class="toolbar"><span class="grow"></span><button class="primary" data-act="tag-new">New tag</button></div>${table([
      { label: "Tag", render: (t) => `<span class="swatch" style="--tint:${tagColor(t.name)}"></span>${escapeHtml(t.name)}${t.registered ? "" : ' <span class="muted">(not registered)</span>'}` },
      { label: "Description", render: (t) => escapeHtml(t.description) }, { label: "Tickets", cls: "num", render: (t) => t.tickets }, { label: "Open", cls: "num", render: (t) => t.open_tickets },
      { label: "Boards", cls: "num", render: (t) => t.boards }, { label: "", cls: "actions", render: (t) => rowButton("tag-edit", t.name, t.registered ? "Edit" : "Register") },
    ], data.tags || [], "No tags yet. Tags appear here as soon as a ticket uses one.")}`;
  }
  return `<p class="page-intro">Templates fill in the Create ticket dialog: type, priority, a description outline, tags and an estimate.</p>
    <div class="toolbar"><span class="grow"></span><button class="ghost" data-act="template-defaults">Add standard templates</button><button class="primary" data-act="template-new">New template</button></div>${table([
    { label: "Template", render: (t) => escapeHtml(t.name) }, { label: "For", render: (t) => escapeHtml(t.project || "every project") },
    { label: "Type", render: (t) => `<span class="chip tint" style="--tint:${typeColor(t.type)}">${t.type}</span>` }, { label: "Priority", render: (t) => t.priority },
    { label: "Tags", render: (t) => t.labels.map((l) => `<span class="chip tint" style="--tint:${tagColor(l)}">${escapeHtml(l)}</span>`).join(" ") },
    { label: "", cls: "actions", render: (t) => rowButton("template-edit", t.id) },
  ], data.templates || [], "No templates yet.")}`;
}

function renderManage() {
  byId("main").innerHTML = renderManageTab();
  const data = state.pageData;
  const find = (list, id, key = "id") => (list || []).find((item) => String(item[key]) === String(id));
  const handlers = {
    "project-new": () => projectForm(null), "project-edit": (id) => projectForm(find(state.projects, id, "key")),
    "area-new": () => areaForm(null), "area-edit": (id) => areaForm(find(state.areas, id)), "area-open": (id) => go({ page: "area", areaId: Number(id) }),
    "board-new": () => boardForm(null), "board-open": (id) => go({ page: "board", boardId: Number(id), view: "board" }),
    "board-edit": async (id) => boardForm(await guarded(() => api("GET", `/api/boards/${id}`))),
    "iteration-new": () => iterationForm(null, state.manageProject), "iteration-edit": (id) => iterationForm(find(data.iterations, id)),
    "tag-new": () => tagForm(null), "tag-edit": (id) => tagForm(find(data.tags, id, "name")),
    "template-new": () => templateForm(null), "template-edit": (id) => templateForm(find(data.templates, id)),
    "template-defaults": async () => { const made = await guarded(() => api("POST", "/api/templates/defaults", {})); if (made) afterChange(made.length ? `Added ${made.length} templates` : "The standard templates are already there"); },
  };
  byId("main").querySelectorAll("[data-act]").forEach((button) => button.addEventListener("click", () => handlers[button.dataset.act](button.dataset.id)));
  const save = byId("orgSave");
  if (save) save.addEventListener("click", async () => { if (await guarded(() => api("PUT", "/api/organisation", { name: byId("orgName").value }))) afterChange("Organisation saved"); });
  const projectFilter = byId("manageProject");
  if (projectFilter) projectFilter.addEventListener("change", () => { state.manageProject = projectFilter.value; refresh(); });
}
