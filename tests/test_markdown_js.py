import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "js" / "markdown_check.js"


@unittest.skipUnless(shutil.which("node"), "Node is not installed; the page renderer runs in the browser and is checked with Node")
class MarkdownRendererTests(unittest.TestCase):
    def test_the_renderer_escapes_input_and_renders_every_block(self):
        result = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
