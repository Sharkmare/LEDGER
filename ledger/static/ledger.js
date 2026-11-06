"use strict";

const STATUS_LABELS = { backlog: "Backlog", todo: "To do", in_progress: "In progress", in_review: "In review", blocked: "Blocked", done: "Done", cancelled: "Cancelled" };
const PRIORITY_MARKS = { lowest: "v", low: "-", medium: "=", high: "+", critical: "!", blocker: "!!" };
const STORAGE = { actor: "ledger.actor", project: "ledger.project", view: "ledger.view", page: "ledger.page", theme: "ledger.theme", nav: "ledger.navCollapsed",
  sections: "ledger.navSections", dashboard: "ledger.dashboard", area: "ledger.area", board: "ledger.board", manage: "ledger.manage", kb: "ledger.kb", areas: "ledger.navAreas", sort: "ledger.sort" };
const DEFAULT_ACTOR = "me";
const SEARCH_DEBOUNCE_MS = 200;
const TOAST_MS = 2600;
const POLL_MS = 8000;
const NARROW_QUERY = "(max-width: 900px)";
const KEY_PATTERN = /^[A-Z][A-Z0-9]+-\d+$/;
const TICKET_VIEWS = ["summary", "board", "list", "plan", "roadmap"];
const VIEW_LABELS = { summary: "Summary", board: "Board", list: "List", plan: "Plan", roadmap: "Roadmap" };
const WORK_ITEMS = [
  { id: "all", label: "All work", icon: "layers" }, { id: "mine", label: "Assigned to me", icon: "user" },
  { id: "open", label: "Open work", icon: "check" }, { id: "blocked", label: "Blocked", icon: "alert" },
];
const ICONS = {
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.5" y2="16.5"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 3 21 9 15 9"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7"/><line x1="12" y1="17" x2="12" y2="17.01"/>',
  sun: '<circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="5" y1="5" x2="6.5" y2="6.5"/><line x1="17.5" y1="17.5" x2="19" y2="19"/><line x1="5" y1="19" x2="6.5" y2="17.5"/><line x1="17.5" y1="6.5" x2="19" y2="5"/>',
  moon: '<path d="M21 13a9 9 0 1 1-10-10 7 7 0 0 0 10 10z"/>',
  layers: '<polygon points="12 3 3 8 12 13 21 8 12 3"/><polyline points="3 13 12 18 21 13"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  check: '<circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16 9"/>',
  alert: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="13"/><line x1="12" y1="16" x2="12" y2="16.01"/>',
  docs: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  chart: '<line x1="6" y1="20" x2="6" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="18" y1="20" x2="18" y2="14"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  board: '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/><rect x="17" y="4" width="4" height="13" rx="1"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/>',
  timeline: '<line x1="3" y1="7" x2="14" y2="7"/><line x1="8" y1="12" x2="20" y2="12"/><line x1="5" y1="17" x2="16" y2="17"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};

Object.assign(ICONS, {
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/><line x1="9" y1="8" x2="15" y2="8"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.2L3 17.8V21h3.2l6.3-6.3a4 4 0 0 0 5.2-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
});

const state = {
  meta: null, org: { name: "" }, projects: [], areas: [], boards: [], tagList: [], tickets: [], total: 0, stats: null,
  page: "tickets", project: "", nav: "all", view: "board", areaId: null, boardId: null, dashboards: [], dashboardId: null, dashboardData: null,
  manageTab: "projects", manageProject: "", kbSpaces: [], kb: { view: "home", spaceId: null, pageId: null, editing: false, history: false, toolKind: "", toolLocation: "", toolQuery: "" }, pageData: null, iterationsAll: [], icons: {}, openKey: null, searchTimer: null, navFilter: "", collapsedSections: [], collapsedAreas: [], sort: { field: "", direction: "asc" }, filters: emptyFilters(),
};

const byId = (id) => document.getElementById(id);

function remember(key, value) { try { localStorage.setItem(key, value); } catch (_) { return; } }
function recall(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; } }

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function svg(name) { return `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`; }

function fillIcons() {
  document.querySelectorAll("[data-icon]").forEach((element) => {
    const name = element.dataset.icon;
    element.innerHTML = name === "theme" ? `<span class="sun">${svg("sun")}</span><span class="moon">${svg("moon")}</span>` : svg(name);
  });
}

function actorName() { return (byId("actorInput").value || "").trim() || DEFAULT_ACTOR; }

async function request(method, path, payload) {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "X-Ledger-Actor": actorName() },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || response.statusText);
  return { result, total: Number(response.headers.get("X-Total-Count") || 0) };
}

async function api(method, path, payload) { return (await request(method, path, payload)).result; }

function toast(message, isError = false) {
  const element = byId("toast");
  element.textContent = message;
  element.className = "toast" + (isError ? " error" : "");
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.hidden = true; }, isError ? TOAST_MS * 2 : TOAST_MS);
}

async function guarded(action) {
  try { return await action(); } catch (error) { toast(error.message, true); return null; }
}

function icon(group, name) {
  const character = state.icons[`${group}_${name}`];
  return character ? `<span class="icon" aria-hidden="true">${escapeHtml(character)}</span>` : "";
}

const statusColor = (status) => `var(--status-${status})`;
const priorityColor = (priority) => `var(--priority-${priority})`;
const typeColor = (type) => `var(--type-${type})`;

function nameColor(name) {
  let hash = 0;
  for (const character of String(name).toLowerCase()) hash = (hash * 31 + character.codePointAt(0)) % 360;
  return `hsl(${hash} 62% 62%)`;
}

function tagColor(name) {
  const tag = state.tagList.find((t) => t.name === String(name).toLowerCase());
  return tag && tag.color ? tag.color : nameColor(name);
}

const initials = (name) => escapeHtml(String(name).trim().slice(0, 2));

function fillSelect(select, values, labelOf = (v) => v, blank = null) {
  select.innerHTML = (blank === null ? "" : `<option value="">${escapeHtml(blank)}</option>`) +
    values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(labelOf(value))}</option>`).join("");
}

function setOptions(select, options, chosen = "") {
  select.innerHTML = options.map((o) => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join("");
  select.value = chosen;
}

async function loadIcons() {
  try {
    const response = await fetch("/fonts/icons.json");
    if (!response.ok) return;
    const table = await response.json();
    for (const [name, code] of Object.entries(table.glyphs || table)) {
      const point = typeof code === "number" ? code : parseInt(String(code).replace(/^U\+/i, ""), 16);
      if (!Number.isNaN(point)) state.icons[name] = String.fromCodePoint(point);
    }
  } catch (_) { return; }
}

function statsFrom(tickets) {
  const tally = (pick) => tickets.reduce((counts, t) => { const key = pick(t); if (key) counts[key] = (counts[key] || 0) + 1; return counts; }, {});
  return { open: tickets.filter((t) => !state.meta.closed_statuses.includes(t.status)).length, unassigned: tickets.filter((t) => !t.assignee).length,
    by_status: tally((t) => t.status), by_type: tally((t) => t.type), by_priority: tally((t) => t.priority), by_assignee: tally((t) => t.assignee) };
}

function currentFilters() {
  return {
    project: state.project,
    assignee: state.nav === "mine" ? actorName() : state.filters.assignee,
    status: state.nav === "blocked" ? "blocked" : state.filters.status,
    type: state.filters.type, priority: state.filters.priority, label: state.filters.label,
    q: byId("searchBox").value.trim(), open: state.nav === "open" || state.filters.open ? "1" : "",
  };
}

function drawerHasFocus() { return !byId("drawer").hidden && byId("drawer").contains(document.activeElement); }

async function loadTicketsPage() {
  if (state.view === "plan") return loadPlan();
  if (state.view === "roadmap") return loadRoadmap();
  const parameters = new URLSearchParams();
  for (const [name, value] of Object.entries(currentFilters())) if (value) parameters.set(name, value);
  const listed = await guarded(() => request("GET", "/api/tickets?" + parameters));
  if (listed) { state.tickets = listed.result; state.total = listed.total; }
  state.stats = await guarded(() => api("GET", "/api/stats" + (state.project ? `?project=${state.project}` : "")));
  state.pageData = null;
}

async function refresh({ redrawDrawer = true } = {}) {
  const editorMounted = state.page === "kb" && state.kb.editing && byId("kbBody");
  const overview = await guarded(() => api("GET", "/api/overview"));
  if (overview) { state.org = overview.organisation; state.areas = overview.areas; state.boards = overview.boards; state.projects = overview.projects; }
  state.tagList = (await guarded(() => api("GET", "/api/tags"))) || state.tagList;
  state.kbSpaces = (await guarded(() => api("GET", "/api/kb/spaces"))) || state.kbSpaces;
  if (editorMounted) { renderNav(); return; }
  const loaders = { tickets: loadTicketsPage, area: loadArea, board: loadBoard, dashboards: loadDashboards, manage: loadManage, kb: loadKb };
  await loaders[state.page]();
  render();
  if (state.openKey && redrawDrawer && !drawerHasFocus()) openTicket(state.openKey, false);
}

function go(changes = {}) {
  if (("page" in changes ? changes.page === "kb" : state.page === "kb") !== (state.page === "kb")) byId("searchBox").value = "";
  Object.assign(state, changes);
  remember(STORAGE.project, state.project);
  remember(STORAGE.view, state.view);
  remember(STORAGE.page, state.page);
  remember(STORAGE.area, state.areaId || "");
  remember(STORAGE.board, state.boardId || "");
  remember(STORAGE.manage, state.manageTab);
  remember(STORAGE.kb, JSON.stringify({ view: state.kb.view, spaceId: state.kb.spaceId, pageId: state.kb.pageId, toolKind: state.kb.toolKind, toolLocation: state.kb.toolLocation }));
  closeNavOnNarrow();
  return refresh();
}

function filterValues(fieldId) {
  const plain = (values) => values.map((value) => ({ value, label: value }));
  if (fieldId === "status") return state.meta.statuses.map((value) => ({ value, label: STATUS_LABELS[value] }));
  if (fieldId === "priority") return plain(state.meta.priorities);
  if (fieldId === "type") return plain(state.meta.types);
  if (fieldId === "label") return plain(state.tagList.map((tag) => tag.name));
  const names = Object.keys((state.stats && state.stats.by_assignee) || {}).filter(Boolean).sort((a, b) => a.localeCompare(b));
  if (state.filters.assignee && !names.includes(state.filters.assignee)) names.push(state.filters.assignee);
  return plain(names);
}

function applyFilters(next) {
  state.filters = next;
  closeColumnMenu();
  refresh();
}

function closeColumnMenu() {
  const menu = byId("columnMenu");
  if (menu) menu.remove();
}

function openColumnMenu(fieldId, anchor) {
  const reopening = byId("columnMenu") && byId("columnMenu").dataset.field === fieldId;
  closeColumnMenu();
  if (reopening) return;
  const field = FILTER_FIELDS.find((entry) => entry.id === fieldId);
  const options = filterValues(fieldId);
  const menu = document.createElement("div");
  menu.id = "columnMenu";
  menu.className = "column-menu";
  menu.dataset.field = fieldId;
  menu.setAttribute("role", "menu");
  menu.innerHTML = `<div class="column-menu-title">Filter ${escapeHtml(field.label)}</div>` +
    options.map((option) => `<button type="button" role="menuitemcheckbox" class="column-menu-item" aria-checked="${state.filters[fieldId] === option.value}" data-value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</button>`).join("") +
    (options.length ? "" : `<div class="column-menu-empty">Nothing to choose</div>`) +
    (fieldId === "status" ? `<button type="button" role="menuitemcheckbox" class="column-menu-item" aria-checked="${state.filters.open}" data-toggle-open="1">Hide done</button>` : "");
  document.body.appendChild(menu);
  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${rect.bottom + 4}px`;
  menu.addEventListener("click", (event) => {
    const item = event.target.closest("button");
    if (!item) return;
    applyFilters(item.dataset.toggleOpen ? toggledFilter(state.filters, "open") : toggledFilter(state.filters, fieldId, item.dataset.value));
  });
}

function renderFilterBar() {
  const onTickets = state.page === "tickets";
  const active = onTickets ? activeFilters(state.filters) : [];
  const activeChips = active.map((entry) => `<span class="filter-chip active"><button type="button" class="chip-body" ${entry.id === "open" ? 'data-filter-toggle="1"' : `data-filter-open="${entry.id}"`}>${escapeHtml(entry.value ? `${entry.label}: ${entry.value}` : entry.label)}</button><button type="button" class="chip-clear" data-filter-clear="${entry.id}" aria-label="Clear ${escapeHtml(entry.label)}">\u00D7</button></span>`);
  const offered = onTickets && state.view === "board"
    ? [...FILTER_FIELDS.filter((field) => !state.filters[field.id]).map((field) => `<button type="button" class="filter-chip" data-filter-open="${field.id}">${field.label} \u25BE</button>`),
      ...(state.filters.open ? [] : [`<button type="button" class="filter-chip" data-filter-toggle="1">Hide done</button>`])]
    : [];
  const clearAll = active.length > 1 ? [`<button type="button" class="ghost" data-filter-clear="all">Clear all</button>`] : [];
  byId("filterChips").innerHTML = [...activeChips, ...offered, ...clearAll].join("");
}

function openCount(project) {
  return Object.entries(project.counts).filter(([status]) => !state.meta.closed_statuses.includes(status)).reduce((sum, [, count]) => sum + count, 0);
}

function tagGroups(projects) {
  if (!projects.some((p) => (p.tags || []).length)) return [{ tag: "", projects }];
  const groups = new Map();
  projects.forEach((p) => (p.tags && p.tags.length ? p.tags : ["untagged"]).forEach((tag) => groups.set(tag, [...(groups.get(tag) || []), p])));
  return [...groups.keys()].sort((a, b) => (a === "untagged") - (b === "untagged") || a.localeCompare(b)).map((tag) => ({ tag, projects: groups.get(tag) }));
}

function sectionCollapsed(name) { return state.collapsedSections.includes(name); }

function navItemHtml({ id, label, iconName, tile, count, active, href, kind, indent = 0, twisty }) {
  const lead = tile ? `<span class="tile" style="--tint:${nameColor(tile)}">${escapeHtml(tile.slice(0, 2))}</span>` : svg(iconName);
  const tag = href ? "a" : "button";
  return `<${tag} class="nav-item${active ? " active" : ""}" ${href ? `href="${href}"` : `type="button"`} data-kind="${kind}" data-id="${escapeHtml(id)}" style="padding-left:${8 + indent * 16}px"
    ${active ? 'aria-current="page"' : ""}>${twisty ? `<span class="twisty ${twisty}" data-twisty="${escapeHtml(id)}" role="button" aria-label="${twisty === "closed" ? "Expand" : "Collapse"} ${escapeHtml(label)}" aria-expanded="${twisty === "open"}"></span>` : kind === "area" ? '<span class="twisty none"></span>' : ""}${lead}<span class="label">${escapeHtml(label)}</span>${count === undefined ? "" : `<span class="count">${count}</span>`}</${tag}>`;
}

function navSections() {
  const filter = state.navFilter.toLowerCase();
  const matches = (label) => !filter || label.toLowerCase().includes(filter);
  const onTickets = state.page === "tickets";
  const areaById = new Map(state.areas.map((a) => [a.id, a]));
  const rootIdOf = (area) => { let node = area; while (node.parent_id && areaById.has(node.parent_id)) node = areaById.get(node.parent_id); return node.id; };
  const blocks = new Map();
  let hiddenBelow = Infinity;
  state.areas.forEach((area) => {
    if (area.depth > hiddenBelow) return;
    hiddenBelow = Infinity;
    const block = blocks.get(rootIdOf(area)) || [];
    blocks.set(rootIdOf(area), block);
    const areaBoards = state.boards.filter((b) => b.area_id === area.id);
    const hasChildren = areaBoards.length > 0 || state.areas.some((other) => other.parent_id === area.id);
    const folded = !filter && hasChildren && state.collapsedAreas.includes(area.id);
    if (folded) hiddenBelow = area.depth;
    const shownBoards = folded ? [] : areaBoards.filter((b) => matches(b.name) || matches(area.path));
    if (matches(area.path) || areaBoards.some((b) => matches(b.name))) {
      block.push((offset) => navItemHtml({ id: area.id, label: area.name, iconName: "folder", count: area.open_tickets, kind: "area", indent: area.depth + offset, twisty: hasChildren ? (folded ? "closed" : "open") : "", active: state.page === "area" && state.areaId === area.id }));
    }
    shownBoards.forEach((b) => block.push((offset) => navItemHtml({ id: b.id, label: b.name, iconName: "board", count: b.tickets, kind: "board", indent: area.depth + 1 + offset, active: state.page === "board" && state.boardId === b.id })));
  });
  const roots = state.areas.filter((a) => !a.parent_id && (blocks.get(a.id) || []).length);
  const areaItems = tagGroups(roots).flatMap((group) => {
    const groupKey = "areagroup:" + group.tag;
    const folded = !filter && !!group.tag && sectionCollapsed(groupKey);
    const header = group.tag ? [navItemHtml({ id: groupKey, label: group.tag, iconName: "folder", count: group.projects.reduce((sum, a) => sum + a.open_tickets, 0), kind: "area-group", twisty: folded ? "closed" : "open" })] : [];
    return folded ? header : [...header, ...group.projects.flatMap((root) => blocks.get(root.id).map((render) => render(group.tag ? 1 : 0)))];
  });
  return [
    { name: "Work", items: WORK_ITEMS.filter((i) => matches(i.label)).map((i) => navItemHtml({ id: i.id, label: i.label, iconName: i.icon, kind: "work", active: onTickets && !state.project && state.nav === i.id && ["board", "list"].includes(state.view) })) },
    { name: state.org.name || "Organisation", key: "Organisation", total: state.areas.length, items: [...areaItems, ...(matches("create area") ? [navItemHtml({ id: "create-area", label: "Create area", iconName: "plus", kind: "create-area" })] : [])] },
    { name: "Projects", total: state.projects.filter((p) => p.status !== "archived").length, items: [
      ...tagGroups(state.projects.filter((p) => p.status !== "archived" && matches(p.key + " " + p.name + " " + (p.tags || []).join(" ")))).flatMap((group) => [
        ...(group.tag ? [navItemHtml({ id: "group:" + group.tag, label: group.tag, iconName: "folder", kind: "project-group", count: group.projects.reduce((sum, p) => sum + openCount(p), 0) })] : []),
        ...group.projects.map((p) => navItemHtml({ id: p.key, label: p.name, tile: p.key, count: openCount(p), kind: "project", indent: group.tag ? 1 : 0, active: onTickets && state.project === p.key && !["plan", "roadmap"].includes(state.view) })),
      ]),
      ...(matches("create project") ? [navItemHtml({ id: "create-project", label: "Create project", iconName: "plus", kind: "create-project" })] : []),
    ] },
    { name: "Planning", items: [
      ...(matches("plan backlog iterations") ? [navItemHtml({ id: "plan", label: "Plan", iconName: "calendar", kind: "plan", active: onTickets && state.view === "plan" })] : []),
      ...(matches("roadmap") ? [navItemHtml({ id: "roadmap", label: "Roadmap", iconName: "timeline", kind: "roadmap", active: onTickets && state.view === "roadmap" })] : []),
    ] },
    { name: "Knowledge", items: [
      ...(matches("knowledge base home") ? [navItemHtml({ id: "home", label: "Knowledge base", iconName: "book", kind: "kb-home", active: state.page === "kb" && state.kb.view === "home" })] : []),
      ...state.kbSpaces.filter((s) => s.kind === "docs" && matches(s.name)).map((s) => navItemHtml({ id: s.id, label: s.name, tile: s.key, count: s.pages, kind: "kb-space", active: state.page === "kb" && ["space", "page"].includes(state.kb.view) && state.kb.spaceId === s.id })),
      ...(matches("tools") ? [navItemHtml({ id: "tools", label: "Tools", iconName: "wrench", kind: "kb-tools", count: (state.kbSpaces.find((s) => s.kind === "tools") || {}).pages, active: state.page === "kb" && state.kb.view === "tools" || (state.page === "kb" && state.kb.view === "page" && state.pageData && state.pageData.page && state.pageData.page.page_type === "tool") })] : []),
      ...(matches("new page") ? [navItemHtml({ id: "kb-new", label: "New page", iconName: "plus", kind: "kb-new" })] : []),
    ] },
    { name: "Reports", items: [
      ...(matches("dashboards") ? [navItemHtml({ id: "dashboards", label: "Dashboards", iconName: "chart", kind: "dashboards", active: state.page === "dashboards" })] : []),
      ...(matches("summary") ? [navItemHtml({ id: "summary", label: "Summary", iconName: "layers", kind: "summary", active: onTickets && state.view === "summary" })] : []),
    ] },
    { name: "Manage", items: MANAGE_TABS.filter((t) => matches(t.label) || matches("manage")).map((t) => navItemHtml({ id: t.id, label: t.label, iconName: t.id === "tags" ? "tag" : "gear", kind: "manage", active: state.page === "manage" && state.manageTab === t.id })) },
    { name: "Help", items: [
      ...(matches("api reference") ? [navItemHtml({ id: "docs", label: "API reference", iconName: "docs", kind: "link", href: "/docs" })] : []),
      ...(matches("keyboard shortcuts") ? [navItemHtml({ id: "shortcuts", label: "Keyboard shortcuts", iconName: "help", kind: "shortcuts" })] : []),
    ] },
  ].filter((section) => section.items.length);
}

function renderNav() {
  const filter = state.navFilter.toLowerCase();
  const sections = navSections();
  byId("navSections").innerHTML = sections.length ? sections.map((section) => {
    const key = section.key || section.name;
    const collapsed = !filter && sectionCollapsed(key);
    return `<div class="nav-section${collapsed ? " collapsed" : ""}" data-section="${escapeHtml(key)}">
      <button type="button" class="nav-heading" aria-expanded="${!collapsed}"><span>${escapeHtml(section.name)}</span>${section.total === undefined ? "" : `<span class="section-count">${section.total}</span>`}<span class="chevron" aria-hidden="true"></span></button>
      <div class="nav-items">${section.items.join("")}</div></div>`;
  }).join("") : `<div class="nav-empty">Nothing matches</div>`;
  wireNav();
}

function ticketViewOr(view) { return ["summary", "board", "list"].includes(state.view) ? state.view : view; }

function toggleSection(name) {
  state.collapsedSections = sectionCollapsed(name) ? state.collapsedSections.filter((n) => n !== name) : [...state.collapsedSections, name];
  remember(STORAGE.sections, JSON.stringify(state.collapsedSections));
  renderNav();
}

function wireNav() {
  byId("navSections").querySelectorAll(".nav-heading").forEach((heading) => heading.addEventListener("click", () => toggleSection(heading.parentElement.dataset.section)));
  byId("navSections").querySelectorAll(".twisty[data-twisty]").forEach((twisty) => twisty.addEventListener("click", (event) => {
    event.stopPropagation();
    if (twisty.dataset.twisty.startsWith("areagroup:")) { toggleSection(twisty.dataset.twisty); return; }
    const id = Number(twisty.dataset.twisty);
    state.collapsedAreas = state.collapsedAreas.includes(id) ? state.collapsedAreas.filter((n) => n !== id) : [...state.collapsedAreas, id];
    remember(STORAGE.areas, JSON.stringify(state.collapsedAreas));
    renderNav();
  }));
  const actions = {
    work: (id) => go({ page: "tickets", project: "", nav: id, view: ticketViewOr("board") }),
    project: (id) => go({ page: "tickets", project: id, nav: "all", view: ticketViewOr("board") }),
    "area-group": (id) => toggleSection(id),
    area: (id) => go({ page: "area", areaId: Number(id) }),
    board: (id) => go({ page: "board", boardId: Number(id), view: ticketViewOr("board") }),
    plan: () => go({ page: "tickets", view: "plan", nav: "all" }),
    roadmap: () => go({ page: "tickets", view: "roadmap", nav: "all" }),
    dashboards: () => go({ page: "dashboards" }),
    summary: () => go({ page: "tickets", view: "summary" }),
    manage: (id) => go({ page: "manage", manageTab: id }),
    "kb-home": () => kbGo({ view: "home", pageId: null }),
    "kb-space": (id) => kbGo({ view: "space", spaceId: Number(id), pageId: null }),
    "kb-tools": () => kbGo({ view: "tools", pageId: null }),
    "kb-new": () => newPageDialog({}),
    "create-area": () => areaForm(null),
    "create-project": () => projectForm(null),
    shortcuts: () => byId("helpDialog").showModal(),
  };
  byId("navSections").querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => {
    const action = actions[item.dataset.kind];
    if (action) action(item.dataset.id);
  }));
}

function crumbLink(label, changes) { return `<a href="#" data-crumb='${escapeHtml(JSON.stringify(changes))}'>${escapeHtml(label)}</a>`; }

function pageHeader() {
  const project = state.projects.find((p) => p.key === state.project);
  const page = state.page;
  if (page === "area" && state.pageData) {
    const { area } = state.pageData;
    const parts = area.path.split(" / ");
    const trail = parts.slice(0, -1).map((name, index) => {
      const ancestor = state.areas.find((a) => a.path === parts.slice(0, index + 1).join(" / "));
      return ancestor ? crumbLink(name, { page: "area", areaId: ancestor.id }) : escapeHtml(name);
    });
    return { title: area.name, crumb: [escapeHtml(state.org.name), ...trail].join(" / "), actions: areaActions(), wire: wireAreaActions, tabs: [] };
  }
  if (page === "board" && state.pageData) {
    const { board } = state.pageData;
    return { title: board.name, crumb: `${crumbLink(board.area, { page: "area", areaId: board.area_id })}`, actions: boardActions(), wire: wireBoardActions,
      tabs: ["board", "list", "summary"].map((v) => ({ id: v, label: VIEW_LABELS[v], active: state.view === v, view: v })) };
  }
  if (page === "kb") return kbHeader();
  if (page === "dashboards") return { title: "Dashboards", crumb: "Reports", actions: dashboardActions(), wire: wireDashboardActions, tabs: [] };
  if (page === "manage") {
    return { title: "Administration", crumb: "Manage", actions: "", wire: null, tabs: MANAGE_TABS.map((t) => ({ id: t.id, label: t.label, active: state.manageTab === t.id, manage: t.id })) };
  }
  const work = WORK_ITEMS.find((i) => i.id === state.nav);
  const views = project ? TICKET_VIEWS : TICKET_VIEWS.filter((v) => v !== "plan");
  const title = state.view === "plan" ? "Plan" : state.view === "roadmap" ? "Roadmap" : project ? project.name : work.label;
  const actions = state.view === "plan" ? planActions() : project && !["plan", "roadmap"].includes(state.view) ? `<button id="projectEdit" class="ghost">Edit project</button>` : "";
  return { title, crumb: project ? `${crumbLink("Projects", { project: "", nav: "all" })} / ${escapeHtml(project.key)}` : "Work", actions,
    wire: () => { wirePlanActions(); const edit = byId("projectEdit"); if (edit) edit.addEventListener("click", () => projectForm(project)); },
    tabs: views.map((v) => ({ id: v, label: VIEW_LABELS[v], active: state.view === v, view: v })) };
}

function renderHeader() {
  const header = pageHeader();
  byId("pageTitle").textContent = header.title;
  document.title = `${header.docTitle || header.title} - LEDGER`;
  byId("breadcrumb").innerHTML = header.crumb;
  byId("breadcrumb").querySelectorAll("[data-crumb]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    go({ page: "tickets", ...JSON.parse(link.dataset.crumb) });
  }));
  byId("pageActions").innerHTML = header.actions;
  if (header.wire) header.wire();
  byId("tabs").innerHTML = header.tabs.map((tab) => `<button class="tab${tab.active ? " active" : ""}" role="tab" aria-selected="${tab.active}" ${tab.view ? `data-view="${tab.view}"` : `data-manage="${tab.manage}"`}>${escapeHtml(tab.label)}</button>`).join("");
  byId("tabs").querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    if (tab.dataset.manage) go({ manageTab: tab.dataset.manage });
    else go({ view: tab.dataset.view });
  }));
  const listing = ["tickets", "board"].includes(state.page) && ["board", "list"].includes(state.view);
  byId("filters").hidden = !listing;
  renderFilterBar();
  byId("sortField").value = state.sort.field;
  const direction = byId("sortDirection");
  direction.hidden = !state.sort.field;
  direction.textContent = state.sort.direction === "asc" ? "▲ Ascending" : "▼ Descending";
}

function cardHtml(ticket) {
  const labels = ticket.labels.slice(0, 2).map((l) => `<span class="chip tint" style="--tint:${tagColor(l)}">${escapeHtml(l)}</span>`).join("");
  const estimate = ticket.estimate === null || ticket.estimate === undefined ? "" : `<span class="points" title="Estimate">${formatNumber(ticket.estimate)}</span>`;
  return `<div class="card" draggable="true" tabindex="0" role="button" data-key="${ticket.key}" aria-label="${escapeHtml(ticket.key + " " + ticket.title)}">
    <div class="title">${escapeHtml(ticket.title)}</div>
    <div class="meta">${icon("type", ticket.type)}<span class="key">${ticket.key}</span>
      <span class="chip tint" style="--tint:${priorityColor(ticket.priority)}" title="Priority ${ticket.priority}">${PRIORITY_MARKS[ticket.priority]} ${ticket.priority}</span>
      <span class="chip tint" style="--tint:${typeColor(ticket.type)}">${escapeHtml(ticket.type)}</span>${labels}${estimate}${ticket.pinned ? `<span class="chip" title="Pinned to this board">pinned</span>` : ""}
      ${ticket.assignee ? `<span class="avatar" style="--tint:${nameColor(ticket.assignee)}" title="${escapeHtml(ticket.assignee)}">${initials(ticket.assignee)}</span>` : ""}</div></div>`;
}

function welcomeHtml() {
  return `<div class="empty"><h2>Welcome to LEDGER</h2><p>Start with a project: it holds your tickets under a short key such as APP.</p>
    <button class="primary" id="emptyCreate">Create your first project</button></div>`;
}

function orderedTickets(tickets) {
  return sortTickets(tickets, state.sort, { statuses: state.meta.statuses, priorities: state.meta.priorities });
}

function setSort(sort) {
  state.sort = sort;
  remember(STORAGE.sort, JSON.stringify(sort));
  render();
}

const COLUMN_FILTERS = { status: "status", priority: "priority", type: "type", assignee: "assignee" };

function listColumns() {
  const columns = SORT_FIELDS.map((field) => ({ ...field, sortable: true, filter: state.page === "tickets" ? COLUMN_FILTERS[field.id] || "" : "" }));
  if (state.page === "tickets") columns.splice(columns.findIndex((column) => column.id === "estimate"), 0, { id: "labels", label: "Tags", sortable: false, filter: "label" });
  return columns;
}

function columnHeaderHtml(column) {
  const sorted = column.sortable && state.sort.field === column.id;
  const arrow = sorted ? (state.sort.direction === "asc" ? " \u25B2" : " \u25BC") : "";
  const filtered = column.filter && state.filters[column.filter];
  const label = column.sortable
    ? `<button type="button" class="sort-header" data-sort="${column.id}">${column.label}${arrow}</button>`
    : `<button type="button" class="sort-header" data-filter-open="${column.filter}">${column.label}</button>`;
  const caret = column.sortable && column.filter
    ? `<button type="button" class="filter-caret${filtered ? " on" : ""}" data-filter-open="${column.filter}" aria-label="Filter ${column.label}" title="Filter ${column.label}">${filtered ? "\u25CF" : "\u25BE"}</button>` : "";
  return `<th aria-sort="${sorted ? (state.sort.direction === "asc" ? "ascending" : "descending") : "none"}">${label}${caret}</th>`;
}

function renderBoard(tickets = state.tickets, statuses = state.meta.statuses) {
  const columns = Object.fromEntries(statuses.map((s) => [s, []]));
  orderedTickets(tickets).forEach((t) => { if (columns[t.status]) columns[t.status].push(t); });
  byId("main").innerHTML = `<div class="board">${statuses.map((status) => `
    <section class="column" data-status="${status}" style="--status-color:${statusColor(status)}" aria-label="${STATUS_LABELS[status]}">
      <h3><span class="heading"><span class="dot" style="--tint:${statusColor(status)}"></span>${STATUS_LABELS[status]}</span><span class="count">${columns[status].length}</span></h3>
      <div class="cards">${columns[status].map(cardHtml).join("") || `<div class="column-empty">Nothing here</div>`}</div></section>`).join("")}</div>`;
  attachBoardEvents();
}

function renderList(tickets = state.tickets) {
  if (!tickets.length) { byId("main").innerHTML = `<div class="empty"><p>No tickets match. Press c to create one.</p></div>`; return; }
  byId("main").innerHTML = `<table class="list"><thead><tr>${listColumns().map(columnHeaderHtml).join("")}</tr></thead><tbody>
    ${orderedTickets(tickets).map((t) => `<tr data-key="${t.key}" tabindex="0" role="button"><td class="key">${t.key}</td><td>${escapeHtml(t.title)}</td>
      <td><span class="pill" style="--pill-color:${statusColor(t.status)}">${STATUS_LABELS[t.status]}</span></td>
      <td><span class="pill" style="--pill-color:${priorityColor(t.priority)}">${icon("priority", t.priority)} ${PRIORITY_MARKS[t.priority]} ${t.priority}</span></td>
      <td>${icon("type", t.type)} ${t.type}</td><td>${escapeHtml(t.assignee)}</td>${state.page === "tickets" ? `<td>${t.labels.slice(0, 3).map((l) => `<span class="chip tint" style="--tint:${tagColor(l)}">${escapeHtml(l)}</span>`).join(" ")}</td>` : ""}<td>${t.estimate === null || t.estimate === undefined ? "" : formatNumber(t.estimate)}</td>
      <td>${new Date(t.updated * 1000).toLocaleDateString()}</td></tr>`).join("")}
    </tbody></table>`;
  byId("main").querySelectorAll("tr[data-key]").forEach((row) => activateOnKey(row, () => openTicket(row.dataset.key)));
  byId("main").querySelectorAll(".sort-header[data-sort]").forEach((button) => button.addEventListener("click", () => setSort(nextSort(state.sort, button.dataset.sort))));
  byId("main").querySelectorAll("[data-filter-open]").forEach((button) => button.addEventListener("click", () => openColumnMenu(button.dataset.filterOpen, button)));
}

function barCard(title, counts, colorOf, labelOf = (v) => v) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const peak = Math.max(1, ...entries.map(([, n]) => n));
  const rows = entries.map(([name, count]) => `<div class="bar-row"><span class="name">${escapeHtml(labelOf(name))}</span>
    <span class="bar"><span style="--tint:${colorOf(name)}; width:${Math.round((count / peak) * 100)}%"></span></span><span class="value">${count}</span></div>`).join("");
  return `<div class="stat-card"><h3>${title}</h3>${rows || `<div class="stat-sub">No tickets</div>`}</div>`;
}

function renderSummary(stats) {
  if (!stats) { byId("main").innerHTML = `<div class="empty"><p>No figures yet.</p></div>`; return; }
  byId("main").innerHTML = `<div class="stat-grid">
    <div class="stat-card"><h3>Open work</h3><div class="stat-number">${stats.open}</div><div class="stat-sub">${stats.unassigned} unassigned</div></div>
    ${barCard("By status", stats.by_status, statusColor, (s) => STATUS_LABELS[s])}
    ${barCard("By priority", stats.by_priority, priorityColor)}
    ${barCard("By type", stats.by_type, typeColor)}
    ${barCard("By assignee", stats.by_assignee, nameColor)}</div>`;
}

function activateOnKey(element, action) {
  element.addEventListener("click", action);
  element.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); action(); } });
}

function updateProfileButton() {
  const button = byId("profileButton");
  button.textContent = actorName().slice(0, 2);
  button.style.setProperty("--tint", nameColor(actorName()));
  button.title = actorName();
}

function renderTicketsPage() {
  if (state.view === "plan") return renderPlan();
  if (state.view === "roadmap") return renderRoadmap();
  if (state.view === "summary") return renderSummary(state.stats);
  if (state.view === "board") return renderBoard();
  return renderList();
}

function renderBoardPage() {
  const { board } = state.pageData;
  if (state.view === "summary") return renderSummary(statsFrom(state.tickets));
  if (state.view === "list") return renderList(state.tickets);
  return renderBoard(state.tickets, board.statuses);
}

let renderedViewKey = "";

function viewKey() {
  return [state.page, state.view, state.project, state.areaId, state.boardId, state.manageTab, state.kb.view, state.kb.spaceId, state.kb.pageId].join("|");
}

function captureScroll() {
  const columns = {};
  document.querySelectorAll("#main .column").forEach((column) => { columns[column.dataset.status] = column.querySelector(".cards").scrollTop; });
  return { main: byId("main").scrollTop, nav: byId("navSections").scrollTop, columns };
}

function restoreScroll(saved) {
  byId("main").scrollTop = saved.main;
  byId("navSections").scrollTop = saved.nav;
  document.querySelectorAll("#main .column").forEach((column) => {
    if (saved.columns[column.dataset.status]) column.querySelector(".cards").scrollTop = saved.columns[column.dataset.status];
  });
}

function render() {
  const key = viewKey();
  const saved = key === renderedViewKey ? captureScroll() : null;
  renderNav();
  renderHeader();
  const searchLabel = state.page === "kb" ? "Search knowledge base" : "Search tickets";
  byId("searchBox").placeholder = searchLabel;
  byId("searchBox").setAttribute("aria-label", searchLabel);
  updateProfileButton();
  const noProjects = !state.projects.length;
  const needsProject = state.page === "tickets" && noProjects;
  if (needsProject) {
    byId("main").innerHTML = welcomeHtml();
    byId("emptyCreate").addEventListener("click", () => projectForm(null));
  } else if (state.page === "kb") renderKb();
  else if (state.page === "area") { renderAreaPage(); wireAreaActions(); }
  else if (state.page === "board") renderBoardPage();
  else if (state.page === "dashboards") renderDashboardsPage();
  else if (state.page === "manage") renderManage();
  else renderTicketsPage();
  const listing = ["board", "list"].includes(state.view) && ["tickets", "board"].includes(state.page);
  const open = state.tickets.filter((t) => !state.meta.closed_statuses.includes(t.status)).length;
  const truncated = state.total > state.tickets.length && state.page === "tickets";
  byId("summary").textContent = !listing ? "" : truncated ? `${state.tickets.length} of ${state.total} shown, narrow the filters` : `${state.tickets.length} shown, ${open} open`;
  byId("summary").classList.toggle("warn", truncated);
  if (saved) restoreScroll(saved);
  renderedViewKey = key;
}

function attachBoardEvents() {
  const main = byId("main");
  main.querySelectorAll(".card").forEach((card) => {
    activateOnKey(card, () => openTicket(card.dataset.key));
    card.addEventListener("dragstart", (event) => { event.dataTransfer.setData("text/plain", card.dataset.key); card.classList.add("dragging"); });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
  });
  main.querySelectorAll(".column").forEach((column) => {
    column.addEventListener("dragover", (event) => { event.preventDefault(); column.classList.add("drop-target"); });
    column.addEventListener("dragleave", () => column.classList.remove("drop-target"));
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("drop-target");
      const key = event.dataTransfer.getData("text/plain");
      if (!key) return;
      if (await guarded(() => api("PATCH", `/api/tickets/${key}`, { status: column.dataset.status }))) toast(`${key} moved to ${STATUS_LABELS[column.dataset.status]}`);
      refresh();
    });
  });
}

function optionList(values, current, labelOf = (v) => STATUS_LABELS[v] || v) {
  return values.map((v) => `<option value="${escapeHtml(v)}"${v === current ? " selected" : ""}>${escapeHtml(labelOf(v))}</option>`).join("");
}

function treeHtml(node, top = true) {
  const item = `<div class="node" tabindex="0" role="link" data-open="${node.key}"><span class="dot" style="--tint:${statusColor(node.status)}"></span><span class="key">${node.key}</span>
    <span class="title">${escapeHtml(node.title)}</span>${node.estimate === null || node.estimate === undefined ? "" : `<span class="points">${formatNumber(node.estimate)}</span>`}</div>`;
  const children = node.children.length ? `<ul>${node.children.map((c) => `<li>${treeHtml(c, false)}</li>`).join("")}</ul>` : "";
  return top ? `<ul class="tree"><li>${item}${children}</li></ul>` : item + children;
}

async function openTicket(key, scroll = true) {
  const ticket = await guarded(() => api("GET", `/api/tickets/${key}`));
  if (!ticket) { closeDrawer(); return; }
  const events = (await guarded(() => api("GET", `/api/tickets/${key}/events`))) || [];
  const iterations = (await guarded(() => api("GET", `/api/iterations?project=${ticket.project_key}`))) || [];
  const tree = ticket.children.length ? await guarded(() => api("GET", `/api/tickets/${key}/tree`)) : null;
  state.openKey = ticket.key;
  history.replaceState(null, "", "#" + ticket.key);
  const mentions = (await guarded(() => api("GET", `/api/kb/mentions?ticket=${ticket.key}`))) || [];
  const knowledgeHtml = mentions.length ? `<h4>Knowledge</h4>${mentions.map((p) => `<div class="rowlink" tabindex="0" role="link" data-kb-page-open="${p.id}"><span class="chip">${p.page_type === "tool" ? "tool" : "page"}</span><span>${escapeHtml(p.title)}</span></div>`).join("")}` : "";
  const progress = ticket.progress;
  const areaChoices = [{ value: "", label: "No area" }, ...state.areas.map((a) => ({ value: String(a.id), label: a.path }))];
  const iterationChoices = [{ value: "", label: "No iteration" }, ...iterations.map((i) => ({ value: String(i.id), label: `${i.name} (${i.state})` }))];
  const choice = (list, current) => list.map((o) => `<option value="${escapeHtml(o.value)}"${o.value === current ? " selected" : ""}>${escapeHtml(o.label)}</option>`).join("");
  const drawer = byId("drawer");
  drawer.innerHTML = `
    <button class="ghost close" id="drawerClose">Close <kbd>Esc</kbd></button>
    <div class="key">${ticket.key}${ticket.parent_key ? ` in <a href="#${ticket.parent_key}">${ticket.parent_key}</a>` : ""}</div>
    <h2 contenteditable="true" id="drawerTitle" spellcheck="false" role="textbox" aria-label="Title">${escapeHtml(ticket.title)}</h2>
    ${progress.total ? `<div class="progress-block"><div class="progress-line">${progressBar(progress.done, progress.total)}<span>${progress.done} of ${progress.total} sub-tickets done${progress.points ? `, ${formatNumber(progress.points_done)} of ${formatNumber(progress.points)} points` : ""}</span></div></div>` : ""}
    <div class="grid">
      <label for="f_status">Status</label><select id="f_status" data-field="status">${optionList(state.meta.statuses, ticket.status)}</select>
      <label for="f_priority">Priority</label><select id="f_priority" data-field="priority">${optionList(state.meta.priorities, ticket.priority)}</select>
      <label for="f_type">Type</label><select id="f_type" data-field="type">${optionList(state.meta.types, ticket.type)}</select>
      <label for="f_assignee">Assignee</label><input type="text" id="f_assignee" data-field="assignee" value="${escapeHtml(ticket.assignee)}">
      <label for="f_labels">Tags</label><input type="text" id="f_labels" data-field="labels" value="${escapeHtml(ticket.labels.join(", "))}" placeholder="comma separated">
      <label for="f_area">Area</label><select id="f_area" data-field="area">${choice(areaChoices, ticket.area_id ? String(ticket.area_id) : "")}</select>
      <label for="f_iteration">Iteration</label><select id="f_iteration" data-field="iteration">${choice(iterationChoices, ticket.iteration_id ? String(ticket.iteration_id) : "")}</select>
      <label for="f_estimate">Estimate</label><input type="number" id="f_estimate" data-field="estimate" min="0" step="any" value="${ticket.estimate === null ? "" : ticket.estimate}" placeholder="points">
      <label for="f_parent">Parent</label><input type="text" id="f_parent" data-field="parent_key" value="${escapeHtml(ticket.parent_key || "")}" placeholder="APP-1">
      <label for="f_start">Start</label><input type="text" id="f_start" data-field="start" value="${escapeHtml(ticket.start)}" placeholder="YYYY-MM-DD">
      <label for="f_due">Due</label><input type="text" id="f_due" data-field="due" value="${escapeHtml(ticket.due)}" placeholder="YYYY-MM-DD">
    </div>
    <h4>Description</h4>
    <textarea id="drawerBody" rows="6" aria-label="Description">${escapeHtml(ticket.body)}</textarea>
    ${knowledgeHtml}
    <h4>Sub-tickets</h4>
    ${tree ? treeHtml(tree) : `<div class="event">none</div>`}
    <div class="actions-row"><button id="subCreate">Add sub-ticket</button></div>
    <h4>Links</h4>
    ${ticket.links.map((l) => `<div class="rowlink" tabindex="0" role="link" data-open="${l.key}"><span class="chip">${l.direction === "out" ? l.kind : "is " + l.kind + " by"}</span><span class="key">${l.key}</span><span>${escapeHtml(l.title)}</span></div>`).join("") || `<div class="event">none</div>`}
    <div class="inline"><input type="text" id="linkTarget" placeholder="APP-2" aria-label="Ticket to link">
      <select id="linkKind" aria-label="Link kind">${state.meta.link_kinds.map((k) => `<option>${k}</option>`).join("")}</select><button id="linkAdd">Link</button></div>
    <h4>Comments</h4>
    ${ticket.comments.map((c) => `<div class="comment"><div class="who">${escapeHtml(c.author)}, ${new Date(c.created * 1000).toLocaleString()}</div>${escapeHtml(c.body)}</div>`).join("")}
    <textarea id="commentBox" rows="3" placeholder="Add a comment  (Ctrl+Enter to post)" aria-label="New comment"></textarea>
    <div class="inline"><button class="primary" id="commentPost">Comment</button><button class="ghost" id="ticketDelete">Delete ticket</button></div>
    <h4>History</h4>
    ${events.map((e) => `<div class="event">${new Date(e.created * 1000).toLocaleString()}  ${escapeHtml(e.actor)}  ${escapeHtml(e.field)}${e.field === "created" ? "" : `: ${escapeHtml(e.old || "-")} to ${escapeHtml(e.new || "-")}`}</div>`).join("")}`;
  drawer.hidden = false;
  if (scroll) drawer.scrollTop = 0;
  wireDrawer(ticket);
}

function wireDrawer(ticket) {
  const drawer = byId("drawer");
  const save = async (changes) => {
    const saved = await guarded(() => api("PATCH", `/api/tickets/${ticket.key}`, changes));
    if (saved) toast("Saved"); else openTicket(ticket.key, false);
    refresh({ redrawDrawer: false });
  };
  byId("drawerClose").addEventListener("click", closeDrawer);
  drawer.querySelectorAll("[data-field]").forEach((control) => control.addEventListener("change", () => save({ [control.dataset.field]: control.value })));
  const title = byId("drawerTitle");
  title.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); title.blur(); } });
  title.addEventListener("blur", () => { const text = title.textContent.trim(); if (text && text !== ticket.title) save({ title: text }); });
  byId("drawerBody").addEventListener("blur", (event) => { if (event.target.value !== ticket.body) save({ body: event.target.value }); });
  drawer.querySelectorAll("[data-open]").forEach((row) => activateOnKey(row, () => openTicket(row.dataset.open)));
  drawer.querySelectorAll("[data-kb-page-open]").forEach((row) => activateOnKey(row, () => { closeDrawer(); kbGo({ view: "page", pageId: Number(row.dataset.kbPageOpen) }); }));
  byId("subCreate").addEventListener("click", () => openNewDialog({ project: ticket.project_key, parent: ticket.key, area: ticket.area_id, iteration: ticket.iteration_id }));
  const postComment = async () => {
    const body = byId("commentBox").value.trim();
    if (body && await guarded(() => api("POST", `/api/tickets/${ticket.key}/comments`, { body }))) { toast("Comment added"); openTicket(ticket.key, false); refresh({ redrawDrawer: false }); }
  };
  byId("commentPost").addEventListener("click", postComment);
  byId("commentBox").addEventListener("keydown", (event) => { if (event.ctrlKey && event.key === "Enter") postComment(); });
  byId("linkAdd").addEventListener("click", async () => {
    const to = byId("linkTarget").value.trim();
    if (to && await guarded(() => api("POST", `/api/tickets/${ticket.key}/links`, { to, kind: byId("linkKind").value }))) { toast("Linked"); openTicket(ticket.key, false); }
  });
  byId("ticketDelete").addEventListener("click", async () => {
    if (!confirm(`Delete ${ticket.key}? This cannot be undone.`)) return;
    if (await guarded(() => api("DELETE", `/api/tickets/${ticket.key}`))) { closeDrawer(); toast(`${ticket.key} deleted`); refresh(); }
  });
}

function closeDrawer() {
  byId("drawer").hidden = true;
  state.openKey = null;
  history.replaceState(null, "", location.pathname);
}

const newTemplates = { list: [], applied: null };

async function loadNewDialogChoices(projectKey, chosenIteration = "", chosenTemplate = "") {
  const iterations = (await guarded(() => api("GET", `/api/iterations?project=${projectKey}`))) || [];
  setOptions(byId("newIteration"), [{ value: "", label: "None" }, ...iterations.filter((i) => i.state !== "done").map((i) => ({ value: String(i.id), label: i.name }))], chosenIteration);
  newTemplates.list = (await guarded(() => api("GET", `/api/templates?project=${projectKey}`))) || [];
  setOptions(byId("newTemplate"), [{ value: "", label: "No template" }, ...newTemplates.list.map((t) => ({ value: String(t.id), label: t.name }))], chosenTemplate);
}

function applyTemplateToDialog(templateId) {
  const template = newTemplates.list.find((t) => String(t.id) === String(templateId));
  if (!template) return;
  byId("newType").value = template.type;
  byId("newPriority").value = template.priority;
  byId("newStatus").value = template.status;
  if (template.title && (!byId("newTitle").value || byId("newTitle").dataset.fromTemplate)) { byId("newTitle").value = template.title; byId("newTitle").dataset.fromTemplate = "1"; }
  byId("newBody").value = template.body;
  byId("newLabels").value = template.labels.join(", ");
  byId("newEstimate").value = template.estimate === null ? "" : template.estimate;
  if (template.assignee) byId("newAssignee").value = template.assignee;
}

async function openNewDialog(prefill = {}) {
  if (!state.projects.length) { projectForm(null); return; }
  byId("newForm").reset();
  delete byId("newTitle").dataset.fromTemplate;
  fillSelect(byId("newProject"), state.projects.map((p) => p.key));
  byId("newProject").value = prefill.project || state.project || state.projects[0].key;
  setOptions(byId("newArea"), [{ value: "", label: "None" }, ...state.areas.map((a) => ({ value: String(a.id), label: a.path }))], prefill.area ? String(prefill.area) : "");
  byId("newType").value = "task";
  byId("newPriority").value = "medium";
  byId("newStatus").value = "backlog";
  byId("newParent").value = prefill.parent || "";
  await loadNewDialogChoices(byId("newProject").value, prefill.iteration ? String(prefill.iteration) : "");
  byId("newDialog").showModal();
  byId("newTitle").focus();
}

function setupDialogs() {
  byId("newForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(byId("newForm")).entries());
    const created = await guarded(() => api("POST", "/api/tickets", payload));
    if (created) { byId("newDialog").close(); toast(`Created ${created.key}`); refresh(); }
  });
  byId("newForm").addEventListener("keydown", (event) => { if (event.ctrlKey && event.key === "Enter") byId("newForm").requestSubmit(); });
  byId("newCancel").addEventListener("click", () => byId("newDialog").close());
  byId("newProject").addEventListener("change", () => loadNewDialogChoices(byId("newProject").value));
  byId("newTemplate").addEventListener("change", (event) => applyTemplateToDialog(event.target.value));
  byId("newTitle").addEventListener("input", (event) => { delete event.target.dataset.fromTemplate; });
  byId("helpClose").addEventListener("click", () => byId("helpDialog").close());
}

function applyTheme(theme) { document.documentElement.dataset.theme = theme; }

function setupTheme() {
  const stored = recall(STORAGE.theme, "");
  applyTheme(stored || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  byId("themeButton").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    remember(STORAGE.theme, next);
    applyTheme(next);
  });
}

const isNarrow = () => window.matchMedia(NARROW_QUERY).matches;

function toggleNav() {
  if (isNarrow()) {
    document.body.classList.toggle("nav-open");
    byId("scrim").hidden = !document.body.classList.contains("nav-open");
  } else {
    document.body.classList.toggle("nav-collapsed");
    remember(STORAGE.nav, document.body.classList.contains("nav-collapsed") ? "1" : "");
  }
}

function closeNavOnNarrow() {
  if (!isNarrow()) return;
  document.body.classList.remove("nav-open");
  byId("scrim").hidden = true;
}

function closeProfileMenu() {
  byId("profileMenu").hidden = true;
  byId("profileButton").setAttribute("aria-expanded", "false");
}

function anyDialogOpen() { return [...document.querySelectorAll("dialog")].some((d) => d.open); }
function isTyping() { return /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable; }

function setupControls() {
  byId("filterChips").addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.dataset.filterOpen) openColumnMenu(target.dataset.filterOpen, target);
    else if (target.dataset.filterToggle) applyFilters(toggledFilter(state.filters, "open"));
    else if (target.dataset.filterClear === "all") applyFilters(emptyFilters());
    else if (target.dataset.filterClear) applyFilters(clearedFilter(state.filters, target.dataset.filterClear));
  });
  document.addEventListener("click", (event) => { if (!event.target.closest("#columnMenu, [data-filter-open]")) closeColumnMenu(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeColumnMenu(); });
  byId("sortField").addEventListener("change", (event) => setSort(event.target.value ? { field: event.target.value, direction: defaultSortDirection(event.target.value) } : { field: "", direction: "asc" }));
  byId("sortDirection").addEventListener("click", () => setSort({ field: state.sort.field, direction: state.sort.direction === "asc" ? "desc" : "asc" }));
  byId("searchBox").addEventListener("input", () => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(() => { if (state.page === "kb") { kbSearchFromBox(byId("searchBox").value.trim()); return; } if (state.page !== "tickets") state.page = "tickets"; if (!["board", "list"].includes(state.view)) state.view = "list"; refresh(); }, SEARCH_DEBOUNCE_MS); });
  byId("navFilter").addEventListener("input", (event) => { state.navFilter = event.target.value.trim(); renderNav(); });
  byId("newButton").addEventListener("click", () => openNewDialog());
  byId("refreshButton").addEventListener("click", () => refresh());
  byId("helpButton").addEventListener("click", () => byId("helpDialog").showModal());
  byId("navToggle").addEventListener("click", toggleNav);
  byId("scrim").addEventListener("click", closeNavOnNarrow);
  byId("profileButton").addEventListener("click", (event) => {
    event.stopPropagation();
    const menu = byId("profileMenu");
    menu.hidden = !menu.hidden;
    byId("profileButton").setAttribute("aria-expanded", String(!menu.hidden));
    if (!menu.hidden) byId("actorInput").focus();
  });
  byId("profileMenu").addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", closeProfileMenu);
  byId("actorInput").addEventListener("input", updateProfileButton);
  byId("actorInput").addEventListener("change", () => { remember(STORAGE.actor, actorName()); if (state.nav === "mine") refresh(); });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openFinder(); return; }
    if (event.key === "Escape") {
      if (!byId("profileMenu").hidden) { closeProfileMenu(); return; }
      if (!byId("drawer").hidden && !anyDialogOpen()) closeDrawer();
    }
    if (isTyping() || event.ctrlKey || event.metaKey || anyDialogOpen()) return;
    if (kbShortcut(event)) return;
    const viewKeys = { s: "summary", b: "board", l: "list" };
    if (event.key === "c") { event.preventDefault(); openNewDialog(); }
    if (event.key === "/") { event.preventDefault(); byId("searchBox").focus(); }
    if (viewKeys[event.key]) go({ page: state.page === "board" ? "board" : "tickets", view: viewKeys[event.key] });
    if (event.key === "n") toggleNav();
    if (event.key === "r") refresh();
    if (event.key === "?") byId("helpDialog").showModal();
  });
  window.addEventListener("hashchange", () => { const key = location.hash.slice(1); if (KEY_PATTERN.test(key)) openTicket(key); });
  setInterval(() => { if (!document.hidden && !isTyping() && !anyDialogOpen() && !dashboardState.editing) refresh(); }, POLL_MS);
}

async function start() {
  fillIcons();
  setupTheme();
  byId("actorInput").value = recall(STORAGE.actor, DEFAULT_ACTOR);
  if ((recall(STORAGE.nav, "") && !isNarrow()) || isNarrow()) document.body.classList.add("nav-collapsed");
  try { state.collapsedSections = JSON.parse(recall(STORAGE.sections, "[]")); } catch (_) { state.collapsedSections = []; }
  try { state.collapsedAreas = JSON.parse(recall(STORAGE.areas, "[]")); } catch (_) { state.collapsedAreas = []; }
  try {
    const savedSort = JSON.parse(recall(STORAGE.sort, "null"));
    if (savedSort && SORT_FIELDS.some((field) => field.id === savedSort.field)) state.sort = { field: savedSort.field, direction: savedSort.direction === "desc" ? "desc" : "asc" };
  } catch (_) { state.sort = { field: "", direction: "asc" }; }
  state.meta = await api("GET", "/api/meta");
  fillSelect(byId("sortField"), SORT_FIELDS.map((field) => field.id), (id) => SORT_FIELDS.find((field) => field.id === id).label, "Default");
  fillSelect(byId("newType"), state.meta.types);
  fillSelect(byId("newPriority"), state.meta.priorities);
  fillSelect(byId("newStatus"), state.meta.statuses, (v) => STATUS_LABELS[v]);
  const overview = await api("GET", "/api/overview");
  Object.assign(state, { org: overview.organisation, areas: overview.areas, boards: overview.boards, projects: overview.projects });
  state.project = recall(STORAGE.project, "");
  if (state.project && !state.projects.some((p) => p.key === state.project)) state.project = "";
  state.view = recall(STORAGE.view, "board");
  if (!["summary", "board", "list", "plan", "roadmap"].includes(state.view)) state.view = "board";
  state.page = recall(STORAGE.page, "tickets");
  state.areaId = Number(recall(STORAGE.area, "")) || null;
  state.boardId = Number(recall(STORAGE.board, "")) || null;
  state.manageTab = recall(STORAGE.manage, "projects");
  state.dashboardId = Number(recall(STORAGE.dashboard, "")) || null;
  try { Object.assign(state.kb, JSON.parse(recall(STORAGE.kb, "{}"))); } catch (_) { state.kb.view = "home"; }
  state.kb.editing = false;
  state.kb.history = false;
  const wantedPage = Number(new URLSearchParams(location.search).get("page"));
  if (wantedPage) { state.page = "kb"; Object.assign(state.kb, { view: "page", pageId: wantedPage }); }
  if (state.page === "area" && !state.areas.some((a) => a.id === state.areaId)) state.page = "tickets";
  if (state.page === "board" && !state.boards.some((b) => b.id === state.boardId)) state.page = "tickets";
  if (state.page === "tickets" && !state.project && state.view === "plan") state.view = "board";
  setupControls();
  setupDialogs();
  await loadIcons();
  await refresh();
  const fromHash = location.hash.slice(1);
  if (KEY_PATTERN.test(fromHash)) openTicket(fromHash);
}

start().catch((error) => { byId("main").innerHTML = `<div class="empty"><p>Could not start: ${escapeHtml(error.message)}</p></div>`; });
