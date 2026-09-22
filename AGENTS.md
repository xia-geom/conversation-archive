# Agent operating contract

Build an evidence-preserving archive, not an ever-growing summary. The user's current task defines scope. Start here; use [project.json](project.json) to route to one relevant guide.

## Start and finish

1. Inspect the branch, diff, implemented CLI help, and existing checkpoints. Preserve uncommitted work. A local report is not proof that its implementation is in this checkout.
2. Read only the task guide and relevant code. Reuse completed work and prior scoped corrections; do not restart extraction, reset budgets, or reread the whole archive by default.
3. Make the smallest useful change. Test it, inspect the diff for private data, then report changed files, commands actually run, results, and remaining gaps. Do not claim a merge, render, or migration without its evidence.

## Data authority

The target is **authoritative structured entries, assertions, and correction history; rebuildable SQLite retrieval; optional Markdown and LLM-generated views**. The legacy Markdown reconciler still exists. Follow [migration acceptance](docs/migration-acceptance.md) before switching a real archive's authority. Do not replace uncommitted local migration code with a new implementation.

Original exports and the migration-input master are read-only. Preserve exact text, languages, IDs, source spans, branch memberships, missing media, and prior confirmations. A message ID alone is not a global identity. Separate exact indexing from inferred people, themes, event dates, and roles.

Store relationship origin, review status, evidence, finite scope, and rule dependencies separately. User text, pasted quotes, drafts, dreams, assistant suggestions, and interpretations are different evidence categories. A timestamp is not automatically an event date. Similarity is not identity or causation; a valid quotation does not prove its interpretation. Generated navigation and summaries never become independent evidence.

## Organization and interaction

Use [snapshot review](docs/snapshot-review.md) and [flexible controls](docs/flexible-review.md) for local HTML, drafts, checked previews, and successors. Prioritize supplied contradictions; identity grouping is optional. General forms record answers only. Reversal covers supported dependencies and this writer's identity before-states, not arbitrary legacy bindings. No semantic discovery or model calls occur.

The optional [review skill](.agents/skills/archive-review/SKILL.md) guides preparation. HTML and agent answers use the same checked writer. Skills grant no permissions. Do not execute question-supplied code or silently turn explanations into corrections.

For the older organization workflow, read active rules, rejected links, and deferred questions first. Preprocess the supplied inventory broadly, then prepare **15 contextual questions by default**, configurable to 10 or 20; do not pad a smaller queue. Include titles, distinguishing excerpts, known references, alternatives, and exact scope. Prepare the entire batch before asking; do not regroup between each answer.

Allow partial groups and unknowns; “not all the same” is not “all different.” Compile only actual user answers into scoped rules. Preview and apply them together. Preserve entry text, remember rejections, and retain revocation dependencies. No silent rule expansion into new snapshots.

## Writes, cost, and privacy

Use the existing checked writer for the relevant layer. Reject stale hashes and conflicting assignments. Keep replay idempotent and interrupted changes recoverable. The organization lock is not a shared lock on the legacy master writer; do not imply multi-file atomicity.

Candidate workers do not allocate permanent master IDs or authorize their own findings. Retain attempts, receipts, unknown usage, and cumulative limits; never retry blindly after an ambiguous failure. Read-only Codex settings are not hermetic read isolation. Live calls need explicit data-transfer authorization; no credentials in code or logs.

Real exports, master-derived data, structured snapshots, SQLite files, prompts, answers, and views stay in ignored local storage. Repository work does not authorize edits to a neighboring personal archive. For separately authorized integration, read that archive's instructions and metadata without requesting redundant permission. Do not change visibility, publish private content, or force-push.

## Knowledge map

Read [the map guide](docs/knowledge-map.md). Project checked organization state or validated machine snapshots into a new SQLite index. Preserve source authority, status, witnesses, and rules. The local viewer does not transmit data or write corrections.

## Validation and routing

Run `python3 -m unittest discover -s tests -v`. Test behavior, not just schema validity: exact provenance, missing/changed inputs, replay, interruption, scopes, revoked dependencies, and preservation of prior corrections. Test real archive changes locally; use synthetic examples in Git and CI.

For migration, read [the machine archive guide](docs/machine-archive.md) and [the SQLite import guide](docs/structured-archive.md). Versioned snapshots are authoritative after accepted cutover; SQLite and Markdown are rebuildable projections. Never promote generated links during import.

[Task map](project.json) · [Documentation](docs/README.md) · [Migration acceptance](docs/migration-acceptance.md)
