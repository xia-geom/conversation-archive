import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from conversation_archive import organization as o
from conversation_archive.machine_archive import apply_correction, build_sqlite, snapshot, validate
from conversation_archive.organization_inputs import index_markdown
from conversation_archive.structured_archive import migrate, render
from conversation_archive.structured_archive import ArchiveError


MASTER = """# Master

## E0001 — First Rowan account

**Event period:** Childhood
**Record kind:** memory
**People / roles:** Rowan
**Topic labels:** school
**Source references:** [SRC-001-S001](#src-001-s001)

Rowan was there.

## E0002 — Second Rowan account

**Event period:** Adulthood
**Record kind:** reflection
**People / roles:** Rowan
**Topic labels:** repair
**Source references:** [SRC-002-S001](#src-002-s001)

I remembered Rowan.
"""


class MachineArchiveTests(unittest.TestCase):
    def prepare(self, root):
        master = root / "master.md"; master.write_text(MASTER, encoding="utf-8")
        data = index_markdown(MASTER, [{"kind":"person","label":"Rowan","family":"rowan"}])
        run = root / "run"; o.prepare(data, run)
        database = root / "migration.sqlite3"
        migrate(master, run / "state.json", database)
        # A retrieval edge is useful, but importing it must never accept it.
        db = sqlite3.connect(database)
        db.execute("INSERT INTO relationships VALUES (?,?,?,?,?,?,?,?,?)", (
            "derived-one", "E0001", "E0002", "related_by_shared_facets",
            "generated_retrieval", "derived", "{}", "[]", "synthetic_test",
        )); db.commit(); db.close()
        return master, database

    def test_snapshot_rebuild_and_correction_without_master_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); master,database=self.prepare(root); before=master.read_bytes()
            archive1=root/"archive-v1"; first=snapshot(database,archive1,"1")
            self.assertEqual("passed",first["status"])
            rebuilt1=root/"rebuilt-v1.sqlite3"; build_sqlite(archive1,rebuilt1)
            manifest=json.loads((archive1/"manifest.json").read_text())
            mentions=[json.loads(x) for x in (archive1/"mentions.jsonl").read_text().splitlines()]
            mids=sorted(m["mention_id"] for m in mentions if m["label"]=="Rowan")
            decision={
                "version":"1.0", "decision_id":"owner-rowan", "basis_snapshot_id":manifest["snapshot_id"],
                "actor":"Owner", "answer":"Both displayed references are Rowan.",
                "operations":[{"op":"bind_mentions","rule_id":"rowan-rule","depends_on":[],
                    "kind":"person","entity_id":"entity:person:rowan","entity_label":"Rowan",
                    "entry_ids":["E0001","E0002"],"mention_ids":mids}],
            }
            decision_path=root/"decision.json"; decision_path.write_text(json.dumps(decision))
            archive2=root/"archive-v2"; second=apply_correction(archive1,decision_path,archive2,"2")
            self.assertEqual("passed",second["status"])
            self.assertEqual(manifest["snapshot_id"],json.loads((archive2/"manifest.json").read_text())["parent_snapshot_id"])
            rebuilt2=root/"rebuilt-v2.sqlite3"; build_sqlite(archive2,rebuilt2)
            views=root/"views"; summary=render(rebuilt2,views)
            db=sqlite3.connect(rebuilt2)
            try:
                self.assertEqual(len(mids),db.execute("SELECT count(*) FROM mentions WHERE entity_id='entity:person:rowan'").fetchone()[0])
                self.assertEqual(len(mids),db.execute("SELECT count(*) FROM relationships WHERE authority='owner_confirmed' AND status='user_confirmed'").fetchone()[0])
                self.assertEqual(("rowan-rule",1),db.execute("SELECT rule_id,active FROM correction_rules WHERE rule_id='rowan-rule'").fetchone())
                self.assertEqual(("generated_retrieval","derived"),db.execute("SELECT authority,status FROM relationships WHERE relationship_id='derived-one'").fetchone())
            finally: db.close()
            self.assertTrue(summary["generated_text_is_evidence"] is False)
            self.assertIn("Rowan",(views/"relationships.md").read_text())
            self.assertEqual(before,master.read_bytes())

    def test_snapshot_hash_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); _,database=self.prepare(root); archive=root/"archive"
            snapshot(database,archive,"1")
            with (archive/"entries.jsonl").open("a",encoding="utf-8") as f: f.write("{}\n")
            report=validate(archive)
            self.assertEqual("failed",report["status"])
            self.assertTrue(any("hash mismatch" in x for x in report["errors"]))

    def test_question_scope_and_completion_are_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, database = self.prepare(root)
            db = sqlite3.connect(database)
            mentions = [dict(zip([c[1] for c in db.execute("PRAGMA table_info(mentions)")], row))
                        for row in db.execute("SELECT * FROM mentions WHERE label='Rowan'")]
            evidence = [{"mention_id": m["mention_id"], "entry_id": m["entry_id"]} for m in mentions]
            db.execute("INSERT INTO unresolved_questions VALUES (?,?,?,?,?,?)",
                       ("Q-rowan", "person", "rowan", "Are these references the same person?",
                        json.dumps(evidence), "unresolved_candidate"))
            db.commit(); db.close()
            first = root / "first"
            snapshot(database, first, "1")
            manifest = json.loads((first / "manifest.json").read_text())
            decision = {"version": "1.0", "decision_id": "owner-rowan-question",
                        "basis_snapshot_id": manifest["snapshot_id"], "actor": "Invented owner",
                        "answer": "All shown references are Rowan.", "operations": [{
                            "op": "bind_mentions", "rule_id": "rowan-question-rule", "depends_on": [],
                            "kind": "person", "entity_id": "entity:person:rowan", "entity_label": "Rowan",
                            "entry_ids": sorted({m["entry_id"] for m in mentions}),
                            "mention_ids": [m["mention_id"] for m in mentions],
                            "question_id": "Q-rowan"}]}
            decision_file = root / "decision.json"
            decision_file.write_text(json.dumps(decision))
            second = root / "second"
            self.assertEqual(apply_correction(first, decision_file, second, "2")["counts"]["unresolved_questions"], 0)
            rules = [json.loads(line) for line in (second / "correction_rules.jsonl").read_text().splitlines()]
            self.assertEqual(json.loads(rules[-1]["payload_json"])["question_id"], "Q-rowan")
            decision["operations"][0]["mention_ids"].append("outside-question")
            decision_file.write_text(json.dumps(decision))
            with self.assertRaises(ArchiveError):
                apply_correction(first, decision_file, root / "invalid", "2")

    def test_relation_decision_is_separate_from_generated_link_and_rejects_cycles(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            master, database = self.prepare(root)
            before = master.read_bytes()
            first = root / "first"
            snapshot(database, first, "1")
            entries = {row["entry_id"]: row for row in
                       (json.loads(line) for line in (first / "entries.jsonl").read_text().splitlines())}
            def evidence(entry_id, quote):
                start = entries[entry_id]["raw_markdown"].index(quote)
                return {"entry_id": entry_id, "start": start, "end": start + len(quote), "quote": quote}
            witnesses = [evidence("E0001", "Rowan was there."),
                         evidence("E0002", "I remembered Rowan.")]
            manifest = json.loads((first / "manifest.json").read_text())
            def decision(basis, decision_id, source, target, relation, result, spans):
                return {"version": "1.0", "decision_id": decision_id,
                        "basis_snapshot_id": basis, "actor": "Invented owner",
                        "answer": "Synthetic relationship answer.", "operations": [{
                            "op": "assert_relation", "rule_id": decision_id + "-rule", "depends_on": [],
                            "source_entry_id": source, "target_entry_id": target,
                            "relation": relation, "decision": result, "evidence": spans}]}
            decision_file = root / "decision.json"
            bad = decision(manifest["snapshot_id"], "bad-quotation", "E0001", "E0002",
                           "continues", "confirm", [dict(witnesses[0], quote="invented"), witnesses[1]])
            decision_file.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ArchiveError, "exact entry quotation"):
                apply_correction(first, decision_file, root / "bad", "2")
            decision_file.write_text(json.dumps(decision(manifest["snapshot_id"], "first-relation",
                "E0001", "E0002", "precedes", "confirm", witnesses)))
            second = root / "second"
            self.assertEqual(apply_correction(first, decision_file, second, "2")["status"], "passed")
            relations = [json.loads(line) for line in (second / "relationships.jsonl").read_text().splitlines()]
            self.assertEqual(next(r for r in relations if r["relationship_id"] == "derived-one")["status"], "derived")
            assertion = next(r for r in relations if r["origin"] == "machine_archive_relation_answer")
            self.assertEqual((assertion["authority"], assertion["status"]), ("owner_confirmed", "user_confirmed"))
            self.assertEqual(json.loads(assertion["evidence_json"]), witnesses)
            second_id = json.loads((second / "manifest.json").read_text())["snapshot_id"]
            decision_file.write_text(json.dumps(decision(second_id, "duplicate-relation",
                "E0001", "E0002", "precedes", "confirm", witnesses)))
            with self.assertRaisesRegex(ArchiveError, "already has an owner decision"):
                apply_correction(second, decision_file, root / "duplicate", "3")
            decision_file.write_text(json.dumps(decision(second_id, "reverse-relation",
                "E0002", "E0001", "precedes", "confirm", witnesses)))
            with self.assertRaisesRegex(ArchiveError, "cycle"):
                apply_correction(second, decision_file, root / "cycle", "3")
            decision_file.write_text(json.dumps(decision(second_id, "rejected-relation",
                "E0002", "E0001", "continues", "reject", witnesses)))
            third = root / "third"
            self.assertEqual(apply_correction(second, decision_file, third, "3")["status"], "passed")
            self.assertTrue(any(r["status"] == "rejected" for r in
                (json.loads(line) for line in (third / "relationships.jsonl").read_text().splitlines())))
            self.assertEqual(master.read_bytes(), before)


if __name__ == "__main__": unittest.main()
