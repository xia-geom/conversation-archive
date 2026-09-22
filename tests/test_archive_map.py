"""The authoritative snapshot is indexed without promoting generated links."""
import json
from pathlib import Path
import tempfile
import unittest

from conversation_archive.knowledge_store import MapError, Store, build_archive
from conversation_archive.machine_archive import apply_correction, snapshot
from tests.test_machine_archive import MachineArchiveTests


class ArchiveMapTests(unittest.TestCase):
    def test_exact_text_status_support_and_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            master, migration = MachineArchiveTests().prepare(root)
            original = master.read_bytes()
            first = root / "first"
            snapshot(migration, first, "1")
            manifest = json.loads((first / "manifest.json").read_text())
            mentions = [json.loads(line) for line in (first / "mentions.jsonl").read_text().splitlines()]
            ids = sorted(m["mention_id"] for m in mentions if m["label"] == "Rowan")
            decision = {"version": "1.0", "decision_id": "rowan-answer",
                        "basis_snapshot_id": manifest["snapshot_id"], "actor": "Invented owner",
                        "answer": "These two references are Rowan.", "operations": [{
                            "op": "bind_mentions", "rule_id": "rowan-rule", "depends_on": [],
                            "kind": "person", "entity_id": "entity:person:rowan", "entity_label": "Rowan",
                            "entry_ids": ["E0001", "E0002"], "mention_ids": ids}]}
            decision_file = root / "decision.json"
            decision_file.write_text(json.dumps(decision))
            second = root / "second"
            apply_correction(first, decision_file, second, "2")
            database = root / "map.sqlite3"
            built = build_archive(second, database)
            self.assertEqual(built["edge_count"], len((second / "relationships.jsonl").read_text().splitlines()) + 2)
            self.assertEqual(build_archive(second, database)["status"], "already_current")
            store = Store(database, archive_root=second)
            entry = store.node("entry:E0001")
            self.assertEqual(entry["text"], next(json.loads(line)["raw_markdown"] for line in
                                            (second / "entries.jsonl").read_text().splitlines()
                                            if json.loads(line)["entry_id"] == "E0001"))
            default = store.neighborhood("entity:person:rowan")
            self.assertEqual({n["id"] for n in default["nodes"]},
                             {"entity:person:rowan", "entry:E0001", "entry:E0002"})
            edge = store.edge(default["edges"][0]["id"])
            self.assertEqual(edge["origin"], "display_projection")
            self.assertEqual(edge["supporting_answers"][0]["rule_id"], "rowan-rule")
            self.assertEqual(len(edge["payload"]["derived_from"]),
                             2 * len(edge["payload"]["evidence"]))
            self.assertTrue(all(e["status"] != "derived" for e in default["edges"]))
            derived = store.neighborhood("entry:E0001", statuses=("derived",))
            self.assertTrue(any(e["origin"] == "generated_retrieval" for e in derived["edges"]))
            self.assertEqual(master.read_bytes(), original)

    def test_invalid_or_changed_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, migration = MachineArchiveTests().prepare(root)
            source = root / "snapshot"
            snapshot(migration, source, "1")
            database = root / "map.sqlite3"
            build_archive(source, database)
            store = Store(database, archive_root=source)
            with (source / "entries.jsonl").open("a") as stream:
                stream.write("{}\n")
            with self.assertRaisesRegex(MapError, "Snapshot changed"):
                store.search("Rowan")
            with self.assertRaisesRegex(MapError, "failed validation"):
                build_archive(source, root / "new.sqlite3")


if __name__ == "__main__":
    unittest.main()
