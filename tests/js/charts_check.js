"use strict";

const assert = require("assert");
const path = require("path");
const { formatNumber, hbars, donut, lineChart, chartLegend, barPairs } = require(path.join(__dirname, "..", "..", "ledger", "static", "charts.js"));

const WIDTH = 600;
const HEIGHT = 180;
const LEFT = 34;
const RIGHT = 10;
const TOP = 10;
const BOTTOM = 22;
const INNER_WIDTH = WIDTH - LEFT - RIGHT;
const INNER_HEIGHT = HEIGHT - TOP - BOTTOM;
const FLOOR_Y = TOP + INNER_HEIGHT;
const CIRCUMFERENCE = 2 * Math.PI * 48;

const numbers = (html, pattern) => [...html.matchAll(pattern)].map((match) => Number(match[1]));
const near = (actual, expected, label) => assert.ok(Math.abs(actual - expected) < 1e-6, `${label}: expected ${expected}, got ${actual}`);
const red = () => "red";
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("whole numbers print as they are and others with one decimal", () => {
  assert.strictEqual(formatNumber(3), "3");
  assert.strictEqual(formatNumber(0), "0");
  assert.strictEqual(formatNumber(2.5), "2.5");
  assert.strictEqual(formatNumber(1.04), "1.0");
  assert.strictEqual(formatNumber(2.26), "2.3");
});

check("bars say so when there is nothing to show", () => {
  assert.ok(hbars([], red).includes("Nothing to show yet."));
});

check("bar lengths are a share of the longest bar, rounded", () => {
  const html = hbars([{ name: "a", value: 10 }, { name: "b", value: 5 }, { name: "c", value: 1 }], red);
  assert.deepStrictEqual(numbers(html, /width:(\d+)%/g), [100, 50, 10]);
});

check("a bar length that is not whole rounds to the nearest percent", () => {
  assert.deepStrictEqual(numbers(hbars([{ name: "a", value: 3 }, { name: "b", value: 2 }], red), /width:(\d+)%/g), [100, 67]);
});

check("bars of zero show no length instead of dividing by zero", () => {
  assert.deepStrictEqual(numbers(hbars([{ name: "a", value: 0 }], red), /width:(\d+)%/g), [0]);
});

check("bars take their colour from the callback and their text from the formatter", () => {
  const html = hbars([{ name: "a", value: 2, points: 9 }], (bucket) => `c${bucket.value}`, (bucket) => `${bucket.points} pts`);
  assert.ok(html.includes("--tint:c2"));
  assert.ok(html.includes(">9 pts<"));
});

check("bar names are escaped", () => {
  const html = hbars([{ name: "<img src=x>", value: 1 }], red);
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img src=x&gt;"));
});

check("a donut with no tickets says so", () => {
  assert.ok(donut([{ name: "a", value: 0 }], red).includes("Nothing to show yet."));
});

check("donut arcs are proportional, follow each other and fill the circle", () => {
  const html = donut([{ name: "a", value: 1 }, { name: "b", value: 3 }], red);
  const dashes = [...html.matchAll(/stroke-dasharray="([\d.]+) ([\d.]+)"/g)].map((m) => [Number(m[1]), Number(m[2])]);
  const offsets = numbers(html, /stroke-dashoffset="(-?[\d.]+)"/g);
  near(dashes[0][0], CIRCUMFERENCE / 4, "first arc");
  near(dashes[1][0], (CIRCUMFERENCE * 3) / 4, "second arc");
  for (const [shown, rest] of dashes) near(shown + rest, CIRCUMFERENCE, "arc plus gap");
  near(offsets[0], 0, "first offset");
  near(offsets[1], -CIRCUMFERENCE / 4, "second offset");
});

check("a donut shows the total and one legend row per bucket, escaped", () => {
  const html = donut([{ name: "<b>", value: 2 }, { name: "ok", value: 3 }], red);
  assert.ok(html.includes(">5</text>"));
  assert.strictEqual((html.match(/class="row-item"/g) || []).length, 2);
  assert.ok(!html.includes("<b>"));
});

const LABELS = ["2026-11-01", "2026-11-02", "2026-11-03"];
const pathOf = (html, index = 0) => [...html.matchAll(/<path class="line" d="([^"]*)"/g)][index][1];

check("a line starts at the left edge, ends at the right edge and tops out at the highest value", () => {
  assert.strictEqual(pathOf(lineChart(LABELS, [{ values: [0, 5, 10], color: "red" }])), `M${LEFT}.0 ${FLOOR_Y}.0 L${LEFT + INNER_WIDTH / 2}.0 84.0 L${LEFT + INNER_WIDTH}.0 ${TOP}.0 `);
});

check("a single point sits in the middle", () => {
  assert.strictEqual(pathOf(lineChart(["2026-11-01"], [{ values: [4], color: "red" }])), `M${LEFT + INNER_WIDTH / 2}.0 ${TOP}.0 `);
});

check("a missing value breaks the line instead of joining across the gap", () => {
  const d = pathOf(lineChart(LABELS, [{ values: [1, null, 3], color: "red" }]));
  assert.strictEqual((d.match(/M/g) || []).length, 2);
  assert.strictEqual((d.match(/L/g) || []).length, 0);
});

check("the scale has a floor of zero and never a peak under one", () => {
  const d = pathOf(lineChart(LABELS, [{ values: [0, 0, 0], color: "red" }]));
  assert.ok(d.startsWith(`M${LEFT}.0 ${FLOOR_Y}.0`));
});

check("a raised floor moves the bottom of the scale", () => {
  const html = lineChart(LABELS, [{ values: [5, 7.5, 10], color: "red" }], { floor: 5 });
  assert.ok(pathOf(html).startsWith(`M${LEFT}.0 ${FLOOR_Y}.0`));
});

check("the grid has five lines labelled from the floor to the peak", () => {
  const html = lineChart(LABELS, [{ values: [0, 5, 10], color: "red" }]);
  assert.strictEqual((html.match(/class="grid"/g) || []).length, 5);
  assert.deepStrictEqual([...html.matchAll(new RegExp(`<text x="${LEFT - 5}" y="[\\d.]+" text-anchor="end">([^<]+)<`, "g"))].map((m) => m[1]), ["0", "2.5", "5", "7.5", "10"]);
});

check("only the first, middle and last dates are labelled, without the year", () => {
  const labels = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"];
  const html = lineChart(labels, [{ values: [1, 2, 3, 4, 5], color: "red" }]);
  const ticks = [...html.matchAll(/text-anchor="(start|middle|end)">(\d\d-\d\d)</g)].map((m) => [m[1], m[2]]);
  assert.deepStrictEqual(ticks, [["start", "11-01"], ["middle", "11-03"], ["end", "11-05"]]);
});

check("fewer than three dates are all labelled", () => {
  const html = lineChart(["2026-11-01", "2026-11-02"], [{ values: [1, 2], color: "red" }]);
  assert.strictEqual([...html.matchAll(/text-anchor="(?:start|middle|end)">\d\d-\d\d</g)].length, 2);
});

check("only the series asked for are dashed", () => {
  const html = lineChart(LABELS, [{ values: [1, 2, 3], color: "red" }, { values: [3, 2, 1], color: "blue" }], { dashed: [0] });
  assert.strictEqual((html.match(/stroke-dasharray="5 5"/g) || []).length, 1);
  assert.ok(html.indexOf('stroke="red" stroke-dasharray') > -1);
});

check("a legend lists each series with its colour and an escaped name", () => {
  const html = chartLegend([{ name: "Created", color: "red" }, { name: "<x>", color: "blue" }]);
  assert.ok(html.includes("--tint:red") && html.includes("--tint:blue"));
  assert.ok(!html.includes("<x>"));
});

check("velocity bars say so when no iteration has finished", () => {
  assert.ok(barPairs([]).includes("No finished iterations yet."));
});

check("velocity bars scale to the biggest figure and sit on the baseline", () => {
  const html = barPairs([{ name: "Sprint 1", committed: 10, completed: 5 }, { name: "Sprint 2", committed: 4, completed: 4 }]);
  const heights = numbers(html, /height="([\d.]+)" rx/g);
  near(heights[0], INNER_HEIGHT, "first committed");
  near(heights[1], INNER_HEIGHT / 2, "first completed");
  near(heights[2], (4 / 10) * INNER_HEIGHT, "second committed");
  const tops = numbers(html, /y="([\d.]+)" width/g);
  near(tops[0] + heights[0], FLOOR_Y, "bar bottom");
  near(tops[1] + heights[1], FLOOR_Y, "completed bar bottom");
});

check("velocity bars scale to a completed figure that is above the committed one", () => {
  const heights = numbers(barPairs([{ name: "S", committed: 2, completed: 8 }]), /height="([\d.]+)" rx/g);
  near(heights[0], INNER_HEIGHT / 4, "committed");
  near(heights[1], INNER_HEIGHT, "completed");
});

check("velocity bars share the width evenly and label with the last ten characters", () => {
  const html = barPairs([{ name: "A very long iteration name", committed: 1, completed: 1 }, { name: "B", committed: 1, completed: 1 }]);
  const lefts = numbers(html, /<rect x="([\d.]+)" y="[\d.]+" width="[\d.]+" height="[\d.]+" rx="3" fill="var\(--muted\)"/g);
  const slot = INNER_WIDTH / 2;
  near(lefts[0], LEFT + slot * 0.15, "first slot");
  near(lefts[1], LEFT + slot + slot * 0.15, "second slot");
  assert.ok(html.includes(">ation name<"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);
