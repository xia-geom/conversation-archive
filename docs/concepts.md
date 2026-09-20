# Concepts and outcome rules

[Overview](../README.md) · [Quickstart](getting-started.md) · [Documentation](README.md)

## The project in one example

A conversation contains a user account, a draft written in the first person, and an assistant's interpretation. Copying all three into a summary as facts would change their meaning. The pipeline preserves where each passage came from, lets an extractor propose attributed findings, and keeps acceptance separate from generation.

The design is **deterministic bookkeeping around probabilistic extraction**. Python selects and checks evidence, records attempts, and controls installation. A model proposes meaning. A reviewer or reviewing agent compares that proposal with the existing record; an exact quotation alone cannot do that semantic work.

## Four things that are not interchangeable

| Term | Plain-language meaning | Example artifact |
| --- | --- | --- |
| Evidence | What a particular export actually contains | Original JSON and normalized message records |
| Packet | A bounded view of evidence, with exact source ranges | `reconcile packet` output |
| Candidate | A proposed statement with attribution and quotations | `candidate.json` |
| Master entry | An accepted, organized item in the living record | A checked entry in the canonical Markdown master |

A manifest is an inventory of inputs and identities. A checkpoint records progress. A receipt records a worker attempt and observed usage. None of these files sends a prompt by itself; the controller invokes the worker.

## Who does what?

| Responsibility | Component | Boundary |
| --- | --- | --- |
| Preserve and normalize original exports | `inventory.py`, provider adapters, `pipeline.py` | No summarization or factual inference |
| Independently compare clean records to sources | `validation.py` | Structural fidelity, not personal truth |
| Freeze scope and render exact packets | `reconciliation.py`, `reconcile_cli.py` | Preparing a packet is not reviewing it |
| Select pending packets and persist attempts | `autonomy.py` | One bounded controller state; no master writing |
| Propose structured candidates | `codex_worker.py`, `extraction.py` | Model output is untrusted |
| Check quotations and coverage | `extraction.py` | Exact spans and basic role boundaries, not semantic accuracy |
| Record judgments and install checked changes | Existing reconciliation workflow | Separate explicit decisions and installation journal |

[Browse the implementation](../conversation_archive/) or read the [autonomy contract](autonomy.md).

## How a finding becomes an outcome

These are **review rules**, not a claim that the extraction controller already performs automatic reconciliation:

| What the evidence establishes | Review outcome | Effect on the master |
| --- | --- | --- |
| The same meaningful information is already present | Already represented | No duplicate narrative |
| The same episode has meaningful additional context | Complementary detail | Expand the relevant entry |
| A separate episode or reflection is supported | Distinct episode | Propose a new entry |
| Two passages may concern the same event, but the match is uncertain | Uncertain overlap | Preserve uncertainty; do not silently merge |
| Material should not become a record entry | Excluded with reason | No addition; retain the disposition |

Attribution is a separate dimension. A draft stays a draft; an assistant's speculation stays assistant content. Similar words, a shared person, or a repeated message ID alone do not prove that two episodes are identical. Read the relevant entry and source context before proposing a merge.

## How the controller reacts

| Observed behavior | Implemented response |
| --- | --- |
| Exact valid proposal for every pending piece | Save unreviewed candidates and a receipt |
| Missing or fabricated quotation, wrong span, or invalid coverage | Block the attempt; do not install a master change |
| Insufficient context declared by the worker | Save a `needs_context` disposition; it does not automatically fetch more context |
| Successful extraction already recorded in this state | Skip its model call on resume |
| Call or observed-token threshold reached | Stop between calls; token thresholds can overshoot by one call |
| Missing usage telemetry | Keep usage unknown and stop further calls |
| Interrupted attempt | Require explicit recovery; do not blindly resend |
| Unavailable media | Retain the reference; do not infer its unseen content |

The candidate controller has `pending`, `in_flight`, `extracted`, and `blocked` job states. The reconciliation workflow separately tracks original-evidence review and installation. `needs_context` is a proposal disposition, not a third queue that has already been implemented.

## Why old summaries and raw review have different counts

Historical summaries are useful navigation and extraction products. They do not establish that every original message or branch was reviewed. Treat summary processing, raw-evidence review, and master integration as separate measures; do not add their counts as if they described disjoint conversations.

The current extraction planner reads pending pieces from an existing frozen review run. It does not automatically map historical summary files to source coverage. A future cross-export matching layer must also distinguish an unchanged logical message from its versioned export evidence.

## Current boundaries

The importer and offline demonstration require no model. Live extraction is optional and transfers packet text to the configured provider. Mocked adapter tests do not establish real-model accuracy or runtime isolation.

Automatic candidate-to-master promotion, cross-export incremental matching, a global spend ledger, and a shared cross-process canonical-writer lock remain future work. The current writer expects `emotion_master.md`, `correction_review_report.md`, and `corrections_before_after.md` with the repository's existing schema; it does not edit arbitrary personal documents.

The existing installation guarantee is checked, journaled replacement per file, not an atomic transaction across all three files. Completion refers only to the frozen selection and its recorded dispositions; it does not certify unavailable media or omitted provider history. See the [dated audit](audit-2026-09-20.md) for remaining work and the [data dictionary](data-dictionary.md) for field-level limits.
