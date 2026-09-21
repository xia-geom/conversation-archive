"""Invented exports only: deduplication never erases source membership/history."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from conversation_archive import raw_store as rs
from conversation_archive.raw_delta import compare
from conversation_archive.raw_json import RawStoreError, analyze, digest, encoded


def node(nid="n1", parent=None, text="I planted mint. 薄荷 🌱", mid="m1"):
    return {"id": nid, "parent": parent, "children": [],
            "message": {"id": mid, "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": [text]}, "metadata": {}}}


def conversation(cid="c1"):
    return {"id": cid, "title": "Invented garden", "current_node": "n1", "mapping": {"n1": node()}}


class RawStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "raw"
        self.input = self.root / "conversations.json"
        self.data = [conversation()]
        self.write()

    def write(self, data=None, **kwargs):
        self.input.write_text(json.dumps(self.data if data is None else data, ensure_ascii=False, **kwargs), encoding="utf-8")

    def ingest(self, source=None, namespace="invented-account"):
        return rs.ingest([source or self.input], self.store, namespace)

    def export(self, result):
        return rs.load_export(self.store, result["export_id"])

    def diff(self, old):
        self.write()
        new = self.ingest()
        return compare(self.store, old["export_id"], new["export_id"])

    def test_exact_restore_after_original_is_unavailable(self):
        original = self.input.read_bytes()
        result = self.ingest()
        self.input.unlink()
        self.assertEqual(rs.verify(self.store, result["export_id"])["status"], "passed")
        output = self.root / "restored.json"
        rs.restore(self.store, result["export_id"], digest(original), output)
        self.assertEqual(output.read_bytes(), original)

    def test_repeat_adds_zero_blobs_or_receipts(self):
        first = self.ingest()
        second = self.ingest()
        self.assertEqual(second["status"], "already_present")
        self.assertEqual(second["new_blobs"], 0)
        self.assertEqual(second["new_blob_bytes"], 0)
        self.assertEqual(second["receipt_id"], first["receipt_id"])
        self.assertEqual(len(list((self.store / "receipts").glob("*.json"))), 1)

    def test_moved_source_same_export_new_location_receipt(self):
        a = self.ingest()
        moved = self.root / "moved.json"
        self.input.rename(moved)
        b = self.ingest(moved)
        self.assertEqual(a["export_id"], b["export_id"])
        self.assertNotEqual(a["receipt_id"], b["receipt_id"])
        self.assertEqual(b["new_blobs"], 0)
        self.assertNotIn(str(self.root), json.dumps(self.export(b)))

    def test_unmodified_message_blob_reused_when_conversation_grows(self):
        a = self.ingest()
        old_blobs = {p["sha256"] for p in self.export(a)["payloads"][0]["parts"]}
        self.data[0]["mapping"]["n2"] = node("n2", "n1", "A later note", "m2")
        self.data[0]["mapping"]["n1"]["children"] = ["n2"]
        self.write()
        b = self.ingest()
        payload = self.export(b)["payloads"][0]
        raw = self.input.read_bytes()
        span = next(n for n in payload["conversations"][0]["nodes"] if n["node_id"] == "n1")["message_byte_span"]
        self.assertIn(digest(raw[span[0]:span[1]]), old_blobs)
        self.assertGreater(b["reused_blobs"], 0)

    def test_same_message_bytes_different_conversation_memberships(self):
        self.data.append(conversation("c2"))
        self.write()
        report = self.ingest()
        self.assertEqual(report["message_occurrences"], 2)
        self.assertEqual(len(self.export(report)["payloads"][0]["conversations"]), 2)
        self.assertEqual(compare(self.store, report["export_id"], report["export_id"])["counts"]["unchanged_messages"], 2)

    def test_key_order_whitespace_and_conversation_order_not_new_messages(self):
        self.data.append(conversation("c2")); self.write()
        a = self.ingest()
        self.data.reverse()
        self.write(sort_keys=True, indent=4)
        b = self.ingest()
        self.assertNotEqual(a["export_id"], b["export_id"])
        d = compare(self.store, a["export_id"], b["export_id"])
        self.assertEqual(d["counts"]["unchanged_messages"], 2)
        self.assertEqual(d["changes"], [])

    def test_unicode_bom_crlf_and_numeric_spelling_preserved(self):
        text = json.dumps(self.data, ensure_ascii=False, indent=2).replace("\n", "\r\n")
        self.input.write_bytes(b"\xef\xbb\xbf" + text.encode() + b"\r\n  ")
        self.test_exact_restore_after_original_is_unavailable()

    def test_lone_surrogate_escape_preserved(self):
        self.input.write_bytes(json.dumps([conversation()], ensure_ascii=True).replace("Invented garden", r"\ud800").encode())
        self.test_exact_restore_after_original_is_unavailable()

    def test_json_pointer_escaping(self):
        n = self.data[0]["mapping"].pop("n1"); n["id"] = "a~/b"
        self.data[0]["mapping"][n["id"]] = n; self.write()
        pointer = self.export(self.ingest())["payloads"][0]["conversations"][0]["nodes"][0]["message_pointer"]
        self.assertEqual(pointer, "/0/mapping/a~0~1b/message")

    def test_changed_message_and_unchanged_reply_context(self):
        self.data[0]["mapping"]["n2"] = node("n2", "n1", "Reply", "m2"); self.write()
        a = self.ingest()
        self.data[0]["mapping"]["n1"]["message"]["content"]["parts"] = ["Corrected meaning"]
        d = self.diff(a)
        self.assertEqual(d["counts"]["changed_messages"], 1)
        self.assertEqual(d["counts"]["context_changed_messages"], 1)
        self.assertFalse(d["review_coverage_claimed"])

    def test_new_branch_does_not_replace_previous_evidence(self):
        a = self.ingest()
        self.data[0]["mapping"]["branch"] = node("branch", "n1", "Alternative", "m2")
        d = self.diff(a)
        self.assertEqual(d["counts"]["new_messages"], 1)
        self.assertEqual(len(self.export(a)["payloads"][0]["conversations"][0]["nodes"]), 1)

    def test_current_branch_selection_change_is_visible(self):
        a = self.ingest(); self.data[0]["current_node"] = None
        d = self.diff(a)
        self.assertEqual(d["counts"]["conversation_metadata_changed"], 1)
        self.assertEqual(d["counts"]["unchanged_messages"], 1)

    def test_reparenting_reports_context_change(self):
        self.data[0]["mapping"]["n2"] = node("n2", "n1", "Reply", "m2"); self.write()
        a = self.ingest(); self.data[0]["mapping"]["n2"]["parent"] = None
        self.assertEqual(self.diff(a)["counts"]["context_changed_messages"], 1)

    def test_missing_conversation_is_not_deletion(self):
        a = self.ingest(); self.data = []
        d = self.diff(a)
        self.assertEqual(d["counts"]["not_present_conversations"], 1)
        self.assertEqual(d["deletions_applied"], 0)
        self.assertEqual(rs.verify(self.store, a["export_id"])["status"], "passed")

    def test_missing_node_is_not_deletion(self):
        a = self.ingest(); self.data[0]["mapping"] = {}
        d = self.diff(a)
        self.assertEqual(d["counts"]["not_present_messages"], 1)
        self.assertEqual(d["deletions_applied"], 0)

    def test_duplicate_conversation_ids_are_ambiguous_not_deduplicated(self):
        a = self.ingest(); self.data.append(copy.deepcopy(self.data[0]))
        d = self.diff(a)
        self.assertEqual(d["counts"]["ambiguous_conversations"], 1)
        self.assertEqual(d["counts"]["unchanged_messages"], 0)
        self.assertTrue(d["ambiguities"])

    def test_missing_or_conflicting_ids_preserved_as_ambiguity(self):
        for change in ({"id": None}, {"conversation_id": "different"}):
            with self.subTest(change=change):
                self.data = [conversation()]; self.data[0].update(change); self.write()
                a = self.ingest(); d = compare(self.store, a["export_id"], a["export_id"])
                self.assertTrue(d["ambiguities"])
                self.assertEqual(a["message_occurrences"], 1)

    def test_unknown_message_id_and_missing_parent_not_auto_matched(self):
        self.data[0]["mapping"]["n1"]["message"]["id"] = None
        self.data[0]["mapping"]["n1"]["parent"] = "missing"; self.write()
        a = self.ingest(); d = compare(self.store, a["export_id"], a["export_id"])
        self.assertIn("missing_message_id", d["ambiguities"][0]["issues"])
        self.assertIn("unavailable_parent_context", d["ambiguities"][0]["issues"])

    def test_account_namespace_cannot_change(self):
        self.ingest()
        with self.assertRaises(RawStoreError): self.ingest(namespace="another-account")

    def test_null_graph_node_message_retained(self):
        self.data[0]["mapping"]["root"] = {"id": "root", "parent": None, "children": ["n1"], "message": None}
        self.write(); a = self.ingest()
        self.assertEqual(len(self.export(a)["payloads"][0]["conversations"][0]["nodes"]), 2)
        self.assertEqual(a["message_occurrences"], 1)

    def test_unknown_attachment_content_preserved_without_network(self):
        self.data[0]["mapping"]["n1"]["message"]["content"]["parts"].append({"content_type": "image_asset_pointer", "asset_pointer": "invented-unavailable"})
        self.write(); self.test_exact_restore_after_original_is_unavailable()

    def test_zip_repackaging_shares_export_but_not_container_receipt(self):
        one, two = self.root / "a.zip", self.root / "b.zip"
        for path, compression in ((one, zipfile.ZIP_STORED), (two, zipfile.ZIP_DEFLATED)):
            with zipfile.ZipFile(path, "w", compression=compression) as z:
                z.writestr("export/conversations.json", self.input.read_bytes())
                z.writestr("image.png", b"invented-media")
        a,b = self.ingest(one), self.ingest(two)
        self.assertEqual(a["export_id"], b["export_id"])
        self.assertNotEqual(a["receipt_id"], b["receipt_id"])
        receipt = json.loads((self.store / "receipts" / (b["receipt_id"] + ".json")).read_text())
        self.assertFalse(receipt["media_archived"])
        self.assertEqual(receipt["locations"][0]["unarchived_member_count"], 1)
        self.assertEqual(b["new_blobs"], 0)

    def test_duplicate_zip_names_rejected(self):
        path = self.root / "bad.zip"
        with zipfile.ZipFile(path, "w") as z, warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for _ in range(2): z.writestr("conversations.json", self.input.read_bytes())
        with self.assertRaises(RawStoreError): self.ingest(path)

    def test_zip_traversal_name_rejected_no_extraction(self):
        path = self.root / "bad.zip"
        with zipfile.ZipFile(path, "w") as z: z.writestr("../conversations.json", self.input.read_bytes())
        with self.assertRaises(RawStoreError): self.ingest(path)

    def test_zip_declared_size_limit(self):
        path = self.root / "large.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z: z.writestr("conversations.json", self.input.read_bytes())
        with patch.object(rs, "MAX_PAYLOAD", 10), self.assertRaises(RawStoreError): self.ingest(path)

    def test_directory_and_split_payloads(self):
        (self.root / "conversations-001.json").write_text(json.dumps([conversation("other")]))
        (self.root / "irrelevant.txt").write_text("not imported")
        a = self.ingest(self.root)
        self.assertEqual(a["payloads"], 2)
        self.assertEqual(a["conversation_occurrences"], 2)

    def test_duplicate_payload_locations_preserved(self):
        alias = self.root / "alias.json"; alias.write_bytes(self.input.read_bytes())
        a = rs.ingest([self.input, alias], self.store, "invented-account")
        self.assertEqual(a["payloads"], 1)
        receipt = rs._json(self.store / "receipts" / (a["receipt_id"] + ".json"))
        self.assertEqual(len(receipt["locations"]), 2)

    def test_invalid_and_duplicate_key_json_no_export_committed(self):
        for data in (b'{"x":1,"x":2}', b'[{"id":"a","id":"b","mapping":{}}]', b'[NaN]', b'[1e500]', b'bad', b'{}'):
            self.input.write_bytes(data)
            with self.assertRaises(RawStoreError): self.ingest()
        self.assertFalse((self.store / "exports").exists())

    def test_corrupt_existing_blob_not_overwritten(self):
        a = self.ingest(); part = self.export(a)["payloads"][0]["parts"][0]
        target = rs._blob_path(self.store, part["sha256"]); target.write_bytes(b"corrupt")
        with self.assertRaises(RawStoreError): self.ingest()
        with self.assertRaises(RawStoreError): rs.verify(self.store, a["export_id"])
        self.assertEqual(target.read_bytes(), b"corrupt")

    def test_manifest_tampering_rejected(self):
        a = self.ingest(); path = self.store / "exports" / (a["export_id"] + ".json")
        body = json.loads(path.read_text()); body["namespace"] = "different"; path.write_text(json.dumps(body))
        with self.assertRaises(RawStoreError): self.export(a)

    def test_occurrence_index_revalidated_from_raw_bytes(self):
        a = self.ingest(); body = self.export(a)
        body["payloads"][0]["conversations"][0]["nodes"][0]["message_sha256"] = "0" * 64
        body.pop("export_id"); body["export_id"] = "EX-" + rs.fingerprint(body)
        rs._publish(rs._export_path(self.store, body["export_id"]), encoded(body) + b"\n")
        with self.assertRaises(RawStoreError): rs.load_export(self.store, body["export_id"])

    def test_source_change_during_read_rejected(self):
        real = rs.sha_file; calls = 0
        def changing(path):
            nonlocal calls
            calls += 1
            return real(path) if calls == 1 else "0" * 64
        with patch.object(rs, "sha_file", changing), self.assertRaises(RawStoreError): self.ingest()
        self.assertFalse((self.store / "exports").exists())

    def test_interrupted_receipt_recovers_without_duplicate_blob(self):
        real = rs._publish
        def interrupted(path, data):
            if path.parent.name == "receipts": raise KeyboardInterrupt()
            return real(path, data)
        with patch.object(rs, "_publish", interrupted), self.assertRaises(KeyboardInterrupt): self.ingest()
        resumed = self.ingest()
        self.assertEqual(resumed["status"], "already_present")
        self.assertEqual(resumed["new_blobs"], 0)
        self.assertEqual(len(list((self.store / "receipts").glob("*.json"))), 1)

    def test_interrupted_blob_write_can_be_retried(self):
        real = rs._publish; calls = 0
        def interrupted(path, data):
            nonlocal calls
            calls += 1
            if calls == 4: raise KeyboardInterrupt()
            return real(path, data)
        with patch.object(rs, "_publish", interrupted), self.assertRaises(KeyboardInterrupt): self.ingest()
        a = self.ingest()
        self.assertEqual(a["status"], "imported")
        self.assertGreater(a["reused_blobs"], 0)
        self.assertEqual(rs.verify(self.store, a["export_id"])["status"], "passed")

    def test_second_writer_refused(self):
        with rs._writer(self.store, "invented-account"):
            with self.assertRaises(RawStoreError): self.ingest()

    def test_unrelated_directory_preserved(self):
        self.store.mkdir(); (self.store / "keep.txt").write_text("keep")
        with self.assertRaises(RawStoreError): self.ingest()
        self.assertEqual((self.store / "keep.txt").read_text(), "keep")

    def test_symlink_store_and_input_refused(self):
        target = self.root / "target"; target.mkdir(); self.store.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RawStoreError): self.ingest()
        self.store.unlink()
        alias = self.root / "alias.json"; alias.symlink_to(self.input)
        with self.assertRaises(RawStoreError): self.ingest(alias)

    def test_symlink_blob_directory_refused(self):
        self.ingest(); target = self.root / "outside"; target.mkdir()
        prefix = next((self.store / "blobs" / "sha256").iterdir())
        prefix.rename(prefix.with_name(prefix.name + "-old")); prefix.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RawStoreError): self.ingest()

    def test_restore_does_not_overwrite_source_or_write_inside_store(self):
        a = self.ingest(); sha = digest(self.input.read_bytes())
        for path in (self.input, self.store / "restored.json"):
            with self.assertRaises(RawStoreError): rs.restore(self.store, a["export_id"], sha, path)

    def test_path_escape_and_namespace_input(self):
        a = self.ingest()
        with self.assertRaises(RawStoreError): rs.load_export(self.store, "../../private")
        with self.assertRaises(RawStoreError): self.ingest(namespace="../private")

    def test_permissions_and_original_unchanged(self):
        original = self.input.read_bytes(); a = self.ingest()
        self.assertEqual(self.input.read_bytes(), original)
        for path in self.store.rglob("*"):
            if path.is_file(): self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_cycle_retained_but_not_automatically_matched(self):
        self.data[0]["mapping"]["n1"]["parent"] = "n1"; self.write()
        a = self.ingest(); d = compare(self.store, a["export_id"], a["export_id"])
        self.assertIn("cyclic_parent_context", d["ambiguities"][0]["issues"])
        self.assertEqual(d["counts"]["unchanged_messages"], 0)

    def test_numeric_lexical_forms_reconstruct_exactly(self):
        raw = b'[{"id":"c","mapping":{},"zero":-0,"n":1.2300e+02}]'
        self.input.write_bytes(raw)
        self.test_exact_restore_after_original_is_unavailable()

    def test_different_message_id_at_same_node_is_changed(self):
        a = self.ingest(); self.data[0]["mapping"]["n1"]["message"]["id"] = "replaced"
        self.assertEqual(self.diff(a)["counts"]["changed_messages"], 1)

    def test_total_bound_applies_across_payloads(self):
        other = self.root / "second.json"; other.write_bytes(self.input.read_bytes())
        with patch.object(rs, "MAX_TOTAL", len(self.input.read_bytes()) + 1), self.assertRaises(RawStoreError):
            rs.ingest([self.input, other], self.store, "invented-account")

    def test_cli_ingest_verify_and_diff(self):
        command = [sys.executable, "-m", "conversation_archive.raw_store"]
        first = subprocess.run(command + ["ingest", "--source", str(self.input), "--store", str(self.store), "--namespace", "example"], capture_output=True, text=True, check=True)
        eid = json.loads(first.stdout)["export_id"]
        for rest in (["verify", "--export", eid], ["diff", "--before", eid, "--after", eid]):
            result = subprocess.run(command + [*rest, "--store", str(self.store)], capture_output=True, text=True, check=True)
            self.assertNotIn("error", json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
