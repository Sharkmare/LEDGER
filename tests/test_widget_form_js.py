import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import dashmodules

SCRIPT = Path(__file__).resolve().parent / "js" / "widget_form_check.js"


@unittest.skipUnless(shutil.which("node"), "Node is not installed; the dashboard widget form is converted in the browser and is checked with Node")
class WidgetFormTests(unittest.TestCase):
    def test_every_conversion_rule_holds(self):
        listing = dashmodules.load([dashmodules.DEFAULT_FOLDER]).describe()
        with tempfile.TemporaryDirectory() as directory:
            listing_file = Path(directory) / "modules.json"
            listing_file.write_text(json.dumps(listing), encoding="utf-8")
            result = subprocess.run(["node", str(SCRIPT), str(listing_file)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
