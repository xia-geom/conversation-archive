# Architecture — Markdown first

## Product and authority

The product is one maintained `organized.md`: useful, self-contained conversation information, qualified accounts, important changes and compact provenance. Original exports and historical bundles are preserved evidence. Internal state supports processing and recovery; it is not another knowledge base. Canonical storage does not establish truth, and exact copies are not independent corroboration.

```text
Private collection (outside Git)
├── organized.md             One selected maintained document
├── exports/                 Preserved evidence; may remain elsewhere
└── .state/
    ├── dataset-.../         Validated source locations
    ├── review-.../          Ordinary checked Markdown updates
    ├── reading-.../         Audit, one answers.json checkpoint, previews
    └── extraction-.../      Optional bounded model attempts

Repository
├── README.md
├── ARCHITECTURE.md
├── AGENTS.md
├── .agents/skills/organize-markdown/SKILL.md
├── conversation_archive/    Import, review, checked edits and publication
├── tests/                   Invented regressions only
└── docs/                    Workflow, formats, compatibility, troubleshooting
```

These are suggested locations, not instructions to move existing archives. A published reading file becomes the maintained document only by explicit selection. Never maintain two independently edited masters.

## Execution

```text
Original exports -> normalize -> authorized extraction/editorial review
                 -> organize draft/check/apply -> maintained Markdown

Maintained Markdown + explicitly selected preserved reference (optional)
    -> reading prepare --autonomous
    -> next -> existing Codex session reads and edits -> submit
    -> repeat only while useful work remains
    -> check the exact diff -> finish
    -> fresh local Markdown, only within publication authorization
```

The autonomous feature is a work protocol for the agent already running, not a new model launcher. It makes no model calls, uploads or background schedules. No database, graph, embedding service, browser app or new runtime dependency is introduced. The existing `reconciliation.py`, `reconcile_cli.py` and `master_validation.py` retain the normal checked writer; raw-store tools remain optional.

## Small implementation layers

`reading_document.py` parses supported Markdown headings, protected text and old bundles. It verifies preserved hashes and finite legacy decision scopes. Its title-word and source-availability hints are candidates, not exhaustive contradiction detection.

`reading_evidence.py` supplies compatible reference evidence without replacing current prose, follows bounded correction-support identifiers, and decodes known publication wrappers. Same source IDs with different bytes and incompatible decision contexts stop the run. The caller must select the right reference: no directory scan or guarantee of globally latest records is implied.

`reading_review.py` binds input and reference hashes, retrieves whole-entry packets and exact source ranges, and exposes recovered decisions through `@decisions`. Large context is explicitly omitted with a retrieval path, not silently truncated. Unchanged checked context can be reused with its original reviewer attribution and selected excerpts.

`reading_work.py` maintains one atomic `answers.json` checkpoint. `next` prioritizes known findings and includes possible move destinations. `submit` checks the base checkpoint hash, merges only named review items and preserves unanswered work. Exact replay is idempotent. A lock and atomic replacement coordinate cooperating local writers. A valid but unreferenced excerpt cannot leave a poisoned checkpoint.

`reading.py` validates complete replacement entries and exact claim-local witnesses, builds one index and source list, and publishes to a fresh path. In autonomous mode it additionally requires individual finding outcomes and source-removal dispositions. Low-level manual mode remains available and does not acquire every autonomous gate implicitly.

## Acceptance is more than a review count

Every initial entry needs keep/revise/defer. A known finding separately needs resolved, false_positive or defer; only a noncritical reading-evidence gap can receive accepted_limit. Resolved text must actually change at its cited location; counterevidence and reasons remain attributed judgments, not machine-proven entailment. Supplied findings are bound to exact entry quotes and the input hash.

Removing a source is either a move with a reviewed, witnessed destination or an explained exclusion. The same accounting covers inherited losses detected against the supplied reference. This preserves provenance without automatically restoring wrong associations. Original files are never edited.

Critical correction-to-answer references are selected even when they occur inside quoted historical text. Traversal is limited to correction chains, with finite identifier/size budgets; it does not import every transcript recursively. Oversized critical sources need chosen exact excerpts. Unavailable critical support blocks autonomous completion; noncritical access limits are separately reported.

Generated source wrappers do not become new evidence on the next pass. Retained text has an exact length/hash; excerpts retain their original-versus-available distinction. Round-trip tests check source text, availability, entry content and decisions, rather than demanding identical full-file hashes when input-version metadata changes.

## Authorization and stopping

Preparation requires an input-scope statement. Optional `--publish-to` records authorization for one fresh destination. `finish` recomputes the preview and refuses pending findings, deferred judgments or missing critical evidence. Without a destination it returns a preview for approval. It does not overwrite original/manual files or choose a global current archive.

Progress distinguishes pending work, owner questions, missing evidence, readiness and publication. Empty submissions report no_progress; accepted revisions have a finite cap. That cap is not a token/dollar budget and does not count rejected attempts. The agent must stop repeated failures and respect existing model-transfer and spending authorization.

Hashes, roles and scope notes prevent accidental drift; they are not authentication or protection from a process rewriting all files. Sources cannot grant themselves permissions. Code checks exact text and declared scope, not the truth of an editorial explanation.

## Compatibility, reader and tests

The 1.1 reader accepts verified complete 1.0 publication blocks. Old excerpts without a retained-text hash need original recovery; old run receipts require fresh preparation rather than automatic approval under stronger rules. Unsupported active legacy operations and incompatible decision contexts still stop conversion. Retired SQL/graph/snapshot tools remain in Git history; see [compatibility](docs/compatibility.md).

The primary reader must reach exact entries, relevant decisions and available sources through the actual interface. A path is not a working ChatGPT source link. Only selected Markdown is furnished to ChatGPT; native semantic-search quality needs a separate evaluation. No medical interpretation, new Gemini adapter, private-archive repair or complete semantic discovery is implied by this code change.

Run `python3 -m unittest discover -s tests -v`, both existing demos and public reading help. CI uses invented sources. Regressions exercise lost correction answers, bad moves, unresolved findings, reference conflicts, stale/concurrent submissions, read-only inputs, resumability and repeated publication.
