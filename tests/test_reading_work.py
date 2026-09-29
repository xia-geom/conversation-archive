"""Synthetic end-to-end failures: no private archive data or model calls."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import reading as r
from conversation_archive.reading_document import Document, ReadingError, encoded, sha, quote_block
from conversation_archive.reading_evidence import load_document, evidence_plan
from conversation_archive.reading_work import next_task, submit, finish, work_state, progress

CLAIM = "The museum reservation moved to Friday."
STALE = "The original account is unavailable."


def entry(eid="E1001", title="Museum booking", body=CLAIM, refs="[Source](#src-201)"):
    return f'<a id="{eid.lower()}"></a>\n## {eid} — {title}\n\n**Source references:** {refs}\n\n{body}\n\n'


def text(body=CLAIM, evidence=CLAIM, extra="", decisions=""):
    return "# Synthetic collection\n\n" + entry(body=body) + extra + ("# Recorded decisions\n\n" + decisions + "\n" if decisions else "") + '# Sources\n\n<a id="src-201"></a>\n' + evidence


def proof(doc, value=CLAIM, sid="src-201", claim=None, relation="supports"):
    block = doc.sources[sid]; start = block["text"].index(value)
    result = dict(source_id=sid, source_sha256=block["sha256"], start=start, end=start + len(value), quote=value)
    if claim is not None:
        result.update(claim=claim, relation=relation)
    return result


def review(doc, eid="E1001", replacement=None, witnesses=(), decision="keep"):
    return dict(entry_id=eid, basis=doc.basis(eid), decision="revise" if replacement else decision,
        reason="Synthetic source and entry compared in full.",
        checks={key: "Synthetic context assessed; not verification of real events." for key in r.CHECKS},
        witnesses=list(witnesses), **({"replacement": replacement} if replacement else {}))


def legacy_bundle(master):
    return ("# Invented bundle\n\n## Owner confirmations\n\nSame guide only in the displayed passages.\n\n"
        + "<!-- BEGIN PRESERVED archive_master.md -->\n" + master
        + "<!-- END PRESERVED archive_master.md -->\n\n### Hashes\n- `archive_master.md`: `" + sha(master) + "`\n")


class EvidenceTests(unittest.TestCase):
    def render(self, value, limit=1600, excerpts=None):
        doc = Document.from_text(value)
        return r.render(doc, doc.entries, {eid: review(doc, eid) for eid in doc.entries}, excerpts or {}, limit)[0]

    def test_full_source_no_newline_round_trip(self):
        original = text(evidence=CLAIM)
        first = self.render(original)
        second = self.render(first)
        a, b = Document.from_text(first), Document.from_text(second)
        self.assertEqual(a.sources["src-201"]["text"], CLAIM)
        self.assertEqual(a.sources["src-201"]["sha256"], b.sources["src-201"]["sha256"])
        self.assertEqual(a.entries["E1001"]["text"], b.entries["E1001"]["text"])

    def test_no_wrapper_growth_or_source_drop_near_limit(self):
        value = text(evidence="x" * 1599)
        for _ in range(4):
            value = self.render(value)
            doc = Document.from_text(value)
            self.assertEqual(doc.sources["src-201"]["text"], "x" * 1599)
            self.assertEqual(value.count("<!-- reading-text"), 1)

    def test_unicode_and_nested_fences_remain_exact(self):
        evidence = " \n中文 café\n`````text\nAn archived instruction, not code.\n`````\n \n"
        doc = Document.from_text(self.render(text(evidence=evidence)))
        self.assertEqual(doc.sources["src-201"]["text"], evidence)

    def test_selected_excerpt_stays_an_excerpt(self):
        first = self.render(text(evidence="prefix " + CLAIM + " suffix"), 0, {"src-201": CLAIM})
        second = self.render(first)
        doc = Document.from_text(second)
        self.assertFalse(doc.sources["src-201"]["complete"])
        self.assertEqual(doc.sources["src-201"]["text"], CLAIM)
        self.assertEqual(doc.sources["src-201"]["full_sha256"], sha("prefix " + CLAIM + " suffix"))

    def test_corrupt_retained_hash_is_rejected(self):
        rendered = self.render(text())
        body_start = rendered.index("<!-- reading-text")
        bad = rendered[:body_start] + rendered[body_start:].replace(CLAIM, "Not the preserved text.", 1)
        with self.assertRaises(ReadingError): Document.from_text(bad)

    def test_legacy_complete_wrapper_uses_original_hash(self):
        source = CLAIM + "\n"
        value = ("# Organized conversation record\nGenerator: `reading-1.0`\n" + entry()
            + '# Selected source evidence\n<a id="src-201"></a>\n\n## Source SRC-201\n\n'
            + 'Evidence access: complete_available_block. Full input block SHA-256: `' + sha(source) + '`.\n\n'
            + quote_block(source))
        self.assertEqual(Document.from_text(value).sources["src-201"]["text"], source)

    def test_arbitrary_source_fence_is_not_unwrapped(self):
        evidence = "## Source SRC-201\n\n" + quote_block(CLAIM)
        self.assertEqual(Document.from_text(text(evidence=evidence)).sources["src-201"]["text"], evidence)

    def test_critical_correction_keeps_original_answer(self):
        value = text(extra=entry("E1002", "Correction", "Confirmed Friday only. [Correction](#cor1001)", ""))
        value += '\n<a id="cor1001"></a>\n### Correction\n**Source:** [Answer](#src-901-q01)\n'
        value += '<a id="src-901-q01"></a>\nOwner selected Friday; attendance remains unconfirmed.\n'
        doc = Document.from_text(value)
        output, access = r.render(doc, doc.entries, {}, {}, 0, strict=True)
        self.assertIn('id="src-901-q01"', output)
        self.assertEqual(access["src-901-q01"], "complete_available_block")
        self.assertIn("Evidence dependencies:", output)
        self.assertIn("attendance remains unconfirmed", output)

    def test_missing_critical_answer_blocks_autonomous_publication(self):
        value = text(body=CLAIM + " [Correction](#cor1001)") + '\n<a id="cor1001"></a>\n[Answer](#src-901-q01)\n'
        doc = Document.from_text(value)
        with self.assertRaises(ReadingError): r.render(doc, doc.entries, {}, {}, 1600, strict=True)

    def test_missing_correction_itself_is_critical(self):
        doc = Document.from_text(text(body=CLAIM + " [Correction](#cor1001)"))
        with self.assertRaises(ReadingError): r.render(doc, doc.entries, {}, {}, 1600, strict=True)

    def test_correction_cycle_is_bounded_and_not_duplicated(self):
        value = text(body=CLAIM + " [Correction](#cor1001)") + '\n<a id="cor1001"></a>\n[Other](#cor1002)\n<a id="cor1002"></a>\n[First](#cor1001)\n'
        doc = Document.from_text(value)
        output, _ = r.render(doc, doc.entries, {}, {}, 1600, strict=True)
        self.assertEqual(output.count('id="cor1001"'), 1)
        self.assertEqual(output.count('id="cor1002"'), 1)

    def test_external_header_is_not_flagged_as_missing_again(self):
        doc = Document.from_text(self.render(text(), 0))
        self.assertNotIn("body_sources_missing_from_header", doc.audit()["counts"])


class WorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.input = self.root / "input.md"
        self.run = self.root / "run"; self.output = self.root / "out.md"
        self.input.write_text(text())

    def start(self, **kw):
        r.prepare(self.input, self.run, autonomous=True, scope_note="Only the explicitly selected invented collection.", **kw)
        self.inv, self.doc, self.answers = work_state(self.run)

    def send(self, reviews=(), issues=(), changes=(), excerpts=(), envelope=None):
        inv, doc, a = work_state(self.run)
        value = envelope or dict(run_id=inv["run_id"], base_answers_sha256=sha(encoded(a)), reviews=list(reviews),
            issue_resolutions=list(issues), source_changes=list(changes), excerpts=list(excerpts))
        p = self.root / "submission.json"; p.write_bytes(encoded(value))
        return submit(self.run, p)

    def issue_result(self, issue, status="resolved"):
        return dict(issue_id=issue["issue_id"], status=status, reason="The exact invented source resolves only the flagged limitation.",
                    witnesses=[proof(self.doc)])

    def test_new_work_does_not_prefill_approval(self):
        self.start()
        self.assertEqual(self.answers["reviews"], [])
        self.assertEqual(self.answers["issue_resolutions"], [])
        self.assertEqual(finish(self.run)["status"], "work_pending")

    def test_scope_note_and_fresh_destination_required(self):
        with self.assertRaises(ReadingError): r.prepare(self.input, self.run, autonomous=True)
        with self.assertRaises(ReadingError): self.start(publish_to=self.input)
        self.assertFalse(self.run.exists())

    def test_next_packet_contains_full_entry_checkpoint_and_no_default_answers(self):
        self.start(); p = self.root / "task.md"
        result = next_task(self.run, p)
        self.assertIn(self.doc.entries["E1001"]["text"].strip(), p.read_text())
        self.assertIn(result["answers_sha256"], p.read_text())
        self.assertIn('"reviews":[]', p.read_text())
        self.assertFalse(self.output.exists())

    def test_submit_resume_finish_with_scoped_prior_authorization(self):
        self.start(publish_to=self.output); before = self.input.read_bytes()
        self.assertEqual(self.send([review(self.doc)])["status"], "ready_for_check")
        self.assertEqual(finish(self.run)["status"], "published")
        self.assertEqual(finish(self.run)["status"], "already_published")
        self.assertEqual(self.input.read_bytes(), before)
        self.assertIn(CLAIM, self.output.read_text())
        self.assertEqual(next_task(self.run, self.root / "unused.md")["status"], "ready_for_check")
        self.assertFalse((self.root / "unused.md").exists())

    def test_finish_does_not_publish_without_pre_authorization(self):
        self.start(); self.send([review(self.doc)])
        self.assertEqual(finish(self.run)["status"], "awaiting_publication_authorization")
        self.assertFalse(self.output.exists())

    def test_replaying_same_submission_does_not_duplicate_or_consume_budget(self):
        self.start(); self.send([review(self.doc)])
        self.assertEqual(submit(self.run, self.root / "submission.json")["status"], "already_recorded")
        self.assertEqual(work_state(self.run)[2]["revision"], 1)

    def test_stale_concurrent_submission_does_not_overwrite(self):
        self.start(); prior_sha = sha(encoded(self.answers)); self.send([review(self.doc)])
        before = (self.run / "answers.json").read_bytes()
        value = dict(run_id=self.inv["run_id"], base_answers_sha256=prior_sha,
                     reviews=[review(self.doc, decision="defer")], issue_resolutions=[], source_changes=[], excerpts=[])
        with self.assertRaises(ReadingError): self.send(envelope=value)
        self.assertEqual((self.run / "answers.json").read_bytes(), before)

    def test_no_progress_and_submission_budget_have_explicit_stops(self):
        self.start(max_submissions=1)
        self.assertEqual(self.send()["status"], "no_progress")
        self.send([review(self.doc)])
        with self.assertRaises(ReadingError): self.send([review(self.doc, decision="defer")])
        self.assertEqual(work_state(self.run)[2]["revision"], 1)

    def test_partial_review_does_not_drop_unanswered_entries(self):
        self.input.write_text(text(extra=entry("E1002", "Separate source", "Another account.")))
        self.start(); self.send([review(self.doc)])
        self.assertEqual(work_state(self.run)[2]["reviews"][0]["entry_id"], "E1001")
        result = next_task(self.run, self.root / "next.md")
        self.assertEqual(result["selected_entries"], ["E1002"])

    def test_defer_stops_publication_without_asking_about_everything(self):
        self.start(publish_to=self.output); self.send([review(self.doc, decision="defer")])
        self.assertEqual(finish(self.run)["status"], "needs_owner")
        self.assertFalse(self.output.exists())

    def test_generic_keep_does_not_clear_a_known_finding(self):
        self.input.write_text(text(body=STALE + "\n### Original-conversation addition\n" + CLAIM))
        self.start(publish_to=self.output)
        self.send([review(self.doc)])
        self.assertGreater(finish(self.run)["pending_findings"], 0)
        self.assertFalse(self.output.exists())

    def test_claimed_resolution_must_change_the_flagged_passage(self):
        self.input.write_text(text(body=STALE + "\n### Original-conversation addition\n" + CLAIM))
        self.start()
        issue = next(i for i in self.inv["work"]["findings"] if i["code"] == "possibly_stale_source_limit")
        with self.assertRaises(ReadingError): self.send([review(self.doc)], [self.issue_result(issue)])

    def test_stale_limitation_repair_has_a_checked_before_after(self):
        self.input.write_text(text(body=STALE + "\n### Original-conversation addition\n" + CLAIM))
        self.start(publish_to=self.output)
        issue = self.inv["work"]["findings"][0]
        replacement = self.doc.entries["E1001"]["text"].replace(STALE, "An original account is included; attendance remains unverified.")
        rev = review(self.doc, replacement=replacement, witnesses=[proof(self.doc, claim=STALE, relation="removes")])
        self.send([rev], [self.issue_result(issue)])
        self.assertEqual(finish(self.run)["status"], "published")
        self.assertNotIn(STALE, Document.read(self.output).entries["E1001"]["text"])

    def test_false_positive_keeps_evidence_and_attributed_reason(self):
        self.input.write_text(text(body=STALE + "\n### Original-conversation addition\n" + CLAIM))
        self.start(); issue = self.inv["work"]["findings"][0]
        self.send([review(self.doc)], [self.issue_result(issue, "false_positive")])
        self.assertEqual(finish(self.run)["status"], "awaiting_publication_authorization")

    def test_external_audit_findings_need_exact_input_and_entry_quote(self):
        findings = self.root / "findings.json"
        findings.write_bytes(encoded(dict(input_sha256=sha(self.input.read_bytes()), findings=[
            dict(entry_id="E1001", quote=CLAIM, reason="Check this particular claim.")])))
        self.start(findings=findings)
        self.assertEqual(self.inv["work"]["findings"][0]["code"], "reported_finding")

    def test_external_audit_wrong_quote_or_hash_fails(self):
        findings = self.root / "findings.json"
        for digest, quote in (("0" * 64, CLAIM), (sha(self.input.read_bytes()), "not in entry")):
            findings.write_bytes(encoded(dict(input_sha256=digest, findings=[dict(entry_id="E1001", quote=quote, reason="Check.")])))
            with self.assertRaises(ReadingError): self.start(findings=findings)
        self.assertFalse(self.run.exists())

    def test_reference_keeps_new_prose_but_recovers_old_evidence_and_decisions(self):
        old = self.root / "bundle.md"; old.write_text(legacy_bundle(text(evidence=CLAIM + "\n")))
        self.input.write_text(text(body="Manually edited current wording.", evidence=CLAIM + "\n"))
        self.start(reference=old)
        self.assertIn("Manually edited", self.doc.entries["E1001"]["text"])
        self.assertIn("Same guide only", self.doc.decisions)
        self.assertEqual(self.inv["reference"]["sha256"], sha(old.read_bytes()))

    def test_reference_change_invalidates_next_and_finish(self):
        old = self.root / "reference.md"; old.write_text(text()); self.start(reference=old)
        old.write_text(old.read_text() + "changed")
        for action in (lambda: next_task(self.run, self.root / "p.md"), lambda: finish(self.run)):
            with self.assertRaises(ReadingError): action()

    def test_conflicting_same_id_evidence_is_not_silently_selected(self):
        old = self.root / "reference.md"; old.write_text(text(evidence="Different original."))
        with self.assertRaises(ReadingError): self.start(reference=old)

    def test_conflicting_decisions_do_not_override_current_manual_decisions(self):
        old = self.root / "reference.md"; old.write_text(text(decisions="Old scoped answer."))
        self.input.write_text(text(decisions="New scoped answer."))
        with self.assertRaises(ReadingError): self.start(reference=old)

    def test_earlier_removed_reference_requires_relocation_or_exclusion(self):
        old = self.root / "reference.md"; old.write_text(text())
        self.input.write_text(text().replace("[Source](#src-201)", ""))
        self.start(reference=old)
        self.assertEqual(self.inv["work"]["findings"][0]["code"], "prior_source_removed")
        with self.assertRaises(ReadingError): self.send([review(self.doc)])
        issue = dict(issue_id=self.inv["work"]["findings"][0]["issue_id"], status="resolved", reason="Unrelated source was deliberately excluded.", witnesses=[])
        change = dict(entry_id="E1001", source_id="src-201", action="exclude", target_entry_id=None, reason="Synthetic unrelated evidence, not a relocation.")
        self.send([review(self.doc)], [issue], [change])
        self.assertEqual(finish(self.run)["status"], "awaiting_publication_authorization")

    def test_move_requires_destination_even_when_quote_is_elsewhere(self):
        self.input.write_text(text(extra=entry("E1002", "Garden", "Seeds were ordered.")))
        self.start()
        replacement = self.doc.entries["E1001"]["text"].replace("[Source](#src-201)", "").replace(CLAIM, "This entry concerns a different booking.")
        first = review(self.doc, replacement=replacement, witnesses=[proof(self.doc, claim=CLAIM, relation="removes")])
        move = dict(entry_id="E1001", source_id="src-201", action="move", target_entry_id="E1002", reason="Move to the correct account.")
        with self.assertRaises(ReadingError): self.send([first, review(self.doc, "E1002")], changes=[move])
        second = review(self.doc, "E1002", self.doc.entries["E1002"]["text"] + CLAIM,
                        [proof(self.doc, claim=CLAIM)])
        self.assertEqual(self.send([first, second], changes=[move])["status"], "ready_for_check")

    def test_evidence_gap_requires_a_selected_excerpt_or_visible_limit(self):
        self.input.write_text(text(evidence="x" * 1800 + CLAIM))
        self.start(publish_to=self.output)
        issue = self.inv["work"]["findings"][0]
        self.assertEqual(issue["code"], "reading_evidence_gap")
        self.send([review(self.doc)])
        self.assertGreater(finish(self.run)["pending_findings"], 0)
        answer = self.issue_result(issue)
        with self.assertRaises(ReadingError): self.send(issues=[answer])
        self.send(issues=[answer], excerpts=[proof(self.doc)])
        self.assertEqual(finish(self.run)["status"], "published")
        self.assertFalse(Document.read(self.output).sources["src-201"]["complete"])

    def test_known_external_limit_can_be_accepted_but_is_not_called_resolved(self):
        self.input.write_text("# Synthetic collection\n" + entry())
        self.start(publish_to=self.output)
        issue = self.inv["work"]["findings"][0]
        outcome = dict(issue_id=issue["issue_id"], status="accepted_limit", witnesses=[],
                       reason="This noncritical entry remains an attributed report; its source is unavailable.")
        self.send([review(self.doc)], [outcome])
        result = finish(self.run)
        self.assertEqual(result["accepted_limits"], 1)
        self.assertIn('"accepted_limit": 1', self.output.read_text())
        self.assertIn("external reference", self.output.read_text())

    def test_discard_only_changes_the_named_draft_items(self):
        self.start(); self.send([review(self.doc)], excerpts=[proof(self.doc)])
        inv, doc, a = work_state(self.run)
        value = dict(run_id=inv["run_id"], base_answers_sha256=sha(encoded(a)),
                     reviews=[], issue_resolutions=[], source_changes=[], excerpts=[], discard={"excerpts": ["src-201"]})
        self.send(envelope=value)
        final = work_state(self.run)[2]
        self.assertEqual(len(final["reviews"]), 1)
        self.assertEqual(final["excerpts"], [])

    def test_an_original_reference_can_restore_an_excerpt_without_dropping_it(self):
        original = text(evidence="prefix " + CLAIM + " suffix")
        doc = Document.from_text(original)
        published = r.render(doc, doc.entries, {}, {"src-201": CLAIM}, 0)[0]
        self.input.write_text(published)
        reference = self.root / "reference.md"; reference.write_text(original)
        self.start(reference=reference)
        evidence, access, _, _, _ = evidence_plan(self.doc, self.doc.entries, {}, 0)
        self.assertEqual(evidence["src-201"], CLAIM)
        self.assertEqual(access["src-201"], "selected_exact_excerpt")
        self.assertEqual(self.doc.sources["src-201"]["text"], "prefix " + CLAIM + " suffix")

    def test_supporting_answer_change_invalidates_the_entry_basis(self):
        original = text(body=CLAIM + " [Correction](#cor1001)") + '\n<a id="cor1001"></a>\n[Answer](#src-901-q01)\n<a id="src-901-q01"></a>\nFriday only.\n'
        before = Document.from_text(original)
        after = Document.from_text(original.replace("Friday only.", "Saturday instead."))
        self.assertNotEqual(before.basis("E1001"), after.basis("E1001"))

    def test_preauthorization_cannot_target_run_bookkeeping(self):
        with self.assertRaises(ReadingError): self.start(publish_to=self.run / "answers.json")
        self.assertFalse(self.run.exists())

    def test_source_and_decision_round_trip_includes_dependency_navigation(self):
        original = text(body=CLAIM + " [Correction](#cor1001)", decisions="A finite recorded decision.")
        original += '\n<a id="cor1001"></a>\n[Answer](#src-901-q01)\n<a id="src-901-q01"></a>\nFriday only.\n'
        doc = Document.from_text(original)
        first = r.render(doc, doc.entries, {}, {}, 1600, strict=True)[0]
        d1 = Document.from_text(first)
        second = r.render(d1, d1.entries, {}, {}, 1600, strict=True)[0]
        d2 = Document.from_text(second)
        self.assertEqual(d1.decisions, d2.decisions)
        self.assertEqual({k: v["sha256"] for k, v in d1.sources.items()}, {k: v["sha256"] for k, v in d2.sources.items()})

    def test_long_critical_source_has_an_actionable_evidence_handoff(self):
        self.input.write_text(text(body=CLAIM + " [Correction](#cor1001)")
            + '\n<a id="cor1001"></a>\n[Answer](#src-901-q01)\n<a id="src-901-q01"></a>\n'
            + "Friday only. " + "x" * 21000)
        self.start(publish_to=self.output); self.send([review(self.doc)])
        result = finish(self.run)
        self.assertEqual(result["status"], "needs_evidence")
        self.assertEqual(result["critical_sources_needing_evidence"], ["src-901-q01"])
        self.send(excerpts=[proof(self.doc, "Friday only.", "src-901-q01")])
        self.assertEqual(finish(self.run)["status"], "published")

    def test_reused_entry_ids_alone_cannot_mix_two_collections(self):
        reference = self.root / "other-collection.md"
        reference.write_text(text(body="Entirely different collection.", evidence="Unrelated evidence.").replace("src-201", "src-702"))
        with self.assertRaises(ReadingError): self.start(reference=reference)

    def test_actor_cannot_be_relabelled_owner(self):
        self.start(); bad = deepcopy(self.answers); bad["reviewer_role"] = "owner"
        with self.assertRaises(ReadingError): r.validate_reviews(bad, self.inv, self.doc, False)

    def test_unreferenced_excerpt_cannot_poison_checkpoint(self):
        self.input.write_text(text(extra=entry("E1002", "Unrelated", "A separate record."))
            + '\n<a id="src-702"></a>\nUnrelated source text.\n')
        self.start(); before = (self.run / "answers.json").read_bytes()
        unrelated = proof(self.doc, value="Unrelated source text.", sid="src-702")
        with self.assertRaises(ReadingError): self.send(excerpts=[unrelated])
        self.assertEqual((self.run / "answers.json").read_bytes(), before)
        self.assertEqual(next_task(self.run, self.root / "next.md")["status"], "task_written")

    def test_checkpoint_failure_is_atomic(self):
        self.start(); before = (self.run / "answers.json").read_bytes()
        with patch("conversation_archive.reading_work.os.replace", side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError): self.send([review(self.doc)])
        self.assertEqual(before, (self.run / "answers.json").read_bytes())
        self.assertFalse(list(self.run.glob(".work-*")))

    def test_manual_output_edit_is_never_overwritten(self):
        self.start(publish_to=self.output); self.send([review(self.doc)]); finish(self.run)
        self.output.write_text("Manual output edit.")
        with self.assertRaises(ReadingError): finish(self.run)
        self.assertEqual(self.output.read_text(), "Manual output edit.")

    def test_cli_exposes_the_real_autonomous_workflow(self):
        capture = io.StringIO()
        with redirect_stdout(capture):
            result = r.main(["prepare", "--input", str(self.input), "--run", str(self.run),
                "--autonomous", "--scope-note", "Only this synthetic collection."])
        self.assertEqual(result, 0)
        self.assertTrue((self.run / "answers.json").exists())
        self.assertNotIn(CLAIM, capture.getvalue())


if __name__ == "__main__":
    unittest.main()
