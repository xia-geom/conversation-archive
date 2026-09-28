# Architecture — Markdown first

## Product and authority

The product is a maintained `organized.md` containing selected useful conversation information: self-contained entries, qualified accounts, changing interpretations, important connections and compact provenance. It is not a database product or a full-transcript export.

Original exports and historical bundles are evidence, unchanged. Markdown is the maintained editorial document; internal state is bookkeeping, not a second knowledge base. Exact copies are not independent corroboration. Canonical storage does not establish factual truth.

## Structure

```text
Private collection (outside Git)
├── organized.md             One selected maintained document
├── exports/                 Preserved evidence; may remain elsewhere
└── .state/                  Imports, review work, receipts and recovery
    ├── dataset-.../         Validated source locations
    ├── review-.../          Existing source review and patch journals
    ├── reading-.../         Entry audit, draft answers, checked preview
    └── extraction-.../      Optional bounded model attempts

Repository
├── README.md                Product and executable invented demo
├── ARCHITECTURE.md           Boundaries and data flow
├── AGENTS.md                Operating/editorial contract
├── .agents/skills/organize-markdown/SKILL.md
├── conversation_archive/    Import, review, checked edits and reading export
├── tests/                   Invented regression cases only
└── docs/                    Workflow, formats, compatibility, troubleshooting
```

These are suggested locations, not instructions to move or delete existing archives. The output of `reading` is a generated publication until the owner explicitly selects it as the maintained document. Do not maintain two independently edited masters. Preview receipts are not another retrieval system.

## Execution path

```text
Original ChatGPT/Claude exports
    -> normalize / validate / exact source packets
    -> authorized extraction and editorial review
    -> organize draft / check / apply
    -> maintained Markdown
    -> reading prepare / packet / source
    -> whole-entry review: keep, revise, or defer
    -> reading check: proposed text and evidence-access accounting
    -> reading publish: fresh local Markdown after approval
```

The existing `reconciliation.py`, `reconcile_cli.py` and `master_validation.py` retain the checked patch writer. New collections use `--document`; legacy `--master` runs keep their original three-file contract. Optional raw-store tools support exact later-export comparisons; they are not prerequisites.

No step imports SQL. No graph, embedding service, browser application or remote model is required. An authorized agent can supply reviewed decisions; deterministic code does not invent them. Existing model-transfer permissions and cumulative budgets remain applicable.

## Two distinct validation jobs

**Preservation:** original bytes, attribution, IDs, source spans and prior corrections stay recoverable. Do not disable protected-block checks merely to make a file smaller.

**Reading quality:** additions belong in the chosen entry, earlier limitations are reconsidered, citations are attached locally, and output is useful without archival machinery. Code checks structure and evidence placement, not semantic truth.

`reading_document.py` transiently inspects the existing Markdown convention and recognized preserved bundles. It checks preserved-document hashes, entry boundaries, all body citations and stale index titles. It flags coexisting unavailable-source statements and later additions. Title-word overlap can suggest a misplaced addition, but is neither an event match nor exhaustive contradiction detection.

`reading_review.py` provides exact whole-entry packets, bounded source reading, immutable input binding and review reuse. Source omissions are explicit. Initial coverage requires keep/revise/defer for each entry, supplied by an authorized reviewer rather than a compulsory owner questionnaire. Unchanged reviewed context can reuse its recorded attribution; changed entry, evidence or decision context needs review again.

`reading.py` checks complete replacement entries, exact scoped witnesses and changed source associations. Global presence of a quote is insufficient: a witness must identify a claim and a citation in the reviewed entry. It generates one index, body-derived source lists and selected exact evidence. Missing or omitted sources are labeled external instead of left as broken internal links. Full reports, graph tables and encoded attachments are not republished wholesale.

## Editorial and legacy boundaries

The optional [organize-markdown skill](.agents/skills/organize-markdown/SKILL.md) guides semantic review: placement, limitations, contradictions and attribution. New evidence requires rereading the whole affected entry, not just appending text. Historical change is not necessarily contradiction. A scoped correction does not confirm an entire account. Ask the owner only about consequential ambiguity the sources cannot settle.

For recognized old bundles, the reader checks entry locators and converts supported active `bind`/`bind_mentions` decisions into recorded answers plus exact original mention scopes. Unknown active operations stop conversion rather than disappearing. This is a bounded compatibility reader, not restored snapshot infrastructure or complete migration acceptance. Other corrections in prose and source-only context still require editorial scope review.

## Safe updates and the primary reader

Manual edits form the baseline for normal updates; stale hashes stop installation. `reading publish` rechecks input, answers, preview and output hash, then atomically creates a fresh file without overwriting existing content. Exact replay is idempotent. It does not change the input, move a CURRENT pointer, authenticate reviewers or upload anything. Hashes detect drift, not malicious rewriting of all records; retain ordinary backups.

The primary reader must be able to search the Markdown, understand an entry independently and identify available evidence. A path or source ID is not an accessible ChatGPT link. Output distinguishes included exact text from external evidence. Actual upload remains separate.

Test that real workflow before adding another format or service. ChatGPT semantic-search quality requires a separate synthetic evaluation; local substring checks do not measure retrieval recall. File extensions, tags and numeric priority fields do not themselves configure native Project retrieval.

## Acceptance

Run `python3 -m unittest discover -s tests -v`, the Markdown demo and `python3 -m conversation_archive reading --help`. CI uses synthetic data only. Tests cover misplaced additions, stale limitations/indexes, local evidence associations, Unicode spans, preserved confirmations, unavailable sources, deferral, deterministic output, changed inputs, reviewer attribution, manual edits and interrupted publication.

Retired SQL/graph/snapshot/HTML engines remain in Git history; [compatibility](docs/compatibility.md) explains existing-data handling. No automatic semantic repair, medical interpretation, Gemini adapter, cloud synchronization, private-data publication or unattended acceptance of model conclusions is claimed.
