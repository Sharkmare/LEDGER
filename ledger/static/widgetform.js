"use strict";

const FILTER_FORM_FIELDS = [
  { filter: "project", label: "Project", kind: "select", row: "f1", choices: "projects", any: "All" },
  { filter: "area", label: "Area", kind: "select", row: "f1", choices: "areas", any: "All" },
  { filter: "type", label: "Type", kind: "select", row: "f2", choices: "types", any: "Any" },
  { filter: "priority", label: "Priority", kind: "select", row: "f2", choices: "priorities", any: "Any" },
  { filter: "assignee", label: "Assignee", kind: "text", row: "f3" },
  { filter: "label", label: "Tag", kind: "text", row: "f3" },
  { filter: "open", label: "Only open tickets", kind: "checkbox" },
];
const WIDTH_OPTIONS = [{ value: "1", label: "One column" }, { value: "2", label: "Two columns" }, { value: "3", label: "Three columns" }];

function usableFilterFields(module) {
  return FILTER_FORM_FIELDS.filter((field) => module.filters.includes(field.filter));
}

function settingField(setting, choices) {
  const field = { name: setting.name, label: setting.label, kind: setting.kind };
  if (setting.help) field.help = setting.help;
  if (setting.kind === "number") field.min = setting.min;
  if (setting.kind === "select") field.options = setting.options;
  if (setting.kind === "iteration") {
    field.kind = "select";
    field.options = [{ value: "", label: setting.empty_label }, ...(choices.iterations || []).map((item) => ({ value: String(item.id), label: `${item.project} ${item.name}` }))];
  }
  return field;
}

function moduleFormFields(module, choices = {}) {
  const fields = [{ name: "title", label: "Title", kind: "text", placeholder: module.title }];
  fields.push({ name: "size", label: "Width", kind: "select", options: WIDTH_OPTIONS });
  for (const setting of module.settings) fields.push(settingField(setting, choices));
  const filterFields = usableFilterFields(module);
  if (filterFields.length) fields.push({ group: "Which tickets" });
  for (const filterField of filterFields) {
    const field = { name: `f_${filterField.filter}`, label: filterField.label, kind: filterField.kind };
    if (filterField.row) field.row = filterField.row;
    if (filterField.choices) field.options = [{ value: "", label: filterField.any }, ...(choices[filterField.choices] || [])];
    fields.push(field);
  }
  return fields;
}

function widgetFromValues(module, values, existing) {
  const widget = { kind: module.id, title: values.title.trim(), size: Number(values.size) };
  if (existing && existing.id) widget.id = existing.id;
  for (const setting of module.settings) {
    const value = values[setting.name];
    if (setting.kind === "checkbox") widget[setting.name] = !!value;
    else if (setting.kind === "number" || setting.kind === "iteration") { if (value !== undefined && value !== null && value !== "") widget[setting.name] = Number(value); }
    else if (value) widget[setting.name] = String(value).trim();
  }
  const filters = {};
  for (const field of usableFilterFields(module)) {
    const value = values[`f_${field.filter}`];
    if (value) filters[field.filter] = field.filter === "open" ? true : value;
  }
  widget.filters = filters;
  return widget;
}

function widgetValues(module, widget) {
  const values = { title: widget.title, size: String(widget.size) };
  for (const setting of module.settings) {
    const value = widget[setting.name];
    if (setting.kind === "checkbox") values[setting.name] = !!value;
    else if (setting.kind === "iteration") values[setting.name] = value ? String(value) : "";
    else values[setting.name] = value === undefined || value === null ? "" : value;
  }
  const filters = widget.filters || {};
  for (const field of usableFilterFields(module)) {
    const value = filters[field.filter];
    values[`f_${field.filter}`] = field.kind === "checkbox" ? !!value : value ? String(value) : "";
  }
  return values;
}

function newWidgetDefaults(module) {
  const widget = { title: "", size: module.size, filters: {} };
  for (const setting of module.settings) if (setting.default !== undefined) widget[setting.name] = setting.default;
  return widget;
}

if (typeof module !== "undefined") module.exports = { moduleFormFields, widgetFromValues, widgetValues, newWidgetDefaults, usableFilterFields };
