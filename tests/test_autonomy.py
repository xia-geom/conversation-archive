"""Failure injection for controller state; all providers here are deterministic fakes."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import autonomy as a
from conversation_archive.extraction import ExtractionError, request_for
from test_extraction import packet, proposal

USAGE = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 25}


class AutonomyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "state"
        self.ids = ["P0001-0001", "P0002-0001"]
        a.initialize(self.root, self.ids, {"synthetic": True}, "invented-test-model")
        self.calls = 0

    def loader(self, pid):
        return packet(pid)

    def worker(self, request, attempt, plan):
        self.calls += 1
        return {"proposal": proposal(request), "usage": USAGE, "error": None}

    def test_resume_never_repeats_successful_calls(self):
        result = a.execute(self.root, self.loader, self.worker)
        self.assertEqual(self.calls, 2)
        self.assertTrue(result["all_candidates_extracted"])
        self.assertFalse(result["raw_review_or_master_integration_claimed"])
        a.execute(self.root, self.loader, self.worker)
        self.assertEqual(self.calls, 2)
        self.assertEqual(result["usage"]["input_tokens"], 200)
        self.assertFalse((self.root / "decisions").exists())

    def test_cumulative_call_budget_persists_across_restarts(self):
        self.assertEqual(a.execute(self.root, self.loader, self.worker, max_calls=1)["stop_reason"], "call_budget")
        a.execute(self.root, self.loader, self.worker, max_calls=1)
        self.assertEqual(self.calls, 1)
        a.execute(self.root, self.loader, self.worker, max_calls=2)
        self.assertEqual(self.calls, 2)

    def test_observed_token_budget_does_not_double_count_cache(self):
        result = a.execute(self.root, self.loader, self.worker, max_tokens=126)
        self.assertEqual(self.calls, 2)  # 100 input + 25 output, NOT +40 cached.
        self.assertTrue(result["all_candidates_extracted"])

    def test_token_budget_stops_between_calls(self):
        result = a.execute(self.root, self.loader, self.worker, max_tokens=125)
        self.assertEqual(self.calls, 1)
        self.assertEqual(result["stop_reason"], "observed_token_budget")

    def test_missing_usage_stops_and_remains_visible(self):
        def worker(*args):
            result = self.worker(*args)
            result["usage"] = None
            return result
        result = a.execute(self.root, self.loader, worker)
        self.assertEqual(self.calls, 1)
        self.assertEqual(result["unknown_usage_calls"], 1)
        a.execute(self.root, self.loader, self.worker)
        self.assertEqual(self.calls, 1)

    def test_invalid_response_blocks_without_automatic_retry(self):
        def worker(*args):
            result = self.worker(*args)
            result["proposal"]["candidates"][0]["evidence"][0]["quote"] = "fiction"
            return result
        result = a.execute(self.root, self.loader, worker)
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["usage"]["input_tokens"], 100)
        a.execute(self.root, self.loader, self.worker)
        self.assertEqual(self.calls, 1)

    def test_prompt_limit_does_not_truncate_or_charge(self):
        result = a.execute(self.root, self.loader, self.worker, max_prompt_chars=10)
        self.assertEqual(self.calls, 0)
        self.assertEqual(result["stop_reason"], "prompt_size_limit_no_truncation")

    def test_saved_candidate_tampering_rejected(self):
        a.execute(self.root, self.loader, self.worker)
        target = self.root / "jobs" / self.ids[0] / "candidate.json"
        body = a.load(target)
        body["proposal"]["candidates"][0]["statement"] = "changed"
        a.atomic_json(target, body)
        with self.assertRaises(ExtractionError):
            a.read_state(self.root)

    def test_changed_model_plan_rejected(self):
        plan = a.load(self.root / "plan.json")
        plan["model"] = "different-model"
        a.atomic_json(self.root / "plan.json", plan)
        with self.assertRaises(ExtractionError):
            a.read_state(self.root)

    def test_lock_blocks_second_controller(self):
        with a.controller_lock(self.root):
            with self.assertRaises(ExtractionError):
                a.execute(self.root, self.loader, self.worker)
        self.assertEqual(self.calls, 0)

    def test_keyboard_interrupt_requires_recovery_no_repeat(self):
        def interrupted(*args):
            self.calls += 1
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            a.execute(self.root, self.loader, interrupted)
        result = a.execute(self.root, self.loader, self.worker)
        self.assertEqual(result["stop_reason"], "recovery_required")
        self.assertEqual(self.calls, 1)
        result = a.recover(self.root, self.loader)
        self.assertEqual(result["unknown_usage_calls"], 1)
        self.assertEqual(result["counts"]["blocked"], 1)

    def test_receipt_recovery_is_idempotent_and_does_not_call_provider(self):
        with patch.object(a, "_finish", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                a.execute(self.root, self.loader, self.worker)
        result = a.recover(self.root, self.loader)
        self.assertEqual(result["usage"], USAGE)
        result = a.recover(self.root, self.loader)
        self.assertEqual(result["usage"], USAGE)
        self.assertEqual(self.calls, 1)
        a.execute(self.root, self.loader, self.worker)
        self.assertEqual(self.calls, 2)

    def test_unknown_exception_message_not_saved(self):
        def failure(*args):
            raise RuntimeError("private example content")
        a.execute(self.root, self.loader, failure)
        receipt = a.load(self.root / "jobs" / self.ids[0] / "attempt-001" / "receipt.json")
        self.assertEqual(receipt["error"], "RuntimeError")
        self.assertNotIn("private example content", str(receipt))

    def test_changed_evidence_before_acceptance_leaves_recoverable_receipt(self):
        loads = 0
        def loader(pid):
            nonlocal loads
            loads += 1
            return packet(pid, text="old" if loads == 1 else "changed")
        with self.assertRaises(ExtractionError):
            a.execute(self.root, loader, self.worker)
        self.assertEqual(self.calls, 1)
        self.assertEqual(a.read_state(self.root)[1]["jobs"][self.ids[0]]["status"], "in_flight")

    def test_unsafe_packet_id_rejected(self):
        with self.assertRaises(ExtractionError):
            a.initialize(Path(self.temp.name) / "other", ["../../private"], {}, "fake")

    def test_boolean_and_invalid_budgets_rejected(self):
        for value in (0, -1, True):
            with self.assertRaises(ExtractionError):
                a.execute(self.root, self.loader, self.worker, max_calls=value)

    def test_usage_validation(self):
        for usage in ({**USAGE, "input_tokens": True}, {**USAGE, "cached_input_tokens": 101}, {"output_tokens": 1}):
            self.assertIsNone(a.checked_usage(usage))

    def test_cli_requires_transfer_permission_before_provider_creation(self):
        with patch("builtins.print"):
            self.assertEqual(a.main(["run", "--state", str(self.root)]), 2)
        self.assertEqual(self.calls, 0)

    def test_receipt_tampering_rejected(self):
        a.execute(self.root, self.loader, self.worker)
        target = self.root / "jobs" / self.ids[0] / "attempt-001" / "receipt.json"
        body = a.load(target)
        body["usage"]["input_tokens"] = 0
        a.atomic_json(target, body)
        with self.assertRaises(ExtractionError):
            a.read_state(self.root)

    def test_existing_unrelated_state_directory_rejected(self):
        other = Path(self.temp.name) / "other"
        other.mkdir()
        (other / "unrelated.txt").write_text("preserve me")
        with self.assertRaises(ExtractionError):
            a.initialize(other, [], {}, "fake")
        self.assertEqual((other / "unrelated.txt").read_text(), "preserve me")
