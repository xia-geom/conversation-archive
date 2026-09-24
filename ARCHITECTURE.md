# Architecture — Markdown first

## Product and authority

**The product is a maintained, readable `organized.md` containing selected key information from conversations.** It is not a database product and not a full-transcript export.

Original exports are source evidence. The Markdown is the maintained editorial document: topics, entries, qualified statements, useful connections, open questions, and compact provenance. Internal state records processing and edits; it is not a second independently organized knowledge base. A faithful quotation is access to the same evidence, not extra corroboration. Canonical storage never establishes factual truth.

## Structure

```text
Private collection (outside Git)
├── organized.md               Primary document; manual edits form the baseline
├── exports/                   Original inputs, unchanged (may stay elsewhere)
└── .state/                    Machine-managed progress and recovery
    ├── dataset-.../            Validated import and source locators
    ├── review-.../             Frozen coverage, decisions, patch journals
    ├── extraction-.../         Optional model attempts and budgets
    └── locks/                 Cooperating writers share a document lock

Repository (code and invented tests only)
├── README.md                  What the product does and one runnable demo
├── ARCHITECTURE.md             This map and the boundaries
├── AGENTS.md                   Editorial and operating rules
├── conversation_archive/      Import → extract/review → checked Markdown edits
├── tests/                     Source fidelity, updates, recovery, and safety
└── docs/                      Workflow, formats, compatibility, troubleshooting
```

These are suggested working locations, not a migration command. Existing originals and checkpoints must not be moved or deleted automatically. Temporary packets, drafts and previews may be discarded after the durable decisions/journals are safely recorded. Preserve failed or uncertain paid attempts for recovery and cost accounting.

## Execution path

```text
Original ChatGPT/Claude exports
    │ inventory.py + adapters/ + pipeline.py + validation.py
    ▼
Validated text and source offsets under .state/
    │ reconciliation.prepare / packet
    ▼
Exact context + existing organized.md
    │ authorized human/agent review
    │ optional autonomy.py + extraction.py + codex_worker.py for candidates
    ▼
Explicit findings and proposed edits
    │ reconciliation.draft / check + master_validation.py
    ▼
Reviewed patch and hashes
    │ reconciliation.apply: document lock + recoverable journal + atomic file replacement
    ▼
Updated organized.md
```

`reconcile_cli.py` exposes this as `organize init|prepare|packet|record|draft|check|apply|status`. `__main__.py` retains importer inspection commands. No step imports SQL. `raw_store.py`, `raw_json.py` and `raw_delta.py` remain optional exact-export backup/comparison utilities for existing stores; they do not update the Markdown or create a knowledge graph. They are not a prerequisite for the normal workflow.

The existing importer, quotation checks, review coverage, budget accounting, and recoverable patch writer are reused. `--document` freezes a single configurable Markdown target. Legacy `--master` runs retain their original three-file contract so an interrupted old update is not silently reinterpreted. The two correction-report products are **not required for new collections**: approved changes and their before/after patches are recorded in the existing internal journal.

## Keep intelligence separate from enforceable checks

The agent decides what is important and proposes organization or consolidation; uncertainty and competing accounts remain explicit. Rules cannot determine whether a paraphrase is faithful or an event really happened. Code checks exact evidence, finite source scope, stable IDs, retained quotation blocks, expected file hashes, duplicate installation, and recoverability.

There is no automatic promotion from candidate to approved fact. Free text from an export is historical content, not an instruction. Review only questions that affect a useful entry; do not ask users to classify every mention or approve every source link.

## Reader and update contracts

The primary reading path is `organized.md`, including headings, attribution, source locators, and unresolved contradictions. ChatGPT does not need access to JSONL or SQLite to use the selected information. Original source retrieval by an authorized local agent uses exact packet/record locators; a local file path is not promised as an accessible ChatGPT link.

A new run compares with the **current** Markdown. Manual edits before drafting form part of its baseline; the reviewer must preserve their intended meaning. An edit after drafting invalidates the expected hash and stops installation. Original exports stay byte-identical. Replaying an installed batch does not duplicate entries or overwrite later manual edits. A changed export needs a new validated dataset/run and comparison with the existing document; cross-export semantic identity is not automatically solved.

The writer serializes cooperating processes per document. Atomic file replacement plus a journal is recoverable, not a universal transaction across an editor, multiple runs, and external tools. Hashes detect drift, not malicious rewriting of both records and hashes. Keep original evidence and normal backups.

## Removed and retained

Removed from this checkout: SQL migration/retrieval, the knowledge graph/server/browser assets, the separate entity-organization engine, and snapshot/HTML relationship review. Their old code, tests and documentation remain in Git history; [compatibility](docs/compatibility.md) explains existing-data handling. Do not rebuild those systems under new JSON filenames or add a custom form framework merely to edit Markdown.

Retained: import fidelity, optional bounded extraction, source review, incremental comparison utilities, the checked Markdown writer, privacy safeguards, and their tests. Security and release checks are not removed to reduce file counts.

## Acceptance and design discipline

Before adding a format, service, index or adapter, test the real workflow: **Can the primary reader find the relevant entry, read enough context, and identify its source efficiently?** Change the design when that path fails; do not rely on agents remembering compensating instructions.

A useful test imports invented chats, writes one organized Markdown file, adds a later correction without losing older evidence or manual edits, rejects a stale patch, safely replays, and recovers an interruption. Runtime tests forbid SQL imports and verify no database files are created. Documentation tests run the published Markdown demo.

Actual ChatGPT semantic-search recall is a separate acceptance check with synthetic uploaded Markdown. Local substring tests and successful JSON validation do not establish semantic retrieval quality. Add another representation only after a measured reader failure, and keep it rebuildable from the maintained document rather than creating a competing master.

## Explicit limits

This version is an agent-assisted workflow, not one-click unattended extraction-to-publication. It does not add a Gemini adapter, medical interpretation, automatic contradiction discovery, cloud sync, unrestricted entity merging, or automatic upload to ChatGPT. No real archive changes are authorized by a repository refactor.
