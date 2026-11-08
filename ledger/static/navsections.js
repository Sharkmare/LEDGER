"use strict";

function buildNavSections(state, { navItemHtml, workItems, manageTabs, queueCount, tagGroups }) {
  const openCount = (project) => Object.entries(project.counts).filter(([status]) => !state.meta.closed_statuses.includes(status)).reduce((sum, [, count]) => sum + count, 0);
  const sectionCollapsed = (name) => state.collapsedSections.includes(name);
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
    { name: "Work", items: workItems.filter((i) => matches(i.label)).map((i) => navItemHtml({ id: i.id, label: i.label, iconName: i.icon, count: i.id === "queue" ? queueCount : undefined, kind: "work", active: onTickets && !state.project && state.nav === i.id && ["board", "list"].includes(state.view) })) },
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
    { name: "Manage", items: manageTabs.filter((t) => matches(t.label) || matches("manage")).map((t) => navItemHtml({ id: t.id, label: t.label, iconName: t.id === "tags" ? "tag" : "gear", kind: "manage", active: state.page === "manage" && state.manageTab === t.id })) },
    { name: "Help", items: [
      ...(matches("api reference") ? [navItemHtml({ id: "docs", label: "API reference", iconName: "docs", kind: "link", href: "/docs" })] : []),
      ...(matches("keyboard shortcuts") ? [navItemHtml({ id: "shortcuts", label: "Keyboard shortcuts", iconName: "help", kind: "shortcuts" })] : []),
    ] },
  ].filter((section) => section.items.length);
}

if (typeof module !== "undefined") module.exports = { buildNavSections };
