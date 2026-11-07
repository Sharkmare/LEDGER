from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

DEFAULT_BASE = "http://127.0.0.1:6680"
REQUEST_TIMEOUT_SECONDS = 15
LIST_FILTERS = ("project", "status", "assignee", "type", "priority", "label", "source", "area", "iteration")
EDIT_FIELDS = ("title", "body", "type", "priority", "assignee", "labels", "due", "status", "start", "estimate", "area", "iteration")
PLANNING_COMMANDS = ("overview", "tree", "plan", "roadmap", "project-set", "question", "area", "board", "iteration", "tag", "template", "dashboard", "metric",
                     "kb-space", "kb-page", "kb-tool", "kb-search", "find", "people", "person-add", "person-rm", "queue")


def default_actor() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "anonymous"


def call(base: str, method: str, path: str, actor: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base.rstrip("/") + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-Ledger-Actor": actor})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(raw).get("error", error.reason)
        except ValueError:
            message = f"{error.code} {error.reason}"
        raise SystemExit(f"ledger: {message}")
    except urllib.error.URLError as error:
        raise SystemExit(f"ledger: cannot reach {base} ({error.reason}). Start the server with: python -m ledger.server")


def drop_empty(values: dict) -> dict:
    return {key: value for key, value in values.items() if value not in (None, "")}


def when(stamp: float) -> str:
    return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")


def ticket_line(ticket: dict) -> str:
    assignee = f" @{ticket['assignee']}" if ticket["assignee"] else ""
    labels = f" [{','.join(ticket['labels'])}]" if ticket["labels"] else ""
    questions = f" ?{ticket['open_questions']}" if ticket.get("open_questions") else ""
    return f"{ticket['key']:<9} {ticket['status']:<11} {ticket['priority']:<8} {ticket['type']:<8} {ticket['title']}{assignee}{labels}{questions}"


def print_ticket(ticket: dict, events: list | None = None) -> None:
    print(f"{ticket['key']}  {ticket['title']}")
    print(f"  type {ticket['type']}  status {ticket['status']}  priority {ticket['priority']}  "
          f"assignee {ticket['assignee'] or '-'}  labels {','.join(ticket['labels']) or '-'}")
    placement = [f"{name} {ticket[name]}" for name in ("area", "iteration") if ticket.get(name)]
    if ticket.get("estimate") is not None:
        placement.append(f"estimate {ticket['estimate']:g}")
    if placement:
        print("  " + "  ".join(placement))
    if ticket.get("parent_key"):
        print(f"  parent {ticket['parent_key']}")
    dates = [f"{name} {ticket[name]}" for name in ("start", "due") if ticket.get(name)]
    if dates:
        print("  " + "  ".join(dates))
    progress = ticket.get("progress") or {}
    if progress.get("total"):
        print(f"  progress {progress['done']}/{progress['total']} sub-tickets done, {progress['points_done']:g}/{progress['points']:g} points")
    if ticket["body"]:
        print("\n" + ticket["body"])
    for child in ticket.get("children", []):
        print(f"  sub {child['key']} {child['status']} {child['title']}")
    for link in ticket.get("links", []):
        print(f"  {link['direction']} {link['kind']} {link['key']} {link['status']} {link['title']}")
    for question in ticket.get("questions", []):
        print("\n  " + question_text(question))
    for comment in ticket.get("comments", []):
        print(f"\n  [{comment['author']} {when(comment['created'])}] {comment['body']}")
    if events:
        print("\nhistory")
        print_events(events)


def question_text(question: dict) -> str:
    asked = f"{question['asker']} {when(question['created'])}"
    if question["answered"] is None:
        return f"question {question['id']} open [{asked}] {question['text']}"
    return (f"question {question['id']} answered [{asked}] {question['text']}\n"
            f"    answer [{question['answerer']} {when(question['answered'])}] {question['answer']}")


def print_events(events: list) -> None:
    for event in events:
        change = "" if event["field"] == "created" else f": {event['old'] or '-'} -> {event['new'] or '-'}"
        print(f"  {when(event['created'])}  {event['actor']}  {event['field']}{change}")


def print_tree(node: dict, depth: int = 0) -> None:
    estimate = f" ({node['estimate']:g})" if node.get("estimate") is not None else ""
    print(f"{'  ' * depth}{node['key']} {node['status']} {node['type']} {node['title']}{estimate}")
    for child in node["children"]:
        print_tree(child, depth + 1)


def add_ticket_commands(commands) -> None:
    list_projects = commands.add_parser("projects", help="list projects with ticket counts")
    list_projects.add_argument("--tag", help="only projects carrying this project tag")
    new_project = commands.add_parser("new-project", help="create a project")
    new_project.add_argument("key")
    new_project.add_argument("name")
    new_project.add_argument("--description", default="")
    new_project.add_argument("--tags", default="", help="comma separated project tags, for example resonite-research")

    add = commands.add_parser("add", help="create a ticket")
    add.add_argument("project", help="project key")
    add.add_argument("title")
    add.add_argument("--body", default="")
    add.add_argument("--type", help="task when not given")
    add.add_argument("--status", help="backlog when not given")
    add.add_argument("--priority", help="medium when not given")
    add.add_argument("--assignee", default="")
    add.add_argument("--labels", default="")
    add.add_argument("--parent")
    add.add_argument("--due", default="")
    add.add_argument("--start", default="")
    add.add_argument("--estimate")
    add.add_argument("--area", help="area id or path")
    add.add_argument("--iteration", help="iteration id or name")
    add.add_argument("--template", help="template id; its values fill every field you leave out")
    add.add_argument("--source", help="stable external id; a second add with the same source is refused")
    add.add_argument("--question", action="append", dest="questions", help="an open question to ask on the new ticket; repeat for more")

    list_command = commands.add_parser("list", help="list tickets")
    for name in LIST_FILTERS:
        list_command.add_argument(f"--{name}")
    list_command.add_argument("-q", "--q", "--text", dest="q", help="text in the title, description or key")
    list_command.add_argument("--open", action="store_true", help="hide done and cancelled")
    list_command.add_argument("--questions", action="store_true", help="only tickets with an unanswered question")
    list_command.add_argument("--exclude-type", dest="exclude_type", help="comma separated ticket types to leave out, for example bug,chore")
    list_command.add_argument("--limit", type=int)
    commands.add_parser("mine", help="open tickets assigned to --as")

    show = commands.add_parser("show", help="show one ticket with its history")
    show.add_argument("key")
    history = commands.add_parser("history", help="show a ticket's change history")
    history.add_argument("key")
    move = commands.add_parser("move", help="set status")
    move.add_argument("key")
    move.add_argument("status")
    done = commands.add_parser("done", help="set status to done")
    done.add_argument("key")
    done.add_argument("--comment", default="")
    assign = commands.add_parser("assign", help="set assignee")
    assign.add_argument("key")
    assign.add_argument("assignee")
    edit = commands.add_parser("edit", help="change fields")
    edit.add_argument("key")
    for name in (*EDIT_FIELDS, "parent"):
        edit.add_argument(f"--{name}")
    edit.add_argument("--add-label", action="append", default=[])
    edit.add_argument("--rm-label", action="append", default=[])
    comment = commands.add_parser("comment", help="add a comment")
    comment.add_argument("key")
    comment.add_argument("body")
    link = commands.add_parser("link", help="link two tickets")
    link.add_argument("key")
    link.add_argument("to")
    link.add_argument("--kind", default="relates")
    remove = commands.add_parser("rm", help="delete a ticket")
    remove.add_argument("key")
    board = commands.add_parser("columns", help="tickets by status column")
    board.add_argument("--project")
    stats = commands.add_parser("stats", help="counts")
    stats.add_argument("--project")


def add_planning_commands(commands) -> None:
    commands.add_parser("overview", help="organisation, areas, boards and projects")
    commands.add_parser("people", help="registered assignees with open ticket counts")
    commands.add_parser("person-add", help="register an assignee").add_argument("name")
    commands.add_parser("person-rm", help="remove an assignee with no open tickets").add_argument("name")
    queue = commands.add_parser("queue", help="open tickets that need a person (you by default)")
    queue.add_argument("--person", default="")
    tree = commands.add_parser("tree", help="a ticket with all its sub-tickets")
    tree.add_argument("key")
    plan = commands.add_parser("plan", help="backlog and iterations of a project")
    plan.add_argument("project")
    roadmap = commands.add_parser("roadmap", help="iterations and dated epics")
    roadmap.add_argument("--project")
    project_set = commands.add_parser("project-set", help="change a project")
    project_set.add_argument("key")
    for name in ("name", "description", "lead", "status", "start", "target", "tags"):
        project_set.add_argument(f"--{name}")

    question = commands.add_parser("question", help="open questions on tickets").add_subparsers(dest="action", required=True)
    question_ask = question.add_parser("ask", help="ask an open question on a ticket")
    question_ask.add_argument("key")
    question_ask.add_argument("text")
    question_answer = question.add_parser("answer", help="answer an open question")
    question_answer.add_argument("id")
    question_answer.add_argument("text")
    question_list = question.add_parser("list", help="list questions, open ones by default")
    question_list.add_argument("key", nargs="?", help="only this ticket")
    question_list.add_argument("--project")
    question_list.add_argument("--state", choices=("open", "answered", "all"), default="open")
    question.add_parser("reopen", help="reopen an answered question").add_argument("id")
    question.add_parser("rm", help="remove a question and its answer").add_argument("id")

    area = commands.add_parser("area", help="areas group boards").add_subparsers(dest="action", required=True)
    area.add_parser("list")
    area_add = area.add_parser("add")
    area_add.add_argument("name")
    area_add.add_argument("--parent")
    area_add.add_argument("--description", default="")
    area_add.add_argument("--tags", default="", help="comma separated tags that group the area in the navigator")
    area_set = area.add_parser("set", help="change an area")
    area_set.add_argument("id")
    for name in ("name", "description", "parent", "tags"):
        area_set.add_argument(f"--{name}")
    area.add_parser("rm").add_argument("id")

    board = commands.add_parser("board", help="boards hold tickets by rule or by pin").add_subparsers(dest="action", required=True)
    board.add_parser("list").add_argument("--area")
    board_add = board.add_parser("add")
    board_add.add_argument("area")
    board_add.add_argument("name")
    board_add.add_argument("--description", default="")
    board_add.add_argument("--scope", choices=["area", "all"])
    for name in ("project", "types", "priorities", "labels", "assignee", "parent", "iteration"):
        board_add.add_argument(f"--{name}")
    board_add.add_argument("--statuses", help="comma separated columns to show")
    board.add_parser("show").add_argument("id")
    for name in ("pin", "unpin"):
        pin = board.add_parser(name)
        pin.add_argument("id")
        pin.add_argument("ticket")
    board.add_parser("rm").add_argument("id")

    iteration = commands.add_parser("iteration", help="sprints and other time boxes").add_subparsers(dest="action", required=True)
    iteration_list = iteration.add_parser("list")
    iteration_list.add_argument("--project")
    iteration_list.add_argument("--state")
    iteration_add = iteration.add_parser("add")
    for name in ("project", "name", "start", "end"):
        iteration_add.add_argument(name)
    iteration_add.add_argument("--goal", default="")
    iteration_add.add_argument("--state", default="planned")
    iteration_set = iteration.add_parser("set")
    iteration_set.add_argument("id")
    for name in ("name", "start", "end", "goal", "state"):
        iteration_set.add_argument(f"--{name}")
    iteration.add_parser("rm").add_argument("id")

    tag = commands.add_parser("tag", help="manage tags").add_subparsers(dest="action", required=True)
    tag.add_parser("list")
    tag_add = tag.add_parser("add")
    tag_add.add_argument("name")
    tag_add.add_argument("--color", default="")
    tag_add.add_argument("--description", default="")
    tag_rename = tag.add_parser("rename")
    tag_rename.add_argument("name")
    tag_rename.add_argument("new_name")
    tag_set = tag.add_parser("set")
    tag_set.add_argument("name")
    tag_set.add_argument("--color")
    tag_set.add_argument("--description")
    tag_merge = tag.add_parser("merge")
    tag_merge.add_argument("name")
    tag_merge.add_argument("into")
    tag.add_parser("rm").add_argument("name")

    template = commands.add_parser("template", help="ticket templates").add_subparsers(dest="action", required=True)
    template.add_parser("list").add_argument("--project")
    template.add_parser("show").add_argument("id")
    template_add = template.add_parser("add")
    template_add.add_argument("name")
    for name in ("description", "project", "type", "priority", "status", "title", "body", "labels", "estimate", "assignee"):
        template_add.add_argument(f"--{name}")
    template.add_parser("defaults", help="add the built-in templates that are missing")
    template.add_parser("rm").add_argument("id")

    dashboard = commands.add_parser("dashboard", help="dashboards of widgets").add_subparsers(dest="action", required=True)
    dashboard.add_parser("list")
    dashboard.add_parser("show").add_argument("id")
    dashboard.add_parser("data").add_argument("id")
    dashboard_add = dashboard.add_parser("add")
    dashboard_add.add_argument("name")
    dashboard_add.add_argument("--description", default="")
    dashboard_add.add_argument("--widgets", help="JSON list of widgets")
    kb_space = commands.add_parser("kb-space", help="knowledge base spaces").add_subparsers(dest="action", required=True)
    kb_space.add_parser("list")
    kb_space_add = kb_space.add_parser("add")
    kb_space_add.add_argument("key")
    kb_space_add.add_argument("name")
    kb_space_add.add_argument("--description", default="")

    kb_page = commands.add_parser("kb-page", help="knowledge base pages").add_subparsers(dest="action", required=True)
    kb_page_list = kb_page.add_parser("list")
    for name in ("space", "type", "label", "status", "kind", "location"):
        kb_page_list.add_argument(f"--{name}")
    kb_page_list.add_argument("--stale", action="store_true", help="only pages past their review date")
    kb_page.add_parser("show").add_argument("id")
    kb_page_add = kb_page.add_parser("add")
    kb_page_add.add_argument("space")
    kb_page_add.add_argument("title")
    kb_page_add.add_argument("--body", default="")
    kb_page_add.add_argument("--body-file", help="read the text from a file")
    kb_page_add.add_argument("--template", help="a template id such as how-to or runbook")
    for name in ("parent", "labels", "status", "review-days", "comment"):
        kb_page_add.add_argument(f"--{name}")
    kb_page_edit = kb_page.add_parser("edit")
    kb_page_edit.add_argument("id")
    for name in ("title", "body", "body-file", "status", "labels", "parent", "review-by", "comment"):
        kb_page_edit.add_argument(f"--{name}")
    kb_page_rm = kb_page.add_parser("rm")
    kb_page_rm.add_argument("id")
    kb_page_rm.add_argument("--cascade", action="store_true")
    kb_page.add_parser("history").add_argument("id")
    kb_page_diff = kb_page.add_parser("diff")
    kb_page_diff.add_argument("id")
    kb_page_diff.add_argument("older")
    kb_page_diff.add_argument("newer")
    kb_page_restore = kb_page.add_parser("restore")
    kb_page_restore.add_argument("id")
    kb_page_restore.add_argument("version")
    kb_page_verify = kb_page.add_parser("verify")
    kb_page_verify.add_argument("id")
    kb_page_verify.add_argument("--days", type=int)
    kb_page_helpful = kb_page.add_parser("helpful")
    kb_page_helpful.add_argument("id")
    kb_page_helpful.add_argument("answer", choices=["yes", "no"])
    kb_page_helpful.add_argument("--comment", default="")
    kb_page.add_parser("fav").add_argument("id")

    kb_tool = commands.add_parser("kb-tool", help="the Tools category of the knowledge base").add_subparsers(dest="action", required=True)
    kb_tool_list = kb_tool.add_parser("list")
    for name in ("kind", "location", "label"):
        kb_tool_list.add_argument(f"--{name}")
    kb_tool_list.add_argument("-q", "--q", dest="q")
    kb_tool.add_parser("show").add_argument("id")
    kb_tool_add = kb_tool.add_parser("add")
    kb_tool_add.add_argument("name")
    for name in ("kind", "location", "path", "url", "invoke", "version", "owner", "tool-status", "docs", "labels", "body"):
        kb_tool_add.add_argument(f"--{name}")
    kb_tool_add.add_argument("--openapi-url", help="address of the OpenAPI description")
    kb_tool_add.add_argument("--openapi-file", help="path to an OpenAPI description on this machine (.json, .yaml, .yml)")
    kb_tool_add.add_argument("--openapi-inline", help="store the OpenAPI description from this JSON file")
    kb_tool_spec = kb_tool.add_parser("spec")
    kb_tool_spec.add_argument("id")
    kb_tool_spec.add_argument("--refresh", action="store_true")

    kb_search = commands.add_parser("kb-search", help="search pages and tools")
    kb_search.add_argument("query")
    kb_search.add_argument("--space")
    kb_search.add_argument("--type", choices=["article", "tool"])
    find = commands.add_parser("find", help="one search over pages, tools and tickets")
    find.add_argument("query")

    dashboard.add_parser("defaults", help="add the built-in dashboards that are missing")
    dashboard.add_parser("rm").add_argument("id")

    metric = commands.add_parser("metric", help="measure one thing now")
    metric.add_argument("kind", choices=["count", "group", "trend", "burndown", "cycle", "aging", "workload", "velocity", "overdue"])
    for name in ("project", "area", "iteration", "type", "status", "priority", "assignee", "label"):
        metric.add_argument(f"--{name}")
    metric.add_argument("--open", action="store_true", help="only open tickets")
    metric.add_argument("--group-by", dest="group_by")
    metric.add_argument("--measure", choices=["total", "created", "closed"])
    metric.add_argument("--days", type=int)
    metric.add_argument("--limit", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LEDGER ticket tracker command line")
    parser.add_argument("--base", default=os.environ.get("LEDGER_URL", DEFAULT_BASE), help="server address")
    parser.add_argument("--as", dest="actor", default=os.environ.get("LEDGER_ACTOR") or default_actor(), help="name recorded in history")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    add_ticket_commands(commands)
    add_planning_commands(commands)
    return parser


def list_path(arguments: argparse.Namespace) -> str:
    parameters = {name: getattr(arguments, name, None) for name in (*LIST_FILTERS, "q", "limit")}
    if arguments.command == "mine":
        parameters["assignee"] = arguments.actor
    parameters["open"] = "1" if arguments.command == "mine" or getattr(arguments, "open", False) else None
    parameters["questions"] = "open" if getattr(arguments, "questions", False) else None
    parameters["exclude_type"] = getattr(arguments, "exclude_type", None)
    return "/api/tickets?" + urllib.parse.urlencode({key: value for key, value in parameters.items() if value})


def edit_changes(arguments: argparse.Namespace, existing_labels: list[str]) -> dict:
    changes = {name: getattr(arguments, name) for name in EDIT_FIELDS if getattr(arguments, name) is not None}
    if arguments.parent is not None:
        changes["parent_key"] = arguments.parent
    if arguments.add_label or arguments.rm_label:
        labels = set(changes["labels"].split(",")) if "labels" in changes else set(existing_labels)
        labels |= {label.strip().lower() for label in arguments.add_label}
        labels -= {label.strip().lower() for label in arguments.rm_label}
        changes["labels"] = sorted(label for label in labels if label)
    if not changes:
        raise SystemExit("ledger: edit needs at least one field, for example --priority high")
    return changes


def run_ticket_command(arguments: argparse.Namespace):
    base, actor, command = arguments.base, arguments.actor, arguments.command
    if command == "projects":
        return call(base, "GET", "/api/projects" + (f"?tag={arguments.tag}" if arguments.tag else ""), actor)
    if command == "new-project":
        return call(base, "POST", "/api/projects", actor,
                    {"key": arguments.key, "name": arguments.name, "description": arguments.description, "tags": arguments.tags})
    if command == "add":
        fields = ("project", "title", "body", "type", "status", "priority", "assignee", "labels", "parent", "due", "start", "estimate", "area",
                  "iteration", "template", "source", "questions")
        return call(base, "POST", "/api/tickets", actor, drop_empty({name: getattr(arguments, name) for name in fields}))
    if command in ("list", "mine"):
        return call(base, "GET", list_path(arguments), actor)
    if command == "show":
        ticket = call(base, "GET", f"/api/tickets/{arguments.key}", actor)
        ticket["events"] = call(base, "GET", f"/api/tickets/{arguments.key}/events", actor)
        return ticket
    if command == "history":
        return call(base, "GET", f"/api/tickets/{arguments.key}/events", actor)
    if command == "move":
        return call(base, "PATCH", f"/api/tickets/{arguments.key}", actor, {"status": arguments.status})
    if command == "done":
        ticket = call(base, "PATCH", f"/api/tickets/{arguments.key}", actor, {"status": "done"})
        if arguments.comment:
            ticket = call(base, "POST", f"/api/tickets/{arguments.key}/comments", actor, {"body": arguments.comment})
        return ticket
    if command == "assign":
        return call(base, "PATCH", f"/api/tickets/{arguments.key}", actor, {"assignee": arguments.assignee})
    if command == "edit":
        existing = call(base, "GET", f"/api/tickets/{arguments.key}", actor)["labels"] if (arguments.add_label or arguments.rm_label) else []
        return call(base, "PATCH", f"/api/tickets/{arguments.key}", actor, edit_changes(arguments, existing))
    if command == "comment":
        return call(base, "POST", f"/api/tickets/{arguments.key}/comments", actor, {"body": arguments.body})
    if command == "link":
        return call(base, "POST", f"/api/tickets/{arguments.key}/links", actor, {"to": arguments.to, "kind": arguments.kind})
    if command == "rm":
        return call(base, "DELETE", f"/api/tickets/{arguments.key}", actor)
    if command == "columns":
        return call(base, "GET", "/api/board" + (f"?project={arguments.project}" if arguments.project else ""), actor)
    if command == "stats":
        return call(base, "GET", "/api/stats" + (f"?project={arguments.project}" if arguments.project else ""), actor)
    raise SystemExit(f"ledger: unknown command {command}")


def quoted(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def run_question(arguments, base, actor):
    if arguments.action == "ask":
        return call(base, "POST", f"/api/tickets/{arguments.key}/questions", actor, {"text": arguments.text})
    if arguments.action == "answer":
        return call(base, "POST", f"/api/questions/{arguments.id}/answer", actor, {"answer": arguments.text})
    if arguments.action == "list":
        parameters = {"state": arguments.state, "project": arguments.project, "ticket": arguments.key}
        return call(base, "GET", "/api/questions?" + urllib.parse.urlencode({key: value for key, value in parameters.items() if value}), actor)
    if arguments.action == "reopen":
        return call(base, "POST", f"/api/questions/{arguments.id}/reopen", actor)
    return call(base, "DELETE", f"/api/questions/{arguments.id}", actor)


def run_area(arguments, base, actor):
    if arguments.action == "list":
        return call(base, "GET", "/api/areas", actor)
    if arguments.action == "add":
        return call(base, "POST", "/api/areas", actor,
                    drop_empty({"name": arguments.name, "parent": arguments.parent, "description": arguments.description, "tags": arguments.tags}))
    if arguments.action == "set":
        changes = {name: getattr(arguments, name) for name in ("name", "description", "parent", "tags") if getattr(arguments, name) is not None}
        if not changes:
            raise SystemExit("ledger: area set needs at least one field, for example --tags resonite-research")
        return call(base, "PATCH", f"/api/areas/{arguments.id}", actor, changes)
    return call(base, "DELETE", f"/api/areas/{arguments.id}", actor)


def run_board(arguments, base, actor):
    action = arguments.action
    if action == "list":
        return call(base, "GET", "/api/boards" + (f"?area={quoted(arguments.area)}" if arguments.area else ""), actor)
    if action == "add":
        rules = drop_empty({name: getattr(arguments, name) for name in ("scope", "project", "types", "priorities", "labels", "assignee", "parent", "iteration")})
        payload = drop_empty({"area": arguments.area, "name": arguments.name, "description": arguments.description, "statuses": arguments.statuses})
        return call(base, "POST", "/api/boards", actor, {**payload, "rules": rules})
    if action == "show":
        return call(base, "GET", f"/api/boards/{arguments.id}", actor)
    if action == "pin":
        return call(base, "POST", f"/api/boards/{arguments.id}/items", actor, {"ticket": arguments.ticket})
    if action == "unpin":
        return call(base, "DELETE", f"/api/boards/{arguments.id}/items/{arguments.ticket}", actor)
    return call(base, "DELETE", f"/api/boards/{arguments.id}", actor)


def run_iteration(arguments, base, actor):
    action = arguments.action
    if action == "list":
        return call(base, "GET", "/api/iterations?" + urllib.parse.urlencode(drop_empty({"project": arguments.project, "state": arguments.state})), actor)
    if action == "add":
        payload = {name: getattr(arguments, name) for name in ("project", "name", "start", "end", "goal", "state")}
        return call(base, "POST", "/api/iterations", actor, payload)
    if action == "set":
        changes = drop_empty({name: getattr(arguments, name) for name in ("name", "start", "end", "goal", "state")})
        if not changes:
            raise SystemExit("ledger: iteration set needs at least one field, for example --state active")
        return call(base, "PATCH", f"/api/iterations/{arguments.id}", actor, changes)
    return call(base, "DELETE", f"/api/iterations/{arguments.id}", actor)


def run_tag(arguments, base, actor):
    action = arguments.action
    if action == "list":
        return call(base, "GET", "/api/tags", actor)
    if action == "add":
        return call(base, "POST", "/api/tags", actor, {"name": arguments.name, "color": arguments.color, "description": arguments.description})
    path = f"/api/tags/{quoted(arguments.name)}"
    if action == "rename":
        return call(base, "PATCH", path, actor, {"name": arguments.new_name})
    if action == "set":
        changes = drop_empty({"color": arguments.color, "description": arguments.description})
        if not changes:
            raise SystemExit("ledger: tag set needs --color or --description")
        return call(base, "PATCH", path, actor, changes)
    if action == "merge":
        return call(base, "POST", path + "/merge", actor, {"into": arguments.into})
    return call(base, "DELETE", path, actor)


def run_template(arguments, base, actor):
    action = arguments.action
    if action == "list":
        return call(base, "GET", "/api/templates" + (f"?project={arguments.project}" if arguments.project else ""), actor)
    if action == "show":
        return call(base, "GET", f"/api/templates/{arguments.id}", actor)
    if action == "add":
        fields = drop_empty({name: getattr(arguments, name) for name in ("description", "project", "type", "priority", "status", "title", "body",
                                                                         "labels", "estimate", "assignee")})
        return call(base, "POST", "/api/templates", actor, {"name": arguments.name, **fields})
    if action == "defaults":
        return call(base, "POST", "/api/templates/defaults", actor, {})
    return call(base, "DELETE", f"/api/templates/{arguments.id}", actor)


def run_dashboard(arguments, base, actor):
    action = arguments.action
    if action == "list":
        return call(base, "GET", "/api/dashboards", actor)
    if action == "show":
        return call(base, "GET", f"/api/dashboards/{arguments.id}", actor)
    if action == "data":
        return call(base, "GET", f"/api/dashboards/{arguments.id}/data", actor)
    if action == "add":
        widgets = json.loads(arguments.widgets) if arguments.widgets else []
        return call(base, "POST", "/api/dashboards", actor, {"name": arguments.name, "description": arguments.description, "widgets": widgets})
    if action == "defaults":
        return call(base, "POST", "/api/dashboards/defaults", actor, {})
    return call(base, "DELETE", f"/api/dashboards/{arguments.id}", actor)


def run_metric(arguments, base, actor):
    filters = drop_empty({name: getattr(arguments, name) for name in ("project", "area", "iteration", "type", "status", "priority", "assignee", "label")})
    if arguments.open:
        filters["open"] = True
    payload = drop_empty({"kind": arguments.kind, "filters": filters, "group_by": arguments.group_by, "measure": arguments.measure,
                          "days": arguments.days, "limit": arguments.limit})
    return call(base, "POST", "/api/metrics", actor, payload)


def metric_lines(kind: str, data: dict) -> list[str]:
    if kind == "count":
        sign = "+" if data["delta"] >= 0 else ""
        return [f"{data['value']}  ({sign}{data['delta']} against the {data['days']} days before, {data['measure']})"]
    if kind == "group":
        return [f"{bucket['name']:<24} {bucket['value']:>4}  {bucket['points']:g} points" for bucket in data["buckets"]] + [f"{data['total']} tickets"]
    if kind == "trend":
        return [f"{point['date']}  created {point['created']:>3}  closed {point['closed']:>3}  open {point['open']:>4}" for point in data["series"]]
    if kind == "burndown":
        lines = [f"{data['iteration']['name']}  {data['total']:g} {data['unit']}"]
        return lines + [f"{day['date']}  remaining {'-' if day['remaining'] is None else format(day['remaining'], 'g'):>6}  ideal {day['ideal']:g}" for day in data["days"]]
    if kind == "cycle":
        lead, cycle = data["lead"], data["cycle"]
        return [f"closed {data['closed']} in {data['days']} days", f"lead time  average {lead['average']}  median {lead['median']}  p85 {lead['p85']} days",
                f"cycle time average {cycle['average']}  median {cycle['median']}  p85 {cycle['p85']} days"] + [
                f"  {bucket['label']:<16} {bucket['value']}" for bucket in data["histogram"]]
    if kind == "aging":
        return [f"{bucket['label']:<16} {bucket['value']}" for bucket in data["buckets"]] + [
                f"oldest {item['key']} {item['age_days']} days  {item['title']}" for item in data["oldest"]]
    if kind == "workload":
        return [f"{person['name']:<20} {person['tickets']:>3} open  {person['points']:g} points  {person['overdue']} overdue" for person in data["people"]]
    if kind == "velocity":
        return [f"{item['name']:<20} committed {item['committed']:g}  completed {item['completed']:g}" for item in data["iterations"]] + [
                f"average {data['average']}"]
    return [f"{data['total']} overdue"] + [f"{item['key']:<9} {item['days_late']:>3} days late  {item['title']}" for item in data["items"]]


def read_text_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as error:
        raise SystemExit(f"ledger: cannot read {path} ({error.strerror})")


def kb_body(arguments) -> str | None:
    if getattr(arguments, "body_file", None):
        return read_text_file(arguments.body_file)
    return getattr(arguments, "body", None)


def run_kb_space(arguments, base, actor):
    if arguments.action == "list":
        return call(base, "GET", "/api/kb/spaces", actor)
    return call(base, "POST", "/api/kb/spaces", actor, {"key": arguments.key, "name": arguments.name, "description": arguments.description})


def run_kb_page(arguments, base, actor):
    action, page = arguments.action, f"/api/kb/pages/{getattr(arguments, 'id', '')}"
    if action == "list":
        parameters = drop_empty({name: getattr(arguments, name) for name in ("space", "type", "label", "status", "kind", "location")})
        if arguments.stale:
            parameters["stale"] = "1"
        return call(base, "GET", "/api/kb/pages?" + urllib.parse.urlencode(parameters), actor)
    if action == "show":
        return call(base, "GET", page + "?view=1", actor)
    if action == "add":
        payload = drop_empty({"space": arguments.space, "title": arguments.title, "body": kb_body(arguments), "template": arguments.template, "parent": arguments.parent,
                              "labels": arguments.labels, "status": arguments.status, "review_days": arguments.review_days, "comment": arguments.comment})
        return call(base, "POST", "/api/kb/pages", actor, payload)
    if action == "edit":
        changes = drop_empty({"title": arguments.title, "body": kb_body(arguments), "status": arguments.status, "labels": arguments.labels,
                              "review_by": arguments.review_by, "comment": arguments.comment})
        if arguments.parent is not None:
            changes["parent"] = arguments.parent
        if not changes:
            raise SystemExit("ledger: edit needs at least one field, for example --title")
        return call(base, "PATCH", page, actor, changes)
    if action == "rm":
        return call(base, "DELETE", page + ("?cascade=1" if arguments.cascade else ""), actor)
    if action == "history":
        return call(base, "GET", page + "/versions", actor)
    if action == "diff":
        return call(base, "GET", page + f"/diff?from={arguments.older}&to={arguments.newer}", actor)
    if action == "restore":
        return call(base, "POST", page + "/restore", actor, {"version": int(arguments.version)})
    if action == "verify":
        return call(base, "POST", page + "/verify", actor, drop_empty({"days": arguments.days}))
    if action == "helpful":
        return call(base, "POST", page + "/feedback", actor, {"helpful": arguments.answer == "yes", "comment": arguments.comment})
    return call(base, "POST", page + "/favourite", actor, {})


def run_kb_tool(arguments, base, actor):
    action = arguments.action
    if action == "list":
        return call(base, "GET", "/api/kb/tools?" + urllib.parse.urlencode(drop_empty({"kind": arguments.kind, "location": arguments.location, "label": arguments.label, "q": arguments.q})), actor)
    if action == "show":
        return call(base, "GET", f"/api/kb/pages/{arguments.id}?view=1", actor)
    if action == "spec":
        return call(base, "GET", f"/api/kb/pages/{arguments.id}/openapi" + ("?refresh=1" if arguments.refresh else ""), actor)
    meta = drop_empty({"kind": arguments.kind, "location": arguments.location, "path": arguments.path, "url": arguments.url, "invoke": arguments.invoke,
                       "version": arguments.version, "owner": arguments.owner, "tool_status": arguments.tool_status, "docs": arguments.docs})
    if arguments.openapi_url:
        meta["openapi"] = {"source": "url", "url": arguments.openapi_url}
    elif arguments.openapi_file:
        meta["openapi"] = {"source": "file", "path": arguments.openapi_file}
    elif arguments.openapi_inline:
        meta["openapi"] = {"source": "inline", "spec": json.loads(read_text_file(arguments.openapi_inline))}
    payload = drop_empty({"space": "TOOLS", "title": arguments.name, "body": arguments.body, "labels": arguments.labels})
    return call(base, "POST", "/api/kb/pages", actor, {**payload, "meta": meta})


def run_kb_command(arguments, base, actor):
    if arguments.command == "kb-search":
        return call(base, "GET", "/api/kb/search?" + urllib.parse.urlencode(drop_empty({"q": arguments.query, "space": arguments.space, "type": arguments.type})), actor)
    if arguments.command == "find":
        return call(base, "GET", "/api/search?" + urllib.parse.urlencode({"q": arguments.query}), actor)
    return {"kb-space": run_kb_space, "kb-page": run_kb_page, "kb-tool": run_kb_tool}[arguments.command](arguments, base, actor)


def hit_text(text: str) -> str:
    return text.replace("\x01", "[").replace("\x02", "]").replace("\n", " ")


def page_row(page: dict) -> str:
    flags = ("*" if page["stale"] else " ") + ("d" if page["status"] == "draft" else " ")
    tool = page.get("tool")
    detail = f"  {tool['kind']}/{tool['location']} {tool['invoke'] or tool['url'] or tool['path']}" if tool else ""
    return f"{page['id']:<5}{flags} {page['title']}{detail}  [{page['status']}, v{page['version']}, {page['views']} views]"


def operation_lines(spec: dict) -> list[str]:
    info = spec.get("info") or {}
    lines = [f"{info.get('title', '')} {info.get('version', '')}".strip()]
    for path, item in (spec.get("paths") or {}).items():
        for method, operation in (item or {}).items():
            if method in ("get", "post", "put", "patch", "delete", "head", "options") and isinstance(operation, dict):
                lines.append(f"  {method.upper():<7} {path}  {operation.get('summary', '')}")
    return lines


def render_kb(arguments, result) -> None:
    command, action = arguments.command, getattr(arguments, "action", None)
    if command in ("kb-search",):
        for hit in result:
            print(f"{hit['id']:<5} {hit['title']}  ({hit['space']['key']}, {hit['page_type']})\n      {hit_text(hit['snippet'])}")
        print(f"{len(result)} hits")
    elif command == "find":
        for label, key in (("Pages", "pages"), ("Tools", "tools")):
            print(f"{label} ({len(result[key])})")
            for hit in result[key]:
                print(f"  {hit['id']:<5} {hit['title']}  {hit_text(hit['snippet'])}")
        print(f"Tickets ({len(result['tickets'])})")
        for ticket in result["tickets"]:
            print(f"  {ticket['key']:<9} {ticket['status']:<11} {ticket['title']}")
    elif command == "kb-space" and action == "list":
        for space in result:
            print(f"{space['key']:<7} {space['name']:<20} {space['pages']} pages  {space['kind']}")
    elif action == "list":
        for page in result:
            print(page_row(page))
        print(f"{len(result)} pages")
    elif action in ("show",) or (command == "kb-page" and action in ("add", "edit", "restore", "verify", "helpful", "fav")) or (command == "kb-tool" and action == "add"):
        print(f"{result['id']}  {result['title']}  [{result['status']}, v{result['version']}]  {result['space']['name']}")
        trail = " / ".join(crumb["title"] for crumb in result["breadcrumbs"])
        print(f"  {trail}" if trail else "  top level", f"  review by {result['review_by'] or '-'}" + ("  STALE" if result["stale"] else ""))
        if result.get("tool"):
            tool = result["meta"]
            print(f"  {tool['kind']} on {tool['location']}  invoke {tool['invoke'] or '-'}  path {tool['path'] or tool['url'] or '-'}  version {tool['version'] or '-'}")
            for command_entry in tool["commands"]:
                print(f"    {command_entry['name']:<16} {command_entry['summary']}")
        if result["body"]:
            print("\n" + result["body"])
        if result["children"]:
            print("\nSub-pages: " + ", ".join(f"{c['id']} {c['title']}" for c in result["children"]))
        if result["tickets"]:
            print("Tickets: " + ", ".join(t["key"] for t in result["tickets"]))
        if result["backlinks"]:
            print("Linked from: " + ", ".join(b["title"] for b in result["backlinks"]))
    elif action == "history":
        for version in result:
            print(f"v{version['version']:<3} {version['author']:<12} {version['comment'] or '-':<24} {version['size']} chars")
    elif action == "diff":
        print(f"v{result['from']} to v{result['to']}: +{result['added']} -{result['removed']}")
        for line in result["lines"]:
            if line["op"] != "equal":
                print(("+ " if line["op"] == "insert" else "- ") + line["text"])
    elif command == "kb-tool" and action == "spec":
        print("\n".join(operation_lines(result["spec"])))
        if result["error"]:
            print(f"(last fetch failed: {result['error']}; showing the cached copy)")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def run_planning_command(arguments: argparse.Namespace):
    base, actor, command = arguments.base, arguments.actor, arguments.command
    if command in ("kb-space", "kb-page", "kb-tool", "kb-search", "find"):
        return run_kb_command(arguments, base, actor)
    if command == "overview":
        return call(base, "GET", "/api/overview", actor)
    if command == "people":
        return call(base, "GET", "/api/people", actor)
    if command == "person-add":
        return call(base, "POST", "/api/people", actor, {"name": arguments.name})
    if command == "person-rm":
        return call(base, "DELETE", f"/api/people/{quoted(arguments.name)}", actor)
    if command == "queue":
        return call(base, "GET", f"/api/queue?person={quoted(arguments.person or actor)}", actor)
    if command == "tree":
        return call(base, "GET", f"/api/tickets/{arguments.key}/tree", actor)
    if command == "plan":
        return call(base, "GET", f"/api/plan?project={arguments.project}", actor)
    if command == "roadmap":
        return call(base, "GET", "/api/roadmap" + (f"?project={arguments.project}" if arguments.project else ""), actor)
    if command == "project-set":
        changes = drop_empty({name: getattr(arguments, name) for name in ("name", "description", "lead", "status", "start", "target", "tags")})
        if not changes:
            raise SystemExit("ledger: project-set needs at least one field, for example --lead ann")
        return call(base, "PATCH", f"/api/projects/{arguments.key}", actor, changes)
    runners = {"question": run_question, "area": run_area, "board": run_board, "iteration": run_iteration, "tag": run_tag, "template": run_template,
               "dashboard": run_dashboard, "metric": run_metric}
    return runners[command](arguments, base, actor)


def run(arguments: argparse.Namespace):
    if arguments.command in PLANNING_COMMANDS:
        return run_planning_command(arguments)
    return run_ticket_command(arguments)


def render_plan(result: dict) -> None:
    for iteration in result["iterations"]:
        print(f"\n{iteration['name']} [{iteration['state']}] {iteration['start']} to {iteration['end']}  "
              f"{iteration['done']}/{iteration['tickets']} done, {iteration['points_done']:g}/{iteration['points']:g} points")
        for ticket in iteration["items"]:
            print("  " + ticket_line(ticket))
    print(f"\nBacklog ({len(result['backlog'])})")
    for ticket in result["backlog"]:
        print("  " + ticket_line(ticket))


def render_roadmap(result: dict) -> None:
    for iteration in result["iterations"]:
        print(f"iteration {iteration['name']:<14} {iteration['start']} to {iteration['end']} [{iteration['state']}]")
    for epic in result["epics"]:
        progress = epic["progress"]
        print(f"epic      {epic['key']:<9} {epic['start'] or '?'} to {epic['due'] or '?'}  {progress['done']}/{progress['total']} done  {epic['title']}")
    print(f"{result['unscheduled_epics']} epics without dates")


def render_overview(result: dict) -> None:
    print(result["organisation"]["name"])
    for project in result["projects"]:
        print(f"  project {project['key']:<6} {project['name']} ({project['status']})")
    for area in result["areas"]:
        print(f"  area {'  ' * area['depth']}{area['name']} ({area['open_tickets']} open, {area['boards']} boards)")
    for board in result["boards"]:
        print(f"  board {board['id']:<3} {board['area']} / {board['name']} ({board['tickets']} tickets)")


def render_board(result: dict) -> None:
    print(f"{result['area']} / {result['name']}  rules {json.dumps(result['rules'])}  {result['tickets']} tickets, {result['pinned']} pinned")
    for status in result["statuses"]:
        tickets = result["columns"][status]
        print(f"\n{status.upper()} ({len(tickets)})")
        for ticket in tickets:
            print("  " + ticket_line(ticket) + ("  (pinned)" if ticket.get("pinned") else ""))


def render_planning(arguments: argparse.Namespace, result) -> None:
    command, action = arguments.command, getattr(arguments, "action", None)
    if command in ("kb-space", "kb-page", "kb-tool", "kb-search", "find"):
        render_kb(arguments, result)
        return
    if command == "tree":
        print_tree(result)
    elif command == "overview":
        render_overview(result)
    elif command == "people":
        for person in result:
            print(f"{person['name']:<20} {person['open_tickets']:>4} open")
    elif command in ("person-add", "person-rm"):
        print(f"{result['name']} {'registered' if command == 'person-add' else 'removed'}")
    elif command == "queue":
        for ticket in result["tickets"]:
            print(f"{ticket_line(ticket)}  [{', '.join(ticket['reasons'])}]")
        print(f"{result['count']} tickets need {result['person']}")
    elif command == "plan":
        render_plan(result)
    elif command == "roadmap":
        render_roadmap(result)
    elif command == "board" and action in ("show", "add", "pin", "unpin"):
        render_board(result)
    elif command == "board" and action == "list":
        for board in result:
            print(f"{board['id']:<4} {board['area']} / {board['name']}  {board['tickets']} tickets  {json.dumps(board['rules'])}")
    elif command == "question" and action == "list":
        for question in result:
            print(f"{question['ticket_key']:<9} {question_text(question)}")
        print(f"{len(result)} questions")
    elif command == "question":
        print_ticket(result)
    elif command == "area" and action == "list":
        for area in result:
            print(f"{area['id']:<4} {'  ' * area['depth']}{area['name']}  {area['open_tickets']} open, {area['boards']} boards")
    elif command == "iteration" and action == "list":
        for iteration in result:
            print(f"{iteration['id']:<4} {iteration['project']:<6} {iteration['name']:<16} {iteration['start']} to {iteration['end']} "
                  f"[{iteration['state']}] {iteration['done']}/{iteration['tickets']} done")
    elif command == "tag" and action == "list":
        for tag in result:
            print(f"{tag['name']:<20} {tag['tickets']:>4} tickets {tag['boards']:>2} boards  {tag['color'] or '-':<8} {'' if tag['registered'] else '(unregistered)'}")
    elif command == "metric":
        print("\n".join(metric_lines(arguments.kind, result["data"])))
    elif command == "dashboard" and action == "list":
        for dashboard in result:
            print(f"{dashboard['id']:<4} {dashboard['name']:<20} {len(dashboard['widgets'])} widgets  {dashboard['description']}")
    elif command == "dashboard" and action in ("show", "add"):
        print(f"{result['name']}  {result['description']}")
        for widget in result["widgets"]:
            print(f"  {widget['id']:<5} {widget['kind']:<9} {widget['title']}")
    elif command == "dashboard" and action == "data":
        for widget in result["dashboard"]["widgets"]:
            data = result["results"][widget["id"]]
            print(f"\n{widget['title']}")
            print("  " + (data["error"] if "error" in data else "\n  ".join(metric_lines(widget["kind"], data))))
    elif command == "template" and action == "list":
        for template in result:
            print(f"{template['id']:<4} {template['name']:<20} {template['type']:<8} {template['priority']:<8} {template['project'] or 'all projects'}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def render_ticket_command(command: str, result) -> None:
    if command in ("list", "mine"):
        for ticket in result:
            print(ticket_line(ticket))
        print(f"{len(result)} tickets")
    elif command == "projects":
        for project in result:
            counts = ", ".join(f"{name} {count}" for name, count in project["counts"].items()) or "empty"
            tags = f"  #{' #'.join(project['tags'])}" if project.get("tags") else ""
            print(f"{project['key']:<6} {project['name']}  [{project['status']}]  ({counts}){tags}")
    elif command == "columns":
        for status in result["statuses"]:
            items = result["columns"][status]
            print(f"\n{status.upper()} ({len(items)})")
            for ticket in items:
                print("  " + ticket_line(ticket))
    elif command == "history":
        print_events(result)
    elif command == "show":
        print_ticket(result, result.get("events"))
    elif command in ("add", "move", "done", "assign", "edit", "comment", "link"):
        print_ticket(result)
    elif command == "stats":
        print(f"open {result['open']}, unassigned {result['unassigned']}")
        for group in ("by_status", "by_type", "by_priority", "by_assignee"):
            print(f"{group[3:]:<9} " + ", ".join(f"{name} {count}" for name, count in result[group].items()))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    arguments = build_parser().parse_args(argv)
    result = run(arguments)
    if arguments.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif arguments.command in PLANNING_COMMANDS:
        render_planning(arguments, result)
    else:
        render_ticket_command(arguments.command, result)


if __name__ == "__main__":
    main(sys.argv[1:])
