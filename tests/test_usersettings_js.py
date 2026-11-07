import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "js" / "usersettings_check.js"


@unittest.skipUnless(shutil.which("node"), "Node is not installed; the saved view settings run in the browser and are checked with Node")
class UserSettingsTests(unittest.TestCase):
    def test_every_user_setting_check_holds(self):
        result = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
