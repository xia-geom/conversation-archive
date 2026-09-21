"""Agent routing and claim-boundary checks; no personal data or model calls."""
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

    def test_language_model_section_routes_before_demo(self):
        text = (ROOT / "README.md").read_text()
        self.assertLess(text.index("## If you are an AI agent or language model"), text.index("## Try it"))
        self.assertIn("[AGENTS.md](AGENTS.md)", text)
        self.assertIn("[project.json](project.json)", text)

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
            if command is None:
                continue
            self.assertEqual(command[:2], ["python3", "-m"])
            self.assertEqual(command[-1], "--help")
            result = subprocess.run([sys.executable, *command[1:]], cwd=ROOT,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout.lower())

    def test_local_report_is_not_a_shipped_migration_claim(self):
        task = self.project["tasks"]["migrate_authority"]
        self.assertEqual(task["status"], "reported_local_not_in_inspected_main")
        self.assertEqual(task["modules"], [])
        self.assertIsNone(task["help"])
        self.assertEqual(self.project["tasks"]["generate_llm_views"]["status"], "planned")

    def test_context_batches_and_synthetic_privacy_are_explicit(self):
        self.assertEqual(self.project["tasks"]["organize"]["default_questions"], 15)
        text = (ROOT / "docs/migration-acceptance.md").read_text()
        for required in ("Correction accounting", "Revocation", "Replay and stale input",
                         "master inaccessible", "No evidence feedback", "synthetic corrections"):
            self.assertIn(required, text)
        self.assertNotIn("/Users/", text)
        self.assertNotRegex(text, r"\b[0-9a-f]{64}\b")
