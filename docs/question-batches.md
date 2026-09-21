# Answer a prepared batch, not one question at a time

[Project overview](../README.md) · [Organization guide](organization.md) · [Codex contract](organization-codex.md)

The workflow is **scan the supplied index → prepare 15 contextual questions → answer together → preview and apply the whole reply → prepare the next batch**. Choose 10 or 20 instead. The system never invents extra questions to fill a batch.

Each card shows the entry title (or exact opening excerpt), a short original passage around the reference, any confirmed project/place/period associations, and relevant previously confirmed identity examples. IDs remain available for precision, but are not the only context. No event date, location, biography, or summary is invented to fill an empty field.

## Try it without a model

Requires Python 3.11+ and macOS or Linux. From the repository root, use fresh directories. The fixture has 40 invented entries and 20 supplied candidate project families; it is not a semantic-discovery benchmark.

<!-- smoke:organization-batch:start -->
```sh
python3 -m conversation_archive.organization prepare --input examples/question-batches.json --run data/batch-example
python3 -m conversation_archive.organization_batches prepare --run data/batch-example --output data/questions-01 --size 15
python3 -m conversation_archive.organization_batches show --run data/batch-example --batch data/questions-01/batch.json
```
<!-- smoke:organization-batch:end -->

Preparation reports 40 entries scanned, 20 candidate questions, and 15 selected. It writes `batch.json` (frozen questions and numbering), `questions.md` (readable cards), and `answers.template.json` (blank, with no preselected answers). Preparation does not change the graph or record a user response. These artifacts contain private text when used on real data; keep them under ignored `data/` or an equivalent private directory.

`--size` defaults to 15 and supports 1–20; normally use 10, 15, or 20. `--context-chars` defaults to 240 and supports 80–1200 characters per excerpt. `--max-items` defaults to 12 candidate references per question. Omitted family members are disclosed and never included in the answer scope.

Need more context for question 2? This opens the frozen entries, not another model session:

```sh
python3 -m conversation_archive.organization_batches show --run data/batch-example --batch data/questions-01/batch.json --number 2 --full
```

## What a card means

A person card can show **R1: previously confirmed Workshop Rowan**, with two source examples, followed by candidate references **A, B, C**. Every reference has its entry title and an exact excerpt. One answer such as “1: A and C are R1; B is unknown” can resolve several references without asking about each separately.

A known reference comes from an active user-confirmed binding, not a shared spelling. Its support is retained as a rule dependency. If there are several possible known identities, the answer must choose one explicitly, or label a new group. Missing dates/places remain missing. Confirmed associations are labeled as associations, not assertions that every event occurred there.

Short excerpts may omit important context. Use `show --number ... --full` before resolving an ambiguity. The source text remains unchanged and is not trusted as executable instructions.

## Submit all answers together

A user may reply conversationally, for example: “1 same; 2 unsure; 3 A and C are R1, B unknown.” A separately invoked Codex agent translates that reply into the strict response document below and copies the original reply into `answer_text`. The CLI does **not** itself interpret natural language. Validate the translation in the preview; a schema check cannot prove it matches the user's intent.

For the invented fixture, create a response to the first two questions only:

```sh
python3 - <<'PY'
import json
from pathlib import Path
batch = json.loads(Path('data/questions-01/batch.json').read_text())
reply = {
    'batch_id': batch['batch_id'],
    'actor': 'Invented example reviewer',
    'answer_text': 'Synthetic demonstration: 1 same project; 2 unsure.',
    'responses': [
        {'number': 1, 'choice': 'same'},
        {'number': 2, 'choice': 'unsure'}
    ]
}
with Path('data/questions-01/answers.json').open('x', encoding='utf-8') as f:
    json.dump(reply, f, ensure_ascii=False, indent=2)
PY
python3 -m conversation_archive.organization_batches preview --run data/batch-example --batch data/questions-01/batch.json --answers data/questions-01/answers.json
python3 -m conversation_archive.organization_batches apply --run data/batch-example --batch data/questions-01/batch.json --answers data/questions-01/answers.json --confirm-user-answer
```

This creates one event for the whole reply, links only question 1's displayed references, defers question 2's displayed mentions, and leaves unanswered questions pending. Repeating the identical apply is idempotent. The explicit flag records operator intent, not authenticated proof of the respondent's identity. Never apply the fixture's answers to a real archive.

### Response choices

For an identity/context-family question:

| Choice | Meaning |
| --- | --- |
| `same` | All shown candidate references name the same entity. With one shown known identity and no omitted identities, it reuses that identity; otherwise a reference or new label must be explicit. With no known identity, it creates one scoped group. |
| `same` with `reference: "R1"` | Bind only the displayed candidates to the displayed confirmed identity R1. |
| `same` with `label: "Separate project"` | Group the displayed candidates as a new entity, not as one of the known references. |
| `groups` | Assign exact card letters to separately specified groups; account for every other letter in `unknown`. |
| `unsure` or `skip` | Keep the shown mentions unresolved and defer them until explicitly reopened. |

An illustrative partial response, for a card that actually shows A, B, C and R1:

```json
{
  "number": 3,
  "choice": "groups",
  "groups": [{"members": ["A", "C"], "reference": "R1"}],
  "unknown": ["B"]
}
```

New groups can have a `label` instead of `reference`. “Only some” or “not all” without identifying the subset must not become “all different.” Identical spellings within one entry retain separate letters when they identify different source occurrences.

Directed-relation questions accept `confirm`, `reject`, or `unsure`/`skip`. **Relation skipping still leaves the proposal pending and may recur in a later batch**; persistent relation deferral is not implemented. The result reports `relations_left_pending`. Mention deferral is persistent. Blank templates, unshown letters, duplicate question numbers, overlapping groups, and contradictory operations are rejected before any state change.

## After the reply

Prepare a fresh batch from the updated organization state:

```sh
python3 -m conversation_archive.organization_batches prepare --run data/batch-example --output data/questions-02 --size 15
```

Resolved references are not asked again. Do not regenerate question numbering halfway through a reply. An unrelated change to the state makes the old reply stale; retain the user's words, inspect the changes, and prepare a new preview rather than silently applying old numbering to new questions. To answer a saved batch in several rounds, apply one partial reply, then prepare a new batch for the remaining work.

## Selection and compatibility

The deterministic scan examines all entries against the **supplied** catalog and all supplied relationship proposals before selecting anything. It does not discover new aliases or hidden relationships itself. A separately invoked Codex agent must first do that semantic preprocessing, using the [operating contract](organization-codex.md).

Ranking discounts overlapping entry/facet coverage and includes reading effort for known-reference excerpts. Prepared batches include at most one chunk of a candidate family. Directed relationships sharing endpoints with an unresolved identity/context question are held for a later batch. This is a conservative scheduling heuristic, not a proven dependency graph: confirming a shared project never automatically confirms continuity or causation. Short batches are allowed when context questions must be answered first.

The original `organization questions` preview now defaults to 15 and renders context cards. It retains the list-shaped output and can show several disjoint chunks of a large family. **Use `organization_batches prepare` for frozen numbering, root-first scheduling, and batch answer compilation.**

Batch format 1.0 adds separate versioned artifacts. Organization input/state format 1.0 and its existing rule operations remain unchanged; old states continue to load without migration. New cards are rebuilt from the recorded history prefix to detect changed context, scope, or numbering. Integrity hashes protect against accidental drift, not an adversary who controls all files. The existing advisory lock and single state-file replacement protect batch application; no canonical master is rewritten.
