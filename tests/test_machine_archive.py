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


if __name__ == "__main__": unittest.main()
