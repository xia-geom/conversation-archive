# Second-stage organization: connect entries without rewriting them

[Project overview](../README.md) · [Documentation](README.md) · [Codex organization contract](organization-codex.md)

Extraction answers **what was said**. Organization asks **which records are connected, in what way, and on what evidence**. Several entries can share a person, project, place or period without describing the same event. Keep those dimensions separate and preserve the original entries.

```text
Existing entries -> exact entry index -> proposed mentions and relationships
                                              |
                           literal observations + existing confirmed rules
                                              |
                       uncertainty families -> a few prioritized questions
                                              |
                       scoped answer -> impact preview -> rule history
                                              |
                       regenerated relationship graph (separate from master)
```

## Implementation status

This release implements a dependency-free **organization sidecar** and an offline clarification loop. It does not yet implement automatic semantic discovery by a live model.

| Component | Current behavior |
| --- | --- |
| Markdown entry index | Reads supported E-numbered Markdown headings, preserves exact source slices, ignores headings inside fenced/archive blocks |
| Mention discovery | Deterministic literal matching against a supplied typed catalog; exact source offsets retained |
| Candidate families | A supplied catalog groups possible aliases; a family is a hypothesis, not an identity assertion |
| Directed relationships | Supplied proposals with exact evidence from both endpoint entries; never accepted merely because quotations match |
| Question selection | Bounded, deterministic ranking by new entry/facet coverage divided by estimated reading effort |
| Corrections | Scoped alias binding, contextual association, relation acceptance/rejection, deferral, revocation, and dependency tracking |
| Persistence | One local state file, advisory writer lock, atomic replacement, expected-state checks, repeat-answer idempotence, integrity hashes |
| Live Codex proposer, calibrated information gain, automatic cross-snapshot rule migration | Designed below, not implemented or benchmarked |

No graph database, vector store, web interface, paid call, or new runtime dependency is required. The sidecar writer requires macOS or Linux. Existing import/extraction/reconciliation APIs and master files are unchanged. A graph JSON export is inspectable data, not an interactive graph visualization.

## Try the six-entry example

Run from the repository root using a fresh directory:

```sh
python3 -m conversation_archive.organization prepare --input examples/organization.json --run data/organization-demo
python3 -m conversation_archive.organization questions --run data/organization-demo --limit 3 --format markdown
```

The invented example contains five project references and a sixth, separate record. The first question groups **Orchard** and **summer build** across five entries. A separate question concerns the name Rowan. None of those literal matches has yet established a shared real-world identity. The two project labels were supplied as a candidate family in the fixture; a model did not discover them in this demo.

Now simulate the owner's answer: “All five project references name Orchard; they are not one event.” Save its finite scope and the current state hash:

```sh
python3 - <<'PY'
import json
from pathlib import Path
from conversation_archive.organization import digest, read_state
run = Path('data/organization-demo')
state = read_state(run)
answer = {
    'event_id': 'demo-answer-1',
    'expected_state_sha256': digest(state),
    'actor': 'Invented example owner',
    'answer': 'These five references name Orchard, not the same event.',
    'operations': [{
        'op': 'bind', 'rule_id': 'project-aliases', 'depends_on': [],
        'kind': 'project', 'aliases': ['Orchard', 'summer build'],
        'entry_ids': ['E0001', 'E0002', 'E0003', 'E0004', 'E0005'],
        'entity_id': 'orchard', 'entity_label': 'Orchard project'
    }]
}
with (run / 'answer.json').open('x', encoding='utf-8') as f:
    json.dump(answer, f, indent=2)
PY
python3 -m conversation_archive.organization preview --run data/organization-demo --decision data/organization-demo/answer.json
python3 -m conversation_archive.organization apply --run data/organization-demo --decision data/organization-demo/answer.json --confirm-user-answer
python3 -m conversation_archive.organization questions --run data/organization-demo --limit 3 --format markdown
python3 -m conversation_archive.organization graph --run data/organization-demo
```

The preview lists five affected entries and the before/after mention assignments. The project question disappears; the people question remains. Reapplying the identical answer returns `already_applied`. No entry text changes, no event identity is inferred, and no causal link is created. The command-line flag records explicit operator intent; it is not an authentication system or proof of who actually answered.

## Index an existing master

```sh
python3 -m conversation_archive.organization_inputs --master /path/to/private/master.md --output data/entry-index.json
```

Supported active headings start with an E and four digits. This is not a general Markdown parser. Each entry has `entry_id`, exact `text`, and a source-text SHA-256 plus Unicode character range. Preserve those fields. Generic JSON entries can instead use stable IDs and text directly, as in [the fixture](../examples/organization.json).

The generated index has an empty `catalog` and `proposals`. **It has not discovered entities yet.** Follow the [Codex contract](organization-codex.md) to propose those fields, or supply a catalog JSON array using `--catalog`. Save an enriched input to a fresh local file, validate it, then call `organization prepare`. Do not replace the original master with the index.

A catalog term has `kind`, literal `label`, and candidate `family`. Kinds are person, organization, place, project, event, period, or topic. Catalog matching observes words; it does not establish that a person participated in an event, that a draft was sent, or that a dated phrase is an event date. Unknown names, languages, pronouns and implicit references require semantic preparation, not increasingly aggressive substring matching.

A relation proposal has a stable `proposal_id`, `source` entry ID, `target` entry ID, `relation`, `reason`, and `evidence`. Evidence lists exact `entry_id`, `start`, `end`, and `quote` for both endpoint entries. Allowed relations are continues, revises, precedes, responds_to, and reported_cause. Reported cause is an attributed connection, not an independently established causal fact.

## What gets added automatically?

| Signal | Allowed outcome | Forbidden inference |
| --- | --- | --- |
| Exact catalog phrase occurs | Observed entry-to-mention edge | Same spelling means same person |
| Existing active, scoped answer matches | Regenerate confirmed mention/entity or context links | Apply the answer outside its stated scope |
| Similar labels or candidate family | Uncertainty question with evidence | Automatically merge entities |
| Nearby dates or shared place/topic | Context for a proposal | Same event or causation |
| User explicitly confirms a directed link | Confirm that named relation | Infer all other relationship types or causal transitivity |
| User identifies separate groups | Separate bindings in one answer | Force the entire cluster to have one identity |
| Unknown or defer | Leave uncertain; suppress deferred mentions until reopened | Treat silence as a negative or a confirmation |

Every graph edge distinguishes `observed_text`, `proposed`, `user_confirmed`, or `rejected`. A language model's numerical confidence is not an authorization field. The current automatic acceptance path is deliberately limited to literal observations and applications of confirmed rules.

## Reusable corrections and their limits

An answer is an append-only event with `event_id`, `actor`, `answer`, `expected_state_sha256`, and `operations`. The whole answer is previewed and installed in one state-file replacement.

**`bind`** maps a kind and list of aliases, within explicit `entry_ids`, to an `entity_id` and `entity_label`. Use optional `mention_ids` to restrict the rule to exact occurrences: two identical names can mean different people even within one entry. One answer can contain several bindings to partition a cluster. Assigning one mention to incompatible entities is rejected rather than resolved by last-write-wins.

**`associate`** records a user-confirmed contextual grouping without inventing a quotation. It has kind, explicit entry IDs, entity ID and label. For example, the owner can associate a set of entries with a named location or project absent from their original wording. The resulting `associated_with` edge is supported by that answer, not claimed to be extracted from the original text. It does not by itself assert that every event physically occurred there.

**`relation`** accepts or rejects a named proposal using a boolean `accept`. Rejection removes it from the question queue and remains in history. Confirmed `precedes` links cannot form a cycle. No causal or identity transitive closure is manufactured.

**`defer`** records exact mention IDs as unresolved without repeating their questions. Reopen them explicitly by revoking that rule. Relation proposals can be left pending; persistent relation deferral is not implemented.

**`revoke`** names a prior rule. The next graph rebuild removes links depending solely on that rule and invalidates dependent rules; independently supported links survive. Non-revocation rules carry `depends_on`, referencing earlier rules. Cycles/forward references are refused. History and original wording stay intact.

Rules are reused across rebuilds of this **frozen entry snapshot**. There is no global text replacement, wildcard scope, implicit identity union, or automatic migration to a new export/master snapshot. A later incremental layer should reuse unchanged entry/mention identities, recheck changed evidence, and propose an explicit expansion of a rule's scope. It must not ask the old question again merely because a job restarted; equally, it must not silently extend a correction to a new context.

## Selecting questions efficiently

The implemented rank is a transparent proxy: new entry/facet coverage divided by estimated effort. Repeated mentions of one entry do not count as many independently affected entries. Greedy selection discounts overlap among already selected questions for the same facet. The default is three questions, with at most twelve displayed mention excerpts per question. JSON discloses a larger family's omitted members; an answer is never inferred for those unseen members.

This is **not calibrated entropy reduction** or a claim that the selector is mathematically optimal. Before adding a learned score, measure how many correct links each question actually resolves and how much user work it takes. Keep separate measures for false merges, scope violations, repeat questions, useful coverage, unsupported causal links, and correction reversibility. A link count alone rewards over-connecting.

The next selector should additionally consider dependency fan-out, contradiction risk, answerability, and diverse question types. Evaluate these changes against a fixed annotated example set. Ask the root question first when several downstream decisions truly depend on it, rather than counting every co-occurring record as guaranteed information gain.

## Efficient Codex responsibilities

Use deterministic code for indexing, exact matching, applying remembered answers, validating spans and scopes, ranking questions, state management, and graph rendering. Use Codex for proposing entities/aliases, interpreting whether a context may be shared, and framing difficult alternatives. Do not feed the whole master into every comparison or compare every entry with every other entry.

The intended proposer reads compact entry cards, uses names/periods/projects/lexical retrieval to form candidate neighborhoods, and fetches full evidence only for those neighborhoods. It should retain uncertainty and explicit alternatives. Full automatic semantic discovery, retrieval indexes, model-call budgeting for this proposer, and incremental recomputation are still future work; the existing extraction controller is not silently repurposed for a different schema.

## Privacy, integrity, and audit boundary

Keep indexes, catalogs, proposals, answers and graph exports local under ignored `data/` or an equivalent private directory. The snapshot can contain the whole private master. Neither this module nor its tests send data to a provider. A separately invoked Codex agent has its own provider and data-transfer boundary.

Hashes and a chained answer history detect accidental drift, not malicious rewriting by someone controlling the directory. Locks are advisory and protect this organization state only. Source quotation checks establish entry-level traceability, not raw-message attribution or factual truth. The graph is an additional view, never a replacement master. An empty question list does not establish completeness; graph output explicitly reports entries without catalog matches and makes no complete-organization claim.

## Design references

These influenced the design, not imported dependencies:

- [Dedupe](https://docs.dedupe.io/): entity resolution with human examples and efficient candidate comparisons. This prototype has not trained Dedupe or implemented its active learner.
- [GraphRAG dataflow](https://microsoft.github.io/graphrag/index/default_dataflow/): separate source units, entities, relationships and group structures. Here, same title/type is deliberately insufficient for automatic identity merging.
- [W3C PROV overview](https://www.w3.org/TR/prov-overview/): keep attribution, versioning and derivation explicit. The sidecar is not claimed to implement the PROV serialization standards.
