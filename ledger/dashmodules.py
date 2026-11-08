from __future__ import annotations

import importlib.util
import itertools
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import modulekit
from .store import LedgerError, NotFound, _require_text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = ROOT / "modules"
FOLDERS_ENV = "LEDGER_MODULES"
MODULE_FILE = "module.py"
SCRIPT_FILE = "ui.js"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
SETTING_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
RESERVED_SETTINGS = ("id", "title", "kind", "size", "filters")
SETTING_KINDS = ("number", "select", "text", "checkbox", "iteration")
SETTING_FIELDS = ("name", "label", "kind", "default", "min", "max", "options", "help", "empty_label")
MODULE_FIELDS = ("id", "title", "description", "size", "order", "filters", "settings")
MAX_TITLE = 80
MAX_TEXT_SETTING = 500
MAX_SIZE = 3
DEFAULT_ORDER = 100
NUMBER_LIMITS = (1, 1_000_000)
IDENTIFIER_SOURCE = itertools.count(1)

log = logging.getLogger("ledger.modules")


@dataclass(frozen=True)
class Module:
    id: str
    title: str
    description: str
    size: int
    order: int
    filters: tuple
    settings: tuple
    data: Callable[..., Any]
    folder: str
    file: str
    script: Path | None

    def describe(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description, "size": self.size, "order": self.order,
                "filters": list(self.filters), "settings": [dict(setting) for setting in self.settings], "folder": self.folder, "file": self.file,
                "script": f"/api/modules/{self.id}/script" if self.script else None}


class Registry:
    def __init__(self, folders: list[Path]):
        self.folders = [str(folder) for folder in folders]
        self.modules: dict[str, Module] = {}
        self.failures: list[dict] = []

    def get(self, module_id: Any) -> Module:
        found = self.modules.get(module_id) if isinstance(module_id, str) else None
        if found is None:
            known = ", ".join(self.modules) or "none loaded"
            raise LedgerError(f"no dashboard module {module_id!r}; loaded modules are {known}")
        return found

    def ordered(self) -> list[Module]:
        return sorted(self.modules.values(), key=lambda module: (module.order, module.title.lower(), module.id))

    def script_of(self, module_id: str) -> Path:
        module = self.modules.get(module_id)
        if module is None or module.script is None or not module.script.is_file():
            raise NotFound(f"module {module_id!r} has no script")
        return module.script

    def describe(self) -> dict:
        return {"folders": list(self.folders), "modules": [module.describe() for module in self.ordered()], "failures": list(self.failures)}

    def fail(self, folder: Path, file: str, error: str) -> None:
        self.failures.append({"folder": str(folder), "file": file, "error": error})
        log.warning("dashboard module %s skipped: %s", Path(folder, file) if file else folder, error)


def default_folders() -> list[Path]:
    configured = os.environ.get(FOLDERS_ENV, "").strip()
    if not configured:
        return [DEFAULT_FOLDER]
    return [Path(part).expanduser() for part in configured.split(os.pathsep) if part.strip()]


def parse_folders(text: str) -> list[Path]:
    return [Path(part).expanduser() for part in text.split(os.pathsep) if part.strip()]


def _normalise_setting(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("a setting must be a dict")
    name = raw.get("name")
    if not isinstance(name, str) or not SETTING_PATTERN.match(name):
        raise ValueError(f"setting name {name!r} must be lower case letters, digits and underscores, starting with a letter")
    if name in RESERVED_SETTINGS or name.startswith("f_"):
        raise ValueError(f"setting name {name!r} is reserved; reserved names are {', '.join(RESERVED_SETTINGS)} and anything starting with f_")
    unknown = sorted(set(raw) - set(SETTING_FIELDS))
    if unknown:
        raise ValueError(f"setting {name} has unknown field {', '.join(unknown)}; fields are {', '.join(SETTING_FIELDS)}")
    kind = raw.get("kind", "text")
    if kind not in SETTING_KINDS:
        raise ValueError(f"setting {name}: kind {kind!r} is not one of {', '.join(SETTING_KINDS)}")
    setting: dict[str, Any] = {"name": name, "label": str(raw.get("label") or name), "kind": kind, "help": str(raw.get("help") or "")}
    if kind == "number":
        low, high = raw.get("min", NUMBER_LIMITS[0]), raw.get("max", NUMBER_LIMITS[1])
        if isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, int) or not isinstance(high, int) or low > high:
            raise ValueError(f"setting {name}: min and max must be whole numbers with min not above max")
        setting["min"], setting["max"] = low, high
    if kind == "select":
        options = raw.get("options")
        if not isinstance(options, (list, tuple)) or not options:
            raise ValueError(f"setting {name}: a select needs a non-empty options list")
        normalised = []
        for option in options:
            value, label = (option.get("value"), option.get("label")) if isinstance(option, dict) else (option, option)
            if not isinstance(value, str):
                raise ValueError(f"setting {name}: option values must be text")
            normalised.append({"value": value, "label": str(label if label is not None else value)})
        if len({option["value"] for option in normalised}) != len(normalised):
            raise ValueError(f"setting {name}: option values must be unique")
        setting["options"] = normalised
    if kind == "iteration":
        setting["empty_label"] = str(raw.get("empty_label") or "None")
    if "default" in raw and raw["default"] is not None:
        default = clean_setting_value(setting, raw["default"])
        if default is not None:
            setting["default"] = default
    return setting


def _normalise_filters(raw: Any) -> tuple:
    if raw is True:
        return modulekit.FILTER_KEYS
    if raw in (False, None):
        return ()
    if not isinstance(raw, (list, tuple)) or any(key not in modulekit.FILTER_KEYS for key in raw):
        raise ValueError(f"filters must be True, False or a list of {', '.join(modulekit.FILTER_KEYS)}")
    return tuple(dict.fromkeys(raw))


def _build(declaration: Any, data: Any, folder: Path, file: str, script: Path | None) -> Module:
    if not isinstance(declaration, dict):
        raise ValueError("MODULE must be a dict")
    unknown = sorted(set(declaration) - set(MODULE_FIELDS))
    if unknown:
        raise ValueError(f"MODULE has unknown field {', '.join(unknown)}; fields are {', '.join(MODULE_FIELDS)}")
    module_id = declaration.get("id")
    if not isinstance(module_id, str) or not ID_PATTERN.match(module_id):
        raise ValueError(f"id {module_id!r} must be lower case letters, digits, - and _, starting with a letter, at most 40 characters")
    title = " ".join(str(declaration.get("title") or "").split())
    if not title:
        raise ValueError("title is required")
    if not callable(data):
        raise ValueError("the module must define a data(connection, settings, filters, now) function")
    size, order = declaration.get("size", 1), declaration.get("order", DEFAULT_ORDER)
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_SIZE:
        raise ValueError(f"size must be a whole number from 1 to {MAX_SIZE}")
    if isinstance(order, bool) or not isinstance(order, int):
        raise ValueError("order must be a whole number")
    raw_settings = declaration.get("settings", [])
    if not isinstance(raw_settings, (list, tuple)):
        raise ValueError("settings must be a list")
    settings = [_normalise_setting(raw) for raw in raw_settings]
    names = [setting["name"] for setting in settings]
    if len(set(names)) != len(names):
        raise ValueError("setting names must be unique")
    return Module(module_id, title[:MAX_TITLE], str(declaration.get("description") or ""), size, order, _normalise_filters(declaration.get("filters")),
                  tuple(settings), data, str(folder), file, script)


def _import(path: Path):
    name = f"ledger_dashboard_module_{next(IDENTIFIER_SOURCE)}"
    spec = importlib.util.spec_from_file_location(name, path)
    imported = importlib.util.module_from_spec(spec)
    sys.modules[name] = imported
    try:
        spec.loader.exec_module(imported)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return imported


def _candidates(folder: Path):
    for entry in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if entry.name.startswith(("_", ".")):
            continue
        if entry.is_file() and entry.suffix == ".py":
            yield entry.name, entry, entry.with_suffix(".js")
        elif entry.is_dir():
            yield f"{entry.name}/{MODULE_FILE}", entry / MODULE_FILE, entry / SCRIPT_FILE


def load(folders: list[Path]) -> Registry:
    registry = Registry(list(folders))
    for folder in registry.folders:
        folder = Path(folder)
        if not folder.is_dir():
            registry.fail(folder, "", "the modules folder does not exist")
            continue
        for file, source, script in _candidates(folder):
            if not source.is_file():
                registry.fail(folder, file, f"no {MODULE_FILE} in this folder")
                continue
            try:
                imported = _import(source)
                module = _build(getattr(imported, "MODULE", None), getattr(imported, "data", None), folder, file, script if script.is_file() else None)
            except (Exception, SystemExit) as error:
                registry.fail(folder, file, f"{type(error).__name__}: {error}")
                continue
            if module.id in registry.modules:
                earlier = registry.modules[module.id]
                registry.fail(folder, file, f"id {module.id!r} is already provided by {Path(earlier.folder, earlier.file)}")
                continue
            registry.modules[module.id] = module
    log.info("loaded %d dashboard modules, skipped %d", len(registry.modules), len(registry.failures))
    return registry


def clean_setting_value(setting: dict, value: Any) -> Any:
    name, kind = setting["name"], setting["kind"]
    blank = value is None or value == ""
    if kind == "checkbox":
        return False if blank else value is True or str(value).strip().lower() in ("1", "true", "yes", "on")
    if blank:
        return setting.get("default")
    if kind == "number":
        return modulekit.whole_number(name, value, setting["min"], setting["max"])
    if kind == "iteration":
        return modulekit.whole_number(name, value, 1, 10**9)
    if kind == "select":
        choices = [option["value"] for option in setting["options"]]
        if not isinstance(value, str) and not isinstance(value, (int, float)) or isinstance(value, bool):
            raise LedgerError(f"{name} must be one of {', '.join(choices)}")
        text = str(value)
        if text not in choices:
            raise LedgerError(f"{name} {text!r} is not one of {', '.join(choices)}")
        return text
    text = _require_text(name, value).strip()
    if len(text) > MAX_TEXT_SETTING:
        raise LedgerError(f"{name} is longer than {MAX_TEXT_SETTING} characters")
    return text or setting.get("default")


def clean_settings(module: Module, given: dict) -> dict:
    cleaned = {}
    for setting in module.settings:
        value = clean_setting_value(setting, given.get(setting["name"]))
        if value is not None:
            cleaned[setting["name"]] = value
    return cleaned


_active: Registry | None = None


def activate(registry: Registry) -> Registry:
    global _active
    _active = registry
    return registry


def current() -> Registry:
    if _active is None:
        activate(load(default_folders()))
    return _active
