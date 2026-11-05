import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger_cli
from test_ledger import LiveServerCase

SPEC = {"openapi": "3.0.3", "info": {"title": "Pets", "version": "2"}, "paths": {"/pets": {"get": {"summary": "List pets"}, "post": {"summary": "Add a pet"}}}}


class KnowledgeCliTests(LiveServerCase):
    def cli(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ledger_cli.main(["--base", self.base, "--as", "cli-test", *arguments])
        return buffer.getvalue()

    def data(self, *arguments):
        return json.loads(self.cli("--json", *arguments))

    def test_spaces_pages_history_and_search(self):
        self.data("kb-space", "add", "DOC", "Documentation")
        self.assertIn("DOC", self.cli("kb-space", "list"))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        body_file = Path(directory.name) / "body.md"
        body_file.write_text("# Setup\n\nInstall the zorbulator first.\n", encoding="utf-8")
        page = self.data("kb-page", "add", "DOC", "Setup guide", "--body-file", str(body_file), "--labels", "setup", "--review-days", "30")
        child = self.data("kb-page", "add", "DOC", "Troubleshooting", "--template", "how-to", "--parent", str(page["id"]))
        self.assertEqual((child["parent_id"], "## Steps" in child["body"]), (page["id"], True))
        edited = self.data("kb-page", "edit", str(page["id"]), "--body", "# Setup\n\nInstall the zorbulator, then restart.", "--comment", "added restart")
        self.assertEqual(edited["version"], 2)
        shown = self.cli("kb-page", "show", str(page["id"]))
        self.assertIn("Setup guide", shown)
        self.assertIn("Sub-pages: ", shown)
        self.assertIn("added restart", self.cli("kb-page", "history", str(page["id"])))
        self.assertIn("+ ", self.cli("kb-page", "diff", str(page["id"]), "1", "2"))
        self.assertIn("v3", self.cli("kb-page", "restore", str(page["id"]), "1").replace("[published, v3]", "v3"))
        self.assertIn("zorbulator", self.cli("kb-search", "zorbulator"))
        self.assertIn("Setup guide", self.cli("find", "zorbulator"))
        self.assertIn("Setup guide", self.cli("kb-page", "list", "--space", "DOC"))
        self.cli("kb-page", "helpful", str(page["id"]), "yes")
        self.cli("kb-page", "fav", str(page["id"]))
        self.cli("kb-page", "verify", str(page["id"]), "--days", "60")
        self.assertEqual(self.data("kb-page", "rm", str(child["id"]))["pages_removed"], 1)
        with self.assertRaises(SystemExit):
            self.cli("kb-page", "edit", str(page["id"]))
        with self.assertRaises(SystemExit):
            self.cli("kb-page", "add", "DOC", "x", "--body-file", str(Path(directory.name) / "missing.md"))

    def test_tools_with_openapi_descriptions(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        spec_path = Path(directory.name) / "pets.json"
        spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
        self.cli("kb-tool", "add", "Pet service", "--kind", "api", "--location", "external", "--url", "https://pets.example.com", "--openapi-inline", str(spec_path))
        self.cli("kb-tool", "add", "Packer", "--kind", "cli", "--invoke", "packer build", "--path", "C:/tools/packer.exe", "--labels", "build")
        file_tool = self.data("kb-tool", "add", "File described", "--kind", "api", "--openapi-file", str(spec_path))
        listing = self.cli("kb-tool", "list")
        self.assertIn("Pet service", listing)
        self.assertIn("packer build", listing)
        self.assertIn("Packer", self.cli("kb-tool", "list", "--kind", "cli"))
        self.assertNotIn("Packer", self.cli("kb-tool", "list", "--kind", "api"))
        self.assertIn("Packer", self.cli("kb-tool", "list", "-q", "packer"))
        spec_text = self.cli("kb-tool", "spec", str(file_tool["id"]))
        self.assertIn("GET", spec_text)
        self.assertIn("/pets", spec_text)
        shown = self.cli("kb-tool", "show", str(file_tool["id"]))
        self.assertIn("api on machine", shown)
        with self.assertRaises(SystemExit):
            self.cli("kb-tool", "add", "Bad", "--openapi-file", str(Path(directory.name) / "nope.json"), "--kind", "api")
            self.cli("kb-tool", "spec", "99999")


if __name__ == "__main__":
    unittest.main()
