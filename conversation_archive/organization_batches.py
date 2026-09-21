"""Prepare contextual question batches; compile one actual user reply into scoped rules.

No model calls, semantic discovery, or canonical-master writes. Batch format 1.0
is separate from the unchanged organization input/state format 1.0.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import html
import json
from pathlib import Path
import re

from . import organization as o

BATCH_VERSION = "1.0"
DEFAULT_SIZE = 15
DEFAULT_CONTEXT_CHARS = 240


def _bounds(max_items, context_chars):
    o.require(type(max_items) is int and 1 <= max_items <= 26, "Use 1–26 references per question")
    o.require(type(context_chars) is int and 80 <= context_chars <= 1200, "Context length must be 80–1200 characters")


def _card(witness, entries, contexts, width):
    """Copy exact entry text; neither a title nor an excerpt is an inferred fact."""
    text = entries[witness["entry_id"]]["text"]
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    heading = re.match(r"^#{1,6}\s+" + re.escape(witness["entry_id"]) + r"\b[\s—:–-]*(.*)", first)
    title = (heading[1] if heading else first) or "Untitled entry"
    lo = max(0, witness["start"] - width // 3)
    hi = min(len(text), lo + width)
    lo = max(0, min(lo, hi - width))
    associations = contexts.get(witness["entry_id"], [])
    return dict(witness, title=title[:100], title_excerpt_only=len(title) > 100,
                title_origin="entry_heading" if heading else "entry_opening_excerpt",
                context=text[lo:hi], context_start=lo, context_end=hi,
                context_excerpt_only=lo > 0 or hi < len(text),
                confirmed_context=associations[:4], confirmed_context_not_shown=max(0, len(associations) - 4))


def question_pool(state, max_items=12, context_chars=DEFAULT_CONTEXT_CHARS):
    """Scan ALL supplied entries/catalog matches before ranking; no new names inferred."""
    _bounds(max_items, context_chars)
    g = o.graph(state)
    entries = {e["entry_id"]: e for e in g["entries"]}
    entities = {e["node_id"]: e for e in g["entities"]}
    by_id = {m["mention_id"]: m for m in g["mentions"]}
    contexts = defaultdict(list)
    for edge in g["edges"]:
        if edge["relation"] not in ("associated_with", "refers_to"):
            continue
        eid = (by_id[edge["source"]]["entry_id"] if edge["relation"] == "refers_to" else edge["source"])
        entity = entities[edge["target"]]
        item = dict(kind=entity["kind"], label=entity["label"], entity=entity["node_id"])
        if item not in contexts[eid]:
            contexts[eid].append(item)
    groups, known = defaultdict(list), defaultdict(list)
    for m in g["mentions"]:
        family = (m["kind"], m["family"])
        if m["mention_id"] in g["assignments"]:
            known[family].append(m)
        elif m["mention_id"] not in g["deferred"]:
            groups[family].append(m)
    pool = []
    for (kind, family), members in sorted(groups.items()):
        anchors = defaultdict(list)
        for m in known[kind, family]:
            anchors[g["assignments"][m["mention_id"]]["entity"]].append(m)
        if len({m["entry_id"] for m in members}) < 2 and not anchors:
            continue
        references = []
        # Show up to three possible known identities, two source examples each.
        # Omitted identities disable an implicit "same as the only shown one".
        for n, (target, supports) in enumerate(sorted(anchors.items())[:3], 1):
            unique_entries, examples = set(), []
            for m in supports:
                if m["entry_id"] not in unique_entries and len(examples) < 2:
                    examples.append(_card(m, entries, contexts, context_chars))
                    unique_entries.add(m["entry_id"])
            support_rule = g["assignments"][supports[0]["mention_id"]]["rule_ids"][0]
            references.append(dict(code=f"R{n}", entity=target, label=entities[target]["label"],
                                   evidence=examples, support_rule_id=support_rule,
                                   additional_support_mentions=len(supports) - len(examples)))
        for start in range(0, len(members), max_items):
            chunk = members[start:start + max_items]
            cards = [dict(_card(m, entries, contexts, context_chars), reference_code=chr(65 + i))
                     for i, m in enumerate(chunk)]
            mids = [m["mention_id"] for m in chunk]
            ids = sorted({m["entry_id"] for m in chunk})
            aliases = sorted({m["label"] for m in members})
            pool.append(dict(question_id="Q-" + o.digest([kind, mids])[:24], kind=kind,
                title=" / ".join(aliases[:3]) + " — " + kind,
                prompt=f"Which references identify the same {kind}? Compare the candidate excerpts with any confirmed references below.",
                hypothesis_family=family, evidence=cards, known_references=references,
                known_entities_not_shown=max(0, len(anchors) - len(references)),
                affected_entry_ids=ids, handles=mids,
                effort_units=1 + (len(cards) + sum(len(r["evidence"]) for r in references)) / 4,
                family_mentions=len(members), family_mentions_not_shown=len(members) - len(chunk),
                options=["same entity", "partition into groups", "some known, some unknown", "defer"],
                answer_scope="Only candidate references shown; confirmed examples are context. No entries are merged.",
                why_grouped="Shared candidate catalog family; identity remains unconfirmed.",
                impact=f"A scoped answer can resolve {len(chunk)} references across {len(ids)} entries; it does not establish the same event."))
    for edge in g["edges"]:
        if edge["status"] != "proposed":
            continue
        pool.append(dict(question_id="Q-" + o.digest(edge)[:24], kind="relation",
            title=edge["relation"] + " — " + edge["source"] + " / " + edge["target"],
            prompt=f"Does the proposed {edge['relation']} relationship hold in the stated direction?",
            proposal_id=edge["proposal_id"], relation=edge["relation"],
            evidence=[_card(w, entries, contexts, context_chars) for w in edge["evidence"]],
            known_references=[], affected_entry_ids=[edge["source"], edge["target"]],
            handles=["relation:" + edge["proposal_id"]], effort_units=2,
            options=["confirm", "reject", "leave pending"], why_grouped=edge["reason"],
            impact="Decides this directed relationship only; chronological proximity does not establish causation.",
            answer_scope="Only this proposal; entries remain separate."))
    # A scheduling heuristic, NOT a deduction that identity proves a relation.
    roots_by_entry = defaultdict(set)
    for q in pool:
        if q["kind"] != "relation":
            for eid in q["affected_entry_ids"]:
                roots_by_entry[eid].add(q["question_id"])
    for q in pool:
        q["possible_context_dependencies"] = (sorted(set().union(*(roots_by_entry[eid] for eid in q["affected_entry_ids"])))
                                                if q["kind"] == "relation" else [])
    stats = dict(entries_scanned=len(entries), catalog_terms=len(state["data"]["catalog"]),
                 mentions_scanned=len(g["mentions"]), candidate_questions=len(pool),
                 relations_held_for_context=sum(bool(q["possible_context_dependencies"]) for q in pool),
                 entries_without_catalog_matches=len(g["entries_without_mentions"]),
                 semantic_discovery_performed=False, organization_complete_claimed=False)
    return pool, stats


def select_questions(pool, limit=DEFAULT_SIZE, root_first=True):
    o.require(type(limit) is int and limit > 0, "Positive question limit required")
    options = [deepcopy(q) for q in pool if not root_first or not q["possible_context_dependencies"]]
    picked, covered, families = [], set(), set()
    while options and len(picked) < limit:
        def gain(q):
            facet = q["kind"] if q["kind"] != "relation" else "relation:" + q["relation"]
            return len({(facet, eid) for eid in q["affected_entry_ids"]} - covered)
        q = min(options, key=lambda x: (-gain(x) / x["effort_units"], -len(x["affected_entry_ids"]), x["question_id"]))
        options.remove(q)
        family = (q["kind"], q.get("hypothesis_family"))
        if not gain(q) or (root_first and q["kind"] != "relation" and family in families):
            continue
        q.update(priority_score=round(gain(q) / q["effort_units"], 4), marginal_entry_facets=gain(q),
                 ranking="new entry/facet coverage / estimated reading effort; not calibrated information gain")
        facet = q["kind"] if q["kind"] != "relation" else "relation:" + q["relation"]
        covered.update((facet, eid) for eid in q["affected_entry_ids"])
        families.add(family)
        picked.append(q)
    return picked


def make_batch(state, size=DEFAULT_SIZE, max_items=12, context_chars=DEFAULT_CONTEXT_CHARS):
    o.require(type(size) is int and 1 <= size <= 20, "Batch size must be 1–20; normally choose 10, 15, or 20")
    pool, stats = question_pool(state, max_items, context_chars)
    selected = select_questions(pool, size, root_first=True)
    body = dict(version=BATCH_VERSION, basis_state_sha256=o.digest(state), data_sha256=state["data_sha256"],
                event_count=len(state["events"]), settings=dict(size=size, max_items=max_items, context_chars=context_chars),
                scan=stats, questions=[dict(q, number=i) for i, q in enumerate(selected, 1)],
                unselected_questions=len(pool) - len(selected),
                scope_note="All supplied catalog/proposals scanned; unrecognized semantic links may remain. No padding to fill a batch.")
    return dict(body, batch_id="QB-" + o.digest(body)[:24])


def validate_batch(state, batch):
    """Rebuild from the checked history prefix, allowing viewing/idempotent replay."""
    o.require(batch.get("version") == BATCH_VERSION and batch.get("data_sha256") == state["data_sha256"], "Batch version or entry snapshot changed")
    count = batch.get("event_count")
    o.require(type(count) is int and 0 <= count <= len(state["events"]), "Invalid batch history boundary")
    events = deepcopy(state["events"][:count])
    basis = dict(state, events=events, events_sha256=o.digest(events))
    o.require(o.digest(basis) == batch.get("basis_state_sha256"), "Batch history no longer matches")
    o.require(make_batch(basis, **batch["settings"]) == batch, "Batch cards, scope, or numbering changed")
    return basis


def _inline(text):
    text = html.escape(" ".join(str(text).split()), quote=False)
    return re.sub(r"([\\`*_\[\]{}#|!])", r"\\\1", text)


def _fenced(text):
    fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
    return [fence + "text", text, fence]


def render_questions(items, full_entries=None):
    lines = ["# Clarification questions", "", "Answer the prepared questions together. No regrouping is needed between answers.",
             "Excerpts and titles come from entries; dates and places are not inferred. Scores are heuristics, not probabilities."]
    if not items:
        lines.append("No questions in this queue. This does not establish complete organization.")
    for i, q in enumerate(items, 1):
        lines += ["", f"## {q.get('number', i)}. {_inline(q['title'])}", "", _inline(q["prompt"]),
                  "", "Why grouped (hypothesis): " + _inline(q["why_grouped"]), "Impact: " + _inline(q["impact"])]
        for ref in q["known_references"]:
            lines += ["", f"**Known reference {ref['code']}: {_inline(ref['label'])} — previously user-confirmed**"]
            for card in ref["evidence"]:
                lines += [f"{_inline(card['entry_id'])} — {_inline(card['title'])}"] + _fenced(card["context"])
            if ref["additional_support_mentions"]:
                lines += [f"Additional supporting references not shown: {ref['additional_support_mentions']}."]
        if q.get("known_entities_not_shown"):
            lines += [f"Other known identities omitted: {q['known_entities_not_shown']}. Do not assume the displayed identity is unique."]
        lines += ["", "**Candidate references**"]
        for card in q["evidence"]:
            label = card.get("reference_code", "Endpoint")
            lines += [f"{label}. **{_inline(card['entry_id'])} — {_inline(card['title'])}**"]
            if card["confirmed_context"]:
                context = "; ".join(x["kind"] + ": " + x["label"] for x in card["confirmed_context"])
                lines += ["Confirmed associations (not inferred event dates/locations): " + _inline(context)]
            if card["confirmed_context_not_shown"]:
                lines += [f"Other confirmed associations not shown: {card['confirmed_context_not_shown']}."]
            text = full_entries[card["entry_id"]] if full_entries is not None else card["context"]
            lines += _fenced(text)
            lines += (["Full entry text shown."] if full_entries is not None else
                      [f"Excerpt [{card['context_start']}, {card['context_end']}); exact quote and offsets retained in batch JSON."])
        if q.get("family_mentions_not_shown"):
            lines += [f"Other pending references in this family: {q['family_mentions_not_shown']}; NOT included in this answer's scope."]
        lines += ["", "Answer choices: " + "; ".join(q["options"]), _inline(q["answer_scope"])]
        if q["kind"] != "relation":
            lines += ["Reply: same [R1 when applicable]; or groups A,C=R1 / B=another person or project; or unsure.",
                      "For partial answers, identify the remaining references as unknown. 'Not all' never means 'all different'."]
        else:
            lines += ["Reply: confirm / reject / unsure (unsure leaves this relation pending)."]
    return "\n".join(lines) + "\n"


def prepare_batch(run, output, **settings):
    run, output = Path(run), Path(output)
    with o.locked(run):
        batch = make_batch(o.read_state(run), **settings)
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        o.atomic_write(output / "batch.json", batch)
        (output / "questions.md").write_text(render_questions(batch["questions"]), encoding="utf-8")
        template = dict(batch_id=batch["batch_id"], actor="", answer_text="", responses=[])
        o.atomic_write(output / "answers.template.json", template)
    return dict(batch_id=batch["batch_id"], questions=len(batch["questions"]), scan=batch["scan"],
                batch_file=str(output / "batch.json"), context_cards=str(output / "questions.md"),
                state_unchanged=True)


def compile_answers(state, batch, answers):
    """Translate explicit structured choices, never infer a user's natural-language intent."""
    basis = validate_batch(state, batch)
    o.keys(answers, ("batch_id", "actor", "answer_text", "responses"))
    o.require(answers["batch_id"] == batch["batch_id"], "Answers reference another batch")
    o.require(all(isinstance(answers[k], str) and answers[k].strip() for k in ("actor", "answer_text")), "Record actual actor and verbatim user response")
    o.require(isinstance(answers["responses"], list) and answers["responses"], "Responses required; blank is not confirmation")
    questions = {q["number"]: q for q in batch["questions"]}
    operations, seen, left_pending = [], set(), []
    event_id = "batch-answer-" + o.digest([batch["batch_id"], answers])[:24]
    def emit(op):
        op.update(rule_id=event_id + "-" + str(len(operations) + 1))
        op.setdefault("depends_on", [])
        operations.append(op)
    for response in answers["responses"]:
        o.keys(response, ("number", "choice"), ("reference", "label", "groups", "unknown"))
        n = response["number"]
        o.require(type(n) is int and n in questions and n not in seen, "Unknown or repeated question number")
        seen.add(n)
        q = questions[n]
        choice = response["choice"]
        if q["kind"] == "relation":
            o.require(set(response) == {"number", "choice"} and choice in ("confirm", "reject", "unsure", "skip"), "Relation needs confirm, reject or unsure")
            if choice in ("unsure", "skip"):
                left_pending.append(n)
            else:
                emit(dict(op="relation", proposal_id=q["proposal_id"], accept=choice == "confirm"))
            continue
        cards = {x["reference_code"]: x for x in q["evidence"]}
        if choice in ("unsure", "skip"):
            o.require(set(response) == {"number", "choice"}, "Unknown answer must not include binding fields")
            emit(dict(op="defer", mention_ids=q["handles"]))
            continue
        o.require(choice in ("same", "groups"), "Use same, explicit groups, or unsure; not-all is not all-different")
        if choice == "same":
            o.require(not ({"groups", "unknown"} & set(response)), "Same cannot include partial groups")
            group = {k: response[k] for k in ("reference", "label") if k in response}
            group["members"] = list(cards)
            if "reference" not in group and "label" not in group:
                o.require(not q["known_entities_not_shown"] and len(q["known_references"]) <= 1, "Choose a known reference explicitly, or label a new group")
                if q["known_references"]:
                    group["reference"] = q["known_references"][0]["code"]
            groups, unknown = [group], []
        else:
            o.require(not ({"reference", "label"} & set(response)), "Put identities inside explicit groups")
            groups, unknown = response.get("groups", []), response.get("unknown", [])
            o.require(isinstance(groups, list) and isinstance(unknown, list)
                      and (not unknown or o.strings(unknown)), "Invalid groups or unknown references")
        accounted = []
        for idx, group in enumerate(groups):
            o.keys(group, ("members",), ("reference", "label"))
            o.require(o.strings(group["members"]) and set(group["members"]) <= set(cards), "Group contains an unshown reference")
            accounted.extend(group["members"])
            subset = [cards[c] for c in group["members"]]
            refs = {r["code"]: r for r in q["known_references"]}
            if "reference" in group:
                o.require("label" not in group and group["reference"] in refs, "Choose one displayed known reference without relabeling it")
                ref = refs[group["reference"]]
                entity_id = ref["entity"].split(":", 2)[2]
                label, dependencies = ref["label"], [ref["support_rule_id"]]
            else:
                label = group.get("label", subset[0]["label"])
                o.require(isinstance(label, str) and label.strip(), "A group label must be nonempty")
                entity_id = "group-" + o.digest([batch["batch_id"], q["question_id"], idx])[:20]
                dependencies = []
            emit(dict(op="bind", kind=q["kind"], aliases=sorted({c["label"] for c in subset}),
                      entry_ids=sorted({c["entry_id"] for c in subset}), mention_ids=[c["mention_id"] for c in subset],
                      entity_id=entity_id, entity_label=label, depends_on=dependencies))
        accounted += unknown
        o.require(len(accounted) == len(set(accounted)) and set(accounted) == set(cards), "Every shown reference must occur once in groups or unknown")
        if unknown:
            emit(dict(op="defer", mention_ids=[cards[c]["mention_id"] for c in unknown]))
    event = dict(event_id=event_id, expected_state_sha256=o.digest(basis), actor=answers["actor"],
                 answer=json.dumps(answers, ensure_ascii=False, sort_keys=True), operations=operations)
    summary = dict(batch_id=batch["batch_id"], responses_received=len(seen),
                   unanswered_numbers=sorted(set(questions) - seen),
                   relations_left_pending=left_pending, new_rule_count=len(operations), canonical_entries_unchanged=True)
    return event, summary


def preview_answers(state, batch, answers):
    event, summary = compile_answers(state, batch, answers)
    if not event["operations"]:
        o.require(event["expected_state_sha256"] == o.digest(state), "Stale answer")
        return state, dict(summary, status="no_changes", state_sha256=o.digest(state))
    updated, report = o.preview(state, event)
    return updated, dict(report, **summary)


def apply_answers(run, batch, answers):
    run = Path(run)
    with o.locked(run):
        state = o.read_state(run)
        updated, report = preview_answers(state, batch, answers)
        if report["status"] not in ("already_applied", "no_changes"):
            o.atomic_write(run / "state.json", updated)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "show", "preview", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--run", type=Path, required=True)
        if name == "prepare":
            p.add_argument("--output", type=Path, required=True)
            p.add_argument("--size", type=int, default=DEFAULT_SIZE)
            p.add_argument("--max-items", type=int, default=12)
            p.add_argument("--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
        else:
            p.add_argument("--batch", type=Path, required=True)
        if name == "show":
            p.add_argument("--number", type=int)
            p.add_argument("--full", action="store_true")
        if name in ("preview", "apply"):
            p.add_argument("--answers", type=Path, required=True)
        if name == "apply":
            p.add_argument("--confirm-user-answer", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_batch(args.run, args.output, size=args.size, max_items=args.max_items, context_chars=args.context_chars)
        else:
            batch = o.load(args.batch)
            if args.command == "show":
                state = o.read_state(args.run)
                basis = validate_batch(state, batch)
                qs = [q for q in batch["questions"] if args.number is None or q["number"] == args.number]
                o.require(args.number is None or bool(qs), "Unknown question number")
                entries = {e["entry_id"]: e["text"] for e in basis["data"]["entries"]} if args.full else None
                if o.digest(state) != batch["basis_state_sha256"]:
                    print("Historical batch: the organization state has changed; answers require a current preview.\n")
                print(render_questions(qs, entries), end="")
                return 0
            if args.command == "apply":
                o.require(args.confirm_user_answer, "Require --confirm-user-answer; never manufacture confirmation")
                result = apply_answers(args.run, batch, o.load(args.answers))
            else:
                result = preview_answers(o.read_state(args.run), batch, o.load(args.answers))[1]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
