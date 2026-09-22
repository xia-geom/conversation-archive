"""Regression checks for queue continuity; all examples are invented."""
import json
from pathlib import Path
import tempfile
import unittest

from conversation_archive import snapshot_review as review
from conversation_archive import machine_archive as ma
from conversation_archive.structured_archive import connect, create_schema
from tests.test_snapshot_review import records_fixture, case_fixture, write, hashes


class ReviewLifecycleTests(unittest.TestCase):
    def test_partial_reply_keeps_unanswered_supplied_cases_in_next_session(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = records_fixture()
            db = connect(root / "input.sqlite3")
            create_schema(db)
            db.execute("INSERT INTO metadata VALUES (?,?)", (
                "master_sha256", records["entries"][0]["source_sha256"]))
            for table in review.CORE_TABLES:
                columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
                db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})",
                               [tuple(row[key] for key in columns) for row in records[table]])
            db.commit()
            db.close()
            source = root / "source"
            ma.snapshot(root / "input.sqlite3", source, "invented-1")
            before = hashes(source)
            bundle = write(root / "cases.json", dict(protocol=review.PROTOCOL,
                basis_snapshot_id=review.read_snapshot(source)[0]["snapshot_id"],
                cases=[case_fixture(), case_fixture("relationship")]))
            review.prepare(source, root / "session1", bundle)
            session_path = root / "session1" / "session.json"
            session = review.read_json(session_path)
            question = session["questions"][0]
            reply = write(root / "answers.json", dict(protocol=review.PROTOCOL,
                session_id=session["session_id"], basis_snapshot_id=session["basis_snapshot_id"],
                actor="Invented reviewer", answers=[dict(question_id=question["question_id"],
                    choice="disagree", note="Synthetic decision only.", previous_rule_id=None)]))
            review.preview(source, session_path, reply, root / "preview")
            preview = root / "preview" / "preview.json"
            self.assertEqual(review.read_json(preview)["retained_proposals"], 2)
            successor = root / "successor"
            review.apply(source, session_path, reply, preview, successor, "invented-2", True)
            # No --cases argument and no original session passed to this preparation.
            review.prepare(successor, root / "session2")
            next_session = review.read_json(root / "session2" / "session.json")
            self.assertEqual(len(next_session["questions"]), 3)
            relation = next(q for q in next_session["questions"] if q["case"]["kind"] == "relationship")
            self.assertIsNone(relation["current"])
            self.assertEqual(relation["question_id"], session["questions"][1]["question_id"])
            self.assertEqual(len(next_session["history"]), 1)
            _, after, _ = review.read_snapshot(successor)
            self.assertFalse(after["relationships"])
            queue = next(r for r in after["correction_rules"] if r["operation"] == "review_queue")
            self.assertEqual(json.loads(queue["payload_json"])["authority"], "unresolved_candidate")
            self.assertEqual(hashes(source), before)

    def test_recorded_dependency_cannot_be_removed_from_case(self):
        records = records_fixture()
        case = case_fixture()
        case["depends_on"] = ["prior-support"]
        case = review.normalize_case(case, {e["entry_id"]: e for e in records["entries"]})
        records["correction_rules"] = [
            dict(rule_id="prior-support", operation="assert_relation", active=1,
                 payload_json=json.dumps({"depends_on": []})),
            dict(rule_id="answer", operation="review_answer", active=1, event_id="event",
                 payload_json=json.dumps(dict(protocol=review.PROTOCOL, case=case,
                    question_id="RQ-" + review.digest(case), choice="disagree", note="Invented",
                    depends_on=[]))),
        ]
        with self.assertRaisesRegex(review.ReviewError, "dependencies changed"):
            review._review_state(records)

    def test_binding_dependency_refuses_revocation_without_mutating_records(self):
        records = records_fixture()
        records["correction_rules"] = [
            dict(rule_id="support", operation="review_answer", active=1,
                 payload_json=json.dumps({"depends_on": []})),
            dict(rule_id="binding", operation="bind_mentions", active=1,
                 payload_json=json.dumps({"depends_on": ["support"]})),
        ]
        before = review.digest(records)
        with self.assertRaisesRegex(review.ReviewError, "unsupported dependent operation"):
            review._withdraw(records, "support", "next-event", 2)
        self.assertEqual(review.digest(records), before)


if __name__ == "__main__":
    unittest.main()
