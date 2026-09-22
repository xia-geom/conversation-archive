# Snapshot review: local HTML, checked decisions

[Agent contract](../AGENTS.md) · [Machine archive](machine-archive.md) · [Older organization batches](question-batches.md)

## Design audit and decision

The audited baseline is `df4d16c94a2739b71f63bd18c44eb30dec75ad6e`. It can record directed relationship assertions, but its contextual batch writer targets the older organization sidecar. Relation deferrals can recur there; the direct machine correction CLI cannot reverse a relationship decision. Saved machine questions contain mention references, not necessarily ready-to-render quote cards. A new HTML heading alone does not repair these interface and lifecycle gaps.

Use one offline review dashboard with a complete searchable **prepared** queue and manageable batches. Default to 15, adjustable from 1 to 20. Supplied potential contradictions come first, ordinary proposed relationships second; optional identity questions do not block the main queue. Several assertion occurrences may appear in one explicitly supplied conflict case. Grouping the display does not establish event identity or merge entries.

The implementation uses the existing authoritative machine snapshot and its correction tables. It does not create another editable master, reuse the unrelated organization state as authority, or give the read-only knowledge-map server write permissions.

## Implemented scope and remaining boundaries

| Capability | Scope |
| --- | --- |
| Read | Validated machine archive 1.0, saved identity questions, supported proposed directed relations, and optional supplied conflict cases. |
| Review | Side-by-side exact entry quotations, full preserved entries, stored metadata/references, search, pagination, explicit choices, notes, draft save/restore, and review-answer history. |
| Apply | Checked preview followed by explicit application to a new snapshot; originals and old snapshots are not rewritten. |
| Correct a review answer | Replace or reopen an answer made through this interface. Preserve old answer payloads and revoke dependent review/directed-relation support. |
| Not implemented here | Automatic contradiction discovery; native PDF/Notes/Gemini import; semantic matching; medical interpretation; identity grouping in this UI; arbitrary legacy correction reversal. |

An empty conflict queue means no conflict cases were supplied or retained, not that the archive is contradiction-free. Prepared coverage and migration-exception counts are recorded in `session.json`; the dashboard shows the prepared-entry/question counts. Neither certifies coverage against live applications. Evidence is checked against preserved **entries**, not reverified against inaccessible original medical pages. Source IDs remain source IDs: the renderer does not invent a file link or event date.

Identity cards are available in All questions for discovery and deferral. Existing identity-binding tools remain separate. Do not resume a large identity-classification exercise merely because those questions exist.

## Local workflow

Run from the repository checkout. Paths below are placeholders for private local directories; never use real data in Git or CI.

```sh
python3 -m conversation_archive.snapshot_review prepare \
  --archive /path/to/private/archive-v1 \
  --output /path/to/private/review/session-01 --size 15
```

Open `session-01/review.html` locally. The session also contains `session.json` and an empty `answers.template.json`. No answer is preselected. Preparation does not count as review.

Use Save draft to download a resumable draft; Restore draft accepts only this session. Drafts stay in memory until downloaded, with an unsaved-change warning. Nothing is kept in browser localStorage. Export answers produces a strict response document after an explicit reviewer label and at least one choice. Review choices and notes are copied exactly; no model interprets the reply.

```sh
python3 -m conversation_archive.snapshot_review preview \
  --archive /path/to/private/archive-v1 \
  --session /path/to/private/review/session-01/session.json \
  --answers /path/to/private/review-answers.json \
  --output /path/to/private/review/preview-01
```

Read `preview-01/preview.html`. It shows each selected outcome, exact evidence, withdrawn/dependent decisions, and the number of prepared cases retained for later sessions. A displayed preview is not an applied change.

```sh
python3 -m conversation_archive.snapshot_review apply \
  --archive /path/to/private/archive-v1 \
  --session /path/to/private/review/session-01/session.json \
  --answers /path/to/private/review-answers.json \
  --preview /path/to/private/review/preview-01/preview.json \
  --output /path/to/private/archive-v2 \
  --snapshot-version local-v2 --confirm-user-answer
```

Use the successor explicitly for the next session or rebuild with the existing machine-archive/knowledge-map tools. No global CURRENT pointer is advanced. Independently created successors are branches, not implicitly merged updates. An unchanged repeat returns `already_applied`; a different reply against a stale snapshot is rejected without deleting the reply. Prepare a new session/preview after applying a partial batch. There is no silent rebasing by question number.

Unanswered supplied cases are retained in the successor as **unresolved candidates**, so the next preparation does not need the old `--cases` file. Retaining their queue is not a review decision or permission to assert the proposed relationships. Only explicitly answered cards create answer history. Existing identity questions stay in their original registry. Before any application, the frozen session itself remains the record of the prepared queue.

## Supplied cases

An optional `--cases` JSON file has exactly `protocol`, `basis_snapshot_id`, and `cases`. The protocol is `snapshot-review-1.0`; the basis must identify the selected snapshot. Each case has `kind`, `title`, `prompt`, `reason`, `evidence`, and `depends_on`. Evidence is a list of exact `entry_id`, `start`, `end`, `quote` records; offsets count Unicode characters, not UTF-8 bytes. The preparer adds an entry-text hash. A conflict needs at least two distinct assertion occurrences. A relationship additionally names `source_entry_id`, `target_entry_id`, and one supported directed `relation`.

Titles, reasons, comparison context, and case grouping are **proposals**. They are not evidence of comparability. Use the prompt/reason to identify the alleged disagreement and unresolved subject, date, unit, or report-version questions. Preserve attribution and qualifications in the actual excerpts; expanding the complete entry remains available.

`depends_on` names explicit comparison-support rules. It must not be inferred from mere thematic overlap. Unknown or inactive support blocks substantive acceptance. Exact duplicates of an evidence occurrence are rejected rather than counted as corroboration. Do not send private case text to a remote model without separate transfer authorization.

## Decisions and authority

The versioned session/answer protocol is separate from the unchanged machine-table schema. New operations are stored in the existing `correction_rules.payload_json`, with the protocol named explicitly:

- `review_queue`: retained cases with `unresolved_candidate` authority. This is queue bookkeeping, not an owner confirmation or independent evidence.
- `review_answer`: the frozen case, selected outcome, verbatim note, and finite support dependencies. The corresponding event preserves the complete structured reply and reviewer label.
- `review_revoke`: the previous support and its affected dependent rules. Old payloads/events remain; only active status and the current interpretation projection change.

A confirmed/rejected directed relation becomes a separate `snapshot_review_answer` relationship with its own rule. Generated or proposed links are never promoted in place. A conflict classification records the review judgment only; it does not create a medical fact or choose which account is true. `insufficient` waits for evidence; `defer` remains out of the default pending batch until explicitly reopened. Blank/unanswered questions do not acquire an answer.

Replacing an answer requires its displayed prior rule ID and a checked preview. Revocation follows explicit dependencies. Independent relationship support remains. If the dependency closure reaches an identity binding or another unsupported operation, the **entire update is refused** rather than guessing an undo. This is not general legacy-archive revocation, nor a completed authority-migration acceptance claim.

## Preservation, failure handling, and privacy

The complete expected snapshot file set, hashes, sizes, quotations, displayed metadata, response scope, prior decisions, and chronology are checked. Preview and apply recompute the same plan. A changed receipt or answer requires another preview. Cross-dependent answers in one batch are rejected when they would invalidate each other.

Application uses the existing SQLite schema and snapshot builder in a private staging directory, preserves source node authority, validates the successor, checks the source again, then publishes the complete directory. An advisory output lock coordinates this workflow's writers; it is not a universal lock for unrelated tools. Originals are never opened for writing. A crash before publication does not install a partial successor; an interrupted published operation can be checked and replayed. There is no multi-archive transaction or automatic pointer update.

The HTML is self-contained, uses text-only rendering and a restrictive content-security policy, and makes no model/network requests. Drafts and exported answers are sensitive local files, not encrypted storage. Keep all real sessions, previews, snapshots, and browser downloads outside Git. Codex can build/test the code with synthetic records; private semantic review remains local unless separately authorized.

## Tests

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s tests -p 'test_snapshot_review*.py' -v
```

Tests cover actual saved-question mention lookup, exact evidence, conflict-first ordering, multiple witnesses per case, invalid/blank/duplicate answers, source preservation, preview gating, replay, persistent deferral, replacement, dependent invalidation, independent support, stale sessions, chronology cycles, and interrupted publication. Lifecycle regressions check that unanswered supplied cases survive partial application, recorded dependencies cannot silently change, and unsupported binding-dependent revocations leave the record untouched. These test review mechanics, not automatic contradiction-detection accuracy.

The browser check uses invented data and the already pinned Playwright dependency from the interface workflow:

```sh
python3 tools/snapshot_review_browser_smoke.py --output data/snapshot-review-browser
```

It checks pagination, draft round trips, structured answer export, inert hostile text, external-request absence, and a narrow viewport. `--memory` is available where administrator policy blocks local-file navigation; that mode explicitly reports that file navigation was not tested. Do not weaken browser policies to run a test.
