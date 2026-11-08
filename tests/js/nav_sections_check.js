"use strict";

const assert = require("assert");
const path = require("path");
const staticDir = path.join(__dirname, "..", "..", "ledger", "static");
const { buildNavSections } = require(path.join(staticDir, "navsections.js"));
const { tagGroups } = require(path.join(staticDir, "taggroups.js"));

const WORK_ITEMS = [{ id: "all", label: "All work", icon: "layers" }, { id: "blocked", label: "Blocked", icon: "alert" }, { id: "queue", label: "Needs you", icon: "user" }];
const MANAGE_TABS = [{ id: "projects", label: "Projects" }, { id: "tags", label: "Tags" }];

const area = (id, name, depth, parentId = null, openTickets = 0, tags = []) => ({ id, name, path: name, depth, parent_id: parentId, open_tickets: openTickets, tags });
const project = (key, name, counts, tags = [], status = "active") => ({ key, name, counts, tags, status });

function baseState(overrides = {}) {
  return {
    navFilter: "", page: "tickets", project: "", nav: "all", view: "board", areaId: null, boardId: null, manageTab: "projects",
    meta: { closed_statuses: ["done", "cancelled"] }, org: { name: "" }, projects: [], areas: [], boards: [], collapsedSections: [], collapsedAreas: [],
    kbSpaces: [], kb: { view: "home" }, pageData: null, ...overrides,
  };
}

function sectionsOf(state, queueCount = 0) {
  return buildNavSections(state, { navItemHtml: (item) => item, workItems: WORK_ITEMS, manageTabs: MANAGE_TABS, queueCount, tagGroups });
}

const section = (sections, name) => sections.find((s) => s.name === name);
const ids = (items) => items.map((item) => item.id);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("every section is present when nothing is filtered", () => {
  const names = sectionsOf(baseState({ projects: [project("A", "Alpha", {})] })).map((s) => s.name);
  assert.deepStrictEqual(names, ["Work", "Organisation", "Projects", "Planning", "Knowledge", "Reports", "Manage", "Help"]);
});

check("the filter keeps only matching entries and drops sections left empty", () => {
  const sections = sectionsOf(baseState({ navFilter: "blocked" }));
  assert.deepStrictEqual(sections.map((s) => s.name), ["Work"]);
  assert.deepStrictEqual(ids(sections[0].items), ["blocked"]);
  assert.deepStrictEqual(sectionsOf(baseState({ navFilter: "zzzz" })), []);
});

check("the work section shows the queue count and nothing else gets one", () => {
  const items = section(sectionsOf(baseState(), 4), "Work").items;
  assert.strictEqual(items.find((i) => i.id === "queue").count, 4);
  assert.strictEqual(items.find((i) => i.id === "all").count, undefined);
});

check("archived projects are left out of the list and of the section total", () => {
  const projects = section(sectionsOf(baseState({ projects: [project("A", "Alpha", {}), project("B", "Beta", {}, [], "archived")] })), "Projects");
  assert.deepStrictEqual(ids(projects.items.filter((i) => i.kind === "project")), ["A"]);
  assert.strictEqual(projects.total, 1);
});

check("a project count leaves out closed statuses", () => {
  const projects = section(sectionsOf(baseState({ projects: [project("A", "Alpha", { todo: 2, in_progress: 1, done: 5, cancelled: 3 })] })), "Projects");
  assert.strictEqual(projects.items.find((i) => i.id === "A").count, 3);
});

check("tagged projects sit under a header that sums their open tickets, indented once", () => {
  const state = baseState({ projects: [project("A", "Alpha", { todo: 2 }, ["hive"]), project("B", "Beta", { todo: 3, done: 9 }, ["hive"]), project("C", "Gamma", { todo: 1 }, ["anubis"])] });
  const items = section(sectionsOf(state), "Projects").items.filter((i) => i.kind !== "create-project");
  assert.deepStrictEqual(ids(items), ["group:anubis", "C", "group:hive", "A", "B"]);
  assert.strictEqual(items.find((i) => i.id === "group:hive").count, 5);
  assert.deepStrictEqual(items.filter((i) => i.kind === "project").map((i) => i.indent), [1, 1, 1]);
});

check("untagged projects stay flat with no header", () => {
  const items = section(sectionsOf(baseState({ projects: [project("A", "Alpha", {})] })), "Projects").items;
  assert.deepStrictEqual(items.map((i) => [i.kind, i.indent]), [["project", 0], ["create-project", undefined]]);
});

check("a project is active only on the tickets page and not on the plan or roadmap views", () => {
  const projects = [project("A", "Alpha", {})];
  const activeOf = (overrides) => section(sectionsOf(baseState({ projects, project: "A", ...overrides })), "Projects").items.find((i) => i.id === "A").active;
  assert.strictEqual(activeOf({}), true);
  assert.strictEqual(activeOf({ page: "kb" }), false);
  assert.strictEqual(activeOf({ view: "plan" }), false);
  assert.strictEqual(activeOf({ view: "roadmap" }), false);
  assert.strictEqual(activeOf({ project: "B" }), false);
});

check("the project filter matches key, name and tags", () => {
  const projects = [project("PAZ", "Pazaak", {}, ["games"]), project("LED", "Ledger", {}, ["hive"])];
  const keysFor = (navFilter) => ids(section(sectionsOf(baseState({ projects, navFilter })), "Projects").items.filter((i) => i.kind === "project"));
  assert.deepStrictEqual(keysFor("paz"), ["PAZ"]);
  assert.deepStrictEqual(keysFor("ledger"), ["LED"]);
  assert.deepStrictEqual(keysFor("hive"), ["LED"]);
});

const AREAS = [area(1, "Ops", 0, null, 4), area(2, "Infra", 1, 1, 2), area(3, "Racks", 2, 2, 1), area(4, "Games", 0, null, 7)];

check("areas are listed depth first, indented by depth, and a parent with children has a twisty", () => {
  const items = section(sectionsOf(baseState({ areas: AREAS })), "Organisation").items.filter((i) => i.kind === "area");
  assert.deepStrictEqual(ids(items), [1, 2, 3, 4]);
  assert.deepStrictEqual(items.map((i) => i.indent), [0, 1, 2, 0]);
  assert.deepStrictEqual(items.map((i) => i.twisty), ["open", "open", "", ""]);
});

check("a folded area hides everything below it but not its sibling", () => {
  const items = section(sectionsOf(baseState({ areas: AREAS, collapsedAreas: [1] })), "Organisation").items.filter((i) => i.kind === "area");
  assert.deepStrictEqual(ids(items), [1, 4]);
  assert.strictEqual(items[0].twisty, "closed");
});

check("a fold only hides the levels under the folded area", () => {
  const items = section(sectionsOf(baseState({ areas: AREAS, collapsedAreas: [2] })), "Organisation").items.filter((i) => i.kind === "area");
  assert.deepStrictEqual(ids(items), [1, 2, 4]);
});

check("filtering ignores folds so a match inside a folded area still shows", () => {
  const items = section(sectionsOf(baseState({ areas: AREAS, collapsedAreas: [1], navFilter: "racks" })), "Organisation").items.filter((i) => i.kind === "area");
  assert.deepStrictEqual(ids(items), [3]);
});

check("boards appear under their area one level deeper and hide when the area is folded", () => {
  const boards = [{ id: 10, name: "Sprint", area_id: 1, tickets: 6 }];
  const open = section(sectionsOf(baseState({ areas: AREAS, boards })), "Organisation").items;
  const board = open.find((i) => i.kind === "board");
  assert.deepStrictEqual([board.id, board.count, board.indent], [10, 6, 1]);
  const folded = section(sectionsOf(baseState({ areas: AREAS, boards, collapsedAreas: [1] })), "Organisation").items;
  assert.strictEqual(folded.some((i) => i.kind === "board"), false);
});

check("a board name that matches the filter keeps its area visible", () => {
  const boards = [{ id: 10, name: "Sprint", area_id: 4, tickets: 1 }];
  const items = section(sectionsOf(baseState({ areas: AREAS, boards, navFilter: "sprint" })), "Organisation").items;
  assert.deepStrictEqual(ids(items.filter((i) => i.kind === "area" || i.kind === "board")), [4, 10]);
});

check("tagged areas get a group header with the summed count, indent their rows, and can be folded", () => {
  const areas = [area(1, "Ops", 0, null, 4, ["hive"]), area(2, "Games", 0, null, 7, ["hive"])];
  const open = section(sectionsOf(baseState({ areas })), "Organisation").items.filter((i) => i.kind !== "create-area");
  assert.deepStrictEqual(ids(open), ["areagroup:hive", 1, 2]);
  assert.strictEqual(open[0].count, 11);
  assert.deepStrictEqual(open.slice(1).map((i) => i.indent), [1, 1]);
  const folded = section(sectionsOf(baseState({ areas, collapsedSections: ["areagroup:hive"] })), "Organisation").items.filter((i) => i.kind !== "create-area");
  assert.deepStrictEqual(ids(folded), ["areagroup:hive"]);
  assert.strictEqual(folded[0].twisty, "closed");
});

check("the organisation section is named after the organisation and totals its areas", () => {
  const organisation = section(sectionsOf(baseState({ areas: AREAS, org: { name: "Hive" } })), "Hive");
  assert.strictEqual(organisation.key, "Organisation");
  assert.strictEqual(organisation.total, 4);
});

check("knowledge shows docs spaces only and marks the tools entry on a tool page", () => {
  const kbSpaces = [{ id: 1, kind: "docs", name: "Runbooks", key: "RB", pages: 3 }, { id: 2, kind: "tools", name: "Tools", key: "TL", pages: 8 }];
  const state = baseState({ kbSpaces, page: "kb", kb: { view: "page", spaceId: 1 }, pageData: { page: { page_type: "tool" } } });
  const items = section(sectionsOf(state), "Knowledge").items;
  assert.deepStrictEqual(items.filter((i) => i.kind === "kb-space").map((i) => i.id), [1]);
  const tools = items.find((i) => i.kind === "kb-tools");
  assert.deepStrictEqual([tools.count, tools.active], [8, true]);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
