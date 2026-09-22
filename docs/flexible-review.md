# Flexible review: declarative questions, deterministic decisions

[Snapshot workflow](snapshot-review.md) · [Agent contract](../AGENTS.md) · [Review skill](../.agents/skills/archive-review/SKILL.md)

## Decision

Use a hybrid, not a choice between HTML and Codex. Authors choose the question, evidence, and controls. A local renderer displays them. A deterministic validator checks submitted values. Registered semantic writers produce a checked successor snapshot. Skills guide preparation but cannot grant permission, validate truth, or bypass the writer.

```
snapshot + supplied cases
        -> frozen question and control specification
        -> local HTML or another client
        -> the same structured answer document
        -> checked preview
        -> explicit application to a new snapshot
```

HTML is a replaceable client, not the archive. A chat answer can be compiled into the same JSON, but its interpretation must be shown for approval. A natural-language explanation never silently changes a grouping, date, or medical result. A cloud Codex session reading local files is still model processing; local paths do not authorize transfer.

## What is implemented

`review-controls-1.0` is a small declarative JSON format, validated using Python's standard library. It is not a claim to implement the full JSON Schema language. The machine snapshot and legacy scalar answer protocol remain unchanged; prepared questions advertise a separate, versioned `controls` extension. Old scalar sessions remain usable with their original capabilities. They cannot acquire grouping powers by adding an answer field.

| Control | Typical use | Semantics |
| --- | --- | --- |
| `choice` | Select one explanation. | Only a listed value is accepted. |
| `multi_choice` | Identify sources reviewed or several applicable reasons. | Unique selected values; no inferred defaults. |
| `text` | Preserve a qualification, raw date, correction proposal, or explanation. | Bounded verbatim text, never auto-parsed into a fact. |
| `groups` | Assign displayed references to explicit groups, leaving others unknown. | Every reference occurs once; groups cannot overlap. |
| `visible_when` | Ask for a date only after choosing the date-related answer. | A simple condition on a preceding single-choice field; hidden values cannot contribute. |

Any new **record-only question** can combine these controls without changing HTML or adding code. A new archive-changing operation is different: it needs a registered compiler, a precise preview, validation, replay/reversal behavior, and tests. A schema cannot choose an arbitrary operation, function, shell command, URL, JavaScript fragment, or renderer.

Generic forms always record the owner's answer and evidence in correction history; they do not modify result fields, merge entities, or decide which medical account is true. Built-in directed relationships keep their existing writer. Built-in identity cards now compile explicit grouping to finite `bind_mentions` rules inside the existing snapshot transaction.

## Example: a new question without a new HTML page

A supplied case uses `kind: "form"`, the usual title/prompt/reason/evidence/dependencies, and this form:

```json
{
  "version": "review-controls-1.0",
  "fields": [
    {
      "id": "outcome", "type": "choice", "label": "What differs?", "required": true,
      "options": [
        {"value": "date", "label": "Dates"},
        {"value": "unknown", "label": "Cannot determine"}
      ]
    },
    {
      "id": "date_text", "type": "text", "label": "Reported date, exactly as written",
      "required": true, "max_length": 100,
      "visible_when": {"field": "outcome", "equals": "date"}
    }
  ]
}
```

The existing `prepare --cases` command validates it and produces the local form. Answering `record` requires a `values` object such as `{"outcome":"date","date_text":"03/04/2020?"}`. The ambiguous date stays ambiguous. Choosing `unknown` hides the date field and excludes its draft value from submission without deleting the resumable draft.

Limits are explicit: 24 fields, 100 options/group references, 10,000 characters per bounded text field. There is no date coercion, expression evaluator, remote schema loading, default answer, or implicit bulk confirmation. Unknown versions and unsupported fields fail closed. Oversized identity cases currently need smaller explicitly scoped source questions; do not split one question into contradictory automatic decisions.

## Identity grouping

The preparer obtains mention IDs and exact spans from the saved question, not from filenames or a model's guesses. The card offers new groups and existing identities already represented on that card. It does not perform an unrestricted whole-archive entity search.

For four displayed references, an answer can put two in one group and the other two in Unknown. Unknown makes **no new identity assertion**: it neither means a distinct identity nor erases an existing assignment. Different group labels alone never establish identity. A new group creates an opaque entity ID; it is not matched by its label.

New bindings touch only explicitly selected, currently unbound references. Existing same-target assignments are preserved, not counted as new independent evidence. Incompatible prior assignments are refused; reopen the supported prior decision instead of silently merging identities. A partial answer retains the source question and is shown as partial. Fully answered question definitions remain recoverable through history.

Grouping records the original source question, exact prior mention states, created entity IDs, and explicit rule dependencies. Replacing or reopening a grouping withdraws only supported interpretation rules and restores its own previous bindings. It preserves history and original text. Dependencies on older unsupported bindings, independently supported assignments, or external uses of an identity can refuse the entire transaction; this is not a general graph merge/split engine. A replacement can explicitly retain an identity previously created by that same withdrawn grouping.

The writer is the authority for validation. Browser validation is a convenience, not a security boundary. Snapshot hashes identify bytes; they are not signatures or proof of human consent. `--confirm-user-answer` is an explicit operator action, not an authentication system.

## Batches, drafts, and equivalent clients

Keep one complete searchable prepared queue. Default batches contain up to 15 questions, adjustable from 1 to 20. Supplied conflicts come first. Identity review stays optional; selecting the Identity type includes pending/partial identity cards rather than forcing all of them into contradiction review.

Save draft retains unfinished controls and explanatory text even before an outcome is selected. Export answers includes only explicit outcomes, so draft work is not mistaken for a decision. Restore is scoped to the frozen session. Submissions carry question IDs, snapshot/session IDs, prior rule IDs, and exact values. Reordering the page cannot change answer scope.

HTML, hand-authored JSON, or an authorized Codex-assisted client all use the same `preview` and `apply` commands. There is no privileged chat-only correction path in this reviewer. No new live chat interpreter or MCP server is included.

## Skills and other tools

The repository skill at `.agents/skills/archive-review/SKILL.md` guides question preparation, evidence selection, the shared answer contract, and verification. It is optional; the HTML works without a model running. It does not discover contradictions automatically and it is not a privacy enforcement mechanism.

The native HTML/Python implementation needs no new runtime dependency. Existing Playwright/Chromium tests check the actual browser behavior. Other options are future conveniences, not prerequisites:

| Option | Appropriate role | Why not required now |
| --- | --- | --- |
| Generic JSON Schema form library | Much larger forms after a measured need. | More packaging/runtime surface; still needs separate semantic validation. |
| Local HTTP save/apply service | Fewer file-download/import steps. | Requires origin checks, authentication/capabilities, concurrency, and write-scope design. |
| MCP adapter | Let several agent clients submit/preview the same answer objects. | A transport adapter, not a replacement for the checked writer or authorization. |
| Hosted forms/database app | Collaboration with separately authorized data hosting. | Changes the current local-only privacy boundary. |
| AI-generated HTML per batch | A disposable visual experiment. | Do not use as the authoritative answer or write mechanism. |

Official background: [OpenAI skill authoring](https://developers.openai.com/codex/skills/) documents reusable `SKILL.md` workflows and repository-local `.agents/skills` discovery. This project uses instructions for preparation and code for enforceable data checks.

## Audit and verification scope

Audited base: `954fb223732f88421ff53d1111c02f43c8770837` (PR #12 merged). Findings addressed: scalar-only hard-coded input; missing identity grouping bridge; unfinished form text not retained; no general record-only questions; and no separate control-version contract. Existing evidence, deferral, stale-session, preview, immutable-successor, and replay behavior is retained.

Run:

```sh
python3 -m unittest discover -s tests -v
python3 tools/flexible_review_browser_smoke.py --output data/flexible-review-browser
```

The new tests cover form constraints, hidden values, unknowns, partial identities, finite scope, conflicting old identities, exact restoration, legacy refusal, tampered projections, record-only behavior, old-session compatibility, snapshot application, and SQLite rebuild. Browser checks cover conditional fields, unfinished drafts, grouping, export, hostile text, no remote requests, and mobile width. The existing scalar browser smoke remains in CI as a regression check.

Local development without the complete repository runs the pure tests only and explicitly skips integration tests. `--memory` browser testing reports that local-file navigation was not tested. CI runs against the complete checkout and tests actual local-file navigation. Use the PR's check results for the exact tested commit; do not turn planned tests into passing claims.

No personal archive was accessed or changed in this implementation. There is still no automatic contradiction-discovery engine, medical inference, arbitrary legacy-binding reversal, live Notes access, automatic transport adapter, or automatic update of a user's current snapshot.
