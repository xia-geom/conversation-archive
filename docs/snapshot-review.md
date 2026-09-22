# Snapshot review: local HTML, checked decisions

[Agent contract](../AGENTS.md) · [Flexible controls and design](flexible-review.md) · [Machine archive](machine-archive.md) · [Older batches](question-batches.md)

## What the reviewer does

Read a validated machine snapshot and prepare one offline dashboard with a searchable queue and batches of 15 (adjustable from 1 to 20). Supplied potential conflicts come first, directed relationships next, general forms next. Identity questions are optional; selecting the Identity type includes them in the current batch.

The renderer shows exact entry quotations, expandable preserved entries, metadata, recorded source references, prior answers, and history. It does not invent links or verify inaccessible original medical pages. An empty conflict queue means no cases were supplied or retained, not that an archive is contradiction-free.

The same checked writer handles structured answers regardless of whether they came from HTML, a hand-authored file, or an authorized agent-assisted client. See [the flexible design](flexible-review.md) for general forms, grouping, and the optional skill. There is no second editable master or browser permission to write the archive directly.

## Prepare

Run from the repository checkout. These paths are placeholders; real archives, sessions, prompts, and answers stay outside Git.

```sh
python3 -m conversation_archive.snapshot_review prepare \
  --archive /path/to/private/archive-v1 \
  --output /path/to/private/review/session-01 --size 15
```

Optional `--cases /path/to/private/cases.json` accepts exactly `protocol`, `basis_snapshot_id`, and `cases`. The protocol is `snapshot-review-1.0`; the basis must match the selected snapshot. Each case contains `kind`, `title`, `prompt`, `reason`, `evidence`, and `depends_on`. Evidence names exact `entry_id`, `start`, `end`, and `quote` values; offsets count Unicode characters, not bytes.

A `conflict` needs at least two distinct assertion occurrences. A `relationship` additionally names `source_entry_id`, `target_entry_id`, and a supported directed `relation`. A `form` adds a versioned declarative `form` as documented in [flexible-review.md](flexible-review.md). Identity controls are derived from the existing source-question/mention registry, not fabricated mention IDs.

Titles, comparison context, and grouped cases remain proposals. Dependencies name explicit support rules, not mere thematic overlap. Inactive dependencies block substantive acceptance. Duplicate quotations do not become independent corroboration. Private cases must not be sent to a remote model without separate authorization.

## Review and save

Open `session-01/review.html`. The folder also contains `session.json` and `answers.template.json`. Prepared rows freeze their control specifications and source scope. Nothing is preselected, and preparing or saving is not reviewing or applying.

Save draft retains all unfinished fields and notes, even when no outcome was selected. Restore is session-scoped. Drafts stay in memory until explicitly downloaded, with an unsaved-change warning; no localStorage is used. Export answers includes only explicit outcomes and their permitted visible field values. Text is preserved without semantic parsing. Grouping assigns each displayed reference once to a group or Unknown; it does not classify unseen references.

## Preview

```sh
python3 -m conversation_archive.snapshot_review preview \
  --archive /path/to/private/archive-v1 \
  --session /path/to/private/review/session-01/session.json \
  --answers /path/to/private/review-answers.json \
  --output /path/to/private/review/preview-01
```

Inspect `preview-01/preview.html`: outcomes, exact values/evidence, proposed identity bindings, withdrawn decisions/dependencies, and pending cases retained. General forms record an answer only, not a change to medical data. Confirming a disagreement does not decide which source is true. A preview is not an applied update.

## Apply an explicit answer

```sh
python3 -m conversation_archive.snapshot_review apply \
  --archive /path/to/private/archive-v1 \
  --session /path/to/private/review/session-01/session.json \
  --answers /path/to/private/review-answers.json \
  --preview /path/to/private/review/preview-01/preview.json \
  --output /path/to/private/archive-v2 \
  --snapshot-version local-v2 --confirm-user-answer
```

The command recomputes the plan, verifies the exact preview, stages and validates the successor, rechecks source hashes, then publishes a complete directory. It does not edit originals or advance a global CURRENT pointer. Select the successor explicitly or rebuild retrieval with existing machine-archive/knowledge-map tools. Independently created successors are branches, not an automatically merged archive.

Replay of an unchanged submitted event returns `already_applied`. Stale different answers are refused without deleting the draft. After applying a partial batch, prepare a new session/preview. No automatic rebase by question number occurs. An advisory output lock coordinates these writers, not unrelated tools or multiple archives.

## Decisions, continuity, and reversal

Existing correction tables remain canonical. `review_queue` stores retained unresolved candidates; it is not owner confirmation. `review_answer` stores the exact frozen case, chosen outcome, values when present, note, and finite dependencies. `review_revoke` preserves the target and affected support history. Old events/payloads stay available.

A directed answer creates its own confirmed/rejected projection rather than promoting a generated edge in place. Identity grouping creates finite `bind_mentions` operations with an explicit `review-identity-1.0` before-state and a dependent `refers_to` projection. Generic forms record values without changing entities or fact fields. Old scalar sessions remain valid but cannot acquire new grouping actions without preparation of a new checked session.

Unanswered supplied cases survive the successor as proposals. Deferral stays out of the default pending queue until reopened. Insufficient evidence remains distinct from no answer. Partial identity groupings preserve unknown references and the source question; complete groupings retain the question definition in history.

Replace/reopen supported review decisions using their displayed previous rule ID. The writer withdraws explicit dependent support and restores its own reversible identity bindings. It refuses arbitrary legacy bindings, independent identity support, external entity uses, and mutually invalidating batches rather than guessing an undo. These limits are listed in the preview and [design guide](flexible-review.md); this is not unrestricted entity merging or a completed migration-acceptance claim.

## Privacy and verification

The self-contained HTML uses text-only rendering, restricted content security policy, and no remote assets, model calls, or network requests. Saved pages and downloads are sensitive files, not encrypted storage. Reusable code/tests belong in Git; real data does not. Local directory placement alone does not rule out cloud sync or model transfer.

```sh
python3 -m unittest discover -s tests -v
python3 tools/snapshot_review_browser_smoke.py --output data/snapshot-review-browser
python3 tools/flexible_review_browser_smoke.py --output data/flexible-review-browser
```

Tests cover original scalar behavior, evidence/hashes, replay, stale answers, partial queues, deferral, replacement, dependency reversal, interruptions, flexible fields, and grouping. Browser tests use invented data. `--memory` explicitly reports local-file navigation as untested when administrator policy blocks it. Do not weaken browser policy to make a test pass.

Not implemented: automatic contradiction discovery, native PDF/Notes/Gemini adapters in this reviewer, medical interpretation, arbitrary legacy correction reversal, live chat parsing, direct browser writes, or automatic personal-archive updates.
