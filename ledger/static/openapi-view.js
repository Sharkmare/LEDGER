"use strict";

const OPENAPI_REQUEST_TIMEOUT_MS = 15000;

function createOpenApiView(spec, options = {}) {
  const baseUrl = options.baseUrl || location.origin;
  const headersFor = options.headersFor || (() => ({}));

  const { resolve, exampleOf, typeLabel, allParameters, collectOperations } = schemaTools(spec);

  function enumChips(schema) {
    const node = resolve(schema);
    return node.enum ? `<div class="enum">${node.enum.map((v) => `<span class="chip">${escapeHtml(v)}</span>`).join("")}</div>` : "";
  }

  function propertyTable(schema) {
    const node = resolve(schema);
    const properties = node.properties || {};
    const required = node.required || [];
    const rows = Object.entries(properties).map(([name, property]) => {
      const detail = resolve(property);
      const notes = [detail.description, detail.default !== undefined ? `default ${detail.default}` : "", detail.maxLength ? `max ${detail.maxLength} characters` : ""].filter(Boolean).join(". ");
      return `<tr><td><span class="name">${escapeHtml(name)}</span>${required.includes(name) ? `<span class="req">required</span>` : ""}</td>
        <td><span class="type">${escapeHtml(typeLabel(property))}</span>${enumChips(property)}</td><td>${escapeHtml(notes)}</td></tr>`;
    }).join("");
    return rows ? `<table class="params"><thead><tr><th>Field</th><th>Type</th><th>Notes</th></tr></thead><tbody>${rows}</tbody></table>` : "";
  }

  function parameterTable(parameters) {
    if (!parameters.length) return "";
    return `<h4>Parameters</h4><table class="params"><thead><tr><th>Name</th><th>In</th><th>Type</th><th>Description</th></tr></thead><tbody>
      ${parameters.map((p) => `<tr><td><span class="name">${escapeHtml(p.name)}</span>${p.required ? `<span class="req">required</span>` : ""}</td><td>${escapeHtml(p.in)}</td>
        <td><span class="type">${escapeHtml(typeLabel(p.schema || {}))}</span>${enumChips(p.schema || {})}</td><td>${escapeHtml(p.description || "")}</td></tr>`).join("")}</tbody></table>`;
  }

  function responseBlocks(responses) {
    return Object.entries(responses || {}).map(([code, raw]) => {
      const response = resolve(raw);
      const media = response.content && (response.content["application/json"] || Object.values(response.content)[0]);
      const sample = media && media.schema ? `<pre class="example">${escapeHtml(JSON.stringify(exampleOf(media.schema), null, 2))}</pre>` : "";
      const headers = Object.entries(response.headers || {}).map(([name, header]) => `<div class="type">${escapeHtml(name)}: ${escapeHtml(resolve(header).description || "")}</div>`).join("");
      return `<div class="response"><span class="status-code ${String(code).startsWith("2") ? "ok" : "bad"}">${escapeHtml(code)}</span> ${escapeHtml(response.description || "")}${headers}${sample}</div>`;
    }).join("");
  }

  function operationHtml(entry) {
    const { path, method, operation, item, index } = entry;
    const parameters = allParameters(item, operation);
    const requestBody = resolve(operation.requestBody || {});
    const body = requestBody.content && (requestBody.content["application/json"] || Object.values(requestBody.content)[0]);
    const bodyExample = body && body.schema ? JSON.stringify(exampleOf(body.schema), null, 2) : "";
    const fields = parameters.map((p, i) => `<label for="try${index}_${i}">${escapeHtml(p.name)}${p.required ? " *" : ""}</label>
      <input id="try${index}_${i}" data-in="${escapeHtml(p.in)}" data-name="${escapeHtml(p.name)}" placeholder="${escapeHtml((p.schema && (p.schema.example || p.schema.default)) || "")}" autocomplete="off">`).join("");
    const search = `${method} ${path} ${operation.summary || ""} ${operation.operationId || ""} ${operation.description || ""}`.toLowerCase();
    return `<details class="operation ${method}" data-index="${index}" data-search="${escapeHtml(search)}"${operation.deprecated ? ' data-deprecated="1"' : ""}>
      <summary><span class="method">${method.toUpperCase()}</span><span class="path">${escapeHtml(path)}</span><span class="summary-text">${escapeHtml(operation.summary || "")}</span></summary>
      <div class="operation-body">
        ${operation.description ? `<p class="page-intro">${escapeHtml(operation.description)}</p>` : ""}
        ${parameterTable(parameters)}
        ${body ? `<h4>Request body</h4>${propertyTable(body.schema)}<pre class="example">${escapeHtml(bodyExample)}</pre>` : ""}
        <h4>Responses</h4>${responseBlocks(operation.responses)}
        ${options.tryIt === false ? "" : `<div class="try"><h4>Try it out</h4><div class="fields">${fields}</div>
          ${body ? `<textarea rows="8" data-body aria-label="Request body">${escapeHtml(bodyExample)}</textarea>` : ""}
          <div><button class="primary" data-execute>Execute</button></div><div class="result" hidden></div></div>`}
      </div></details>`;
  }

  function serverBase() {
    const server = (spec.servers && spec.servers[0] && spec.servers[0].url) || "/";
    try { return new URL(server, baseUrl).href.replace(/\/$/, ""); } catch (_) { return baseUrl.replace(/\/$/, ""); }
  }

  async function execute(element, entry) {
    const result = element.querySelector(".result");
    const request = requestTarget(entry.path, [...element.querySelectorAll(".fields input")].map((input) => ({ in: input.dataset.in, name: input.dataset.name, value: input.value })));
    result.hidden = false;
    if (request.unfilled) { result.innerHTML = `<div class="meta">Fill in the path parameters first.</div>`; return; }
    const bodyField = element.querySelector("[data-body]");
    const address = serverBase() + request.target + (request.query ? "?" + request.query : "");
    const headers = new URL(address).origin === location.origin ? headersFor() : {};
    if (bodyField) headers["Content-Type"] = "application/json";
    const started = performance.now();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), OPENAPI_REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(address, { method: entry.method.toUpperCase(), headers, body: bodyField ? bodyField.value : undefined, signal: controller.signal });
      const text = await response.text();
      let shown = text;
      try { shown = JSON.stringify(JSON.parse(text), null, 2); } catch (_) { shown = text; }
      result.innerHTML = `<div class="meta"><span class="status-code ${response.ok ? "ok" : "bad"}">${response.status}</span> ${Math.round(performance.now() - started)} ms, ${escapeHtml(address)}</div><pre class="example">${escapeHtml(shown.slice(0, 20000))}</pre>`;
    } catch (error) {
      result.innerHTML = `<div class="meta">The request did not complete: ${escapeHtml(error.name === "AbortError" ? "timed out" : error.message)}.
        A browser only calls another address if that service allows it (CORS). Use the command line for services that do not.</div>`;
    } finally {
      clearTimeout(timer);
    }
  }

  function render(container) {
    const info = spec.info || {};
    const operations = collectOperations();
    const tags = [];
    for (const entry of operations) if (!tags.includes(entry.tag)) tags.push(entry.tag);
    const declared = (spec.tags || []).map((t) => t.name);
    tags.sort((a, b) => (declared.indexOf(a) < 0 ? 999 : declared.indexOf(a)) - (declared.indexOf(b) < 0 ? 999 : declared.indexOf(b)));
    const schemas = Object.entries((spec.components && spec.components.schemas) || spec.definitions || {});
    container.innerHTML = `<div class="api-view">
      <div class="api-head"><h2>${escapeHtml(info.title || "API")}<span class="version">v${escapeHtml(info.version || "?")}</span></h2>
        ${info.description ? `<p class="page-intro">${escapeHtml(info.description)}</p>` : ""}
        <div class="kpi-sub">${operations.length} endpoints, ${schemas.length} models${spec.servers && spec.servers.length ? `, server ${escapeHtml(spec.servers[0].url)}` : ""}</div></div>
      <div class="api-tools"><input type="search" data-api-filter placeholder="Filter ${operations.length} endpoints" aria-label="Filter endpoints" autocomplete="off">
        <button type="button" class="ghost" data-api-expand>Expand all</button><button type="button" class="ghost" data-api-collapse>Collapse all</button></div>
      <div data-api-empty class="empty-line" hidden>No endpoint matches.</div>
      ${tags.map((tag) => `<section class="api-tag" data-tag="${escapeHtml(tag)}"><h3 class="tag-heading">${escapeHtml(tag)}</h3>${operations.filter((e) => e.tag === tag).map(operationHtml).join("")}</section>`).join("")}
      ${schemas.length ? `<h3 class="tag-heading">Models</h3>${schemas.map(([name, schema]) => `<details class="model"><summary>${escapeHtml(name)}</summary>${propertyTable(schema)}<pre class="example">${escapeHtml(JSON.stringify(exampleOf(schema), null, 2))}</pre></details>`).join("")}` : ""}</div>`;
    container.querySelectorAll(".operation").forEach((element) => {
      const entry = operations[Number(element.dataset.index)];
      const button = element.querySelector("[data-execute]");
      if (button) button.addEventListener("click", () => execute(element, entry));
    });
    const filter = container.querySelector("[data-api-filter]");
    filter.addEventListener("input", () => {
      const words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;
      container.querySelectorAll(".operation").forEach((element) => {
        const match = words.every((word) => element.dataset.search.includes(word));
        element.hidden = !match;
        shown += match ? 1 : 0;
      });
      container.querySelectorAll(".api-tag").forEach((section) => { section.hidden = ![...section.querySelectorAll(".operation")].some((e) => !e.hidden); });
      container.querySelector("[data-api-empty]").hidden = shown > 0;
    });
    container.querySelector("[data-api-expand]").addEventListener("click", () => container.querySelectorAll(".operation:not([hidden])").forEach((d) => { d.open = true; }));
    container.querySelector("[data-api-collapse]").addEventListener("click", () => container.querySelectorAll(".operation").forEach((d) => { d.open = false; }));
    return { operations };
  }

  return { render, resolve, exampleOf };
}
