from __future__ import annotations

import http.server
import json
import logging
import mimetypes
import re
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Callable

MAX_BODY_BYTES = 12_000_000
CONNECTION_TIMEOUT_SECONDS = 30
STATUS_NAMES = {200: "OK", 201: "Created", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed", 413: "Payload Too Large", 500: "Internal Server Error"}
MIME_OVERRIDES = {".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".html": "text/html", ".woff2": "font/woff2",
                  ".woff": "font/woff", ".ttf": "font/ttf", ".svg": "image/svg+xml", ".png": "image/png"}
TEXT_PREFIXES = ("text/", "application/json")
CONVERTERS = {"int": (r"\d+", int), "path": (r".+", str), "string": (r"[^/]+", str)}
logger = logging.getLogger("ledger")


class HTTPError(Exception):
    def __init__(self, code: int, description: str = ""):
        super().__init__(description)
        self.code = code
        self.name = STATUS_NAMES.get(code, "Error")
        self.description = description or self.name


def abort(code: int, description: str = "") -> None:
    raise HTTPError(code, description)


class Headers:
    def __init__(self, items: Any = ()):
        self._items: dict[str, tuple[str, str]] = {}
        for name, value in (items.items() if hasattr(items, "items") else items):
            self[name] = value

    def __setitem__(self, name: str, value: Any) -> None:
        self._items[name.lower()] = (name, str(value))

    def __getitem__(self, name: str) -> str:
        return self._items[name.lower()][1]

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._items

    def get(self, name: str, default: Any = None) -> Any:
        entry = self._items.get(name.lower())
        return entry[1] if entry else default

    def items(self) -> list[tuple[str, str]]:
        return list(self._items.values())


class Args:
    def __init__(self, query: str):
        self._values = urllib.parse.parse_qs(query, keep_blank_values=True)

    def get(self, name: str, default: Any = None) -> Any:
        values = self._values.get(name)
        return values[0] if values else default

    def __contains__(self, name: str) -> bool:
        return name in self._values


class Request:
    def __init__(self, method: str, target: str, headers: Headers, data: bytes = b""):
        parts = urllib.parse.urlsplit(target)
        self.method = method.upper()
        self.path = urllib.parse.unquote(parts.path)
        self.args = Args(parts.query)
        self.headers = headers
        self.data = data

    def get_json(self, silent: bool = False) -> Any:
        if not self.data:
            if silent:
                return None
            raise HTTPError(400, "the request needs a JSON body")
        try:
            return json.loads(self.data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            if silent:
                return None
            raise HTTPError(400, "the request body is not valid JSON") from None


class Response:
    def __init__(self, data: bytes = b"", status: int = 200, headers: Any = None):
        self.data = data
        self.status_code = status
        self.headers = headers if isinstance(headers, Headers) else Headers(headers or {})

    @property
    def mimetype(self) -> str:
        return self.headers.get("Content-Type", "").split(";")[0].strip()

    def get_json(self) -> Any:
        return json.loads(self.data.decode("utf-8"))

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None


def jsonify(value: Any) -> Response:
    return Response(json.dumps(value, ensure_ascii=False).encode("utf-8"), 200, {"Content-Type": "application/json; charset=utf-8"})


def send_from_directory(directory: str | Path, filename: str) -> Response:
    root = Path(directory).resolve()
    target = (root / filename).resolve()
    if root != target and root not in target.parents or not target.is_file():
        raise HTTPError(404, "no such file")
    kind = MIME_OVERRIDES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if kind.startswith(TEXT_PREFIXES):
        kind += "; charset=utf-8"
    return Response(target.read_bytes(), 200, {"Content-Type": kind})


class _Context(threading.local):
    request: Request | None = None
    values: dict | None = None


_context = _Context()


class _RequestProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(_context.request, name)


class _Globals:
    def __getattr__(self, name: str) -> Any:
        try:
            return _context.values[name]
        except (KeyError, TypeError):
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
        _context.values[name] = value

    def pop(self, name: str, default: Any = None) -> Any:
        return (_context.values or {}).pop(name, default)


request = _RequestProxy()
g = _Globals()


def _compile(rule: str) -> tuple[re.Pattern, dict[str, Callable]]:
    casts: dict[str, Callable] = {}

    def replace(match: re.Match) -> str:
        kind, name = match.group(1) or "string", match.group(2)
        pattern, cast = CONVERTERS[kind]
        casts[name] = cast
        return f"(?P<{name}>{pattern})"

    return re.compile("^" + re.sub(r"<(?:(\w+):)?(\w+)>", replace, rule) + "$"), casts


class Rule:
    def __init__(self, rule: str, methods: set):
        self.rule = rule
        self.methods = methods


class App:
    def __init__(self):
        self.routes: list[tuple[re.Pattern, dict, set, Callable, str]] = []
        self.before_hooks: list[Callable] = []
        self.after_hooks: list[Callable] = []
        self.teardown_hooks: list[Callable] = []
        self.error_handlers: list[tuple[type, Callable]] = []
        self.logger = logger

    def route(self, rule: str, methods: tuple[str, ...] = ("GET",)) -> Callable:
        pattern, casts = _compile(rule)

        def register(view: Callable) -> Callable:
            self.routes.append((pattern, casts, {m.upper() for m in methods}, view, rule))
            return view

        return register

    def get(self, rule: str) -> Callable:
        return self.route(rule, ("GET",))

    def post(self, rule: str) -> Callable:
        return self.route(rule, ("POST",))

    def put(self, rule: str) -> Callable:
        return self.route(rule, ("PUT",))

    def patch(self, rule: str) -> Callable:
        return self.route(rule, ("PATCH",))

    def delete(self, rule: str) -> Callable:
        return self.route(rule, ("DELETE",))

    def before_request(self, hook: Callable) -> Callable:
        self.before_hooks.append(hook)
        return hook

    def after_request(self, hook: Callable) -> Callable:
        self.after_hooks.append(hook)
        return hook

    def teardown_request(self, hook: Callable) -> Callable:
        self.teardown_hooks.append(hook)
        return hook

    def errorhandler(self, error_class: type) -> Callable:
        def register(handler: Callable) -> Callable:
            self.error_handlers.append((error_class, handler))
            return handler

        return register

    def _match(self, req: Request) -> tuple[Callable, dict]:
        path_matched = False
        for pattern, casts, methods, view, _rule in self.routes:
            found = pattern.match(req.path)
            if not found:
                continue
            path_matched = True
            if req.method in methods or (req.method == "HEAD" and "GET" in methods):
                return view, {name: casts[name](value) for name, value in found.groupdict().items()}
        raise HTTPError(405 if path_matched else 404, "method not allowed here" if path_matched else "no such page or endpoint")

    @staticmethod
    def _as_response(value: Any) -> Response:
        status = None
        if isinstance(value, tuple):
            value, status = value[0], value[1]
        if not isinstance(value, Response):
            value = jsonify(value)
        if status is not None:
            value.status_code = status
        return value

    def _handle_error(self, error: Exception) -> Response:
        ranked = [(type(error).__mro__.index(cls), handler) for cls, handler in self.error_handlers if isinstance(error, cls)]
        if ranked:
            return self._as_response(min(ranked, key=lambda pair: pair[0])[1](error))
        if isinstance(error, HTTPError):
            return Response(json.dumps({"error": error.description}).encode("utf-8"), error.code, {"Content-Type": "application/json; charset=utf-8"})
        self.logger.exception("unhandled error")
        return Response(json.dumps({"error": f"server error: {type(error).__name__}"}).encode("utf-8"), 500, {"Content-Type": "application/json; charset=utf-8"})

    def handle(self, req: Request) -> Response:
        _context.request, _context.values = req, {}
        failure: Exception | None = None
        try:
            try:
                view, arguments = self._match(req)
                for hook in self.before_hooks:
                    hook()
                response = self._as_response(view(**arguments))
            except Exception as error:
                failure = error
                response = self._handle_error(error)
            for hook in self.after_hooks:
                response = hook(response) or response
            return response
        finally:
            for hook in self.teardown_hooks:
                hook(failure)
            _context.request, _context.values = None, None

    def iter_rules(self) -> list["Rule"]:
        return [Rule(rule, methods) for _pattern, _casts, methods, _view, rule in self.routes]

    def test_client(self) -> "Client":
        return Client(self)

    def run(self, host: str = "127.0.0.1", port: int = 8000, threaded: bool = True) -> None:
        app = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = CONNECTION_TIMEOUT_SECONDS

            def log_message(self, format: str, *args: Any) -> None:
                logger.info("%s %s", self.address_string(), format % args)

            def respond(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY_BYTES:
                    response = Response(json.dumps({"error": "the request is too large"}).encode("utf-8"), 413, {"Content-Type": "application/json"})
                    self.close_connection = True
                else:
                    body = self.rfile.read(length) if length else b""
                    response = app.handle(Request(self.command, self.path, Headers(self.headers.items()), body))
                payload = b"" if self.command == "HEAD" else response.data
                self.send_response(response.status_code)
                for name, value in response.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(response.data)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = respond

            def handle(self) -> None:
                try:
                    super().handle()
                except (ConnectionError, TimeoutError):
                    self.close_connection = True

        class Server(http.server.ThreadingHTTPServer if threaded else http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        with Server((host, port), Handler) as server:
            server.serve_forever()


class Client:
    def __init__(self, app: App):
        self.app = app

    def open(self, method: str, path: str, json_body: Any = None, data: Any = None, headers: Any = None) -> Response:
        header_set = Headers(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            header_set["Content-Type"] = "application/json"
        elif data is not None:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")
        else:
            body = b""
        return self.app.handle(Request(method, path, header_set, body))

    def get(self, path: str, headers: Any = None) -> Response:
        return self.open("GET", path, headers=headers)

    def delete(self, path: str, headers: Any = None) -> Response:
        return self.open("DELETE", path, headers=headers)

    def post(self, path: str, json: Any = None, data: Any = None, headers: Any = None) -> Response:
        return self.open("POST", path, json, data, headers)

    def put(self, path: str, json: Any = None, data: Any = None, headers: Any = None) -> Response:
        return self.open("PUT", path, json, data, headers)

    def patch(self, path: str, json: Any = None, data: Any = None, headers: Any = None) -> Response:
        return self.open("PATCH", path, json, data, headers)
