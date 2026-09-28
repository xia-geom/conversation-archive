"""Real importer -> approved key information -> one Markdown file; invented data only."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import reconciliation as r
from conversation_archive.demo import synthetic_export
from conversation_archive.model import FormatError
from conversation_archive.pipeline import normalize

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def prepare_example(root, name="initial", sentence=None):
    state = root / ".state" / name
    state.mkdir(parents=True)
    exported = synthetic_export()[:1]
    if sentence:
        exported[0]["mapping"]["u"]["message"]["content"]["parts"] = [sentence]
    source = write(root / "exports" / (name + ".json"), exported)
    config = state / "inputs.toml"
    config.write_text('[[sources]]\nprovider="chatgpt"\npath=' + json.dumps(str(source)) + '\n')
    normalize(config, state / "dataset")
    document = root / "organized.md"
    if not document.exists():
        r.init_document(document)
    run = state / "review"
    r.prepare(state / "dataset", document, run, project_id="invented-project", document_only=True)
    return document, run, source


def review_example(run, did="garden"):
    packet = r.packet(run)
    piece = next(p for p in packet["pieces"] if p["role"] == "user" and p["segment_index"] >= 0)
    quote = dict(message_record_id=piece["message_record_id"], segment_index=piece["segment_index"],
                 start=piece["start"], end=piece["end"], text=piece["text"])
    decision = dict(decision_id=did, reviewer="Synthetic test reviewer", reviewed_at="2026-01-01T00:00:00Z",
        coverage=[dict(piece_id=p["piece_id"], outcome="complementary_detail" if p is piece else "excluded",
                       reason="Invented user report retained; assistant suggestions are not owner facts.",
                       finding_ids=["F1"] if p is piece else []) for p in packet["pieces"]],
        findings=[dict(finding_id="F1", outcome="complementary_detail", reason="Explicit synthetic user report.",
                       attribution="owner", quotes=[quote])])
    r.record(run, decision)
    return decision, piece


def supported_entry(piece, eid="E0001", interpretation="The owner reported planting mint."):
    return (f'<a id="{eid.lower()}"></a>\n### {eid} — Garden\n\n{interpretation}\n\n'
            f'Source: ChatGPT, message `{piece["original_message_id"]}`, '
            f'export SHA-256 `{piece["provenance"]["sha256"]}`, '
            f'JSON pointer `{piece["provenance"]["json_pointer"]}`.\n'
            'Event date: not established by the message timestamp.\n\n'
            f'```text\n{piece["text"]}\n```\n')


def stage_example(document, run, decision, before_passage, after_passage, eid="E0001", bid="garden-update"):
    return r.draft(run, dict(batch_id=bid, document_sha256=r.digest(r.read_document(document)),
        decision_ids=[decision["decision_id"]], finding_dispositions={decision["decision_id"] + "/F1":
            dict(outcome="integrated", reason="Source-checked synthetic entry.", entry_ids=[eid])},
        patches=[dict(before=before_passage, after=after_passage)]), Path(run) / (bid + ".json"))


class MarkdownWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.document, self.run, self.source = prepare_example(self.root)
        self.source_hash = r.sha_file(self.source)
        self.decision, self.piece = review_example(self.run)
        self.before = r.read_document(self.document)
        self.marker = '<!-- Add supported entries with stable E0001-style IDs here. -->'

    def stage(self):
        stage_example(self.document, self.run, self.decision, self.marker, supported_entry(self.piece))
        return self.run / "garden-update.json"

    def test_actual_markdown_output_needs_no_reports_or_database(self):
        batch = self.stage()
        self.assertEqual(r.read_document(self.document), self.before)
        self.assertEqual(set(r.load(batch)["files"]), {"organized.md"})
        self.assertEqual(r.check(self.run, batch)[0]["report_validation"]["status"], "not_required")
        self.assertEqual(r.apply(self.run, batch)["status"], "applied")
        text = r.read_document(self.document)
        self.assertIn("The owner reported planting mint.", text)
        self.assertIn(self.piece["text"], text)
        self.assertNotIn("You may enjoy gardening.", text)
        self.assertEqual([p.name for p in self.root.glob("*.md")], ["organized.md"])
        self.assertFalse(list(self.root.rglob("*.sqlite*")))
        self.assertEqual(r.sha_file(self.source), self.source_hash)
        self.assertEqual(r.apply(self.run, batch)["status"], "already_applied")
        self.assertEqual(r.read_document(self.document).count('<a id="e0001">'), 1)

    def test_manual_edit_after_preparation_survives_checked_patch(self):
        self.document.write_text(self.before + "\nOwner correction: keep the garden accounts separate.\n")
        batch = self.stage()
        r.apply(self.run, batch)
        self.assertIn("Owner correction: keep the garden accounts separate.", r.read_document(self.document))

    def test_edit_after_draft_is_not_overwritten(self):
        batch = self.stage()
        current = self.before + "\nManual edit after draft.\n"
        self.document.write_text(current)
        with self.assertRaises(FormatError): r.apply(self.run, batch)
        self.assertEqual(r.read_document(self.document), current)

    def test_stale_edit_plan_is_rejected(self):
        edits = dict(batch_id="stale", document_sha256="wrong", decision_ids=[], finding_dispositions={}, patches=[])
        with self.assertRaises(FormatError): r.draft(self.run, edits, self.run / "bad.json")
        self.assertFalse((self.run / "bad.json").exists())

    def test_extraneous_report_or_path_is_rejected(self):
        batch = r.load(self.stage())
        batch["files"]["../unrelated.md"] = next(iter(batch["files"].values()))
        with self.assertRaises(FormatError): r.apply(self.run, batch)
        self.assertFalse((self.root.parent / "unrelated.md").exists())

    def test_same_document_has_one_lock_across_runs(self):
        batch = self.stage()
        with r.document_lock(self.document), self.assertRaises(FormatError):
            r.apply(self.run, batch)
        self.assertEqual(r.read_document(self.document), self.before)

    def test_interruption_after_document_install_is_recoverable(self):
        batch = self.stage(); original = r.atomic_text
        def interrupt(path, text):
            if Path(path).name == "garden-update.json" and '"status": "complete"' in text:
                raise OSError("Synthetic journal interruption")
            return original(path, text)
        with patch.object(r, "atomic_text", side_effect=interrupt), self.assertRaises(OSError):
            r.apply(self.run, batch)
        self.assertEqual(r.load(self.run / "changes" / "garden-update.json")["status"], "installing")
        self.assertEqual(r.apply(self.run, batch)["status"], "applied")
        self.assertEqual(r.read_document(self.document).count('<a id="e0001">'), 1)

    def test_later_export_adds_correction_without_destroying_old_evidence(self):
        r.apply(self.run, self.stage())
        old = r.read_document(self.document)
        self.document.write_text(old + "\nManual note: use reported wording, not a diagnosis.\n")
        document, run2, _ = prepare_example(self.root, "later", "I planted basil. My earlier claim about mint was wrong.")
        decision, piece = review_example(run2, "later-report")
        old_sentence = "The owner reported planting mint."
        new = ("The owner initially reported mint; a later message corrected that to basil.\n\n"
               + supported_entry(piece, "E0002", "Later correction reported by the owner."))
        stage_example(document, run2, decision, old_sentence, new, "E0002", "later-update")
        r.apply(run2, run2 / "later-update.json")
        text = r.read_document(document)
        self.assertIn(self.piece["text"], text); self.assertIn(piece["text"], text)
        self.assertIn("Manual note: use reported wording", text)
        self.assertEqual(r.sha_file(self.source), self.source_hash)
        self.assertEqual(r.apply(run2, run2 / "later-update.json")["status"], "already_applied")

    def test_preserved_quote_cannot_be_silently_rewritten(self):
        r.apply(self.run, self.stage())
        from conversation_archive.master_validation import validate_master
        text = r.read_document(self.document)
        self.assertEqual(validate_master(text.replace(self.piece["text"], "invented replacement"), text)["status"], "failed")

    def test_missing_source_passage_cannot_be_installed(self):
        with self.assertRaises(FormatError):
            stage_example(self.document, self.run, self.decision, self.marker,
                          supported_entry(self.piece).replace(self.piece["text"], "unsupported paraphrase"))

    def test_utf8_newlines_preserved(self):
        path = self.root / "unicode.md"; raw = "# 中文\r\nÉvidence.\r\n".encode()
        path.write_bytes(raw); self.assertEqual(r.read_document(path).encode(), raw)

    def test_initializer_does_not_overwrite(self):
        with self.assertRaises(FileExistsError): r.init_document(self.document)
        self.assertEqual(r.read_document(self.document), self.before)

    def test_new_cli_defaults_to_markdown_and_requires_apply_confirmation(self):
        batch = self.stage()
        base = [sys.executable, "-m", "conversation_archive", "organize"]
        packet = subprocess.run(base + ["packet", "--run", str(self.run), "--packet-id", "P0001-0001"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertTrue(packet.stdout.startswith("# Review packet"))
        attempt = subprocess.run(base + ["apply", "--run", str(self.run), "--batch", str(batch)],
                                 cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(attempt.returncode, 2)
        self.assertEqual(r.read_document(self.document), self.before)
        approved = subprocess.run(base + ["apply", "--run", str(self.run), "--batch", str(batch),
                                         "--confirm-user-answer"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(approved.returncode, 0, approved.stderr)

    def test_no_database_import_in_runtime_package(self):
        for path in (ROOT / "conversation_archive").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                names = [n.name for n in node.names] if isinstance(node, ast.Import) else (
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                self.assertFalse(any(n.split('.')[0] in {"sqlite3", "sqlalchemy"} for n in names), path)


if __name__ == "__main__":
    unittest.main()
