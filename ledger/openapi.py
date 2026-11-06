from __future__ import annotations

from . import kb, metrics, questions, store

API_VERSION = "1.2.0"
KEY_EXAMPLE = "APP-1"


def ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def json_body(schema: dict, required: bool = True) -> dict:
    return {"required": required, "content": {"application/json": {"schema": schema}}}


def json_response(description: str, schema: dict, headers: dict | None = None) -> dict:
    response = {"description": description, "content": {"application/json": {"schema": schema}}}
    if headers:
        response["headers"] = headers
    return response


def query(name: str, description: str, schema: dict | None = None) -> dict:
    return {"name": name, "in": "query", "required": False, "description": description, "schema": schema or {"type": "string"}}


def question_parameter() -> dict:
    return {"name": "question_id", "in": "path", "required": True, "description": "Question id", "schema": {"type": "integer", "example": 7}}


def key_parameter() -> dict:
    return {"name": "ticket_key", "in": "path", "required": True, "description": "Ticket key, PROJECT-NUMBER",
            "schema": {"type": "string", "example": KEY_EXAMPLE}}


ERRORS = {
    "400": json_response("The request was refused; the message says why", ref("Error")),
    "404": json_response("No such project or ticket", ref("Error")),
}


def schemas() -> dict:
    ticket_properties = {
        "id": {"type": "integer"},
        "key": {"type": "string", "example": KEY_EXAMPLE},
        "project_key": {"type": "string", "example": "APP"},
        "number": {"type": "integer"},
        "title": {"type": "string", "maxLength": store.MAX_TITLE_CHARS},
        "body": {"type": "string"},
        "type": {"type": "string", "enum": list(store.TICKET_TYPES)},
        "status": {"type": "string", "enum": list(store.STATUSES)},
        "priority": {"type": "string", "enum": list(store.PRIORITIES)},
        "assignee": {"type": "string"},
        "labels": {"type": "array", "items": {"type": "string"}},
        "parent_key": {"type": "string", "nullable": True},
        "due": {"type": "string", "description": "YYYY-MM-DD or empty", "example": "2026-12-01"},
        "source": {"type": "string", "nullable": True, "description": "Stable external id, unique across tickets"},
        "created": {"type": "number", "description": "Unix time"},
        "updated": {"type": "number", "description": "Unix time"},
        "closed": {"type": "number", "nullable": True, "description": "Unix time, null while open"},
        "start": {"type": "string", "description": "YYYY-MM-DD or empty"},
        "estimate": {"type": "number", "nullable": True, "description": "Story points or hours, your choice"},
        "open_questions": {"type": "integer", "description": "Questions on this ticket that nobody has answered yet"},
        "area_id": {"type": "integer", "nullable": True}, "area": {"type": "string", "description": "Area path such as Platform / Tools"},
        "iteration_id": {"type": "integer", "nullable": True}, "iteration": {"type": "string"},
    }
    return {
        "Error": {"type": "object", "properties": {"error": {"type": "string", "example": "no ticket APP-99"}}},
        "Project": {"type": "object", "properties": {
            "key": {"type": "string", "example": "APP"}, "name": {"type": "string", "example": "My app"},
            "description": {"type": "string"}, "created": {"type": "number"},
            "next_number": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Project tags that group the project in the navigator"},
            "counts": {"type": "object", "additionalProperties": {"type": "integer"}, "description": "Tickets per status"}}},
        "NewProject": {"type": "object", "required": ["key", "name"], "properties": {
            "key": {"type": "string", "pattern": "^[A-Z][A-Z0-9]{1,9}$", "example": "APP"},
            "name": {"type": "string", "example": "My app"}, "description": {"type": "string"},
            "tags": {"type": "string", "description": "Comma separated project tags", "example": "games,tools"}}},
        "Ticket": {"type": "object", "properties": {**ticket_properties,
            "comments": {"type": "array", "items": ref("Comment")},
            "questions": {"type": "array", "items": ref("Question")},
            "children": {"type": "array", "items": {"type": "object", "properties": {
                "key": {"type": "string"}, "title": {"type": "string"}, "status": {"type": "string"}}}},
            "links": {"type": "array", "items": ref("Link")},
            "progress": {"type": "object", "description": "All descendants except cancelled ones", "properties": {
                "total": {"type": "integer"}, "done": {"type": "integer"}, "points": {"type": "number"}, "points_done": {"type": "number"}}}}},
        "TicketSummary": {"type": "object", "properties": ticket_properties},
        "NewTicket": {"type": "object", "required": ["project", "title"], "properties": {
            "project": {"type": "string", "example": "APP"},
            "title": {"type": "string", "maxLength": store.MAX_TITLE_CHARS, "example": "Login fails on empty password"},
            "body": {"type": "string"},
            "type": {"type": "string", "enum": list(store.TICKET_TYPES), "default": "task"},
            "status": {"type": "string", "enum": list(store.STATUSES), "default": "backlog"},
            "priority": {"type": "string", "enum": list(store.PRIORITIES), "default": "medium"},
            "assignee": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}, "description": "A list, or one comma separated string"},
            "parent": {"type": "string", "description": "Parent ticket key", "example": KEY_EXAMPLE},
            "due": {"type": "string", "example": "2026-12-01"},
            "source": {"type": "string", "description": "Stable external id; a second ticket with the same value is refused"},
            "start": {"type": "string"}, "estimate": {"type": "number"},
            "area": {"type": "string", "description": "Area id or path"}, "iteration": {"type": "string", "description": "Iteration id or name"},
            "template": {"type": "integer", "description": "Template id; its values fill every field you leave out"},
            "questions": {"type": "array", "items": {"type": "string"}, "description": "Open questions to ask on the new ticket"}}},
        "TicketPatch": {"type": "object", "description": "Any subset of the editable fields",
            "properties": {
                "title": {"type": "string"}, "body": {"type": "string"},
                "type": {"type": "string", "enum": list(store.TICKET_TYPES)},
                "status": {"type": "string", "enum": list(store.STATUSES)},
                "priority": {"type": "string", "enum": list(store.PRIORITIES)},
                "assignee": {"type": "string"}, "labels": {"type": "array", "items": {"type": "string"}},
                "parent_key": {"type": "string", "description": "Empty string clears the parent"}, "due": {"type": "string"},
                "start": {"type": "string"}, "estimate": {"type": "number"},
                "area": {"type": "string", "description": "Area id or path, empty clears it"},
                "iteration": {"type": "string", "description": "Iteration id or name, empty clears it"}}},
        "Comment": {"type": "object", "properties": {
            "id": {"type": "integer"}, "author": {"type": "string"}, "body": {"type": "string"}, "created": {"type": "number"}}},
        "Question": {"type": "object", "properties": {
            "id": {"type": "integer"}, "text": {"type": "string", "maxLength": questions.MAX_QUESTION_CHARS, "example": "Which payment provider do we use?"},
            "asker": {"type": "string"}, "created": {"type": "number", "description": "Unix time"},
            "answer": {"type": "string", "description": "Empty while the question is open"}, "answerer": {"type": "string"},
            "answered": {"type": "number", "nullable": True, "description": "Unix time, null while the question is open"}}},
        "QuestionListing": {"type": "object", "properties": {
            "id": {"type": "integer"}, "ticket_key": {"type": "string", "example": KEY_EXAMPLE}, "ticket_title": {"type": "string"},
            "ticket_status": {"type": "string", "enum": list(store.STATUSES)}, "text": {"type": "string"}, "asker": {"type": "string"},
            "created": {"type": "number"}, "answer": {"type": "string"}, "answerer": {"type": "string"},
            "answered": {"type": "number", "nullable": True}}},
        "NewQuestion": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string", "maxLength": questions.MAX_QUESTION_CHARS}}},
        "NewAnswer": {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string", "maxLength": questions.MAX_ANSWER_CHARS}}},
        "NewComment": {"type": "object", "required": ["body"], "properties": {"body": {"type": "string", "example": "Reproduced on a clean install"}}},
        "Link": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": list(store.LINK_KINDS)}, "key": {"type": "string"}, "title": {"type": "string"},
            "status": {"type": "string"}, "direction": {"type": "string", "enum": ["out", "in"]}}},
        "NewLink": {"type": "object", "required": ["to"], "properties": {
            "to": {"type": "string", "example": "APP-2"}, "kind": {"type": "string", "enum": list(store.LINK_KINDS), "default": "relates"}}},
        "Event": {"type": "object", "properties": {
            "actor": {"type": "string"}, "field": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
            "created": {"type": "number"}}},
        "Board": {"type": "object", "properties": {
            "statuses": {"type": "array", "items": {"type": "string"}},
            "columns": {"type": "object", "additionalProperties": {"type": "array", "items": ref("TicketSummary")}}}},
        "Stats": {"type": "object", "properties": {
            "open": {"type": "integer"}, "unassigned": {"type": "integer"},
            "by_status": {"type": "object", "additionalProperties": {"type": "integer"}},
            "by_type": {"type": "object", "additionalProperties": {"type": "integer"}},
            "by_priority": {"type": "object", "additionalProperties": {"type": "integer"}},
            "by_assignee": {"type": "object", "additionalProperties": {"type": "integer"}}}},
        "Meta": {"type": "object", "properties": {
            "types": {"type": "array", "items": {"type": "string"}}, "statuses": {"type": "array", "items": {"type": "string"}},
            "priorities": {"type": "array", "items": {"type": "string"}}, "closed_statuses": {"type": "array", "items": {"type": "string"}},
            "link_kinds": {"type": "array", "items": {"type": "string"}}, "editable_fields": {"type": "array", "items": {"type": "string"}}}},
    }


def paths() -> dict:
    project_filter = query("project", "Project key")
    total_header = {"X-Total-Count": {"description": "Number of tickets matching the filters, before the limit", "schema": {"type": "integer"}}}
    return {
        "/healthz": {"get": {"tags": ["Service"], "summary": "Liveness check", "operationId": "healthz",
            "responses": {"200": json_response("The server is up", {"type": "object", "properties": {"ok": {"type": "boolean"}, "service": {"type": "string"}}})}}},
        "/api": {"get": {"tags": ["Service"], "summary": "Short list of endpoints", "operationId": "apiIndex",
            "responses": {"200": json_response("Summary and endpoint lines", {"type": "object", "properties": {
                "summary": {"type": "string"}, "endpoints": {"type": "array", "items": {"type": "string"}}}})}}},
        "/api/meta": {"get": {"tags": ["Service"], "summary": "Allowed values for types, statuses, priorities and links", "operationId": "meta",
            "responses": {"200": json_response("The vocabulary", ref("Meta"))}}},
        "/api/projects": {
            "get": {"tags": ["Projects"], "summary": "List projects with ticket counts per status", "operationId": "listProjects",
                "parameters": [query("tag", "Only projects carrying this project tag")],
                "responses": {"200": json_response("Projects ordered by key", {"type": "array", "items": ref("Project")})}},
            "post": {"tags": ["Projects"], "summary": "Create a project", "operationId": "createProject",
                "requestBody": json_body(ref("NewProject")),
                "responses": {"201": json_response("The new project", ref("Project")), "400": ERRORS["400"]}}},
        "/api/tickets": {
            "get": {"tags": ["Tickets"], "summary": "List tickets, highest priority first", "operationId": "listTickets",
                "parameters": [
                    project_filter,
                    query("status", "One status", {"type": "string", "enum": list(store.STATUSES)}),
                    query("type", "One type", {"type": "string", "enum": list(store.TICKET_TYPES)}),
                    query("priority", "One priority", {"type": "string", "enum": list(store.PRIORITIES)}),
                    query("assignee", "Assignee, ignoring case"),
                    query("label", "A whole label"),
                    query("q", "Text in the title, description or key; % and _ match themselves"),
                    query("source", "Exact source value"),
                    query("area", "Area id or path; includes sub-areas"),
                    query("iteration", "Iteration id"),
                    query("open", "Set to 1 to hide done and cancelled tickets", {"type": "string", "enum": ["1"]}),
                    query("questions", "Set to open to keep only tickets with an unanswered question", {"type": "string", "enum": ["open"]}),
                    query("limit", "Maximum tickets returned", {"type": "integer", "default": 500, "maximum": 5000})],
                "responses": {"200": json_response("Matching tickets", {"type": "array", "items": ref("TicketSummary")}, total_header),
                              "400": ERRORS["400"], "404": ERRORS["404"]}},
            "post": {"tags": ["Tickets"], "summary": "Create a ticket", "operationId": "createTicket",
                "requestBody": json_body(ref("NewTicket")),
                "responses": {"201": json_response("The new ticket", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/tickets/{ticket_key}": {
            "get": {"tags": ["Tickets"], "summary": "Read a ticket with comments, sub-tickets and links", "operationId": "getTicket",
                "parameters": [key_parameter()],
                "responses": {"200": json_response("The ticket", ref("Ticket")), "404": ERRORS["404"]}},
            "patch": {"tags": ["Tickets"], "summary": "Change fields; every change is written to the history", "operationId": "updateTicket",
                "parameters": [key_parameter()], "requestBody": json_body(ref("TicketPatch")),
                "responses": {"200": json_response("The updated ticket", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}},
            "delete": {"tags": ["Tickets"], "summary": "Delete a ticket that has no sub-tickets", "operationId": "deleteTicket",
                "parameters": [key_parameter()],
                "responses": {"200": json_response("Deleted", {"type": "object", "properties": {"deleted": {"type": "string"}}}),
                              "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/tickets/{ticket_key}/comments": {
            "post": {"tags": ["Tickets"], "summary": "Add a comment", "operationId": "addComment",
                "parameters": [key_parameter()], "requestBody": json_body(ref("NewComment")),
                "responses": {"201": json_response("The ticket with its comments", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/tickets/{ticket_key}/questions": {
            "post": {"tags": ["Questions"], "summary": "Ask an open question on a ticket", "operationId": "askQuestion",
                "parameters": [key_parameter()], "requestBody": json_body(ref("NewQuestion")),
                "responses": {"201": json_response("The ticket with its questions", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/questions": {
            "get": {"tags": ["Questions"], "summary": "List questions across tickets, oldest first", "operationId": "listQuestions",
                "parameters": [
                    query("state", "open (default), answered or all", {"type": "string", "enum": list(questions.QUESTION_STATES), "default": "open"}),
                    project_filter, query("ticket", "One ticket key")],
                "responses": {"200": json_response("Matching questions", {"type": "array", "items": ref("QuestionListing")}),
                              "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/questions/{question_id}/answer": {
            "post": {"tags": ["Questions"], "summary": "Answer an open question; the answer is written to the ticket history", "operationId": "answerQuestion",
                "parameters": [question_parameter()], "requestBody": json_body(ref("NewAnswer")),
                "responses": {"200": json_response("The ticket with its questions", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/questions/{question_id}/reopen": {
            "post": {"tags": ["Questions"], "summary": "Reopen an answered question and clear its answer", "operationId": "reopenQuestion",
                "parameters": [question_parameter()],
                "responses": {"200": json_response("The ticket with its questions", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/questions/{question_id}": {
            "delete": {"tags": ["Questions"], "summary": "Remove a question and its answer", "operationId": "removeQuestion",
                "parameters": [question_parameter()],
                "responses": {"200": json_response("The ticket with its questions", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/tickets/{ticket_key}/links": {
            "post": {"tags": ["Tickets"], "summary": "Link this ticket to another", "operationId": "addLink",
                "parameters": [key_parameter()], "requestBody": json_body(ref("NewLink")),
                "responses": {"201": json_response("The ticket with its links", ref("Ticket")), "400": ERRORS["400"], "404": ERRORS["404"]}}},
        "/api/tickets/{ticket_key}/events": {
            "get": {"tags": ["Tickets"], "summary": "Change history, oldest first", "operationId": "ticketEvents",
                "parameters": [key_parameter()],
                "responses": {"200": json_response("Events", {"type": "array", "items": ref("Event")}), "404": ERRORS["404"]}}},
        "/api/board": {"get": {"tags": ["Reports"], "summary": "Tickets grouped into one column per status", "operationId": "board",
            "parameters": [project_filter],
            "responses": {"200": json_response("The board", ref("Board"))}}},
        "/api/stats": {"get": {"tags": ["Reports"], "summary": "Ticket counts by status, type, priority and assignee", "operationId": "stats",
            "parameters": [project_filter],
            "responses": {"200": json_response("Counts", ref("Stats"))}}},
        "/api/openapi.json": {"get": {"tags": ["Service"], "summary": "This specification", "operationId": "openapi",
            "responses": {"200": {"description": "OpenAPI 3.0 document", "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    }


def id_parameter(name: str, description: str) -> dict:
    return {"name": name, "in": "path", "required": True, "description": description, "schema": {"type": "integer"}}


def name_parameter(name: str, description: str) -> dict:
    return {"name": name, "in": "path", "required": True, "description": description, "schema": {"type": "string"}}


def operation(tag: str, summary: str, operation_id: str, responses: dict, parameters: list | None = None, body: dict | None = None) -> dict:
    result = {"tags": [tag], "summary": summary, "operationId": operation_id, "responses": responses}
    if parameters:
        result["parameters"] = parameters
    if body:
        result["requestBody"] = body
    return result


def crud_paths(tag: str, noun: str, plural: str, collection: str, member: str, id_name: str, schema: str, new_schema: str,
               list_parameters: list | None = None) -> dict:
    parameter = id_parameter(id_name, f"{noun} id")
    return {
        collection: {
            "get": operation(tag, f"List {plural}", f"list{schema}s", {"200": json_response(plural, {"type": "array", "items": ref(schema)})},
                             list_parameters),
            "post": operation(tag, f"Create a {noun}", f"create{schema}", {"201": json_response(f"The new {noun}", ref(schema)),
                              "400": ERRORS["400"], "404": ERRORS["404"]}, body=json_body(ref(new_schema))),
        },
        member: {
            "get": operation(tag, f"Read a {noun}", f"get{schema}", {"200": json_response(noun, ref(schema)), "404": ERRORS["404"]}, [parameter]),
            "patch": operation(tag, f"Change a {noun}", f"update{schema}", {"200": json_response(f"The updated {noun}", ref(schema)),
                               "400": ERRORS["400"], "404": ERRORS["404"]}, [parameter], json_body({"type": "object"})),
            "delete": operation(tag, f"Delete a {noun}", f"delete{schema}", {"200": json_response("Deleted", {"type": "object"}),
                                "400": ERRORS["400"], "404": ERRORS["404"]}, [parameter]),
        },
    }


def organisation_paths() -> dict:
    project = {"name": "project", "in": "query", "required": False, "description": "Project key", "schema": {"type": "string"}}
    required_project = {**project, "required": True}
    paths_found = {
        "/api/overview": {"get": operation("Organisation", "Organisation, areas, boards and projects in one call", "overview",
                                           {"200": json_response("Everything the navigator needs", {"type": "object"})})},
        "/api/organisation": {
            "get": operation("Organisation", "Read the organisation name", "getOrganisation", {"200": json_response("Organisation", ref("Organisation"))}),
            "put": operation("Organisation", "Rename the organisation", "putOrganisation",
                             {"200": json_response("Organisation", ref("Organisation")), "400": ERRORS["400"]}, body=json_body(ref("Organisation")))},
        "/api/projects/{project_key}": {"patch": operation(
            "Organisation", "Change a project: name, description, lead, status, start, target, tags", "updateProject",
            {"200": json_response("The updated project", ref("Project")), "400": ERRORS["400"], "404": ERRORS["404"]},
            [name_parameter("project_key", "Project key")], json_body({"type": "object"}))},
        "/api/boards/{board_id}/items": {"post": operation(
            "Boards", "Pin a ticket to a board whatever its rules say", "pinTicket",
            {"201": json_response("The board", ref("Board")), "404": ERRORS["404"]}, [id_parameter("board_id", "Board id")],
            json_body({"type": "object", "required": ["ticket"], "properties": {"ticket": {"type": "string", "example": "APP-1"}}}))},
        "/api/boards/{board_id}/items/{ticket_key}": {"delete": operation(
            "Boards", "Unpin a ticket from a board", "unpinTicket", {"200": json_response("The board", ref("Board")), "404": ERRORS["404"]},
            [id_parameter("board_id", "Board id"), key_parameter()])},
        "/api/plan": {"get": operation("Planning", "Backlog and iterations of a project with their open tickets", "plan",
                                       {"200": json_response("The plan", {"type": "object"}), "404": ERRORS["404"]}, [required_project])},
        "/api/roadmap": {"get": operation("Planning", "Iterations and dated epics on one timeline", "roadmap",
                                          {"200": json_response("The roadmap", {"type": "object"}), "404": ERRORS["404"]}, [project])},
        "/api/tags/{tag_name}": {
            "patch": operation("Tags", "Rename a tag everywhere, or change its colour and description", "updateTag",
                               {"200": json_response("The updated tag", ref("Tag")), "400": ERRORS["400"], "404": ERRORS["404"]},
                               [name_parameter("tag_name", "Tag name")], json_body({"type": "object"})),
            "delete": operation("Tags", "Delete a tag and remove it from every ticket and board", "deleteTag",
                                {"200": json_response("What changed", {"type": "object"}), "404": ERRORS["404"]}, [name_parameter("tag_name", "Tag name")])},
        "/api/tags/{tag_name}/merge": {"post": operation(
            "Tags", "Merge a tag into another one", "mergeTag", {"200": json_response("The target tag", ref("Tag")), "400": ERRORS["400"], "404": ERRORS["404"]},
            [name_parameter("tag_name", "Tag to merge away")], json_body({"type": "object", "required": ["into"], "properties": {"into": {"type": "string"}}}))},
        "/api/tags": {
            "get": operation("Tags", "List tags with ticket and board counts, including labels that were never registered", "listTags",
                             {"200": json_response("Tags", {"type": "array", "items": ref("Tag")})}),
            "post": operation("Tags", "Register a tag with a colour and description", "createTag",
                              {"201": json_response("The new tag", ref("Tag")), "400": ERRORS["400"]}, body=json_body(ref("Tag")))},
        "/api/templates/defaults": {"post": operation("Templates", "Add the built-in templates that are missing", "seedTemplates",
                                                      {"201": json_response("Templates created", {"type": "array", "items": ref("Template")})})},
        "/api/tickets/{ticket_key}/tree": {"get": operation("Tickets", "Sub-tickets nested to any depth", "ticketTree",
                                                            {"200": json_response("The tree", {"type": "object"}), "404": ERRORS["404"]}, [key_parameter()])},
    }
    paths_found.update(crud_paths("Areas", "area", "Areas", "/api/areas", "/api/areas/{area_id}", "area_id", "Area", "NewArea"))
    paths_found.update(crud_paths("Boards", "board", "Boards", "/api/boards", "/api/boards/{board_id}", "board_id", "Board", "NewBoard",
                                  [{"name": "area", "in": "query", "required": False, "description": "Area id or name", "schema": {"type": "string"}}]))
    paths_found.update(crud_paths("Planning", "iteration", "Iterations", "/api/iterations", "/api/iterations/{iteration_id}", "iteration_id",
                                  "Iteration", "NewIteration",
                                  [{"name": "project", "in": "query", "required": False, "description": "Project key", "schema": {"type": "string"}},
                                   {"name": "state", "in": "query", "required": False, "description": "One state",
                                    "schema": {"type": "string", "enum": list(store.ITERATION_STATES)}}]))
    paths_found.update(crud_paths("Templates", "template", "Templates", "/api/templates", "/api/templates/{template_id}", "template_id",
                                  "Template", "Template",
                                  [{"name": "project", "in": "query", "required": False, "description": "Project key; adds its own templates to the shared ones",
                                    "schema": {"type": "string"}}]))
    return paths_found


def organisation_schemas() -> dict:
    count = {"type": "integer"}
    return {
        "Organisation": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string", "example": "My organisation"}}},
        "NewArea": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "example": "Platform"}, "description": {"type": "string"},
            "parent": {"type": "string", "description": "Parent area id or path, empty for a top-level area"},
            "tags": {"type": "string", "description": "Comma separated tags that group a top-level area in the navigator"}}},
        "Area": {"type": "object", "properties": {
            "id": count, "name": {"type": "string"}, "description": {"type": "string"}, "parent_id": {"type": "integer", "nullable": True},
            "tags": {"type": "array", "items": {"type": "string"}},
            "path": {"type": "string", "example": "Platform / Tools"}, "depth": count, "boards": count, "tickets": count,
            "open_tickets": count, "boards_list": {"type": "array", "items": ref("Board")}}},
        "NewBoard": {"type": "object", "required": ["area", "name"], "properties": {
            "area": {"type": "string", "description": "Area id or path", "example": "Platform"},
            "name": {"type": "string", "example": "Bugs"}, "description": {"type": "string"},
            "rules": ref("BoardRules"),
            "statuses": {"type": "array", "items": {"type": "string", "enum": list(store.STATUSES)}, "description": "Columns to show; empty shows all"}}},
        "BoardRules": {"type": "object", "description": "Which tickets the board holds besides the ones pinned to it", "properties": {
            "scope": {"type": "string", "enum": ["area", "all"], "default": "area",
                      "description": "area: tickets in this area or its sub-areas; all: any ticket matching the other rules"},
            "project": {"type": "string"}, "types": {"type": "array", "items": {"type": "string", "enum": list(store.TICKET_TYPES)}},
            "priorities": {"type": "array", "items": {"type": "string", "enum": list(store.PRIORITIES)}},
            "labels": {"type": "array", "items": {"type": "string"}, "description": "Any of these labels"},
            "assignee": {"type": "string"}, "parent": {"type": "string", "description": "Only descendants of this ticket"},
            "iteration": {"type": "integer"}}},
        "Board": {"type": "object", "properties": {
            "id": count, "area_id": count, "area": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"},
            "rules": ref("BoardRules"), "statuses": {"type": "array", "items": {"type": "string"}}, "pinned": count, "tickets": count,
            "columns": {"type": "object", "additionalProperties": {"type": "array", "items": ref("TicketSummary")}},
            "hidden": {"type": "integer", "description": "Tickets whose status has no column on this board"},
            "pinned_keys": {"type": "array", "items": {"type": "string"}}}},
        "NewIteration": {"type": "object", "required": ["project", "name", "start", "end"], "properties": {
            "project": {"type": "string", "example": "APP"}, "name": {"type": "string", "example": "Sprint 1"},
            "start": {"type": "string", "example": "2026-11-09"}, "end": {"type": "string", "example": "2026-11-20"},
            "goal": {"type": "string"}, "state": {"type": "string", "enum": list(store.ITERATION_STATES), "default": "planned"}}},
        "Iteration": {"type": "object", "properties": {
            "id": count, "project": {"type": "string"}, "name": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
            "goal": {"type": "string"}, "state": {"type": "string", "enum": list(store.ITERATION_STATES)},
            "tickets": count, "done": count, "points": {"type": "number"}, "points_done": {"type": "number"}}},
        "Tag": {"type": "object", "properties": {
            "name": {"type": "string", "example": "auth"}, "color": {"type": "string", "example": "#4cc2ff", "description": "Hex colour, empty for automatic"},
            "description": {"type": "string"}, "registered": {"type": "boolean"}, "tickets": count, "open_tickets": count, "boards": count}},
        "Template": {"type": "object", "required": ["name"], "properties": {
            "id": count, "name": {"type": "string", "example": "Bug report"}, "description": {"type": "string"},
            "project": {"type": "string", "description": "Empty for a template shared by every project"},
            "type": {"type": "string", "enum": list(store.TICKET_TYPES)}, "priority": {"type": "string", "enum": list(store.PRIORITIES)},
            "status": {"type": "string", "enum": list(store.STATUSES)}, "title": {"type": "string"}, "body": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}}, "estimate": {"type": "number", "nullable": True},
            "assignee": {"type": "string"}}},
    }


def dashboard_paths() -> dict:
    found = {
        "/api/metrics": {"post": operation("Metrics", "Measure one thing: a count, a breakdown, a trend, a burndown and more", "metric",
                         {"200": json_response("The widget as understood, and its data", ref("MetricResult")), "400": ERRORS["400"], "404": ERRORS["404"]},
                         body=json_body(ref("Widget")))},
        "/api/dashboards/defaults": {"post": operation("Dashboards", "Add the built-in dashboards that are missing", "seedDashboards",
                                                       {"201": json_response("Dashboards created", {"type": "array", "items": ref("Dashboard")})})},
        "/api/dashboards/{dashboard_id}/data": {"get": operation(
            "Dashboards", "Evaluate every widget of a dashboard", "dashboardData",
            {"200": json_response("The dashboard and one result per widget id", {"type": "object"}), "404": ERRORS["404"]},
            [id_parameter("dashboard_id", "Dashboard id")])},
    }
    found.update(crud_paths("Dashboards", "dashboard", "Dashboards", "/api/dashboards", "/api/dashboards/{dashboard_id}", "dashboard_id",
                            "Dashboard", "NewDashboard"))
    return found


def dashboard_schemas() -> dict:
    count = {"type": "integer"}
    return {
        "Widget": {"type": "object", "required": ["kind"], "properties": {
            "id": {"type": "string", "description": "Assigned when omitted"},
            "kind": {"type": "string", "enum": list(metrics.METRIC_KINDS)}, "title": {"type": "string"},
            "size": {"type": "integer", "minimum": 1, "maximum": 3, "description": "Columns the widget spans"},
            "filters": {"type": "object", "description": "project, area, iteration, type, status, priority, assignee, label, open",
                        "properties": {"project": {"type": "string"}, "area": {"type": "string"}, "iteration": count,
                                       "type": {"type": "string"}, "status": {"type": "string"}, "priority": {"type": "string"},
                                       "assignee": {"type": "string"}, "label": {"type": "string"}, "open": {"type": "boolean"}}},
            "group_by": {"type": "string", "enum": list(metrics.GROUP_FIELDS), "description": "For group widgets"},
            "chart": {"type": "string", "enum": list(metrics.CHART_STYLES), "description": "For group widgets"},
            "measure": {"type": "string", "enum": list(metrics.COUNT_MEASURES), "description": "For count widgets"},
            "days": {"type": "integer", "minimum": 1, "maximum": metrics.MAX_DAYS, "description": "Window for counts, trends and cycle time"},
            "interval": {"type": "string", "enum": list(metrics.INTERVALS), "description": "For trend widgets"},
            "iteration": {"type": "integer", "description": "For burndown widgets; the current iteration when omitted"},
            "limit": {"type": "integer", "minimum": 1, "maximum": metrics.MAX_LIMIT}}},
        "MetricResult": {"type": "object", "properties": {"widget": ref("Widget"), "data": {"type": "object", "description": "Shape depends on the kind"}}},
        "NewDashboard": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "example": "Overview"}, "description": {"type": "string"},
            "widgets": {"type": "array", "items": ref("Widget")}}},
        "Dashboard": {"type": "object", "properties": {
            "id": count, "name": {"type": "string"}, "description": {"type": "string"}, "widgets": {"type": "array", "items": ref("Widget")},
            "created": {"type": "number"}}},
    }


def kb_paths() -> dict:
    page_id = id_parameter("page_id", "Page id")
    query_parameter = lambda name, description, schema=None: query(name, description, schema)
    page_filters = [
        query_parameter("space", "Space id or key"), query_parameter("parent", "Parent page id, or root for top-level pages"),
        query_parameter("status", "One status", {"type": "string", "enum": list(kb.PAGE_STATUSES)}),
        query_parameter("type", "article or tool", {"type": "string", "enum": list(kb.PAGE_TYPES)}), query_parameter("label", "A whole tag"),
        query_parameter("stale", "1 for pages past their review date", {"type": "string", "enum": ["1"]}),
        query_parameter("favourite", "1 for the caller's favourites", {"type": "string", "enum": ["1"]}),
        query_parameter("kind", "Tool kind", {"type": "string", "enum": list(kb.TOOL_KINDS)}),
        query_parameter("location", "Tool location", {"type": "string", "enum": list(kb.TOOL_LOCATIONS)}),
        query_parameter("order", "Sort order", {"type": "string", "enum": ["updated", "title", "views", "tree"]}),
        query_parameter("translations", "1 to include translations; by default only base pages are listed", {"type": "string", "enum": ["1"]}),
        query_parameter("limit", "Maximum pages returned", {"type": "integer", "default": 200}),
    ]
    found = {
        "/api/kb/overview": {"get": operation("Knowledge", "Everything the knowledge base home shows", "kbOverview", {"200": json_response("Spaces, recent, popular, favourites, reviews", ref("KbOverview"))})},
        "/api/kb/templates": {"get": operation("Knowledge", "Page templates for new articles", "kbTemplates",
                                               {"200": json_response("Templates", {"type": "array", "items": ref("KbTemplate")})})},
        "/api/kb/spaces/{space_id}/tree": {"get": operation("Knowledge", "A space's whole page tree in one response; for large spaces page it with /children instead", "kbTree",
                                                            {"200": json_response("Root pages with children", {"type": "array", "items": {"type": "object"}}), "404": ERRORS["404"]},
                                                            [id_parameter("space_id", "Space id")])},
        "/api/kb/spaces/{space_id}/children": {"get": operation("Knowledge", "One folder level of a space, paged, with a child count per page", "kbChildren",
                                                                {"200": json_response("The pages of one level", ref("KbLevel")), "400": ERRORS["400"], "404": ERRORS["404"]},
                                                                [id_parameter("space_id", "Space id"), query("parent", "Parent page id; empty or root for the top level"),
                                                                 query("offset", "Pages to skip", {"type": "integer", "default": 0}),
                                                                 query("limit", f"Pages to return, at most {kb.LEVEL_LIMIT_MAX}", {"type": "integer", "default": kb.LEVEL_LIMIT_DEFAULT})])},
        "/api/kb/tools": {"get": operation("Tools", "The Tools category: tools on this machine and external ones", "kbTools",
                                           {"200": json_response("Tool pages", {"type": "array", "items": ref("KbPageSummary")}), "400": ERRORS["400"]},
                                           [query_parameter("kind", "Tool kind", {"type": "string", "enum": list(kb.TOOL_KINDS)}),
                                            query_parameter("location", "machine or external", {"type": "string", "enum": list(kb.TOOL_LOCATIONS)}),
                                            query_parameter("label", "A whole tag"), query_parameter("q", "Search text"),
                                            query_parameter("status", "Page status"), query_parameter("order", "updated, title, views or tree")])},
        "/api/kb/pages/{page_id}/versions": {"get": operation("Knowledge", "Edit history, newest first", "kbVersions",
                                                              {"200": json_response("Versions", {"type": "array", "items": ref("KbVersion")}), "404": ERRORS["404"]}, [page_id])},
        "/api/kb/pages/{page_id}/versions/{version}": {"get": operation("Knowledge", "One old version with its full text", "kbVersion",
                                                                        {"200": json_response("The version", {"type": "object"}), "404": ERRORS["404"]},
                                                                        [page_id, id_parameter("version", "Version number")])},
        "/api/kb/pages/{page_id}/diff": {"get": operation("Knowledge", "Line by line difference between two versions", "kbDiff",
                                                          {"200": json_response("The difference", ref("KbDiff")), "400": ERRORS["400"], "404": ERRORS["404"]},
                                                          [page_id, query("from", "Older version", {"type": "integer"}), query("to", "Newer version", {"type": "integer"})])},
        "/api/kb/pages/{page_id}/restore": {"post": operation("Knowledge", "Bring an old version back as a new version", "kbRestore",
                                                              {"200": json_response("The page", ref("KbPage")), "404": ERRORS["404"]}, [page_id],
                                                              json_body({"type": "object", "required": ["version"], "properties": {"version": {"type": "integer"}}}))},
        "/api/kb/pages/{page_id}/feedback": {
            "get": operation("Knowledge", "Comments left with feedback", "kbFeedbackList", {"200": json_response("Feedback with a comment", {"type": "array", "items": {"type": "object"}})}, [page_id]),
            "post": operation("Knowledge", "Say whether the page helped; one vote per person, a second replaces the first", "kbFeedback",
                              {"201": json_response("The page", ref("KbPage")), "400": ERRORS["400"], "404": ERRORS["404"]}, [page_id],
                              json_body({"type": "object", "required": ["helpful"], "properties": {"helpful": {"type": "boolean"}, "comment": {"type": "string"}}}))},
        "/api/kb/pages/{page_id}/favourite": {"post": operation("Knowledge", "Toggle this page in the caller's favourites", "kbFavourite",
                                                                {"200": json_response("The page", ref("KbPage")), "404": ERRORS["404"]}, [page_id])},
        "/api/kb/pages/{page_id}/verify": {"post": operation("Knowledge", "Confirm the page is still right and set the next review date", "kbVerify",
                                                             {"200": json_response("The page", ref("KbPage")), "400": ERRORS["400"], "404": ERRORS["404"]}, [page_id],
                                                             json_body({"type": "object", "properties": {"days": {"type": "integer", "default": kb.DEFAULT_REVIEW_DAYS}}}, False))},
        "/api/kb/pages/{page_id}/openapi": {"get": operation("Tools", "A tool's OpenAPI description, fetched from its URL or file and cached", "kbToolSpec",
                                                             {"200": json_response("The description and where it came from", ref("KbToolSpec")), "400": ERRORS["400"], "404": ERRORS["404"]},
                                                             [page_id, query("refresh", "1 to fetch it again", {"type": "string", "enum": ["1"]})])},
        "/api/kb/search": {"get": operation("Knowledge", "Ranked full-text search of pages and tools", "kbSearch",
                                            {"200": json_response("Hits with highlighted snippets", {"type": "array", "items": ref("KbSearchHit")})},
                                            [query("q", "Words to find; the last word matches as a prefix"), query("space", "Space id or key"),
                                             query("type", "article or tool", {"type": "string", "enum": list(kb.PAGE_TYPES)}), query("limit", "Maximum hits", {"type": "integer", "default": 20})])},
        "/api/kb/mentions": {"get": operation("Knowledge", "Pages whose text mentions a ticket", "kbMentions",
                                              {"200": json_response("Pages", {"type": "array", "items": ref("KbPageSummary")}), "400": ERRORS["400"]},
                                              [query("ticket", "Ticket key such as APP-12")])},
        "/api/search": {"get": operation("Knowledge", "One search over pages, tools and tickets", "searchEverything",
                                         {"200": json_response("Grouped results", {"type": "object"})}, [query("q", "Words to find"), query("limit", "Maximum per group", {"type": "integer", "default": 8})])},
    }
    found.update(crud_paths("Knowledge", "space", "Spaces", "/api/kb/spaces", "/api/kb/spaces/{space_id}", "space_id", "KbSpace", "NewKbSpace"))
    pages = crud_paths("Knowledge", "page", "Pages", "/api/kb/pages", "/api/kb/pages/{page_id}", "page_id", "KbPage", "NewKbPage", page_filters)
    pages["/api/kb/pages"]["get"]["responses"]["200"] = json_response("Pages without their text", {"type": "array", "items": ref("KbPageSummary")})
    pages["/api/kb/pages/{page_id}"]["get"]["parameters"].append(query("view", "1 to count this read as a view", {"type": "string", "enum": ["1"]}))
    pages["/api/kb/pages/{page_id}"]["delete"]["parameters"].append(query("cascade", "1 to delete sub-pages too", {"type": "string", "enum": ["1"]}))
    found.update(pages)
    return found


def kb_schemas() -> dict:
    count = {"type": "integer"}
    tool = {"type": "object", "description": "Only for pages in the Tools space", "properties": {
        "kind": {"type": "string", "enum": list(kb.TOOL_KINDS)}, "location": {"type": "string", "enum": list(kb.TOOL_LOCATIONS), "description": "machine or external"},
        "path": {"type": "string"}, "url": {"type": "string"}, "invoke": {"type": "string", "example": "packer build FILE"}, "version": {"type": "string"},
        "owner": {"type": "string"}, "tool_status": {"type": "string", "enum": list(kb.TOOL_STATUSES)}, "docs": {"type": "string"},
        "commands": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "summary": {"type": "string"}, "usage": {"type": "string"}}}},
        "openapi": {"type": "object", "properties": {
            "source": {"type": "string", "enum": ["", "inline", "url", "file"]}, "url": {"type": "string"}, "path": {"type": "string"},
            "spec": {"type": "object", "description": "The OpenAPI document itself when the source is inline"}}}}}
    summary_properties = {
        "id": count, "space_id": count, "parent_id": {"type": "integer", "nullable": True}, "position": count, "title": {"type": "string"},
        "page_type": {"type": "string", "enum": list(kb.PAGE_TYPES)}, "status": {"type": "string", "enum": list(kb.PAGE_STATUSES)},
        "labels": {"type": "array", "items": {"type": "string"}}, "author": {"type": "string"}, "created": {"type": "number"}, "updated": {"type": "number"},
        "review_by": {"type": "string"}, "verified_by": {"type": "string"}, "verified_at": {"type": "number", "nullable": True}, "stale": {"type": "boolean"},
        "views": count, "helpful": count, "unhelpful": count, "version": count, "excerpt": {"type": "string"}, "tool": {"type": "object"},
        "translation_of": {"type": "integer", "nullable": True, "description": "Id of the base page when this page is a translation"},
        "locale": {"type": "string", "description": "Language code of a translation such as ja or zh-cn, empty for a base page"}}
    return {
        "NewKbSpace": {"type": "object", "required": ["key", "name"], "properties": {
            "key": {"type": "string", "example": "ENG"}, "name": {"type": "string", "example": "Engineering"}, "description": {"type": "string"},
            "color": {"type": "string", "example": "#4cc2ff"}}},
        "KbSpace": {"type": "object", "properties": {
            "id": count, "key": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "kind": {"type": "string", "enum": list(kb.SPACE_KINDS)},
            "color": {"type": "string"}, "pages": count, "updated": {"type": "number", "nullable": True}}},
        "NewKbPage": {"type": "object", "required": ["space", "title"], "properties": {
            "space": {"type": "string", "description": "Space id or key; TOOLS makes a tool page"}, "title": {"type": "string", "example": "Deploy runbook"},
            "body": {"type": "string", "description": "Markdown; [[Page title]] links to a page and APP-12 links to a ticket"},
            "template": {"type": "string", "description": "A template id from /api/kb/templates; fills an empty body"},
            "parent": {"type": "integer"}, "labels": {"type": "array", "items": {"type": "string"}}, "status": {"type": "string", "enum": list(kb.PAGE_STATUSES)},
            "meta": tool, "review_days": {"type": "integer", "description": "Days until the page needs a review"}, "comment": {"type": "string"},
            "translation_of": {"type": "integer", "description": "Make this page a translation of that base page; needs locale"},
            "locale": {"type": "string", "example": "ja", "description": "Language code of the translation; needs translation_of"}}},
        "KbPageSummary": {"type": "object", "properties": summary_properties},
        "KbPage": {"type": "object", "properties": {**summary_properties, "body": {"type": "string"}, "meta": tool, "space": {"type": "object"},
                   "breadcrumbs": {"type": "array", "items": {"type": "object"}}, "children": {"type": "array", "description": f"The first {kb.CHILD_PREVIEW_LIMIT} sub-pages; page the rest with /children", "items": {"type": "object"}},
                   "children_total": count, "siblings": {"type": "object", "description": "The previous and next page under the same parent, each {id, title} or null"},
                   "backlinks": {"type": "array", "items": {"type": "object"}}, "tickets": {"type": "array", "items": {"type": "object"}},
                   "wiki": {"type": "object", "description": "Each [[link]] in the text, resolved to a page or null"}, "favourite": {"type": "boolean"},
                   "my_feedback": {"type": "boolean", "nullable": True},
                   "languages": {"type": "array", "description": "The base page and its translations, empty when the page has none",
                                 "items": {"type": "object", "properties": {"id": count, "title": {"type": "string"}, "locale": {"type": "string"}, "current": {"type": "boolean"}}}}}},
        "KbLevel": {"type": "object", "properties": {"total": count, "offset": count, "items": {"type": "array", "items": {"type": "object", "properties": {
                        "id": count, "parent_id": {"type": "integer", "nullable": True}, "position": count, "title": {"type": "string"},
                        "page_type": {"type": "string"}, "status": {"type": "string"}, "child_count": count}}}}},
        "KbVersion": {"type": "object", "properties": {"version": count, "title": {"type": "string"}, "author": {"type": "string"}, "comment": {"type": "string"},
                                                       "created": {"type": "number"}, "size": count}},
        "KbDiff": {"type": "object", "properties": {"from": count, "to": count, "added": count, "removed": count, "title_changed": {"type": "boolean"},
                   "lines": {"type": "array", "items": {"type": "object", "properties": {"op": {"type": "string", "enum": ["equal", "insert", "delete"]}, "text": {"type": "string"}}}}}},
        "KbSearchHit": {"type": "object", "properties": {"id": count, "title": {"type": "string"}, "page_type": {"type": "string"}, "space": {"type": "object"},
                        "snippet": {"type": "string", "description": "Matches are wrapped in the control characters U+0001 and U+0002"}, "rank": {"type": "number"}}},
        "KbTemplate": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "body": {"type": "string"}}},
        "KbToolSpec": {"type": "object", "properties": {"spec": {"type": "object"}, "source": {"type": "string"}, "fetched_at": {"type": "number", "nullable": True},
                                                        "error": {"type": "string", "description": "Why the last fetch failed; the cached copy is still served"}}},
        "KbOverview": {"type": "object", "properties": {"spaces": {"type": "array", "items": ref("KbSpace")}, "recent": {"type": "array", "items": ref("KbPageSummary")},
                       "popular": {"type": "array", "items": ref("KbPageSummary")}, "favourites": {"type": "array", "items": ref("KbPageSummary")},
                       "needs_review": {"type": "array", "items": ref("KbPageSummary")}, "drafts": {"type": "array", "items": ref("KbPageSummary")},
                       "counts": {"type": "object"}, "search": {"type": "boolean", "description": "Whether ranked full-text search is available"}}},
    }


def build_spec() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "LEDGER API",
            "version": API_VERSION,
            "description": "JSON API of the LEDGER ticket tracker. Send an X-Ledger-Actor header on writes to record who made a change.",
        },
        "servers": [{"url": "/"}],
        "tags": [{"name": "Service"}, {"name": "Organisation"}, {"name": "Projects"}, {"name": "Areas"}, {"name": "Boards"},
                 {"name": "Planning"}, {"name": "Tickets"}, {"name": "Questions"}, {"name": "Tags"}, {"name": "Templates"}, {"name": "Reports"},
                 {"name": "Dashboards"}, {"name": "Metrics"}, {"name": "Knowledge"}, {"name": "Tools"}],
        "paths": {**paths(), **organisation_paths(), **dashboard_paths(), **kb_paths()},
        "components": {"schemas": {**schemas(), **organisation_schemas(), **dashboard_schemas(), **kb_schemas()}},
    }
