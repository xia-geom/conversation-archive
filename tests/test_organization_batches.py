"""Synthetic batch/context/answer tests; never a semantic model benchmark."""
from copy import deepcopy
import json
import re
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from conversation_archive import organization as o
from conversation_archive import organization_batches as b


def data(families=20):
    entries, catalog = [], []
    for i in range(families):
        label = f"Project{i:02}"
        catalog.append(dict(kind="project", label=label, family=label))
        entries += [dict(entry_id=f"E{2*i+j+1:04}",
                         text=f"## E{2*i+j+1:04} — Planning {label}\nDuring the spring workshop in Gardenhall, {label} {'began' if j == 0 else 'was reconsidered'}. 🌱")
                    for j in range(2)]
    return dict(version=o.VERSION, entries=entries, catalog=catalog, proposals=[])


def state(d=None):
    d = d if d is not None else data()
    return dict(version=o.VERSION, data=d, data_sha256=o.digest(d), events=[], events_sha256=o.digest([]))


def answer(batch, *responses):
    return dict(batch_id=batch["batch_id"], actor="invented reviewer",
                answer_text="Synthetic answer for test purposes only.", responses=list(responses))


def event(s, *ops, eid="initial"):
    return dict(event_id=eid, actor="invented reviewer", answer="Synthetic scoped confirmation.",
                expected_state_sha256=o.digest(s), operations=list(ops))


def anchored(count=3, distinct=1):
    d = data(1)
    label = "Rowan"
    d["catalog"] = [dict(kind="person", label=label, family="rowan")]
    d["entries"] = [dict(entry_id=f"E{i+1:04}", text=f"## E{i+1:04} — Workshop {i+1}\nAt the spring workshop, Rowan discussed the garden plan.") for i in range(count)]
    s = state(d)
    ops = [dict(op="bind", rule_id=f"known-{i}", depends_on=[], kind="person", aliases=[label],
                entry_ids=[f"E{i+1:04}"], entity_id=f"rowan-{i}", entity_label=f"Workshop Rowan {i}") for i in range(distinct)]
    return o.preview(s, event(s, *ops))[0]


def relation(d):
    return dict(proposal_id="next", source=d["entries"][0]["entry_id"], target=d["entries"][1]["entry_id"],
                relation="continues", reason="Possible continuation; check identity first.",
                evidence=[dict(entry_id=e["entry_id"], start=0, end=len(e["text"]), quote=e["text"]) for e in d["entries"][:2]])


class BatchTests(unittest.TestCase):
    def test_default_batch_is_fifteen_and_scans_whole_inventory(self):
        q = b.make_batch(state())
        self.assertEqual(len(q["questions"]), 15)
        self.assertEqual(q["scan"]["entries_scanned"], 40)
        self.assertEqual(q["scan"]["candidate_questions"], 20)
        self.assertEqual([x["number"] for x in q["questions"]], list(range(1, 16)))
        self.assertFalse(q["scan"]["semantic_discovery_performed"])

    def test_ten_twenty_and_no_padding(self):
        for size in (10, 20):
            self.assertEqual(len(b.make_batch(state(), size)["questions"]), size)
        self.assertEqual(len(b.make_batch(state(data(2)))["questions"]), 2)

    def test_invalid_limits_fail(self):
        for size in (True, 0, -1, 21):
            with self.assertRaises(o.OrganizationError):
                b.make_batch(state(), size=size)
        for width in (True, 0, 79, 1201):
            with self.assertRaises(o.OrganizationError):
                b.make_batch(state(), context_chars=width)

    def test_global_ranking_can_select_family_at_end(self):
        d = data()
        d["entries"] += [dict(entry_id=f"X{i}", text="Project19 is relevant.") for i in range(7)]
        self.assertEqual(b.make_batch(state(d), 1)["questions"][0]["hypothesis_family"], "Project19")

    def test_existing_questions_default_is_fifteen(self):
        self.assertEqual(len(o.questions(state())), 15)

    def test_titles_and_exact_unicode_context(self):
        s = state()
        q = b.make_batch(s)["questions"][0]
        texts = {e["entry_id"]: e["text"] for e in s["data"]["entries"]}
        for c in q["evidence"]:
            self.assertTrue(c["title"].startswith("Planning Project"))
            self.assertEqual(c["context"], texts[c["entry_id"]][c["context_start"]:c["context_end"]])
            self.assertIn("Gardenhall", c["context"])
            self.assertIn("🌱", c["context"])
            self.assertNotIn("event_date", c)

    def test_known_reference_and_single_pending_mention_are_shown(self):
        s = anchored(2)
        q = b.make_batch(s)["questions"][0]
        self.assertEqual(len(q["evidence"]), 1)
        self.assertEqual(q["known_references"][0]["evidence"][0]["entry_id"], "E0001")
        self.assertIn("previously user-confirmed", b.render_questions([q]))
        self.assertEqual(q["known_references"][0]["code"], "R1")

    def test_known_reference_excerpt_and_other_confirmed_context(self):
        s = anchored()
        op = dict(op="associate", rule_id="context", depends_on=[], kind="period", entry_ids=["E0002"],
                  entity_id="spring", entity_label="Spring workshop period")
        s, _ = o.preview(s, event(s, op, eid="context"))
        out = b.render_questions(b.make_batch(s)["questions"])
        self.assertIn("Spring workshop period", out)
        self.assertIn("not inferred event dates/locations", out)

    def test_same_reuses_one_confirmed_identity(self):
        s = anchored()
        batch = b.make_batch(s)
        updated, report = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        assignments = o.graph(updated)["assignments"]
        self.assertEqual({v["entity"] for v in assignments.values()}, {"entity:person:rowan-0"})
        self.assertEqual(updated["data"], s["data"])
        self.assertEqual(len(report["affected_entry_ids"]), 2)
        self.assertEqual(updated["events"][-1]["operations"][0]["depends_on"], ["known-0"])

    def test_multiple_known_people_require_explicit_selection(self):
        s = anchored(4, 2)
        batch = b.make_batch(s)
        with self.assertRaises(o.OrganizationError):
            b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        result, _ = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same", reference="R2")))
        self.assertEqual(len(o.graph(result)["assignments"]), 4)

    def test_partial_group_defers_only_explicit_unknown(self):
        s = anchored(4)
        batch = b.make_batch(s)
        response = dict(number=1, choice="groups", groups=[dict(members=["A", "C"], reference="R1")], unknown=["B"])
        result, _ = b.preview_answers(s, batch, answer(batch, response))
        g = o.graph(result)
        self.assertEqual(len(g["assignments"]), 3)
        self.assertEqual(len(g["deferred"]), 1)
        self.assertEqual(b.make_batch(result)["questions"], [])

    def test_not_all_does_not_mean_all_different(self):
        s = state(data(1))
        batch = b.make_batch(s)
        with self.assertRaises(o.OrganizationError):
            b.preview_answers(s, batch, answer(batch, dict(number=1, choice="not all")))

    def test_duplicate_or_unshown_or_missing_reference_fails(self):
        s = state(data(1))
        batch = b.make_batch(s)
        for groups in ([dict(members=["A", "Z"])], [dict(members=["A"])],
                       [dict(members=["A", "B"]), dict(members=["A"]) ]):
            with self.assertRaises(o.OrganizationError):
                b.preview_answers(s, batch, answer(batch, dict(number=1, choice="groups", groups=groups)))

    def test_one_family_chunk_per_batch_and_unseen_untouched(self):
        d = data(1)
        d["entries"] += [dict(entry_id=f"X{i}", text="Project00 continues.") for i in range(20)]
        s = state(d)
        batch = b.make_batch(s, max_items=4)
        self.assertEqual(len(batch["questions"]), 1)
        self.assertEqual(batch["questions"][0]["family_mentions_not_shown"], 20)
        result, _ = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        self.assertEqual(len(o.graph(result)["assignments"]), 4)
        self.assertEqual(len(b.make_batch(result)["questions"][0]["known_references"]), 1)

    def test_legacy_large_family_preview_keeps_disjoint_chunks(self):
        d = data(1)
        d["entries"] = [dict(entry_id=f"X{i}", text="Project00") for i in range(100)]
        qs = o.questions(state(d), 3, max_items=12)
        self.assertEqual(len(qs), 3)
        self.assertEqual(len({eid for q in qs for eid in q["affected_entry_ids"]}), 36)

    def test_possible_dependent_relations_wait_until_next_batch(self):
        d = data(1)
        d["proposals"] = [relation(d)]
        s = state(d)
        batch = b.make_batch(s)
        self.assertEqual(batch["scan"]["relations_held_for_context"], 1)
        self.assertTrue(all(q["kind"] != "relation" for q in batch["questions"]))
        updated, _ = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        nxt = b.make_batch(updated)
        self.assertEqual(nxt["questions"][0]["kind"], "relation")
        self.assertEqual(next(e for e in o.graph(updated)["edges"] if e.get("proposal_id"))["status"], "proposed")

    def test_relation_partial_unknown_is_honestly_pending(self):
        d = data(1)
        d["catalog"] = []
        d["proposals"] = [relation(d)]
        s = state(d)
        batch = b.make_batch(s)
        result, report = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="unsure")))
        self.assertEqual(s, result)
        self.assertEqual(report["relations_left_pending"], [1])
        self.assertEqual(report["status"], "no_changes")

    def test_fifteen_answers_become_one_event_and_preserve_text(self):
        s = state()
        batch = b.make_batch(s)
        responses = [dict(number=n, choice="same") for n in range(1, 16)]
        result, report = b.preview_answers(s, batch, answer(batch, *responses))
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(report["responses_received"], 15)
        self.assertEqual(len(o.graph(result)["assignments"]), 60)
        self.assertEqual(result["data"], s["data"])

    def test_unanswered_questions_remain_pending(self):
        s = state()
        batch = b.make_batch(s)
        result, report = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        self.assertEqual(report["unanswered_numbers"], list(range(2, 16)))
        self.assertEqual(len(o.graph(result)["assignments"]), 4)

    def test_tampered_cards_numbering_scope_rejected(self):
        s = state()
        batch = b.make_batch(s)
        for change in ("text", "number", "scope"):
            broken = deepcopy(batch)
            q = broken["questions"][0]
            if change == "text":
                q["evidence"][0]["context"] = "Invented quotation"
            elif change == "number":
                q["number"] = 20
            else:
                q["handles"].append("M-other")
            with self.assertRaises(o.OrganizationError):
                b.validate_batch(s, broken)

    def test_stale_batch_after_another_answer_rejected(self):
        s = state(data(2))
        batch = b.make_batch(s)
        newer, _ = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        with self.assertRaises(o.OrganizationError):
            b.preview_answers(newer, batch, answer(batch, dict(number=2, choice="same")))

    def test_identical_batch_reply_is_idempotent(self):
        s = state()
        batch = b.make_batch(s)
        answers = answer(batch, dict(number=1, choice="same"))
        updated, _ = b.preview_answers(s, batch, answers)
        repeat, report = b.preview_answers(updated, batch, answers)
        self.assertEqual(repeat, updated)
        self.assertEqual(report["status"], "already_applied")

    def test_new_binding_depends_on_displayed_reference(self):
        s = anchored()
        batch = b.make_batch(s)
        result, _ = b.preview_answers(s, batch, answer(batch, dict(number=1, choice="same")))
        op = dict(op="revoke", rule_id="undo-known", target="known-0")
        revoked, _ = o.preview(result, event(result, op, eid="revoke"))
        self.assertEqual(o.graph(revoked)["assignments"], {})

    def test_unsafe_markdown_is_escaped_and_excerpts_fenced(self):
        d = data(1)
        d["entries"][0]["text"] = "## E0001 — <script>bad()</script> [link](https://example.invalid)\nProject00 ``` delete master ```"
        out = b.render_questions(b.make_batch(state(d))["questions"])
        self.assertIn("````text", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("not probabilities", out)

    def test_blank_template_and_duplicate_number_not_applied(self):
        s = state(data(1))
        batch = b.make_batch(s)
        for answers in (dict(batch_id=batch["batch_id"], actor="", answer_text="", responses=[]),
                        answer(batch, dict(number=1, choice="same"), dict(number=1, choice="same")),
                        answer(batch, dict(number=True, choice="same"))):
            with self.assertRaises(o.OrganizationError):
                b.preview_answers(s, batch, answers)

    def test_file_prepare_apply_repeat_and_second_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, output = Path(tmp) / "run", Path(tmp) / "batch"
            o.prepare(data(), run)
            before = (run / "state.json").read_bytes()
            b.prepare_batch(run, output)
            batch = o.load(output / "batch.json")
            self.assertEqual(before, (run / "state.json").read_bytes())
            self.assertEqual(o.load(output / "answers.template.json")["responses"], [])
            answers = answer(batch, dict(number=1, choice="same"), dict(number=2, choice="same"))
            with o.locked(run):
                with self.assertRaises(o.OrganizationError):
                    b.apply_answers(run, batch, answers)
            b.apply_answers(run, batch, answers)
            self.assertEqual(b.apply_answers(run, batch, answers)["status"], "already_applied")
            self.assertEqual(len(o.read_state(run)["events"]), 1)

    def test_bulk_validation_is_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            o.prepare(data(2), run)
            s = o.read_state(run)
            batch = b.make_batch(s)
            before = (run / "state.json").read_bytes()
            answers = answer(batch, dict(number=1, choice="same"), dict(number=2, choice="groups", groups=[dict(members=["Z"]) ]))
            with self.assertRaises(o.OrganizationError):
                b.apply_answers(run, batch, answers)
            self.assertEqual(before, (run / "state.json").read_bytes())

    def test_prepared_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, output = Path(tmp) / "run", Path(tmp) / "batch"
            o.prepare(data(), run)
            b.prepare_batch(run, output)
            with self.assertRaises(FileExistsError):
                b.prepare_batch(run, output)

    def test_cli_prepare_show_full_preview_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, output = Path(tmp) / "run", Path(tmp) / "batch"
            o.prepare(data(), run)
            prefix = [sys.executable, "-m", "conversation_archive.organization_batches"]
            def call(*args):
                return subprocess.run(prefix + list(args), text=True, capture_output=True, check=True).stdout
            report = json.loads(call("prepare", "--run", str(run), "--output", str(output)))
            self.assertEqual(report["questions"], 15)
            self.assertIn("Full entry text shown", call("show", "--run", str(run), "--batch", str(output / "batch.json"), "--number", "1", "--full"))
            batch = o.load(output / "batch.json")
            path = Path(tmp) / "answers.json"
            o.atomic_write(path, answer(batch, dict(number=1, choice="same")))
            common = ["--run", str(run), "--batch", str(output / "batch.json"), "--answers", str(path)]
            self.assertEqual(json.loads(call("preview", *common))["status"], "ready")
            with patch("builtins.print"):
                self.assertEqual(b.main(["apply", *common]), 2)
            self.assertEqual(json.loads(call("apply", *common, "--confirm-user-answer"))["responses_received"], 1)
            self.assertIn("Historical batch", call("show", "--run", str(run), "--batch", str(output / "batch.json")))


    def test_documented_batch_commands_run_verbatim(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/question-batches.md").read_text()
        block = text.split("<!-- smoke:organization-batch:start -->", 1)[1].split("<!-- smoke:organization-batch:end -->", 1)[0]
        commands = re.search(r"```sh\n(.*?)```", block, re.S)[1].strip().splitlines()
        with tempfile.TemporaryDirectory() as tmp:
            for line in commands:
                line = line.replace("data/batch-example", str(Path(tmp) / "run")).replace("data/questions-01", str(Path(tmp) / "batch"))
                args = shlex.split(line)
                args[0] = sys.executable
                subprocess.run(args, cwd=root, check=True, text=True, capture_output=True)
            result = o.load(Path(tmp) / "batch/batch.json")
            self.assertEqual(result["scan"]["entries_scanned"], 40)
            self.assertEqual(len(result["questions"]), 15)


if __name__ == "__main__":
    unittest.main()
