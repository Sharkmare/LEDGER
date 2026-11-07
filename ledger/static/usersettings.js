"use strict";

const SETTING_KEYS = ["hidden_types", "hidden_statuses", "sort"];
const DEFAULT_SORT = { field: "", direction: "asc" };

function defaultSetting(key) {
  return key === "sort" ? { ...DEFAULT_SORT } : [];
}

function cleanSetting(key, value, vocabulary) {
  if (key === "sort") {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    if (value.field !== "" && !vocabulary.sortFields.includes(value.field)) return null;
    return { field: value.field, direction: value.direction === "desc" ? "desc" : "asc" };
  }
  if (!Array.isArray(value)) return null;
  const known = key === "hidden_types" ? vocabulary.types : vocabulary.statuses;
  return known.filter((name) => value.includes(name));
}

function parseStoredSetting(key, text, vocabulary) {
  if (!text) return null;
  try { return cleanSetting(key, JSON.parse(text), vocabulary); } catch (_) { return null; }
}

function hasChoice(key, value) {
  if (value === null || value === undefined) return false;
  return key === "sort" ? Boolean(value.field) : value.length > 0;
}

function resolveSetting(key, serverValue, localValue) {
  if (serverValue !== null && serverValue !== undefined) return { value: serverValue, source: "server", upload: false };
  if (hasChoice(key, localValue)) return { value: localValue, source: "local", upload: true };
  return { value: defaultSetting(key), source: "default", upload: false };
}

function cachedTextsFor(cacheOwner, actor, texts) {
  const empty = Object.fromEntries(SETTING_KEYS.map((key) => [key, ""]));
  if (cacheOwner && cacheOwner.trim().toLowerCase() !== String(actor).trim().toLowerCase()) return empty;
  return { ...empty, ...texts };
}

function planSettings(serverSettings, storedText, vocabulary) {
  const reachable = Boolean(serverSettings) && typeof serverSettings === "object";
  const values = {};
  const uploads = [];
  for (const key of SETTING_KEYS) {
    const local = parseStoredSetting(key, storedText[key], vocabulary);
    const remote = reachable ? cleanSetting(key, serverSettings[key], vocabulary) : null;
    const decision = resolveSetting(key, remote, local);
    values[key] = decision.value;
    if (decision.upload && reachable) uploads.push(key);
  }
  return { values, uploads, reachable };
}

if (typeof module !== "undefined") module.exports = { SETTING_KEYS, cachedTextsFor, cleanSetting, parseStoredSetting, hasChoice, resolveSetting, planSettings, defaultSetting };
