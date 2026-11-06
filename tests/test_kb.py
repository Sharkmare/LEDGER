import datetime
import functools
import http.server
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import kb, store

MARK_ON, MARK_OFF = "\x01", "\x02"
SPEC = {"openapi": "3.0.3", "info": {"title": "Pets", "version": "2.1"},
        "paths": {"/pets": {"get": {"summary": "List pets", "tags": ["pets"]}, "post": {"summary": "Add a pet"}}, "/pets/{id}": {"delete": {"summary": "Remove a pet"}}},
        "components": {"schemas": {"Pet": {"type": "object"}}}}
SPEC_YAML = "openapi: 3.0.3\ninfo:\n  title: Yaml pets\n  version: '1'\npaths:\n  /a:\n    get:\n      summary: Fetch a\n"


def workspace():
    connection = store.connect(":memory:")
    store.create_project(connection, "APP", "App")
    kb.create_space(connection, "ENG", "Engineering")
    return connection


class SpaceTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_the_tools_space_exists_first_and_cannot_be_removed_or_renamed(self):
        spaces = kb.list_spaces(self.connection)
        self.assertEqual([(s["key"], s["kind"]) for s in spaces], [("TOOLS", "tools"), ("ENG", "docs")])
        with self.assertRaises(store.LedgerError):
            kb.delete_space(self.connection, "TOOLS")
        with self.assertRaises(store.LedgerError):
            kb.update_space(self.connection, "TOOLS", {"name": "Gadgets"})
        self.assertEqual(kb.update_space(self.connection, "TOOLS", {"description": "mine"})["description"], "mine")

    def test_space_rules(self):
        for arguments in ({"key": "e", "name": "x"}, {"key": "ENG", "name": "Other"}, {"key": "OPS", "name": "engineering"}, {"key": "OPS", "name": " "},
                          {"key": "OPS", "name": "Ops", "color": "red"}, {"key": "TOOLS", "name": "Mine"}):
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                kb.create_space(self.connection, **arguments)
        space = kb.create_space(self.connection, "ops", "Operations", color="#AABBCC")
        self.assertEqual((space["key"], space["color"], space["kind"]), ("OPS", "#aabbcc", "docs"))

    def test_a_space_with_pages_cannot_be_deleted(self):
        kb.create_page(self.connection, "ENG", "A page")
        with self.assertRaises(store.LedgerError):
            kb.delete_space(self.connection, "ENG")
        empty = kb.create_space(self.connection, "OPS", "Operations")
        kb.delete_space(self.connection, empty["id"])
        with self.assertRaises(store.NotFound):
            kb.get_space(self.connection, "OPS")


class PageTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()

    def test_translations_hide_from_lists_trees_and_counts_but_show_as_languages(self):
        base = kb.create_page(self.connection, "ENG", "Basic controls")
        japanese = kb.create_page(self.connection, "ENG", "Basic controls/ja", translation_of=base["id"], locale="JA")
        kb.create_page(self.connection, "ENG", "Basic controls/fr", translation_of=base["id"], locale="fr")
        other = kb.create_page(self.connection, "ENG", "Other")
        self.assertEqual(japanese["locale"], "ja")
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, space="ENG", order="title")], ["Basic controls", "Other"])
        self.assertEqual(len(kb.list_pages(self.connection, space="ENG", translations=True)), 4)
        self.assertEqual([n["title"] for n in kb.tree(self.connection, "ENG")], ["Basic controls", "Other"])
        self.assertEqual(kb.get_space(self.connection, "ENG")["pages"], 2)
        languages = kb.get_page(self.connection, japanese["id"])["languages"]
        self.assertEqual([(entry["locale"], entry["current"]) for entry in languages], [("", False), ("fr", False), ("ja", True)])
        self.assertEqual([(entry["locale"], entry["current"]) for entry in kb.get_page(self.connection, base["id"])["languages"]], [("", True), ("fr", False), ("ja", False)])
        self.assertEqual(kb.get_page(self.connection, other["id"])["languages"], [])

    def test_translation_rules(self):
        base = kb.create_page(self.connection, "ENG", "Guide")
        variant = kb.create_page(self.connection, "ENG", "Guide/ja", translation_of=base["id"], locale="ja")
        cases = (
            {"translation_of": base["id"], "locale": ""},
            {"translation_of": None, "locale": "de"},
            {"translation_of": base["id"], "locale": "Japanese"},
            {"translation_of": base["id"], "locale": "ja"},
            {"translation_of": variant["id"], "locale": "de"},
        )
        for fields in cases:
            with self.assertRaises(kb.LedgerError, msg=str(fields)):
                kb.create_page(self.connection, "ENG", "Another", **fields)
        with self.assertRaises(kb.LedgerError):
            kb.update_page(self.connection, base["id"], {"translation_of": variant["id"], "locale": "de"})
        with self.assertRaises(kb.LedgerError):
            kb.update_page(self.connection, base["id"], {"translation_of": base["id"], "locale": "de"})

    def test_a_page_can_be_linked_and_unlinked_after_creation_and_deleting_a_base_removes_its_translations(self):
        base = kb.create_page(self.connection, "ENG", "Guide")
        loose = kb.create_page(self.connection, "ENG", "Guide/de")
        linked = kb.update_page(self.connection, loose["id"], {"translation_of": base["id"], "locale": "de"})
        self.assertEqual((linked["translation_of"], linked["locale"]), (base["id"], "de"))
        unlinked = kb.update_page(self.connection, loose["id"], {"translation_of": None})
        self.assertEqual((unlinked["translation_of"], unlinked["locale"]), (None, ""))
        kb.update_page(self.connection, loose["id"], {"translation_of": base["id"], "locale": "de"})
        removed = kb.delete_page(self.connection, base["id"])
        self.assertEqual(removed["pages_removed"], 2)
        self.assertEqual(kb.list_pages(self.connection, space="ENG", translations=True), [])

    def test_a_tree_keeps_its_order_and_reports_breadcrumbs(self):
        root = kb.create_page(self.connection, "ENG", "Handbook")
        first = kb.create_page(self.connection, "ENG", "Setup", parent=root["id"])
        kb.create_page(self.connection, "ENG", "Deploy", parent=root["id"])
        deep = kb.create_page(self.connection, "ENG", "Local", parent=first["id"])
        tree = kb.tree(self.connection, "ENG")
        self.assertEqual([(node["title"], [c["title"] for c in node["children"]]) for node in tree], [("Handbook", ["Setup", "Deploy"])])
        self.assertEqual([crumb["title"] for crumb in kb.get_page(self.connection, deep["id"])["breadcrumbs"]], ["Handbook", "Setup"])
        kb.update_page(self.connection, first["id"], {"position": 9})
        self.assertEqual([c["title"] for c in kb.tree(self.connection, "ENG")[0]["children"]], ["Deploy", "Setup"])

    def test_parents_must_share_the_space_and_never_form_a_cycle(self):
        kb.create_space(self.connection, "OPS", "Operations")
        other = kb.create_page(self.connection, "OPS", "Elsewhere")
        root = kb.create_page(self.connection, "ENG", "Root")
        child = kb.create_page(self.connection, "ENG", "Child", parent=root["id"])
        with self.assertRaises(store.LedgerError):
            kb.create_page(self.connection, "ENG", "Bad", parent=other["id"])
        with self.assertRaises(store.LedgerError):
            kb.update_page(self.connection, root["id"], {"parent": child["id"]})
        with self.assertRaises(store.LedgerError):
            kb.update_page(self.connection, root["id"], {"parent": root["id"]})
        self.assertIsNone(kb.update_page(self.connection, child["id"], {"parent": ""})["parent_id"])

    def test_values_are_validated(self):
        for arguments in ({"title": " "}, {"title": ["a"]}, {"title": "x" * 201}, {"title": "t", "body": 5}, {"title": "t", "status": "live"},
                          {"title": "t", "labels": 5}, {"title": "t", "meta": {"kind": "cli"}}, {"title": "t", "body": "x" * (kb.MAX_BODY_CHARS + 1)},
                          {"title": "t", "review_days": 0}):
            with self.assertRaises(store.LedgerError, msg=str(arguments)):
                kb.create_page(self.connection, "ENG", **arguments)
        with self.assertRaises(store.NotFound):
            kb.create_page(self.connection, "NOPE", "t")

    def test_listing_filters(self):
        kb.create_page(self.connection, "ENG", "Alpha", labels="ops")
        kb.create_page(self.connection, "ENG", "Beta", status="draft")
        gone = kb.create_page(self.connection, "ENG", "Gamma")
        kb.update_page(self.connection, gone["id"], {"status": "archived"})
        self.assertEqual(sorted(p["title"] for p in kb.list_pages(self.connection, space="ENG")), ["Alpha", "Beta"])
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, status="draft")], ["Beta"])
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, label="ops")], ["Alpha"])
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, status="archived")], ["Gamma"])
        with self.assertRaises(store.LedgerError):
            kb.list_pages(self.connection, order="random")

    def test_delete_refuses_sub_pages_unless_cascaded_and_cleans_up(self):
        root = kb.create_page(self.connection, "ENG", "Root", body="needle here")
        kb.create_page(self.connection, "ENG", "Child", parent=root["id"], body="needle too")
        with self.assertRaises(store.LedgerError):
            kb.delete_page(self.connection, root["id"])
        result = kb.delete_page(self.connection, root["id"], cascade=True)
        self.assertEqual(result["pages_removed"], 2)
        self.assertEqual(kb.search(self.connection, "needle"), [])
        for table in ("kb_pages", "kb_versions", "kb_links"):
            self.assertEqual(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.page = kb.create_page(self.connection, "ENG", "Guide", body="one\ntwo\nthree", author="ann")

    def test_content_edits_make_versions_and_other_edits_do_not(self):
        kb.update_page(self.connection, self.page["id"], {"body": "one\ntwo\nthree\nfour"}, author="bob", comment="added four")
        kb.update_page(self.connection, self.page["id"], {"labels": "x", "status": "draft"}, author="cy")
        history = kb.list_versions(self.connection, self.page["id"])
        self.assertEqual([(v["version"], v["author"], v["comment"]) for v in history], [(2, "bob", "added four"), (1, "ann", "Created")])
        self.assertEqual(kb.get_page(self.connection, self.page["id"])["version"], 2)

    def test_an_unchanged_save_creates_nothing(self):
        kb.update_page(self.connection, self.page["id"], {"body": "one\ntwo\nthree", "title": "Guide"})
        self.assertEqual(len(kb.list_versions(self.connection, self.page["id"])), 1)

    def test_diff_counts_added_and_removed_lines(self):
        kb.update_page(self.connection, self.page["id"], {"body": "one\n2\nthree\nfour"})
        diff = kb.diff_versions(self.connection, self.page["id"], 1, 2)
        self.assertEqual((diff["added"], diff["removed"]), (2, 1))
        self.assertEqual([(line["op"], line["text"]) for line in diff["lines"]],
                         [("equal", "one"), ("delete", "two"), ("insert", "2"), ("equal", "three"), ("insert", "four")])

    def test_restore_writes_a_new_version_with_the_old_text(self):
        kb.update_page(self.connection, self.page["id"], {"body": "changed"})
        restored = kb.restore_version(self.connection, self.page["id"], 1, author="dee")
        self.assertEqual((restored["body"], restored["version"]), ("one\ntwo\nthree", 3))
        self.assertEqual(kb.list_versions(self.connection, self.page["id"])[0]["comment"], "Restored version 1")
        with self.assertRaises(store.NotFound):
            kb.get_version(self.connection, self.page["id"], 99)


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        store.create_ticket(self.connection, "APP", "A ticket")

    def test_tickets_and_wiki_links_are_found_and_resolved(self):
        target = kb.create_page(self.connection, "ENG", "Rollback")
        page = kb.create_page(self.connection, "ENG", "Deploy", body="See [[rollback]], [[Missing page]] and APP-1 and APP-99")
        loaded = kb.get_page(self.connection, page["id"])
        self.assertEqual([t["key"] for t in loaded["tickets"]], ["APP-1"])
        self.assertEqual(loaded["wiki"], {"rollback": {"id": target["id"], "title": "Rollback"}, "missing page": None})
        self.assertEqual([b["title"] for b in kb.get_page(self.connection, target["id"])["backlinks"]], ["Deploy"])
        kb.update_page(self.connection, page["id"], {"body": "no links now"})
        self.assertEqual(kb.get_page(self.connection, target["id"])["backlinks"], [])


class MentionTests(unittest.TestCase):
    def test_pages_that_mention_a_ticket_are_listed_and_archived_ones_are_not(self):
        connection = workspace()
        store.create_ticket(connection, "APP", "A ticket")
        mention = kb.create_page(connection, "ENG", "Runbook", body="Fixes APP-1 for good")
        kb.create_page(connection, "ENG", "Unrelated", body="APP-2 only")
        hidden = kb.create_page(connection, "ENG", "Old notes", body="APP-1 once")
        kb.update_page(connection, hidden["id"], {"status": "archived"})
        self.assertEqual([p["id"] for p in kb.pages_mentioning(connection, "app-1")], [mention["id"]])
        with self.assertRaises(store.LedgerError):
            kb.pages_mentioning(connection, "nonsense")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        kb.create_page(self.connection, "ENG", "Deploying the service", body="Steps to ship a release")
        kb.create_page(self.connection, "ENG", "Style guide", body="Never deploy on a Friday")
        kb.create_page(self.connection, "ENG", "Lunch menu", body="Soup and bread")

    def test_title_matches_rank_above_body_matches_and_stemming_works(self):
        hits = kb.search(self.connection, "deploy")
        self.assertEqual([h["title"] for h in hits], ["Deploying the service", "Style guide"])

    def test_prefix_and_snippet_markers(self):
        hit = kb.search(self.connection, "frid")[0]
        self.assertEqual(hit["title"], "Style guide")
        self.assertIn(f"{MARK_ON}Friday{MARK_OFF}", hit["snippet"])

    def test_words_not_all_present_still_find_something(self):
        self.assertEqual([h["title"] for h in kb.search(self.connection, "soup release")][:2].__len__(), 2)

    def test_odd_input_is_safe(self):
        for text in ('"', "*", "(", "a AND", "NEAR(", "'; DROP TABLE kb_pages; --", "   ", ""):
            self.assertIsInstance(kb.search(self.connection, text), list)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kb_pages").fetchone()[0], 3)

    def test_filters_and_archived_pages(self):
        other = kb.create_space(self.connection, "OPS", "Operations")
        kb.create_page(self.connection, other["id"], "Deploy checklist")
        self.assertEqual([h["space"]["key"] for h in kb.search(self.connection, "deploy", space="OPS")], ["OPS"])
        page = kb.list_pages(self.connection, space="ENG", order="title")[0]
        kb.update_page(self.connection, page["id"], {"status": "archived"})
        self.assertNotIn(page["title"], [h["title"] for h in kb.search(self.connection, "deploy")])

    def test_edits_update_the_index(self):
        page = kb.search(self.connection, "soup")[0]
        kb.update_page(self.connection, page["id"], {"body": "Salad only"})
        self.assertEqual(kb.search(self.connection, "soup"), [])
        self.assertEqual(kb.search(self.connection, "salad")[0]["id"], page["id"])

    def test_tool_commands_and_tags_are_searchable(self):
        kb.create_page(self.connection, "TOOLS", "Packer", labels="build", meta={"commands": [{"name": "bundle", "summary": "zips the artefacts"}]})
        self.assertEqual(kb.search(self.connection, "zips", page_type="tool")[0]["title"], "Packer")
        self.assertEqual(kb.search(self.connection, "build", page_type="tool")[0]["title"], "Packer")
        self.assertEqual(kb.search(self.connection, "zips", page_type="article"), [])

    def test_everything_finder_splits_pages_tools_and_tickets(self):
        store.create_ticket(self.connection, "APP", "Deploy broke")
        kb.create_page(self.connection, "TOOLS", "Deploy tool", meta={"invoke": "deploy --go"})
        found = kb.find_everything(self.connection, "deploy")
        self.assertEqual(([p["title"] for p in found["pages"]], [t["title"] for t in found["tools"]], [t["title"] for t in found["tickets"]]),
                         (["Deploying the service", "Style guide"], ["Deploy tool"], ["Deploy broke"]))


class ReviewAndFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.page = kb.create_page(self.connection, "ENG", "Policy", review_days=30)

    def test_a_page_goes_stale_after_its_review_date_and_verifying_clears_it(self):
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        stale = kb.update_page(self.connection, self.page["id"], {"review_by": yesterday})
        self.assertTrue(stale["stale"])
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, stale=True)], ["Policy"])
        verified = kb.verify_page(self.connection, self.page["id"], "ann", 45)
        expected = (datetime.date.today() + datetime.timedelta(days=45)).isoformat()
        self.assertEqual((verified["stale"], verified["verified_by"], verified["review_by"]), (False, "ann", expected))
        for days in (0, -1, "soon"):
            with self.assertRaises(store.LedgerError, msg=str(days)):
                kb.verify_page(self.connection, self.page["id"], "ann", days)

    def test_feedback_is_one_vote_per_person_and_counts_follow(self):
        kb.record_feedback(self.connection, self.page["id"], "ann", True)
        kb.record_feedback(self.connection, self.page["id"], "bob", False, "outdated screenshots")
        kb.record_feedback(self.connection, self.page["id"], "bob", True)
        page = kb.get_page(self.connection, self.page["id"], "bob")
        self.assertEqual((page["helpful"], page["unhelpful"], page["my_feedback"]), (2, 0, True))
        kb.record_feedback(self.connection, self.page["id"], "cy", False, "wrong link")
        self.assertEqual([(f["actor"], f["comment"]) for f in kb.list_feedback(self.connection, self.page["id"])], [("cy", "wrong link")])
        with self.assertRaises(store.LedgerError):
            kb.record_feedback(self.connection, self.page["id"], "ann", "yes")

    def test_favourites_are_per_person(self):
        self.assertTrue(kb.toggle_favourite(self.connection, self.page["id"], "ann")["favourite"])
        self.assertFalse(kb.get_page(self.connection, self.page["id"], "bob")["favourite"])
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, favourite_of="ann")], ["Policy"])
        self.assertFalse(kb.toggle_favourite(self.connection, self.page["id"], "ann")["favourite"])

    def test_views_count_only_when_asked(self):
        kb.get_page(self.connection, self.page["id"])
        kb.get_page(self.connection, self.page["id"], count_view=True)
        self.assertEqual(kb.get_page(self.connection, self.page["id"])["views"], 1)

    def test_the_overview_has_every_shelf(self):
        kb.toggle_favourite(self.connection, self.page["id"], "ann")
        overview = kb.overview(self.connection, "ann")
        self.assertEqual(sorted(overview), ["counts", "drafts", "favourites", "needs_review", "popular", "recent", "search", "spaces"])
        self.assertEqual((overview["counts"]["pages"], overview["favourites"][0]["title"], overview["search"]), (1, "Policy", True))


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.connection = workspace()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def tool(self, title="Tool", **meta):
        return kb.create_page(self.connection, "TOOLS", title, body="Notes", meta=meta)

    def test_tool_pages_live_only_in_the_tools_space_and_carry_details(self):
        tool = self.tool("Packer", kind="cli", path="C:/tools/packer.exe", invoke="packer build", version="1.2", owner="ann",
                         commands=[{"name": "build", "summary": "Build it", "usage": "packer build FILE"}])
        self.assertEqual((tool["page_type"], tool["tool"]["kind"], tool["tool"]["location"], tool["tool"]["commands"], tool["meta"]["commands"][0]["usage"]),
                         ("tool", "cli", "machine", 1, "packer build FILE"))
        article = kb.create_page(self.connection, "ENG", "Plain")
        self.assertEqual(article["page_type"], "article")
        with self.assertRaises(store.LedgerError):
            kb.update_page(self.connection, article["id"], {"meta": {"kind": "cli"}})

    def test_bad_tool_details_are_refused(self):
        bad = ({"kind": "toaster"}, {"location": "moon"}, {"tool_status": "dead"}, {"url": "ftp://x"}, {"commands": "all"}, {"commands": [{"summary": "no name"}]},
               {"colour": "red"}, {"openapi": {"source": "inline", "spec": {"nope": 1}}}, {"openapi": {"source": "url"}}, {"openapi": {"source": "file"}},
               {"openapi": {"source": "carrier pigeon"}}, {"openapi": "spec"})
        for meta in bad:
            with self.assertRaises(store.LedgerError, msg=str(meta)):
                self.tool(**meta)

    def test_an_inline_description_is_summarised_and_served(self):
        tool = self.tool("Pets", kind="api", location="external", url="https://pets.example.com", openapi={"source": "inline", "spec": SPEC})
        self.assertEqual((tool["tool"]["has_openapi"], tool["tool"]["operations"]), (True, 3))
        served = kb.tool_spec(self.connection, tool["id"])
        self.assertEqual((served["source"], served["spec"]["info"]["title"]), ("inline", "Pets"))
        self.assertEqual(kb.search(self.connection, "Remove a pet", page_type="tool")[0]["title"], "Pets")

    def test_a_file_description_in_json_or_yaml_is_read_and_cached(self):
        json_path = Path(self.directory.name) / "spec.json"
        json_path.write_text(json.dumps(SPEC), encoding="utf-8")
        yaml_path = Path(self.directory.name) / "spec.yaml"
        yaml_path.write_text(SPEC_YAML, encoding="utf-8")
        from_json = self.tool("Json tool", openapi={"source": "file", "path": str(json_path)})
        from_yaml = self.tool("Yaml tool", openapi={"source": "file", "path": str(yaml_path)})
        self.assertEqual(kb.tool_spec(self.connection, from_json["id"])["spec"]["info"]["title"], "Pets")
        self.assertEqual(kb.tool_spec(self.connection, from_yaml["id"])["spec"]["info"]["title"], "Yaml pets")
        self.assertEqual(kb.get_page(self.connection, from_yaml["id"])["tool"]["operations"], 1)
        json_path.write_text(json.dumps({**SPEC, "info": {"title": "Changed", "version": "3"}}), encoding="utf-8")
        self.assertEqual(kb.tool_spec(self.connection, from_json["id"])["spec"]["info"]["title"], "Pets")
        self.assertEqual(kb.tool_spec(self.connection, from_json["id"], refresh=True)["spec"]["info"]["title"], "Changed")

    def test_unreadable_files_are_refused_with_the_reason(self):
        text_file = Path(self.directory.name) / "notes.txt"
        text_file.write_text("{}", encoding="utf-8")
        for path, expected in ((str(text_file), "must end in"), (str(Path(self.directory.name) / "missing.json"), "no file")):
            tool = self.tool(f"Broken {expected}", openapi={"source": "file", "path": path})
            with self.assertRaises(store.LedgerError) as raised:
                kb.tool_spec(self.connection, tool["id"])
            self.assertIn(expected, str(raised.exception))

    def test_a_url_description_is_fetched_cached_and_survives_the_server_going_away(self):
        Path(self.directory.name, "openapi.json").write_text(json.dumps(SPEC), encoding="utf-8")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=self.directory.name)
        handler.log_message = lambda *args: None
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/openapi.json"
        tool = self.tool("Remote", kind="api", location="external", openapi={"source": "url", "url": url})
        self.assertEqual(kb.tool_spec(self.connection, tool["id"])["spec"]["info"]["title"], "Pets")
        server.shutdown()
        server.server_close()
        served = kb.tool_spec(self.connection, tool["id"], refresh=True)
        self.assertEqual((served["spec"]["info"]["title"], "could not fetch" in served["error"]), ("Pets", True))
        never_fetched = self.tool("Never", openapi={"source": "url", "url": "http://127.0.0.1:9/none.json"})
        with self.assertRaises(store.LedgerError):
            kb.tool_spec(self.connection, never_fetched["id"])

    def test_a_tool_without_a_description_says_so(self):
        tool = self.tool("Plain tool")
        with self.assertRaises(store.NotFound):
            kb.tool_spec(self.connection, tool["id"])
        with self.assertRaises(store.LedgerError):
            kb.tool_spec(self.connection, kb.create_page(self.connection, "ENG", "Article")["id"])

    def test_filters_by_kind_and_location(self):
        self.tool("A", kind="cli", location="machine")
        self.tool("B", kind="api", location="external")
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, space="TOOLS", tool_kind="api")], ["B"])
        self.assertEqual([p["title"] for p in kb.list_pages(self.connection, space="TOOLS", location="machine")], ["A"])


if __name__ == "__main__":
    unittest.main()
