from __future__ import annotations

import datetime
import difflib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import miniyaml, store
from .organise import _clean_name
from .store import LedgerError, NotFound, _require_choice, _require_text

PAGE_TYPES = ("article", "tool")
PAGE_STATUSES = ("draft", "published", "archived")
SPACE_KINDS = ("docs", "tools")
TOOL_KINDS = ("cli", "api", "library", "service", "script", "app")
TOOL_LOCATIONS = ("machine", "external")
TOOL_STATUSES = ("active", "experimental", "deprecated")
SPEC_SOURCES = ("", "inline", "url", "file")
TOOLS_SPACE_KEY = "TOOLS"
TOOLS_SPACE_NAME = "Tools"
MAX_BODY_CHARS = 200_000
MAX_SPEC_BYTES = 5_000_000
SPEC_TIMEOUT_SECONDS = 10
SPEC_SUFFIXES = (".json", ".yaml", ".yml")
MAX_COMMANDS = 200
DEFAULT_REVIEW_DAYS = 90
SPACE_COLORS = ("#4cc2ff", "#5fd38d", "#ffc24c", "#b58cff", "#ff7a7a", "#4fd1c5", "#ff9a4c")
TICKET_KEY_IN_TEXT = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
WIKI_LINK_IN_TEXT = re.compile(r"\[\[([^\]\n]{1,200})\]\]")
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

PAGE_TEMPLATES = (
    {"id": "blank", "name": "Blank page", "description": "Start from nothing", "body": ""},
    {"id": "how-to", "name": "How-to guide", "description": "Steps that get one job done",
     "body": "One sentence on what this achieves and who it is for.\n\n## Before you start\n\n- \n\n## Steps\n\n1. \n2. \n3. \n\n## Check it worked\n\n\n## If something goes wrong\n\n"},
    {"id": "runbook", "name": "Runbook", "description": "What to do when a system misbehaves",
     "body": "> [!NOTE]\n> Owner and on-call route go here.\n\n## Symptoms\n\n- \n\n## Quick checks\n\n1. \n\n## Fix\n\n```\ncommand\n```\n\n## Escalate when\n\n- \n"},
    {"id": "decision", "name": "Decision record", "description": "A choice, the options and why one won",
     "body": "- Status: proposed\n- Date: \n- Deciders: \n\n## Context\n\n\n## Options\n\n| Option | Good | Bad |\n|---|---|---|\n|  |  |  |\n\n## Decision\n\n\n## Consequences\n\n"},
    {"id": "meeting", "name": "Meeting notes", "description": "Agenda, notes and follow-ups",
     "body": "Date: \nPeople: \n\n## Agenda\n\n- \n\n## Notes\n\n\n## Actions\n\n- [ ] \n"},
    {"id": "reference", "name": "Reference", "description": "Facts to look up, in tables",
     "body": "What this covers in one line.\n\n## Overview\n\n| Name | Meaning |\n|---|---|\n|  |  |\n\n## See also\n\n- [[Related page]]\n"},
)


def _today() -> str:
    return datetime.date.today().isoformat()


def _space_row(connection: sqlite3.Connection, space: Any) -> sqlite3.Row:
    if isinstance(space, bool) or space in (None, ""):
        raise LedgerError("a space is required")
    if isinstance(space, int) or str(space).strip().isdigit():
        row = connection.execute("SELECT * FROM kb_spaces WHERE id = ?", (int(space),)).fetchone()
    else:
        row = connection.execute("SELECT * FROM kb_spaces WHERE key = ?", (str(space).strip().upper(),)).fetchone()
        if not row and str(space).strip().upper() == TOOLS_SPACE_KEY:
            ensure_tools_space(connection)
            row = connection.execute("SELECT * FROM kb_spaces WHERE key = ?", (TOOLS_SPACE_KEY,)).fetchone()
    if not row:
        raise NotFound(f"no space {space}")
    return row


def _page_row(connection: sqlite3.Connection, page_id: Any) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM kb_pages WHERE id = ?", (page_id,)).fetchone()
    if not row:
        raise NotFound(f"no page {page_id}")
    return row


def has_search(connection: sqlite3.Connection) -> bool:
    return bool(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'kb_fts'").fetchone())


def _space_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    space = dict(row)
    counts = connection.execute(
        "SELECT COUNT(*) AS pages, MAX(updated) AS updated FROM kb_pages WHERE space_id = ? AND status != 'archived' AND translation_of IS NULL", (row["id"],)).fetchone()
    space["pages"], space["updated"] = counts["pages"], counts["updated"]
    return space


def ensure_tools_space(connection: sqlite3.Connection) -> dict:
    row = connection.execute("SELECT * FROM kb_spaces WHERE kind = 'tools'").fetchone()
    if not row:
        connection.execute("INSERT INTO kb_spaces (key, name, description, kind, color, created) VALUES (?, ?, ?, 'tools', ?, ?)",
                           (TOOLS_SPACE_KEY, TOOLS_SPACE_NAME, "Tools on this machine and external services, with an overview of what each can do", "#ffc24c", time.time()))
        connection.commit()
        row = connection.execute("SELECT * FROM kb_spaces WHERE kind = 'tools'").fetchone()
    return _space_dict(connection, row)


def create_space(connection: sqlite3.Connection, key: Any, name: Any, description: Any = "", color: Any = "") -> dict:
    key = str(key).strip().upper()
    if not store.PROJECT_KEY_PATTERN.match(key):
        raise LedgerError("space key is 2 to 10 capital letters or digits and starts with a letter")
    if key == TOOLS_SPACE_KEY:
        raise LedgerError(f"{TOOLS_SPACE_KEY} is the key of the built-in Tools space")
    name = _clean_name("name", name)
    if connection.execute("SELECT 1 FROM kb_spaces WHERE key = ? OR name = ? COLLATE NOCASE", (key, name)).fetchone():
        raise LedgerError(f"there is already a space with the key {key} or the name {name!r}")
    color = _require_text("color", color).strip() or SPACE_COLORS[connection.execute("SELECT COUNT(*) FROM kb_spaces").fetchone()[0] % len(SPACE_COLORS)]
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
        raise LedgerError("color must look like #4cc2ff")
    cursor = connection.execute("INSERT INTO kb_spaces (key, name, description, kind, color, created) VALUES (?, ?, ?, 'docs', ?, ?)",
                                (key, name, _require_text("description", description), color.lower(), time.time()))
    connection.commit()
    return get_space(connection, cursor.lastrowid)


def get_space(connection: sqlite3.Connection, space: Any) -> dict:
    return _space_dict(connection, _space_row(connection, space))


def list_spaces(connection: sqlite3.Connection) -> list[dict]:
    ensure_tools_space(connection)
    spaces = [_space_dict(connection, row) for row in connection.execute("SELECT * FROM kb_spaces")]
    return sorted(spaces, key=lambda space: (space["kind"] != "tools", space["name"].lower()))


def update_space(connection: sqlite3.Connection, space: Any, changes: dict) -> dict:
    row = _space_row(connection, space)
    unknown = sorted(set(changes) - {"name", "description", "color"})
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are name, description, color")
    name = _clean_name("name", changes["name"]) if "name" in changes else row["name"]
    if row["kind"] == "tools" and name != row["name"]:
        raise LedgerError("the Tools space keeps its name")
    description = _require_text("description", changes["description"]) if "description" in changes else row["description"]
    color = _require_text("color", changes["color"]).strip().lower() if "color" in changes else row["color"]
    if not re.match(r"^#[0-9a-f]{6}$", color):
        raise LedgerError("color must look like #4cc2ff")
    for other in connection.execute("SELECT id, name FROM kb_spaces"):
        if other["id"] != row["id"] and other["name"].lower() == name.lower():
            raise LedgerError(f"there is already a space named {name!r}")
    connection.execute("UPDATE kb_spaces SET name = ?, description = ?, color = ? WHERE id = ?", (name, description, color, row["id"]))
    connection.commit()
    return get_space(connection, row["id"])


def delete_space(connection: sqlite3.Connection, space: Any) -> None:
    row = _space_row(connection, space)
    if row["kind"] == "tools":
        raise LedgerError("the Tools space cannot be deleted")
    if connection.execute("SELECT 1 FROM kb_pages WHERE space_id = ?", (row["id"],)).fetchone():
        raise LedgerError("the space still has pages; move or delete them first")
    connection.execute("DELETE FROM kb_spaces WHERE id = ?", (row["id"],))
    connection.commit()


def _clean_url(field: str, value: Any) -> str:
    text = _require_text(field, value).strip()
    if text and not re.match(r"^https?://", text, re.IGNORECASE):
        raise LedgerError(f"{field} must start with http:// or https://")
    return text


def _clean_spec(spec: Any) -> dict:
    if not isinstance(spec, dict) or not ("openapi" in spec or "swagger" in spec) or not isinstance(spec.get("paths", {}), dict):
        raise LedgerError("an OpenAPI description needs an openapi (or swagger) version and a paths object")
    if len(json.dumps(spec)) > MAX_SPEC_BYTES:
        raise LedgerError("the OpenAPI description is too large")
    return spec


def clean_tool_meta(meta: Any, current: dict | None = None) -> dict:
    meta = {} if meta in (None, "") else meta
    if not isinstance(meta, dict):
        raise LedgerError("tool details must be an object")
    allowed = ("kind", "location", "path", "url", "invoke", "version", "owner", "tool_status", "docs", "commands", "openapi")
    unknown = sorted(set(meta) - set(allowed))
    if unknown:
        raise LedgerError(f"unknown tool field {', '.join(unknown)}; fields are {', '.join(allowed)}")
    base = {"kind": "cli", "location": "machine", "path": "", "url": "", "invoke": "", "version": "", "owner": "", "tool_status": "active", "docs": "",
            "commands": [], "openapi": {"source": "", "url": "", "path": "", "spec": None, "cached": None, "fetched_at": None, "error": "", "summary": None}}
    if "openapi" in meta and not isinstance(meta["openapi"], dict):
        raise LedgerError("openapi must be an object")
    merged = {**base, **(current or {}), **meta}
    merged["kind"] = _require_choice("kind", merged["kind"], TOOL_KINDS)
    merged["location"] = _require_choice("location", merged["location"], TOOL_LOCATIONS)
    merged["tool_status"] = _require_choice("tool_status", merged["tool_status"], TOOL_STATUSES)
    for field in ("path", "invoke", "version", "owner", "docs"):
        merged[field] = _require_text(field, merged[field]).strip()
    merged["url"] = _clean_url("url", merged["url"])
    commands = merged["commands"]
    if not isinstance(commands, list) or len(commands) > MAX_COMMANDS:
        raise LedgerError(f"commands must be a list of at most {MAX_COMMANDS} items")
    cleaned_commands = []
    for command in commands:
        if not isinstance(command, dict) or not str(command.get("name", "")).strip():
            raise LedgerError("each command needs a name")
        cleaned_commands.append({"name": str(command["name"]).strip(), "summary": str(command.get("summary", "")).strip(),
                                 "usage": str(command.get("usage", "")).strip()})
    merged["commands"] = cleaned_commands
    spec_settings = {**base["openapi"], **((current or {}).get("openapi") or {}), **(meta.get("openapi") or {})}
    source = _require_choice("openapi source", spec_settings["source"] or "", SPEC_SOURCES) if spec_settings["source"] else ""
    spec_settings["source"] = source
    spec_settings["url"] = _clean_url("openapi url", spec_settings["url"])
    spec_settings["path"] = _require_text("openapi path", spec_settings["path"]).strip()
    if source == "inline":
        spec_settings["spec"] = _clean_spec(spec_settings["spec"])
    elif source == "url" and not spec_settings["url"]:
        raise LedgerError("an OpenAPI source of url needs the address")
    elif source == "file" and not spec_settings["path"]:
        raise LedgerError("an OpenAPI source of file needs the path")
    if source != "inline":
        spec_settings["spec"] = None
    merged["openapi"] = spec_settings
    return merged


def spec_summary(spec: dict) -> dict:
    operations = [(method, path) for path, item in (spec.get("paths") or {}).items() if isinstance(item, dict) for method in item if method in HTTP_METHODS]
    info = spec.get("info") or {}
    return {"title": str(info.get("title", "")), "version": str(info.get("version", "")), "operations": len(operations),
            "paths": len(spec.get("paths") or {}), "schemas": len(((spec.get("components") or {}).get("schemas")) or spec.get("definitions") or {})}


def _parse_spec_text(text: str) -> dict:
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return miniyaml.loads(text)
    except miniyaml.YamlError as error:
        raise LedgerError(f"the description is neither JSON nor readable YAML: {error}") from None


def _fetch_spec(settings: dict) -> dict:
    if settings["source"] == "inline":
        return _clean_spec(settings["spec"])
    if settings["source"] == "url":
        request = urllib.request.Request(settings["url"], headers={"Accept": "application/json, application/yaml, */*", "User-Agent": "ledger-kb"})
        try:
            with urllib.request.urlopen(request, timeout=SPEC_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_SPEC_BYTES + 1)
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise LedgerError(f"could not fetch {settings['url']}: {getattr(error, 'reason', error)}") from None
    elif settings["source"] == "file":
        path = Path(settings["path"]).expanduser()
        if path.suffix.lower() not in SPEC_SUFFIXES:
            raise LedgerError(f"a description file must end in {', '.join(SPEC_SUFFIXES)}")
        if not path.is_file():
            raise LedgerError(f"there is no file at {path}")
        raw = path.read_bytes()[:MAX_SPEC_BYTES + 1]
    else:
        raise LedgerError("this tool has no OpenAPI description")
    if len(raw) > MAX_SPEC_BYTES:
        raise LedgerError("the OpenAPI description is larger than 5 MB")
    return _clean_spec(_parse_spec_text(raw.decode("utf-8", errors="replace")))


def _ticket_keys(text: str) -> list[str]:
    return sorted(set(TICKET_KEY_IN_TEXT.findall(text)))


def _wiki_titles(text: str) -> list[str]:
    return sorted({match.strip() for match in WIKI_LINK_IN_TEXT.findall(text) if match.strip()})


def _tool_search_text(meta: dict) -> str:
    parts = [meta.get("kind", ""), meta.get("location", ""), meta.get("path", ""), meta.get("url", ""), meta.get("invoke", ""), meta.get("owner", ""),
             meta.get("docs", "")]
    parts += [f"{command['name']} {command['summary']}" for command in meta.get("commands", [])]
    spec = (meta.get("openapi") or {}).get("spec") or (meta.get("openapi") or {}).get("cached")
    if spec:
        for path, item in list((spec.get("paths") or {}).items())[:400]:
            parts.append(path)
            if isinstance(item, dict):
                parts += [str(operation.get("summary", "")) for method, operation in item.items() if method in HTTP_METHODS and isinstance(operation, dict)]
    return " ".join(str(part) for part in parts if part)


def _reindex(connection: sqlite3.Connection, row: sqlite3.Row) -> None:
    if not has_search(connection):
        return
    meta = json.loads(row["meta"])
    connection.execute("DELETE FROM kb_fts WHERE rowid = ?", (row["id"],))
    if row["status"] == "archived":
        return
    connection.execute("INSERT INTO kb_fts (rowid, title, body, labels, extra) VALUES (?, ?, ?, ?, ?)",
                       (row["id"], row["title"], row["body"], " ".join(json.loads(row["labels"])), _tool_search_text(meta) if row["page_type"] == "tool" else ""))


def _record_links(connection: sqlite3.Connection, page_id: int, body: str) -> None:
    connection.execute("DELETE FROM kb_links WHERE page_id = ?", (page_id,))
    for key in _ticket_keys(body):
        connection.execute("INSERT OR IGNORE INTO kb_links (page_id, kind, target) VALUES (?, 'ticket', ?)", (page_id, key))
    for title in _wiki_titles(body):
        connection.execute("INSERT OR IGNORE INTO kb_links (page_id, kind, target) VALUES (?, 'page', ?)", (page_id, title.lower()))


def _save_version(connection: sqlite3.Connection, row: sqlite3.Row, author: str, comment: str) -> None:
    connection.execute("INSERT INTO kb_versions (page_id, version, title, body, meta, author, comment, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (row["id"], row["version"], row["title"], row["body"], row["meta"], author, comment, time.time()))


def _clean_title(value: Any) -> str:
    title = " ".join(_require_text("title", value).split())
    if not title:
        raise LedgerError("title is required")
    if len(title) > store.MAX_TITLE_CHARS:
        raise LedgerError(f"title is {len(title)} characters, the limit is {store.MAX_TITLE_CHARS}")
    return title


def _clean_body(value: Any) -> str:
    body = _require_text("body", value)
    if len(body) > MAX_BODY_CHARS:
        raise LedgerError(f"the page is {len(body)} characters, the limit is {MAX_BODY_CHARS}")
    return body


def _clean_review_by(value: Any) -> str:
    return store._clean_date("review_by", value)


CHILD_PREVIEW_LIMIT = 100
TITLE_LOOKUP_BATCH = 500
LEVEL_LIMIT_DEFAULT = 200
LEVEL_LIMIT_MAX = 1000
LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}(-[a-z0-9]+)*$")


def _clean_translation(connection: sqlite3.Connection, translation_of: Any, locale: Any, space_id: int, own_id: int | None) -> tuple[int | None, str]:
    base_given = translation_of not in (None, "")
    locale_given = _require_text("locale", locale or "").strip() != ""
    if not base_given and not locale_given:
        return None, ""
    if base_given != locale_given:
        raise LedgerError("a translation needs both translation_of and locale")
    locale = str(locale).strip().lower()
    if not LOCALE_PATTERN.match(locale):
        raise LedgerError("locale is a language code such as en, ja or zh-cn")
    base = _page_row(connection, translation_of)
    if base["space_id"] != space_id:
        raise LedgerError("a translation must be in the same space as its base page")
    if own_id is not None and base["id"] == own_id:
        raise LedgerError("a page cannot be a translation of itself")
    if base["translation_of"] is not None:
        raise LedgerError("translate the base page, not another translation")
    if own_id is not None and connection.execute("SELECT 1 FROM kb_pages WHERE translation_of = ?", (own_id,)).fetchone():
        raise LedgerError("a page that has translations cannot itself be a translation")
    duplicate = connection.execute("SELECT id FROM kb_pages WHERE translation_of = ? AND locale = ? AND id IS NOT ?", (base["id"], locale, own_id)).fetchone()
    if duplicate:
        raise LedgerError(f"the page already has a {locale} translation")
    return base["id"], locale


def _check_parent(connection: sqlite3.Connection, parent: Any, space_id: int, own_id: int | None) -> int | None:
    if parent in (None, "", 0):
        return None
    row = _page_row(connection, int(parent)) if (isinstance(parent, int) or str(parent).isdigit()) else None
    if row is None:
        raise LedgerError("parent must be a page id")
    if row["space_id"] != space_id:
        raise LedgerError("a page and its parent must be in the same space")
    cursor = row
    while cursor is not None:
        if own_id is not None and cursor["id"] == own_id:
            raise LedgerError("a page cannot be moved under itself or one of its own sub-pages")
        cursor = connection.execute("SELECT * FROM kb_pages WHERE id = ?", (cursor["parent_id"],)).fetchone() if cursor["parent_id"] else None
    return row["id"]


def create_page(connection: sqlite3.Connection, space: Any, title: Any, body: Any = "", parent: Any = None, labels: Any = None, status: Any = "published",
                meta: Any = None, author: str = "system", source: str | None = None, review_days: Any = None, comment: Any = "",
                translation_of: Any = None, locale: Any = "") -> dict:
    space_row = _space_row(connection, space)
    page_type = "tool" if space_row["kind"] == "tools" else "article"
    title, body = _clean_title(title), _clean_body(body)
    status = _require_choice("status", status, PAGE_STATUSES)
    parent_id = _check_parent(connection, parent, space_row["id"], None)
    translation_id, locale = _clean_translation(connection, translation_of, locale, space_row["id"], None)
    meta_value = clean_tool_meta(meta) if page_type == "tool" else {}
    if page_type == "article" and meta not in (None, "", {}):
        raise LedgerError("only pages in the Tools space carry tool details")
    if source is not None and connection.execute("SELECT 1 FROM kb_pages WHERE source = ?", (source,)).fetchone():
        raise LedgerError(f"source {source!r} is already a page")
    review_by = ""
    if review_days not in (None, ""):
        days = int(review_days)
        if days < 1:
            raise LedgerError("review days must be at least 1")
        review_by = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
    position = connection.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM kb_pages WHERE space_id = ? AND parent_id IS ?", (space_row["id"], parent_id)).fetchone()[0]
    now = time.time()
    cursor = connection.execute(
        "INSERT INTO kb_pages (space_id, parent_id, position, title, body, page_type, meta, status, labels, author, created, updated, review_by, source, translation_of, locale, version)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (space_row["id"], parent_id, position, title, body, page_type, json.dumps(meta_value, ensure_ascii=False), status,
         json.dumps(store._clean_labels(labels), ensure_ascii=False), author, now, now, review_by, source, translation_id, locale))
    row = _page_row(connection, cursor.lastrowid)
    _save_version(connection, row, author, _require_text("comment", comment) or "Created")
    _record_links(connection, row["id"], body)
    _reindex(connection, row)
    connection.commit()
    return get_page(connection, row["id"])


def _excerpt(body: str, length: int = 180) -> str:
    text = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    text = re.sub(r"[#>*`_|\[\]-]+", " ", text)
    text = " ".join(text.split())
    return text if len(text) <= length else text[:length].rsplit(" ", 1)[0] + "..."


def _tool_summary(meta: dict) -> dict:
    spec = (meta.get("openapi") or {})
    summary = spec.get("summary") or (spec_summary(spec["spec"]) if spec.get("spec") else None)
    return {"kind": meta.get("kind"), "location": meta.get("location"), "invoke": meta.get("invoke"), "version": meta.get("version"),
            "tool_status": meta.get("tool_status"), "path": meta.get("path"), "url": meta.get("url"), "has_openapi": bool(spec.get("source")),
            "operations": summary["operations"] if summary else None, "commands": len(meta.get("commands", []))}


def _summary_dict(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    meta = json.loads(row["meta"])
    today = _today()
    page = {"id": row["id"], "space_id": row["space_id"], "parent_id": row["parent_id"], "position": row["position"], "title": row["title"],
            "page_type": row["page_type"], "status": row["status"], "labels": json.loads(row["labels"]), "author": row["author"], "created": row["created"],
            "updated": row["updated"], "review_by": row["review_by"], "verified_by": row["verified_by"], "verified_at": row["verified_at"],
            "stale": bool(row["review_by"]) and row["review_by"] < today, "views": row["views"], "helpful": row["helpful"], "unhelpful": row["unhelpful"],
            "version": row["version"], "excerpt": _excerpt(row["body"]), "translation_of": row["translation_of"], "locale": row["locale"]}
    if row["page_type"] == "tool":
        page["tool"] = _tool_summary(meta)
    return page


def _breadcrumbs(connection: sqlite3.Connection, row: sqlite3.Row) -> list[dict]:
    trail, seen, cursor = [], set(), row
    while cursor["parent_id"] and cursor["parent_id"] not in seen:
        seen.add(cursor["parent_id"])
        cursor = connection.execute("SELECT id, title, parent_id FROM kb_pages WHERE id = ?", (cursor["parent_id"],)).fetchone()
        if not cursor:
            break
        trail.append({"id": cursor["id"], "title": cursor["title"]})
    return list(reversed(trail))


def _resolve_titles(connection: sqlite3.Connection, targets: list[str]) -> dict:
    wanted = list(dict.fromkeys(target.lower() for target in targets))
    found: dict[str, dict | None] = {target: None for target in wanted}
    for start in range(0, len(wanted), TITLE_LOOKUP_BATCH):
        batch = wanted[start:start + TITLE_LOOKUP_BATCH]
        rows = connection.execute(
            f"SELECT id, title FROM kb_pages WHERE title COLLATE NOCASE IN ({','.join('?' * len(batch))}) AND status != 'archived' ORDER BY id DESC", batch)
        for match in rows:
            found[match["title"].lower()] = {"id": match["id"], "title": match["title"]}
    return found


def _neighbours(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    scope = "space_id = ? AND parent_id IS ? AND status != 'archived' AND translation_of IS NULL"
    arguments = (row["space_id"], row["parent_id"])
    previous = connection.execute(
        f"SELECT id, title FROM kb_pages WHERE {scope} AND (position < ? OR (position = ? AND id < ?)) ORDER BY position DESC, id DESC LIMIT 1",
        (*arguments, row["position"], row["position"], row["id"])).fetchone()
    following = connection.execute(
        f"SELECT id, title FROM kb_pages WHERE {scope} AND (position > ? OR (position = ? AND id > ?)) ORDER BY position, id LIMIT 1",
        (*arguments, row["position"], row["position"], row["id"])).fetchone()
    return {"previous": dict(previous) if previous else None, "next": dict(following) if following else None}


def _languages(connection: sqlite3.Connection, row: sqlite3.Row) -> list[dict]:
    base_id = row["translation_of"] or row["id"]
    base = _page_row(connection, base_id)
    variants = connection.execute("SELECT id, title, locale FROM kb_pages WHERE translation_of = ? AND status != 'archived' ORDER BY locale", (base_id,)).fetchall()
    if not variants:
        return []
    entries = [{"id": base["id"], "title": base["title"], "locale": ""}] + [{"id": v["id"], "title": v["title"], "locale": v["locale"]} for v in variants]
    return [{**entry, "current": entry["id"] == row["id"]} for entry in entries]


def get_page(connection: sqlite3.Connection, page_id: Any, actor: str | None = None, count_view: bool = False) -> dict:
    row = _page_row(connection, page_id)
    if count_view:
        connection.execute("UPDATE kb_pages SET views = views + 1 WHERE id = ?", (row["id"],))
        connection.commit()
        row = _page_row(connection, page_id)
    page = _summary_dict(connection, row)
    space = _space_row(connection, row["space_id"])
    page.update({"body": row["body"], "meta": json.loads(row["meta"]), "source": row["source"], "space": {"id": space["id"], "key": space["key"], "name": space["name"],
                 "kind": space["kind"], "color": space["color"]}, "breadcrumbs": _breadcrumbs(connection, row)})
    page["children"] = [{"id": child["id"], "title": child["title"], "status": child["status"], "page_type": child["page_type"], "position": child["position"]}
                        for child in connection.execute(
                            "SELECT id, title, status, page_type, position FROM kb_pages WHERE parent_id = ? AND status != 'archived' AND translation_of IS NULL ORDER BY position, id LIMIT ?",
                            (row["id"], CHILD_PREVIEW_LIMIT))]
    page["children_total"] = connection.execute(
        "SELECT COUNT(*) FROM kb_pages WHERE parent_id = ? AND status != 'archived' AND translation_of IS NULL", (row["id"],)).fetchone()[0]
    page["siblings"] = _neighbours(connection, row)
    page["languages"] = _languages(connection, row)
    page["backlinks"] = [{"id": link["id"], "title": link["title"]} for link in connection.execute(
        "SELECT p.id, p.title FROM kb_links l JOIN kb_pages p ON p.id = l.page_id WHERE l.kind = 'page' AND l.target = ? AND p.id != ? AND p.status != 'archived' ORDER BY p.title",
        (row["title"].lower(), row["id"]))]
    tickets = []
    for link in connection.execute("SELECT target FROM kb_links WHERE page_id = ? AND kind = 'ticket' ORDER BY target", (row["id"],)):
        try:
            ticket = store.get_ticket(connection, link["target"])
            tickets.append({"key": ticket["key"], "title": ticket["title"], "status": ticket["status"]})
        except LedgerError:
            continue
    page["tickets"] = tickets
    page["wiki"] = _resolve_titles(connection, _wiki_titles(row["body"]))
    page["favourite"] = bool(actor and connection.execute("SELECT 1 FROM kb_favourites WHERE actor = ? AND page_id = ?", (actor, row["id"])).fetchone())
    page["my_feedback"] = None
    if actor:
        mine = connection.execute("SELECT helpful FROM kb_feedback WHERE actor = ? AND page_id = ?", (actor, row["id"])).fetchone()
        page["my_feedback"] = None if not mine else bool(mine["helpful"])
    return page


def update_page(connection: sqlite3.Connection, page_id: Any, changes: dict, author: str = "system", comment: Any = "") -> dict:
    row = _page_row(connection, page_id)
    allowed = ("title", "body", "parent", "position", "labels", "status", "meta", "review_by", "translation_of", "locale")
    unknown = sorted(set(changes) - set(allowed))
    if unknown:
        raise LedgerError(f"cannot edit {', '.join(unknown)}; editable fields are {', '.join(allowed)}")
    title = _clean_title(changes["title"]) if "title" in changes else row["title"]
    body = _clean_body(changes["body"]) if "body" in changes else row["body"]
    status = _require_choice("status", changes["status"], PAGE_STATUSES) if "status" in changes else row["status"]
    labels = json.dumps(store._clean_labels(changes["labels"]), ensure_ascii=False) if "labels" in changes else row["labels"]
    review_by = _clean_review_by(changes["review_by"]) if "review_by" in changes else row["review_by"]
    meta = row["meta"]
    if "meta" in changes:
        if row["page_type"] != "tool":
            raise LedgerError("only tool pages carry tool details")
        meta = json.dumps(clean_tool_meta(changes["meta"], json.loads(row["meta"])), ensure_ascii=False)
    parent_id, position = row["parent_id"], row["position"]
    if "parent" in changes:
        parent_id = _check_parent(connection, changes["parent"], row["space_id"], row["id"])
        if parent_id != row["parent_id"] and "position" not in changes:
            position = connection.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM kb_pages WHERE space_id = ? AND parent_id IS ?", (row["space_id"], parent_id)).fetchone()[0]
    if "position" in changes:
        if isinstance(changes["position"], bool) or not str(changes["position"]).lstrip("-").isdigit():
            raise LedgerError("position must be a whole number")
        position = int(changes["position"])
    translation_id, locale = row["translation_of"], row["locale"]
    if "translation_of" in changes and changes["translation_of"] in (None, "") and "locale" not in changes:
        locale = ""
    if "translation_of" in changes or "locale" in changes:
        translation_id, locale = _clean_translation(
            connection, changes.get("translation_of", translation_id), changes.get("locale", locale), row["space_id"], row["id"])
    content_changed = (title, body, meta) != (row["title"], row["body"], row["meta"])
    version = row["version"] + 1 if content_changed else row["version"]
    now = time.time()
    connection.execute(
        "UPDATE kb_pages SET title = ?, body = ?, meta = ?, status = ?, labels = ?, review_by = ?, parent_id = ?, position = ?, translation_of = ?, locale = ?, version = ?, updated = ?, author = ? WHERE id = ?",
        (title, body, meta, status, labels, review_by, parent_id, position, translation_id, locale, version, now if content_changed or status != row["status"] else row["updated"],
         author if content_changed else row["author"], row["id"]))
    updated = _page_row(connection, row["id"])
    if content_changed:
        _save_version(connection, updated, author, _require_text("comment", comment))
        _record_links(connection, row["id"], body)
    _reindex(connection, updated)
    connection.commit()
    return get_page(connection, row["id"])


def delete_page(connection: sqlite3.Connection, page_id: Any, cascade: bool = False) -> dict:
    row = _page_row(connection, page_id)
    children = [child["id"] for child in connection.execute("SELECT id FROM kb_pages WHERE parent_id = ? AND translation_of IS NULL", (row["id"],))]
    if children and not cascade:
        raise LedgerError("the page has sub-pages; move them, delete them first, or delete with cascade")
    found, stack = [], [row["id"]]
    while stack:
        current = stack.pop()
        found.append(current)
        stack += [child["id"] for child in connection.execute("SELECT id FROM kb_pages WHERE parent_id = ? OR translation_of = ?", (current, current))]
    for current in reversed(found):
        for table in ("kb_versions", "kb_links", "kb_feedback", "kb_favourites"):
            connection.execute(f"DELETE FROM {table} WHERE page_id = ?", (current,))
        if has_search(connection):
            connection.execute("DELETE FROM kb_fts WHERE rowid = ?", (current,))
        connection.execute("DELETE FROM kb_pages WHERE id = ?", (current,))
    connection.commit()
    return {"deleted": row["id"], "pages_removed": len(found)}


def list_pages(connection: sqlite3.Connection, space: Any = None, parent: Any = "any", status: Any = None, label: Any = None, page_type: Any = None,
               stale: bool = False, favourite_of: str | None = None, limit: int = 200, order: str = "updated", tool_kind: Any = None,
               location: Any = None, translations: bool = False) -> list[dict]:
    clauses, parameters = [], []
    if not translations:
        clauses.append("translation_of IS NULL")
    if space not in (None, ""):
        clauses.append("space_id = ?")
        parameters.append(_space_row(connection, space)["id"])
    if parent != "any":
        clauses.append("parent_id IS ?")
        parameters.append(None if parent in (None, "", "root") else int(parent))
    if status:
        clauses.append("status = ?")
        parameters.append(_require_choice("status", status, PAGE_STATUSES))
    else:
        clauses.append("status != 'archived'")
    if page_type:
        clauses.append("page_type = ?")
        parameters.append(_require_choice("type", page_type, PAGE_TYPES))
    if label:
        clauses.append("EXISTS (SELECT 1 FROM json_each(kb_pages.labels) WHERE json_each.value = ?)")
        parameters.append(str(label).strip().lower())
    if stale:
        clauses.append("review_by != '' AND review_by < ?")
        parameters.append(_today())
    if favourite_of:
        clauses.append("id IN (SELECT page_id FROM kb_favourites WHERE actor = ?)")
        parameters.append(favourite_of)
    if tool_kind:
        clauses.append("json_extract(meta, '$.kind') = ?")
        parameters.append(_require_choice("kind", tool_kind, TOOL_KINDS))
    if location:
        clauses.append("json_extract(meta, '$.location') = ?")
        parameters.append(_require_choice("location", location, TOOL_LOCATIONS))
    ordering = {"updated": "updated DESC", "title": "title COLLATE NOCASE", "views": "views DESC, updated DESC", "tree": "position, id"}.get(order)
    if ordering is None:
        raise LedgerError("order must be updated, title, views or tree")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(f"SELECT * FROM kb_pages {where} ORDER BY {ordering} LIMIT ?", (*parameters, limit)).fetchall()
    return [_summary_dict(connection, row) for row in rows]


def level(connection: sqlite3.Connection, space: Any, parent: Any = None, offset: Any = 0, limit: Any = LEVEL_LIMIT_DEFAULT) -> dict:
    space_row = _space_row(connection, space)
    parent_id = None if parent in (None, "", "root") else _check_parent(connection, parent, space_row["id"], None)
    for name, value in (("offset", offset), ("limit", limit)):
        if isinstance(value, bool) or not str(value).isdigit():
            raise LedgerError(f"{name} must be a whole number")
    offset, limit = int(offset), min(max(int(limit), 1), LEVEL_LIMIT_MAX)
    scope = "space_id = ? AND parent_id IS ? AND status != 'archived' AND translation_of IS NULL"
    total = connection.execute(f"SELECT COUNT(*) FROM kb_pages WHERE {scope}", (space_row["id"], parent_id)).fetchone()[0]
    rows = connection.execute(
        f"SELECT p.id, p.parent_id, p.position, p.title, p.page_type, p.status,"
        f" (SELECT COUNT(*) FROM kb_pages c WHERE c.parent_id = p.id AND c.status != 'archived' AND c.translation_of IS NULL) AS child_count"
        f" FROM kb_pages p WHERE p.{scope.replace(' AND ', ' AND p.')} ORDER BY p.position, p.id LIMIT ? OFFSET ?",
        (space_row["id"], parent_id, limit, offset)).fetchall()
    return {"total": total, "offset": offset, "items": [dict(row) for row in rows]}


def tree(connection: sqlite3.Connection, space: Any) -> list[dict]:
    space_row = _space_row(connection, space)
    rows = connection.execute("SELECT * FROM kb_pages WHERE space_id = ? AND status != 'archived' AND translation_of IS NULL ORDER BY position, id", (space_row["id"],)).fetchall()
    nodes = {row["id"]: {**_summary_dict(connection, row), "children": []} for row in rows}
    roots = []
    for row in rows:
        node = nodes[row["id"]]
        if row["parent_id"] in nodes:
            nodes[row["parent_id"]]["children"].append(node)
        else:
            roots.append(node)
    return roots


def list_versions(connection: sqlite3.Connection, page_id: Any) -> list[dict]:
    row = _page_row(connection, page_id)
    return [{"version": v["version"], "title": v["title"], "author": v["author"], "comment": v["comment"], "created": v["created"], "size": len(v["body"])}
            for v in connection.execute("SELECT * FROM kb_versions WHERE page_id = ? ORDER BY version DESC", (row["id"],))]


def get_version(connection: sqlite3.Connection, page_id: Any, version: Any) -> dict:
    row = _page_row(connection, page_id)
    found = connection.execute("SELECT * FROM kb_versions WHERE page_id = ? AND version = ?", (row["id"], int(version))).fetchone() if str(version).isdigit() else None
    if not found:
        raise NotFound(f"page {row['id']} has no version {version}")
    return {"version": found["version"], "title": found["title"], "body": found["body"], "meta": json.loads(found["meta"]), "author": found["author"],
            "comment": found["comment"], "created": found["created"]}


def diff_versions(connection: sqlite3.Connection, page_id: Any, older: Any, newer: Any) -> dict:
    first, second = get_version(connection, page_id, older), get_version(connection, page_id, newer)
    left, right = first["body"].splitlines(), second["body"].splitlines()
    lines = []
    for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes():
        if tag == "equal":
            lines += [{"op": "equal", "text": text} for text in left[a0:a1]]
            continue
        lines += [{"op": "delete", "text": text} for text in left[a0:a1]]
        lines += [{"op": "insert", "text": text} for text in right[b0:b1]]
    return {"from": first["version"], "to": second["version"], "title_changed": first["title"] != second["title"], "lines": lines,
            "added": sum(1 for line in lines if line["op"] == "insert"), "removed": sum(1 for line in lines if line["op"] == "delete")}


def restore_version(connection: sqlite3.Connection, page_id: Any, version: Any, author: str = "system") -> dict:
    old = get_version(connection, page_id, version)
    changes = {"title": old["title"], "body": old["body"]}
    if _page_row(connection, page_id)["page_type"] == "tool":
        changes["meta"] = old["meta"]
    return update_page(connection, page_id, changes, author, f"Restored version {old['version']}")


def record_feedback(connection: sqlite3.Connection, page_id: Any, actor: str, helpful: Any, comment: Any = "") -> dict:
    row = _page_row(connection, page_id)
    if not isinstance(helpful, bool):
        raise LedgerError("helpful must be true or false")
    connection.execute(
        "INSERT INTO kb_feedback (page_id, actor, helpful, comment, created) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(page_id, actor) DO UPDATE SET helpful = excluded.helpful, comment = excluded.comment, created = excluded.created",
        (row["id"], actor, int(helpful), _require_text("comment", comment), time.time()))
    counts = connection.execute("SELECT SUM(helpful) AS yes, COUNT(*) AS total FROM kb_feedback WHERE page_id = ?", (row["id"],)).fetchone()
    connection.execute("UPDATE kb_pages SET helpful = ?, unhelpful = ? WHERE id = ?", (counts["yes"] or 0, counts["total"] - (counts["yes"] or 0), row["id"]))
    connection.commit()
    return get_page(connection, row["id"], actor)


def list_feedback(connection: sqlite3.Connection, page_id: Any) -> list[dict]:
    row = _page_row(connection, page_id)
    return [{"actor": f["actor"], "helpful": bool(f["helpful"]), "comment": f["comment"], "created": f["created"]}
            for f in connection.execute("SELECT * FROM kb_feedback WHERE page_id = ? AND comment != '' ORDER BY created DESC", (row["id"],))]


def toggle_favourite(connection: sqlite3.Connection, page_id: Any, actor: str) -> dict:
    row = _page_row(connection, page_id)
    if connection.execute("SELECT 1 FROM kb_favourites WHERE actor = ? AND page_id = ?", (actor, row["id"])).fetchone():
        connection.execute("DELETE FROM kb_favourites WHERE actor = ? AND page_id = ?", (actor, row["id"]))
    else:
        connection.execute("INSERT INTO kb_favourites (actor, page_id, created) VALUES (?, ?, ?)", (actor, row["id"], time.time()))
    connection.commit()
    return get_page(connection, row["id"], actor)


def verify_page(connection: sqlite3.Connection, page_id: Any, actor: str, days: Any = DEFAULT_REVIEW_DAYS) -> dict:
    row = _page_row(connection, page_id)
    count = int(days) if str(days).lstrip("-").isdigit() else 0
    if count < 1:
        raise LedgerError("review days must be a whole number of at least 1")
    review_by = (datetime.date.today() + datetime.timedelta(days=count)).isoformat()
    connection.execute("UPDATE kb_pages SET verified_by = ?, verified_at = ?, review_by = ? WHERE id = ?", (actor, time.time(), review_by, row["id"]))
    connection.commit()
    return get_page(connection, row["id"], actor)


def _match_expression(query: str, joiner: str) -> str:
    tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
    return f" {joiner} ".join(f'"{token}"*' for token in tokens[:12])


def search(connection: sqlite3.Connection, query: Any, space: Any = None, page_type: Any = None, limit: int = 20) -> list[dict]:
    text = _require_text("q", query).strip()
    if not text:
        return []
    clauses, parameters = ["p.status != 'archived'"], []
    if space not in (None, ""):
        clauses.append("p.space_id = ?")
        parameters.append(_space_row(connection, space)["id"])
    if page_type:
        clauses.append("p.page_type = ?")
        parameters.append(_require_choice("type", page_type, PAGE_TYPES))
    results: list[dict] = []
    if has_search(connection):
        for joiner in ("AND", "OR"):
            expression = _match_expression(text, joiner)
            if not expression:
                break
            rows = connection.execute(
                "SELECT p.id, p.title, p.page_type, p.space_id, snippet(kb_fts, 1, char(1), char(2), '...', 14) AS snippet, bm25(kb_fts, 8.0, 1.0, 4.0, 2.0) AS rank"
                f" FROM kb_fts JOIN kb_pages p ON p.id = kb_fts.rowid WHERE kb_fts MATCH ? AND {' AND '.join(clauses)} ORDER BY rank LIMIT ?",
                (expression, *parameters, limit)).fetchall()
            results = [dict(row) for row in rows]
            if results:
                break
    else:
        like = f"%{text}%"
        rows = connection.execute(
            f"SELECT p.id, p.title, p.page_type, p.space_id, substr(p.body, 1, 160) AS snippet, 0 AS rank FROM kb_pages p WHERE (p.title LIKE ? OR p.body LIKE ?) AND {' AND '.join(clauses)} LIMIT ?",
            (like, like, *parameters, limit)).fetchall()
        results = [dict(row) for row in rows]
    spaces = {row["id"]: row for row in connection.execute("SELECT * FROM kb_spaces")}
    for result in results:
        space_row = spaces[result.pop("space_id")]
        result["space"] = {"id": space_row["id"], "key": space_row["key"], "name": space_row["name"], "color": space_row["color"], "kind": space_row["kind"]}
    return results


def _tool_settings(connection: sqlite3.Connection, page_id: Any) -> tuple[sqlite3.Row, dict, dict]:
    row = _page_row(connection, page_id)
    if row["page_type"] != "tool":
        raise LedgerError("only tool pages have an OpenAPI description")
    meta = json.loads(row["meta"])
    return row, meta, meta["openapi"]


def _spec_result(settings: dict) -> dict:
    return {"spec": settings["spec"] if settings["source"] == "inline" else settings["cached"], "source": settings["source"],
            "fetched_at": None if settings["source"] == "inline" else settings["fetched_at"], "error": settings["error"]}


def spec_plan(connection: sqlite3.Connection, page_id: Any, refresh: bool = False) -> dict:
    _row, _meta, settings = _tool_settings(connection, page_id)
    if not settings["source"]:
        raise NotFound("this tool has no OpenAPI description; add one in its details")
    if settings["source"] == "inline" or (settings["cached"] and not refresh):
        return {"result": _spec_result(settings)}
    return {"fetch": {key: settings[key] for key in ("source", "url", "path", "spec")}}


def fetch_spec(settings: dict) -> dict:
    return _fetch_spec(settings)


def spec_commit(connection: sqlite3.Connection, page_id: Any, spec: dict | None, error: str = "") -> dict:
    row, meta, settings = _tool_settings(connection, page_id)
    if error:
        settings["error"] = error
    else:
        settings.update(cached=spec, fetched_at=time.time(), error="", summary=spec_summary(spec))
    connection.execute("UPDATE kb_pages SET meta = ? WHERE id = ?", (json.dumps(meta, ensure_ascii=False), row["id"]))
    _reindex(connection, _page_row(connection, row["id"]))
    connection.commit()
    if error and not settings["cached"]:
        raise LedgerError(error)
    return _spec_result(settings)


def tool_spec(connection: sqlite3.Connection, page_id: Any, refresh: bool = False) -> dict:
    plan = spec_plan(connection, page_id, refresh)
    if "result" in plan:
        return plan["result"]
    try:
        spec, error = fetch_spec(plan["fetch"]), ""
    except LedgerError as problem:
        spec, error = None, str(problem)
    return spec_commit(connection, page_id, spec, error)


def overview(connection: sqlite3.Connection, actor: str | None = None) -> dict:
    ensure_tools_space(connection)
    today = _today()
    return {
        "spaces": list_spaces(connection),
        "recent": list_pages(connection, limit=8, order="updated"),
        "popular": list_pages(connection, limit=6, order="views"),
        "favourites": list_pages(connection, favourite_of=actor, limit=12) if actor else [],
        "needs_review": list_pages(connection, stale=True, limit=8),
        "drafts": list_pages(connection, status="draft", limit=8),
        "counts": {"pages": connection.execute("SELECT COUNT(*) FROM kb_pages WHERE status != 'archived' AND translation_of IS NULL").fetchone()[0],
                   "tools": connection.execute("SELECT COUNT(*) FROM kb_pages WHERE page_type = 'tool' AND status != 'archived'").fetchone()[0],
                   "stale": connection.execute("SELECT COUNT(*) FROM kb_pages WHERE review_by != '' AND review_by < ? AND status != 'archived'", (today,)).fetchone()[0]},
        "search": has_search(connection),
    }


def pages_mentioning(connection: sqlite3.Connection, ticket_key: Any) -> list[dict]:
    project_key, number = store.parse_ticket_key(_require_text("ticket", ticket_key))
    rows = connection.execute(
        "SELECT p.* FROM kb_links l JOIN kb_pages p ON p.id = l.page_id WHERE l.kind = 'ticket' AND l.target = ? AND p.status != 'archived' ORDER BY p.updated DESC",
        (f"{project_key}-{number}",)).fetchall()
    return [_summary_dict(connection, row) for row in rows]


def find_everything(connection: sqlite3.Connection, query: Any, limit: int = 8) -> dict:
    text = _require_text("q", query).strip()
    pages = search(connection, text, limit=limit) if text else []
    tickets = store.list_tickets(connection, query=text, limit=limit) if text else []
    return {"query": text,
            "pages": [{"id": p["id"], "title": p["title"], "snippet": p["snippet"], "space": p["space"], "page_type": p["page_type"]} for p in pages if p["page_type"] == "article"],
            "tools": [{"id": p["id"], "title": p["title"], "snippet": p["snippet"], "space": p["space"]} for p in pages if p["page_type"] == "tool"],
            "tickets": [{"key": t["key"], "title": t["title"], "status": t["status"], "priority": t["priority"]} for t in tickets]}
