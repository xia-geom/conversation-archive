"""Telemetry/command contract tests. No actual Codex or model account required."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from conversation_archive.codex_worker import CodexWorker, REQUIRED_FLAGS, event_summary
from conversation_archive.extraction import ExtractionError


class CodexWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "events.jsonl"

    def test_completed_turn_usage(self):
        self.path.write_text('{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20,"reasoning_output_tokens":10}}\n')
        self.assertEqual(event_summary(self.path)["usage"], {"input_tokens":100,"cached_input_tokens":40,"output_tokens":20})

    def test_missing_usage_is_unknown_not_zero(self):
        self.path.write_text('{"type":"turn.started"}\n')
        self.assertIsNone(event_summary(self.path)["usage"])

    def test_incomplete_usage_is_unknown(self):
        self.path.write_text('{"type":"turn.completed","usage":{"input_tokens":100}}\n')
        self.assertIsNone(event_summary(self.path)["usage"])

    def test_invalid_json_and_duplicate_keys(self):
        for text in ('broken', '{"type":"error","type":"turn.completed"}', '[]'):
            self.path.write_text(text)
            self.assertIsNotNone(event_summary(self.path)["error"])

    def test_tool_use_is_rejected_not_silently_accepted(self):
        self.path.write_text('{"type":"item.completed","item":{"type":"mcp_tool_call"}}\n')
        self.assertEqual(event_summary(self.path)["error"], "Unexpected tool activity")

    def test_cli_contract_is_explicit_and_read_only(self):
        worker = object.__new__(CodexWorker)
        worker.executable = "codex"
        command = worker.command({"model":"invented-model","effort":"medium"}, Path("/invented"))
        self.assertIn("read-only", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("features.shell_tool=false", command)
        self.assertIn("features.unified_exec=false", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], "-")

    def test_unsupported_cli_fails_closed(self):
        with patch("subprocess.run", return_value=SimpleNamespace(stdout="old CLI")):
            with self.assertRaises(ExtractionError):
                CodexWorker()

    def test_preflight_records_version_without_model_call(self):
        values = [SimpleNamespace(stdout=" ".join(REQUIRED_FLAGS)), SimpleNamespace(stdout="invented-codex-version")]
        with patch("subprocess.run", side_effect=values) as run:
            worker = CodexWorker()
        self.assertEqual(worker.version, "invented-codex-version")
        self.assertEqual(run.call_count, 2)

    def test_failed_later_turn_does_not_claim_complete_usage(self):
        self.path.write_text('{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":0,"output_tokens":20}}\n{"type":"turn.failed"}\n')
        self.assertIsNone(event_summary(self.path)["usage"])
