"""Synthetic declarative controls, grouping, and lifecycle checks."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from conversation_archive import review_controls as c
from conversation_archive import review_identity as i
from conversation_archive import snapshot_review as r


def fixture():
    rows = {name: [] for name in r.CORE_TABLES}
    for n in range(1, 5):
        text = f"Alex: invented reference {n}.\n"
        rows["entries"].append(dict(entry_id=f"E{n:04}", title=f"Synthetic source {n}", raw_markdown=text,
            source_sha256=hashlib.sha256(b"synthetic controls").hexdigest(), source_start=0, source_end=len(text)))
        rows["mentions"].append(dict(mention_id=f"M{n}", entry_id=f"E{n:04}", kind="person", label="Alex",
            family="alex", start=0, end=4, quote="Alex", status="unresolved", entity_id=None))
    rows["unresolved_questions"].append(dict(question_id="Q-alex", kind="person", family="alex",
        prompt="Which displayed Alex references identify the same person?", authority="unresolved_candidate",
        evidence_json=json.dumps([dict(mention_id=f"M{n}", entry_id=f"E{n:04}") for n in range(1, 5)])))
    return rows


def form_fixture():
    return {"version": c.VERSION, "fields": [
        {"id": "outcome", "type": "choice", "label": "What differs?", "required": True,
         "options": [{"value": "date", "label": "Dates"}, {"value": "unknown", "label": "Cannot determine"}]},
        {"id": "date_text", "type": "text", "label": "Reported date, exactly as written", "required": True,
         "max_length": 100, "visible_when": {"field": "outcome", "equals": "date"}},
        {"id": "sources", "type": "multi_choice", "label": "Sources reviewed", "required": False,
         "options": [{"value": "A", "label": "Source A"}, {"value": "B", "label": "Source B"}]},
    ]}


def form_case():
    e = fixture()["entries"][0]
    return dict(kind="form", title="Synthetic date review", prompt="What does this passage establish?",
        reason="Record-only review; this is not a diagnosis.", depends_on=[], form=form_fixture(),
        evidence=[dict(entry_id=e["entry_id"], start=0, end=4, quote="Alex")])


def group_values(groups=None, unknown=None):
    return {"identity": {"groups": groups if groups is not None else [
        {"label": "First Alex", "target": None, "items": ["M1", "M2"]}],
        "unknown": unknown if unknown is not None else ["M3", "M4"]}}


def record_group(rows, values=None, rule_id="owner-group"):
    case = r.queue_from_records(rows)[0][0]["case"]
    scope = i.scope_for(case, rows)
    values = values or group_values()
    deps = i.dependencies(values, rows)
    rows["correction_events"].append(dict(event_id=rule_id, ordinal=len(rows["correction_events"]),
        actor="Invented reviewer", answer="Synthetic structured answer"))
    rows["correction_rules"].append(dict(rule_id=rule_id, event_id=rule_id, ordinal=len(rows["correction_rules"]),
        operation="review_answer", active=1, payload_json=json.dumps(dict(protocol=r.PROTOCOL,
            question_id="RQ-" + r.digest(case), case=case, choice="group", note="Invented", depends_on=deps,
            control_dependencies=deps, controls_version=c.VERSION, values=values, identity_scope=scope))))
    effects = i.bind_groups(rows, scope, values, rule_id, rule_id)
    r._review_state(rows)
    return scope, effects


class ControlTests(unittest.TestCase):
    def test_text_and_ambiguous_dates_are_preserved_without_coercion(self):
        values = {"outcome": "date", "date_text": "03/04/2020? <0.01", "sources": ["A", "B"]}
        self.assertEqual(c.validate_values(form_fixture(), values), values)

    def test_conditions_do_not_fill_defaults(self):
        self.assertEqual(c.validate_values(form_fixture(), {"outcome": "unknown"}), {"outcome": "unknown"})
        with self.assertRaises(c.ControlError): c.validate_values(form_fixture(), {"outcome": "date"})

    def test_hidden_values_cannot_silently_contribute(self):
        with self.assertRaises(c.ControlError):
            c.validate_values(form_fixture(), {"outcome": "unknown", "date_text": "2020"})

    def test_multiple_choice_rejects_duplicates_and_unknowns(self):
        for value in (["A", "A"], ["C"], "A", True):
            with self.subTest(value=value), self.assertRaises(c.ControlError):
                c.validate_values(form_fixture(), {"outcome": "unknown", "sources": value})

    def test_unknown_renderer_version_and_executable_keys_fail_closed(self):
        for change in (lambda f: f.update(version="future"),
                       lambda f: f["fields"][0].update(type="javascript"),
                       lambda f: f["fields"][0].update(on_change="alert(1)"),
                       lambda f: f.update(effect="bind_mentions")):
            form = form_fixture(); change(form)
            with self.assertRaises(c.ControlError): c.validate_form(form)

    def test_duplicate_fields_and_options_are_rejected(self):
        for form in (form_fixture(), form_fixture()):
            if len(form["fields"]) == 3:
                form["fields"].append(deepcopy(form["fields"][0]))
            with self.assertRaises(c.ControlError): c.validate_form(form)
        form = form_fixture(); form["fields"][0]["options"].append(form["fields"][0]["options"][0])
        with self.assertRaises(c.ControlError): c.validate_form(form)

    def test_conditions_are_bounded_and_reference_preceding_choices(self):
        form = form_fixture(); form["fields"][1]["visible_when"]["field"] = "sources"
        with self.assertRaises(c.ControlError): c.validate_form(form)

    def test_unknown_answer_fields_and_text_limits_are_enforced(self):
        for values in ({"outcome": "unknown", "execute": "anything"},
                       {"outcome": "date", "date_text": "a" * 101},
                       {"outcome": "date", "date_text": 2020}):
            with self.assertRaises(c.ControlError): c.validate_values(form_fixture(), values)

    def test_same_generic_controls_do_not_require_health_specific_code(self):
        form = form_fixture(); form["fields"][0]["label"] = "Which project milestone is disputed?"
        self.assertEqual(c.validate_values(form, {"outcome": "unknown"}), {"outcome": "unknown"})

    def test_partial_grouping_keeps_unknowns_separate(self):
        rows = fixture(); case = r.queue_from_records(rows)[0][0]["case"]
        form = c.identity_form(i.scope_for(case, rows))
        self.assertEqual(c.validate_values(form, group_values()), group_values())

    def test_grouping_rejects_duplicate_missing_and_out_of_scope_references(self):
        rows = fixture(); form = c.identity_form(i.scope_for(r.queue_from_records(rows)[0][0]["case"], rows))
        for values in (group_values(unknown=["M1", "M3", "M4"]), group_values(unknown=["M3"]),
                       group_values(unknown=["M3", "OTHER"])):
            with self.assertRaises(c.ControlError): c.validate_values(form, values)

    def test_groups_are_not_inferred_from_labels(self):
        rows = fixture(); before = deepcopy(rows["entries"])
        record_group(rows, group_values(groups=[{"label": "Alex", "target": None, "items": ["M1", "M3"]},
                                                {"label": "Alex", "target": None, "items": ["M2"]}], unknown=["M4"]))
        ids = [m["entity_id"] for m in rows["mentions"]]
        self.assertEqual(ids[0], ids[2]); self.assertNotEqual(ids[0], ids[1]); self.assertIsNone(ids[3])
        self.assertEqual(rows["entries"], before)

    def test_unknown_makes_no_distinctness_or_overwrite_claim(self):
        rows = fixture(); record_group(rows)
        self.assertTrue(all(m["entity_id"] is None for m in rows["mentions"][2:]))
        self.assertTrue(all(x["relation"] == "refers_to" for x in rows["relationships"]))

    def test_existing_assignment_cannot_be_moved_by_a_new_group(self):
        rows = fixture(); record_group(rows)
        with self.assertRaises(c.ControlError): record_group(rows, rule_id="another-group")

    def test_new_binding_reversal_restores_prior_state_and_question(self):
        rows = fixture(); before = deepcopy(rows)
        record_group(rows, group_values(groups=[{"label": "One person", "target": None,
                                                "items": ["M1", "M2", "M3", "M4"]}], unknown=[]))
        self.assertFalse(rows["unresolved_questions"])
        r._withdraw(rows, "owner-group", "withdrawal", 0)
        r._review_state(rows)
        self.assertEqual(rows["entries"], before["entries"])
        self.assertEqual(rows["mentions"], before["mentions"])
        self.assertEqual(rows["unresolved_questions"], before["unresolved_questions"])
        self.assertFalse(rows["entities"]); self.assertFalse(rows["relationships"])

    def test_legacy_binding_dependency_is_not_guessed(self):
        rows = fixture(); record_group(rows)
        rows["correction_rules"].append(dict(rule_id="legacy", operation="bind_mentions", active=1,
            payload_json=json.dumps({"depends_on": ["owner-group"]})))
        before = r.digest(rows)
        with self.assertRaises(r.ReviewError): r._withdraw(rows, "owner-group", "withdraw", 0)
        self.assertEqual(r.digest(rows), before)

    def test_an_extra_binding_support_blocks_unsafe_reversal_atomically(self):
        rows = fixture(); record_group(rows)
        edge = deepcopy(rows["relationships"][0]); edge["origin"] = "other_writer"
        edge["rule_ids_json"] = '["independent"]'; edge["relationship_id"] = "other-edge"
        rows["correction_rules"].append(dict(rule_id="independent", operation="assert_relation", active=1,
            payload_json='{"depends_on":[]}'))
        rows["relationships"].append(edge); before = r.digest(rows)
        with self.assertRaises(c.ControlError): r._withdraw(rows, "owner-group", "withdraw", 0)
        self.assertEqual(r.digest(rows), before)

    def test_tampered_binding_projection_is_detected(self):
        rows = fixture(); record_group(rows)
        rows["relationships"][0]["target_id"] = "invented-wrong-target"
        with self.assertRaises(c.ControlError): r._review_state(rows)

    def test_missing_binding_rules_cannot_leave_a_false_active_group(self):
        rows = fixture(); record_group(rows)
        rows["mentions"][0]["entity_id"] = None
        with self.assertRaises(c.ControlError): r._review_state(rows)

    def test_general_form_cannot_change_registered_relation_semantics(self):
        case = form_case(); case["kind"] = "conflict"
        with self.assertRaises(r.ReviewError):
            r.normalize_case(case, {e["entry_id"]: e for e in fixture()["entries"]})


@unittest.skipUnless(importlib.util.find_spec("conversation_archive.machine_archive"),
                     "Full-repository integration is run in GitHub CI")
class FlexibleIntegrationTests(unittest.TestCase):
    def setUp(self):
        from conversation_archive import machine_archive as ma
        from conversation_archive.structured_archive import connect, create_schema
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / "original"
        records = fixture(); db = connect(self.root / "input.sqlite3"); create_schema(db)
        db.execute("INSERT INTO metadata VALUES (?,?)", ("master_sha256", records["entries"][0]["source_sha256"]))
        for table in r.CORE_TABLES:
            columns = [x[1] for x in db.execute(f"PRAGMA table_info({table})")]
            db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})",
                           [tuple(row[k] for k in columns) for row in records[table]])
        db.commit(); db.close(); ma.snapshot(self.root / "input.sqlite3", self.source, "synthetic-0")
        self.before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}
        self.n = 0

    def session(self, source=None, cases=None):
        self.n += 1; source = source or self.source; output = self.root / f"review-{self.n}"
        path = None
        if cases:
            path = self.root / f"cases-{self.n}.json"
            path.write_bytes(r.encoded(dict(protocol=r.PROTOCOL, basis_snapshot_id=r.read_snapshot(source)[0]["snapshot_id"], cases=cases)))
        r.prepare(source, output, path)
        return output / "session.json", r.read_json(output / "session.json")

    def commit(self, source, path, session, question, choice, values=None):
        answer = dict(question_id=question["question_id"], choice=choice, note="Synthetic owner answer",
            previous_rule_id=question["current"]["rule_id"] if question["current"] else None)
        if values is not None: answer["values"] = values
        reply = dict(protocol=r.PROTOCOL, session_id=session["session_id"], basis_snapshot_id=session["basis_snapshot_id"],
                     actor="Synthetic reviewer", answers=[answer])
        answer_path = self.root / f"answer-{self.n}.json"; answer_path.write_bytes(r.encoded(reply))
        preview = self.root / f"preview-{self.n}"
        r.preview(source, path, answer_path, preview)
        output = self.root / f"successor-{self.n}"
        result = r.apply(source, path, answer_path, preview / "preview.json", output, f"synthetic-{self.n}", True)
        self.assertEqual(result["status"], "applied")
        return output

    def test_group_preview_apply_rebuild_and_reopen(self):
        from conversation_archive import machine_archive as ma
        path, session = self.session(); q = session["questions"][0]
        output = self.commit(self.source, path, session, q, "group", group_values())
        records = r.read_snapshot(output)[1]
        self.assertEqual(records["mentions"][0]["entity_id"], records["mentions"][1]["entity_id"])
        self.assertIsNone(records["mentions"][2]["entity_id"])
        self.assertEqual(ma.build_sqlite(output, self.root / "rebuilt.sqlite3")["status"], "passed")
        path2, session2 = self.session(output)
        output2 = self.commit(output, path2, session2, session2["questions"][0], "reopen")
        self.assertTrue(all(m["entity_id"] is None for m in r.read_snapshot(output2)[1]["mentions"]))
        self.assertFalse(r.read_snapshot(output2)[1]["entities"])
        self.assertFalse(any(n["node_type"] == "person" for n in ma.load_jsonl(output2 / "nodes.jsonl")))
        self.assertEqual(self.before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()})

    def test_generic_answers_are_record_only_and_pending_forms_survive(self):
        case2 = form_case(); case2["title"] = "Another synthetic question"
        path, session = self.session(cases=[form_case(), case2])
        q = next(q for q in session["questions"] if q["case"]["kind"] == "form")
        output = self.commit(self.source, path, session, q, "record", {"outcome": "unknown"})
        records = r.read_snapshot(output)[1]
        self.assertFalse(records["relationships"]); self.assertFalse(records["entities"])
        _, following = self.session(output)
        forms = [q for q in following["questions"] if q["case"]["kind"] == "form"]
        self.assertEqual(len(forms), 2); self.assertEqual(sum(q["current"] is None for q in forms), 1)

    def test_replacing_partial_groups_can_keep_existing_entity_id(self):
        path, session = self.session()
        output = self.commit(self.source, path, session, session["questions"][0], "group", group_values())
        eid = r.read_snapshot(output)[1]["mentions"][0]["entity_id"]
        path2, session2 = self.session(output)
        values = group_values(groups=[dict(label="First Alex", target=eid, items=["M1", "M2", "M3"])], unknown=["M4"])
        output2 = self.commit(output, path2, session2, session2["questions"][0], "group", values)
        self.assertTrue(all(m["entity_id"] == eid for m in r.read_snapshot(output2)[1]["mentions"][:3]))

    def test_changed_controls_rejected_even_with_rehashed_session(self):
        path, session = self.session()
        session["questions"][0]["controls"]["effect"] = "record_only"
        session["session_id"] = "RS-" + r.digest({k: v for k, v in session.items() if k != "session_id"})
        with self.assertRaises(r.ReviewError): r._checked_session(session, *self._checked_args())

    def _checked_args(self):
        manifest, records, fingerprint = r.read_snapshot(self.source)
        return manifest, records, fingerprint

    def test_legacy_session_deferral_still_works(self):
        path, session = self.session()
        for q in session["questions"]: q.pop("controls", None)
        session["session_id"] = "RS-" + r.digest({k: v for k, v in session.items() if k != "session_id"})
        path.write_bytes(r.encoded(session))
        output = self.commit(self.source, path, session, session["questions"][0], "defer")
        _, next_session = self.session(output)
        self.assertEqual(next_session["questions"][0]["current"]["choice"], "defer")

    def test_grouping_cannot_be_smuggled_into_a_legacy_session(self):
        path, session = self.session()
        for q in session["questions"]: q.pop("controls", None)
        session["session_id"] = "RS-" + r.digest({k: v for k, v in session.items() if k != "session_id"})
        path.write_bytes(r.encoded(session))
        with self.assertRaises(r.ReviewError):
            self.commit(self.source, path, session, session["questions"][0], "group", group_values())


if __name__ == "__main__":
    unittest.main()
