import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from test_ledger import LiveServerCase


class SimilarCliTests(LiveServerCase):
    def run_cli(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return out.getvalue(), err.getvalue()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ledger_cli.call(cls.base, "POST", "/api/projects", "t", {"key": "CLS", "name": "Cli similar"})
        for title in ("Login page crashes on submit", "Login page crashes on submit button", "Login page crashes on submit click",
                      "Login page crashes on submit again"):
            ledger_cli.call(cls.base, "POST", "/api/tickets", "t", {"project": "CLS", "title": title})

    def test_add_warns_on_stderr_with_at_most_three_lines_and_still_creates(self):
        out, err = self.run_cli("add", "CLS", "Login page crashes on submit")
        lines = err.strip().splitlines()
        self.assertEqual(lines[0], "Similar open tickets:")
        self.assertEqual(len(lines), 4)
        self.assertRegex(lines[1], r"^CLS-\d+ .+ \(\d+%\)$")
        self.assertIn("(100%)", lines[1])
        self.assertNotIn("Similar", out)
        self.assertIn("Login page crashes on submit", out)

    def test_json_output_on_stdout_stays_parseable(self):
        out, err = self.run_cli("--json", "add", "CLS", "Login page crashes on submit")
        self.assertTrue(json.loads(out)["key"].startswith("CLS-"))
        self.assertIn("Similar open tickets:", err)

    def test_the_flag_skips_the_check(self):
        out, err = self.run_cli("add", "CLS", "Login page crashes on submit", "--no-similar-check")
        self.assertEqual(err, "")
        self.assertIn("Login page crashes", out)

    def test_nothing_is_printed_when_nothing_is_close(self):
        out, err = self.run_cli("add", "CLS", "Rotate the database backup keys")
        self.assertEqual(err, "")
        self.assertIn("Rotate the database backup keys", out)

    def test_a_failing_check_does_not_stop_the_ticket_being_created(self):
        original = ledger_cli.find_similar
        ledger_cli.find_similar = lambda *_: (_ for _ in ()).throw(SystemExit("ledger: boom"))
        try:
            out, err = self.run_cli("add", "CLS", "Brand new unrelated work item")
        finally:
            ledger_cli.find_similar = original
        self.assertIn("Brand new unrelated work item", out)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
