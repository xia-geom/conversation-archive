"""Checked finite-scope identity grouping and reversal of this writer's bindings.

No name matching or natural-language interpretation occurs here. A group is an
explicit user assertion over displayed mention IDs, never over future mentions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .review_controls import ControlError, identity_form, need, validate_values

VERSION = "review-identity-1.0"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _payload(rule):
    return json.loads(rule["payload_json"])


def owned(rule):
    return (rule["operation"] == "bind_mentions"
            and _payload(rule).get("review_binding", {}).get("version") == VERSION)


def scope_for(case, records):
    """Recover a question definition from its registry or immutable review history."""
    qid = case.get("source_question_id")
    question = next((q for q in records["unresolved_questions"] if q["question_id"] == qid), None)
    if question is None:
        for rule in records["correction_rules"]:
            payload = _payload(rule)
            scope = payload.get("identity_scope")
            if scope and scope["question"]["question_id"] == qid:
                question = scope["question"]
                break
    need(question is not None, "Identity grouping needs an existing source question")
    refs = json.loads(question["evidence_json"])
    index = {m["mention_id"]: m for m in records["mentions"]}
    mentions = []
    for ref in refs:
        m = index.get(ref["mention_id"])
        need(m is not None and m["entry_id"] == ref["entry_id"]
             and m["kind"] == question["kind"], "Identity reference no longer matches its question")
        mentions.append(deepcopy(m))
    need(0 < len(mentions) <= 100 and len({m["mention_id"] for m in mentions}) == len(mentions),
         "Invalid or oversized identity question")
    witness = lambda x: (x["entry_id"], x["start"], x["end"], x["quote"])
    need({witness(m) for m in mentions} == {witness(e) for e in case["evidence"]},
         "Identity form does not match the displayed quotations")
    # Offer identities already represented on this card. No archive-wide person search.
    ids = {m["entity_id"] for m in mentions if m["entity_id"]}
    entities = [deepcopy(e) for e in records["entities"] if e["entity_id"] in ids]
    need({e["entity_id"] for e in entities} == ids
         and all(e["kind"] == question["kind"] for e in entities), "Missing or mismatched identity target")
    return {"question": deepcopy(question), "mentions": mentions, "entities": entities}


def dependencies(values, records):
    result = set()
    groups = values["identity"]["groups"]
    selected = {mid for g in groups for mid in g["items"]}
    targets = {g["target"] for g in groups if g["target"]}
    active = {r["rule_id"] for r in records["correction_rules"] if r["active"]}
    for rel in records["relationships"]:
        if (rel["relation"] == "refers_to" and rel["source_id"] in selected
                and rel["status"] == "user_confirmed"):
            result.update(json.loads(rel["rule_ids_json"]))
    for rule in records["correction_rules"]:
        if rule["active"] and owned(rule):
            op = _payload(rule)
            if op["entity_id"] in targets and op["review_binding"]["created_entity"]:
                result.add(rule["rule_id"])
    need(result <= active, "Identity context depends on an inactive correction")
    return sorted(result)


def bind_groups(records, scope, values, parent_rule, event_id, restorable=()):
    """Mutate only a transaction's working copy; caller publishes a checked successor."""
    validate_values(identity_form(scope), values)
    groups = values["identity"]["groups"]
    need(bool(groups), "Choose at least one group, or use insufficient evidence")
    mentions = {m["mention_id"]: m for m in records["mentions"]}
    frozen = {m["mention_id"]: m for m in scope["mentions"]}
    question = scope["question"]
    effects = []
    for number, group in enumerate(groups):
        entity_id = group["target"] or ("entity:" + question["kind"] + ":review-"
                      + _digest([parent_rule, number, group["items"]])[:24])
        entity = next((e for e in records["entities"] if e["entity_id"] == entity_id), None)
        restored = next((e for e in restorable if e["entity_id"] == entity_id), None)
        if group["target"] is not None:
            need((entity is not None or restored is not None)
                 and (entity or restored)["kind"] == question["kind"], "Selected identity is no longer available")
        selected = []
        for mid in group["items"]:
            m = mentions[mid]
            need(m["kind"] == question["kind"] and m["entry_id"] == frozen[mid]["entry_id"], "Identity scope changed")
            need(not m["entity_id"] or m["entity_id"] == entity_id,
                 "Group conflicts with an existing assignment; reopen that decision first")
            if m["entity_id"] is None:
                selected.append(m)
        if not selected:
            effects.append({"entity_id": entity_id, "bound_mentions": [], "preserved_existing": group["items"]})
            continue
        created = entity is None
        if created:
            entity = deepcopy(restored) if restored else {
                "entity_id": entity_id, "kind": question["kind"], "label": group["label"],
                "authority": "owner_confirmed"}
            records["entities"].append(entity)
        rid = "RB-" + _digest([parent_rule, number])
        op = {"op": "bind_mentions", "rule_id": rid, "depends_on": [parent_rule],
              "kind": question["kind"], "entity_id": entity_id, "entity_label": entity["label"],
              "entry_ids": sorted({m["entry_id"] for m in selected}),
              "mention_ids": [m["mention_id"] for m in selected], "question_id": question["question_id"],
              "review_binding": {"version": VERSION, "parent_rule": parent_rule,
                                 "before": deepcopy(selected), "created_entity": created,
                                 "question": deepcopy(question)}}
        records["correction_rules"].append({"rule_id": rid, "event_id": event_id,
            "ordinal": len(records["correction_rules"]), "operation": "bind_mentions", "active": 1,
            "payload_json": json.dumps(op, ensure_ascii=False, sort_keys=True)})
        for m in selected:
            m["entity_id"], m["status"] = entity_id, "owner_confirmed"
            evidence = {k: m[k] for k in ("entry_id", "start", "end", "quote")}
            records["relationships"].append({"relationship_id": "RI-" + _digest([rid, m["mention_id"]]),
                "source_id": m["mention_id"], "target_id": entity_id, "relation": "refers_to",
                "authority": "owner_confirmed", "status": "user_confirmed",
                "evidence_json": json.dumps([evidence], ensure_ascii=False, sort_keys=True),
                "rule_ids_json": json.dumps([rid]), "origin": "snapshot_review_binding"})
        effects.append({"entity_id": entity_id, "label": entity["label"], "created": created,
                        "bound_mentions": op["mention_ids"]})
    if all(mentions[m["mention_id"]]["entity_id"] is not None for m in scope["mentions"]):
        records["unresolved_questions"] = [q for q in records["unresolved_questions"]
                                           if q["question_id"] != question["question_id"]]
    return effects


def validate_bindings(records):
    rules = {r["rule_id"]: r for r in records["correction_rules"]}
    mentions = {m["mention_id"]: m for m in records["mentions"]}
    entities = {e["entity_id"]: e for e in records["entities"]}
    expected = {}
    for rule in records["correction_rules"]:
        if rule["active"] and rule["operation"] == "review_answer":
            answer = _payload(rule)
            if answer.get("choice") == "group":
                scope = answer["identity_scope"]
                validate_values(identity_form(scope), answer["values"])
                frozen = {m["mention_id"]: m for m in scope["mentions"]}
                for number, group in enumerate(answer["values"]["identity"]["groups"]):
                    target = group["target"] or ("entity:" + scope["question"]["kind"] + ":review-"
                        + _digest([rule["rule_id"], number, group["items"]])[:24])
                    for mid in group["items"]:
                        m = mentions.get(mid)
                        need(m is not None and m["entity_id"] == target
                             and all(m[k] == frozen[mid][k] for k in frozen[mid] if k not in {"entity_id", "status"}),
                             "Active grouping differs from its displayed scope or assignment")
    for rule in records["correction_rules"]:
        if not owned(rule):
            continue
        op = _payload(rule)
        meta = op["review_binding"]
        need(op["rule_id"] == rule["rule_id"] and op["depends_on"] == [meta["parent_rule"]]
             and meta["parent_rule"] in rules, "Invalid identity binding support")
        parent = rules[meta["parent_rule"]]
        answer = _payload(parent)
        need(parent["operation"] == "review_answer" and answer.get("choice") == "group"
             and answer.get("case", {}).get("kind") == "identity", "Identity binding lacks a grouping answer")
        before = meta["before"]
        need(isinstance(before, list) and [m["mention_id"] for m in before] == op["mention_ids"]
             and all(m["entity_id"] is None for m in before), "Invalid prior identity states")
        for old in before:
            current = mentions.get(old["mention_id"])
            need(current is not None and all(current[k] == old[k] for k in old if k not in {"entity_id", "status"}),
                 "Preserved identity evidence changed")
        if not rule["active"]:
            continue
        need(parent["active"] and op["entity_id"] in entities, "Active binding has missing authority or entity")
        for old in before:
            current = mentions[old["mention_id"]]
            need(current["entity_id"] == op["entity_id"] and current["status"] == "owner_confirmed",
                 "Active identity projection differs from its decision")
            expected[(rule["rule_id"], old["mention_id"])] = op["entity_id"]
    observed = {}
    for rel in records["relationships"]:
        if rel["origin"] != "snapshot_review_binding":
            continue
        supports = json.loads(rel["rule_ids_json"])
        need(len(supports) == 1, "Invalid identity projection support")
        key = (supports[0], rel["source_id"])
        need(key in expected and key not in observed and rel["target_id"] == expected[key]
             and rel["relation"] == "refers_to" and rel["authority"] == "owner_confirmed"
             and rel["status"] == "user_confirmed", "Invalid identity projection")
        m = mentions[rel["source_id"]]
        need(json.loads(rel["evidence_json"]) == [{k: m[k] for k in ("entry_id", "start", "end", "quote")}],
             "Identity projection quotation changed")
        observed[key] = rel["target_id"]
    need(observed == expected, "Missing active identity projection")


def undo_bindings(records, withdrawn):
    """Caller has removed withdrawn projection edges in a private working copy."""
    created, questions = set(), {}
    mentions = {m["mention_id"]: m for m in records["mentions"]}
    for rule in withdrawn:
        if not owned(rule):
            continue
        op = _payload(rule)
        meta = op["review_binding"]
        for before in meta["before"]:
            m = mentions[before["mention_id"]]
            need(m["entity_id"] == op["entity_id"] and m["status"] == "owner_confirmed",
                 "Cannot reverse an identity changed by another writer")
            need(not any(r["relation"] == "refers_to" and r["source_id"] == m["mention_id"]
                         and r["status"] == "user_confirmed" for r in records["relationships"]),
                 "Identity still has independent binding support")
            m.update(deepcopy(before))
        if meta["created_entity"]:
            created.add(op["entity_id"])
        questions[meta["question"]["question_id"]] = meta["question"]
    for eid in created:
        need(not any(m["entity_id"] == eid for m in mentions.values())
             and not any(eid in {r["source_id"], r["target_id"]} for r in records["relationships"]),
             "Identity still has external uses; review those dependencies first")
    records["entities"] = [e for e in records["entities"] if e["entity_id"] not in created]
    existing = {q["question_id"] for q in records["unresolved_questions"]}
    for qid, question in questions.items():
        if qid not in existing:
            records["unresolved_questions"].append(deepcopy(question))
    return created
