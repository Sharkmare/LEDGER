import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "js" / "tag_groups_check.js"


@unittest.skipUnless(shutil.which("node"), "Node is not installed; the navigator tag grouping runs in the browser and is checked with Node")
class TagGroupsTests(unittest.TestCase):
    def test_every_grouping_rule_holds(self):
        result = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
