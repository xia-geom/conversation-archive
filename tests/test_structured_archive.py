import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from conversation_archive import organization as o
from conversation_archive.organization_inputs import index_markdown
from conversation_archive.structured_archive import ArchiveError, migrate, query, render, validate


MASTER = """# Master

## E0001 — First memory

**Event period:** Childhood
**Record kind:** memory
**People / roles:** Rowan, mother
**Topic labels:** shame, school
**Source references:** [SRC-001-S001](#src-001-s001)

I remember Rowan at school.

## E0002 — Later reflection

**Event period:** Adulthood
**Record kind:** reflection
**People / roles:** Rowan
**Topic labels:** shame, repair
**Source references:** [SRC-002-S001](#src-002-s001)

I thought again about Rowan.
"""


class StructuredArchiveTests(unittest.TestCase):
    def fixture(self, root):
        master = root / "master.md"
        master.write_text(MASTER, encoding="utf-8")
        data = index_markdown(MASTER, [{"kind": "person", "label": "Rowan", "family": "rowan"}])
        run = root / "organization"
        o.prepare(data, run)
        state = o.read_state(run)
        mids = [m["mention_id"] for m in o.mentions(data)]
        event = {
            "event_id": "owner-answer-1",
            "expected_state_sha256": o.digest(state),
            "actor": "Owner",
            "answer": "Both references are Rowan.",
            "operations": [{
                "op": "bind", "rule_id": "rowan-confirmed", "depends_on": [],
                "kind": "person", "aliases": ["Rowan"], "entry_ids": ["E0001", "E0002"],
                "mention_ids": mids, "entity_id": "rowan", "entity_label": "Rowan",
            }],
        }
        o.apply(run, event)
        questions = root / "questions.json"
        questions.write_text(json.dumps([{
            "question_id": "Q-one", "kind": "event", "hypothesis_family": "school-memory",
            "prompt": "Same event?", "evidence": [],
        }]), encoding="utf-8")
        return master, run / "state.json", questions

    def test_migration_preserves_exact_entries_and_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); master, state, questions = self.fixture(root)
            before = hashlib.sha256(master.read_bytes()).hexdigest()
            dbpath = root / "archive.sqlite3"
            result = migrate(master, state, dbpath, questions)
            self.assertEqual("passed", result["status"])
            self.assertEqual(2, result["counts"]["entries"])
            self.assertEqual(before, hashlib.sha256(master.read_bytes()).hexdigest())
            db = sqlite3.connect(dbpath)
            try:
                slices = [x[0] for x in db.execute("SELECT raw_markdown FROM entries ORDER BY entry_id")]
                indexed = index_markdown(MASTER)["entries"]
                self.assertEqual([e["text"] for e in indexed], slices)
                self.assertEqual({"explicit_master_metadata"}, {x[0] for x in db.execute("SELECT DISTINCT authority FROM entry_metadata")})
                self.assertEqual(4, db.execute("SELECT count(*) FROM relationships WHERE authority='owner_confirmed' AND relation='refers_to'").fetchone()[0])
                self.assertEqual(1, db.execute("SELECT count(*) FROM correction_rules WHERE active=1").fetchone()[0])
                self.assertEqual(1, db.execute("SELECT count(*) FROM unresolved_questions").fetchone()[0])
            finally:
                db.close()

    def test_render_is_derived_and_repeat_migration_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); master, state, questions = self.fixture(root)
            dbpath = root / "archive.sqlite3"; migrate(master, state, dbpath, questions)
            before = master.read_bytes()
            summary = render(dbpath, root / "views")
            self.assertFalse(summary["generated_text_is_evidence"])
            self.assertIn("Generated from SQLite", (root / "views/navigation.md").read_text())
            self.assertEqual(before, master.read_bytes())
            with self.assertRaises(ArchiveError): migrate(master, state, dbpath, questions)

    def test_validation_detects_master_drift_and_query_works(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); master, state, questions = self.fixture(root)
            dbpath = root / "archive.sqlite3"; migrate(master, state, dbpath, questions)
            self.assertEqual("E0001", query(dbpath, "E0001", None)[0]["entry_id"])
            self.assertEqual(2, len(query(dbpath, None, "Rowan")))
            master.write_text(MASTER + "\nchanged\n", encoding="utf-8")
            checked = validate(dbpath, master)
            self.assertEqual("failed", checked["status"])
            self.assertIn("master hash mismatch", checked["errors"])


if __name__ == "__main__":
    unittest.main()
