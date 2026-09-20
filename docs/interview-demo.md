# Interview demonstration and development plan

## The engineering story

Present this as an **evidence-preserving conversation-to-knowledge pipeline**, not a chatbot wrapper. The interesting problem is preserving authorship, versions, branches, uncertainty and recoverability while using a probabilistic model for extraction. The design makes deterministic software own scope, identities, validation, accounting and commits; the model proposes attributed candidates.

A defensible current description:

> Built a Python pipeline for preserving and validating conversation exports, with exact-source provenance, branch-aware review packets, journaled reconciliation, and a bounded resumable Codex candidate-extraction controller. Added synthetic tests for malformed evidence, attribution boundaries, interruption recovery and duplicate-call prevention.

Use first-person ownership only for work you can explain and defend. Explain the AI-assisted development process, which design choices you made, what you inspected, and how tests challenged generated code. Do not claim measured model accuracy or fully automatic master integration before those exist. Keep the private case-study report separate; obtain permission before disclosing any operational metrics beyond this synthetic repository.

## Five-minute offline demo

Run from the repository root:

```sh
python3 -m conversation_archive.demo --output data/interview-demo
python3 -m conversation_archive.autonomy status --state data/interview-demo/extraction
python3 -m unittest discover -s tests -v
```

Use a fresh output directory for another demonstration. No Codex installation, API key, personal export or network is required. The worker is a deterministic fixture, deliberately **not** a semantic model.

1. Show the invented source: multilingual text, an unsent draft, two branches, a repeated original message ID, and missing media. Explain why flattening or global ID deduplication would lose meaning.
2. Open one packet and candidate sidecar. Follow a quoted span through its piece offset, message occurrence, JSON pointer and source hash. Explain that exact quotation validates provenance, not interpretation.
3. Show the returned first-pass, resumed and replay counts. The first pass uses one fixture call; resuming completes pending work; replay starts zero additional calls. Show the interruption tests for the ambiguous-response case.
4. Show fabricated-quote rejection and that raw-review coverage is still zero and master hashes unchanged. Candidate generation is not authorization to rewrite the record.
5. Explain the next milestone: reviewed promotion, a shared master writer lock, and a gold-standard evaluation set. Finish with one limitation you can explain precisely rather than an unsupported accuracy claim.

## Design decisions worth defending

| Decision | Why it is useful now | Trade-off |
| --- | --- | --- |
| JSONL + ordinary files | Inspectable, portable, no service dependencies | Queries and concurrent writers are less convenient than a database |
| One controller and candidate-only workers | Clear trust boundary and predictable resource use | Lower throughput; master promotion remains separate |
| Exact evidence plus attribution | Auditable origin and fewer obvious role mistakes | Does not establish semantic truth or recall |
| Frozen input scope | Repeatable coverage and safe resumption | New exports need an explicit incremental mapping layer |
| Fail-stop unknown usage | Avoids blind paid retries after interruption | Operator audit is needed to resume blocked work |
| Small structured prompts | Reproducible contracts, limited context | Long-range context must be requested rather than guessed |

## Evaluation that would make the project substantially stronger

Do not optimize for number of extracted facts. First build an annotated synthetic set and record expected atomic facts, attribution, evidence spans, nonfacts and deliberate ambiguities. Split prompt-development examples from a held-out set. Match predicted facts to reference facts with a documented manual adjudication protocol; exact string equality is insufficient for paraphrases.

Report precision of supported candidates, recall of salient annotated facts, attribution error, uncertainty/abstention behavior, false merges, and source coverage independently. Report counts and denominators; do not average away empty or difficult cases. An abstention can be appropriate but should not inflate recall. Use source/branch groups when splitting to avoid near-duplicate leakage.

For efficiency, record model/version/effort/prompt fingerprint, input/cached/output usage, wall time, failures, and accepted supported candidates on the same fixed workload. Keep deterministic validation failures separate from semantic errors. Compare a simple rule baseline, one economical model configuration, and one escalation configuration. Do not reuse unverified per-token price claims; apply a dated pricing source only when actual billing is known.

## Practical milestones with exit criteria

**Milestone 1 — This extension.** Run the offline demo; inspect candidates; resume without repeating successful calls; pass source-contract and recovery tests. The real Codex adapter still needs a small explicit live calibration run on synthetic data.

**Milestone 2 — Review and commit.** Add an explicit candidate-to-review proposal referencing existing entries, complete context and candidate hashes. Implement a cross-process lock for the canonical writer. Demonstrate competing writers cannot interleave and that interrupted application recovers without duplicate history.

**Milestone 3 — Incremental exports.** Reimport a modified synthetic export and show unchanged content is not charged again, changed spans are reviewed, and every branch membership remains accounted for. Distinguish logical identity from immutable evidence identity.

**Milestone 4 — Quality and navigation.** Publish the annotated synthetic evaluation and a reproducible report. Add a local evidence browser or lexical search only after identifying actual review bottlenecks. A small tested system with honest boundaries is a stronger demonstration than an unmeasured multi-agent stack.
