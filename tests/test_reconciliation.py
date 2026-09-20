"""Synthetic checks for explicit review, frozen evidence, and recovery."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from conversation_archive.pipeline import normalize
from conversation_archive import reconciliation as r
from conversation_archive.model import FormatError

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


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = self.root / "inputs"
        shutil.copytree(Path(__file__).parent / "fixtures", self.inputs)
        path = self.inputs / "chatgpt.json"
        data = json.loads(path.read_text())
        for c in data:
            c["conversation_template_id"] = "invented-project"
        path.write_text(json.dumps(data))
        self.dataset = self.root / "dataset"
        normalize(self.inputs / "demo.toml", self.dataset)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.master = self.archive / r.FILES[0]
        self.master.write_text(MASTER)
        for n in r.FILES[1:]:
            (self.archive / n).write_text("# Invented report\n")
        self.run = self.root / "run"
        r.prepare(
            self.dataset,
            self.master,
            self.run,
            project_id="invented-project",
            max_chars=25,
        )

    def decide(self):
        p = r.packet(self.run)
        doc = dict(
            decision_id="D" + p["packet_id"],
            reviewer="invented reviewer",
            reviewed_at="2026-01-01",
            coverage=[
                dict(
                    piece_id=x["piece_id"],
                    outcome="excluded",
                    reason="Invented exercise reviewed; no proposed change.",
                )
                for x in p["pieces"]
            ],
            findings=[],
        )
        r.record(self.run, doc)
        return doc

    def batch(self, doc):
        files = {}
        for n in r.FILES:
            old = (self.archive / n).read_text()
            files[n] = dict(
                before_sha256=r.digest(old), after_sha256=r.digest(old), patches=[]
            )
        return dict(
            batch_id="B1",
            decision_ids=[doc["decision_id"]],
            finding_dispositions={},
            files=files,
        )

    def test_generated_is_not_reviewed(self):
        self.assertIn("pieces", r.packet(self.run))
        self.assertEqual(r.status(self.run)["covered_pieces"], 0)
        self.assertFalse(r.status(self.run)["complete"])

    def test_parent_order_and_exact_continuations(self):
        inv = r.load(self.run / "inventory.json")
        parts = {}
        for p in inv["packets"]:
            body = r.packet(self.run, p["packet_id"])
            self.assertLessEqual(sum(len(x["text"]) for x in body["pieces"]), 25)
            for piece in body["pieces"]:
                parts.setdefault(
                    (piece["message_record_id"], piece["segment_index"]), []
                ).append(piece)
        for (mid, index), pieces in parts.items():
            if index < 0:
                continue
            m = r.original_record(
                self.dataset, "messages", inv["messages"][mid]["offset"]
            )
            self.assertEqual(
                "".join(x["text"] for x in sorted(pieces, key=lambda x: x["start"])),
                m["text_segments"][index]["text"],
            )
        c = r.original_record(
            self.dataset, "conversations", inv["conversations"][0]["offset"]
        )
        seen = set()
        for n in r.graph_order(c):
            if n["parent_id"] is not None:
                self.assertIn(n["parent_id"], seen)
            seen.add(n["node_id"])

    def test_reused_ids_preserve_memberships(self):
        inv = r.load(self.run / "inventory.json")
        self.assertEqual(
            sum(
                m["original_id"] == "shared-invented-user"
                for m in inv["messages"].values()
            ),
            2,
        )

    def test_record_idempotence_and_overlap(self):
        doc = self.decide()
        n = r.status(self.run)["covered_pieces"]
        self.assertEqual(r.record(self.run, doc)["status"], "already_recorded")
        self.assertEqual(r.status(self.run)["covered_pieces"], n)
        doc["decision_id"] = "another"
        with self.assertRaises(FormatError):
            r.record(self.run, doc)

    def test_source_mutation(self):
        with (self.inputs / "chatgpt.json").open("a") as f:
            f.write(" ")
        with self.assertRaises(FormatError):
            r.packet(self.run)

    def test_dataset_mutation(self):
        with (self.dataset / "messages.jsonl").open("a") as f:
            f.write("\n")
        with self.assertRaises(FormatError):
            r.packet(self.run)

    def test_invented_quote_rejected(self):
        p = r.packet(self.run)
        piece = next(x for x in p["pieces"] if x["segment_index"] >= 0)
        doc = dict(
            decision_id="D-quote",
            reviewer="test",
            reviewed_at="2026-01-01",
            coverage=[
                dict(
                    piece_id=x["piece_id"],
                    outcome="complementary_detail",
                    reason="test",
                    finding_ids=["F1"],
                )
                for x in p["pieces"]
            ],
            findings=[
                dict(
                    finding_id="F1",
                    outcome="complementary_detail",
                    reason="test",
                    attribution="owner",
                    quotes=[
                        dict(
                            message_record_id=piece["message_record_id"],
                            segment_index=piece["segment_index"],
                            start=0,
                            end=1,
                            text="X",
                        )
                    ],
                )
            ],
        )
        with self.assertRaises(FormatError):
            r.record(self.run, doc)

    def test_apply_repeat_and_no_false_completion(self):
        batch = self.batch(self.decide())
        self.assertEqual(r.apply(self.run, batch)["status"], "applied")
        self.assertEqual(r.apply(self.run, batch)["status"], "already_applied")
        self.assertFalse(r.status(self.run)["complete"])

    def test_stale_master(self):
        batch = self.batch(self.decide())
        self.master.write_text(MASTER + "Unexpected edit\n")
        with self.assertRaises(FormatError):
            r.apply(self.run, batch)

    def test_interrupted_apply_recovers(self):
        batch = self.batch(self.decide())
        extra = "\n## R0001 — Invented check\n\n| Before | After |\n| --- | --- |\n| Before. | After. |\n"
        for n in r.FILES:
            old = (self.archive / n).read_text()
            new = old + ("\nReviewed.\n" if n == r.FILES[0] else extra)
            batch["files"][n] = dict(
                before_sha256=r.digest(old),
                after_sha256=r.digest(new),
                patches=[dict(before=old, after=new)],
            )
        original = r.atomic_text

        def crash(path, text):
            if Path(path).name == r.FILES[1]:
                raise OSError("Simulated interruption")
            return original(path, text)

        with (
            patch.object(r, "atomic_text", side_effect=crash),
            self.assertRaises(OSError),
        ):
            r.apply(self.run, batch)
        self.assertEqual(r.load(self.run / "changes/B1.json")["status"], "installing")
        self.assertEqual(r.apply(self.run, batch)["status"], "applied")
        self.assertEqual(self.master.read_text().count("Reviewed."), 1)

    def test_empty_conversation_is_not_automatically_complete(self):
        member = self.root / "membership.json"
        member.write_text(
            json.dumps(
                dict(
                    conversation_ids=["invented-claude-empty"],
                    observed_at="2026-01-01",
                    evidence="invented fixture membership",
                    project_name="Invented",
                )
            )
        )
        run = self.root / "claude-run"
        r.prepare(self.dataset, self.master, run, provider="claude", membership=member)
        self.assertFalse(r.status(run)["complete"])
        self.assertEqual(r.packet(run)["pieces"][0]["kind"], "empty_conversation")

    def test_every_message_has_pieces(self):
        inv = r.load(self.run / "inventory.json")
        self.assertEqual(len(inv["messages"]), 5)
        self.assertTrue(
            all(
                any(
                    x["message_record_id"] == mid
                    for p in inv["packets"]
                    for x in p["pieces"]
                )
                for mid in inv["messages"]
            )
        )


if __name__ == "__main__":
    unittest.main()
