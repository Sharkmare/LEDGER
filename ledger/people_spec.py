from __future__ import annotations

SCHEMA_PREFIX = "#/components/schemas/"
ERROR_REF = {"$ref": SCHEMA_PREFIX + "Error"}
TICKET_REF = {"$ref": SCHEMA_PREFIX + "Ticket"}
PERSON_REF = {"$ref": SCHEMA_PREFIX + "Person"}


def _json(description: str, schema: dict) -> dict:
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def paths() -> dict:
    refused = _json("The request was refused; the message says why", ERROR_REF)
    missing = _json("No such person", ERROR_REF)
    name_parameter = {"name": "person_name", "in": "path", "required": True, "description": "Registered name, lowercase",
                      "schema": {"type": "string", "example": "ann"}}
    return {
        "/api/people": {
            "get": {"tags": ["People"], "summary": "List registered people with their open ticket counts", "operationId": "listPeople",
                "responses": {"200": _json("Registered people", {"type": "array", "items": PERSON_REF})}},
            "post": {"tags": ["People"], "summary": "Register a person so tickets can be assigned to them", "operationId": "addPerson",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": SCHEMA_PREFIX + "NewPerson"}}}},
                "responses": {"201": _json("The new person", PERSON_REF), "400": refused}}},
        "/api/people/{person_name}": {
            "delete": {"tags": ["People"], "summary": "Remove a person; refused while they have open tickets", "operationId": "removePerson",
                "parameters": [name_parameter], "responses": {"200": _json("The removed person", PERSON_REF), "400": refused, "404": missing}}},
        "/api/queue": {
            "get": {"tags": ["People"], "summary": "Open tickets assigned to a person; each row says why it needs attention: assigned, in review or an open question",
                "operationId": "personQueue",
                "parameters": [{"name": "person", "in": "query", "required": False, "description": "Name; defaults to the requesting actor. An unregistered name has an empty queue",
                               "schema": {"type": "string"}}],
                "responses": {"200": _json("The queue", {"$ref": SCHEMA_PREFIX + "Queue"}), "400": refused}}},
    }


def schemas() -> dict:
    return {
        "Person": {"type": "object", "properties": {"name": {"type": "string", "example": "ann"}, "created": {"type": "number"},
                                                    "open_tickets": {"type": "integer"}}},
        "NewPerson": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string", "maxLength": 40, "example": "ann"}}},
        "QueueTicket": {"allOf": [TICKET_REF, {"type": "object", "properties": {
            "reasons": {"type": "array", "items": {"type": "string", "enum": ["assigned", "review", "question"]}}}}]},
        "Queue": {"type": "object", "properties": {"person": {"type": "string"}, "count": {"type": "integer"},
                                                   "tickets": {"type": "array", "items": {"$ref": SCHEMA_PREFIX + "QueueTicket"}}}},
    }
