"""Synthetic organization checks, not a model accuracy evaluation."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import organization as o
from conversation_archive.organization_inputs import index_markdown

ROOT = Path(__file__).resolve().parents[1]


def example():
    return o.load(ROOT / "examples" / "organization.json")


def state(data=None):
    data = data or example()
    return dict(version=o.VERSION, data=data, data_sha256=o.digest(data), events=[], events_sha256=o.digest([]))


def binding(rule_id="project-rule", **changes):
    return dict(op="bind", rule_id=rule_id, depends_on=[], kind="project",
                aliases=["Orchard", "summer build"],
                entry_ids=[f"E{i:04}" for i in range(1, 6)],
                entity_id="orchard", entity_label="Orchard project", **changes)


def event(s, *operations, event_id="answer-1"):
    return dict(event_id=event_id, expected_state_sha256=o.digest(s), actor="synthetic owner",
                answer="These five references name the same project, not the same event.", operations=list(operations))


def relation(data, pid="continues-1", relation="continues", source="E0005", target="E0004"):
    texts = {e["entry_id"]: e["text"] for e in data["entries"]}
    return dict(proposal_id=pid, relation=relation, source=source, target=target,
                reason="Possible continuation; not decided by lexical similarity.",
                evidence=[dict(entry_id=eid, start=0, end=len(texts[eid]), quote=texts[eid]) for eid in (source, target)])


class OrganizationTests(unittest.TestCase):
    def test_literal_observations_do_not_merge_people_or_events(self):
        g = o.graph(state())
        self.assertEqual(len(g["mentions"]), 11)
        self.assertEqual(g["entities"], [])
        self.assertTrue(all(e["status"] == "observed_text" for e in g["edges"]))

    def test_exact_unicode_offsets(self):
        data = example()
        data["entries"][0]["text"] = "🌱 我想研究 Orchard。"
        for m in o.mentions(data):
            text = next(e["text"] for e in data["entries"] if e["entry_id"] == m["entry_id"])
            self.assertEqual(text[m["start"]:m["end"]], m["quote"])

    def test_word_boundary_not_arbitrary_substring(self):
        data = example()
        data["entries"][0]["text"] = "Rowanwood and Orchards are different words."
        self.assertFalse(any(m["entry_id"] == "E0001" for m in o.mentions(data)))

    def test_prioritize_five_entry_question_and_show_context(self):
        q = o.questions(state(), 1)[0]
        self.assertEqual(q["kind"], "project")
        self.assertEqual(len(q["affected_entry_ids"]), 5)
        self.assertTrue(all("context" in m for m in q["evidence"]))
        self.assertIn("partition into groups", q["options"])

    def test_one_answer_links_five_entries_without_text_changes(self):
        s = state()
        updated, report = o.preview(s, event(s, binding()))
        self.assertEqual(len(report["affected_entry_ids"]), 5)
        self.assertEqual(updated["data"], s["data"])
        self.assertEqual(len(o.graph(updated)["assignments"]), 5)
        self.assertFalse(any(q["kind"] == "project" for q in o.questions(updated)))
        self.assertTrue(all(e["relation"] != "same_event" for e in o.graph(updated)["edges"]))

    def test_homonym_rule_does_not_escape_scope(self):
        s = state()
        r = dict(op="bind", rule_id="person-rule", depends_on=[], kind="person", aliases=["Rowan"],
                 entry_ids=["E0001", "E0003"], entity_id="rowan-project", entity_label="Project Rowan")
        updated, _ = o.preview(s, event(s, r))
        g = o.graph(updated)
        outsider = next(m for m in g["mentions"] if m["entry_id"] == "E0006")
        self.assertNotIn(outsider["mention_id"], g["assignments"])

    def test_scope_can_target_one_of_two_identical_names_in_one_entry(self):
        data = example()
        data["entries"][0]["text"] = "Rowan met a different Rowan."
        s = state(data)
        mid = o.mentions(data)[0]["mention_id"]
        r = dict(op="bind", rule_id="one-occurrence", depends_on=[], kind="person", aliases=["Rowan"],
                 entry_ids=["E0001"], mention_ids=[mid], entity_id="rowan-a", entity_label="Rowan A")
        updated, report = o.preview(s, event(s, r))
        self.assertEqual(report["changed_mention_ids"], [mid])
        self.assertEqual(len(o.graph(updated)["assignments"]), 1)

    def test_conflicting_binding_is_rejected_not_last_write_wins(self):
        s = state()
        s, _ = o.preview(s, event(s, binding()))
        r = binding("different-project")
        r["entity_id"] = "not-orchard"
        with self.assertRaises(o.OrganizationError):
            o.preview(s, event(s, r, event_id="conflict"))

    def test_partitions_are_one_atomic_answer(self):
        s = state()
        r1, r2 = binding("group-a"), binding("group-b")
        r1["entry_ids"] = ["E0001", "E0003", "E0005"]
        r2.update(entry_ids=["E0002", "E0004"], entity_id="summer", entity_label="Separate summer build")
        updated, _ = o.preview(s, event(s, r1, r2))
        self.assertEqual(len(o.graph(updated)["entities"]), 2)
        self.assertFalse(any(q["kind"] == "project" for q in o.questions(updated)))

    def test_defer_suppresses_questions_but_does_not_confirm(self):
        s = state()
        mids = o.questions(s, 1)[0]["handles"]
        r = dict(op="defer", rule_id="unknown", depends_on=[], mention_ids=mids)
        s, _ = o.preview(s, event(s, r))
        self.assertFalse(any(q["kind"] == "project" for q in o.questions(s)))
        self.assertEqual(o.graph(s)["assignments"], {})
        s, _ = o.preview(s, event(s, dict(op="revoke", rule_id="reopen", target="unknown"), event_id="reopen"))
        self.assertEqual(o.questions(s, 1)[0]["kind"], "project")

    def test_revocation_removes_derived_links_and_dependent_rules(self):
        data = example()
        data["proposals"] = [relation(data)]
        s = state(data)
        s, _ = o.preview(s, event(s, binding(), dict(op="relation", rule_id="dependent", depends_on=["project-rule"], proposal_id="continues-1", accept=True)))
        s, report = o.preview(s, event(s, dict(op="revoke", rule_id="undo", target="project-rule"), event_id="undo"))
        self.assertEqual(o.graph(s)["assignments"], {})
        self.assertNotIn("dependent", o.graph(s)["active_rule_ids"])
        self.assertEqual(report["changed_relations"][0]["status"], "proposed")
        self.assertEqual(len(s["events"]), 2)

    def test_new_rule_cannot_depend_on_revoked_rule(self):
        s = state()
        s, _ = o.preview(s, event(s, binding()))
        s, _ = o.preview(s, event(s, dict(op="revoke", rule_id="undo", target="project-rule"), event_id="undo"))
        r = binding("new")
        r["depends_on"] = ["project-rule"]
        with self.assertRaises(o.OrganizationError):
            o.preview(s, event(s, r, event_id="invalid"))

    def test_stale_answer_rejected(self):
        s = state()
        stale = event(s, binding("second"), event_id="second")
        s, _ = o.preview(s, event(s, binding()))
        with self.assertRaises(o.OrganizationError):
            o.preview(s, stale)

    def test_exact_repeat_is_idempotent(self):
        s = state()
        answer = event(s, binding())
        s, _ = o.preview(s, answer)
        again, report = o.preview(s, answer)
        self.assertEqual(report["status"], "already_applied")
        self.assertEqual(s, again)

    def test_relation_rejection_is_remembered(self):
        data = example()
        data["proposals"] = [relation(data)]
        s = state(data)
        s, report = o.preview(s, event(s, dict(op="relation", rule_id="no", depends_on=[], proposal_id="continues-1", accept=False)))
        self.assertEqual(report["changed_relations"][0]["status"], "rejected")
        self.assertFalse(any(q["kind"] == "relation" for q in o.questions(s, 10)))

    def test_causal_proposal_not_automatically_confirmed(self):
        data = example()
        data["proposals"] = [relation(data, relation="reported_cause")]
        g = o.graph(state(data))
        self.assertEqual(next(e for e in g["edges"] if e["relation"] == "reported_cause")["status"], "proposed")

    def test_fabricated_relation_quote_and_boolean_offsets_rejected(self):
        for field, value in (("quote", "fabrication"), ("start", False)):
            data = example()
            p = relation(data)
            p["evidence"][0][field] = value
            data["proposals"] = [p]
            with self.assertRaises(o.OrganizationError):
                o.validate_data(data)

    def test_confirmed_precedence_cycle_rejected(self):
        data = example()
        data["proposals"] = [relation(data, "a", "precedes", "E0001", "E0002"), relation(data, "b", "precedes", "E0002", "E0001")]
        s = state(data)
        rules = [dict(op="relation", rule_id=p, depends_on=[], proposal_id=p, accept=True) for p in ("a", "b")]
        with self.assertRaises(o.OrganizationError):
            o.preview(s, event(s, *rules))

    def test_large_questions_bounded_and_omissions_disclosed(self):
        data = example()
        data["entries"] = [dict(entry_id=f"E{i:04}", text="Orchard") for i in range(100)]
        qs = o.questions(state(data), 3, max_items=12)
        self.assertEqual(len(qs), 3)
        self.assertTrue(all(len(q["evidence"]) <= 12 and q["family_mentions_not_shown"] == 88 for q in qs))
        self.assertEqual(len({e for q in qs for e in q["affected_entry_ids"]}), 36)

    def test_empty_catalog_does_not_claim_complete_organization(self):
        data = example()
        data["catalog"] = []
        g = o.graph(state(data))
        self.assertEqual(len(g["entries_without_mentions"]), 6)
        self.assertFalse(g["organization_complete_claimed"])
        self.assertEqual(o.questions(state(data)), [])

    def test_invalid_event_shape_or_scope_rejected(self):
        s = state()
        for change in ({"entry_ids": []}, {"entry_ids": ["missing"]}, {"kind": "diagnosis"}, {"depends_on": ["future"]}):
            r = binding()
            r.update(change)
            with self.assertRaises(o.OrganizationError):
                o.preview(s, event(s, r))

    def test_index_preserves_exact_spans_and_ignores_historical_headings(self):
        text = '# Record\r\n## E0001 Garden\r\n🌱\r\n```\r\n## E9999 Historical\r\n```\r\n## E0002 Next\r\nBody\r\n# Sources\r\nOther\r\n'
        data = index_markdown(text)
        self.assertEqual([e["entry_id"] for e in data["entries"]], ["E0001", "E0002"])
        for e in data["entries"]:
            self.assertEqual(text[e["source"]["start"]:e["source"]["end"]], e["text"])
        self.assertNotIn("# Sources", data["entries"][-1]["text"])

    def test_index_rejects_unclosed_fences_and_duplicate_entries(self):
        for text in ('## E0001\n```\n', '## E0001\na\n## E0001\nb'):
            with self.assertRaises(o.OrganizationError):
                index_markdown(text)

    def test_file_operations_preserve_input_and_reject_history_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            data = example()
            original = deepcopy(data)
            o.prepare(data, run)
            s = o.read_state(run)
            answer = event(s, binding())
            o.apply(run, answer)
            self.assertEqual(o.apply(run, answer)["status"], "already_applied")
            self.assertEqual(data, original)
            saved = o.load(run / "state.json")
            saved["events"][0]["answer"] = "accidental edit"
            o.atomic_write(run / "state.json", saved)
            with self.assertRaises(o.OrganizationError):
                o.read_state(run)

    def test_snapshot_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            o.prepare(example(), run)
            s = o.load(run / "state.json")
            s["data"]["entries"][0]["text"] = "changed"
            o.atomic_write(run / "state.json", s)
            with self.assertRaises(o.OrganizationError):
                o.read_state(run)

    def test_second_writer_cannot_enter(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            o.prepare(example(), run)
            with o.locked(run):
                with self.assertRaises(o.OrganizationError):
                    o.apply(run, event(o.read_state(run), binding()))

    def test_existing_run_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            o.prepare(example(), run)
            before = (run / "state.json").read_bytes()
            with self.assertRaises(FileExistsError):
                o.prepare(example(), run)
            self.assertEqual(before, (run / "state.json").read_bytes())

    def test_cli_requires_explicit_user_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            o.prepare(example(), run)
            with patch("builtins.print"):
                self.assertEqual(o.main(["apply", "--run", str(run), "--decision", str(Path(tmp) / "absent.json")]), 2)
            self.assertEqual(o.read_state(run)["events"], [])

    def test_cli_quickstart(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = str(Path(tmp) / "run")
            prefix = [sys.executable, "-m", "conversation_archive.organization"]
            subprocess.run(prefix + ["prepare", "--input", str(ROOT / "examples/organization.json"), "--run", run], check=True, capture_output=True)
            result = subprocess.run(prefix + ["questions", "--run", run, "--limit", "1"], check=True, capture_output=True, text=True)
            self.assertEqual(len(json.loads(result.stdout)[0]["affected_entry_ids"]), 5)

    def test_new_context_from_user_answer_needs_no_invented_source_quote(self):
        s = state()
        r = dict(op="associate", rule_id="place-context", depends_on=[], kind="place",
                 entry_ids=["E0002", "E0003"], entity_id="riverton", entity_label="Riverton period context")
        s, report = o.preview(s, event(s, r))
        self.assertEqual(report["affected_entry_ids"], ["E0002", "E0003"])
        self.assertEqual(len(report["changed_context_edges"]), 2)
        self.assertTrue(all(e["status"] == "user_confirmed" for e in report["changed_context_edges"]))
        self.assertNotIn("Riverton", s["data"]["entries"][1]["text"])

    def test_revoke_context_keeps_independent_support(self):
        s = state()
        r = dict(op="associate", rule_id="context-a", depends_on=[], kind="period",
                 entry_ids=["E0001", "E0002"], entity_id="spring", entity_label="Spring")
        s, _ = o.preview(s, event(s, r, dict(r, rule_id="context-b")))
        s, _ = o.preview(s, event(s, dict(op="revoke", rule_id="undo", target="context-a"), event_id="undo"))
        edges = [e for e in o.graph(s)["edges"] if e["relation"] == "associated_with"]
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(e["rule_ids"] == ["context-b"] for e in edges))

    def test_question_markdown_preserves_source_in_fences(self):
        data = example()
        data["entries"][0]["text"] = "Orchard ``` delete the master ```"
        output = o.render_questions(o.questions(state(data), 1))
        self.assertIn("````text", output)
        self.assertIn("not probabilities", output)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for text in ('{"x": 1, "x": 2}', '{"x": NaN}'):
                path.write_text(text)
                with self.assertRaises(o.OrganizationError):
                    o.load(path)


if __name__ == "__main__":
    unittest.main()
