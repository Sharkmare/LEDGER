from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from . import store
from .store import LedgerError

ANONYMOUS = "anonymous"
SORT_FIELDS = ("key", "title", "status", "priority", "type", "assignee", "estimate", "updated")
SORT_DIRECTIONS = ("asc", "desc")
SETTING_KEYS = ("hidden_types", "hidden_statuses", "sort")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_settings (
    actor TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated REAL NOT NULL,
    PRIMARY KEY (actor, key)
);
"""


def ensure_table(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def person(name: Any) -> str:
    cleaned = str(name or "").strip().lower()
    if not cleaned or cleaned == ANONYMOUS:
        raise LedgerError("settings follow a name: set your name in the profile menu first")
    return cleaned


def _check_key(key: Any) -> str:
    if key not in SETTING_KEYS:
        raise LedgerError(f"unknown setting {key!r}; use one of {', '.join(SETTING_KEYS)}")
    return key


def _clean_choices(key: str, value: Any, allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LedgerError(f"{key} must be a list of names")
    unknown = [item for item in value if item not in allowed]
    if unknown:
        raise LedgerError(f"{key} has unknown values {', '.join(unknown)}; use {', '.join(allowed)}")
    return [item for item in allowed if item in value]


def _clean_sort(value: Any) -> dict:
    if not isinstance(value, dict):
        raise LedgerError("sort must be an object with field and direction")
    field = value.get("field", "")
    direction = value.get("direction", "asc")
    if field != "" and field not in SORT_FIELDS:
        raise LedgerError(f"sort field must be empty or one of {', '.join(SORT_FIELDS)}")
    if direction not in SORT_DIRECTIONS:
        raise LedgerError(f"sort direction must be one of {', '.join(SORT_DIRECTIONS)}")
    return {"field": field, "direction": direction}


def clean_value(key: Any, value: Any) -> Any:
    key = _check_key(key)
    if key == "hidden_types":
        return _clean_choices(key, value, tuple(store.TICKET_TYPES))
    if key == "hidden_statuses":
        return _clean_choices(key, value, tuple(store.STATUSES))
    return _clean_sort(value)


def list_settings(connection: sqlite3.Connection, actor: Any) -> dict:
    rows = connection.execute("SELECT key, value FROM user_settings WHERE actor = ?", (person(actor),)).fetchall()
    return {row["key"]: json.loads(row["value"]) for row in rows if row["key"] in SETTING_KEYS}


def set_setting(connection: sqlite3.Connection, actor: Any, key: Any, value: Any) -> dict:
    owner = person(actor)
    cleaned = clean_value(key, value)
    connection.execute(
        "INSERT INTO user_settings (actor, key, value, updated) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(actor, key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
        (owner, key, json.dumps(cleaned), time.time()))
    connection.commit()
    return list_settings(connection, owner)


def clear_setting(connection: sqlite3.Connection, actor: Any, key: Any) -> dict:
    owner = person(actor)
    connection.execute("DELETE FROM user_settings WHERE actor = ? AND key = ?", (owner, _check_key(key)))
    connection.commit()
    return list_settings(connection, owner)


def _json(description: str, schema: dict) -> dict:
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def openapi_schemas() -> dict:
    return {"UserSettings": {"type": "object", "description": "The caller's saved view settings; a key is absent until it is set", "properties": {
        "hidden_types": {"type": "array", "items": {"type": "string", "enum": list(store.TICKET_TYPES)}},
        "hidden_statuses": {"type": "array", "items": {"type": "string", "enum": list(store.STATUSES)}},
        "sort": {"type": "object", "properties": {"field": {"type": "string", "enum": ["", *SORT_FIELDS]},
                                                  "direction": {"type": "string", "enum": list(SORT_DIRECTIONS)}}}}},
        "UserSettingValue": {"type": "object", "required": ["value"], "properties": {"value": {"description": "The new value; its shape depends on the key"}}}}


def openapi_paths() -> dict:
    refused = _json("The setting or its value was refused, or no name was sent; the message says why", {"$ref": "#/components/schemas/Error"})
    key = {"name": "key", "in": "path", "required": True, "description": "One of " + ", ".join(SETTING_KEYS),
           "schema": {"type": "string", "enum": list(SETTING_KEYS)}}
    saved = _json("All of the caller's settings", {"$ref": "#/components/schemas/UserSettings"})
    return {
        "/api/settings": {"get": {"tags": ["Settings"], "summary": "Read the caller's view settings, keyed by the X-Ledger-Actor name",
                                  "operationId": "listSettings", "responses": {"200": saved, "400": refused}}},
        "/api/settings/{key}": {
            "put": {"tags": ["Settings"], "summary": "Set one view setting", "operationId": "setSetting", "parameters": [key],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserSettingValue"}}}},
                    "responses": {"200": saved, "400": refused}},
            "delete": {"tags": ["Settings"], "summary": "Clear one view setting", "operationId": "clearSetting", "parameters": [key],
                       "responses": {"200": saved, "400": refused}}},
    }
