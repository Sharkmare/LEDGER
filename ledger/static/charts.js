"use strict";

const CHART_WIDTH = 600;
const CHART_HEIGHT = 180;
const CHART_PAD = { left: 34, right: 10, top: 10, bottom: 22 };

if (typeof escapeHtml === "undefined") globalThis.escapeHtml = require("./escape.js").escapeHtml;

function formatNumber(value) { return Number.isInteger(value) ? String(value) : value.toFixed(1); }

function hbars(buckets, colorOf, formatValue = (b) => b.value) {
  if (!buckets.length) return `<div class="widget-error">Nothing to show yet.</div>`;
  const peak = Math.max(1, ...buckets.map((b) => b.value));
  return `<div class="hbars">${buckets.map((bucket) => `<div class="hbar"><span class="name" title="${escapeHtml(bucket.name)}">${escapeHtml(bucket.name)}</span>
    <span class="track"><span style="--tint:${colorOf(bucket)}; width:${Math.round((bucket.value / peak) * 100)}%"></span></span>
    <span class="value">${formatValue(bucket)}</span></div>`).join("")}</div>`;
}

function donut(buckets, colorOf) {
  const total = buckets.reduce((sum, b) => sum + b.value, 0);
  if (!total) return `<div class="widget-error">Nothing to show yet.</div>`;
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = buckets.map((bucket) => {
    const length = (bucket.value / total) * circumference;
    const arc = `<circle r="${radius}" cx="66" cy="66" fill="none" stroke="${colorOf(bucket)}" stroke-width="20" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 66 66)"/>`;
    offset += length;
    return arc;
  }).join("");
  return `<div class="donut-wrap"><svg viewBox="0 0 132 132" role="img" aria-label="Breakdown">${arcs}
    <text x="66" y="62" text-anchor="middle" style="font-size:22px;font-weight:700;fill:var(--text);font-family:var(--font-display)">${total}</text>
    <text x="66" y="80" text-anchor="middle" style="font-size:10px;fill:var(--muted)">tickets</text></svg>
    <div class="legend">${buckets.map((bucket) => `<div class="row-item"><span class="dot" style="--tint:${colorOf(bucket)}"></span><span class="name">${escapeHtml(bucket.name)}</span><span class="value">${bucket.value}</span></div>`).join("")}</div></div>`;
}

function lineChart(labels, series, { floor = 0, dashed = [] } = {}) {
  const innerWidth = CHART_WIDTH - CHART_PAD.left - CHART_PAD.right;
  const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;
  const values = series.flatMap((s) => s.values).filter((v) => v !== null && v !== undefined);
  const peak = Math.max(1, ...values);
  const x = (index) => CHART_PAD.left + (labels.length < 2 ? innerWidth / 2 : (index / (labels.length - 1)) * innerWidth);
  const y = (value) => CHART_PAD.top + innerHeight - ((value - floor) / (peak - floor)) * innerHeight;
  const grid = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
    const value = floor + (peak - floor) * fraction;
    return `<line class="grid" x1="${CHART_PAD.left}" x2="${CHART_WIDTH - CHART_PAD.right}" y1="${y(value)}" y2="${y(value)}"/>
      <text x="${CHART_PAD.left - 5}" y="${y(value) + 3}" text-anchor="end">${formatNumber(value)}</text>`;
  }).join("");
  const picks = labels.length < 3 ? labels.map((_, i) => i) : [0, Math.floor((labels.length - 1) / 2), labels.length - 1];
  const ticks = picks.map((index) => `<text x="${x(index)}" y="${CHART_HEIGHT - 6}" text-anchor="${index === 0 ? "start" : index === labels.length - 1 ? "end" : "middle"}">${escapeHtml(labels[index].slice(5))}</text>`).join("");
  const lines = series.map((entry, number) => {
    let path = "";
    let drawing = false;
    entry.values.forEach((value, index) => {
      if (value === null || value === undefined) { drawing = false; return; }
      path += `${drawing ? "L" : "M"}${x(index).toFixed(1)} ${y(value).toFixed(1)} `;
      drawing = true;
    });
    return `<path class="line" d="${path}" stroke="${entry.color}" ${dashed.includes(number) ? 'stroke-dasharray="5 5"' : ""}/>`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="Chart">${grid}${lines}${ticks}</svg>`;
}

function chartLegend(entries) {
  return `<div class="chart-legend">${entries.map((e) => `<span><span class="dot" style="--tint:${e.color}"></span>${escapeHtml(e.name)}</span>`).join("")}</div>`;
}

function barPairs(items) {
  if (!items.length) return `<div class="widget-error">No finished iterations yet.</div>`;
  const peak = Math.max(1, ...items.flatMap((i) => [i.committed, i.completed]));
  const slot = (CHART_WIDTH - CHART_PAD.left - CHART_PAD.right) / items.length;
  const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;
  const bars = items.map((item, index) => {
    const left = CHART_PAD.left + index * slot + slot * 0.15;
    const width = slot * 0.7;
    const committed = (item.committed / peak) * innerHeight;
    const completed = (item.completed / peak) * innerHeight;
    const base = CHART_PAD.top + innerHeight;
    return `<rect x="${left}" y="${base - committed}" width="${width}" height="${committed}" rx="3" fill="var(--muted)" opacity="0.3"/>
      <rect x="${left + width * 0.2}" y="${base - completed}" width="${width * 0.6}" height="${completed}" rx="3" fill="var(--status-done)"/>
      <text x="${left + width / 2}" y="${CHART_HEIGHT - 6}" text-anchor="middle">${escapeHtml(item.name.slice(-10))}</text>`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="Velocity"><line class="axis" x1="${CHART_PAD.left}" x2="${CHART_WIDTH - CHART_PAD.right}" y1="${CHART_PAD.top + innerHeight}" y2="${CHART_PAD.top + innerHeight}"/>${bars}</svg>`;
}

if (typeof module !== "undefined") module.exports = { formatNumber, hbars, donut, lineChart, chartLegend, barPairs };
