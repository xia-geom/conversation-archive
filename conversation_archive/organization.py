"""Evidence-linked organization sidecar; no model calls or canonical-master writes."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

VERSION = "1.0"
KINDS = {"person", "organization", "place", "project", "event", "period", "topic"}
RELATIONS = {"continues", "revises", "precedes", "responds_to", "reported_cause"}


class OrganizationError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load(path):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise OrganizationError("Duplicate JSON key")
            result[k] = v
        return result
    def constant(_):
        raise OrganizationError("Non-finite JSON number")
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=pairs, parse_constant=constant)


def require(condition, message):
    if not condition:
        raise OrganizationError(message)


def keys(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value)
            and set(value) <= set(required) | set(optional), "Unexpected object fields")


def strings(values):
    return (isinstance(values, list) and bool(values)
            and all(isinstance(x, str) and x.strip() for x in values)
            and len(set(values)) == len(values))


def normal(text):
    return " ".join(text.casefold().split())


def validate_data(data):
    keys(data, ("version", "entries", "catalog", "proposals"))
    require(data["version"] == VERSION, "Unsupported organization input version")
    require(isinstance(data["entries"], list) and data["entries"], "Entries required")
    entries = {}
    for e in data["entries"]:
        keys(e, ("entry_id", "text"), ("source",))
        require(isinstance(e["entry_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]+", e["entry_id"]), "Unsafe entry ID")
        require(e["entry_id"] not in entries and isinstance(e["text"], str), "Duplicate entry or invalid text")
        entries[e["entry_id"]] = e
    require(isinstance(data["catalog"], list), "Catalog must be an array")
    seen = set()
    for c in data["catalog"]:
        keys(c, ("kind", "label", "family"))
        require(c["kind"] in KINDS and all(isinstance(c[k], str) and c[k].strip() for k in ("label", "family")), "Invalid catalog term")
        key = (c["kind"], normal(c["label"]))
        require(key not in seen, "Duplicate catalog term; one candidate family per term")
        seen.add(key)
    require(isinstance(data["proposals"], list), "Proposals must be an array")
    seen = set()
    for p in data["proposals"]:
        keys(p, ("proposal_id", "relation", "source", "target", "reason", "evidence"))
        require(isinstance(p["proposal_id"], str) and p["proposal_id"].strip()
                and p["proposal_id"] not in seen, "Duplicate or invalid proposal ID")
        seen.add(p["proposal_id"])
        require(p["relation"] in RELATIONS and p["source"] in entries
                and p["target"] in entries and p["source"] != p["target"], "Invalid relation endpoints")
        require(isinstance(p["reason"], str) and p["reason"].strip(), "Relation needs a reason")
        require(isinstance(p["evidence"], list), "Evidence must be an array")
        witnesses = set()
        for q in p["evidence"]:
            keys(q, ("entry_id", "start", "end", "quote"))
            require(q["entry_id"] in (p["source"], p["target"]), "Evidence outside relation endpoints")
            text = entries[q["entry_id"]]["text"]
            require(type(q["start"]) is int and type(q["end"]) is int
                    and 0 <= q["start"] < q["end"] <= len(text)
                    and text[q["start"]:q["end"]] == q["quote"], "Evidence span mismatch")
            witnesses.add(q["entry_id"])
        require(witnesses == {p["source"], p["target"]}, "Cite both endpoints; a quote alone does not prove a relation")
    return entries


def mentions(data):
    """Literal catalog matches are observations, never automatic entity resolution."""
    found = []
    for e in data["entries"]:
        for c in data["catalog"]:
            pattern = r"\s+".join(re.escape(w) for w in c["label"].split())
            if c["label"][0].isalnum():
                pattern = r"(?<!\w)" + pattern
            if c["label"][-1].isalnum():
                pattern += r"(?!\w)"
            for match in re.finditer(pattern, e["text"], re.I):
                witness = dict(entry_id=e["entry_id"], entry_sha256=digest({"entry_id": e["entry_id"], "text": e["text"]}), kind=c["kind"],
                               start=match.start(), end=match.end(), quote=match[0])
                found.append(dict(witness, mention_id="M-" + digest(witness)[:24],
                                  label=c["label"], family=c["family"], source=e.get("source")))
    return sorted(found, key=lambda m: (m["entry_id"], m["start"], m["kind"], m["mention_id"]))


def active_rules(state):
    rules, revoked = {}, set()
    for event in state["events"]:
        for rule in event["operations"]:
            require(rule["rule_id"] not in rules, "Rule IDs are append-only and unique")
            if rule["op"] == "revoke":
                require(rule["target"] in rules and rules[rule["target"]]["op"] != "revoke", "Unknown revocation target")
                revoked.add(rule["target"])
            else:
                require(all(dep in rules and rules[dep]["op"] != "revoke" for dep in rule["depends_on"]), "Dependencies must reference earlier rules")
            rules[rule["rule_id"]] = rule
    active = {}
    for rid, r in rules.items():
        if r["op"] != "revoke" and rid not in revoked and all(dep in active for dep in r["depends_on"]):
            active[rid] = r
    return active


def graph(state):
    data = state["data"]
    entries = validate_data(data)
    found = mentions(data)
    by_id = {m["mention_id"]: m for m in found}
    assignments, entities, deferred, dispositions, contexts = {}, {}, set(), {}, {}
    active = active_rules(state)
    for rid, r in active.items():
        if r["op"] == "bind":
            require(set(r["entry_ids"]) <= set(entries), "Rule scope contains unknown entries")
            selected = [m for m in found if m["kind"] == r["kind"] and m["entry_id"] in r["entry_ids"]
                        and normal(m["label"]) in {normal(a) for a in r["aliases"]}
                        and ("mention_ids" not in r or m["mention_id"] in r["mention_ids"])]
            if "mention_ids" in r:
                require(set(r["mention_ids"]) == {m["mention_id"] for m in selected}, "Mention selector outside declared scope")
            require(bool(selected), "Rule matches no mentions")
            target = "entity:" + r["kind"] + ":" + r["entity_id"]
            require(target not in entities or entities[target]["label"] == r["entity_label"], "Conflicting entity labels")
            entities[target] = dict(node_id=target, kind=r["kind"], label=r["entity_label"])
            for m in selected:
                mid = m["mention_id"]
                require(mid not in assignments or assignments[mid]["entity"] == target, "Conflicting identity bindings; revoke or narrow the old rule")
                assignments.setdefault(mid, {"entity": target, "rule_ids": []})["rule_ids"].append(rid)
        elif r["op"] == "associate":
            require(set(r["entry_ids"]) <= set(entries), "Context rule contains unknown entries")
            target = "entity:" + r["kind"] + ":" + r["entity_id"]
            require(target not in entities or entities[target]["label"] == r["entity_label"], "Conflicting entity labels")
            entities[target] = dict(node_id=target, kind=r["kind"], label=r["entity_label"])
            for eid in r["entry_ids"]:
                contexts.setdefault((eid, target), []).append(rid)
        elif r["op"] == "defer":
            require(set(r["mention_ids"]) <= set(by_id), "Unknown deferred mention")
            deferred.update(r["mention_ids"])
        elif r["op"] == "relation":
            require(r["proposal_id"] in {p["proposal_id"] for p in data["proposals"]}, "Unknown relation proposal")
            key = r["proposal_id"]
            require(key not in dispositions or dispositions[key]["accept"] == r["accept"], "Conflicting relation decisions")
            dispositions.setdefault(key, {"accept": r["accept"], "rule_ids": []})["rule_ids"].append(rid)
    edges = [dict(source=m["entry_id"], target=m["mention_id"], relation="mentions",
                  status="observed_text", evidence=[m]) for m in found]
    for mid, value in assignments.items():
        edges.append(dict(source=mid, target=value["entity"], relation="refers_to",
                          status="user_confirmed", rule_ids=value["rule_ids"]))
    for (eid, target), rules in contexts.items():
        edges.append(dict(source=eid, target=target, relation="associated_with",
                          status="user_confirmed", rule_ids=rules))
    for p in data["proposals"]:
        decision = dispositions.get(p["proposal_id"])
        edges.append(dict(source=p["source"], target=p["target"], relation=p["relation"],
                          proposal_id=p["proposal_id"], evidence=p["evidence"], reason=p["reason"],
                          status=("user_confirmed" if decision["accept"] else "rejected") if decision else "proposed",
                          rule_ids=decision["rule_ids"] if decision else []))
    # Only explicitly confirmed precedence is a strict order; do not infer it from timestamps.
    order = defaultdict(list)
    for e in edges:
        if e["relation"] == "precedes" and e["status"] == "user_confirmed":
            order[e["source"]].append(e["target"])
    indegree = {eid: 0 for eid in entries}
    for targets in order.values():
        for target in targets:
            indegree[target] += 1
    ready = deque(eid for eid, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for target in order[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    require(visited == len(entries), "Confirmed precedence contains a cycle")
    return dict(version=VERSION, state_sha256=digest(state), entries=data["entries"], mentions=found,
                entries_without_mentions=sorted(set(entries) - {m["entry_id"] for m in found}),
                organization_complete_claimed=False,
                entities=list(entities.values()), edges=edges, assignments=assignments,
                deferred=sorted(deferred - set(assignments)), active_rule_ids=list(active),
                limitations=["Entry-level evidence, not revalidated raw-message truth.",
                             "Catalog families are hypotheses; chronology is not causation."])


def questions(state, limit=3, max_items=12):
    require(type(limit) is int and limit > 0 and type(max_items) is int and max_items > 0, "Positive question limits required")
    g = graph(state)
    entry_text = {e["entry_id"]: e["text"] for e in g["entries"]}
    pending = [m for m in g["mentions"] if m["mention_id"] not in g["assignments"] and m["mention_id"] not in g["deferred"]]
    groups = defaultdict(list)
    for m in pending:
        groups[m["kind"], m["family"]].append(m)
    options = []
    for (kind, family), members in sorted(groups.items()):
        for start in range(0, len(members), max_items):
            group = []
            for m in members[start:start + max_items]:
                text = entry_text[m["entry_id"]]
                lo, hi = max(0, m["start"] - 100), min(len(text), m["end"] + 140)
                group.append(dict(m, context=text[lo:hi], context_start=lo, context_end=hi, context_excerpt_only=(lo > 0 or hi < len(text))))
            if len({m["entry_id"] for m in members}) < 2:
                continue
            # Never infer an answer for the other chunks of a large family.
            mids = [m["mention_id"] for m in group]
            options.append(dict(question_id="Q-" + digest([kind, mids])[:24], kind=kind,
                prompt=f"Which {kind} does each reference mean? Group only those that refer to the same {kind}; separate the others or mark them unknown.",
                hypothesis_family=family, evidence=group, affected_entry_ids=sorted({m["entry_id"] for m in group}),
                handles=mids, effort_units=1 + len(group) / 4, family_mentions=len(members),
                family_mentions_not_shown=len(members) - len(group),
                options=["same entity", "partition into groups", "some known, some unknown", "defer"],
                answer_scope="Only the references shown. No identity merge of entries."))
    for e in g["edges"]:
        if e["status"] == "proposed":
            options.append(dict(question_id="Q-" + digest(e)[:24], kind="relation",
                prompt=f"Is the proposed {e['relation']} link from {e['source']} to {e['target']} supported? The quoted passages do not by themselves settle this.",
                proposal_id=e["proposal_id"], evidence=e["evidence"],
                affected_entry_ids=[e["source"], e["target"]], handles=["relation:" + e["proposal_id"]],
                effort_units=2, options=["confirm", "reject", "leave pending"]))
    # Greedy marginal-coverage heuristic. No calibrated entropy/probability claim.
    picked, covered = [], set()
    while options and len(picked) < limit:
        def rank(q):
            gain = len(set(q["affected_entry_ids"]) - {x[1] for x in covered if x[0] == q["kind"]})
            return (-gain / q["effort_units"], -len(q["affected_entry_ids"]), q["question_id"])
        q = min(options, key=rank)
        options.remove(q)
        gain = len(set(q["affected_entry_ids"]) - {x[1] for x in covered if x[0] == q["kind"]})
        if not gain:
            continue
        q.update(priority_score=round(gain / q["effort_units"], 4),
                 marginal_entry_facets=gain, ranking="new entry/facet coverage / estimated effort; not measured information gain")
        picked.append(q)
        covered.update((q["kind"], eid) for eid in q["affected_entry_ids"])
    return picked


def validate_event(event):
    keys(event, ("event_id", "expected_state_sha256", "actor", "answer", "operations"))
    require(all(isinstance(event[k], str) and event[k].strip() for k in ("event_id", "expected_state_sha256", "actor", "answer")), "Record event identity, actor, answer, and expected state")
    require(isinstance(event["operations"], list) and event["operations"], "Empty correction")
    for r in event["operations"]:
        require(isinstance(r, dict), "Correction operation must be an object")
        common = ("op", "rule_id", "depends_on")
        if r.get("op") == "bind":
            keys(r, common + ("kind", "aliases", "entry_ids", "entity_id", "entity_label"), ("mention_ids",))
            if "mention_ids" in r:
                require(strings(r["mention_ids"]), "Nonempty exact mention selector required")
            require(r["kind"] in KINDS and strings(r["aliases"]) and strings(r["entry_ids"]), "Explicit nonempty alias and entry scopes required")
            require(all(isinstance(r[k], str) and r[k].strip() for k in ("entity_id", "entity_label")), "Entity identity required")
        elif r.get("op") == "associate":
            keys(r, common + ("kind", "entry_ids", "entity_id", "entity_label"))
            require(r["kind"] in KINDS and strings(r["entry_ids"]), "Explicit context scope required")
            require(all(isinstance(r[k], str) and r[k].strip() for k in ("entity_id", "entity_label")), "Context identity required")
        elif r.get("op") == "relation":
            keys(r, common + ("proposal_id", "accept"))
            require(type(r["accept"]) is bool and isinstance(r["proposal_id"], str), "Relation needs explicit boolean decision")
        elif r.get("op") == "defer":
            keys(r, common + ("mention_ids",))
            require(strings(r["mention_ids"]), "Explicit deferred mentions required")
        elif r.get("op") == "revoke":
            keys(r, ("op", "rule_id", "target"))
            require(isinstance(r["target"], str), "Revocation target required")
        else:
            raise OrganizationError("Unknown correction operation")
        require(isinstance(r["rule_id"], str) and r["rule_id"].strip(), "Rule ID required")
        if r["op"] != "revoke":
            require(isinstance(r["depends_on"], list) and (not r["depends_on"] or strings(r["depends_on"])), "Invalid dependencies")


def preview(state, event):
    validate_event(event)
    for old in state["events"]:
        if old["event_id"] == event["event_id"]:
            require(old == event, "Event ID reused with different content")
            return state, {"status": "already_applied", "state_sha256": digest(state)}
    require(event["expected_state_sha256"] == digest(state), "Stale answer: regenerate its impact preview")
    before = graph(state)
    after_state = deepcopy(state)
    after_state["events"].append(deepcopy(event))
    after_state["events_sha256"] = digest(after_state["events"])
    after = graph(after_state)
    for rule in event["operations"]:
        if rule["op"] != "revoke":
            require(rule["rule_id"] in after["active_rule_ids"], "New rule depends on revoked or inactive support")
    changed = sorted(mid for mid in set(before["assignments"]) | set(after["assignments"])
                     if before["assignments"].get(mid) != after["assignments"].get(mid))
    lookup = {m["mention_id"]: m for m in after["mentions"]}
    old_rel = {e["proposal_id"]: e for e in before["edges"] if "proposal_id" in e}
    changed_rel = [e for e in after["edges"] if "proposal_id" in e and e != old_rel[e["proposal_id"]]]
    changed_defer = sorted(set(before["deferred"]) ^ set(after["deferred"]))
    old_context = {digest(e): e for e in before["edges"] if e["relation"] == "associated_with"}
    new_context = {digest(e): e for e in after["edges"] if e["relation"] == "associated_with"}
    changed_context = [old_context.get(k, new_context.get(k)) for k in sorted(set(old_context) ^ set(new_context))]
    return after_state, dict(status="ready", changed_mention_ids=changed,
        affected_entry_ids=sorted({lookup[mid]["entry_id"] for mid in changed + changed_defer}
                                  | {e[k] for e in changed_rel for k in ("source", "target")}
                                  | {e["source"] for e in changed_context}),
        changed_relations=changed_rel, changed_deferred_mentions=changed_defer, changed_context_edges=changed_context,
        before_assignments={mid: before["assignments"].get(mid) for mid in changed},
        after_assignments={mid: after["assignments"].get(mid) for mid in changed},
        active_rule_ids=after["active_rule_ids"], state_sha256=digest(after_state),
        canonical_entries_unchanged=True)


def atomic_write(path, value):
    fd, name = tempfile.mkstemp(prefix=".organization-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked(run):
    import fcntl  # POSIX advisory lock, not a master-writer lock.
    with (run / ".organization.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OrganizationError("Another writer owns this organization run") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_state(run):
    state = load(run / "state.json")
    keys(state, ("version", "data", "data_sha256", "events", "events_sha256"))
    require(state["version"] == VERSION and digest(state["data"]) == state["data_sha256"], "Input snapshot changed")
    require(isinstance(state["events"], list) and digest(state["events"]) == state["events_sha256"], "Invalid or changed event history")
    # Replay expected-state hashes: detect accidental edits to old decisions.
    previous = dict(state, events=[], events_sha256=digest([]))
    seen = set()
    for event in state["events"]:
        validate_event(event)
        require(event["event_id"] not in seen and event["expected_state_sha256"] == digest(previous), "Decision history changed")
        seen.add(event["event_id"])
        new_events = previous["events"] + [event]
        previous = dict(previous, events=new_events, events_sha256=digest(new_events))
    graph(state)
    return state


def prepare(data, run):
    validate_data(data)
    state = dict(version=VERSION, data=deepcopy(data), data_sha256=digest(data), events=[], events_sha256=digest([]))
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_write(run / "state.json", state)
    return dict(state_sha256=digest(state), entries=len(data["entries"]), mentions=len(mentions(data)))


def apply(run, event):
    run = Path(run)
    with locked(run):
        updated, report = preview(read_state(run), event)
        if report["status"] != "already_applied":
            atomic_write(run / "state.json", updated)
        return report


def render_questions(items):
    lines = ["# Clarification questions", "", "Priority scores are workload heuristics, not probabilities."]
    if not items:
        lines.append("No questions in this queue. This does not establish complete organization.")
    for number, q in enumerate(items, 1):
        lines.extend(["", f"## {number}. {q['kind']}", "", q["prompt"], "",
                      f"Affected entries: {', '.join(q['affected_entry_ids'])}", ""])
        for evidence in q["evidence"]:
            text = evidence.get("context", evidence["quote"])
            fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
            lines.extend([f"Entry {evidence['entry_id']} (excerpt; exact evidence retained in JSON):", fence + "text", text, fence])
        lines.extend(["", "Answer choices: " + "; ".join(q["options"]),
                      "Entries remain separate. Only the confirmed relationship changes."])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    for name in ("questions", "graph", "preview", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--run", type=Path, required=True)
        if name == "questions":
            p.add_argument("--limit", type=int, default=3)
            p.add_argument("--format", choices=("json", "markdown"), default="json")
        if name in ("preview", "apply"):
            p.add_argument("--decision", type=Path, required=True)
        if name == "apply":
            p.add_argument("--confirm-user-answer", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(load(args.input), args.run)
        elif args.command == "apply":
            require(args.confirm_user_answer, "Applying corrections requires --confirm-user-answer; model proposals are not user confirmation")
            result = apply(args.run, load(args.decision))
        else:
            state = read_state(args.run)
            result = (questions(state, args.limit) if args.command == "questions" else
                      graph(state) if args.command == "graph" else preview(state, load(args.decision))[1])
        if args.command == "questions" and args.format == "markdown":
            print(render_questions(result), end="")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
