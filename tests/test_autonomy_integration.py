"""Use the actual importer, frozen review inventory, and controller together."""
from pathlib import Path
import tempfile
import unittest

from conversation_archive.demo import run_demo


class AutonomyIntegrationTests(unittest.TestCase):
    def test_synthetic_raw_to_candidates_resume_and_master_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_demo(Path(temp) / "demo")
        self.assertTrue(report["all_candidates_extracted"])
        self.assertEqual(report["replay_extra_calls"], 0)
        self.assertTrue(report["fabricated_quote_rejected"])
        self.assertEqual(report["raw_reviewed_pieces"], 0)
        self.assertTrue(report["canonical_files_unchanged"])
        self.assertGreater(report["packets"], 1)
