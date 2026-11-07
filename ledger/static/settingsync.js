"use strict";

const SETTING_STORAGE = { hidden_types: "hiddenTypes", hidden_statuses: "hiddenStatuses", sort: "sort" };
const SETTING_STATE = { hidden_types: "hiddenTypes", hidden_statuses: "hiddenStatuses", sort: "sort" };
const SETTINGS_OWNER_STORAGE = "ledger.settingsOwner";
let settingsSyncRound = 0;

function settingVocabulary() {
  return { types: state.meta.types, statuses: state.meta.statuses, sortFields: SORT_FIELDS.map((field) => field.id) };
}

function storedSettingTexts() {
  const texts = {};
  for (const key of SETTING_KEYS) texts[key] = recall(STORAGE[SETTING_STORAGE[key]], "");
  return cachedTextsFor(recall(SETTINGS_OWNER_STORAGE, ""), actorName(), texts);
}

function applySettings(values) {
  remember(SETTINGS_OWNER_STORAGE, actorName());
  for (const key of SETTING_KEYS) {
    state[SETTING_STATE[key]] = values[key];
    remember(STORAGE[SETTING_STORAGE[key]], JSON.stringify(values[key]));
  }
}

async function fetchServerSettings() {
  try { return await api("GET", "/api/settings"); } catch (_) { return null; }
}

async function syncSettings() {
  const round = ++settingsSyncRound;
  const serverSettings = await fetchServerSettings();
  if (round !== settingsSyncRound) return;
  const plan = planSettings(serverSettings, storedSettingTexts(), settingVocabulary());
  applySettings(plan.values);
  renderTypeSettings();
  renderStatusSettings();
  for (const key of plan.uploads) await saveSetting(key, plan.values[key]);
}

async function saveSetting(key, value) {
  remember(SETTINGS_OWNER_STORAGE, actorName());
  remember(STORAGE[SETTING_STORAGE[key]], JSON.stringify(value));
  try { await api("PUT", `/api/settings/${key}`, { value }); } catch (error) { toast(`Could not save the setting for your name: ${error.message}`, true); }
}
