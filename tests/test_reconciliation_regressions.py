"""Regression checks for review completeness and recoverable installation.

All inputs are invented. These tests never open the owner's archive.
"""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import reconciliation as r
from conversation_archive.model import FormatError
from conversation_archive.pipeline import normalize

MASTER = """---
entry_count: 1
distinct_retained_sources: 0
correction_count: 0
next_entry_id: "E0002"
next_source_id: "SRC-001"
next_correction_id: "COR0001"
---
# Invented archive
<a id="e0001"></a>
## E0001 — Invented garden
The owner planted mint.
"""


class ReconciliationRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = self.root / "inputs"
        shutil.copytree(Path(__file__).parent / "fixtures", self.inputs)
        self.dataset = self.root / "dataset"
        normalize(self.inputs / "demo.toml", self.dataset)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.master = self.archive / r.FILES[0]
        self.master.write_text(MASTER)
        for name in r.FILES[1:]:
            (self.archive / name).write_text("# Invented report\n")
        self.member = self.root / "membership.json"
        r.atomic_json(
            self.member,
            dict(
                conversation_ids=["invented-gpt-two"],
                observed_at="2026-01-01",
                evidence="Synthetic fixture only",
                project_name="Invented",
            ),
        )
        self.run = self.root / "run"
        r.prepare(self.dataset, self.master, self.run, membership=self.member)

    def decision(self, uncertain=False):
        packet = r.packet(self.run)
        findings = []
        if uncertain:
            piece = next(
                p for p in packet["pieces"] if p["segment_index"] >= 0 and p["text"]
            )
            findings = [
                dict(
                    finding_id="F1",
                    outcome="uncertain_overlap",
                    attribution="owner",
                    reason="Cannot identify which invented garden is described",
                    quotes=[
                        dict(
                            message_record_id=piece["message_record_id"],
                            segment_index=piece["segment_index"],
                            start=piece["start"],
                            end=piece["end"],
                            text=piece["text"],
                        )
                    ],
                )
            ]
        document = dict(
            decision_id="D1",
            reviewer="Synthetic test",
            reviewed_at="2026-01-01",
            findings=findings,
            coverage=[
                dict(
                    piece_id=p["piece_id"],
                    outcome="uncertain_overlap" if uncertain else "excluded",
                    reason="Explicitly reviewed synthetic exercise",
                    finding_ids=["F1"] if uncertain else [],
                )
                for p in packet["pieces"]
            ],
        )
        r.record(self.run, document)
        return document

    def batch(self, document, unresolved=False, change=False):
        files = {}
        for name in r.FILES:
            before = (self.archive / name).read_text()
            after = before
            if change:
                after += (
                    "\nReviewed.\n"
                    if name == r.FILES[0]
                    else "\n## R0001 — Invented comparison\n\n"
                    "| Before | After |\n| --- | --- |\n| Old. | New. |\n"
                )
            files[name] = dict(
                before_sha256=r.digest(before),
                after_sha256=r.digest(after),
                patches=[dict(before=before, after=after)] if change else [],
            )
        return dict(
            batch_id="B1",
            decision_ids=[document["decision_id"]],
            files=files,
            finding_dispositions=(
                {
                    "D1/F1": dict(
                        outcome="unresolved", reason="More source evidence needed"
                    )
                }
                if unresolved
                else {}
            ),
        )

    def interrupt(self, batch):
        original = r.atomic_text

        def fail_on_report(path, text):
            if Path(path).name == r.FILES[1]:
                raise OSError("Simulated power loss before first report")
            return original(path, text)

        with patch.object(r, "atomic_text", side_effect=fail_on_report):
            with self.assertRaises(OSError):
                r.apply(self.run, batch)
        self.assertEqual(r.load(self.run / "changes/B1.json")["status"], "installing")

    def test_unresolved_finding_prevents_complete_after_installation(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        state = r.status(self.run)
        self.assertEqual(state["covered_pieces"], state["total_pieces"])
        self.assertEqual(state["counts"].get("reviewed_with_gaps"), 1)
        self.assertFalse(state["complete"])

    def test_absent_observed_member_remains_gap_after_found_chat_completed(self):
        member = self.root / "claude-membership.json"
        r.atomic_json(
            member,
            dict(
                conversation_ids=["invented-claude-empty", "invented-not-exported"],
                observed_at="2026-01-01",
                evidence="Synthetic UI list",
                project_name="Invented",
            ),
        )
        run = self.root / "claude-run"
        initial = r.prepare(
            self.dataset, self.master, run, provider="claude", membership=member
        )
        self.assertEqual(initial["missing_membership_ids"], ["invented-not-exported"])
        packet = r.packet(run)
        decision = dict(
            decision_id="D-empty",
            reviewer="Synthetic test",
            reviewed_at="2026-01-01",
            findings=[],
            coverage=[
                dict(
                    piece_id=p["piece_id"],
                    outcome="excluded",
                    reason="Invented empty exported conversation inspected",
                )
                for p in packet["pieces"]
            ],
        )
        r.record(run, decision)
        r.apply(run, self.batch(decision))
        final = r.status(run)
        self.assertEqual(final["counts"].get("integrated"), 1)
        self.assertEqual(final["missing_membership_ids"], ["invented-not-exported"])
        self.assertFalse(final["complete"])

    def test_installing_decision_cannot_be_superseded_and_remains_recoverable(self):
        document = self.decision()
        batch = self.batch(document, change=True)
        self.interrupt(batch)
        replacement = {
            **document,
            "decision_id": "D2",
            "supersedes": document["decision_id"],
        }
        with self.assertRaises(FormatError):
            r.record(self.run, replacement)
        self.assertEqual(r.apply(self.run, batch)["status"], "applied")
        self.assertEqual(self.master.read_text().count("Reviewed."), 1)
        self.assertEqual(r.apply(self.run, batch)["status"], "already_applied")

    def test_other_batch_cannot_overtake_interrupted_installation(self):
        document = self.decision()
        batch = self.batch(document, change=True)
        self.interrupt(batch)
        another = copy.deepcopy(batch)
        another["batch_id"] = "B2"
        with self.assertRaisesRegex(FormatError, "Recover pending installation"):
            r.apply(self.run, another)
        self.assertFalse((self.run / "changes/B2.json").exists())
        self.assertEqual(r.apply(self.run, batch)["status"], "applied")

    def test_status_rejects_modified_source(self):
        with (self.inputs / "chatgpt.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaises(FormatError):
            r.status(self.run)

    def test_status_rejects_modified_dataset(self):
        with (self.dataset / "messages.jsonl").open("a") as stream:
            stream.write("\n")
        with self.assertRaises(FormatError):
            r.status(self.run)

    def test_mixed_chatgpt_unknown_part_has_its_own_review_unit(self):
        message = dict(
            provider="chatgpt",
            role="user",
            content_kind="multimodal_text",
            provenance=dict(json_pointer="/message"),
            text_segments=[
                dict(json_pointer="/message/content/parts/0", kind="text", text="hello")
            ],
            raw=dict(
                content=dict(
                    parts=[
                        "hello",
                        dict(content_type="unfamiliar", payload="unique evidence"),
                    ]
                )
            ),
        )
        units = r.units(message)
        self.assertEqual(units[0]["text"], "hello")
        other = next(u for u in units if u["json_pointer"].endswith("/parts/1"))
        self.assertLess(other["segment_index"], 0)
        self.assertEqual(json.loads(other["text"])["payload"], "unique evidence")

    def test_mixed_claude_tool_payload_not_hidden_by_readable_text(self):
        message = dict(
            provider="claude",
            role="assistant",
            content_kind="claude_blocks",
            provenance=dict(json_pointer="/message"),
            text_segments=[
                dict(json_pointer="/message/content/0/text", kind="text", text="reply")
            ],
            raw=dict(
                content=[
                    dict(type="text", text="reply"),
                    dict(type="tool_result", content="invented tool evidence"),
                    dict(type="thinking", thinking="Not owner evidence"),
                ]
            ),
        )
        units = r.units(message)
        tool = next(u for u in units if u["json_pointer"].endswith("/content/1"))
        self.assertEqual(json.loads(tool["text"])["content"], "invented tool evidence")
        internal = next(u for u in units if u["json_pointer"].endswith("/content/2"))
        self.assertEqual(internal["kind"], "internal_assistant_content")
        self.assertEqual(internal["text"], "")

    def completed_revision(self, previous, name, completed_at, outcome):
        """Synthetic journal fixture: no additional canonical installation."""
        revision = copy.deepcopy(previous)
        revision["batch_id"] = name
        revision["batch"]["batch_id"] = name
        revision["completed_at"] = completed_at
        revision["finding_dispositions"]["D1/F1"] = dict(
            outcome=outcome, reason="Explicit synthetic revision"
        )
        revision["batch"]["finding_dispositions"] = copy.deepcopy(
            revision["finding_dispositions"]
        )
        r.atomic_json(self.run / "changes" / (name + ".json"), revision)
        return revision

    def test_latest_completed_resolution_clears_historical_gap(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        prior_path = self.run / "changes/B1.json"
        prior = r.load(prior_path)
        prior["completed_at"] = "2026-01-01T12:00:00Z"
        r.atomic_json(prior_path, prior)
        old_bytes = prior_path.read_bytes()
        # A filename sorting before B1 must still win by its completion instant.
        self.completed_revision(
            prior, "A-later-resolution", "2026-01-01T13:00:00Z", "excluded"
        )
        result = r.status(self.run)
        self.assertTrue(result["complete"])
        self.assertEqual(result["counts"].get("integrated"), 1)
        self.assertEqual(prior_path.read_bytes(), old_bytes)

    def test_latest_reopening_wins_over_old_resolution_across_timezones(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        prior_path = self.run / "changes/B1.json"
        prior = r.load(prior_path)
        prior["completed_at"] = "2026-01-01T12:00:00Z"
        r.atomic_json(prior_path, prior)
        self.completed_revision(
            prior, "Z-resolution", "2026-01-01T13:00:00Z", "excluded"
        )
        self.completed_revision(
            prior, "A-reopening", "2026-01-01T09:00:00-05:00", "unresolved"
        )
        result = r.status(self.run)
        self.assertFalse(result["complete"])
        self.assertEqual(result["counts"].get("reviewed_with_gaps"), 1)

    def test_same_instant_finding_dispositions_have_no_implicit_precedence(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        prior_path = self.run / "changes/B1.json"
        prior = r.load(prior_path)
        prior["completed_at"] = "2026-01-01T12:00:00Z"
        r.atomic_json(prior_path, prior)
        self.completed_revision(prior, "B2", "2026-01-01T07:00:00-05:00", "excluded")
        with self.assertRaisesRegex(FormatError, "Ambiguous completed journal order"):
            r.status(self.run)

    def test_completion_without_timezone_cannot_establish_latest_disposition(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        path = self.run / "changes/B1.json"
        journal = r.load(path)
        journal["completed_at"] = "2026-01-01T12:00:00"
        r.atomic_json(path, journal)
        with self.assertRaisesRegex(FormatError, "timezone-aware completed_at"):
            r.status(self.run)

    def test_incomplete_resolution_does_not_override_completed_gap(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        prior = r.load(self.run / "changes/B1.json")
        revision = self.completed_revision(
            prior, "B2", "2099-01-01T12:00:00Z", "excluded"
        )
        revision["status"] = "installing"
        r.atomic_json(self.run / "changes/B2.json", revision)
        result = r.status(self.run)
        self.assertFalse(result["complete"])
        self.assertEqual(result["counts"].get("reviewed_with_gaps"), 1)

    def resolution_batch(self, document, prior="B1", batch_id="B2", change=False):
        batch = self.batch(document, change=change)
        batch["batch_id"] = batch_id
        batch["finding_dispositions"] = {
            "D1/F1": dict(
                outcome="excluded",
                reason="Explicitly resolved: invented example is outside archive scope",
            )
        }
        batch["resolution_revision"] = dict(
            prior_batch_id=prior,
            finding_ids=["D1/F1"],
            reason="Resolve the earlier documented overlap question",
        )
        return batch

    def test_new_batch_cannot_reuse_decision_to_duplicate_installed_text(self):
        document = self.decision()
        first = self.batch(document, change=True)
        r.apply(self.run, first)
        before_files = {name: (self.archive / name).read_bytes() for name in r.FILES}
        files = {}
        for name in r.FILES:
            before = (self.archive / name).read_text()
            after = before + (
                "\nReviewed.\n"
                if name == r.FILES[0]
                else "\n## R0002 — Same decision twice\n\n"
                "| Before | After |\n| --- | --- |\n| Old. | New. |\n"
            )
            files[name] = dict(
                before_sha256=r.digest(before),
                after_sha256=r.digest(after),
                patches=[dict(before=before, after=after)],
            )
        second = dict(
            batch_id="B2", decision_ids=["D1"], finding_dispositions={}, files=files
        )
        with self.assertRaisesRegex(FormatError, "Decision already installed"):
            r.check(self.run, second)
        with self.assertRaisesRegex(FormatError, "Decision already installed"):
            r.apply(self.run, second)
        self.assertEqual(
            before_files, {name: (self.archive / name).read_bytes() for name in r.FILES}
        )
        self.assertEqual(self.master.read_text().count("Reviewed."), 1)
        self.assertFalse((self.run / "changes/B2.json").exists())
        self.assertEqual(r.apply(self.run, first)["status"], "already_applied")

    def test_explicit_resolution_installs_once_and_clears_gap(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        original_journal = (self.run / "changes/B1.json").read_bytes()
        revision = self.resolution_batch(document)
        self.assertEqual(r.check(self.run, revision)[0]["status"], "passed")
        self.assertEqual(r.apply(self.run, revision)["status"], "applied")
        self.assertTrue(r.status(self.run)["complete"])
        self.assertEqual(r.apply(self.run, revision)["status"], "already_applied")
        self.assertEqual(original_journal, (self.run / "changes/B1.json").read_bytes())

    def test_resolution_cannot_reference_stale_prior_batch(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        r.apply(self.run, self.resolution_batch(document))
        stale = self.resolution_batch(document, prior="B1", batch_id="B3")
        with self.assertRaisesRegex(FormatError, "latest completed batch"):
            r.apply(self.run, stale)

    def test_resolution_cannot_reinstall_a_resolved_finding(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        r.apply(self.run, self.resolution_batch(document))
        repeated = self.resolution_batch(document, prior="B2", batch_id="B3")
        with self.assertRaisesRegex(FormatError, "only change unresolved findings"):
            r.apply(self.run, repeated)

    def test_resolution_cannot_change_undeclared_finding(self):
        document = self.decision(uncertain=True)
        # Replace the as-yet-uninstalled decision explicitly with two findings.
        replacement = copy.deepcopy(document)
        replacement["decision_id"] = "D2"
        replacement["supersedes"] = "D1"
        second = copy.deepcopy(replacement["findings"][0])
        second["finding_id"] = "F2"
        replacement["findings"].append(second)
        for item in replacement["coverage"]:
            item["finding_ids"] = ["F1", "F2"]
        r.record(self.run, replacement)
        batch = self.batch(replacement)
        batch["finding_dispositions"] = {
            "D2/" + key: dict(outcome="unresolved", reason="Open synthetic question")
            for key in ("F1", "F2")
        }
        r.apply(self.run, batch)
        revision = self.batch(replacement)
        revision["batch_id"] = "B2"
        revision["finding_dispositions"] = {
            "D2/" + key: dict(outcome="excluded", reason="Resolved synthetic question")
            for key in ("F1", "F2")
        }
        revision["resolution_revision"] = dict(
            prior_batch_id="B1",
            finding_ids=["D2/F1"],
            reason="Only F1 has been explicitly reconsidered",
        )
        with self.assertRaisesRegex(FormatError, "undeclared finding"):
            r.apply(self.run, revision)

    def test_interrupted_explicit_resolution_remains_recoverable(self):
        document = self.decision(uncertain=True)
        r.apply(self.run, self.batch(document, unresolved=True))
        revision = self.resolution_batch(document, change=True)
        original = r.atomic_text

        def fail_on_report(path, text):
            if Path(path).name == r.FILES[1]:
                raise OSError("Simulated interrupted resolution")
            return original(path, text)

        with patch.object(r, "atomic_text", side_effect=fail_on_report):
            with self.assertRaises(OSError):
                r.apply(self.run, revision)
        self.assertEqual(r.load(self.run / "changes/B2.json")["status"], "installing")
        self.assertEqual(r.apply(self.run, revision)["status"], "applied")
        self.assertTrue(r.status(self.run)["complete"])
        self.assertEqual(self.master.read_text().count("Reviewed."), 1)

    def media_document(self, both_memberships=False):
        path = self.inputs / "chatgpt.json"
        exported = json.loads(path.read_text())
        selected = exported if both_memberships else exported[1:]
        for conversation in selected:
            for node in conversation["mapping"].values():
                message = node.get("message")
                if message and message["id"] == "shared-invented-user":
                    message["content"]["content_type"] = "multimodal_text"
                    message["content"]["parts"].append(
                        dict(
                            content_type="image_asset_pointer",
                            asset_pointer="file-service://invented-unavailable-image",
                        )
                    )
        path.write_text(json.dumps(exported))
        self.dataset = self.root / "media-dataset"
        normalize(self.inputs / "demo.toml", self.dataset)
        member = r.load(self.member)
        member["conversation_ids"] = [c["id"] for c in selected]
        r.atomic_json(self.member, member)
        self.run = self.root / "media-run"
        r.prepare(self.dataset, self.master, self.run, membership=self.member)
        inventory = r.load(self.run / "inventory.json")
        coverage = []
        media_gaps = []
        for packet in inventory["packets"]:
            for piece in packet["pieces"]:
                coverage.append(
                    dict(
                        piece_id=piece["piece_id"],
                        outcome="excluded",
                        reason="Reviewed invented fixture; media pixels not inspected",
                        finding_ids=[],
                    )
                )
                if piece["kind"] == "multimodal_or_unrecognized_content":
                    media_gaps.append(
                        dict(
                            message_record_id=piece["message_record_id"],
                            json_pointer=piece["json_pointer"],
                            status="not_visually_inspected",
                        )
                    )
        return dict(
            decision_id="D1",
            reviewer="Synthetic test",
            reviewed_at="2026-01-01",
            coverage=coverage,
            findings=[],
            media_gaps=media_gaps,
        )

    def test_media_gaps_remain_separate_after_text_completion_and_reapply(self):
        document = self.media_document()
        # Duplicate declarations of the same source occurrence count once.
        document["media_gaps"].append(copy.deepcopy(document["media_gaps"][0]))
        r.record(self.run, document)
        batch = self.batch(document)
        r.apply(self.run, batch)
        self.assertEqual(r.apply(self.run, batch)["status"], "already_applied")
        result = r.status(self.run)
        self.assertTrue(result["complete"])
        self.assertEqual(result["media_gap_count"], 1)
        self.assertEqual(result["conversations_with_media_gaps"], 1)

    def test_media_counts_use_active_decisions_only(self):
        document = self.media_document()
        r.record(self.run, document)
        old_path = self.run / "decisions/D1.json"
        old_bytes = old_path.read_bytes()
        self.assertEqual(r.status(self.run)["media_gap_count"], 1)
        corrected = {
            **document,
            "decision_id": "D2",
            "supersedes": "D1",
            "media_gaps": [],
        }
        r.record(self.run, corrected)
        result = r.status(self.run)
        self.assertEqual(result["media_gap_count"], 0)
        self.assertEqual(result["conversations_with_media_gaps"], 0)
        self.assertEqual(old_path.read_bytes(), old_bytes)

    def test_media_same_original_id_keeps_both_conversation_memberships(self):
        document = self.media_document(both_memberships=True)
        r.record(self.run, document)
        result = r.status(self.run)
        self.assertEqual(result["media_gap_count"], 2)
        self.assertEqual(result["conversations_with_media_gaps"], 2)


if __name__ == "__main__":
    unittest.main()
