"""Keep the product surface small and its actual capabilities explicit."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AgentEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))

    def test_root_entrypoints_remain_short(self):
        self.assertLessEqual(len((ROOT / "README.md").read_text().split()), 600)
        self.assertLessEqual(len((ROOT / "AGENTS.md").read_text().split()), 750)
        self.assertLessEqual(len((ROOT / "docs/README.md").read_text().split()), 300)

    def test_primary_product_and_reading_path_are_markdown(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("organized.md", text)
        self.assertIn("[Architecture](ARCHITECTURE.md)", text)
        self.assertIn("[Agent instructions](AGENTS.md)", text)
        self.assertIn("agent", text.lower())
        self.assertNotIn("docs/machine-archive.md", text)
        self.assertNotIn("docs/knowledge-map.md", text)
        self.assertIn("Markdown", self.project["primary_reader"])
        self.assertIn("organized.md", self.project["target_authority"]["canonical"])

    def test_task_paths_exist_and_stay_in_repo(self):
        self.assertEqual(self.project["schema_version"], "1.0")
        self.assertEqual(self.project["instructions"], "AGENTS.md")
        for task in self.project["tasks"].values():
            for name in [task["guide"], *task["modules"]]:
                path = (ROOT / name).resolve()
                self.assertTrue(path.is_relative_to(ROOT))
                self.assertTrue(path.is_file(), name)

    def test_task_help_commands_execute_without_data_or_model(self):
        for task in self.project["tasks"].values():
            command = task["help"]
            self.assertEqual(command[:2], ["python3", "-m"])
            self.assertEqual(command[-1], "--help")
            result = subprocess.run([sys.executable, *command[1:]], cwd=ROOT,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout.lower())

    def test_removed_architecture_is_not_hidden_in_required_workflow(self):
        self.assertEqual(set(self.project["tasks"]), {"organize", "import", "extract", "raw_store"})
        self.assertFalse(self.project["tasks"]["organize"]["requires_database"])
        self.assertFalse(self.project["tasks"]["organize"]["unattended_semantic_integration"])
        self.assertFalse(self.project["tasks"]["extract"]["automatic_document_update"])
        for name in ("machine_archive", "structured_archive", "knowledge_map", "snapshot_review"):
            self.assertFalse((ROOT / "conversation_archive" / (name + ".py")).exists())

    def test_real_workflow_and_privacy_requirements_stay_explicit(self):
        text = (ROOT / "ARCHITECTURE.md").read_text()
        for required in ("primary reader", "Manual edits", "source", "semantic-search", "No step imports SQL"):
            self.assertIn(required, text)
        self.assertNotIn("/Users/", text)
        self.assertIn("synthetic", text)
        self.assertIn("not", text)
