"""Invented data only. No personal archive, model calls, or live Notes access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import snapshot_review as review
from conversation_archive.review_html import render, render_preview


def records_fixture():
    records = {name: [] for name in review.CORE_TABLES}
    for number, text in enumerate(("Sample event: quantity 4.\n", "Sample event: quantity 7.\n"), 1):
        eid = f"E{number:04}"
        records["entries"].append(dict(entry_id=eid, title=f"Invented source {number}", raw_markdown=text,
            source_sha256=hashlib.sha256(b"invented").hexdigest(), source_start=0, source_end=len(text)))
        records["mentions"].append(dict(mention_id=f"M{number}", entry_id=eid, kind="event", label="Sample",
            family="sample", start=0, end=6, quote="Sample", status="unresolved", entity_id=None))
    records["unresolved_questions"].append(dict(question_id="Q-sample", kind="event", family="sample",
        prompt="Do these mentions identify the same event?", authority="unresolved_candidate",
        evidence_json=json.dumps([dict(mention_id=f"M{n}", entry_id=f"E{n:04}") for n in (1, 2)])))
    return records


def case_fixture(kind="conflict", relation="precedes", reverse=False):
    texts = {e["entry_id"]: e["raw_markdown"] for e in records_fixture()["entries"]}
    case = dict(kind=kind, title="Invented comparison", prompt="Do these sources disagree about the same event?",
        reason="Synthetic comparison only; the event match remains a proposal.", depends_on=[],
        evidence=[dict(entry_id=eid, start=0, end=len(text), quote=text) for eid, text in texts.items()])
    if kind == "relationship":
        case.update(relation=relation, source_entry_id="E0002" if reverse else "E0001",
                    target_entry_id="E0001" if reverse else "E0002", prompt="Does this directed relation hold?")
    return case


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def hashes(root):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}


class ReviewPureTests(unittest.TestCase):
    def setUp(self):
        self.records = records_fixture()
        self.entries = {e["entry_id"]: e for e in self.records["entries"]}

    def test_actual_saved_identity_question_resolves_mention_references(self):
        queue, blocked, _ = review.queue_from_records(self.records)
        self.assertFalse(blocked)
        self.assertEqual(queue[0]["case"]["evidence"][0]["quote"], "Sample")
        self.assertEqual(queue[0]["choices"], ["defer", "reopen"])

    def test_conflicts_rank_before_relations_and_optional_identity(self):
        queue, _, _ = review.queue_from_records(self.records,
            [case_fixture("relationship"), case_fixture()])
        self.assertEqual([q["case"]["kind"] for q in queue], ["conflict", "relationship", "identity"])

    def test_wrong_quote_or_hash_is_rejected(self):
        case = case_fixture()
        case["evidence"][0]["quote"] = "Not in evidence"
        with self.assertRaises(review.ReviewError): review.normalize_case(case, self.entries)
        case = review.normalize_case(case_fixture(), self.entries)
        case["evidence"][0]["entry_sha256"] = "wrong"
        with self.assertRaises(review.ReviewError): review.normalize_case(case, self.entries)

    def test_relation_requires_both_endpoints_and_supported_type(self):
        for relation in ("unsupported", "precedes"):
            case = case_fixture("relationship", relation)
            case["evidence"] = case["evidence"][:1]
            with self.assertRaises(review.ReviewError): review.normalize_case(case, self.entries)

    def test_one_issue_can_contain_multiple_source_occurrences(self):
        case = case_fixture()
        case["evidence"].append(dict(entry_id="E0001", start=0, end=6, quote="Sample"))
        queue, _, _ = review.queue_from_records(self.records, [case])
        self.assertEqual(sum(q["case"]["kind"] == "conflict" for q in queue), 1)
        self.assertEqual(len(queue[0]["case"]["evidence"]), 3)

    def test_duplicate_evidence_is_not_independent_confirmation(self):
        case = case_fixture()
        case["evidence"].append(case["evidence"][0].copy())
        with self.assertRaises(review.ReviewError): review.normalize_case(case, self.entries)

    def test_invalid_supplied_case_is_not_silently_dropped(self):
        case = case_fixture()
        case["evidence"] = []
        with self.assertRaises(review.ReviewError): review.queue_from_records(self.records, [case])

    def test_strict_json_and_bounds(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input.json"
            for text in ('{"a":1,"a":2}', '{"a":NaN}'):
                p.write_text(text)
                with self.assertRaises(review.ReviewError): review.read_json(p)
            p.write_text('{}')
            with self.assertRaises(review.ReviewError): review.read_json(p, limit=1)

    def test_html_payload_is_inert_and_network_is_disabled(self):
        hostile = '</script><img src="https://invalid.example/x" onerror="alert(1)">'
        document = render({"x": hostile})
        self.assertNotIn(hostile, document)
        self.assertIn('\\u003c/script', document)
        self.assertIn('connect-src &#x27;none&#x27;', document)
        self.assertNotIn('localStorage.', document)
        self.assertNotIn('.innerHTML', document)
        self.assertIn('textContent', document)

    def test_preview_escapes_notes(self):
        doc = render_preview(dict(basis_snapshot_id="invented", impact=[dict(title="<svg>",
            kind="conflict", choice="disagree", note="<script>alert(1)</script>",
            withdrawn_rules=[], evidence=[])]))
        self.assertIn('&lt;script&gt;', doc)
        self.assertNotIn('<script>alert(1)', doc)


@unittest.skipUnless(importlib.util.find_spec("conversation_archive.machine_archive"),
                     "Full-repository integration runs in the repository test suite")
class ReviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        from conversation_archive.structured_archive import connect, create_schema
        from conversation_archive import machine_archive as ma
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        db = connect(self.root / "input.sqlite3")
        create_schema(db)
        records = records_fixture()
        db.execute("INSERT INTO metadata VALUES (?,?)", ("master_sha256", records["entries"][0]["source_sha256"]))
        for table in review.CORE_TABLES:
            cols = [x[1] for x in db.execute(f"PRAGMA table_info({table})")]
            db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in cols)})",
                           [tuple(row[k] for k in cols) for row in records[table]])
        db.commit(); db.close()
        ma.snapshot(self.root / "input.sqlite3", self.source, "synthetic-1")
        self.before = hashes(self.source)
        self.counter = 0

    def session(self, source=None, cases=None):
        source = source or self.source
        self.counter += 1
        path = self.root / f"session-{self.counter}"
        bundle = None
        if cases is not None:
            bundle = write(self.root / f"cases-{self.counter}.json", dict(protocol=review.PROTOCOL,
                basis_snapshot_id=review.read_snapshot(source)[0]["snapshot_id"], cases=cases))
        review.prepare(source, path, bundle)
        return path / "session.json", review.read_json(path / "session.json")

    def answers(self, session, selected):
        responses = []
        for question, choice in selected:
            responses.append(dict(question_id=question["question_id"], choice=choice, note="Invented reviewer answer.",
                previous_rule_id=question["current"]["rule_id"] if question["current"] else None))
        return write(self.root / f"answers-{self.counter}.json", dict(protocol=review.PROTOCOL,
            session_id=session["session_id"], basis_snapshot_id=session["basis_snapshot_id"],
            actor="Synthetic reviewer", answers=responses))

    def apply_answers(self, source, session_path, answers):
        preview_dir = self.root / f"preview-{self.counter}"
        output = self.root / f"successor-{self.counter}"
        review.preview(source, session_path, answers, preview_dir)
        result = review.apply(source, session_path, answers, preview_dir / "preview.json", output,
                              f"synthetic-{self.counter + 1}", True)
        self.assertEqual(result["status"], "applied")
        return output, preview_dir / "preview.json"

    def test_prepare_is_read_only_and_not_a_discovery_claim(self):
        _, data = self.session(cases=[case_fixture()])
        self.assertEqual(data["coverage"]["conflict_cases"], 1)
        self.assertFalse(data["coverage"]["automatic_conflict_discovery"])
        self.assertEqual(hashes(self.source), self.before)

    def test_conflict_decision_is_not_a_medical_or_graph_assertion(self):
        path, data = self.session(cases=[case_fixture()])
        answers = self.answers(data, [(data["questions"][0], "disagree")])
        out, _ = self.apply_answers(self.source, path, answers)
        _, records, _ = review.read_snapshot(out)
        self.assertFalse(records["relationships"])
        self.assertEqual(len(records["correction_events"]), 1)
        self.assertEqual(hashes(self.source), self.before)

    def test_relation_update_rebuilds_and_replays_without_duplicate_decisions(self):
        from conversation_archive.machine_archive import build_sqlite
        path, data = self.session(cases=[case_fixture("relationship")])
        answers = self.answers(data, [(data["questions"][0], "confirm")])
        out, receipt = self.apply_answers(self.source, path, answers)
        self.assertEqual(build_sqlite(out, self.root / "rebuilt.sqlite3")["status"], "passed")
        original_hashes = hashes(out)
        result = review.apply(self.source, path, answers, receipt, out, "ignored", True)
        self.assertEqual(result["status"], "already_applied")
        result = review.apply(out, path, answers, receipt, self.root / "not-created", "ignored", True)
        self.assertEqual(result["status"], "already_applied")
        self.assertFalse((self.root / "not-created").exists())
        self.assertEqual(hashes(out), original_hashes)

    def test_persistent_deferral_then_explicit_reopen(self):
        path, data = self.session(cases=[case_fixture("relationship")])
        out, _ = self.apply_answers(self.source, path, self.answers(data, [(data["questions"][0], "defer")]))
        path2, data2 = self.session(out)
        q = next(q for q in data2["questions"] if q["case"]["kind"] == "relationship")
        self.assertEqual(q["current"]["choice"], "defer")
        out2, _ = self.apply_answers(out, path2, self.answers(data2, [(q, "reopen")]))
        _, data3 = self.session(out2)
        q3 = next(q for q in data3["questions"] if q["case"]["kind"] == "relationship")
        self.assertIsNone(q3["current"])
        self.assertTrue(any(not item["active"] for item in data3["history"]))

    def test_replacing_confirm_with_reject_preserves_old_answer_and_evidence(self):
        path, data = self.session(cases=[case_fixture("relationship")])
        out, _ = self.apply_answers(self.source, path, self.answers(data, [(data["questions"][0], "confirm")]))
        out_hashes = hashes(out)
        path2, data2 = self.session(out)
        q = next(q for q in data2["questions"] if q["case"]["kind"] == "relationship")
        out2, _ = self.apply_answers(out, path2, self.answers(data2, [(q, "reject")]))
        _, records, _ = review.read_snapshot(out2)
        self.assertEqual(records["relationships"][0]["status"], "rejected")
        self.assertEqual(len(records["correction_events"]), 2)
        self.assertEqual(hashes(out), out_hashes)
        self.assertEqual(hashes(self.source), self.before)

    def test_checked_preview_and_explicit_application_are_required(self):
        path, data = self.session(cases=[case_fixture()])
        answers = self.answers(data, [(data["questions"][0], "different_events")])
        receipt = self.root / "missing.json"
        with self.assertRaises(review.ReviewError):
            review.apply(self.source, path, answers, receipt, self.root / "bad", "2", False)
        with self.assertRaises(review.ReviewError):
            review.apply(self.source, path, answers, receipt, self.root / "bad", "2", True)
        self.assertFalse((self.root / "bad").exists())

    def test_stale_session_rejected_but_user_answer_retained(self):
        path, data = self.session(cases=[case_fixture(), case_fixture("relationship")])
        first = self.answers(data, [(data["questions"][0], "disagree")])
        out, _ = self.apply_answers(self.source, path, first)
        another = self.answers(data, [(data["questions"][1], "confirm")])
        with self.assertRaises(review.ReviewError): review.plan(out, path, another)
        self.assertTrue(another.exists())

    def test_duplicate_unknown_blank_and_invalid_answers_fail(self):
        path, data = self.session(cases=[case_fixture()])
        answers = self.answers(data, [(data["questions"][0], "disagree")])
        original = review.read_json(answers)
        variants = [dict(original, answers=[])]
        variants.append(dict(original, answers=original["answers"] * 2))
        variants.append(dict(original, answers=[dict(original["answers"][0], question_id="unknown")]))
        variants.append(dict(original, answers=[dict(original["answers"][0], choice="invented-choice")]))
        for invalid in variants:
            write(answers, invalid)
            with self.assertRaises(review.ReviewError): review.plan(self.source, path, answers)
        self.assertEqual(hashes(self.source), self.before)

    def test_changing_displayed_metadata_even_with_rehashed_session_is_rejected(self):
        path, data = self.session(cases=[case_fixture()])
        data["metadata"].append(dict(entry_id="E0001", field="event_period", value="invented date"))
        data["session_id"] = "RS-" + review.digest({k: v for k, v in data.items() if k != "session_id"})
        write(path, data)
        answers = self.answers(data, [(data["questions"][0], "disagree")])
        with self.assertRaises(review.ReviewError): review.plan(self.source, path, answers)

    def test_partial_answer_does_not_resolve_unanswered_questions(self):
        path, data = self.session(cases=[case_fixture(), case_fixture("relationship")])
        out, _ = self.apply_answers(self.source, path, self.answers(data, [(data["questions"][0], "disagree")]))
        _, records, _ = review.read_snapshot(out)
        self.assertEqual(len(records["unresolved_questions"]), 1)
        self.assertFalse(records["relationships"])

    def test_chronology_cycle_rejected_before_writing(self):
        path, data = self.session(cases=[case_fixture("relationship"), case_fixture("relationship", reverse=True)])
        answers = self.answers(data, [(q, "confirm") for q in data["questions"] if q["case"]["kind"] == "relationship"])
        with self.assertRaises(review.ReviewError): review.plan(self.source, path, answers)
        self.assertEqual(hashes(self.source), self.before)

    def test_interruption_leaves_source_unchanged_and_no_published_successor(self):
        path, data = self.session(cases=[case_fixture()])
        answers = self.answers(data, [(data["questions"][0], "disagree")])
        review.preview(self.source, path, answers, self.root / "preview")
        with patch("conversation_archive.machine_archive.snapshot", side_effect=RuntimeError("synthetic interruption")):
            with self.assertRaises(RuntimeError):
                review.apply(self.source, path, answers, self.root / "preview" / "preview.json",
                             self.root / "unpublished", "2", True)
        self.assertFalse((self.root / "unpublished").exists())
        self.assertEqual(hashes(self.source), self.before)

    def test_revocation_invalidates_dependents_but_keeps_independent_support(self):
        path, data = self.session(cases=[case_fixture("relationship")])
        out, _ = self.apply_answers(self.source, path, self.answers(data, [(data["questions"][0], "confirm")]))
        _, records, _ = review.read_snapshot(out)
        rule = next(r["rule_id"] for r in records["correction_rules"] if r["operation"] == "review_answer")
        dependent = case_fixture("relationship", "responds_to"); dependent["depends_on"] = [rule]
        independent = case_fixture("relationship", "revises")
        path2, data2 = self.session(out, [dependent, independent])
        out2, _ = self.apply_answers(out, path2, self.answers(data2,
            [(q, "confirm") for q in data2["questions"] if q["case"].get("relation") in {"responds_to", "revises"}]))
        path3, data3 = self.session(out2)
        original = next(q for q in data3["questions"] if q["case"].get("relation") == "precedes")
        out3, _ = self.apply_answers(out2, path3, self.answers(data3, [(original, "reopen")]))
        _, new_records, _ = review.read_snapshot(out3)
        self.assertEqual([r["relation"] for r in new_records["relationships"]], ["revises"])
        _, data4 = self.session(out3)
        blocked = next(q for q in data4["questions"] if q["case"].get("relation") == "responds_to")
        self.assertTrue(blocked["blocked"])

    def test_missing_manifest_member_cannot_bypass_hash_check(self):
        manifest = review.read_json(self.source / "manifest.json")
        del manifest["files"]["entries.jsonl"]
        write(self.source / "manifest.json", manifest)
        with self.assertRaises(review.ReviewError): review.read_snapshot(self.source)


if __name__ == "__main__":
    unittest.main()
