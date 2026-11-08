"use strict";

if (typeof escapeHtml === "undefined") globalThis.escapeHtml = require("./escape.js").escapeHtml;

const dashboardModuleRenderers = {};

function registerDashboardModule(id, definition) {
  dashboardModuleRenderers[id] = definition;
}

function rawDataBody(data) {
  return `<pre class="widget-raw">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
}

function widgetBody(widget, data, helpers, renderers = dashboardModuleRenderers) {
  const errorBody = (message) => `<div class="widget-error">${escapeHtml(message)}</div>`;
  if (!data) return errorBody("Loading");
  if (data.error) return errorBody(data.error);
  const renderer = renderers[widget.kind];
  if (!renderer || typeof renderer.render !== "function") return rawDataBody(data);
  try {
    return renderer.render(widget, data, helpers);
  } catch (error) {
    return errorBody(`The ${widget.kind} module could not draw this widget: ${error.message}`);
  }
}

async function loadModuleScripts(descriptors, loadScript, loaded = new Set()) {
  const failures = [];
  await Promise.all(descriptors.filter((item) => item.script && !loaded.has(item.id)).map(async (item) => {
    try {
      await loadScript(item.script);
      loaded.add(item.id);
    } catch (error) {
      failures.push({ id: item.id, error: error.message || String(error) });
    }
  }));
  return failures;
}

function moduleById(descriptors, id) {
  return descriptors.find((item) => item.id === id) || null;
}

function moduleChoices(descriptors) {
  return descriptors.map((item) => ({ value: item.id, label: item.title }));
}

function moduleFailureLines(failures) {
  return failures.map((failure) => `${failure.file || failure.folder}: ${failure.error}`);
}

if (typeof module !== "undefined") {
  module.exports = { registerDashboardModule, widgetBody, loadModuleScripts, moduleById, moduleChoices, moduleFailureLines, dashboardModuleRenderers };
}
