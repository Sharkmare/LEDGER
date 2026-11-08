"use strict";

if (typeof escapeHtml === "undefined") globalThis.escapeHtml = require("./escape.js").escapeHtml;

function fieldHtml(field, value) {
  const id = `form_${field.name}`;
  const attributes = `id="${id}" data-name="${field.name}"${field.required ? " required" : ""}${field.disabled ? " disabled" : ""}`;
  const shown = value === undefined || value === null ? "" : value;
  let control;
  if (field.kind === "select") {
    control = `<select ${attributes}>${field.options.map((o) => `<option value="${escapeHtml(o.value)}"${String(o.value) === String(shown) ? " selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}</select>`;
  } else if (field.kind === "textarea") {
    control = `<textarea ${attributes} rows="${field.rows || 4}">${escapeHtml(shown)}</textarea>`;
  } else if (field.kind === "checkbox") {
    return `<div class="field"><label><input type="checkbox" ${attributes}${shown ? " checked" : ""}> ${escapeHtml(field.label)}</label>${field.help ? `<span class="help">${escapeHtml(field.help)}</span>` : ""}</div>`;
  } else if (field.kind === "color") {
    const swatch = /^#[0-9a-f]{6}$/i.test(shown) ? shown : "#4cc2ff";
    control = `<div class="color-field"><input type="color" data-color-for="${id}" value="${swatch}" aria-label="Pick a colour"><input type="text" ${attributes} value="${escapeHtml(shown)}" placeholder="Automatic" autocomplete="off"></div>`;
  } else {
    const type = field.kind === "number" ? "number" : "text";
    control = `<input type="${type}" ${attributes} value="${escapeHtml(shown)}"${field.min !== undefined ? ` min="${field.min}"` : ""}${field.kind === "number" ? ' step="any"' : ""}${field.placeholder ? ` placeholder="${escapeHtml(field.placeholder)}"` : ""} autocomplete="off">`;
  }
  return `<div class="field"><label for="${id}">${escapeHtml(field.label)}</label>${control}${field.help ? `<span class="help">${escapeHtml(field.help)}</span>` : ""}</div>`;
}

function formBodyHtml(fields, values) {
  let html = "";
  let index = 0;
  while (index < fields.length) {
    const field = fields[index];
    if (field.group) { html += `<h3 class="group-title">${escapeHtml(field.group)}</h3>`; index += 1; continue; }
    if (field.row) {
      const rowFields = [];
      while (index < fields.length && fields[index].row === field.row) { rowFields.push(fields[index]); index += 1; }
      html += `<div class="field-row">${rowFields.map((f) => fieldHtml(f, values[f.name])).join("")}</div>`;
    } else {
      html += fieldHtml(field, values[field.name]);
      index += 1;
    }
  }
  return html;
}

if (typeof module !== "undefined") module.exports = { fieldHtml, formBodyHtml };
