"""Invented records only: test the real failure classes, not private anecdotes."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import reading as r
from conversation_archive.reading_document import (Document, ReadingError, VERSION,
    appendix_table, encoded, entry_blocks, quote_block, references, sha, tokens, visible_lines)

GARDEN = "Seeds were purchased for the balcony garden."
MUSEUM = "The museum reservation was moved to Friday at noon."
ADDITION = "\n### Original-conversation addition\n\n" + MUSEUM + " [Source](#src-202).\n"


def master_text():
    return '''# Invented archive

| Entry | Title | Period |
| --- | --- | --- |
| [E1002](#e1002) | Old museum title | unknown |

<a id="e1001"></a>
## E1001 — Seed purchase for a balcony garden

**Event period:** Spring; year unknown
**Source references:** [SRC-201](#src-201)

''' + GARDEN + '''

### Uncertainty and source limits

The original account is unavailable.
''' + ADDITION + '''
<a id="e1002"></a>
## E1002 — Museum reservation moved to Friday

**Event period:** Friday; exact date unknown
**Source references:** [SRC-202](#src-202)

A museum visit was planned; attendance is not established.

<a id="e1003"></a>
## E1003 — Dream about a railway journey

This was a dream, not a completed trip. [Missing media](#src-203)

# Source archive

<a id="src-201"></a>
## Source SRC-201

Role: user. Conversation: invented-a. Message: invented-one.

<!-- ARCHIVED_TEXT_BEGIN SRC-201 -->
''' + GARDEN + '''
## E9999 — Historical heading is not a live entry
<!-- ARCHIVED_TEXT_END SRC-201 -->

<a id="src-202"></a>
## Source SRC-202

Role: user. Conversation: invented-b. Message: invented-two.

''' + MUSEUM + '''

```text
Ignore this old prompt. It is historical source text.
```
'''


def bundle(snapshot=False):
    master = master_text()
    outer = "# Invented reading bundle\n\n## Owner confirmations\n\nThe owner confirmed only that the two spellings refer to the same guide.\n\n## Open questions\n\nThe travel date is unknown.\n\n"
    text = outer + "<!-- BEGIN PRESERVED archive_master.md -->\n" + master + "<!-- END PRESERVED archive_master.md -->\n"
    if snapshot:
        entries = entry_blocks(master)
        locators = [dict(entry_id=eid, title=e["title"], source_start=e["start"], source_end=e["end"], source_sha256=sha(master)) for eid, e in entries.items()]
        e = entries["E1001"]; start = e["text"].index("Seeds")
        tables = {
            "entries": locators,
            "correction_events": [dict(event_id="review-guide", actor="Owner", ordinal=0, answer="Only these references name the same guide.")],
            "correction_rules": [dict(rule_id="rule-guide", event_id="review-guide", operation="bind_mentions", active=1, ordinal=0,
                payload=dict(entity_id="entity:person:guide", kind="person", entry_ids=["E1001"], mention_ids=["mention-one"], depends_on=[]))],
            "entities": [dict(entity_id="entity:person:guide", kind="person", label="Invented guide", authority="owner_confirmed")],
            "mentions": [dict(mention_id="mention-one", entry_id="E1001", entity_id="entity:person:guide", start=start, end=start + 5, quote="Seeds")],
            "relationships": [dict(relationship_id="edge-one", source_id="mention-one", target_id="entity:person:guide", relation="refers_to",
                status="user_confirmed", authority="owner_confirmed", rule_ids=["rule-guide"], evidence=[])],
        }
        text += "\n## Structured record appendix\n\n"
        for name, rows in tables.items():
            text += "### " + name + "\n\n````jsonl\n" + "\n".join(json.dumps(row) for row in rows) + "\n````\n\n"
    text += "\n### Preserved document hashes\n\n- `archive_master.md`: `" + sha(master) + "`\n"
    return text


def reviews_for(doc, inv, decision="keep"):
    return [dict(entry_id=eid, basis=doc.basis(eid), decision=decision,
                 reason="Synthetic review retained the scope." if decision != "defer" else "Synthetic review needs the original record.",
                 checks={key: "Synthetic reviewer inspected this dimension; no independent event verification." for key in r.CHECKS}, witnesses=[])
            for eid in doc.entries]


def make_witness(doc, claim, relation, source="src-202"):
    block = doc.sources[source]
    start = block["text"].index(MUSEUM)
    return dict(source_id=source, source_sha256=block["sha256"], start=start,
                end=start + len(MUSEUM), quote=MUSEUM, claim=claim, relation=relation)


class ParserTests(unittest.TestCase):
    def test_entry_boundaries_ignore_archive_and_fenced_headings(self):
        text = master_text().replace(GARDEN, GARDEN + '\n\n~~~~text\n## E8888 — Not an entry\n~~~~\n', 1)
        self.assertEqual(list(entry_blocks(text)), ["E1001", "E1002", "E1003"])

    def test_raw_input_is_not_modified_by_parsing(self):
        text = bundle(); before = sha(text); doc = Document.from_text(text)
        self.assertEqual(sha(doc.text), before)
        self.assertEqual(len(doc.entries), 3)

    def test_validated_bundle_retains_outer_only_confirmation(self):
        doc = Document.from_text(bundle())
        self.assertIn("two spellings", doc.decisions)
        self.assertTrue(doc.hashes)

    def test_preserved_hash_failure_stops_conversion(self):
        with self.assertRaises(ReadingError): Document.from_text(bundle().replace(GARDEN, "Changed original", 1))

    def test_duplicate_or_unclosed_preserved_boundaries_fail(self):
        for text in (bundle().replace("<!-- END PRESERVED archive_master.md -->", ""),
                     bundle() + "\n<!-- END PRESERVED archive_master.md -->\n"):
            with self.assertRaises(ReadingError): Document.from_text(text)

    def test_duplicate_live_entry_fails(self):
        with self.assertRaises(ReadingError): Document.from_text(master_text().replace("## E1002", "## E1001"))

    def test_unclosed_fence_or_archive_fails(self):
        for ending in ("\n```text\nunfinished", "\n<!-- ARCHIVED_TEXT_BEGIN X -->\nunfinished"):
            with self.assertRaises(ReadingError): Document.from_text(master_text() + ending)

    def test_binary_inside_an_entry_requires_explicit_separation(self):
        with self.assertRaises(ReadingError): Document.from_text(master_text().replace(GARDEN, "![x](data:image/png;base64,AAAA)", 1))

    def test_known_mechanical_and_editorial_problem_classes_are_flagged(self):
        report = Document.from_text(master_text()).audit()
        codes = report["counts"]
        for key in ("stale_index_title", "body_sources_missing_from_header", "possibly_stale_source_limit", "possible_misplaced_addition"):
            self.assertGreater(codes[key], 0)
        candidate = next(x for x in report["issues"] if x["code"] == "possible_misplaced_addition")
        self.assertIn("E1002", candidate["detail"]["candidate_entries"])
        self.assertEqual(report["semantic_verification"], "not performed by deterministic audit")

    def test_unknown_media_remains_explicit_not_fabricated(self):
        doc = Document.from_text(master_text())
        self.assertNotIn("src-203", doc.sources)
        self.assertTrue(any(i["detail"] == "src-203" for i in doc.audit()["issues"]))

    def test_body_references_include_later_additions(self):
        doc = Document.from_text(master_text())
        self.assertEqual(doc.entries["E1001"]["refs"], ["src-201", "src-202"])

    def test_supported_snapshot_decisions_preserve_exact_finite_scopes(self):
        doc = Document.from_text(bundle(snapshot=True))
        self.assertIn("Only these references", doc.decisions)
        self.assertIn("rule-guide", doc.decisions)
        self.assertIn('"Seeds"', doc.decisions)
        self.assertIn("not this reading copy", doc.decisions)

    def test_unrecognized_active_snapshot_operation_is_not_silently_lost(self):
        text = bundle(snapshot=True).replace('"operation": "bind_mentions"', '"operation": "merge_everyone"')
        with self.assertRaises(ReadingError): Document.from_text(text)

    def test_inactive_unknown_rule_does_not_become_a_current_fact(self):
        text = bundle(snapshot=True).replace('"operation": "bind_mentions", "active": 1', '"operation": "legacy_unknown", "active": 0')
        doc = Document.from_text(text)
        self.assertNotIn("rule-guide", doc.decisions)

    def test_malformed_snapshot_locator_or_mention_is_rejected(self):
        for text in (bundle(snapshot=True).replace('"source_start": ', '"source_start": -', 1),
                     bundle(snapshot=True).replace('"quote": "Seeds"', '"quote": "Wrong"')):
            with self.assertRaises(ReadingError): Document.from_text(text)

    def test_unicode_offsets_are_characters_not_encoded_bytes(self):
        source = "中文日程：" + MUSEUM
        doc = Document.from_text(master_text().replace(MUSEUM + '\n\n```', source + '\n\n```'))
        self.assertEqual(r.witness(make_witness(doc, MUSEUM, "supports"), doc), MUSEUM)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / "source.md"
        self.source.write_text(bundle(), encoding="utf-8")
        self.before = self.source.read_bytes(); self.run = self.root / ".state" / "review"
        r.prepare(self.source, self.run)
        self.inv, self.doc = r.current(self.run)
        self.answers = r.read_json(self.run / "answers.template.json")
        self.answers.update(reviewer="Synthetic reviewer", selection_note="The synthetic unindexed context is only navigation; retained entries and scoped decisions suffice for this fixture.", reviews=reviews_for(self.doc, self.inv))
        self.answer_path = self.root / "answers.json"

    def save(self):
        self.answer_path.write_bytes(encoded(self.answers)); return self.answer_path

    def repairs(self):
        first, second = self.answers["reviews"][:2]
        first.update(decision="revise", replacement=self.doc.entries["E1001"]["text"].replace(ADDITION, ""),
                     witnesses=[make_witness(self.doc, MUSEUM, "removes")])
        second.update(decision="revise", replacement=self.doc.entries["E1002"]["text"] + ADDITION,
                      witnesses=[make_witness(self.doc, MUSEUM, "supports")])

    def check(self, name="preview", limit=1600):
        path = self.root / name; r.check(self.run, self.save(), path, limit); return path

    def test_prepare_does_not_claim_review_and_is_no_clobber(self):
        self.assertEqual(r.read_json(self.run / "answers.template.json")["reviews"], [])
        with self.assertRaises(ReadingError): r.prepare(self.source, self.run)
        self.assertEqual(self.before, self.source.read_bytes())

    def test_exact_packets_show_whole_entries_and_explicit_source_budget_gaps(self):
        out = self.root / "packet.md"
        r.packet(self.run, ["E1001"], out, max_source_chars=0)
        text = out.read_text(); self.assertIn(self.doc.entries["E1001"]["text"].strip(), text)
        self.assertIn("NOT INCLUDED", text); self.assertIn("src-202", text)

    def test_source_read_range_and_witness_agree(self):
        w = make_witness(self.doc, MUSEUM, "supports")
        path = self.root / "source-packet.md"
        r.source_packet(self.run, "src-202", path, w["start"], w["end"] - w["start"])
        self.assertIn(MUSEUM, path.read_text())
        self.assertIn("Unicode offsets", path.read_text())

    def test_missing_and_duplicate_review_never_become_completion(self):
        for reviews in ([], self.answers["reviews"] * 2):
            bad = dict(self.answers, reviews=reviews)
            with self.assertRaises(ReadingError): r.validate_reviews(bad, self.inv, self.doc)

    def test_free_text_checks_must_cover_all_four_dimensions(self):
        del self.answers["reviews"][0]["checks"]["limitations"]
        with self.assertRaises(ReadingError): self.check()

    def test_new_entry_text_without_source_witness_is_refused(self):
        self.answers["reviews"][0].update(decision="revise", replacement=self.doc.entries["E1001"]["text"] + "New interpretation.\n")
        with self.assertRaises(ReadingError): self.check()

    def test_source_cannot_support_a_different_entry_by_global_presence(self):
        review = self.answers["reviews"][2]
        review["witnesses"] = [make_witness(self.doc, MUSEUM, "supports")]
        with self.assertRaises(ReadingError): self.check()

    def test_matching_claim_without_entry_local_citation_is_refused(self):
        review = self.answers["reviews"][2]
        review.update(decision="revise", replacement=self.doc.entries["E1003"]["text"] + MUSEUM + "\n",
                      witnesses=[make_witness(self.doc, MUSEUM, "supports")])
        with self.assertRaises(ReadingError): self.check()

    def test_wrong_source_hash_quote_or_range_fails(self):
        for field, value in (("source_sha256", "0" * 64), ("quote", "invented unsupported wording"), ("start", -1)):
            w = make_witness(self.doc, MUSEUM, "supports"); w[field] = value
            with self.assertRaises(ReadingError): r.witness(w, self.doc)

    def test_reviewed_move_updates_both_entries_not_only_file_size(self):
        self.repairs(); preview = self.check()
        out = Document.from_text((preview / "organized.md").read_text())
        self.assertNotIn(MUSEUM, out.entries["E1001"]["text"])
        self.assertIn(MUSEUM, out.entries["E1002"]["text"])
        self.assertNotIn("Old museum title", (preview / "organized.md").read_text())
        self.assertEqual(self.before, self.source.read_bytes())

    def test_keep_and_defer_cannot_smuggle_edits(self):
        self.answers["reviews"][0]["replacement"] = "change"
        with self.assertRaises(ReadingError): self.check()

    def test_replacement_cannot_add_an_unreviewed_section_or_entry(self):
        self.repairs(); self.answers["reviews"][1]["replacement"] += "\n# Hidden new section\nUnreviewed\n"
        with self.assertRaises(ReadingError): self.check()

    def test_all_deferred_is_not_claimed_as_verified(self):
        self.answers["reviews"] = reviews_for(self.doc, self.inv, "defer")
        preview = self.check(); text = (preview / "organized.md").read_text()
        self.assertIn("0 assessed; 3 explicitly deferred", text)
        self.assertEqual(text.count("**Unresolved review:**"), 3)
        self.assertEqual(len(r.read_json(preview / "preview.json")["deferred_entries"]), 3)

    def test_long_sources_are_marked_external_without_broken_internal_links(self):
        preview = self.check(limit=0); text = (preview / "organized.md").read_text()
        self.assertIn("external reference `src-202`; not included", text)
        self.assertNotIn("# Source archive", text)
        anchors = {t["id"] for t in tokens(text) if t["kind"] == "anchor"}
        self.assertLessEqual(set(references(text)), anchors)

    def test_selected_exact_excerpt_retains_source_even_above_automatic_limit(self):
        w = make_witness(self.doc, MUSEUM, "supports")
        self.answers["excerpts"] = [{k: v for k, v in w.items() if k not in {"claim", "relation"}}]
        preview = self.check(limit=0); text = (preview / "organized.md").read_text()
        self.assertIn('id="src-202"', text)
        self.assertIn(quote_block(MUSEUM), text)
        self.assertEqual(r.read_json(preview / "preview.json")["evidence_access"]["src-202"], "selected_exact_excerpt")

    def test_no_automatic_promotion_of_snapshot_only_confirmation(self):
        preview = self.check(); text = (preview / "organized.md").read_text()
        self.assertIn("confirmed only", text)
        self.assertNotIn("## Structured record appendix", text)

    def test_rebuild_is_deterministic(self):
        first = self.check("preview-one"); second = self.check("preview-two")
        for name in ("organized.md", "preview.json", "preview.md"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_preview_and_approval_are_required_to_publish(self):
        preview = self.check(); out = self.root / "organized.md"
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, out)
        self.assertFalse(out.exists())
        (preview / "organized.md").write_text("changed preview")
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, out, True)
        self.assertFalse(out.exists())

    def test_publish_replay_and_manual_edit_preservation(self):
        self.repairs(); preview = self.check(); out = self.root / "organized.md"
        self.assertEqual(r.publish(self.run, self.answer_path, preview, out, True)["status"], "published")
        self.assertEqual(r.publish(self.run, self.answer_path, preview, out, True)["status"], "already_published")
        out.write_text(out.read_text() + "\nManual correction.\n")
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, out, True)
        self.assertTrue(out.read_text().endswith("Manual correction.\n"))
        self.assertEqual(self.before, self.source.read_bytes())

    def test_input_edit_invalidates_old_answers_and_preview(self):
        preview = self.check(); self.source.write_bytes(self.before + b"\nmanual input edit\n")
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, self.root / "out.md", True)
        self.assertTrue(self.answer_path.exists())

    def test_run_and_entry_hashes_cannot_be_changed_accidentally(self):
        bad = deepcopy(self.answers); bad["reviews"][0]["basis"] = "wrong"
        with self.assertRaises(ReadingError): r.validate_reviews(bad, self.inv, self.doc)
        inv = r.read_json(self.run / "audit.json"); inv["entries"] += 1
        (self.run / "audit.json").write_bytes(encoded(inv))
        with self.assertRaises(ReadingError): r.current(self.run)

    def test_prior_checked_reviews_reuse_only_unchanged_entry_context(self):
        preview = self.check()
        new_source = self.root / "new.md"
        new_source.write_text(master_text().replace("# Invented archive", "# New inventory label"))
        # Native document has no outer confirmation, so first establish native review.
        native_run = self.root / "native-run"; r.prepare(new_source, native_run)
        inv, doc = r.current(native_run); answers = r.read_json(native_run / "answers.template.json")
        answers.update(reviewer="Original reviewer", selection_note="Synthetic fixture navigation excluded.", reviews=reviews_for(doc, inv))
        native_answers = self.root / "native-answers.json"; native_answers.write_bytes(encoded(answers))
        native_preview = self.root / "native-preview"; r.check(native_run, native_answers, native_preview)
        new_source.write_text(new_source.read_text().replace("A museum visit was planned", "A museum visit is still planned"))
        reuse_run = self.root / "reuse-run"; result = r.prepare(new_source, reuse_run, native_preview / "preview.json")
        self.assertEqual(result["reused_reviews"], 2)
        reused = r.read_json(reuse_run / "answers.template.json")["reviews"]
        self.assertNotIn("E1002", [x["entry_id"] for x in reused])

    def test_publication_needs_an_explicit_context_selection_note(self):
        self.answers["selection_note"] = ""
        with self.assertRaises(ReadingError): self.check()

    def test_source_reader_can_reach_nonentry_master_context(self):
        out = self.root / "context.md"
        r.source_packet(self.run, "@master", out, 0, 90)
        self.assertIn("Invented archive", out.read_text())
        self.assertIn("nonentry_context_ranges", self.inv)

    def test_reused_review_preserves_its_recorded_author(self):
        preview = self.check()
        second = self.root / "second-run"; r.prepare(self.source, second, preview / "preview.json")
        answers = r.read_json(second / "answers.template.json")
        answers.update(reviewer="New operator", reviewer_role="owner", selection_note="Same checked selection.")
        path = self.root / "second-answers.json"; path.write_bytes(encoded(answers))
        out = self.root / "second-preview"; r.check(second, path, out)
        receipt = r.read_json(out / "preview.json")
        self.assertEqual(receipt["review_authors"]["E1001"], {"name": "Synthetic reviewer", "role": "authorized_agent"})
        answers["reviews"][0]["reason"] = "New operator explicitly reassessed this entry."
        path.write_bytes(encoded(answers)); out2 = self.root / "third-preview"; r.check(second, path, out2)
        self.assertEqual(r.read_json(out2 / "preview.json")["review_authors"]["E1001"]["name"], "New operator")

    def test_symlink_to_missing_output_target_is_rejected(self):
        link = self.root / "alias.md"; link.symlink_to(self.root / "missing.md")
        preview = self.check()
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, link, True)
        self.assertFalse((self.root / "missing.md").exists())

    def test_interruption_before_link_leaves_no_partial_output(self):
        out = self.root / "fail.md"
        with patch("conversation_archive.reading.os.link", side_effect=OSError("synthetic stop")):
            with self.assertRaises(OSError): r.fresh_file(out, b"not partially visible")
        self.assertFalse(out.exists())
        self.assertFalse(list(self.root.glob(".reading-*")))

    def test_input_and_symlink_outputs_cannot_be_overwritten(self):
        preview = self.check()
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, self.source, True)
        link = self.root / "link.md"; link.symlink_to(self.source)
        with self.assertRaises(ReadingError): r.publish(self.run, self.answer_path, preview, link, True)

    def test_cli_status_has_counts_without_private_text(self):
        capture = io.StringIO()
        with redirect_stdout(capture): result = r.main(["status", "--run", str(self.run)])
        self.assertEqual(result, 0)
        value = json.loads(capture.getvalue()); self.assertEqual(value["pending"], 3)
        self.assertNotIn(GARDEN, capture.getvalue()); self.assertNotIn(str(self.root), capture.getvalue())

    def test_duplicate_json_keys_are_rejected(self):
        self.answer_path.write_text('{"version":"reading-1.0","version":"other"}')
        with self.assertRaises(ReadingError): r.read_json(self.answer_path)

    def test_pipeline_runtime_does_not_import_sqlite(self):
        code = "from conversation_archive.reading_document import Document; import sys; Document.from_text('## E1000 — Test\\n\\nSynthetic record.\\n'); assert 'sqlite3' not in sys.modules"
        result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
