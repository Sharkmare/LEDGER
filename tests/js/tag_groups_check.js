"use strict";

const assert = require("assert");
const path = require("path");
const { tagGroups } = require(path.join(__dirname, "..", "..", "ledger", "static", "taggroups.js"));

const project = (key, tags, status = "active") => ({ key, tags, status });
const tags = (groups) => groups.map((group) => group.tag);
const keys = (group) => group.projects.map((p) => p.key);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("without any tag the list stays flat with an empty header", () => {
  const groups = tagGroups([project("A", []), project("B", undefined)]);
  assert.deepStrictEqual(tags(groups), [""]);
  assert.deepStrictEqual(keys(groups[0]), ["A", "B"]);
});

check("each tag becomes a group header in alphabetical order", () => {
  const groups = tagGroups([project("A", ["hive"]), project("B", ["anubis"]), project("C", ["hive"])]);
  assert.deepStrictEqual(tags(groups), ["anubis", "hive"]);
  assert.deepStrictEqual(keys(groups[1]), ["A", "C"]);
});

check("a project with several tags is listed under each of them", () => {
  const groups = tagGroups([project("A", ["hive", "anubis"])]);
  assert.deepStrictEqual(tags(groups), ["anubis", "hive"]);
  assert.deepStrictEqual(groups.map(keys), [["A"], ["A"]]);
});

check("projects with no tag go last under the untagged header", () => {
  const groups = tagGroups([project("A", []), project("B", ["zeta"]), project("C", ["alpha"])]);
  assert.deepStrictEqual(tags(groups), ["alpha", "zeta", "untagged"]);
  assert.deepStrictEqual(keys(groups[2]), ["A"]);
});

check("archived projects filtered out by the caller leave no empty group", () => {
  const all = [project("A", ["old"], "archived"), project("B", ["live"])];
  assert.deepStrictEqual(tags(tagGroups(all.filter((p) => p.status !== "archived"))), ["live"]);
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} tag grouping checks passed`);
process.exit(failed ? 1 : 0);
