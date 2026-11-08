"use strict";

function descendantsOf(areas, areaId) {
  const found = [areaId];
  for (const area of areas) if (found.includes(area.parent_id) && !found.includes(area.id)) found.push(area.id);
  return areas.reduce((ids, area) => (ids.includes(area.id) ? ids : found.includes(area.parent_id) ? [...ids, area.id] : ids), found);
}

function treeMovePlan(flat, draggedId, target, where) {
  const parent = where === "inside" ? target.id : target.parent_id;
  const siblings = flat.filter((n) => n.parent_id === (parent || null) && n.id !== draggedId).sort((a, b) => a.position - b.position || a.id - b.id);
  let index = siblings.length;
  if (where !== "inside") index = siblings.findIndex((n) => n.id === target.id) + (where === "after" ? 1 : 0);
  const ordered = [...siblings.slice(0, index), { id: draggedId }, ...siblings.slice(index)];
  const renumber = ordered.map((sibling, i) => ({ id: sibling.id, position: i + 1, was: sibling.position }))
    .filter((entry) => entry.id !== draggedId && entry.was !== entry.position)
    .map(({ id, position }) => ({ id, position }));
  return { parent: parent || "", position: index + 1, renumber };
}

if (typeof module !== "undefined") module.exports = { descendantsOf, treeMovePlan };
