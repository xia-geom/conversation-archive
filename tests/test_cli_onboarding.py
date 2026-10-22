"""Public CLI discovery and safe, offline first-run behavior."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliOnboardingTests(unittest.TestCase):
    def cli(self, *args, module="conversation_archive"):
        return subprocess.run(
            [sys.executable, "-m", module, *map(str, args)],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_no_arguments_show_useful_help_successfully(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("usage: conversation-archive", result.stdout)
        self.assertIn("demo --output /tmp/conversation-demo", result.stdout)
        self.assertIn("organize --help", result.stdout)
        self.assertIn("reading --help", result.stdout)
        self.assertIn("docs/getting-started.md", result.stdout)
        self.assertNotIn("__main__.py", result.stdout)

    def test_root_help_describes_every_command(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        help_text = " ".join(result.stdout.split())
        for description in (
            "invented conversations", "Audit existing entries", "Review imported conversations",
            "List export files", "Import ChatGPT or Claude exports", "Check an imported dataset",
            "Read an exact message",
        ):
            with self.subTest(description=description):
                self.assertIn(description, help_text)

    def test_workflow_help_explains_commands_and_next_steps(self):
        expectations = {
            "organize": ("init -> prepare", "Select imported conversations", "supporting quotations",
                         "inspect their diff", "docs/formats.md"),
            "reading": ("Start an audit", "answers.template.json", "whole entries", "exact range",
                        "publication preview", "fresh local Markdown", "remaining review work"),
        }
        for command, descriptions in expectations.items():
            with self.subTest(command=command):
                result = self.cli(command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"usage: conversation-archive {command}", result.stdout)
                self.assertNotIn("__main__.py", result.stdout)
                help_text = " ".join(result.stdout.split())
                for description in descriptions:
                    self.assertIn(description, help_text)

    def test_existing_leaf_commands_and_reconcile_alias_still_have_help(self):
        commands = [
            ("inventory",), ("normalize",), ("validate",), ("inspect",), ("demo",),
            *[("organize", c) for c in ("init", "prepare", "packet", "record", "draft", "check", "apply", "status")],
            *[("reading", c) for c in ("prepare", "packet", "source", "check", "publish", "status")],
            ("reconcile", "prepare"),
        ]
        for command in commands:
            with self.subTest(command=command):
                result = self.cli(*command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage: conversation-archive", result.stdout)
                self.assertEqual(result.stderr, "")

    def test_root_demo_creates_readable_document_and_rerun_preserves_every_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "example with spaces"
            result = self.cli("demo", "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            document = output / "organized.md"
            self.assertIn(str(document.resolve()), result.stdout)
            self.assertIn("Next:", result.stdout)
            self.assertIn("Checks: passed", result.stdout)
            self.assertIn("Original export: unchanged", result.stdout)
            self.assertIn("Safe replay: already_applied", result.stdout)
            self.assertIn("docs/getting-started.md", result.stdout)
            self.assertIn("predetermined review decisions", result.stdout)
            self.assertIn("The owner reported planting mint.", document.read_text(encoding="utf-8"))
            files = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
            repeated = self.cli("demo", "--output", output)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(repeated.stdout, "")
            self.assertIn("choose a new --output path", repeated.stderr)
            self.assertNotIn("Traceback", repeated.stderr)
            self.assertEqual(files, {p.relative_to(output): p.read_bytes()
                                     for p in output.rglob("*") if p.is_file()})

    def test_demo_rejects_existing_file_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "existing.md"
            output.write_text("Keep this manual edit.\n", encoding="utf-8")
            for module, args in (("conversation_archive", ("demo",)),
                                 ("conversation_archive.demo", ("--markdown",)),
                                 ("conversation_archive.demo", ())):
                with self.subTest(module=module, args=args):
                    result = self.cli(*args, "--output", output, module=module)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("choose a new --output path", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(output.read_text(encoding="utf-8"), "Keep this manual edit.\n")

    def test_legacy_demo_module_preserves_json_success_and_safe_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            for mode in ((), ("--markdown",)):
                with self.subTest(mode=mode):
                    output = Path(temp) / ("markdown" if mode else "extraction")
                    result = self.cli(*mode, "--output", output, module="conversation_archive.demo")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    report = json.loads(result.stdout)
                    self.assertTrue(report["fixture_only_not_model_accuracy"])
                    if mode:
                        self.assertEqual(report["document"], "organized.md")
                        self.assertTrue(report["original_unchanged"])
                    else:
                        self.assertEqual(report["replay_extra_calls"], 0)
                        self.assertTrue(report["canonical_files_unchanged"])
                    files = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
                    repeated = self.cli(*mode, "--output", output, module="conversation_archive.demo")
                    self.assertEqual(repeated.returncode, 2)
                    self.assertEqual(repeated.stdout, "")
                    self.assertNotIn("Traceback", repeated.stderr)
                    self.assertEqual(files, {p.relative_to(output): p.read_bytes()
                                             for p in output.rglob("*") if p.is_file()})

    def test_invalid_command_still_fails(self):
        result = self.cli("not-a-command")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
