import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import dashmodules, metrics, people, store

BUILTIN_IDS = ["count", "group", "trend", "burndown", "cycle", "aging", "workload", "velocity", "overdue"]
GOOD_SOURCE = """
MODULE = {{"id": "{id}", "title": "{id} title", "description": "about {id}", "size": 2, "filters": ["project"],
          "settings": [{{"name": "days", "kind": "number", "default": 7, "min": 1, "max": 30}},
                       {{"name": "style", "kind": "select", "options": ["flat", "tall"]}}]}}

def data(connection, settings, filters, now):
    return {{"settings": settings, "filters": filters, "now": now}}
"""


def restore_builtin_modules():
    dashmodules.activate(dashmodules.load([dashmodules.DEFAULT_FOLDER]))


class ModuleFolderCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(restore_builtin_modules)
        self.folder = Path(self.directory.name)

    def write(self, name, source, folder=None):
        path = (folder or self.folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def good(self, name, module_id=None, folder=None):
        return self.write(name, GOOD_SOURCE.format(id=module_id or Path(name).stem), folder)

    def load(self, *folders):
        with mock.patch.object(dashmodules.log, "warning"):
            return dashmodules.load(list(folders) or [self.folder])


class LoaderTests(ModuleFolderCase):
    def test_a_single_file_module_loads_with_its_declaration(self):
        self.good("alpha.py")
        registry = self.load()
        module = registry.get("alpha")
        self.assertEqual((module.title, module.description, module.size, module.filters, module.file), ("alpha title", "about alpha", 2, ("project",), "alpha.py"))
        self.assertEqual(registry.failures, [])
        self.assertEqual([setting["name"] for setting in module.settings], ["days", "style"])

    def test_a_folder_module_loads_from_module_py(self):
        self.good("module.py", "beta", self.folder / "beta")
        registry = self.load()
        self.assertEqual(registry.get("beta").file, "beta/module.py")

    def test_the_browser_script_is_found_next_to_the_module(self):
        self.good("alpha.py")
        (self.folder / "alpha.js").write_text("registerDashboardModule('alpha', {});", encoding="utf-8")
        self.good("module.py", "beta", self.folder / "beta")
        (self.folder / "beta" / "ui.js").write_text("registerDashboardModule('beta', {});", encoding="utf-8")
        self.good("gamma.py")
        registry = self.load()
        self.assertEqual(registry.script_of("alpha"), self.folder / "alpha.js")
        self.assertEqual(registry.script_of("beta"), self.folder / "beta" / "ui.js")
        with self.assertRaises(store.NotFound):
            registry.script_of("gamma")
        described = {item["id"]: item["script"] for item in registry.describe()["modules"]}
        self.assertEqual(described, {"alpha": "/api/modules/alpha/script", "beta": "/api/modules/beta/script", "gamma": None})

    def test_an_empty_folder_loads_nothing_and_reports_nothing(self):
        registry = self.load()
        self.assertEqual((registry.modules, registry.failures), ({}, []))

    def test_a_missing_folder_is_reported(self):
        registry = self.load(self.folder / "nowhere")
        self.assertEqual(len(registry.failures), 1)
        self.assertIn("does not exist", registry.failures[0]["error"])

    def test_helper_hidden_and_foreign_files_are_ignored_without_noise(self):
        self.good("_shared.py")
        self.good(".hidden.py")
        self.write("notes.txt", "not a module")
        self.write("alpha.js", "registerDashboardModule('alpha', {});")
        (self.folder / "__pycache__").mkdir()
        registry = self.load()
        self.assertEqual((registry.modules, registry.failures), ({}, []))

    def test_a_folder_without_module_py_is_reported(self):
        (self.folder / "stray").mkdir()
        registry = self.load()
        self.assertEqual([(f["file"], "module.py" in f["error"]) for f in registry.failures], [("stray/module.py", True)])

    def test_broken_modules_are_skipped_with_a_reason_and_the_rest_still_load(self):
        self.good("a_good.py")
        self.write("b_syntax.py", "MODULE = {")
        self.write("c_raises.py", "raise RuntimeError('boom at import')")
        self.write("d_nomodule.py", "def data(connection, settings, filters, now): return {}")
        self.write("e_nodata.py", "MODULE = {'id': 'nodata', 'title': 'T'}")
        self.write("f_badid.py", "MODULE = {'id': 'Bad Id', 'title': 'T'}\ndef data(*a): return {}")
        self.write("g_notitle.py", "MODULE = {'id': 'notitle'}\ndef data(*a): return {}")
        self.write("h_unknownfield.py", "MODULE = {'id': 'odd', 'title': 'T', 'colour': 'red'}\ndef data(*a): return {}")
        self.write("i_badsetting.py", "MODULE = {'id': 'badsetting', 'title': 'T', 'settings': [{'name': 'x', 'kind': 'select'}]}\ndef data(*a): return {}")
        self.write("j_reserved.py", "MODULE = {'id': 'reserved', 'title': 'T', 'settings': [{'name': 'size', 'kind': 'number'}]}\ndef data(*a): return {}")
        self.write("k_exit.py", "raise SystemExit(3)")
        registry = self.load()
        self.assertEqual(list(registry.modules), ["a_good"])
        reasons = {failure["file"]: failure["error"] for failure in registry.failures}
        self.assertEqual(sorted(reasons), ["b_syntax.py", "c_raises.py", "d_nomodule.py", "e_nodata.py", "f_badid.py", "g_notitle.py",
                                           "h_unknownfield.py", "i_badsetting.py", "j_reserved.py", "k_exit.py"])
        self.assertIn("boom at import", reasons["c_raises.py"])
        self.assertIn("MODULE must be a dict", reasons["d_nomodule.py"])
        self.assertIn("data(", reasons["e_nodata.py"])
        self.assertIn("'Bad Id'", reasons["f_badid.py"])
        self.assertIn("title is required", reasons["g_notitle.py"])
        self.assertIn("colour", reasons["h_unknownfield.py"])
        self.assertIn("options", reasons["i_badsetting.py"])
        self.assertIn("reserved", reasons["j_reserved.py"])

    def test_a_duplicate_id_keeps_the_first_module_and_reports_the_second(self):
        self.good("a_first.py", "same")
        self.good("b_second.py", "same")
        registry = self.load()
        self.assertEqual(registry.get("same").file, "a_first.py")
        self.assertEqual(len(registry.failures), 1)
        self.assertEqual(registry.failures[0]["file"], "b_second.py")
        self.assertIn("already provided", registry.failures[0]["error"])

    def test_an_earlier_folder_wins_a_duplicate_id(self):
        first, other = self.folder / "first", self.folder / "other"
        self.good("one.py", "same", first)
        self.good("two.py", "same", other)
        self.good("three.py", "extra", other)
        registry = self.load(first, other)
        self.assertEqual(sorted(registry.modules), ["extra", "same"])
        self.assertEqual(registry.get("same").file, "one.py")
        self.assertEqual(len(registry.failures), 1)

    def test_modules_are_listed_by_order_then_title(self):
        for name, order, title in (("a.py", 50, "Zed"), ("b.py", 10, "Mid"), ("c.py", 10, "Alpha")):
            self.write(name, f"MODULE = {{'id': '{name[0]}', 'title': '{title}', 'order': {order}}}\ndef data(*a): return {{}}")
        self.assertEqual([module.id for module in self.load().ordered()], ["c", "b", "a"])

    def test_a_skipped_module_is_logged(self):
        self.write("broken.py", "MODULE = {")
        with self.assertLogs("ledger.modules", level="WARNING") as captured:
            dashmodules.load([self.folder])
        self.assertTrue(any("broken.py" in line for line in captured.output))

    def test_unknown_module_ids_are_refused_with_the_loaded_list(self):
        self.good("alpha.py")
        with self.assertRaises(store.LedgerError) as raised:
            self.load().get("nope")
        self.assertIn("alpha", str(raised.exception))


class FolderConfigurationTests(unittest.TestCase):
    def test_the_default_is_the_modules_folder_in_the_repository(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(dashmodules.FOLDERS_ENV, None)
            self.assertEqual(dashmodules.default_folders(), [dashmodules.DEFAULT_FOLDER])
        self.assertEqual(dashmodules.DEFAULT_FOLDER, Path(__file__).resolve().parents[1] / "modules")

    def test_the_environment_variable_replaces_the_default_and_takes_several_folders(self):
        value = os.pathsep.join(["first", "second"])
        with mock.patch.dict(os.environ, {dashmodules.FOLDERS_ENV: value}):
            self.assertEqual(dashmodules.default_folders(), [Path("first"), Path("second")])

    def test_parse_folders_skips_blank_parts(self):
        self.assertEqual(dashmodules.parse_folders(os.pathsep.join(["a", " ", "b"])), [Path("a"), Path("b")])


class SettingTests(ModuleFolderCase):
    def module(self):
        self.good("alpha.py")
        return self.load().get("alpha")

    def test_defaults_fill_in_and_missing_optional_values_are_left_out(self):
        self.assertEqual(dashmodules.clean_settings(self.module(), {}), {"days": 7})

    def test_values_are_checked_against_the_declaration(self):
        module = self.module()
        self.assertEqual(dashmodules.clean_settings(module, {"days": "12", "style": "tall"}), {"days": 12, "style": "tall"})
        for bad in ({"days": 0}, {"days": 31}, {"days": "many"}, {"days": True}, {"style": "round"}, {"style": ["flat"]}):
            with self.assertRaises(store.LedgerError, msg=str(bad)):
                dashmodules.clean_settings(module, bad)

    def test_checkbox_text_and_iteration_settings(self):
        self.write("kinds.py", """
            MODULE = {"id": "kinds", "title": "Kinds", "settings": [
                {"name": "flag", "kind": "checkbox"}, {"name": "note", "kind": "text", "default": "hi"}, {"name": "sprint", "kind": "iteration"}]}
            def data(*a): return {}
            """)
        module = self.load().get("kinds")
        self.assertEqual(dashmodules.clean_settings(module, {}), {"flag": False, "note": "hi"})
        self.assertEqual(dashmodules.clean_settings(module, {"flag": "true", "note": "  yo ", "sprint": "4"}), {"flag": True, "note": "yo", "sprint": 4})
        with self.assertRaises(store.LedgerError):
            dashmodules.clean_settings(module, {"note": "x" * 600})
        with self.assertRaises(store.LedgerError):
            dashmodules.clean_settings(module, {"sprint": 0})

    def test_a_default_that_breaks_its_own_rules_stops_the_module_loading(self):
        self.write("bad.py", "MODULE = {'id': 'bad', 'title': 'T', 'settings': [{'name': 'n', 'kind': 'number', 'default': 99, 'max': 5}]}\ndef data(*a): return {}")
        registry = self.load()
        self.assertEqual(list(registry.modules), [])
        self.assertIn("between", registry.failures[0]["error"])


class BuiltinModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = dashmodules.load([dashmodules.DEFAULT_FOLDER])

    def test_every_dashboard_element_is_a_module_in_the_modules_folder(self):
        self.assertEqual(self.registry.failures, [])
        self.assertEqual([module.id for module in self.registry.ordered()], BUILTIN_IDS)

    def test_every_builtin_has_a_title_a_description_and_a_browser_script(self):
        for module in self.registry.ordered():
            self.assertTrue(module.title and module.description, module.id)
            self.assertIsNotNone(module.script, module.id)
            self.assertTrue(module.script.is_file(), module.id)

    def test_builtins_use_the_same_loader_as_any_other_module(self):
        for module in self.registry.ordered():
            self.assertEqual(Path(module.folder), dashmodules.DEFAULT_FOLDER)
            self.assertTrue((Path(module.folder) / module.file).is_file())

    def test_the_example_module_loads_when_dropped_in(self):
        examples = Path(__file__).resolve().parents[1] / "examples" / "modules"
        with tempfile.TemporaryDirectory() as directory:
            for source in examples.iterdir():
                (Path(directory) / source.name).write_bytes(source.read_bytes())
            registry = dashmodules.load([Path(directory)])
        self.assertEqual((list(registry.modules), registry.failures), (["stale"], []))
        self.assertIsNotNone(registry.get("stale").script)

    def test_the_readme_shows_the_example_module_exactly(self):
        root = Path(__file__).resolve().parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        for name in ("stale.py", "stale.js"):
            source = (root / "examples" / "modules" / name).read_text(encoding="utf-8").strip()
            self.assertIn(source, readme, name)

    def test_the_readme_names_every_builtin_module_and_setting_kind(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        for module_id in BUILTIN_IDS:
            self.assertIn(f"`{module_id}`", readme, module_id)
        for kind in dashmodules.SETTING_KINDS:
            self.assertIn(f"| `{kind}` |", readme, kind)
        for field in dashmodules.MODULE_FIELDS:
            self.assertIn(f"| `{field}` |", readme, field)


class WidgetThroughModulesTests(ModuleFolderCase):
    def setUp(self):
        super().setUp()
        self.connection = store.connect(":memory:")
        store.create_project(self.connection, "APP", "App")
        people.add(self.connection, "ann")
        self.write("custom.py", """
            MODULE = {"id": "custom", "title": "Custom thing", "size": 3, "filters": ["project"],
                      "settings": [{"name": "days", "kind": "number", "default": 7, "min": 1, "max": 30}]}
            def data(connection, settings, filters, now):
                return {"days": settings["days"], "filters": filters, "tickets": connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]}
            """)
        self.write("explodes.py", """
            MODULE = {"id": "explodes", "title": "Explodes"}
            def data(connection, settings, filters, now):
                raise ZeroDivisionError("division by zero")
            """)
        dashmodules.activate(dashmodules.load([dashmodules.DEFAULT_FOLDER, self.folder]))

    def test_a_custom_module_is_usable_in_a_widget_with_its_own_defaults(self):
        store.create_ticket(self.connection, "APP", "one")
        widget = metrics.clean_widget(self.connection, {"kind": "custom", "filters": {"project": "app"}})
        self.assertEqual((widget["size"], widget["days"], widget["title"], widget["filters"]), (3, 7, "Custom thing", {"project": "APP"}))
        result = metrics.evaluate(self.connection, {"kind": "custom", "days": 9})
        self.assertEqual(result["data"], {"days": 9, "filters": {}, "tickets": 1})

    def test_widgets_are_checked_against_the_module_declaration(self):
        for widget in ({"kind": "custom", "days": 31}, {"kind": "custom", "colour": "red"}, {"kind": "custom", "filters": {"type": "bug"}},
                       {"kind": "missing"}, {"kind": "burndown", "filters": {"type": "bug"}}, {"kind": "count", "style": "x"}):
            with self.assertRaises(store.LedgerError, msg=str(widget)):
                metrics.clean_widget(self.connection, widget)

    def test_widgets_saved_before_modules_still_load(self):
        legacy = {"id": "w1", "kind": "overdue", "title": "Overdue", "size": 1, "filters": {}, "days": 30, "limit": 8}
        widget = metrics.clean_widget(self.connection, legacy)
        self.assertNotIn("days", widget)
        self.assertEqual(widget["limit"], 8)
        self.assertEqual(metrics.clean_widget(self.connection, {"kind": "count", "limit": 8})["days"], 7)

    def test_a_module_that_fails_or_went_missing_only_spoils_its_own_widget(self):
        dashboard = metrics.create_dashboard(self.connection, "Mixed", widgets=[{"kind": "custom"}, {"kind": "explodes"}, {"kind": "count"}])
        self.connection.execute("UPDATE dashboards SET widgets = ? WHERE id = ?", (
            '[{"id": "a", "kind": "custom"}, {"id": "b", "kind": "explodes"}, {"id": "c", "kind": "count"}, {"id": "d", "kind": "gone"}]', dashboard["id"]))
        with self.assertLogs("ledger.modules", level="ERROR"):
            results = metrics.dashboard_data(self.connection, dashboard["id"])["results"]
        self.assertEqual(results["a"]["days"], 7)
        self.assertIn("ZeroDivisionError", results["b"]["error"])
        self.assertEqual(results["c"]["value"], 0)
        self.assertIn("gone", results["d"]["error"])


if __name__ == "__main__":
    unittest.main()
