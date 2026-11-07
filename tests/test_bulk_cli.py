import contextlib
import io
import json
import unittest

import ledger_cli
from ledger import bulk_cli
from tests.test_ledger import LiveServerCase


class KeyParsingTests(unittest.TestCase):
    def test_json_list_output_gives_its_keys(self):
        self.assertEqual(bulk_cli.keys_from_text(json.dumps([{"key": "A-1", "title": "x"}, {"key": "A-2"}])), ["A-1", "A-2"])

    def test_json_list_of_strings(self):
        self.assertEqual(bulk_cli.keys_from_text('["A-1", "B-7"]'), ["A-1", "B-7"])

    def test_plain_lines_use_the_first_word_and_skip_other_lines(self):
        text = "APP-1  [todo] first\n\nAPP-12 second\n2 tickets\n"
        self.assertEqual(bulk_cli.keys_from_text(text), ["APP-1", "APP-12"])


class BulkCliTests(LiveServerCase):
    def run_cli(self, *arguments, stdin=""):
        buffer = io.StringIO()
        code = 0
        original = bulk_cli.sys.stdin
        bulk_cli.sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(buffer):
                try:
                    ledger_cli.main(["--base", self.base, "--as", "cli-bulk", *arguments])
                except SystemExit as error:
                    code = error.code
        finally:
            bulk_cli.sys.stdin = original
        return code, buffer.getvalue()

    def setUp(self):
        self.run_cli("new-project", "BCLI", "Bulk cli")
        self.keys = [json.loads(self.run_cli("--json", "add", "BCLI", f"t{n}")[1])["key"] for n in range(3)]

    def test_keys_on_the_command_line_with_summary(self):
        code, output = self.run_cli("bulk", *self.keys, "--priority", "high", "--add-label", "x", "--comment", "triage")
        self.assertEqual((code, output.strip()), (0, "updated 3, unchanged 0, failed 0"))
        shown = json.loads(self.run_cli("--json", "show", self.keys[0])[1])
        self.assertEqual((shown["priority"], shown["labels"], shown["comments"][0]["body"]), ("high", ["x"], "triage"))

    def test_failures_are_listed_and_exit_one(self):
        code, output = self.run_cli("bulk", self.keys[0], "BCLI-999", "--status", "in_review")
        self.assertEqual(code, 1)
        self.assertIn("updated 1, unchanged 0, failed 1", output)
        self.assertIn("BCLI-999:", output)

    def test_json_output_still_exits_one_on_failure(self):
        code, output = self.run_cli("--json", "bulk", "BCLI-999", "--status", "in_review")
        self.assertEqual((code, json.loads(output)["failed"][0]["key"]), (1, "BCLI-999"))

    def test_remove_label_and_parent(self):
        self.run_cli("bulk", *self.keys, "--add-label", "a", "--add-label", "b")
        self.run_cli("bulk", *self.keys[1:], "--rm-label", "a", "--parent", self.keys[0])
        child = json.loads(self.run_cli("--json", "show", self.keys[1])[1])
        self.assertEqual((child["labels"], child["parent_key"]), (["b"], self.keys[0]))

    def test_keys_piped_from_list_json(self):
        self.run_cli("person-add", "ann")
        listing = self.run_cli("--json", "list", "--project", "BCLI")[1]
        code, output = self.run_cli("bulk", "--keys-from", "-", "--assignee", "ann", stdin=listing)
        listed = len(json.loads(listing))
        self.assertGreaterEqual(listed, 3)
        self.assertEqual((code, output.strip()), (0, f"updated {listed}, unchanged 0, failed 0"))

    def test_refuses_without_keys_or_changes(self):
        for arguments in (("bulk", "--status", "done"), ("bulk", self.keys[0]), ("bulk", "--keys-from", "x", "--status", "done")):
            with self.assertRaises(SystemExit) as raised:
                with contextlib.redirect_stdout(io.StringIO()):
                    ledger_cli.main(["--base", self.base, *arguments])
            self.assertNotIn(raised.exception.code, (0, None))


if __name__ == "__main__":
    unittest.main()
