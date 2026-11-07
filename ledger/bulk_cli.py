from __future__ import annotations

import argparse
import json
import re
import sys

KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,9}-\d+$")
STDIN_MARKER = "-"
FIELD_FLAGS = ("status", "priority", "type", "assignee", "area", "iteration")


def add_parser(commands) -> None:
    bulk = commands.add_parser("bulk", help="change many tickets at once")
    bulk.add_argument("keys", nargs="*", help="ticket keys")
    bulk.add_argument("--keys-from", metavar="-", help="read keys from standard input (a list --json reply, or one key per line)")
    for name in FIELD_FLAGS:
        bulk.add_argument(f"--{name}")
    bulk.add_argument("--parent")
    bulk.add_argument("--add-label", action="append", default=[])
    bulk.add_argument("--rm-label", action="append", default=[])
    bulk.add_argument("--comment", default="")


def keys_from_text(text: str) -> list[str]:
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, list):
        return [item["key"] if isinstance(item, dict) and "key" in item else item for item in parsed]
    words = (line.split()[0] for line in text.splitlines() if line.strip())
    return [word for word in words if KEY_PATTERN.match(word)]


def collect_keys(arguments: argparse.Namespace, stdin=None) -> list[str]:
    keys = list(arguments.keys)
    if arguments.keys_from is not None:
        if arguments.keys_from != STDIN_MARKER:
            raise SystemExit("ledger: --keys-from only reads standard input, use --keys-from -")
        keys += keys_from_text((stdin or sys.stdin).read())
    if not keys:
        raise SystemExit("ledger: bulk needs ticket keys, for example bulk APP-1 APP-2 --status done, or --keys-from -")
    return keys


def collect_changes(arguments: argparse.Namespace) -> dict:
    changes = {name: getattr(arguments, name) for name in FIELD_FLAGS if getattr(arguments, name) is not None}
    if arguments.parent is not None:
        changes["parent_key"] = arguments.parent
    if arguments.add_label:
        changes["add_labels"] = arguments.add_label
    if arguments.rm_label:
        changes["remove_labels"] = arguments.rm_label
    if not changes and not arguments.comment:
        raise SystemExit("ledger: bulk needs a change or a comment, for example --status done")
    return changes


def run(arguments: argparse.Namespace, base: str, actor: str, call, stdin=None):
    payload = {"keys": collect_keys(arguments, stdin), "changes": collect_changes(arguments), "comment": arguments.comment}
    return call(base, "POST", "/api/tickets/bulk", actor, payload)


def render(result: dict) -> None:
    print(f"updated {len(result['updated'])}, unchanged {len(result['unchanged'])}, failed {len(result['failed'])}")
    for failure in result["failed"]:
        print(f"  {failure['key']}: {failure['error']}")


def exit_status(command: str, result) -> int:
    return 1 if command == "bulk" and result["failed"] else 0
