import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "js" / "planning_html_check.js"


@unittest.skipUnless(shutil.which("node"), "Node is not installed; the board rule chips and progress bars are built in the browser and are checked with Node")
class PlanningHtmlTests(unittest.TestCase):
    def test_every_chip_and_progress_rule_holds(self):
        result = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
