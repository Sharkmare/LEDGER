import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import changelog


def git(repository, *arguments):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *arguments], cwd=repository, check=True, capture_output=True)


def commit(repository, subject):
    (repository / "file.txt").write_text(subject, encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", subject)


class HeadingTests(unittest.TestCase):
    def test_the_first_word_picks_the_heading(self):
        cases = {"Add tags to projects": "Added", "Show the sort control": "Added", "Fix list limit parsing (#12)": "Fixed",
                 "Keep scroll positions": "Fixed", "Remove the Clear button": "Removed", "Sort lists by key": "Changed", "Collapse areas": "Changed"}
        for subject, heading in cases.items():
            self.assertEqual(changelog.heading_for(subject), heading, subject)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository = Path(self.directory.name)
        git(self.repository, "init", "-q")
        commit(self.repository, "LEDGER v1.0.0")
        git(self.repository, "tag", "v1.0.0")
        commit(self.repository, "Add a thing")
        commit(self.repository, "Fix a crash")
        commit(self.repository, "Tidy the layout")
        commit(self.repository, "LEDGER v1.1.0")
        git(self.repository, "tag", "v1.1.0")
        commit(self.repository, "Remove an old option")

    def text(self, upcoming=None):
        return changelog.generate(self.repository, upcoming, today="2026-01-02")

    def test_tagged_ranges_become_sections_newest_first_without_release_commits(self):
        text = self.text()
        self.assertLess(text.index("## Unreleased"), text.index("## 1.1.0"))
        self.assertLess(text.index("## 1.1.0"), text.index("## 1.0.0"))
        section = text.split("## 1.1.0", 1)[1].split("## 1.0.0")[0]
        self.assertIn("### Added\n\n- Add a thing", section)
        self.assertIn("### Fixed\n\n- Fix a crash", section)
        self.assertIn("### Changed\n\n- Tidy the layout", section)
        self.assertIn("No changes recorded.", text.split("## 1.0.0", 1)[1])

    def test_a_release_names_the_commits_since_the_last_tag(self):
        text = self.text("1.2.0")
        self.assertIn("## 1.2.0 (2026-01-02)", text)
        self.assertIn("### Removed\n\n- Remove an old option", text)
        self.assertNotIn("Unreleased", text)

    def test_releasing_a_tagged_version_is_refused(self):
        with self.assertRaises(ValueError):
            self.text("1.1.0")

    def test_check_passes_when_current_and_fails_after_a_new_commit(self):
        output = self.repository / "CHANGELOG.md"
        self.assertEqual(changelog.main(["--repository", str(self.repository), "--output", str(output)]), 0)
        self.assertEqual(changelog.main(["--repository", str(self.repository), "--output", str(output), "--check"]), 0)
        commit(self.repository, "Add another thing")
        self.assertEqual(changelog.main(["--repository", str(self.repository), "--output", str(output), "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
