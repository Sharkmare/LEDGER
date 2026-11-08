"use strict";

const ITERATION_COLORS = { planned: "var(--status-todo)", active: "var(--status-in_progress)", done: "var(--status-done)" };
const ROADMAP_LABEL_WIDTH = 190;

function ruleChips(rules) {
  const chips = [];
  const chip = (text) => chips.push(`<span class="chip">${escapeHtml(text)}</span>`);
  if (rules.scope === "all") chip("any area");
  if (rules.project) chip(`project ${rules.project}`);
  if (rules.types) chip(`types ${rules.types.join(", ")}`);
  if (rules.priorities) chip(`priority ${rules.priorities.join(", ")}`);
  (rules.labels || []).forEach((label) => chips.push(`<span class="chip tint" style="--tint:${tagColor(label)}">${escapeHtml(label)}</span>`));
  if (rules.assignee) chip(`@${rules.assignee}`);
  if (rules.parent) chip(`under ${rules.parent}`);
  if (rules.iteration) chip(`iteration ${rules.iteration}`);
  return chips.length ? chips.join("") : `<span class="muted">Everything in the area</span>`;
}

function progressBar(done, total) {
  const percent = total ? Math.round((done / total) * 100) : 0;
  return `<div class="progress" role="progressbar" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"><span style="width:${percent}%"></span></div>`;
}

function nameOfArea(areaId) {
  const area = state.areas.find((a) => a.id === areaId);
  return area ? area.path : "";
}

async function loadArea() {
  const area = await guarded(() => api("GET", `/api/areas/${state.areaId}`));
  if (!area) { state.areaId = null; state.page = "tickets"; return; }
  const tickets = await guarded(() => request("GET", `/api/tickets?area=${state.areaId}&open=1&limit=30&exclude_type=${hiddenTypesParameter(state.hiddenTypes)}`));
  state.pageData = { area, tickets: tickets ? tickets.result : [], total: tickets ? tickets.total : 0 };
}

function areaActions() {
  return `<button id="areaBoardNew" class="primary">New board</button><button id="areaChildNew" class="ghost">New sub-area</button>
    <button id="areaEdit" class="ghost">Edit area</button>`;
}

function wireAreaActions() {
  const { area } = state.pageData;
  byId("areaBoardNew").addEventListener("click", () => boardForm(null, area.id));
  byId("areaChildNew").addEventListener("click", () => areaForm(null, area.id));
  byId("areaEdit").addEventListener("click", () => areaForm(area));
}

function renderAreaPage() {
  const { area, tickets, total } = state.pageData;
  const children = state.areas.filter((a) => a.parent_id === area.id);
  const boards = area.boards_list;
  byId("main").innerHTML = `${area.description ? `<p class="page-intro">${escapeHtml(area.description)}</p>` : ""}
    <div class="section-title">Boards <span class="grow"></span></div>
    ${boards.length ? `<div class="cards-grid">${boards.map((board) => `<div class="panel-card clickable" tabindex="0" role="button" data-board="${board.id}">
        <h3>${escapeHtml(board.name)}</h3>${board.description ? `<div class="muted">${escapeHtml(board.description)}</div>` : ""}
        <div class="rule-row">${ruleChips(board.rules)}</div>
        <div class="facts"><span>${board.tickets} tickets</span><span>${board.pinned} pinned</span><span>${board.statuses.length} columns</span></div></div>`).join("")}</div>`
      : `<div class="empty-line">No boards yet. A board shows the tickets of this area that match its rules, plus anything you pin to it.</div>`}
    ${children.length ? `<div class="section-title">Sub-areas</div><div class="cards-grid">${children.map((child) => `<div class="panel-card clickable" tabindex="0" role="button" data-area="${child.id}">
        <h3>${escapeHtml(child.name)}</h3><div class="facts"><span>${child.open_tickets} open</span><span>${child.boards} boards</span></div></div>`).join("")}</div>` : ""}
    <div class="section-title">Open tickets in this area${total > tickets.length ? ` <span class="muted">(${tickets.length} of ${total})</span>` : ""}</div>
    ${tickets.length ? `<table class="list"><tbody>${tickets.map((t) => `<tr data-key="${t.key}" tabindex="0" role="button"><td class="key">${t.key}</td><td>${escapeHtml(t.title)}</td>
        <td><span class="pill" style="--pill-color:${statusColor(t.status)}">${STATUS_LABELS[t.status]}</span></td><td>${escapeHtml(t.assignee)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-line">Nothing open here. Give a ticket this area from its drawer or the Create dialog.</div>`}`;
  byId("main").querySelectorAll("[data-board]").forEach((card) => activateOnKey(card, () => go({ page: "board", boardId: Number(card.dataset.board), view: "board" })));
  byId("main").querySelectorAll("[data-area]").forEach((card) => activateOnKey(card, () => go({ page: "area", areaId: Number(card.dataset.area) })));
  byId("main").querySelectorAll("tr[data-key]").forEach((row) => activateOnKey(row, () => openTicket(row.dataset.key)));
}

async function loadBoard() {
  const board = await guarded(() => api("GET", `/api/boards/${state.boardId}`));
  if (!board) { state.boardId = null; state.page = "tickets"; return; }
  state.pageData = { board };
  state.tickets = Object.values(board.columns).flat();
  state.total = state.tickets.length;
}

function boardActions() {
  return `<button id="boardPin" class="ghost">Pin ticket</button><button id="boardEdit" class="ghost">Edit board</button>`;
}

function wireBoardActions() {
  const { board } = state.pageData;
  byId("boardPin").addEventListener("click", () => pinForm(board));
  byId("boardEdit").addEventListener("click", () => boardForm(board));
}

function iterationStateChip(iteration) {
  return `<span class="chip tint" style="--tint:${ITERATION_COLORS[iteration.state]}">${iteration.state}</span>`;
}

async function loadPlan() {
  if (!state.project) { state.pageData = { plan: null }; return; }
  state.pageData = { plan: await guarded(() => api("GET", `/api/plan?project=${state.project}`)) };
}

function planRow(ticket) {
  return `<div class="plan-row" draggable="true" tabindex="0" role="button" data-key="${ticket.key}">
    <span class="key">${ticket.key}</span>${icon("type", ticket.type)}<span class="title" title="${escapeHtml(ticket.title)}">${escapeHtml(ticket.title)}</span>
    <span class="chip tint" style="--tint:${priorityColor(ticket.priority)}">${ticket.priority}</span>
    ${ticket.assignee ? `<span class="avatar" style="--tint:${nameColor(ticket.assignee)}" title="${escapeHtml(ticket.assignee)}">${initials(ticket.assignee)}</span>` : ""}
    <span class="points" title="Estimate">${ticket.estimate === null || ticket.estimate === undefined ? "-" : formatNumber(ticket.estimate)}</span></div>`;
}

function pickProjectHtml(message) {
  return `<div class="empty"><h2>${message}</h2><p>Choose a project to continue.</p><div class="cards-grid" style="max-width:720px;margin:0 auto;text-align:left">
    ${state.projects.map((p) => `<div class="panel-card clickable" tabindex="0" role="button" data-pick="${p.key}"><h3>${escapeHtml(p.key)} ${escapeHtml(p.name)}</h3></div>`).join("")}</div></div>`;
}

function wirePickProject() {
  byId("main").querySelectorAll("[data-pick]").forEach((card) => activateOnKey(card, () => go({ project: card.dataset.pick, nav: "all" })));
}

function renderPlan() {
  const plan = state.pageData.plan;
  if (!plan) { byId("main").innerHTML = pickProjectHtml("Pick a project to plan"); wirePickProject(); return; }
  const backlogPoints = plan.backlog.reduce((sum, t) => sum + (t.estimate || 0), 0);
  const iterations = plan.iterations.map((iteration) => {
    const done = iteration.points ? iteration.points_done : iteration.done;
    const total = iteration.points ? iteration.points : iteration.tickets;
    const next = iteration.state === "planned" ? ["active", "Start"] : iteration.state === "active" ? ["done", "Complete"] : null;
    return `<div class="plan-box" data-drop-iteration="${iteration.id}"><header><h3>${escapeHtml(iteration.name)}</h3>${iterationStateChip(iteration)}
        <span class="plan-meta">${iteration.start} to ${iteration.end}</span><span class="grow"></span>
        ${next ? `<button class="small" data-iteration-state="${iteration.id}" data-next="${next[0]}">${next[1]}</button>` : ""}
        <button class="small ghost" data-iteration-edit="${iteration.id}">Edit</button></header>
      ${iteration.goal ? `<div class="plan-goal">${escapeHtml(iteration.goal)}</div>` : ""}
      <div class="plan-progress"><div class="progress-line">${progressBar(done, total)}<span>${formatNumber(done)} of ${formatNumber(total)} ${iteration.points ? "points" : "tickets"} done</span></div></div>
      <div class="plan-body">${iteration.items.map(planRow).join("") || `<div class="empty-line">Drag tickets here from the backlog.</div>`}</div></div>`;
  }).join("");
  byId("main").innerHTML = `<div class="plan"><div class="plan-column"><div class="plan-box" data-drop-iteration=""><header><h3>Backlog</h3>
      <span class="plan-meta">${plan.backlog.length} tickets, ${formatNumber(backlogPoints)} points</span></header>
      <div class="plan-body">${plan.backlog.map(planRow).join("") || `<div class="empty-line">The backlog is empty.</div>`}</div></div></div>
    <div class="plan-column">${iterations || `<div class="empty-line">No iterations yet. Create one to plan a sprint.</div>`}</div></div>`;
  wirePlan(plan);
}

function wirePlan(plan) {
  const main = byId("main");
  main.querySelectorAll(".plan-row").forEach((row) => {
    activateOnKey(row, () => openTicket(row.dataset.key));
    row.addEventListener("dragstart", (event) => { event.dataTransfer.setData("text/plain", row.dataset.key); row.classList.add("dragging"); });
    row.addEventListener("dragend", () => row.classList.remove("dragging"));
  });
  main.querySelectorAll("[data-drop-iteration]").forEach((box) => {
    box.addEventListener("dragover", (event) => { event.preventDefault(); box.classList.add("drop-target"); });
    box.addEventListener("dragleave", () => box.classList.remove("drop-target"));
    box.addEventListener("drop", async (event) => {
      event.preventDefault();
      box.classList.remove("drop-target");
      const key = event.dataTransfer.getData("text/plain");
      if (!key) return;
      const target = box.dataset.dropIteration;
      if (await guarded(() => api("PATCH", `/api/tickets/${key}`, { iteration: target }))) toast(target ? `${key} planned` : `${key} back in the backlog`);
      refresh();
    });
  });
  main.querySelectorAll("[data-iteration-state]").forEach((button) => button.addEventListener("click", async () => {
    if (await guarded(() => api("PATCH", `/api/iterations/${button.dataset.iterationState}`, { state: button.dataset.next }))) refresh();
  }));
  main.querySelectorAll("[data-iteration-edit]").forEach((button) => button.addEventListener("click", () => {
    iterationForm(plan.iterations.find((i) => String(i.id) === button.dataset.iterationEdit), state.project);
  }));
}

function planActions() {
  return state.project ? `<button id="planNew" class="primary">New iteration</button>` : "";
}

function wirePlanActions() {
  const button = byId("planNew");
  if (button) button.addEventListener("click", () => iterationForm(null, state.project));
}

async function loadRoadmap() {
  state.pageData = { roadmap: await guarded(() => api("GET", "/api/roadmap" + (state.project ? `?project=${state.project}` : ""))) };
}

function renderRoadmap() {
  const roadmap = state.pageData.roadmap;
  if (!roadmap || (!roadmap.iterations.length && !roadmap.epics.length)) {
    byId("main").innerHTML = `<div class="empty"><h2>Nothing to put on a roadmap yet</h2><p>The roadmap shows iterations and epics that have dates. Give an epic a start and due date, or create an iteration in Plan.</p>
      ${roadmap && roadmap.unscheduled_epics ? `<p>${roadmap.unscheduled_epics} epics have no dates yet.</p>` : ""}</div>`;
    return;
  }
  const layout = roadmapLayout(roadmap, Date.now());
  const bar = ({ left, width, percent }, tint, label, attrs) =>
    `<div class="rm-bar" style="left:${left}%;width:${width}%;--tint:${tint}" ${attrs} tabindex="0" title="${escapeHtml(label)}"><span class="fill" style="width:${percent}%"></span><span>${escapeHtml(label)}</span></div>`;
  const iterationRows = layout.iterations.map((row) => {
    const i = row.iteration;
    return `<div class="rm-row"><div class="rm-label" title="${escapeHtml(i.name)}">${escapeHtml(state.project ? i.name : `${i.project} ${i.name}`)}</div>
      <div class="rm-track">${bar(row, ITERATION_COLORS[i.state], `${i.name} ${row.percent}%`, "")}</div></div>`;
  }).join("");
  const epicRows = layout.epics.map((row) => {
    const epic = row.epic;
    return `<div class="rm-row"><div class="rm-label" title="${escapeHtml(epic.title)}"><span class="key">${epic.key}</span> ${escapeHtml(epic.title)}</div>
      <div class="rm-track">${bar(row, statusColor(epic.status), `${epic.progress.done}/${epic.progress.total} done`, `data-open-ticket="${epic.key}"`)}</div></div>`;
  }).join("");
  const months = layout.months.map((m) => `<div class="rm-month" style="left:${m.left}%">${m.label}</div>`).join("");
  const todayLine = layout.todayOffset === null ? "" : `<div class="rm-today" style="left:calc(${ROADMAP_LABEL_WIDTH}px + (100% - ${ROADMAP_LABEL_WIDTH}px) * ${layout.todayOffset})"></div>`;
  byId("main").innerHTML = `<div class="roadmap">${todayLine}<div class="rm-head">${months}</div>
    ${iterationRows ? `<div class="rm-group">Iterations</div>${iterationRows}` : ""}${epicRows ? `<div class="rm-group">Epics</div>${epicRows}` : ""}
    ${roadmap.unscheduled_epics ? `<p class="muted">${roadmap.unscheduled_epics} epics have no dates and are not shown.</p>` : ""}</div>`;
  byId("main").querySelectorAll("[data-open-ticket]").forEach((element) => activateOnKey(element, () => openTicket(element.dataset.openTicket)));
}
