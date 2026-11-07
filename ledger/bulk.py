from __future__ import annotations

import sqlite3

from . import store

MAX_BULK_KEYS = 200
LABEL_CHANGES = ("add_labels", "remove_labels")


def clean_keys(keys) -> list[str]:
    if not isinstance(keys, list) or not keys:
        raise store.LedgerError("keys must be a non-empty list of ticket keys")
    seen: dict[str, None] = {}
    for key in keys:
        if not isinstance(key, str) or not key.strip():
            raise store.LedgerError("every key must be a ticket key such as APP-1")
        seen.setdefault(key.strip().upper(), None)
    if len(seen) > MAX_BULK_KEYS:
        raise store.LedgerError(f"at most {MAX_BULK_KEYS} tickets per bulk change")
    return list(seen)


def clean_changes(changes, comment: str) -> tuple[dict, str]:
    if changes is None:
        changes = {}
    if not isinstance(changes, dict):
        raise store.LedgerError("changes must be an object")
    if comment is None:
        comment = ""
    if not isinstance(comment, str):
        raise store.LedgerError("comment must be text")
    comment = comment.strip()
    if not changes and not comment:
        raise store.LedgerError("give changes, a comment, or both")
    unknown = sorted(set(changes) - set(store.EDITABLE_FIELDS) - set(LABEL_CHANGES))
    if unknown:
        allowed = ", ".join((*store.EDITABLE_FIELDS, *LABEL_CHANGES))
        raise store.LedgerError(f"cannot change {', '.join(unknown)}; allowed fields are {allowed}")
    return changes, comment


def changes_for(ticket: dict, changes: dict) -> dict:
    plain = {field: value for field, value in changes.items() if field not in LABEL_CHANGES}
    if "add_labels" in changes or "remove_labels" in changes:
        labels = set(store._clean_labels(plain["labels"])) if "labels" in plain else set(ticket["labels"])
        labels |= set(store._clean_labels(changes.get("add_labels") or []))
        labels -= set(store._clean_labels(changes.get("remove_labels") or []))
        plain["labels"] = sorted(labels)
    return plain


def update(connection: sqlite3.Connection, keys, changes, actor: str, comment: str = "") -> dict:
    ordered = clean_keys(keys)
    changes, comment = clean_changes(changes, comment)
    updated: list[str] = []
    unchanged: list[str] = []
    failed: list[dict] = []
    for key in ordered:
        try:
            before = store.get_ticket(connection, key)
            applied = changes_for(before, changes)
            if comment and applied.get("status") == "done":
                applied["comment"] = comment
            after = store.update_ticket(connection, key, applied, actor=actor) if changes else before
            if comment and len(after["comments"]) == len(before["comments"]):
                store.add_comment(connection, key, actor, comment)
        except store.LedgerError as error:
            failed.append({"key": key, "error": str(error)})
            continue
        (updated if bool(changes) and after != before else unchanged).append(key)
    return {"updated": updated, "failed": failed, "unchanged": unchanged}
