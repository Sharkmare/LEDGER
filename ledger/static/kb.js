"use strict";

const KB_RECENT_STORAGE = "ledger.kbRecent";
const KB_DRAFT_PREFIX = "ledger.kbDraft.";
const KB_LEVEL_SIZE = 200;
const KB_START_HERE_LIMIT = 30;
const KB_SEARCH_LIMIT = 50;
const KB_RECENT_LIMIT = 8;
const KB_AUTOSAVE_MS = 2000;
const KB_PREVIEW_DELAY_MS = 120;
const KB_FIND_DELAY_MS = 150;
const KB_TOOL_KINDS = { cli: "Command line", api: "API", library: "Library", service: "Service", script: "Script", app: "Application" };
const KB_TOOL_COLORS = { cli: "#4fd1c5", api: "#4cc2ff", library: "#b58cff", service: "#5fd38d", script: "#ffc24c", app: "#ff9a4c" };
const KB_LOCATIONS = { machine: "On this machine", external: "External" };
const KB_TOOL_STATUS_COLORS = { active: "#5fd38d", experimental: "#ffc24c", deprecated: "#ff7a7a" };

const kbLive = { editor: null, draftTimer: null, previewTimer: null, findTimer: null, titles: [], viewed: null };

function kbRecents() {
  try { return JSON.parse(recall(KB_RECENT_STORAGE, "[]")); } catch (_) { return []; }
}

function kbRemember(entry) {
  const next = [entry, ...kbRecents().filter((r) => !(r.kind === entry.kind && r.id === entry.id))].slice(0, KB_RECENT_LIMIT);
  remember(KB_RECENT_STORAGE, JSON.stringify(next));
}

const kbTree = { spaceId: null, levels: {} };

function kbExpanded(spaceId) {
  return kbParseExpanded(recall(kbExpandedKey(spaceId), "[]"));
}

function kbSaveExpanded(spaceId, ids) {
  remember(kbExpandedKey(spaceId), JSON.stringify(ids));
}

function kbExpand(spaceId, ids) {
  const open = kbExpanded(spaceId);
  const next = kbWithExpanded(open, ids);
  if (next.length !== open.length) kbSaveExpanded(spaceId, next);
}

function kbLevelUrl(spaceId, key, offset, limit) {
  return `/api/kb/spaces/${spaceId}/children?parent=${key === "root" ? "" : key}&offset=${offset}&limit=${limit}`;
}

async function loadKbLevel(spaceId, key, onError = (error) => toast(error.message, true)) {
  const loaded = kbTree.levels[key] ? kbTree.levels[key].items.length : 0;
  try {
    kbTree.levels[key] = await api("GET", kbLevelUrl(spaceId, key, 0, Math.max(KB_LEVEL_SIZE, loaded)));
    return true;
  } catch (error) { onError(error); return false; }
}

async function loadExpandedKbLevel(spaceId, id) {
  let rejected = false;
  await loadKbLevel(spaceId, String(id), (error) => { rejected = kbIsServerRejection(error); });
  if (rejected) kbSaveExpanded(spaceId, kbWithoutExpanded(kbExpanded(spaceId), id));
}

async function loadKbTree(spaceId, ancestorIds) {
  if (kbTree.spaceId !== spaceId) { kbTree.spaceId = spaceId; kbTree.levels = {}; }
  kbExpand(spaceId, ancestorIds);
  await Promise.all([loadKbLevel(spaceId, "root"), ...kbExpanded(spaceId).map((id) => loadExpandedKbLevel(spaceId, id))]);
}

async function showMoreKbLevel(key) {
  const level = kbTree.levels[key];
  const more = await guarded(() => api("GET", kbLevelUrl(kbTree.spaceId, key, level.items.length, KB_LEVEL_SIZE)));
  if (more) kbTree.levels[key] = { ...more, items: [...level.items, ...more.items] };
  renderKb();
}

function kbGo(partial) {
  return go({ page: "kb", kb: { ...state.kb, editing: false, history: false, ...partial } });
}

function kbContext(page) {
  return { ticket: (key) => state.projects.some((p) => key.startsWith(p.key + "-")), wiki: (page && page.wiki) || {} };
}

function copyText(text, message = "Copied") {
  const done = () => toast(message);
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => toast("Copy failed", true));
  else {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
    done();
  }
}

function spaceTile(space, size = 28) {
  const letters = space.kind === "tools" ? svg("wrench") : escapeHtml(space.key.slice(0, 2));
  return `<span class="space-tile" style="--tint:${space.color};width:${size}px;height:${size}px">${letters}</span>`;
}

function badgeHtml(page) {
  const badges = [];
  if (page.status === "draft") badges.push(`<span class="chip">draft</span>`);
  if (page.stale) badges.push(`<span class="chip tint" style="--tint:var(--priority-high)" title="Review date ${escapeHtml(page.review_by)}">needs review</span>`);
  return badges.join(" ");
}

function pageRow(page, withSpace = true) {
  const space = state.pageData && state.pageData.spaceMap ? state.pageData.spaceMap[page.space_id] : null;
  const tool = page.tool ? `<span class="chip tint" style="--tint:${KB_TOOL_COLORS[page.tool.kind] || "var(--muted)"}">${escapeHtml(page.tool.kind)}</span>` : "";
  return `<div class="kb-row" tabindex="0" role="link" data-kb-open="${page.id}">
    ${withSpace && space ? spaceTile(space, 22) : ""}<span class="title">${escapeHtml(page.title)}</span>${tool}${badgeHtml(page)}
    <span class="muted">${ago(page.updated)}</span></div>`;
}

function shelf(title, pages, empty) {
  return `<div class="section-title">${escapeHtml(title)}</div>${pages.length ? `<div class="kb-shelf">${pages.map((p) => pageRow(p)).join("")}</div>` : `<div class="empty-line">${escapeHtml(empty)}</div>`}`;
}

async function loadKb() {
  if (state.kb.view === "search" && !state.kb.query) state.kb.view = "home";
  const view = state.kb.view;
  const data = {};
  const overview = await guarded(() => api("GET", "/api/kb/overview"));
  data.overview = overview || { spaces: [], counts: {} };
  data.spaceMap = Object.fromEntries(data.overview.spaces.map((s) => [s.id, s]));
  if (view === "space" || view === "page") {
    const space = data.spaceMap[state.kb.spaceId] || data.overview.spaces.find((s) => s.kind === "docs") || null;
    if (space) {
      state.kb.spaceId = space.id;
      data.space = space;
      if (!(view === "page" && state.kb.pageId)) await loadKbTree(space.id, []);
    }
  }
  if (view === "page" && state.kb.pageId) {
    const first = kbLive.viewed !== state.kb.pageId;
    data.page = await guarded(() => api("GET", `/api/kb/pages/${state.kb.pageId}${first ? "?view=1" : ""}`));
    if (!data.page) { state.kb.view = "home"; state.kb.pageId = null; } else {
      const reveal = kbAncestorsToReveal(kbLive.viewed, state.kb.pageId, data.page.breadcrumbs.map((crumb) => crumb.id));
      kbLive.viewed = state.kb.pageId;
      data.space = data.spaceMap[data.page.space.id];
      await loadKbTree(data.page.space.id, reveal);
      state.kb.spaceId = data.page.space.id;
      kbRemember({ kind: data.page.page_type === "tool" ? "tool" : "page", id: data.page.id, title: data.page.title });
      if (state.kb.history) data.versions = (await guarded(() => api("GET", `/api/kb/pages/${data.page.id}/versions`))) || [];
    }
  }
  if (view === "search") {
    const parameters = new URLSearchParams({ q: state.kb.query, limit: String(KB_SEARCH_LIMIT) });
    if (state.kb.searchSpaceId && !state.kb.searchAll) parameters.set("space", state.kb.searchSpaceId);
    data.hits = (await guarded(() => api("GET", "/api/kb/search?" + parameters))) || [];
    data.space = data.spaceMap[state.kb.searchSpaceId] || null;
  }
  if (view === "tools") {
    const parameters = new URLSearchParams();
    for (const [name, value] of Object.entries({ kind: state.kb.toolKind, location: state.kb.toolLocation, q: state.kb.toolQuery })) if (value) parameters.set(name, value);
    data.tools = (await guarded(() => api("GET", "/api/kb/tools?" + parameters))) || [];
  }
  state.pageData = data;
}

function kbHeader() {
  const data = state.pageData || {};
  const view = state.kb.view;
  if (view === "search") return { title: "Search", crumb: crumbLink("Knowledge base", { page: "kb", kb: { ...state.kb, view: "home", query: "", back: null } }), actions: "", wire: null, tabs: [] };
  if (view === "tools") {
    return { title: "Tools", crumb: "Knowledge base", actions: `<button id="kbAddTool" class="primary">Add tool</button>`, wire: () => byId("kbAddTool").addEventListener("click", () => toolForm(null)), tabs: [] };
  }
  if (view === "page" && data.page) {
    const page = data.page;
    const trail = [crumbLink("Knowledge base", { page: "kb", kb: { ...state.kb, view: "home", pageId: null, editing: false } })];
    trail.push(page.page_type === "tool" ? crumbLink("Tools", { page: "kb", kb: { ...state.kb, view: "tools", editing: false } })
      : crumbLink(page.space.name, { page: "kb", kb: { ...state.kb, view: "space", spaceId: page.space.id, pageId: null, editing: false } }));
    page.breadcrumbs.forEach((c) => trail.push(crumbLink(c.title, { page: "kb", kb: { ...state.kb, view: "page", pageId: c.id, editing: false } })));
    return { title: "", docTitle: page.title, crumb: trail.join(" / "), actions: "", wire: null, tabs: [] };
  }
  if (view === "space" && data.space) {
    return { title: data.space.name, crumb: crumbLink("Knowledge base", { page: "kb", kb: { ...state.kb, view: "home" } }), actions: `<button id="kbSpaceNewPage" class="primary">New page</button><button id="kbSpaceEdit" class="ghost">Edit space</button>`,
      wire: () => { byId("kbSpaceNewPage").addEventListener("click", () => newPageDialog({ space: data.space.id })); byId("kbSpaceEdit").addEventListener("click", () => spaceForm(data.space)); }, tabs: [] };
  }
  return { title: "Knowledge base", crumb: "Knowledge", actions: `<button id="kbNewPage" class="primary">New page</button><button id="kbNewSpace" class="ghost">New space</button><button id="kbHomeTool" class="ghost">Add tool</button>`,
    wire: () => { byId("kbNewPage").addEventListener("click", () => newPageDialog({})); byId("kbNewSpace").addEventListener("click", () => spaceForm(null)); byId("kbHomeTool").addEventListener("click", () => toolForm(null)); }, tabs: [] };
}

function renderKb() {
  const view = state.kb.view;
  if (view === "search") return renderKbSearch();
  if (view === "tools") return renderTools();
  if (view === "page" && state.pageData.page) {
    if (state.kb.editing) return renderEditor();
    if (state.pageData.page.page_type === "tool") {
      byId("main").innerHTML = `<section class="kb-content" id="kbContent"></section>`;
      return renderToolPage(byId("kbContent"));
    }
    return renderKbLayout(renderPageRead);
  }
  if (view === "space" && state.pageData.space) return renderKbLayout(renderSpaceHome);
  return renderKbHome();
}

function wireKbLinks(root) {
  root.querySelectorAll("[data-kb-open]").forEach((element) => activateOnKey(element, () => kbGo({ view: "page", pageId: Number(element.dataset.kbOpen) })));
  root.querySelectorAll("a[data-kb-page]").forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); kbGo({ view: "page", pageId: Number(link.dataset.kbPage) }); }));
  root.querySelectorAll("a[data-kb-create]").forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); newPageDialog({ title: link.dataset.kbCreate, space: state.kb.spaceId }); }));
  root.querySelectorAll("a[data-ticket]").forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); openTicket(link.dataset.ticket); }));
  root.querySelectorAll("[data-copy-code]").forEach((button) => button.addEventListener("click", () => copyText(button.parentElement.querySelector("code").textContent, "Code copied")));
  root.querySelectorAll("a[data-anchor]").forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); const target = document.getElementById(link.dataset.anchor); if (target) target.scrollIntoView({ behavior: "smooth" }); }));
}

function renderKbSearch() {
  const { hits, space } = state.pageData;
  const scoped = space && !state.kb.searchAll;
  byId("main").innerHTML = `<div class="kb-doc kb-search-results"><h1>Results for \u201C${escapeHtml(state.kb.query)}\u201D${scoped ? ` in ${escapeHtml(space.name)}` : ""}</h1>
    ${space ? `<p><button type="button" class="ghost small" id="kbSearchScope">${scoped ? "Search all spaces" : `Search only ${escapeHtml(space.name)}`}</button></p>` : ""}
    ${hits.length ? `<div class="kb-hits">${hits.map(hitRowHtml).join("")}</div>` : `<p class="muted">Nothing matches. Try fewer or shorter words.</p>`}</div>`;
  wireKbLinks(byId("main"));
  const scope = byId("kbSearchScope");
  if (scope) scope.addEventListener("click", () => kbGo({ searchAll: !state.kb.searchAll }));
}

function hitRowHtml(hit) {
  return `<div class="kb-hit" tabindex="0" role="link" data-kb-open="${hit.id}"><span class="title">${escapeHtml(hit.title)}</span><span class="muted">${escapeHtml(hit.space ? hit.space.name : "")}</span>
    <span class="snippet">${snippetHtml(hit.snippet)}</span></div>`;
}

function kbSearchFromBox(text) {
  const next = kbSearchTransition(state.kb, text);
  if (next) kbGo(next);
}

function renderKbHome() {
  const { overview } = state.pageData;
  const spaces = overview.spaces;
  byId("main").innerHTML = `<div class="kb-home">
    <div class="kb-hero"><h2>What are you looking for?</h2>
      <div class="kb-search"><span data-icon-inline="search">${svg("search")}</span><input id="kbHomeSearch" type="search" placeholder="Search pages, tools and tickets" autocomplete="off" aria-label="Search the knowledge base"><kbd>Ctrl K</kbd></div>
      <div id="kbHomeResults" class="kb-results" hidden></div>
      <div class="kb-counts">${overview.counts.pages} pages, ${overview.counts.tools} tools${overview.counts.stale ? `, <a href="#" data-kb-stale>${overview.counts.stale} need review</a>` : ""}</div></div>
    <div class="section-title">Spaces</div>
    <div class="cards-grid">${spaces.map((space) => `<div class="panel-card clickable kb-space-card" tabindex="0" role="button" data-kb-space="${space.id}" data-kind="${space.kind}">
      <div class="kb-space-head">${spaceTile(space, 34)}<h3>${escapeHtml(space.name)}</h3></div><div class="muted">${escapeHtml(space.description) || "&nbsp;"}</div>
      <div class="facts"><span>${space.pages} ${space.kind === "tools" ? "tools" : "pages"}</span><span>${space.updated ? `updated ${ago(space.updated)}` : "empty"}</span></div></div>`).join("")}</div>
    ${overview.favourites.length ? shelf("Your favourites", overview.favourites, "") : ""}
    ${shelf("Recently updated", overview.recent, "Nothing yet. Create the first page.")}
    ${overview.needs_review.length ? shelf("Needs review", overview.needs_review, "") : ""}
    ${overview.drafts.length ? shelf("Drafts", overview.drafts, "") : ""}
    ${overview.popular.some((p) => p.views) ? shelf("Most read", overview.popular.filter((p) => p.views), "") : ""}</div>`;
  const main = byId("main");
  main.querySelectorAll("[data-kb-space]").forEach((card) => activateOnKey(card, () => {
    const space = state.pageData.spaceMap[card.dataset.kbSpace];
    kbGo(space.kind === "tools" ? { view: "tools" } : { view: "space", spaceId: space.id, pageId: null });
  }));
  const stale = main.querySelector("[data-kb-stale]");
  if (stale) stale.addEventListener("click", (event) => { event.preventDefault(); openFinder("review"); });
  wireKbLinks(main);
  const search = byId("kbHomeSearch");
  search.addEventListener("input", () => {
    clearTimeout(kbLive.findTimer);
    kbLive.findTimer = setTimeout(async () => {
      const text = search.value.trim();
      const box = byId("kbHomeResults");
      if (!text) { box.hidden = true; return; }
      const found = await guarded(() => api("GET", "/api/search?q=" + encodeURIComponent(text)));
      if (!found) return;
      box.hidden = false;
      box.innerHTML = findResultsHtml(found) || `<div class="empty-line">Nothing matches "${escapeHtml(text)}".</div>`;
      wireFindResults(box);
    }, KB_FIND_DELAY_MS);
  });
  search.addEventListener("keydown", (event) => { if (event.key === "Enter") { const first = byId("kbHomeResults").querySelector("[data-find]"); if (first) first.click(); } });
}

function snippetHtml(text) {
  return escapeHtml(text || "").replace(/\u0001/g, "<mark>").replace(/\u0002/g, "</mark>");
}

function findResultsHtml(found) {
  const section = (title, items, render) => (items.length ? `<div class="find-group"><div class="find-title">${title}</div>${items.map(render).join("")}</div>` : "");
  const pageItem = (p) => `<div class="find-item" tabindex="0" data-find="page" data-id="${p.id}"><span class="title">${escapeHtml(p.title)}</span><span class="snippet">${snippetHtml(p.snippet)}</span><span class="muted">${escapeHtml(p.space.name)}</span></div>`;
  return section("Pages", found.pages, pageItem) + section("Tools", found.tools, pageItem) +
    section("Tickets", found.tickets, (t) => `<div class="find-item" tabindex="0" data-find="ticket" data-id="${t.key}"><span class="key">${t.key}</span><span class="title">${escapeHtml(t.title)}</span><span class="pill" style="--pill-color:${statusColor(t.status)}">${STATUS_LABELS[t.status]}</span></div>`);
}

function wireFindResults(root, after = () => {}) {
  root.querySelectorAll("[data-find]").forEach((item) => activateOnKey(item, () => {
    after();
    if (item.dataset.find === "ticket") openTicket(item.dataset.id);
    else kbGo({ view: "page", pageId: Number(item.dataset.id) });
  }));
}

function treeNodeHtml(node, context) {
  const open = node.child_count > 0 && context.expanded.has(node.id);
  const level = open ? kbTree.levels[String(node.id)] : null;
  const children = level ? `<ul class="kb-children">${treeLevelHtml(String(node.id), level, context)}</ul>` : "";
  return `<div class="kb-node${node.id === context.activeId ? " active" : ""}" draggable="true" data-id="${node.id}" data-parent="${node.parent_id || ""}" data-position="${node.position}">
    <button type="button" class="twist${node.child_count ? "" : " empty"}" data-twist="${node.id}" aria-label="Expand or collapse" aria-expanded="${open}">${node.child_count ? (open ? "&#9662;" : "&#9656;") : ""}</button>
    <a class="node-title" tabindex="0" data-kb-open="${node.id}">${escapeHtml(node.title)}</a>${node.status === "draft" ? `<span class="chip">draft</span>` : ""}${node.child_count ? `<span class="node-count">${node.child_count}</span>` : ""}
    <button type="button" class="node-add" data-add-child="${node.id}" title="Add a sub-page" aria-label="Add a sub-page">+</button></div>${children}`;
}

function treeLevelHtml(key, level, context) {
  const rows = level.items.map((item) => `<li>${treeNodeHtml(item, context)}</li>`).join("");
  const remaining = level.total - level.items.length;
  const more = remaining > 0 ? `<li><button type="button" class="ghost small kb-more" data-more="${key}">Show ${Math.min(remaining, KB_LEVEL_SIZE)} more (${remaining} left)</button></li>` : "";
  return rows + more;
}

function renderKbLayout(renderContent) {
  const { space } = state.pageData;
  const previousBody = byId("kbTreeBody");
  const treeScroll = previousBody && previousBody.dataset.space === String(space.id) ? previousBody.scrollTop : 0;
  const context = { activeId: state.kb.view === "page" ? state.kb.pageId : null, expanded: new Set(kbExpanded(space.id)) };
  const rootLevel = kbTree.levels.root || { items: [], total: 0 };
  const spaces = state.pageData.overview.spaces.filter((s) => s.kind === "docs");
  byId("main").innerHTML = `<div class="kb-layout"><nav class="kb-tree" aria-label="Pages in ${escapeHtml(space.name)}">
      <div class="kb-tree-head">${spaceTile(space, 26)}<select id="kbSpaceSwitch" aria-label="Space">${spaces.map((s) => `<option value="${s.id}"${s.id === space.id ? " selected" : ""}>${escapeHtml(s.name)}</option>`).join("")}</select></div>
      <div class="kb-tree-actions"><button type="button" class="ghost small" id="kbTreeNew">New page</button></div>
      <div class="kb-tree-body" id="kbTreeBody" data-space="${space.id}">${rootLevel.items.length ? `<ul class="kb-roots">${treeLevelHtml("root", rootLevel, context)}</ul>` : `<div class="empty-line">No pages yet.</div>`}</div></nav>
    <section class="kb-content" id="kbContent"></section></div>`;
  const tool = state.pageData.overview.spaces.find((s) => s.kind === "tools");
  byId("kbSpaceSwitch").addEventListener("change", (event) => kbGo({ view: "space", spaceId: Number(event.target.value), pageId: null }));
  byId("kbTreeNew").addEventListener("click", () => newPageDialog({ space: space.id }));
  byId("kbTreeBody").scrollTop = treeScroll;
  wireTree(byId("kbTreeBody"), space);
  renderContent(byId("kbContent"));
  void tool;
}

function wireTree(container, space) {
  wireKbLinks(container);
  container.querySelectorAll("[data-twist]").forEach((button) => button.addEventListener("click", async () => {
    const id = Number(button.dataset.twist);
    const open = kbExpanded(space.id);
    const next = open.includes(id) ? kbWithoutExpanded(open, id) : [...open, id];
    kbSaveExpanded(space.id, next);
    if (next.includes(id) && !kbTree.levels[String(id)]) await loadKbLevel(kbTree.spaceId, String(id));
    renderKb();
  }));
  container.querySelectorAll("[data-more]").forEach((button) => button.addEventListener("click", () => showMoreKbLevel(button.dataset.more)));
  container.querySelectorAll("[data-add-child]").forEach((button) => button.addEventListener("click", () => newPageDialog({ space: space.id, parent: Number(button.dataset.addChild) })));
  const flat = Object.values(kbTree.levels).flatMap((level) => level.items);
  container.querySelectorAll(".kb-node").forEach((node) => {
    node.addEventListener("dragstart", (event) => { event.dataTransfer.setData("text/plain", node.dataset.id); node.classList.add("dragging"); });
    node.addEventListener("dragend", () => node.classList.remove("dragging"));
    node.addEventListener("dragover", (event) => {
      event.preventDefault();
      const box = node.getBoundingClientRect();
      const where = event.clientY < box.top + box.height * 0.28 ? "before" : event.clientY > box.bottom - box.height * 0.28 ? "after" : "inside";
      node.dataset.drop = where;
    });
    node.addEventListener("dragleave", () => { delete node.dataset.drop; });
    node.addEventListener("drop", async (event) => {
      event.preventDefault();
      const where = node.dataset.drop || "inside";
      delete node.dataset.drop;
      const dragged = Number(event.dataTransfer.getData("text/plain"));
      const target = flat.find((n) => n.id === Number(node.dataset.id));
      if (!dragged || !target || dragged === target.id) return;
      await moveInTree(flat, dragged, target, where);
    });
  });
}

async function moveInTree(flat, draggedId, target, where) {
  const plan = treeMovePlan(flat, draggedId, target, where);
  const dragged = await guarded(() => api("PATCH", `/api/kb/pages/${draggedId}`, { parent: plan.parent, position: plan.position }));
  if (!dragged) return;
  for (const sibling of plan.renumber) await guarded(() => api("PATCH", `/api/kb/pages/${sibling.id}`, { position: sibling.position }));
  toast("Moved");
  refresh();
}

function renderSpaceHome(container) {
  const { space } = state.pageData;
  const roots = kbTree.levels.root || { items: [], total: 0 };
  container.innerHTML = `<div class="kb-doc"><h1>${escapeHtml(space.name)}</h1>${space.description ? `<p class="page-intro">${escapeHtml(space.description)}</p>` : ""}
    ${roots.items.length ? `<div class="section-title">Start here</div><div class="kb-shelf">${roots.items.slice(0, KB_START_HERE_LIMIT).map(shelfRowHtml).join("")}</div>${roots.total > KB_START_HERE_LIMIT ? `<p class="muted">${roots.total - KB_START_HERE_LIMIT} more in the tree.</p>` : ""}` : `<div class="empty"><h2>This space is empty</h2><p>Pages you add appear in the tree on the left.</p><button class="primary" id="kbEmptyNew">Create the first page</button></div>`}</div>`;
  wireKbLinks(container);
  const empty = byId("kbEmptyNew");
  if (empty) empty.addEventListener("click", () => newPageDialog({ space: space.id }));
}

function reviewBadge(page) {
  if (page.verified_by && !page.stale) return `<span class="chip tint" style="--tint:var(--status-done)" title="Next review ${escapeHtml(page.review_by)}">verified by ${escapeHtml(page.verified_by)} ${ago(page.verified_at)}</span>`;
  if (page.stale) return `<span class="chip tint" style="--tint:var(--priority-high)">review was due ${escapeHtml(page.review_by)}</span>`;
  if (page.review_by) return `<span class="chip" title="Next review">review by ${escapeHtml(page.review_by)}</span>`;
  return "";
}

function tocHtml(headings) {
  const items = headings.filter((h) => h.level <= 3);
  if (items.length < 2) return "";
  return `<div class="kb-rail-block"><h4>On this page</h4><ul class="kb-toc">${items.map((h) => `<li style="padding-left:${(h.level - 1) * 12}px"><a href="#${h.id}" data-toc="${h.id}">${escapeHtml(h.text)}</a></li>`).join("")}</ul></div>`;
}

function pageActionsHtml(page) {
  return `<div class="kb-actions"><button type="button" class="primary" id="kbEdit">Edit <kbd>e</kbd></button>
    <button type="button" class="ghost" id="kbFav" title="Add to your favourites">${page.favourite ? "&#9733; Favourite" : "&#9734; Favourite"}</button>
    <button type="button" class="ghost" id="kbHistory">History (${page.version})</button>
    <button type="button" class="ghost" id="kbVerify" title="Confirm the page is still right">Verify</button>
    <button type="button" class="ghost" id="kbCopyLink">Copy link</button>
    <button type="button" class="ghost" id="kbMore">More</button></div>`;
}

function wirePageActions(page) {
  byId("kbEdit").addEventListener("click", () => startEditing());
  byId("kbFav").addEventListener("click", async () => { if (await guarded(() => api("POST", `/api/kb/pages/${page.id}/favourite`, {}))) refresh(); });
  byId("kbHistory").addEventListener("click", () => kbGo({ view: "page", pageId: page.id, history: true }));
  byId("kbVerify").addEventListener("click", () => openForm({
    title: `Verify ${page.title}`, intro: "Confirm the page is correct today and choose when it should be looked at again.",
    fields: [{ name: "days", label: "Review again in (days)", kind: "number", min: 1 }], values: { days: 90 }, submitLabel: "Verify",
    onSubmit: async (values) => { await api("POST", `/api/kb/pages/${page.id}/verify`, { days: Number(values.days) }); toast("Verified"); await refresh(); },
  }));
  byId("kbCopyLink").addEventListener("click", () => copyText(`${location.origin}${location.pathname}?page=${page.id}`, "Link copied"));
  byId("kbMore").addEventListener("click", () => openForm({
    title: `${page.title}`, intro: "Archived pages disappear from the tree and from search but keep their history.",
    fields: [{ name: "status", label: "Status", kind: "select", options: [{ value: "published", label: "Published" }, { value: "draft", label: "Draft" }, { value: "archived", label: "Archived" }] },
      { name: "review_by", label: "Review by", kind: "text", placeholder: "YYYY-MM-DD" }, { name: "labels", label: "Tags", kind: "text", help: "Comma separated" }],
    values: { status: page.status, review_by: page.review_by, labels: page.labels.join(", ") }, submitLabel: "Save",
    buttons: [{ label: "Delete page", danger: true, onClick: async (dialog) => {
      const cascade = page.children.length > 0;
      if (!confirm(cascade ? `Delete ${page.title} and its ${page.children.length} sub-pages? This cannot be undone.` : `Delete ${page.title}? This cannot be undone.`)) return;
      if (await guarded(() => api("DELETE", `/api/kb/pages/${page.id}${cascade ? "?cascade=1" : ""}`))) { dialog.close(); await kbGo({ view: "space", spaceId: page.space.id, pageId: null }); toast("Page deleted"); }
    } }],
    onSubmit: async (values) => {
      await api("PATCH", `/api/kb/pages/${page.id}`, { status: values.status, review_by: values.review_by, labels: splitList(values.labels) });
      await refresh();
    },
  }));
}

function helpfulHtml(page) {
  const voted = page.my_feedback;
  return `<div class="kb-helpful"><span>Was this page helpful?</span>
    <button type="button" class="${voted === true ? "primary" : "ghost"}" data-helpful="yes">Yes</button><button type="button" class="${voted === false ? "primary" : "ghost"}" data-helpful="no">No</button>
    <span class="muted">${page.helpful} found it helpful${page.unhelpful ? `, ${page.unhelpful} did not` : ""}</span></div>`;
}

function wireHelpful(page) {
  document.querySelectorAll("[data-helpful]").forEach((button) => button.addEventListener("click", () => {
    const helpful = button.dataset.helpful === "yes";
    if (helpful) { api("POST", `/api/kb/pages/${page.id}/feedback`, { helpful: true }).then(() => { toast("Thanks"); refresh(); }, (e) => toast(e.message, true)); return; }
    openForm({
      title: "What was missing?", intro: "A short note helps whoever maintains this page.", fields: [{ name: "comment", label: "Comment", kind: "textarea", rows: 3 }], values: {}, submitLabel: "Send",
      onSubmit: async (values) => { await api("POST", `/api/kb/pages/${page.id}/feedback`, { helpful: false, comment: values.comment }); toast("Thanks, noted"); await refresh(); },
    });
  }));
}

function siblingsNav(page) {
  const { previous, next } = page.siblings;
  return previous || next ? `<div class="kb-prevnext">${previous ? `<a data-kb-open="${previous.id}" tabindex="0">&#8592; ${escapeHtml(previous.title)}</a>` : "<span></span>"}${next ? `<a data-kb-open="${next.id}" tabindex="0">${escapeHtml(next.title)} &#8594;</a>` : ""}</div>` : "";
}

function shelfRowHtml(child) {
  return `<div class="kb-row" tabindex="0" role="link" data-kb-open="${child.id}"><span class="title">${escapeHtml(child.title)}</span>${child.status === "draft" ? `<span class="chip">draft</span>` : ""}</div>`;
}

function wireShelfMore(page) {
  const button = byId("kbShelfMore");
  if (!button) return;
  const shelf = byId("kbShelf");
  button.addEventListener("click", async () => {
    const shown = shelf.querySelectorAll(".kb-row").length;
    const more = await guarded(() => api("GET", kbLevelUrl(page.space.id, String(page.id), shown, KB_LEVEL_SIZE)));
    if (!more) return;
    shelf.insertAdjacentHTML("beforeend", more.items.map(shelfRowHtml).join(""));
    wireKbLinks(shelf);
    const total = shelf.querySelectorAll(".kb-row").length;
    byId("kbShelfCount").textContent = total < page.children_total ? ` (${total} of ${page.children_total})` : "";
    if (total >= page.children_total) button.remove();
  });
}

function renderPageRead(container) {
  const page = state.pageData.page;
  if (state.kb.history) return renderHistory(container);
  const rendered = renderMarkdown(page.body, kbContext(page));
  const rail = `${tocHtml(rendered.headings)}
    ${page.tickets.length ? `<div class="kb-rail-block"><h4>Tickets mentioned</h4>${page.tickets.map((t) => `<div class="rowlink" tabindex="0" role="link" data-ticket-open="${t.key}"><span class="dot" style="--tint:${statusColor(t.status)}"></span><span class="key">${t.key}</span><span class="title">${escapeHtml(t.title)}</span></div>`).join("")}</div>` : ""}
    ${page.backlinks.length ? `<div class="kb-rail-block"><h4>Linked from</h4>${page.backlinks.map((b) => `<div class="rowlink" tabindex="0" role="link" data-kb-open="${b.id}">${escapeHtml(b.title)}</div>`).join("")}</div>` : ""}
    <div class="kb-rail-block"><h4>Details</h4><div class="muted">Version ${page.version}, ${page.views} views</div><div class="muted">Created ${ago(page.created)}</div></div>`;
  container.innerHTML = `<div class="kb-doc-wrap"><article class="kb-doc">
      <h1>${escapeHtml(page.title)}</h1>
      ${languagesHtml(page)}
      <div class="kb-meta"><span class="muted">Updated ${ago(page.updated)} by ${escapeHtml(page.author || "unknown")}</span>${badgeHtml(page)} ${reviewBadge(page)}
        ${page.labels.map((l) => `<span class="chip tint" style="--tint:${tagColor(l)}">${escapeHtml(l)}</span>`).join("")}</div>
      ${pageActionsHtml(page)}
      <div class="md">${rendered.html || `<p class="muted">This page is empty. Press e to start writing.</p>`}</div>
      ${page.children.length ? `<div class="section-title">Sub-pages<span id="kbShelfCount">${page.children_total > page.children.length ? ` (${page.children.length} of ${page.children_total})` : ""}</span></div><div class="kb-shelf" id="kbShelf">${page.children.map(shelfRowHtml).join("")}</div>${page.children_total > page.children.length ? `<button type="button" class="ghost small" id="kbShelfMore">Show more</button>` : ""}` : ""}
      ${siblingsNav(page)}${helpfulHtml(page)}</article><aside class="kb-rail">${rail}</aside></div>`;
  wireKbLinks(container);
  wireShelfMore(page);
  wirePageActions(page);
  wireHelpful(page);
  container.querySelectorAll("[data-ticket-open]").forEach((row) => activateOnKey(row, () => openTicket(row.dataset.ticketOpen)));
  container.querySelectorAll("[data-toc]").forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); const target = document.getElementById(link.dataset.toc); if (target) target.scrollIntoView({ behavior: "smooth" }); }));
}

function languagesHtml(page) {
  if (!page.languages.length) return "";
  const entries = page.languages.map((entry) => entry.current
    ? `<span class="chip current" aria-current="true">${escapeHtml(entry.locale || "base")}</span>`
    : `<a href="#" class="chip" data-kb-page="${entry.id}" title="${escapeHtml(entry.title)}">${escapeHtml(entry.locale || "base")}</a>`);
  return `<nav class="kb-languages" aria-label="Languages">${entries.join("")}</nav>`;
}

async function startEditing() {
  await loadTitles();
  state.kb.editing = true;
  kbLive.editor = null;
  render();
}

function draftKey(page) { return KB_DRAFT_PREFIX + page.id; }

function renderEditor() {
  const page = state.pageData.page;
  const draftText = recall(draftKey(page), "");
  let draft = null;
  try { draft = draftText ? JSON.parse(draftText) : null; } catch (_) { draft = null; }
  const usable = draft && (draft.body !== page.body || draft.title !== page.title);
  const currentParent = page.breadcrumbs.length ? page.breadcrumbs[page.breadcrumbs.length - 1] : null;
  byId("main").innerHTML = `<div class="kb-editor">
    <div class="kb-editor-head"><input id="kbTitle" class="kb-title-input" value="${escapeHtml(page.title)}" aria-label="Page title" maxlength="200" autocomplete="off">
      <div class="kb-editor-actions"><input id="kbComment" placeholder="What changed? (optional)" aria-label="What changed" autocomplete="off">
        <button type="button" class="primary" id="kbSave">${page.status === "draft" ? "Publish" : "Save"} <kbd>Ctrl S</kbd></button><button type="button" class="ghost" id="kbCancel">Cancel <kbd>Esc</kbd></button></div></div>
    ${usable ? `<div class="kb-draft-banner">You have unsaved changes from ${ago(draft.at / 1000)}. <button type="button" class="ghost small" id="kbRestoreDraft">Restore them</button> <button type="button" class="ghost small" id="kbDiscardDraft">Discard</button></div>` : ""}
    <div class="kb-toolbar" role="toolbar" aria-label="Formatting">${[
      ["h2", "H2", "Heading"], ["h3", "H3", "Subheading"], ["bold", "B", "Bold (Ctrl B)"], ["italic", "I", "Italic (Ctrl I)"], ["code", "&lt;/&gt;", "Code"], ["link", "Link", "Link (Ctrl L)"],
      ["ul", "List", "Bulleted list"], ["ol", "1.", "Numbered list"], ["task", "Task", "Task list"], ["quote", "Quote", "Quote"], ["table", "Table", "Table"], ["fence", "Block", "Code block"], ["callout", "Note", "Callout"], ["wiki", "[[ ]]", "Link to another page"],
    ].map(([id, label, title]) => `<button type="button" data-format="${id}" title="${title}" aria-label="${title}">${label}</button>`).join("")}<span class="grow"></span><span class="muted" id="kbCount"></span></div>
    <div class="kb-split"><div class="kb-write"><textarea id="kbBody" spellcheck="true" aria-label="Page text">${escapeHtml(page.body)}</textarea><div id="kbSuggest" class="kb-suggest" hidden></div></div>
      <div class="kb-preview md" id="kbPreview"></div></div>
    <div class="kb-editor-foot"><label>Tags <input id="kbLabels" value="${escapeHtml(page.labels.join(", "))}" placeholder="comma separated" autocomplete="off"></label>
      <label>Sub-page of <input id="kbParentFind" placeholder="Find a parent" autocomplete="off"><select id="kbParent"><option value="">Top level</option>${currentParent ? `<option value="${currentParent.id}" selected>${escapeHtml(currentParent.title)}</option>` : ""}</select></label>
      <label>Review in days <input id="kbReview" type="number" min="1" placeholder="${page.review_by ? "keep" : "none"}"></label>
      ${page.status === "draft" ? "" : `<label>Status <select id="kbStatus"><option value="published"${page.status === "published" ? " selected" : ""}>Published</option><option value="draft">Draft</option></select></label>`}</div></div>`;
  wireEditor(page, draft);
}

function editorSnapshot() {
  return { title: byId("kbTitle").value, body: byId("kbBody").value, at: Date.now() };
}

function wireEditor(page, draft) {
  const body = byId("kbBody");
  const preview = byId("kbPreview");
  let dirty = false;
  const update = () => {
    preview.innerHTML = renderMarkdown(body.value, { ...kbContext(page), wiki: wikiMap(body.value, kbLive.titles) }).html;
    byId("kbCount").textContent = `${body.value.length} characters`;
    wireKbLinks(preview);
  };
  const touch = () => {
    dirty = true;
    clearTimeout(kbLive.previewTimer);
    kbLive.previewTimer = setTimeout(update, KB_PREVIEW_DELAY_MS);
    clearTimeout(kbLive.draftTimer);
    kbLive.draftTimer = setTimeout(() => remember(draftKey(page), JSON.stringify(editorSnapshot())), KB_AUTOSAVE_MS);
  };
  const leave = (message) => {
    clearTimeout(kbLive.draftTimer);
    clearTimeout(kbLive.previewTimer);
    state.kb.editing = false;
    if (message) toast(message);
    refresh();
  };
  const save = async () => {
    const changes = { title: byId("kbTitle").value, body: body.value, labels: splitList(byId("kbLabels").value), comment: byId("kbComment").value };
    const parent = byId("kbParent").value;
    changes.parent = parent === "" ? "" : Number(parent);
    const review = byId("kbReview").value;
    if (review) changes.review_by = new Date(Date.now() + Number(review) * 86400000).toISOString().slice(0, 10);
    const status = byId("kbStatus");
    changes.status = page.status === "draft" ? "published" : status.value;
    const saved = await guarded(() => api("PATCH", `/api/kb/pages/${page.id}`, changes));
    if (!saved) return;
    try { localStorage.removeItem(draftKey(page)); } catch (_) { return; }
    leave(page.status === "draft" ? "Published" : "Saved");
  };
  const cancel = () => {
    if (dirty && !confirm("Leave without saving? Your draft is kept in this browser.")) return;
    leave();
  };
  update();
  body.focus();
  body.addEventListener("input", () => { touch(); suggestWikiLinks(body); });
  byId("kbTitle").addEventListener("input", touch);
  byId("kbSave").addEventListener("click", save);
  byId("kbParentFind").addEventListener("input", (event) => {
    clearTimeout(kbLive.findTimer);
    kbLive.findTimer = setTimeout(async () => {
      const text = event.target.value.trim();
      if (!text) return;
      const hits = (await guarded(() => api("GET", `/api/kb/search?q=${encodeURIComponent(text)}&space=${page.space.id}&type=article&limit=15`))) || [];
      const select = byId("kbParent");
      const chosen = select.options[select.selectedIndex];
      const kept = chosen && chosen.value ? [{ id: chosen.value, title: chosen.textContent }] : [];
      const options = [...kept, ...hits.filter((hit) => hit.id !== page.id && !kept.some((k) => Number(k.id) === hit.id))];
      select.innerHTML = `<option value="">Top level</option>` + options.map((hit) => `<option value="${hit.id}"${kept.length && Number(kept[0].id) === hit.id ? " selected" : ""}>${escapeHtml(hit.title)}</option>`).join("");
    }, 250);
  });
  byId("kbCancel").addEventListener("click", cancel);
  const restore = byId("kbRestoreDraft");
  if (restore) restore.addEventListener("click", () => { byId("kbTitle").value = draft.title; body.value = draft.body; update(); dirty = true; byId("kbRestoreDraft").closest(".kb-draft-banner").remove(); });
  const discard = byId("kbDiscardDraft");
  if (discard) discard.addEventListener("click", () => { try { localStorage.removeItem(draftKey(page)); } catch (_) { return; } discard.closest(".kb-draft-banner").remove(); });
  document.querySelectorAll("[data-format]").forEach((button) => button.addEventListener("click", () => { applyFormat(body, button.dataset.format); touch(); body.focus(); }));
  kbLive.editor = { save, cancel, body };
  body.addEventListener("keydown", (event) => handleEditorKeys(event, body, save, cancel));
  byId("kbTitle").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); body.focus(); } handleEditorKeys(event, body, save, cancel, true); });
  byId("kbComment").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); save(); } });
}

function handleEditorKeys(event, body, save, cancel, fromTitle = false) {
  const suggest = byId("kbSuggest");
  if (!fromTitle && suggest && !suggest.hidden) {
    const items = [...suggest.querySelectorAll("[data-suggest]")];
    const active = items.findIndex((i) => i.classList.contains("active"));
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); const next = (active + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length; items.forEach((i, n) => i.classList.toggle("active", n === next)); return; }
    if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); insertSuggestion(body, items[Math.max(active, 0)].dataset.suggest); return; }
    if (event.key === "Escape") { event.preventDefault(); suggest.hidden = true; return; }
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save(); return; }
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); save(); return; }
  if (event.key === "Escape") { event.preventDefault(); cancel(); return; }
  if (fromTitle) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") { event.preventDefault(); applyFormat(body, "bold"); body.dispatchEvent(new Event("input")); return; }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "i") { event.preventDefault(); applyFormat(body, "italic"); body.dispatchEvent(new Event("input")); return; }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "l") { event.preventDefault(); applyFormat(body, "link"); body.dispatchEvent(new Event("input")); return; }
  if (event.key === "Tab" && !event.shiftKey) { event.preventDefault(); document.execCommand("insertText", false, "  "); return; }
  if (event.key === "Enter") continueList(event, body);
}

function applyEdit(body, edit) {
  body.setSelectionRange(edit.from, edit.to);
  document.execCommand("insertText", false, edit.text);
  if (edit.caretStart !== undefined) body.setSelectionRange(edit.caretStart, edit.caretEnd);
}

function continueList(event, body) {
  const edit = listContinuation(body.value, body.selectionStart, body.selectionEnd);
  if (!edit) return;
  event.preventDefault();
  applyEdit(body, edit);
}

function applyFormat(body, kind) {
  const edit = formatEdit(body.value, body.selectionStart, body.selectionEnd, kind);
  if (edit) applyEdit(body, edit);
}

function suggestWikiLinks(body) {
  const box = byId("kbSuggest");
  const before = body.value.slice(0, body.selectionStart);
  const query = openWikiQuery(before);
  if (query === null) { box.hidden = true; return; }
  const found = wikiSuggestions(kbLive.titles, query);
  if (!found.length) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = found.map((t, i) => `<div class="suggest-item${i === 0 ? " active" : ""}" data-suggest="${escapeHtml(t.title)}">${escapeHtml(t.title)} <span class="muted">${escapeHtml(t.space)}</span></div>`).join("");
  box.querySelectorAll("[data-suggest]").forEach((item) => item.addEventListener("mousedown", (event) => { event.preventDefault(); insertSuggestion(body, item.dataset.suggest); }));
}

function insertSuggestion(body, title) {
  const before = body.value.slice(0, body.selectionStart);
  const query = openWikiQuery(before);
  if (query === null) return;
  body.setSelectionRange(body.selectionStart - query.length, body.selectionStart);
  document.execCommand("insertText", false, `${title}]]`);
  byId("kbSuggest").hidden = true;
  body.dispatchEvent(new Event("input"));
}

async function loadTitles() {
  const pages = (await guarded(() => api("GET", "/api/kb/pages?limit=1000&order=title"))) || [];
  const spaces = state.pageData && state.pageData.spaceMap ? state.pageData.spaceMap : {};
  kbLive.titles = pages.filter((p) => p.page_type === "article").map((p) => ({ id: p.id, title: p.title, space: (spaces[p.space_id] || {}).name || "" }));
}

function renderHistory(container) {
  const { page, versions } = state.pageData;
  container.innerHTML = `<div class="kb-doc"><h1>History of ${escapeHtml(page.title)}</h1>
    <div class="kb-actions"><button type="button" class="ghost" id="kbBackToPage">Back to the page</button></div>
    <div class="kb-history"><div class="kb-versions">${versions.map((v) => `<div class="kb-version" tabindex="0" role="button" data-version="${v.version}"><strong>v${v.version}</strong>
        <span>${escapeHtml(v.author || "unknown")}</span><span class="muted">${ago(v.created)}</span><span class="muted">${escapeHtml(v.comment) || "no comment"}</span></div>`).join("")}</div>
      <div class="kb-diff" id="kbDiff"><div class="empty-line">Pick a version to compare it with the one before.</div></div></div></div>`;
  byId("kbBackToPage").addEventListener("click", () => kbGo({ view: "page", pageId: page.id }));
  const show = async (version) => {
    container.querySelectorAll(".kb-version").forEach((e) => e.classList.toggle("active", Number(e.dataset.version) === version));
    const index = versions.findIndex((v) => v.version === version);
    const older = versions[index + 1];
    const box = byId("kbDiff");
    if (!older) { box.innerHTML = `<div class="empty-line">This is the first version.</div>${version !== page.version ? `<button type="button" class="ghost" data-restore="${version}">Restore this version</button>` : ""}`; wireRestore(box, page); return; }
    const diff = await guarded(() => api("GET", `/api/kb/pages/${page.id}/diff?from=${older.version}&to=${version}`));
    if (!diff) return;
    box.innerHTML = `<div class="kb-diff-head"><strong>v${diff.from} to v${diff.to}</strong> <span class="diff-add">+${diff.added}</span> <span class="diff-del">-${diff.removed}</span>${diff.title_changed ? ` <span class="chip">title changed</span>` : ""}
      ${version !== page.version ? `<button type="button" class="ghost small" data-restore="${version}">Restore v${version}</button>` : ""}</div>
      <pre class="kb-diff-lines">${diff.lines.map((l) => `<div class="diff-line ${l.op}"><span class="mark">${l.op === "insert" ? "+" : l.op === "delete" ? "-" : " "}</span>${escapeHtml(l.text) || "&nbsp;"}</div>`).join("")}</pre>`;
    wireRestore(box, page);
  };
  container.querySelectorAll(".kb-version").forEach((element) => activateOnKey(element, () => show(Number(element.dataset.version))));
  if (versions.length) show(versions[0].version);
}

function wireRestore(box, page) {
  box.querySelectorAll("[data-restore]").forEach((button) => button.addEventListener("click", async () => {
    if (!confirm(`Restore version ${button.dataset.restore}? It becomes a new version.`)) return;
    if (await guarded(() => api("POST", `/api/kb/pages/${page.id}/restore`, { version: Number(button.dataset.restore) }))) { toast("Restored"); kbGo({ view: "page", pageId: page.id }); }
  }));
}

function newPageDialog(prefill) {
  const spaces = state.pageData && state.pageData.overview ? state.pageData.overview.spaces.filter((s) => s.kind === "docs") : [];
  if (!spaces.length) { toast("Create a space first", true); spaceForm(null); return; }
  api("GET", "/api/kb/templates").then((templates) => {
    let chosen = "blank";
    openForm({
      title: "New page", wide: true,
      fields: [{ name: "title", label: "Title", kind: "text", required: true, row: "a" }, { name: "space", label: "Space", kind: "select", row: "a", options: spaces.map((s) => ({ value: String(s.id), label: s.name })) }],
      values: { title: prefill.title || "", space: String(prefill.space || state.kb.spaceId || spaces[0].id) }, submitLabel: "Create and start writing",
      extra: (container) => {
        container.innerHTML = `<h3 class="group-title">Start from</h3><div class="kb-templates">${templates.map((t) => `<div class="kb-template${t.id === chosen ? " active" : ""}" tabindex="0" role="button" data-template="${t.id}"><strong>${escapeHtml(t.name)}</strong><span class="muted">${escapeHtml(t.description)}</span></div>`).join("")}</div>`;
        container.querySelectorAll("[data-template]").forEach((card) => activateOnKey(card, () => { chosen = card.dataset.template; container.querySelectorAll(".kb-template").forEach((c) => c.classList.toggle("active", c === card)); }));
      },
      onSubmit: async (values) => {
        const created = await api("POST", "/api/kb/pages", { space: values.space, title: values.title, template: chosen === "blank" ? "" : chosen, parent: prefill.parent || null, status: "draft" });
        await loadTitles();
        state.kb = { ...state.kb, view: "page", spaceId: created.space.id, pageId: created.id, editing: true, history: false };
        state.page = "kb";
        await refresh();
      },
    });
  }, (error) => toast(error.message, true));
}

function spaceForm(existing) {
  openForm({
    title: existing ? `Edit space ${existing.name}` : "New space", intro: existing ? "" : "A space holds a tree of pages about one subject, for example a product or a team.",
    fields: [{ name: "key", label: "Key", kind: "text", required: true, disabled: !!existing, row: "a", placeholder: "ENG" }, { name: "name", label: "Name", kind: "text", required: true, row: "a" },
      { name: "description", label: "Description", kind: "textarea", rows: 3 }, { name: "color", label: "Colour", kind: "color", help: "Leave empty to pick one for you" }],
    values: existing || {}, submitLabel: existing ? "Save" : "Create",
    buttons: existing && existing.kind === "docs" ? [{ label: "Delete", danger: true, onClick: async (dialog) => {
      if (!confirm(`Delete the space ${existing.name}? It must be empty.`)) return;
      if (await guarded(() => api("DELETE", `/api/kb/spaces/${existing.id}`))) { dialog.close(); await kbGo({ view: "home" }); }
    } }] : [],
    onSubmit: async (values) => {
      if (existing) await api("PATCH", `/api/kb/spaces/${existing.id}`, { name: values.name, description: values.description, color: values.color || existing.color });
      else { const created = await api("POST", "/api/kb/spaces", { key: values.key, name: values.name, description: values.description, color: values.color }); state.kb = { ...state.kb, view: "space", spaceId: created.id, pageId: null }; }
      await refresh();
    },
  });
}

function toolMetaFromValues(values) {
  const commands = String(values.commands || "").split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name, summary, usage] = line.split("|").map((part) => part.trim());
    return { name, summary: summary || "", usage: usage || "" };
  });
  const source = values.spec_source;
  const openapi = { source };
  if (source === "url") openapi.url = values.spec_url;
  if (source === "file") openapi.path = values.spec_path;
  if (source === "inline") { try { openapi.spec = JSON.parse(values.spec_json); } catch (_) { throw new Error("The pasted OpenAPI description is not valid JSON. Use a file or an address for YAML."); } }
  return { kind: values.kind, location: values.location, invoke: values.invoke, path: values.path, url: values.url, version: values.version, owner: values.owner,
    tool_status: values.tool_status, docs: values.docs, commands, openapi };
}

function toolForm(existing) {
  const meta = existing ? existing.meta : { kind: "cli", location: "machine", tool_status: "active", commands: [], openapi: { source: "" } };
  const openapi = meta.openapi || { source: "" };
  openForm({
    title: existing ? `Edit tool ${existing.title}` : "Add a tool", wide: true,
    intro: "Describe what the tool is and how to use it. Add an OpenAPI description and the tool page shows every endpoint with a try-it panel.",
    fields: [
      { name: "title", label: "Name", kind: "text", required: true, row: "a" },
      { name: "kind", label: "Kind", kind: "select", row: "a", options: Object.entries(KB_TOOL_KINDS).map(([value, label]) => ({ value, label })) },
      { name: "location", label: "Where it lives", kind: "select", row: "b", options: Object.entries(KB_LOCATIONS).map(([value, label]) => ({ value, label })) },
      { name: "tool_status", label: "Status", kind: "select", row: "b", options: [{ value: "active", label: "Active" }, { value: "experimental", label: "Experimental" }, { value: "deprecated", label: "Deprecated" }] },
      { name: "invoke", label: "How to run it", kind: "text", placeholder: "packer build FILE" },
      { name: "path", label: "Path on this machine", kind: "text", row: "c", placeholder: "C:/tools/packer.exe" },
      { name: "url", label: "Address", kind: "text", row: "c", placeholder: "https://api.example.com" },
      { name: "version", label: "Version", kind: "text", row: "d" }, { name: "owner", label: "Owner", kind: "text", row: "d" },
      { name: "docs", label: "Documentation link", kind: "text" },
      { name: "labels", label: "Tags", kind: "text", help: "Comma separated" },
      { group: "Commands" },
      { name: "commands", label: "One per line: name | what it does | usage", kind: "textarea", rows: 4, placeholder: "build | Build the image | packer build FILE" },
      { group: "OpenAPI description" },
      { name: "spec_source", label: "Where the description comes from", kind: "select", options: [{ value: "", label: "None" }, { value: "url", label: "An address (fetched and cached)" }, { value: "file", label: "A file on this machine (.json, .yaml, .yml)" }, { value: "inline", label: "Pasted JSON" }] },
      { name: "spec_url", label: "Address of the description", kind: "text", row: "e", placeholder: "https://api.example.com/openapi.json" },
      { name: "spec_path", label: "File path", kind: "text", row: "e", placeholder: "C:/tools/api/openapi.yaml" },
      { name: "spec_json", label: "Pasted JSON", kind: "textarea", rows: 4 },
    ],
    values: { title: existing ? existing.title : "", kind: meta.kind, location: meta.location, tool_status: meta.tool_status, invoke: meta.invoke, path: meta.path, url: meta.url, version: meta.version, owner: meta.owner,
      docs: meta.docs, labels: existing ? existing.labels.join(", ") : "", commands: (meta.commands || []).map((c) => `${c.name} | ${c.summary} | ${c.usage}`).join("\n"),
      spec_source: openapi.source || "", spec_url: openapi.url || "", spec_path: openapi.path || "", spec_json: openapi.source === "inline" && openapi.spec ? JSON.stringify(openapi.spec, null, 2) : "" },
    submitLabel: existing ? "Save" : "Add tool",
    onSubmit: async (values) => {
      const built = toolMetaFromValues(values);
      if (existing) {
        const saved = await api("PATCH", `/api/kb/pages/${existing.id}`, { title: values.title, labels: splitList(values.labels), meta: built, comment: "Updated tool details" });
        state.kb = { ...state.kb, view: "page", pageId: saved.id };
      } else {
        const created = await api("POST", "/api/kb/pages", { space: "TOOLS", title: values.title, labels: splitList(values.labels), meta: built });
        state.kb = { ...state.kb, view: "page", pageId: created.id };
      }
      state.page = "kb";
      await refresh();
    },
  });
}

function toolCardHtml(page) {
  const tool = page.tool;
  const color = KB_TOOL_COLORS[tool.kind] || "var(--muted)";
  const detail = tool.invoke || tool.path || tool.url || "";
  return `<div class="panel-card clickable tool-card" tabindex="0" role="button" data-kb-open="${page.id}">
    <div class="tool-head"><span class="space-tile" style="--tint:${color}">${escapeHtml(tool.kind.slice(0, 3).toUpperCase())}</span><h3>${escapeHtml(page.title)}</h3>
      ${tool.tool_status !== "active" ? `<span class="chip tint" style="--tint:${KB_TOOL_STATUS_COLORS[tool.tool_status]}">${tool.tool_status}</span>` : ""}</div>
    <div class="muted tool-excerpt">${escapeHtml(page.excerpt) || "&nbsp;"}</div>
    ${detail ? `<code class="tool-invoke">${escapeHtml(detail)}</code>` : ""}
    <div class="rule-row"><span class="chip">${KB_LOCATIONS[tool.location]}</span><span class="chip tint" style="--tint:${color}">${KB_TOOL_KINDS[tool.kind]}</span>
      ${tool.operations !== null && tool.operations !== undefined ? `<span class="chip tint" style="--tint:var(--accent)">${tool.operations} endpoints</span>` : tool.has_openapi ? `<span class="chip">OpenAPI</span>` : ""}
      ${tool.commands ? `<span class="chip">${tool.commands} commands</span>` : ""}${tool.version ? `<span class="chip">v${escapeHtml(tool.version)}</span>` : ""}
      ${page.labels.slice(0, 3).map((l) => `<span class="chip tint" style="--tint:${tagColor(l)}">${escapeHtml(l)}</span>`).join("")}</div></div>`;
}

function renderTools() {
  const { tools } = state.pageData;
  const chip = (label, value, current, name) => `<button type="button" class="filter-chip${current === value ? " active" : ""}" data-tool-filter="${name}" data-value="${value}">${label}</button>`;
  byId("main").innerHTML = `<p class="page-intro">Tools on this machine and external services, with what each one can do. Add an OpenAPI description to a tool and its endpoints become browsable and testable here.</p>
    <div class="tool-filters">${chip("All", "", state.kb.toolLocation, "location")}${chip("On this machine", "machine", state.kb.toolLocation, "location")}${chip("External", "external", state.kb.toolLocation, "location")}
      <span class="divider"></span>${chip("Any kind", "", state.kb.toolKind, "kind")}${Object.entries(KB_TOOL_KINDS).map(([value, label]) => chip(label, value, state.kb.toolKind, "kind")).join("")}
      <input id="toolSearch" type="search" placeholder="Search ${tools.length} tools" value="${escapeHtml(state.kb.toolQuery)}" aria-label="Search tools" autocomplete="off"></div>
    ${tools.length ? `<div class="cards-grid">${tools.map(toolCardHtml).join("")}</div>` : `<div class="empty"><h2>No tools match</h2><p>Add the first tool, or clear the filters.</p><button class="primary" id="toolEmptyAdd">Add a tool</button></div>`}`;
  const main = byId("main");
  main.querySelectorAll("[data-tool-filter]").forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.toolFilter === "location" ? "toolLocation" : "toolKind";
    kbGo({ view: "tools", [key]: button.dataset.value });
  }));
  const search = byId("toolSearch");
  search.addEventListener("input", () => { clearTimeout(kbLive.findTimer); kbLive.findTimer = setTimeout(async () => { state.kb.toolQuery = search.value.trim(); const position = search.selectionStart; await loadKb(); renderTools(); const again = byId("toolSearch"); again.focus(); again.setSelectionRange(position, position); }, KB_FIND_DELAY_MS * 2); });
  const empty = byId("toolEmptyAdd");
  if (empty) empty.addEventListener("click", () => toolForm(null));
  wireKbLinks(main);
}

function factRow(label, value, copy) {
  if (!value) return "";
  return `<div class="fact"><span class="fact-label">${escapeHtml(label)}</span><code>${escapeHtml(value)}</code>${copy ? `<button type="button" class="ghost small" data-copy="${escapeHtml(value)}">Copy</button>` : ""}</div>`;
}

function renderToolPage(container) {
  const page = state.pageData.page;
  if (state.kb.history) return renderHistory(container);
  const meta = page.meta;
  const rendered = renderMarkdown(page.body, kbContext(page));
  const color = KB_TOOL_COLORS[meta.kind] || "var(--muted)";
  container.innerHTML = `<div class="kb-doc-wrap"><article class="kb-doc tool-page">
      <div class="tool-title"><span class="space-tile big" style="--tint:${color}">${escapeHtml(meta.kind.slice(0, 3).toUpperCase())}</span><div><h1>${escapeHtml(page.title)}</h1>
        <div class="kb-meta"><span class="chip">${KB_LOCATIONS[meta.location]}</span><span class="chip tint" style="--tint:${color}">${KB_TOOL_KINDS[meta.kind]}</span>
        <span class="chip tint" style="--tint:${KB_TOOL_STATUS_COLORS[meta.tool_status]}">${meta.tool_status}</span>${meta.version ? `<span class="chip">v${escapeHtml(meta.version)}</span>` : ""}
        ${meta.owner ? `<span class="muted">owner ${escapeHtml(meta.owner)}</span>` : ""}${reviewBadge(page)}
        ${page.labels.map((l) => `<span class="chip tint" style="--tint:${tagColor(l)}">${escapeHtml(l)}</span>`).join("")}</div></div></div>
      <div class="kb-actions"><button type="button" class="primary" id="toolEditDetails">Edit details</button><button type="button" class="ghost" id="kbEdit">Edit notes <kbd>e</kbd></button>
        <button type="button" class="ghost" id="kbFav">${page.favourite ? "&#9733; Favourite" : "&#9734; Favourite"}</button><button type="button" class="ghost" id="kbHistory">History (${page.version})</button>
        <button type="button" class="ghost" id="kbVerify">Verify</button><button type="button" class="ghost" id="kbCopyLink">Copy link</button><button type="button" class="ghost" id="kbMore">More</button></div>
      <div class="section-title">Use it</div>
      <div class="facts-block">${factRow("Run", meta.invoke, true)}${factRow("On disk", meta.path, true)}${factRow("Address", meta.url, true)}${meta.docs ? `<div class="fact"><span class="fact-label">Docs</span>${/^https?:/.test(meta.docs) ? `<a href="${escapeHtml(meta.docs)}" target="_blank" rel="noopener noreferrer">${escapeHtml(meta.docs)}</a>` : `<code>${escapeHtml(meta.docs)}</code>`}</div>` : ""}
        ${!meta.invoke && !meta.path && !meta.url && !meta.docs ? `<div class="empty-line">No usage details yet. Choose Edit details to add them.</div>` : ""}</div>
      ${meta.commands.length ? `<div class="section-title">Commands</div><table class="data-table"><thead><tr><th>Command</th><th>What it does</th><th>Usage</th></tr></thead><tbody>
        ${meta.commands.map((c) => `<tr><td><code>${escapeHtml(c.name)}</code></td><td>${escapeHtml(c.summary)}</td><td>${c.usage ? `<code>${escapeHtml(c.usage)}</code> <button type="button" class="ghost small" data-copy="${escapeHtml(c.usage)}">Copy</button>` : ""}</td></tr>`).join("")}</tbody></table>` : ""}
      <div id="toolSpec">${meta.openapi && meta.openapi.source ? `<div class="section-title">API overview <span class="grow"></span><button type="button" class="ghost small" id="toolRefresh">Fetch again</button></div><div id="toolSpecBody" class="empty-line">Loading the description</div>` : ""}</div>
      ${rendered.html ? `<div class="section-title">Notes</div><div class="md">${rendered.html}</div>` : ""}
      ${helpfulHtml(page)}</article><aside class="kb-rail">${tocHtml(rendered.headings)}
        ${page.backlinks.length ? `<div class="kb-rail-block"><h4>Linked from</h4>${page.backlinks.map((b) => `<div class="rowlink" tabindex="0" role="link" data-kb-open="${b.id}">${escapeHtml(b.title)}</div>`).join("")}</div>` : ""}
        <div class="kb-rail-block"><h4>Details</h4><div class="muted">Version ${page.version}, ${page.views} views</div><div class="muted">Updated ${ago(page.updated)}</div></div></aside></div>`;
  wireKbLinks(container);
  wirePageActions(page);
  wireHelpful(page);
  byId("toolEditDetails").addEventListener("click", () => toolForm(page));
  container.querySelectorAll("[data-copy]").forEach((button) => button.addEventListener("click", () => copyText(button.dataset.copy)));
  if (meta.openapi && meta.openapi.source) loadToolSpec(page, false);
  const refreshButton = byId("toolRefresh");
  if (refreshButton) refreshButton.addEventListener("click", () => loadToolSpec(page, true));
}

async function loadToolSpec(page, refreshSpec) {
  const body = byId("toolSpecBody");
  if (!body) return;
  body.className = "empty-line";
  body.textContent = refreshSpec ? "Fetching the description" : "Loading the description";
  try {
    const result = await api("GET", `/api/kb/pages/${page.id}/openapi${refreshSpec ? "?refresh=1" : ""}`);
    const server = (result.spec.servers && result.spec.servers[0] && result.spec.servers[0].url) || page.meta.url || "";
    const view = createOpenApiView(result.spec, { baseUrl: /^https?:/.test(server) ? server : (page.meta.url || location.origin), tryIt: true });
    body.className = "";
    view.render(body);
    const note = document.createElement("div");
    note.className = "kpi-sub";
    note.textContent = `From ${result.source}${result.fetched_at ? `, fetched ${ago(result.fetched_at)}` : ""}.${result.error ? ` The last fetch failed (${result.error}), so this is the cached copy.` : ""}`;
    body.prepend(note);
    if (refreshSpec) { toast("Description updated"); }
  } catch (error) {
    body.className = "empty-line danger";
    body.textContent = error.message;
  }
}

function finderDestinations() {
  const items = [
    { label: "Knowledge base home", hint: "Knowledge", run: () => kbGo({ view: "home", pageId: null }) },
    { label: "Tools", hint: "Knowledge", run: () => kbGo({ view: "tools", pageId: null }) },
    { label: "Dashboards", hint: "Reports", run: () => go({ page: "dashboards" }) },
    { label: "Plan", hint: "Planning", run: () => go({ page: "tickets", view: "plan" }) },
    { label: "Roadmap", hint: "Planning", run: () => go({ page: "tickets", view: "roadmap" }) },
    { label: "All work", hint: "Work", run: () => go({ page: "tickets", project: "", nav: "all", view: "board" }) },
    { label: "Create ticket", hint: "Action", run: () => openNewDialog() },
    { label: "New knowledge page", hint: "Action", run: () => newPageDialog({}) },
    { label: "Add tool", hint: "Action", run: () => toolForm(null) },
  ];
  state.pageData && state.pageData.overview && state.pageData.overview.spaces.filter((s) => s.kind === "docs").forEach((s) => items.push({ label: s.name, hint: "Space", run: () => kbGo({ view: "space", spaceId: s.id, pageId: null }) }));
  state.projects.forEach((p) => items.push({ label: `${p.key} ${p.name}`, hint: "Project", run: () => go({ page: "tickets", project: p.key, nav: "all", view: "board" }) }));
  state.areas.forEach((a) => items.push({ label: a.path, hint: "Area", run: () => go({ page: "area", areaId: a.id }) }));
  state.boards.forEach((b) => items.push({ label: `${b.area} / ${b.name}`, hint: "Board", run: () => go({ page: "board", boardId: b.id, view: "board" }) }));
  MANAGE_TABS.forEach((t) => items.push({ label: `Administration: ${t.label}`, hint: "Manage", run: () => go({ page: "manage", manageTab: t.id }) }));
  return items;
}

function openFinder(mode) {
  if (byId("finder")) { byId("finderInput").focus(); return; }
  const overlay = document.createElement("div");
  overlay.id = "finder";
  overlay.className = "finder-overlay";
  overlay.innerHTML = `<div class="finder" role="dialog" aria-label="Find anything"><div class="finder-input"><span>${svg("search")}</span>
    <input id="finderInput" placeholder="Find pages, tools, tickets or jump anywhere" autocomplete="off" aria-label="Find anything"><kbd>Esc</kbd></div><div id="finderList" class="finder-list"></div>
    <div class="finder-foot"><span><kbd>&#8593;</kbd> <kbd>&#8595;</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div></div>`;
  document.body.appendChild(overlay);
  const input = byId("finderInput");
  const list = byId("finderList");
  let entries = [];
  let active = 0;
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey, true); };
  const paint = () => {
    list.innerHTML = entries.length ? entries.map((entry, index) => `<div class="finder-item${index === active ? " active" : ""}" data-index="${index}"><span class="title">${entry.html || escapeHtml(entry.label)}</span><span class="muted">${escapeHtml(entry.hint)}</span></div>`).join("")
      : `<div class="empty-line">Nothing matches.</div>`;
    list.querySelectorAll(".finder-item").forEach((element) => {
      element.addEventListener("mouseenter", () => { active = Number(element.dataset.index); list.querySelectorAll(".finder-item").forEach((e, i) => e.classList.toggle("active", i === active)); });
      element.addEventListener("click", () => choose(Number(element.dataset.index)));
    });
    const current = list.querySelector(".finder-item.active");
    if (current) current.scrollIntoView({ block: "nearest" });
  };
  const choose = (index) => { const entry = entries[index]; if (!entry) return; close(); entry.run(); };
  const build = async () => {
    const text = input.value.trim().toLowerCase();
    if (!text) {
      const recent = kbRecents().map((r) => ({ label: r.title, hint: r.kind === "tool" ? "Recent tool" : "Recent page", run: () => kbGo({ view: "page", pageId: r.id }) }));
      entries = [...recent, ...finderDestinations().slice(0, mode === "review" ? 0 : 9)];
      if (mode === "review") {
        const stale = (await guarded(() => api("GET", "/api/kb/pages?stale=1&limit=20"))) || [];
        entries = stale.map((p) => ({ label: p.title, hint: `review was due ${p.review_by}`, run: () => kbGo({ view: "page", pageId: p.id }) }));
      }
      active = 0;
      paint();
      return;
    }
    const destinations = finderDestinations().filter((d) => d.label.toLowerCase().includes(text)).slice(0, 6).map((d) => ({ label: d.label, hint: d.hint, run: d.run }));
    entries = destinations;
    active = 0;
    paint();
    const found = await guarded(() => api("GET", "/api/search?q=" + encodeURIComponent(input.value.trim()) + "&limit=6"));
    if (!found || input.value.trim().toLowerCase() !== text) return;
    const content = [
      ...found.pages.map((p) => ({ html: `${escapeHtml(p.title)} <span class="snippet">${snippetHtml(p.snippet)}</span>`, label: p.title, hint: p.space.name, run: () => kbGo({ view: "page", pageId: p.id }) })),
      ...found.tools.map((p) => ({ html: `${escapeHtml(p.title)} <span class="snippet">${snippetHtml(p.snippet)}</span>`, label: p.title, hint: "Tool", run: () => kbGo({ view: "page", pageId: p.id }) })),
      ...found.tickets.map((t) => ({ label: `${t.key}  ${t.title}`, hint: STATUS_LABELS[t.status], run: () => openTicket(t.key) })),
    ];
    entries = [...content, ...destinations];
    active = 0;
    paint();
  };
  const onKey = (event) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); active = Math.min(entries.length - 1, active + 1); paint(); }
    else if (event.key === "ArrowUp") { event.preventDefault(); active = Math.max(0, active - 1); paint(); }
    else if (event.key === "Enter" && document.activeElement === input) { event.preventDefault(); choose(active); }
  };
  document.addEventListener("keydown", onKey, true);
  overlay.addEventListener("mousedown", (event) => { if (event.target === overlay) close(); });
  input.addEventListener("input", () => { clearTimeout(kbLive.findTimer); kbLive.findTimer = setTimeout(build, KB_FIND_DELAY_MS); });
  input.focus();
  build();
}

function kbShortcut(event) {
  if (state.page !== "kb" || state.kb.view !== "page" || state.kb.editing || state.kb.history || !state.pageData || !state.pageData.page) return false;
  if (event.key === "e") { event.preventDefault(); startEditing(); return true; }
  return false;
}
