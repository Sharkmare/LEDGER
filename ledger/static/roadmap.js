"use strict";

const MS_PER_DAY = 86400000;
const ROADMAP_PAD_DAYS = 10;
const UNDATED_EPIC_DAYS = 14;
const MIN_BAR_PERCENT = 0.6;

function parseDay(text) { return new Date(`${text}T00:00:00`).getTime(); }

function monthStarts(first, last) {
  const months = [];
  const cursor = new Date(first);
  cursor.setDate(1);
  cursor.setHours(0, 0, 0, 0);
  while (cursor.getTime() <= last) {
    months.push({ at: cursor.getTime(), label: cursor.toLocaleDateString(undefined, { month: "short", year: "2-digit" }) });
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return months;
}

function roadmapPercent(done, total) { return total ? Math.round((done / total) * 100) : 0; }

function roadmapLayout(roadmap, now) {
  const first = parseDay(roadmap.range.start) - ROADMAP_PAD_DAYS * MS_PER_DAY;
  const last = parseDay(roadmap.range.end) + ROADMAP_PAD_DAYS * MS_PER_DAY;
  const span = last - first;
  const place = (start, end) => {
    const finish = end + MS_PER_DAY;
    return { left: ((start - first) / span) * 100, width: Math.max(((finish - start) / span) * 100, MIN_BAR_PERCENT) };
  };
  const iterations = roadmap.iterations.map((iteration) => ({
    iteration, percent: iteration.points ? roadmapPercent(iteration.points_done, iteration.points) : roadmapPercent(iteration.done, iteration.tickets),
    ...place(parseDay(iteration.start), parseDay(iteration.end)),
  }));
  const epics = roadmap.epics.map((epic) => {
    const start = epic.start ? parseDay(epic.start) : parseDay(epic.due) - UNDATED_EPIC_DAYS * MS_PER_DAY;
    const end = epic.due ? parseDay(epic.due) : parseDay(epic.start) + UNDATED_EPIC_DAYS * MS_PER_DAY;
    const percent = epic.progress.total ? roadmapPercent(epic.progress.done, epic.progress.total) : epic.status === "done" ? 100 : 0;
    return { epic, percent, ...place(start, end) };
  });
  const months = monthStarts(first, last).map((month) => ({ label: month.label, left: ((month.at - first) / span) * 100 }));
  return { iterations, epics, months, todayOffset: now >= first && now <= last ? (now - first) / span : null };
}

if (typeof module !== "undefined") module.exports = { parseDay, monthStarts, roadmapLayout, roadmapPercent };
