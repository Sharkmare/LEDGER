import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "js" / "roadmap_check.js"


@unittest.skipUnless(shutil.which("node"), "Node is not installed; the roadmap layout is computed in the browser and is checked with Node")
class RoadmapTests(unittest.TestCase):
    def test_every_layout_rule_holds(self):
        result = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
