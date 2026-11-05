import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_commit_message as checker

GOOD = (
    "Add a knowledge base with a Tools category",
    "Fix list limit parsing (#12)",
    "Stop the board refresh from closing the editor\n\nThe poll replaced the page while a draft was open.",
    "Fix crash on empty search\n\nCloses #31",
    "x" * 72,
)
BAD = {
    "empty": "",
    "only comments": "# Please enter the commit message\n# lines starting with # are ignored\n",
    "too long": "x" * 73,
    "vague": "Update",
    "vague with a stop": "Fixes.",
    "merge commit": "Merge branch 'main' into feature",
    "fixup": "fixup! Add a thing",
    "no blank line": "Add a thing\nbecause it was missing",
    "long body": "Add a thing\n\n" + "\n".join(f"line {n}" for n in range(6)),
    "wide body": "Add a thing\n\n" + "y" * 101,
    "long dash": "Add a thing " + chr(0x2014) + " quickly",
    "short dash": "Add a thing " + chr(0x2013) + " quickly",
}


class CheckerTests(unittest.TestCase):
    def test_compact_messages_pass(self):
        for message in GOOD:
            self.assertEqual(checker.problems(message), [], message)

    def test_each_bad_message_is_refused_for_its_own_reason(self):
        for name, message in BAD.items():
            self.assertTrue(checker.problems(message), name)
        self.assertIn("73", checker.problems(BAD["too long"])[0])
        self.assertIn("merge", checker.problems(BAD["merge commit"])[0])
        self.assertIn("second line", checker.problems(BAD["no blank line"])[0])
        self.assertIn("6 lines", checker.problems(BAD["long body"])[0])

    def test_git_comment_lines_do_not_count(self):
        message = "Add a thing\n# Please enter the commit message\n# On branch main\n"
        self.assertEqual(checker.problems(message), [])

    def test_the_hook_script_exits_with_the_result(self):
        with tempfile.TemporaryDirectory() as directory:
            good, bad = Path(directory) / "good.txt", Path(directory) / "bad.txt"
            good.write_text("Add a thing\n", encoding="utf-8")
            bad.write_text("x" * 80 + "\n", encoding="utf-8")
            script = str(ROOT / "tools" / "check_commit_message.py")
            self.assertEqual(subprocess.run([sys.executable, script, str(good)], capture_output=True).returncode, 0)
            refused = subprocess.run([sys.executable, script, str(bad)], capture_output=True, text=True)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("80 characters", refused.stderr)
            self.assertIn("CONTRIBUTING.md", refused.stderr)
            self.assertEqual(subprocess.run([sys.executable, script], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
