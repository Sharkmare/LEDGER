from __future__ import annotations

import argparse
import contextlib
import os
import threading
from pathlib import Path

from .web import App, HTTPError, abort, g, jsonify, request, send_from_directory

from . import kb, manage, metrics, openapi, organise, store

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 6680
DEFAULT_DATABASE = ROOT / "data" / "ledger.db"
DEFAULT_FONT_DIR = ROOT / "fonts"
STATIC_DIR = Path(__file__).resolve().parent / "static"
ACTOR_HEADER = "X-Ledger-Actor"
TOTAL_HEADER = "X-Total-Count"
DEFAULT_LIST_LIMIT = 500
MAX_LIST_LIMIT = 5000

API_HELP = {
    "summary": "LEDGER ticket tracker. JSON in and out. Send X-Ledger-Actor on writes to record who made a change.",
    "endpoints": [
        "GET  /healthz",
        "GET  /api/meta                        types, statuses, priorities, link kinds",
        "GET  /api/projects | POST {key,name,description}",
        "GET  /api/tickets?project=&status=&assignee=&type=&priority=&label=&q=&source=&open=1&limit=",
        "POST /api/tickets {project,title,body,type,status,priority,assignee,labels,parent,due,source}",
        "GET  /api/tickets/<KEY-N> | PATCH {field: value} | DELETE",
        "POST /api/tickets/<KEY-N>/comments {body}",
        "POST /api/tickets/<KEY-N>/links {to,kind}",
        "GET  /api/tickets/<KEY-N>/events",
        "GET  /api/board?project=",
        "GET  /api/stats?project=",
        "GET  /api/overview                    organisation, areas, boards, projects",
        "GET|PUT /api/organisation",
        "GET|POST /api/areas | GET|PATCH|DELETE /api/areas/<id>",
        "GET|POST /api/boards | GET|PATCH|DELETE /api/boards/<id> | POST /api/boards/<id>/items | DELETE .../items/<KEY-N>",
        "GET|POST /api/iterations | GET|PATCH|DELETE /api/iterations/<id>",
        "GET  /api/plan?project=  /api/roadmap?project=",
        "GET|POST /api/tags | PATCH|DELETE /api/tags/<name> | POST /api/tags/<name>/merge {into}",
        "GET|POST /api/templates | POST /api/templates/defaults | GET|PATCH|DELETE /api/templates/<id>",
        "PATCH /api/projects/<KEY>  |  GET /api/tickets/<KEY-N>/tree",
        "POST /api/metrics {kind,filters,...}  one measure; kinds count group trend burndown cycle aging workload velocity overdue",
        "GET|POST /api/dashboards | POST /api/dashboards/defaults | GET|PATCH|DELETE /api/dashboards/<id> | GET /api/dashboards/<id>/data",
        "GET /api/kb/overview  /api/kb/templates  /api/kb/search?q=  /api/search?q=   knowledge base and one search over pages, tools and tickets",
        "GET|POST /api/kb/spaces | GET|PATCH|DELETE /api/kb/spaces/<id> | GET /api/kb/spaces/<id>/tree",
        "GET|POST /api/kb/pages | GET|PATCH|DELETE /api/kb/pages/<id> | GET .../versions, .../versions/<n>, .../diff?from=&to= | POST .../restore",
        "POST /api/kb/pages/<id>/feedback, /favourite, /verify | GET /api/kb/pages/<id>/feedback",
        "GET /api/kb/tools?kind=&location=&q=  GET /api/kb/pages/<id>/openapi?refresh=1   the Tools category and a tool's OpenAPI description",
        "GET  /api/openapi.json                OpenAPI 3 description; interactive page at /docs",
    ],
}


def create_app(database_path: str | Path = DEFAULT_DATABASE, font_dir: str | Path | None = None) -> App:
    app = App()
    connection = store.connect(database_path)
    if not connection.execute("SELECT 1 FROM organisation").fetchone() and not connection.execute("SELECT 1 FROM projects").fetchone():
        organise.set_organisation(connection, organise.DEFAULT_ORGANISATION)
        manage.seed_default_templates(connection)
        metrics.seed_default_dashboards(connection)
    kb.ensure_tools_space(connection)
    fonts_directory = Path(font_dir or os.environ.get("LEDGER_FONT_DIR") or DEFAULT_FONT_DIR)
    database_lock = threading.RLock()

    @contextlib.contextmanager
    def without_database_lock():
        database_lock.release()
        try:
            yield
        finally:
            database_lock.acquire()

    @app.before_request
    def lock_database():
        database_lock.acquire()
        g.holds_lock = True

    @app.teardown_request
    def unlock_database(_error):
        if g.pop("holds_lock", False):
            database_lock.release()

    @app.errorhandler(Exception)
    def unexpected(error):
        if isinstance(error, HTTPError):
            return jsonify({"error": error.description or error.name}), error.code
        app.logger.exception("unhandled error")
        return jsonify({"error": f"server error: {type(error).__name__}"}), 500

    @app.errorhandler(store.NotFound)
    def not_found(error):
        return jsonify({"error": str(error)}), 404

    @app.errorhandler(store.LedgerError)
    def refused(error):
        return jsonify({"error": str(error)}), 400

    @app.after_request
    def no_cache_for_pages(response):
        if not request.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def actor() -> str:
        payload = request.get_json(silent=True)
        from_body = payload.get("actor") if isinstance(payload, dict) else None
        return str(request.headers.get(ACTOR_HEADER) or from_body or "anonymous").strip()

    def body_json() -> dict:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise store.LedgerError("request body must be a JSON object")
        return payload

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "service": "ledger"})

    @app.get("/api")
    def api_help():
        return jsonify(API_HELP)

    @app.get("/api/openapi.json")
    def openapi_document():
        return jsonify(openapi.build_spec())

    @app.get("/docs")
    def docs():
        return send_from_directory(STATIC_DIR, "docs.html")

    @app.get("/api/meta")
    def meta():
        return jsonify({"types": store.TICKET_TYPES, "statuses": store.STATUSES, "priorities": store.PRIORITIES,
                        "closed_statuses": store.CLOSED_STATUSES, "link_kinds": store.LINK_KINDS,
                        "editable_fields": store.EDITABLE_FIELDS})

    @app.get("/api/projects")
    def projects():
        return jsonify(store.list_projects(connection, request.args.get("tag")))

    @app.post("/api/projects")
    def new_project():
        payload = body_json()
        created = store.create_project(connection, payload.get("key", ""), payload.get("name", ""), payload.get("description", ""),
                                      payload.get("lead", ""), payload.get("start", ""), payload.get("target", ""),
                                      payload.get("tags", ""))
        return jsonify(created), 201

    @app.get("/api/tickets")
    def tickets():
        arguments = request.args
        try:
            limit = min(max(int(arguments.get("limit", DEFAULT_LIST_LIMIT)), 1), MAX_LIST_LIMIT)
        except ValueError:
            raise store.LedgerError("limit must be a whole number") from None
        filters = dict(
            project_key=arguments.get("project"), status=arguments.get("status"), assignee=arguments.get("assignee"),
            type=arguments.get("type"), priority=arguments.get("priority"), label=arguments.get("label"),
            query=arguments.get("q"), source=arguments.get("source"), area=arguments.get("area"), iteration=arguments.get("iteration"),
            include_closed=arguments.get("open") not in ("1", "true"))
        response = jsonify(store.list_tickets(connection, limit=limit, **filters))
        response.headers[TOTAL_HEADER] = str(store.count_tickets(connection, **filters))
        return response

    @app.post("/api/tickets")
    def new_ticket():
        payload = body_json()
        if payload.get("template") not in (None, ""):
            payload = manage.apply_template(connection, payload["template"], payload)
        created = store.create_ticket(
            connection, payload.get("project", ""), payload.get("title", ""), body=payload.get("body", ""),
            type=payload.get("type", "task"), status=payload.get("status", "backlog"),
            priority=payload.get("priority", "medium"), assignee=payload.get("assignee", ""),
            labels=payload.get("labels"), parent_key=payload.get("parent"), due=payload.get("due", ""),
            source=payload.get("source"), actor=actor(), start=payload.get("start", ""), estimate=payload.get("estimate"),
            area=payload.get("area"), iteration=payload.get("iteration"))
        return jsonify(created), 201

    @app.get("/api/tickets/<ticket_key>")
    def ticket(ticket_key):
        return jsonify(store.get_ticket(connection, ticket_key))

    @app.patch("/api/tickets/<ticket_key>")
    def edit_ticket(ticket_key):
        payload = body_json()
        payload.pop("actor", None)
        return jsonify(store.update_ticket(connection, ticket_key, payload, actor=actor()))

    @app.delete("/api/tickets/<ticket_key>")
    def remove_ticket(ticket_key):
        store.delete_ticket(connection, ticket_key)
        return jsonify({"deleted": ticket_key.upper()})

    @app.post("/api/tickets/<ticket_key>/comments")
    def comment(ticket_key):
        return jsonify(store.add_comment(connection, ticket_key, actor(), body_json().get("body", ""))), 201

    @app.post("/api/tickets/<ticket_key>/links")
    def link(ticket_key):
        payload = body_json()
        return jsonify(store.add_link(connection, ticket_key, payload.get("to", ""), payload.get("kind", "relates"))), 201

    @app.get("/api/tickets/<ticket_key>/events")
    def events(ticket_key):
        return jsonify(store.ticket_events(connection, ticket_key))

    @app.get("/api/board")
    def board():
        return jsonify(store.board(connection, project_key=request.args.get("project")))

    @app.get("/api/stats")
    def stats():
        return jsonify(store.stats(connection, project_key=request.args.get("project")))

    @app.get("/api/overview")
    def overview():
        return jsonify(organise.overview(connection))

    @app.get("/api/organisation")
    def get_organisation():
        return jsonify(organise.get_organisation(connection))

    @app.put("/api/organisation")
    def put_organisation():
        return jsonify(organise.set_organisation(connection, body_json().get("name")))

    @app.patch("/api/projects/<project_key>")
    def edit_project(project_key):
        return jsonify(store.update_project(connection, project_key, body_json()))

    @app.get("/api/areas")
    def areas():
        return jsonify(organise.list_areas(connection))

    @app.post("/api/areas")
    def new_area():
        payload = body_json()
        created = organise.create_area(connection, payload.get("name"), payload.get("description", ""), payload.get("parent"),
                                     payload.get("tags", ""))
        return jsonify(created), 201

    @app.get("/api/areas/<int:area_id>")
    def area(area_id):
        return jsonify(organise.get_area(connection, area_id))

    @app.patch("/api/areas/<int:area_id>")
    def edit_area(area_id):
        return jsonify(organise.update_area(connection, area_id, body_json()))

    @app.delete("/api/areas/<int:area_id>")
    def remove_area(area_id):
        organise.delete_area(connection, area_id)
        return jsonify({"deleted": area_id})

    @app.get("/api/boards")
    def boards():
        return jsonify(organise.list_boards(connection, area=request.args.get("area")))

    @app.post("/api/boards")
    def new_board():
        payload = body_json()
        created = organise.create_board(connection, payload.get("area"), payload.get("name"), payload.get("description", ""),
                                        payload.get("rules"), payload.get("statuses"))
        return jsonify(created), 201

    @app.get("/api/boards/<int:board_id>")
    def board_detail(board_id):
        return jsonify(organise.get_board(connection, board_id))

    @app.patch("/api/boards/<int:board_id>")
    def edit_board(board_id):
        return jsonify(organise.update_board(connection, board_id, body_json()))

    @app.delete("/api/boards/<int:board_id>")
    def remove_board(board_id):
        organise.delete_board(connection, board_id)
        return jsonify({"deleted": board_id})

    @app.post("/api/boards/<int:board_id>/items")
    def pin(board_id):
        return jsonify(organise.pin_ticket(connection, board_id, body_json().get("ticket", ""))), 201

    @app.delete("/api/boards/<int:board_id>/items/<ticket_key>")
    def unpin(board_id, ticket_key):
        return jsonify(organise.unpin_ticket(connection, board_id, ticket_key))

    @app.get("/api/iterations")
    def iterations():
        return jsonify(organise.list_iterations(connection, project=request.args.get("project"), state=request.args.get("state")))

    @app.post("/api/iterations")
    def new_iteration():
        payload = body_json()
        created = organise.create_iteration(connection, payload.get("project"), payload.get("name"), payload.get("start"),
                                            payload.get("end"), payload.get("goal", ""), payload.get("state", "planned"))
        return jsonify(created), 201

    @app.get("/api/iterations/<int:iteration_id>")
    def iteration(iteration_id):
        return jsonify(organise.get_iteration(connection, iteration_id))

    @app.patch("/api/iterations/<int:iteration_id>")
    def edit_iteration(iteration_id):
        return jsonify(organise.update_iteration(connection, iteration_id, body_json()))

    @app.delete("/api/iterations/<int:iteration_id>")
    def remove_iteration(iteration_id):
        organise.delete_iteration(connection, iteration_id)
        return jsonify({"deleted": iteration_id})

    @app.get("/api/plan")
    def plan():
        return jsonify(organise.plan(connection, request.args.get("project", "")))

    @app.get("/api/roadmap")
    def roadmap():
        return jsonify(organise.roadmap(connection, request.args.get("project")))

    @app.get("/api/tags")
    def tags():
        return jsonify(manage.list_tags(connection))

    @app.post("/api/tags")
    def new_tag():
        payload = body_json()
        return jsonify(manage.create_tag(connection, payload.get("name"), payload.get("color", ""), payload.get("description", ""))), 201

    @app.patch("/api/tags/<tag_name>")
    def edit_tag(tag_name):
        return jsonify(manage.update_tag(connection, tag_name, body_json(), actor=actor()))

    @app.delete("/api/tags/<tag_name>")
    def remove_tag(tag_name):
        return jsonify(manage.delete_tag(connection, tag_name, actor=actor()))

    @app.post("/api/tags/<tag_name>/merge")
    def merge_tag(tag_name):
        return jsonify(manage.merge_tags(connection, tag_name, body_json().get("into"), actor=actor()))

    @app.get("/api/templates")
    def templates():
        return jsonify(manage.list_templates(connection, project=request.args.get("project")))

    @app.post("/api/templates")
    def new_template():
        return jsonify(manage.create_template(connection, **body_json())), 201

    @app.post("/api/templates/defaults")
    def default_templates():
        return jsonify(manage.seed_default_templates(connection)), 201

    @app.get("/api/templates/<int:template_id>")
    def template(template_id):
        return jsonify(manage.get_template(connection, template_id))

    @app.patch("/api/templates/<int:template_id>")
    def edit_template(template_id):
        return jsonify(manage.update_template(connection, template_id, body_json()))

    @app.delete("/api/templates/<int:template_id>")
    def remove_template(template_id):
        manage.delete_template(connection, template_id)
        return jsonify({"deleted": template_id})

    @app.get("/api/tickets/<ticket_key>/tree")
    def tree(ticket_key):
        return jsonify(store.ticket_tree(connection, ticket_key))

    @app.post("/api/metrics")
    def metric():
        return jsonify(metrics.evaluate(connection, body_json()))

    @app.get("/api/dashboards")
    def dashboards():
        return jsonify(metrics.list_dashboards(connection))

    @app.post("/api/dashboards")
    def new_dashboard():
        payload = body_json()
        created = metrics.create_dashboard(connection, payload.get("name"), payload.get("description", ""), payload.get("widgets"))
        return jsonify(created), 201

    @app.post("/api/dashboards/defaults")
    def default_dashboards():
        return jsonify(metrics.seed_default_dashboards(connection)), 201

    @app.get("/api/dashboards/<int:dashboard_id>")
    def dashboard(dashboard_id):
        return jsonify(metrics.get_dashboard(connection, dashboard_id))

    @app.patch("/api/dashboards/<int:dashboard_id>")
    def edit_dashboard(dashboard_id):
        return jsonify(metrics.update_dashboard(connection, dashboard_id, body_json()))

    @app.delete("/api/dashboards/<int:dashboard_id>")
    def remove_dashboard(dashboard_id):
        metrics.delete_dashboard(connection, dashboard_id)
        return jsonify({"deleted": dashboard_id})

    @app.get("/api/dashboards/<int:dashboard_id>/data")
    def dashboard_values(dashboard_id):
        return jsonify(metrics.dashboard_data(connection, dashboard_id))

    def whole_number(name, default=None):
        text = request.args.get(name)
        if text in (None, ""):
            return default
        if not str(text).lstrip("-").isdigit():
            raise store.LedgerError(f"{name} must be a whole number")
        return int(text)

    @app.get("/api/kb/overview")
    def kb_overview():
        return jsonify(kb.overview(connection, actor()))

    @app.get("/api/kb/templates")
    def kb_templates():
        return jsonify(list(kb.PAGE_TEMPLATES))

    @app.get("/api/kb/spaces")
    def kb_spaces():
        return jsonify(kb.list_spaces(connection))

    @app.post("/api/kb/spaces")
    def kb_new_space():
        payload = body_json()
        return jsonify(kb.create_space(connection, payload.get("key", ""), payload.get("name", ""), payload.get("description", ""), payload.get("color", ""))), 201

    @app.get("/api/kb/spaces/<int:space_id>")
    def kb_space(space_id):
        return jsonify(kb.get_space(connection, space_id))

    @app.patch("/api/kb/spaces/<int:space_id>")
    def kb_edit_space(space_id):
        return jsonify(kb.update_space(connection, space_id, body_json()))

    @app.delete("/api/kb/spaces/<int:space_id>")
    def kb_remove_space(space_id):
        kb.delete_space(connection, space_id)
        return jsonify({"deleted": space_id})

    @app.get("/api/kb/spaces/<int:space_id>/tree")
    def kb_tree(space_id):
        return jsonify(kb.tree(connection, space_id))

    @app.get("/api/kb/spaces/<int:space_id>/children")
    def kb_children(space_id):
        arguments = request.args
        return jsonify(kb.level(connection, space_id, arguments.get("parent"), arguments.get("offset", 0), arguments.get("limit", kb.LEVEL_LIMIT_DEFAULT)))

    @app.get("/api/kb/tools")
    def kb_tools():
        arguments = request.args
        pages = kb.list_pages(connection, space=kb.TOOLS_SPACE_KEY, status=arguments.get("status"), label=arguments.get("label"),
                              tool_kind=arguments.get("kind"), location=arguments.get("location"), limit=whole_number("limit", 500), order=arguments.get("order", "title"))
        query = (arguments.get("q") or "").strip()
        if query:
            found = {hit["id"] for hit in kb.search(connection, query, space=kb.TOOLS_SPACE_KEY, limit=200)}
            pages = [page for page in pages if page["id"] in found]
        return jsonify(pages)

    @app.get("/api/kb/pages")
    def kb_pages():
        arguments = request.args
        parent = arguments.get("parent", "any")
        pages = kb.list_pages(
            connection, space=arguments.get("space"), parent=parent, status=arguments.get("status"), label=arguments.get("label"),
            page_type=arguments.get("type"), stale=arguments.get("stale") in ("1", "true"), favourite_of=actor() if arguments.get("favourite") in ("1", "true") else None,
            limit=whole_number("limit", 200), order=arguments.get("order", "updated"), tool_kind=arguments.get("kind"), location=arguments.get("location"),
            translations=arguments.get("translations") in ("1", "true"))
        return jsonify(pages)

    @app.post("/api/kb/pages")
    def kb_new_page():
        payload = body_json()
        body = payload.get("body", "")
        if payload.get("template") not in (None, ""):
            template = next((t for t in kb.PAGE_TEMPLATES if t["id"] == payload["template"]), None)
            if template is None:
                raise store.NotFound(f"no page template {payload['template']!r}")
            body = body or template["body"]
        created = kb.create_page(connection, payload.get("space"), payload.get("title"), body, payload.get("parent"), payload.get("labels"),
                                 payload.get("status", "published"), payload.get("meta"), actor(), None, payload.get("review_days"), payload.get("comment", ""),
                                 payload.get("translation_of"), payload.get("locale", ""))
        return jsonify(created), 201

    @app.get("/api/kb/pages/<int:page_id>")
    def kb_page(page_id):
        return jsonify(kb.get_page(connection, page_id, actor(), count_view=request.args.get("view") in ("1", "true")))

    @app.patch("/api/kb/pages/<int:page_id>")
    def kb_edit_page(page_id):
        payload = body_json()
        comment = payload.pop("comment", "")
        return jsonify(kb.update_page(connection, page_id, payload, actor(), comment))

    @app.delete("/api/kb/pages/<int:page_id>")
    def kb_remove_page(page_id):
        return jsonify(kb.delete_page(connection, page_id, cascade=request.args.get("cascade") in ("1", "true")))

    @app.get("/api/kb/pages/<int:page_id>/versions")
    def kb_versions(page_id):
        return jsonify(kb.list_versions(connection, page_id))

    @app.get("/api/kb/pages/<int:page_id>/versions/<int:version>")
    def kb_version(page_id, version):
        return jsonify(kb.get_version(connection, page_id, version))

    @app.get("/api/kb/pages/<int:page_id>/diff")
    def kb_diff(page_id):
        older, newer = whole_number("from"), whole_number("to")
        if older is None or newer is None:
            raise store.LedgerError("give the two versions to compare as from and to")
        return jsonify(kb.diff_versions(connection, page_id, older, newer))

    @app.post("/api/kb/pages/<int:page_id>/restore")
    def kb_restore(page_id):
        return jsonify(kb.restore_version(connection, page_id, body_json().get("version"), actor()))

    @app.get("/api/kb/pages/<int:page_id>/feedback")
    def kb_feedback_list(page_id):
        return jsonify(kb.list_feedback(connection, page_id))

    @app.post("/api/kb/pages/<int:page_id>/feedback")
    def kb_feedback(page_id):
        payload = body_json()
        return jsonify(kb.record_feedback(connection, page_id, actor(), payload.get("helpful"), payload.get("comment", ""))), 201

    @app.post("/api/kb/pages/<int:page_id>/favourite")
    def kb_favourite(page_id):
        return jsonify(kb.toggle_favourite(connection, page_id, actor()))

    @app.post("/api/kb/pages/<int:page_id>/verify")
    def kb_verify(page_id):
        payload = request.get_json(silent=True)
        days = payload.get("days", kb.DEFAULT_REVIEW_DAYS) if isinstance(payload, dict) else kb.DEFAULT_REVIEW_DAYS
        return jsonify(kb.verify_page(connection, page_id, actor(), days))

    @app.get("/api/kb/pages/<int:page_id>/openapi")
    def kb_openapi(page_id):
        plan = kb.spec_plan(connection, page_id, refresh=request.args.get("refresh") in ("1", "true"))
        if "result" in plan:
            return jsonify(plan["result"])
        with without_database_lock():
            try:
                spec, error = kb.fetch_spec(plan["fetch"]), ""
            except store.LedgerError as problem:
                spec, error = None, str(problem)
        return jsonify(kb.spec_commit(connection, page_id, spec, error))

    @app.get("/api/kb/search")
    def kb_search():
        arguments = request.args
        return jsonify(kb.search(connection, arguments.get("q", ""), space=arguments.get("space"), page_type=arguments.get("type"), limit=whole_number("limit", 20)))

    @app.get("/api/kb/mentions")
    def kb_mentions():
        return jsonify(kb.pages_mentioning(connection, request.args.get("ticket", "")))

    @app.get("/api/search")
    def search_everything():
        return jsonify(kb.find_everything(connection, request.args.get("q", ""), whole_number("limit", 8)))

    @app.get("/fonts/<path:filename>")
    def fonts(filename):
        if not (fonts_directory / filename).is_file():
            abort(404)
        return send_from_directory(fonts_directory, filename)

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="LEDGER ticket tracker server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LEDGER_PORT", DEFAULT_PORT)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--database", default=os.environ.get("LEDGER_DB", str(DEFAULT_DATABASE)))
    arguments = parser.parse_args()
    create_app(arguments.database).run(host=arguments.host, port=arguments.port, threaded=True)


if __name__ == "__main__":
    main()
