"""Offline snapshot review: declarative controls, checked answers, immutable successors.

The snapshot remains authoritative. HTML, Codex, and other clients submit the
same versioned answers; neither form definitions nor skills authorize writes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import review_controls as controls
from . import review_identity as identity

PROTOCOL = "snapshot-review-1.0"
RELATIONS = {"continues", "revises", "precedes", "responds_to", "reported_cause"}
# Legacy choices stay readable. Additional actions are explicitly versioned in a
# prepared row's controls, rather than silently changing an older saved session.
CHOICES = {
    "relationship": ("confirm", "reject", "insufficient", "defer", "reopen"),
    "conflict": ("disagree", "different_events", "different_date_roles",
                 "transcription_discrepancy", "corrected_report", "insufficient", "defer", "reopen"),
    "identity": ("defer", "reopen"),
    "form": ("record", "insufficient", "defer", "reopen"),
}
CORE_TABLES = ("migration_sources", "entries", "entry_metadata", "source_references",
               "entities", "mentions", "relationships", "correction_events",
               "correction_rules", "unresolved_questions")


class ReviewError(controls.ControlError):
    """A review cannot be represented safely with the supplied evidence."""


def require(condition, message):
    if not condition:
        raise ReviewError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read_json(path, limit=32 * 1024 * 1024):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ReviewError("Non-finite JSON value")
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= limit, "Missing or oversized JSON input")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError("Invalid UTF-8 JSON input") from exc


def write_json(path, value):
    with Path(path).open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _fingerprint(root):
    root = Path(root).resolve()
    require(not (root / "manifest.json").is_symlink(), "Snapshot manifest is a symlink")
    manifest = read_json(root / "manifest.json")
    expected = {name + ".jsonl" for name in CORE_TABLES} | {"nodes.jsonl"}
    require(set(manifest.get("files", {})) == expected, "Unsupported or incomplete snapshot manifest")
    observed, total = {}, 0
    for name in sorted(expected):
        path = root / name
        require(not path.is_symlink() and path.is_file(), "Missing file or snapshot symlink")
        size = path.stat().st_size
        total += size
        require(total <= 512 * 1024 * 1024, "Snapshot exceeds review size bound")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        item = manifest["files"][name]
        require(item.get("sha256") == sha and item.get("bytes") == size, "Snapshot file hash or size mismatch")
        observed[name] = sha
    return digest({"manifest": manifest, "files": observed})


def read_snapshot(root):
    from . import machine_archive as ma
    root = Path(root).resolve()
    before = _fingerprint(root)
    require(ma.validate(root)["status"] == "passed", "Invalid authoritative snapshot")
    manifest, records = read_json(root / "manifest.json"), ma.archive_records(root)
    require(_fingerprint(root) == before, "Snapshot changed during reading")
    _review_state(records)
    return manifest, records, before


def _evidence(items, entries):
    require(isinstance(items, list) and bool(items), "Question needs exact evidence")
    result = []
    for item in items:
        require(isinstance(item, dict) and set(item) in (
            {"entry_id", "start", "end", "quote"},
            {"entry_id", "start", "end", "quote", "entry_sha256"}), "Unexpected evidence fields")
        entry = entries.get(item["entry_id"])
        require(entry is not None, "Unknown evidence entry")
        text = entry["raw_markdown"]
        lo, hi, quote = item["start"], item["end"], item["quote"]
        require(type(lo) is int and type(hi) is int and isinstance(quote, str)
                and bool(quote.strip()) and 0 <= lo < hi <= len(text)
                and text[lo:hi] == quote, "Evidence quotation mismatch")
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        require(item.get("entry_sha256", sha) == sha, "Question evidence changed")
        result.append(dict(entry_id=item["entry_id"], start=lo, end=hi, quote=quote, entry_sha256=sha))
    require(len({digest(item) for item in result}) == len(result), "Duplicate evidence occurrence")
    return result


def normalize_case(case, entries):
    fields = {"kind", "title", "prompt", "reason", "evidence", "depends_on"}
    optional = {"relation", "source_entry_id", "target_entry_id", "source_question_id", "form"}
    require(isinstance(case, dict) and fields <= set(case) <= fields | optional, "Unexpected review-case fields")
    kind = case["kind"]
    require(isinstance(kind, str) and kind in CHOICES, "Unsupported question kind")
    require(all(isinstance(case[key], str) and case[key].strip()
                for key in ("title", "prompt", "reason")), "Question needs context and a precise prompt")
    deps = case["depends_on"]
    require(isinstance(deps, list) and all(isinstance(x, str) and x for x in deps)
            and len(set(deps)) == len(deps), "Invalid question dependencies")
    result = dict(case, evidence=_evidence(case["evidence"], entries), depends_on=sorted(deps))
    if kind == "relationship":
        require(case.get("relation") in RELATIONS, "Unsupported directed relationship")
        a, b = case.get("source_entry_id"), case.get("target_entry_id")
        require(a in entries and b in entries and a != b, "Invalid relationship endpoints")
        require({x["entry_id"] for x in result["evidence"]} == {a, b}, "Relationship must cite both endpoints")
    else:
        require(not {"relation", "source_entry_id", "target_entry_id"} & set(case), "Unexpected relationship scope")
        if kind == "conflict":
            require(len(result["evidence"]) >= 2, "Potential conflict needs at least two assertion occurrences")
    if kind == "form":
        require("form" in case, "A general question needs a declared form")
        result["form"] = controls.validate_form(case["form"])
    else:
        require("form" not in case, "Custom fields cannot change a registered semantic operation")
    return result


def _control_spec(case, records):
    """Trusted registry of semantic effects; a supplied form is always record-only."""
    if case["kind"] == "form":
        return {"version": controls.VERSION, "effect": "record_only", "action": "record", "form": case["form"]}
    if case["kind"] == "identity":
        scope = identity.scope_for(case, records)
        return {"version": controls.VERSION, "effect": "bind_mentions", "action": "group",
                "form": controls.identity_form(scope), "scope": scope}
    return None


def _answer_values(case, answer, spec):
    action = spec["action"] if spec else None
    if answer["choice"] == action:
        require("values" in answer, "A structured answer is required")
        return controls.validate_values(spec["form"], answer["values"])
    require("values" not in answer, "This outcome does not accept form values")
    return None


def _review_state(records):
    entries = {e["entry_id"]: e for e in records["entries"]}
    rules = {r["rule_id"]: r for r in records["correction_rules"]}
    require(len(rules) == len(records["correction_rules"]), "Duplicate correction rule IDs")
    active, cases, history = {}, {}, []
    for rule in records["correction_rules"]:
        if rule["operation"] == "review_queue":
            payload = json.loads(rule["payload_json"])
            require(payload.get("protocol") == PROTOCOL and payload.get("authority") == "unresolved_candidate"
                    and isinstance(payload.get("cases"), list), "Invalid retained question queue")
            for candidate in payload["cases"]:
                case = normalize_case(candidate, entries)
                require(case["kind"] != "identity", "Identity questions stay in their existing registry")
                cases["RQ-" + digest(case)] = case
            continue
        if rule["operation"] != "review_answer":
            continue
        payload = json.loads(rule["payload_json"])
        require(payload.get("protocol") == PROTOCOL, "Unsupported review history protocol")
        case = normalize_case(payload["case"], entries)
        qid, choice = "RQ-" + digest(case), payload.get("choice")
        allowed = set(CHOICES[case["kind"]]) | ({"group"} if case["kind"] == "identity" else set())
        require(payload.get("question_id") == qid and choice in allowed and choice != "reopen", "Invalid recorded answer")
        extra_deps = payload.get("control_dependencies", [])
        require(isinstance(extra_deps, list) and all(isinstance(x, str) for x in extra_deps)
                and (case["kind"] == "identity" and choice == "group" or not extra_deps), "Invalid control dependencies")
        expected_deps = [] if choice == "defer" else sorted(set(case["depends_on"]) | set(extra_deps))
        require(payload["depends_on"] == expected_deps, "Recorded comparison dependencies changed")
        require(set(payload["depends_on"]) <= set(rules), "Missing recorded review dependency")
        if "values" in payload:
            require(payload.get("controls_version") == controls.VERSION, "Unsupported recorded controls")
            spec = ({"action": "group", "form": controls.identity_form(payload["identity_scope"])}
                    if case["kind"] == "identity" else {"action": "record", "form": case.get("form")})
            _answer_values(case, payload, spec)
        else:
            require(choice not in {"group", "record"}, "Recorded form answer is missing its values")
        cases[qid] = case
        item = {"question_id": qid, "rule_id": rule["rule_id"], "event_id": rule["event_id"],
                "choice": choice, "note": payload["note"], "active": bool(rule["active"])}
        if "values" in payload:
            item["values"] = payload["values"]
        history.append(item)
        if rule["active"]:
            require(qid not in active, "Conflicting active answers for a question")
            require(all(rules[r]["active"] for r in payload["depends_on"]), "Review answer depends on an inactive rule")
            active[qid] = dict(item)
    observed = set()
    for rel in records["relationships"]:
        if rel["origin"] != "snapshot_review_answer":
            continue
        supports = json.loads(rel["rule_ids_json"])
        require(len(supports) == 1 and supports[0] in rules, "Review relationship lacks its decision")
        rule = rules[supports[0]]
        payload = json.loads(rule["payload_json"])
        case = payload["case"]
        require(rule["active"] and rule["operation"] == "review_answer" and case["kind"] == "relationship"
                and payload["choice"] in {"confirm", "reject"}
                and rel["source_id"] == case["source_entry_id"] and rel["target_id"] == case["target_entry_id"]
                and rel["relation"] == case["relation"] and rel["authority"] == "owner_confirmed"
                and rel["status"] == ("user_confirmed" if payload["choice"] == "confirm" else "rejected")
                and json.loads(rel["evidence_json"]) == case["evidence"], "Review relationship disagrees with recorded answer")
        require(supports[0] not in observed, "Duplicate review relationship")
        observed.add(supports[0])
    required = {rid for rid, r in rules.items() if r["active"] and r["operation"] == "review_answer"
                and json.loads(r["payload_json"])["case"]["kind"] == "relationship"
                and json.loads(r["payload_json"])["choice"] in {"confirm", "reject"}}
    require(observed == required, "An active relationship answer is missing its projection")
    identity.validate_bindings(records)
    return active, cases, history


def queue_from_records(records, supplied=()):
    entries = {e["entry_id"]: e for e in records["entries"]}
    active, prior_cases, history = _review_state(records)
    candidates, blocked = list(prior_cases.values()) + list(supplied), []
    mentions = {m["mention_id"]: m for m in records["mentions"]}
    for question in records["unresolved_questions"]:
        try:
            evidence = []
            for witness in json.loads(question["evidence_json"]):
                mention = mentions[witness["mention_id"]]
                require(mention["entry_id"] == witness["entry_id"], "Question mention scope mismatch")
                evidence.append({k: mention[k] for k in ("entry_id", "start", "end", "quote")})
            candidates.append(dict(kind="identity", title=question["family"] or question["kind"],
                prompt=question["prompt"], reason="Existing identity question; optional, not a contradiction.",
                evidence=evidence, depends_on=[], source_question_id=question["question_id"]))
        except (ReviewError, KeyError, TypeError, json.JSONDecodeError):
            blocked.append({"id": question["question_id"], "reason": "Unsupported saved-question evidence"})
    for rel in records["relationships"]:
        if rel["status"] != "proposed" or rel["relation"] not in RELATIONS:
            continue
        try:
            evidence = json.loads(rel["evidence_json"])
            require(isinstance(evidence, list), "Unsupported proposal evidence")
            evidence = [{k: w[k] for k in ("entry_id", "start", "end", "quote")} for w in evidence]
            candidates.append(dict(kind="relationship", title=rel["relation"],
                prompt="Does this directed relationship hold for the two displayed entries?",
                reason="Existing proposed relationship, not an established fact.", evidence=evidence,
                relation=rel["relation"], source_entry_id=rel["source_id"].removeprefix("entry:"),
                target_entry_id=rel["target_id"].removeprefix("entry:"), depends_on=[]))
        except (ReviewError, KeyError, TypeError, json.JSONDecodeError):
            blocked.append({"id": rel["relationship_id"], "reason": "Proposal lacks explicit two-entry spans"})
    rows, live = {}, {r["rule_id"] for r in records["correction_rules"] if r["active"]}
    for candidate in candidates:
        try:
            case = normalize_case(candidate, entries)
        except controls.ControlError:
            if candidate in supplied:
                raise
            blocked.append({"id": candidate.get("source_question_id", "existing-proposal"),
                            "reason": "Existing proposal has unsupported or changed evidence"})
            continue
        qid = "RQ-" + digest(case)
        rows[qid] = {"question_id": qid, "case": case, "current": active.get(qid),
                     "blocked": "Inactive comparison dependency" if set(case["depends_on"]) - live else None,
                     "choices": list(CHOICES[case["kind"]])}
    order = {"conflict": 0, "relationship": 1, "form": 2, "identity": 3}
    return sorted(rows.values(), key=lambda q: (order[q["case"]["kind"]], q["question_id"])), blocked, history


def _outside(output, *inputs):
    out = Path(output).resolve()
    for source in inputs:
        require(not out.is_relative_to(Path(source).resolve()), "Output must be outside preserved inputs")
    return out


def prepare(archive, output, cases_path=None, size=15):
    from .review_html import render
    require(type(size) is int and 1 <= size <= 20, "Batch size must be 1–20")
    manifest, records, fingerprint = read_snapshot(archive)
    supplied = []
    if cases_path:
        bundle = read_json(cases_path)
        require(set(bundle) == {"protocol", "basis_snapshot_id", "cases"}
                and bundle["protocol"] == PROTOCOL and bundle["basis_snapshot_id"] == manifest["snapshot_id"]
                and isinstance(bundle["cases"], list), "Invalid or stale supplied cases")
        supplied = bundle["cases"]
    queue, blocked, history = queue_from_records(records, supplied)
    for row in queue:
        spec = _control_spec(row["case"], records)
        if spec:
            row["controls"] = spec
    selected = {w["entry_id"] for q in queue for w in q["case"]["evidence"]}
    body = dict(protocol=PROTOCOL, basis_snapshot_id=manifest["snapshot_id"],
        basis_fingerprint=fingerprint, batch_size=size, questions=queue, blocked=blocked, history=history,
        entries=[e for e in records["entries"] if e["entry_id"] in selected],
        metadata=[e for e in records["entry_metadata"] if e["entry_id"] in selected],
        source_references=[e for e in records["source_references"] if e["entry_id"] in selected],
        coverage={"snapshot_entries": len(records["entries"]), "prepared_questions": len(queue),
                  "conflict_cases": sum(q["case"]["kind"] == "conflict" for q in queue),
                  "migration_exceptions": len(manifest.get("migration_exceptions", [])),
                  "automatic_conflict_discovery": False, "live_source_completeness": "not established"})
    session = dict(body, session_id="RS-" + digest(body))
    out = _outside(output, archive)
    require(not out.exists(), "Review session output exists")
    out.mkdir(parents=True, mode=0o700)
    try:
        write_json(out / "session.json", session)
        (out / "review.html").write_text(render(session), encoding="utf-8")
        os.chmod(out / "review.html", 0o600)
        write_json(out / "answers.template.json", dict(protocol=PROTOCOL, session_id=session["session_id"],
                   basis_snapshot_id=manifest["snapshot_id"], actor="", answers=[]))
        require(_fingerprint(archive) == fingerprint, "Snapshot changed during preparation")
    except Exception:
        shutil.rmtree(out)
        raise
    return {"status": "prepared", **session["coverage"], "session_id": session["session_id"]}


def _checked_session(session, manifest, records, fingerprint):
    require(session.get("protocol") == PROTOCOL, "Unsupported review session")
    body = {k: v for k, v in session.items() if k != "session_id"}
    require(session.get("session_id") == "RS-" + digest(body), "Changed review session")
    require(session["basis_snapshot_id"] == manifest["snapshot_id"] and session["basis_fingerprint"] == fingerprint,
            "Stale review; preserve answers and prepare a new preview")
    entries = {e["entry_id"]: e for e in records["entries"]}
    current, _, _ = _review_state(records)
    questions = {}
    for row in session["questions"]:
        case = normalize_case(row["case"], entries)
        qid = "RQ-" + digest(case)
        require(row["question_id"] == qid and qid not in questions and row["current"] == current.get(qid)
                and row["choices"] == list(CHOICES[case["kind"]]), "Question scope or prior answer changed")
        if "controls" in row:
            require(row["controls"] == _control_spec(case, records), "Form controls or identity scope changed")
        require(case["kind"] != "form" or "controls" in row, "A general form is missing its controls")
        questions[qid] = row
    selected = {w["entry_id"] for q in questions.values() for w in q["case"]["evidence"]}
    require(len(session["entries"]) == len(selected) and {e["entry_id"] for e in session["entries"]} == selected,
            "Displayed entry coverage changed")
    for entry in session["entries"]:
        require(entries.get(entry["entry_id"]) == entry, "Displayed source text changed")
    require(session["metadata"] == [e for e in records["entry_metadata"] if e["entry_id"] in selected]
            and session["source_references"] == [e for e in records["source_references"] if e["entry_id"] in selected],
            "Displayed source metadata changed")
    return questions


def _withdraw(records, target, event_id, ordinal):
    """Preflight the whole dependency closure; publish mutations only on success."""
    rules = {r["rule_id"]: r for r in records["correction_rules"]}
    require(target in rules and rules[target]["active"], "Unknown or inactive decision to replace")
    affected = {target}
    while True:
        extra = {rid for rid, r in rules.items() if r["active"]
                 and set(json.loads(r["payload_json"]).get("depends_on", [])) & affected}
        if extra <= affected:
            break
        affected |= extra
    require(all(rules[r]["operation"] in {"review_answer", "assert_relation"} or identity.owned(rules[r])
                for r in affected), "Replacement affects an unsupported dependent operation; nothing was applied")
    draft = deepcopy(records)
    for rule in draft["correction_rules"]:
        if rule["rule_id"] in affected:
            rule["active"] = 0
    kept = []
    for rel in draft["relationships"]:
        supports = json.loads(rel["rule_ids_json"])
        if set(supports) & affected:
            remaining = [r for r in supports if r not in affected and rules[r]["active"]]
            if not remaining:
                continue
            rel["rule_ids_json"] = json.dumps(remaining)
        kept.append(rel)
    draft["relationships"] = kept
    identity.undo_bindings(draft, [rules[r] for r in affected])
    draft["correction_rules"].append({"rule_id": "RV-" + digest([event_id, target]), "event_id": event_id,
        "ordinal": ordinal, "operation": "review_revoke", "active": 1,
        "payload_json": json.dumps({"protocol": PROTOCOL, "target": target,
                                    "affected_rules": sorted(affected), "depends_on": []}, sort_keys=True)})
    records.clear()
    records.update(draft)
    return sorted(affected)


def plan(archive, session_path, answers_path):
    manifest, records, fingerprint = read_snapshot(archive)
    session, reply = read_json(session_path), read_json(answers_path)
    require(isinstance(reply, dict) and set(reply) == {
        "protocol", "session_id", "basis_snapshot_id", "actor", "answers"}, "Unexpected answer fields")
    require(reply["protocol"] == PROTOCOL and reply["session_id"] == session["session_id"]
            and reply["basis_snapshot_id"] == session["basis_snapshot_id"], "Answers belong to another session")
    require(isinstance(reply["actor"], str) and bool(reply["actor"].strip())
            and isinstance(reply["answers"], list), "Reviewer and explicit answers required")
    event_id = "RE-" + digest(reply)
    prior = next((e for e in records["correction_events"] if e["event_id"] == event_id), None)
    if prior:
        require(prior["answer"] == encoded(reply).decode("utf-8") and prior["actor"] == reply["actor"], "Reused decision ID")
        return {"status": "already_applied", "event_id": event_id}, records, manifest
    questions = _checked_session(session, manifest, records, fingerprint)
    require(bool(reply["answers"]), "Blank answers are not decisions")
    records = deepcopy(records)
    impact, seen, new_rules = [], set(), []
    records["correction_events"].append({"event_id": event_id,
        "ordinal": max((e["ordinal"] for e in records["correction_events"]), default=-1) + 1,
        "actor": reply["actor"], "answer": encoded(reply).decode("utf-8")})
    known_cases = _review_state(records)[1]
    added_cases = [q["case"] for qid, q in questions.items() if qid not in known_cases and q["case"]["kind"] != "identity"]
    if added_cases:
        records["correction_rules"].append({"rule_id": "RQK-" + digest([event_id, added_cases]),
            "event_id": event_id, "ordinal": len(records["correction_rules"]), "operation": "review_queue", "active": 1,
            "payload_json": json.dumps({"protocol": PROTOCOL, "authority": "unresolved_candidate",
                "session_id": session["session_id"], "basis_snapshot_id": manifest["snapshot_id"],
                "cases": added_cases, "depends_on": []}, ensure_ascii=False, sort_keys=True)})
    for answer in reply["answers"]:
        required = {"question_id", "choice", "note", "previous_rule_id"}
        require(isinstance(answer, dict) and required <= set(answer) <= required | {"values"}, "Unexpected individual-answer fields")
        qid = answer["question_id"]
        require(qid in questions and qid not in seen, "Unknown or repeated question")
        seen.add(qid)
        row = questions[qid]
        case, choice, spec = row["case"], answer["choice"], row.get("controls")
        allowed = set(row["choices"]) | ({spec["action"]} if spec else set())
        require(isinstance(choice, str) and choice in allowed and isinstance(answer["note"], str), "Invalid answer choice")
        require(not row["blocked"] or choice in {"defer", "reopen"}, "Comparison is blocked")
        values = _answer_values(case, answer, spec)
        old = row["current"]["rule_id"] if row["current"] else None
        require(answer["previous_rule_id"] == old, "Replacement scope does not match displayed decision")
        prior_rules = {r["rule_id"]: deepcopy(r) for r in records["correction_rules"]}
        removed = _withdraw(records, old, event_id, len(records["correction_rules"])) if old else []
        withdrawn = []
        for rid in removed:
            prior_payload = json.loads(prior_rules[rid]["payload_json"])
            withdrawn.append({"rule_id": rid, "operation": prior_rules[rid]["operation"],
                              "title": prior_payload.get("case", {}).get("title", "Dependent correction"),
                              "choice": prior_payload.get("choice", prior_payload.get("decision"))})
        require(choice != "reopen" or old is not None, "No previous decision to reopen")
        effects = []
        if choice != "reopen":
            extra_deps = identity.dependencies(values, records) if choice == "group" else []
            deps = [] if choice == "defer" else sorted(set(case["depends_on"]) | set(extra_deps))
            active = {r["rule_id"] for r in records["correction_rules"] if r["active"]}
            require(set(deps) <= active, "Comparison dependency is inactive")
            rid = "RA-" + digest([event_id, qid])
            payload = {"protocol": PROTOCOL, "question_id": qid, "case": case,
                       "choice": choice, "note": answer["note"], "depends_on": deps}
            if values is not None:
                payload.update(controls_version=controls.VERSION, values=values)
                if choice == "group":
                    payload.update(identity_scope=spec["scope"], control_dependencies=extra_deps)
            records["correction_rules"].append({"rule_id": rid, "event_id": event_id,
                "ordinal": len(records["correction_rules"]), "operation": "review_answer", "active": 1,
                "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True)})
            new_rules.append(rid)
            if choice == "group":
                retired_ids = {json.loads(prior_rules[r]["payload_json"])["entity_id"]
                    for r in removed if identity.owned(prior_rules[r])
                    and json.loads(prior_rules[r]["payload_json"])["review_binding"]["created_entity"]}
                restorable = [e for e in spec["scope"]["entities"] if e["entity_id"] in retired_ids]
                effects = identity.bind_groups(records, spec["scope"], values, rid, event_id, restorable)
            elif case["kind"] == "relationship" and choice in {"confirm", "reject"}:
                a, b = case["source_entry_id"], case["target_entry_id"]
                require(not any(r["source_id"].removeprefix("entry:") == a
                    and r["target_id"].removeprefix("entry:") == b and r["relation"] == case["relation"]
                    and r["authority"] == "owner_confirmed" for r in records["relationships"]),
                    "An independently recorded relationship decision already exists")
                records["relationships"].append({"relationship_id": "RR-" + digest([event_id, qid]),
                    "source_id": a, "target_id": b, "relation": case["relation"], "authority": "owner_confirmed",
                    "status": "user_confirmed" if choice == "confirm" else "rejected",
                    "evidence_json": json.dumps(case["evidence"], ensure_ascii=False, sort_keys=True),
                    "rule_ids_json": json.dumps([rid]), "origin": "snapshot_review_answer"})
        item = {"question_id": qid, "title": case["title"], "kind": case["kind"],
                "choice": choice, "note": answer["note"], "withdrawn_rules": removed,
                "withdrawn_decisions": withdrawn, "evidence": case["evidence"]}
        if values is not None:
            item.update(values=values, effect=spec["effect"], identity_changes=effects)
        impact.append(item)
    from .machine_archive import confirmed_precedes_cycle
    require(not confirmed_precedes_cycle(records["relationships"]), "Confirmed chronology would contain a cycle")
    _review_state(records)
    active = {r["rule_id"] for r in records["correction_rules"] if r["active"]}
    require(set(new_rules) <= active, "Batch answers invalidate each other; split or revise the batch")
    receipt = {"protocol": PROTOCOL, "status": "preview", "event_id": event_id,
               "basis_snapshot_id": manifest["snapshot_id"], "basis_fingerprint": fingerprint,
               "session_sha256": digest(session), "answers_sha256": digest(reply),
               "plan_sha256": digest(records), "impact": impact,
               "unanswered": len(questions) - len(seen), "retained_proposals": len(added_cases), "source_text_changed": False}
    return receipt, records, manifest


def preview(archive, session, answers, output):
    from .review_html import render_preview
    receipt, _, _ = plan(archive, session, answers)
    if receipt["status"] == "already_applied":
        return receipt
    out = _outside(output, archive, Path(session).parent)
    require(not out.exists(), "Preview output exists")
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "preview.json", receipt)
    (out / "preview.html").write_text(render_preview(receipt), encoding="utf-8")
    os.chmod(out / "preview.html", 0o600)
    return {"status": "previewed", "answered": len(receipt["impact"]), "unanswered": receipt["unanswered"]}


@contextmanager
def _output_lock(output):
    import fcntl
    path = output.parent / ("." + output.name + ".review.lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def apply(archive, session, answers, preview_path, output, snapshot_version, confirmed=False):
    from . import machine_archive as ma
    from .structured_archive import connect, create_schema
    require(confirmed is True, "Explicit --confirm-user-answer is required")
    receipt, records, manifest = plan(archive, session, answers)
    if receipt["status"] == "already_applied":
        return receipt
    require(read_json(preview_path) == receipt, "Missing or stale checked preview")
    require(isinstance(snapshot_version, str) and snapshot_version.strip(), "Snapshot version required")
    out = _outside(output, archive, Path(session).parent, Path(preview_path).parent)
    out.parent.mkdir(parents=True, exist_ok=True)
    with _output_lock(out):
        if out.exists():
            existing, _, _ = read_snapshot(out)
            old_receipt, _, _ = plan(out, session, answers)
            require(old_receipt["status"] == "already_applied" and existing["parent_snapshot_id"] == manifest["snapshot_id"],
                    "Output already exists")
            return old_receipt
        stage = Path(tempfile.mkdtemp(prefix="." + out.name + "-review-", dir=out.parent))
        try:
            database = stage / "staging.sqlite3"
            db = connect(database)
            try:
                create_schema(db)
                db.execute("INSERT INTO metadata VALUES (?,?)", ("master_sha256", manifest["master_sha256"]))
                for table in ma.TABLES:
                    columns = [x[1] for x in db.execute(f"PRAGMA table_info({table})")]
                    sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
                    db.executemany(sql, [tuple(row[k] for k in columns) for row in records[table]])
                db.commit()
                require(not list(db.execute("PRAGMA foreign_key_check")), "Correction integrity failure")
            finally:
                db.close()
            candidate = stage / "snapshot"
            old_entities = {e["entity_id"] for e in ma.load_jsonl(Path(archive) / "entities.jsonl")}
            removed_entities = old_entities - {e["entity_id"] for e in records["entities"]}
            original_nodes = [n for n in ma.load_jsonl(Path(archive) / "nodes.jsonl") if n["node_id"] not in removed_entities]
            known_nodes = {n["node_id"] for n in ma.relationship_nodes(records, None)}
            extra = {"nodes": [{"id": n["node_id"], "type": n["node_type"], "label": n["label"]}
                                for n in original_nodes if n["node_id"] not in known_nodes]}
            write_json(stage / "extra-nodes.json", extra)
            ma.snapshot(database, candidate, snapshot_version, derived_graph=stage / "extra-nodes.json",
                        parent_snapshot_id=manifest["snapshot_id"], migration_exceptions=manifest.get("migration_exceptions", []))
            generated = {n["node_id"]: n for n in ma.load_jsonl(candidate / "nodes.jsonl")}
            generated.update({n["node_id"]: n for n in original_nodes})
            (candidate / "nodes.jsonl").unlink()
            ma.dump_jsonl(candidate / "nodes.jsonl", [generated[k] for k in sorted(generated)])
            changed_manifest = ma.load_json(candidate / "manifest.json")
            raw = (candidate / "nodes.jsonl").read_bytes()
            changed_manifest["files"]["nodes.jsonl"] = {
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "records": len(generated)}
            body = {k: v for k, v in changed_manifest.items() if k != "snapshot_id"}
            changed_manifest["snapshot_id"] = "AS-" + ma.digest_json(body)[:32]
            ma.dump_json(candidate / "manifest.json", changed_manifest)
            new_manifest, new_records, _ = read_snapshot(candidate)
            require(new_records["entries"] == records["entries"], "Source entry text changed")
            require(_fingerprint(archive) == receipt["basis_fingerprint"], "Source changed before publication")
            require(not out.exists(), "Output appeared concurrently")
            for path in candidate.iterdir():
                os.chmod(path, 0o600)
                with path.open("rb") as f:
                    os.fsync(f.fileno())
            os.rename(candidate, out)
            parent_fd = os.open(out.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            return {"status": "applied", "snapshot_id": new_manifest["snapshot_id"],
                    "answered": len(receipt["impact"]), "source_text_changed": False}
        finally:
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cases", type=Path)
    p.add_argument("--size", type=int, default=15)
    for name in ("preview", "apply"):
        p = commands.add_parser(name)
        for arg in ("archive", "session", "answers", "output"):
            p.add_argument("--" + arg, type=Path, required=True)
        if name == "apply":
            p.add_argument("--preview", type=Path, required=True)
            p.add_argument("--snapshot-version", required=True)
            p.add_argument("--confirm-user-answer", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.archive, args.output, args.cases, args.size)
        elif args.command == "preview":
            result = preview(args.archive, args.session, args.answers, args.output)
        else:
            result = apply(args.archive, args.session, args.answers, args.preview,
                           args.output, args.snapshot_version, args.confirm_user_answer)
        print(json.dumps(result))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
            "message": str(exc) if isinstance(exc, controls.ControlError) else "Review failed; inspect inputs locally."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
