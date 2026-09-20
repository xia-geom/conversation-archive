"""Synthetic evidence tests: preservation, coverage, failures, and reproducibility."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from conversation_archive.inventory import inventory, sha_file, strict_loads
from conversation_archive.model import FormatError
from conversation_archive.pipeline import (
    normalize,
    validate,
    inspect_record,
    write_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        shutil.copytree(FIXTURES, self.inputs)
        self.config = self.inputs / "demo.toml"
        self.out = self.root / "clean"

    def edit_source(self, provider, edit):
        path = self.inputs / (provider + ".json")
        obj = json.loads(path.read_text())
        edit(obj)
        write_json(path, obj)

    def rows(self, kind):
        return [
            json.loads(line)
            for line in (self.out / (kind + ".jsonl")).read_text().splitlines()
        ]

    def alter_clean(self, kind, edit):
        rows = self.rows(kind)
        edit(rows)
        path = self.out / (kind + ".jsonl")
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        )
        manifest = json.loads((self.out / "manifest.json").read_text())
        manifest["files"][path.name]["sha256"] = sha_file(path)
        write_json(self.out / "manifest.json", manifest)

    def test_realistic_preservation_and_membership(self):
        before = {p.name: sha_file(p) for p in self.inputs.iterdir() if p.is_file()}
        report = normalize(self.config, self.out)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["counts"]["messages"], 8)
        self.assertEqual(report["statistics"]["branch_points"], 2)
        self.assertEqual(report["statistics"]["empty_conversations"], 1)
        self.assertEqual(
            report["statistics"]["repeated_message_ids_across_memberships"], 1
        )
        self.assertEqual(
            report["statistics"]["claude_text_differs_from_text_blocks"], 1
        )
        rows = self.rows("messages")
        shared = [r for r in rows if r["original_id"] == "shared-invented-user"]
        self.assertEqual(len(shared), 2)
        self.assertNotEqual(shared[0]["record_id"], shared[1]["record_id"])
        self.assertIn("~1~0node", shared[0]["provenance"]["json_pointer"])
        self.assertEqual(
            shared[0]["text_segments"][0]["text"],
            "我今天种了薄荷。\nÇa pousse — maybe 🌱!",
        )
        claude = next(r for r in rows if r["original_id"] == "invented-c-a")
        self.assertEqual(
            [s["text"] for s in claude["text_segments"]],
            ["Exported text representation.", "A different block representation."],
        )
        special = next(r for r in rows if r["content_kind"] == "thoughts")
        self.assertEqual(special["text_segments"], [])
        self.assertIn("thoughts", special["raw"]["content"])
        for r in rows:
            pair = inspect_record(self.out, record_id=r["record_id"])
            self.assertEqual(pair["original"], r["raw"])
        self.assertTrue(
            all(
                c["current_node_id"] is None
                for c in self.rows("conversations")
                if c["provider"] == "claude"
            )
        )
        self.assertEqual(
            before, {p.name: sha_file(p) for p in self.inputs.iterdir() if p.is_file()}
        )
        self.assertEqual(validate(self.out), report)

    def test_repeat_import_is_byte_identical(self):
        normalize(self.config, self.out)
        repeat = self.root / "repeat"
        normalize(self.config, repeat)
        for p in self.out.iterdir():
            self.assertEqual(p.read_bytes(), (repeat / p.name).read_bytes(), p.name)
        with self.assertRaises(FormatError):
            normalize(self.config, self.out)

    def test_zip_duplicate_imported_once_all_aliases_checked(self):
        with zipfile.ZipFile(self.inputs / "duplicate.zip", "w") as z:
            z.write(self.inputs / "claude.json", "nested/conversations.json")
        with self.config.open("a") as f:
            f.write(
                '\n[[sources]]\nprovider = "claude"\npath = "duplicate.zip"\nattachment_root = "."\n'
            )
        inv = inventory(self.config)
        self.assertEqual(len(inv["sources"]), 2)
        report = normalize(self.config, self.out)
        self.assertEqual(report["statistics"]["exact_duplicate_source_locations"], 1)
        with (self.inputs / "duplicate.zip").open("ab") as f:
            f.write(b"changed container")
        self.assertEqual(validate(self.out)["status"], "failed")

    def test_unfamiliar_content_preserved_and_reported(self):
        def edit(data):
            data[0]["chat_messages"][1]["content"].append(
                {"type": "future-block", "unknown": ["细节", 42]}
            )

        self.edit_source("claude", edit)
        report = normalize(self.config, self.out)
        self.assertTrue(any(w["code"] == "unknown_content" for w in report["warnings"]))
        row = next(
            r for r in self.rows("messages") if r["original_id"] == "invented-c-a"
        )
        self.assertEqual(row["raw"]["content"][-1]["unknown"], ["细节", 42])

    def test_multimodal_and_unfamiliar_parts_preserved(self):
        def edit(data):
            content = data[0]["mapping"]["user/~node"]["message"]["content"]
            content.update(
                content_type="multimodal_text",
                parts=[
                    "原文",
                    {
                        "content_type": "image_asset_pointer",
                        "asset_pointer": "invented://image",
                    },
                    7,
                ],
            )

        self.edit_source("chatgpt", edit)
        report = normalize(self.config, self.out)
        self.assertTrue(any(w["code"] == "unknown_part" for w in report["warnings"]))
        refs = [
            r
            for r in self.rows("attachments")
            if r["attachment_kind"] == "multimodal_reference"
        ]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["raw"]["asset_pointer"], "invented://image")
        self.assertEqual(refs[0]["availability"], "unverified_reference")

    def test_transcription_is_text_not_an_attachment(self):
        def edit(data):
            data[0]["mapping"]["user/~node"]["message"]["content"].update(
                content_type="multimodal_text",
                parts=[
                    {
                        "content_type": "audio_transcription",
                        "text": "听写 — exact punctuation!",
                    }
                ],
            )

        self.edit_source("chatgpt", edit)
        report = normalize(self.config, self.out)
        self.assertEqual(report["statistics"]["audio_transcription_segments"], 1)
        self.assertEqual(report["counts"]["attachments"], 2)
        row = next(r for r in self.rows("messages") if r["node_id"] == "user/~node")
        self.assertEqual(row["text_segments"][0]["kind"], "transcription_text")
        self.assertEqual(row["text_segments"][0]["text"], "听写 — exact punctuation!")
        self.assertTrue(
            row["text_segments"][0]["json_pointer"].endswith("/parts/0/text")
        )

    def test_unknown_multimodal_dictionary_warns(self):
        def edit(data):
            data[0]["mapping"]["user/~node"]["message"]["content"]["parts"] = [
                {"future_key": "kept"}
            ]

        self.edit_source("chatgpt", edit)
        report = normalize(self.config, self.out)
        self.assertTrue(
            any(w["code"] == "unknown_multimodal_content" for w in report["warnings"])
        )
        self.assertTrue(
            any(r["raw"] == {"future_key": "kept"} for r in self.rows("attachments"))
        )

    def test_unknown_chatgpt_content_is_retained(self):
        self.edit_source(
            "chatgpt",
            lambda d: d[0]["mapping"]["reply-a"]["message"].update(
                content={"content_type": "future-content", "payload": ["新形式"]}
            ),
        )
        report = normalize(self.config, self.out)
        self.assertTrue(any(w["code"] == "unknown_content" for w in report["warnings"]))
        r = next(r for r in self.rows("messages") if r["original_id"] == "invented-a")
        self.assertEqual(r["raw"]["content"]["payload"], ["新形式"])
        self.assertEqual(r["text_segments"], [])

    def test_ambiguous_attachment_not_chosen(self):
        other = self.root / "other"
        other.mkdir()
        (other / "invented-note.txt").write_text("Another invented file")
        with self.config.open("a") as f:
            f.write(
                '\n[[sources]]\nprovider="claude"\npath="claude.json"\nattachment_root="../other"\n'
            )
        normalize(self.config, self.out)
        self.assertTrue(
            any(
                r["availability"] == "ambiguous_candidates"
                and r["resolved_path"] is None
                for r in self.rows("attachments")
            )
        )

    def test_directory_inventory_excludes_sidecars(self):
        source_dir = self.root / "export"
        source_dir.mkdir()
        shutil.copy(self.inputs / "chatgpt.json", source_dir / "conversations-000.json")
        (source_dir / "account.json").write_text(
            '{"invented_account":"not conversation data"}'
        )
        config = self.root / "directory.toml"
        config.write_text('[[sources]]\nprovider="chatgpt"\npath="export"\n')
        inv = inventory(config)
        self.assertEqual(len(inv["sources"]), 1)
        with self.assertRaisesRegex(FormatError, "outside source directories"):
            normalize(config, source_dir / "clean")

    def test_unknown_role_not_inferred(self):
        self.edit_source(
            "claude", lambda d: d[0]["chat_messages"][0].update(sender="future-role")
        )
        report = normalize(self.config, self.out)
        self.assertTrue(any(w["code"] == "unknown_role" for w in report["warnings"]))
        self.assertTrue(any(r["role"] == "unknown" for r in self.rows("messages")))

    def test_dangling_parent_rejected(self):
        self.edit_source(
            "claude",
            lambda d: d[0]["chat_messages"][1].update(
                parent_message_uuid="absent-parent"
            ),
        )
        with self.assertRaisesRegex(FormatError, "dangling_parent"):
            normalize(self.config, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.root.glob(".*-staging-*")), [])

    def test_absent_child_lists_keep_parent_graph(self):
        def remove_children(data):
            for c in data:
                for n in c["mapping"].values():
                    n.pop("children")

        self.edit_source("chatgpt", remove_children)
        report = normalize(self.config, self.out)
        self.assertEqual(report["statistics"]["branch_points"], 2)
        self.assertTrue(
            any(w["code"] == "missing_child_lists" for w in report["warnings"])
        )
        for c in self.rows("conversations"):
            if c["provider"] == "chatgpt":
                self.assertTrue(all(n["children_ids"] is None for n in c["graph"]))

    def test_explicit_contradictory_children_rejected(self):
        self.edit_source(
            "chatgpt", lambda d: d[0]["mapping"]["root"].update(children=[])
        )
        with self.assertRaisesRegex(FormatError, "parent_link"):
            normalize(self.config, self.out)

    def test_cycle_rejected(self):
        self.edit_source(
            "claude",
            lambda d: d[0]["chat_messages"][0].update(
                parent_message_uuid="invented-c-a"
            ),
        )
        with self.assertRaisesRegex(FormatError, "graph_cycle"):
            normalize(self.config, self.out)

    def test_timestamp_without_timezone_rejected(self):
        self.edit_source(
            "claude",
            lambda d: d[0]["chat_messages"][0].update(created_at="2025-01-01T12:30:00"),
        )
        with self.assertRaisesRegex(FormatError, "invalid_timestamp"):
            normalize(self.config, self.out)

    def test_duplicate_claude_id_rejected(self):
        self.edit_source(
            "claude", lambda d: d[0]["chat_messages"][1].update(uuid="invented-c-user")
        )
        with self.assertRaisesRegex(FormatError, "Duplicate Claude"):
            normalize(self.config, self.out)

    def test_wrong_list_shape_rejected(self):
        self.edit_source(
            "claude", lambda d: d[0]["chat_messages"][0].update(content={})
        )
        with self.assertRaisesRegex(FormatError, "content must be a list"):
            normalize(self.config, self.out)

    def test_invalid_json_values_rejected(self):
        for text in ('{"x":1,"x":2}', "[NaN]", "[Infinity]", "{broken"):
            with self.subTest(text=text), self.assertRaises(FormatError):
                strict_loads(text)
        (self.inputs / "claude.json").write_text("{broken")
        with self.assertRaises(FormatError):
            normalize(self.config, self.out)
        self.assertFalse(self.out.exists())

    def test_attachment_availability_and_extracted_text(self):
        report = normalize(self.config, self.out)
        rows = self.rows("attachments")
        self.assertEqual(
            {r["availability"] for r in rows}, {"local_filename_match", "missing"}
        )
        self.assertTrue(
            any(
                s["kind"] == "attachment_text"
                for r in self.rows("messages")
                for s in r["text_segments"]
            )
        )
        self.assertTrue(any(w["code"] == "attachment_gaps" for w in report["warnings"]))
        (self.inputs / "invented-note.txt").write_text("Modified candidate file")
        self.assertTrue(
            any(
                e["code"] == "attachment_availability"
                for e in validate(self.out)["errors"]
            )
        )

    def test_unsafe_attachment_never_resolved(self):
        self.edit_source(
            "claude",
            lambda d: d[0]["chat_messages"][0]["attachments"][0].update(
                file_name="../outside.txt"
            ),
        )
        normalize(self.config, self.out)
        self.assertTrue(
            any(
                r["availability"] == "unsafe_reference" and r["resolved_path"] is None
                for r in self.rows("attachments")
            )
        )

    def test_symlink_attachment_escape_never_resolved(self):
        (self.root / "outside.txt").write_text("Synthetic outside")
        (self.inputs / "invented-note.txt").unlink()
        (self.inputs / "invented-note.txt").symlink_to(self.root / "outside.txt")
        normalize(self.config, self.out)
        self.assertTrue(
            any(
                r["availability"] == "unsafe_reference"
                for r in self.rows("attachments")
            )
        )

    def test_source_mutation_blocks_validation_and_inspection(self):
        normalize(self.config, self.out)
        self.edit_source("claude", lambda d: d[0].update(name="Changed source"))
        self.assertEqual(validate(self.out)["status"], "failed")
        rid = next(
            r["record_id"] for r in self.rows("messages") if r["provider"] == "claude"
        )
        with self.assertRaises(FormatError):
            inspect_record(self.out, record_id=rid)

    def test_clean_tampering_detected(self):
        normalize(self.config, self.out)
        with (self.out / "messages.jsonl").open("a") as f:
            f.write("{}\n")
        self.assertTrue(
            any(
                e["code"] == "clean_hash_mismatch" for e in validate(self.out)["errors"]
            )
        )
        with self.assertRaises(FormatError):
            inspect_record(self.out, line=1)

    def test_fidelity_check_independent_of_manifest_hash(self):
        normalize(self.config, self.out)
        self.alter_clean(
            "messages",
            lambda rows: rows[0]["text_segments"][0].update(
                text="Incorrect simplification"
            ),
        )
        self.assertTrue(
            any(e["code"] == "text_fidelity" for e in validate(self.out)["errors"])
        )

    def test_message_omission_detected_independent_of_hash(self):
        normalize(self.config, self.out)
        self.alter_clean("messages", lambda rows: rows.pop())
        self.assertTrue(
            any(e["code"] == "source_coverage" for e in validate(self.out)["errors"])
        )

    def test_attachment_cannot_be_reassigned(self):
        normalize(self.config, self.out)
        other = next(
            r for r in self.rows("messages") if r["original_id"] == "invented-c-a"
        )
        self.alter_clean(
            "attachments",
            lambda rows: rows[0].update(message_record_id=other["record_id"]),
        )
        self.assertTrue(
            any(
                e["code"] == "attachment_source_membership"
                for e in validate(self.out)["errors"]
            )
        )

    def test_expected_counts_fail_loudly(self):
        self.config.write_text(
            self.config.read_text().replace(
                "chatgpt_messages = 5", "chatgpt_messages = 7"
            )
        )
        with self.assertRaisesRegex(FormatError, "expected_count"):
            normalize(self.config, self.out)

    def test_output_must_not_contain_source(self):
        with self.assertRaises(FormatError):
            normalize(self.config, self.root)

    def test_cli(self):
        def run(*args):
            return subprocess.run(
                [sys.executable, "-m", "conversation_archive", *args],
                text=True,
                capture_output=True,
            )

        inv = run(
            "inventory",
            "--config",
            str(self.config),
            "--output",
            str(self.root / "inventory.json"),
        )
        self.assertEqual(inv.returncode, 0, inv.stderr)
        result = run(
            "normalize", "--config", str(self.config), "--output", str(self.out)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        pair = run("inspect", "--dataset", str(self.out), "--line", "1")
        self.assertEqual(pair.returncode, 0, pair.stderr)
        self.assertIn("original", json.loads(pair.stdout))
        result = run("validate", "--dataset", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            run("inspect", "--dataset", str(self.out), "--line", "0").returncode, 2
        )


if __name__ == "__main__":
    unittest.main()
