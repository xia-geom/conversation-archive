# Conversation archive

A small Python pipeline for preserving and inspecting ChatGPT and Claude exports.
**Clean means consistently structured and traceable. Text is not rewritten, summarized, translated, or classified.**

This repository contains code, documentation, and invented test conversations only. Real exports stay where they are. Local configuration, derived datasets, inventories, and reports are excluded from Git. The importer never changes a personal master. The optional reconciliation layer can install explicitly reviewed, checked changes into a canonical master and its two reports when the owner authorizes integration.

## Understand the data flow

```text
Original JSON files or JSON inside ZIPs (read-only)
  → inventory: identify payload bytes with SHA-256, retain duplicate locations
  → provider adapter: project each conversation, message, and attachment reference
  → independent validation: compare records back to the original JSON
  → install a complete dataset only when validation has no errors
```

The three tables are **JSONL**: each line is one complete JSON object. You can read a line without learning a database first.

| Output | What one record represents |
| --- | --- |
| `conversations.jsonl` | One conversation in one source, including its parent graph and exported metadata |
| `messages.jsonl` | One message occurrence in that conversation; original object plus readable fields |
| `attachments.jsonl` | One exported attachment/file/multimodal reference, not a copy of its bytes |
| `manifest.json` | Input locations and hashes, duplicate aliases, importer version, output hashes and counts |
| `validation_report.json` | Errors, warnings, counts, and limitations of the completed import |

A message contains `raw` (the complete original JSON object) and `text_segments` (exact strings with source pointers). Claude sometimes exports different strings in `text` and its text blocks. Both remain accessible; **do not concatenate or count them as separate utterances**. Attachment text and exported audio transcriptions are explicitly marked. A transcript is not verified against the original speech. Assistant thoughts and tool blocks remain in `raw`; they are not projected as user statements.

## Run the invented example first

Requires **Python 3.11 or later**. No third-party runtime or test dependencies, account, or API key is needed. Run commands from the repository directory; installation is optional.

```sh
python3 -m unittest discover -s tests -v
python3 -m conversation_archive inventory --config tests/fixtures/demo.toml --output data/demo-inventory.json
python3 -m conversation_archive normalize --config tests/fixtures/demo.toml --output data/demo
python3 -m conversation_archive validate --dataset data/demo
python3 -m conversation_archive inspect --dataset data/demo --kind messages --line 1
```

The example has four conversations, eight message occurrences, and two attachment references. Normalization also validates automatically. Output directories must be new or empty; an existing dataset is never overwritten. To repeat the example, use another directory such as `data/demo-repeat`.

The [walkthrough](docs/walkthrough.md) explains what to predict, inspect, and deliberately break. The [data dictionary](docs/data-dictionary.md) explains every field and its limits.

## Import your exports locally

Create an ignored `local.toml`. These are illustrative paths, not locations that the code assumes:

```toml
[[sources]]
provider = "chatgpt"
path = "/path/to/chatgpt-export"
attachment_root = "/path/to/chatgpt-export" # optional; exact relative filenames only

[[sources]]
provider = "claude"
path = "/path/to/claude/conversations.json"

# Optional independently observed acceptance counts, not guessed values:
# [expected]
# chatgpt_conversations = 123
# claude_conversations = 45
```

A source may be a JSON array file, a directory of `conversations.json` / `conversations-NNN.json`, or a ZIP containing those names. Directory scanning is **nonrecursive** and does not automatically open ZIPs. Explicitly list a ZIP when you want it checked. ZIP members are read in memory, without extracting files. All configured payloads must be valid UTF-8 JSON arrays. Duplicate JSON keys and nonfinite numbers are rejected because ordinary JSON parsing could lose information.

```sh
python3 -m conversation_archive inventory --config local.toml --output data/inventory.json
python3 -m conversation_archive normalize --config local.toml --output data/clean-v1
python3 -m conversation_archive validate --dataset data/clean-v1 --report data/recheck.json
python3 -m conversation_archive inspect --dataset data/clean-v1 --kind messages --line 1
```

`inspect` displays the clean record, its original JSON at the recorded pointer, and source locations. You can use `--record-id` instead of `--line`. It checks the clean file hash and the source hashes first. Its output may contain private conversation text; keep terminal captures local.

Only conversation payloads are imported. HTML views, account/login metadata, derived memories, project documents, and library sidecars are not silently treated as conversation messages. This milestone does not infer project membership, event dates, emotions, diagnoses, or relationships.

## What makes this trustworthy—and what does not

- **Source fidelity:** source hashes are checked before and after processing, and again during validation. Every exported message occurrence must have a clean record. Missing values, Unicode, punctuation, and unknown content are retained in original objects. JSON whitespace/key order and numeric spelling are not reproduced in clean files; original source bytes are retained in place and hashed.
- **Membership before deduplication:** original message IDs can recur across conversations. Record IDs use provider, source payload hash, and JSON pointer, so occurrences remain separate. Only byte-identical source payloads from the same provider are imported once. Their file/ZIP locations are all recorded and checked.
- **Branch preservation:** parent links, null graph nodes, and exported selection information survive. Absent ChatGPT child lists are `null`; branch counts can be calculated from explicit parent links. Claude's selected branch remains unknown. A reused message ID or branch title does not prove cross-conversation ancestry.
- **Independent checks:** the validator rereads raw JSON and performs its own census and field/graph checks. It does not merely trust counts supplied by the adapters. Invalid references, cycles, unexpected counts, or changed text prevent installation.
- **Honest attachment limits:** an exact relative filename can identify a local candidate, but does not prove it is the original attachment. Missing, ambiguous, unsafe, and unverified references remain visible. No network attachment fetches occur.
- **Reproducibility:** the same input bytes, source locations/configuration, attachment state, and importer version produce identical output bytes. There are no generated wall-clock timestamps. Moving a source changes manifest paths but not source-based record IDs. Changing any byte in a source produces new IDs for that payload: these are versioned evidence identities, not lifetime conversation IDs.

Warnings permit an import but require interpretation; errors stop it. Unknown content shapes are preserved in `raw` and reported. Unsupported structural shapes stop the import with a clear error instead of producing a partial dataset. A failed staged dataset is removed; the error explains the failed check. The completed local report separates errors, warnings, and export limitations.

Validation establishes **structural fidelity**, not the truth of personal accounts, completeness of the account history, or correctness of assistant explanations. Exported assistant content is not independent evidence of a user experience. Git ignore rules prevent normal accidental staging, but are not access control or encryption; inspect the staged files and history before publishing.

## Repository map

```text
conversation_archive/
  model.py                 shared identity and provenance helpers
  inventory.py             input discovery, hashes, strict JSON, source pointers
  adapters/chatgpt.py       ChatGPT graph projection
  adapters/claude.py        Claude parent graph and content projection
  pipeline.py              staged output, attachment candidates, inspection
  validation.py            source census and fidelity checks
  reconciliation.py        frozen review inventory, packets, decisions, installation journal
  master_validation.py     active Markdown structure and preservation checks
  reconcile_cli.py          prepare, packet, record, status, check, apply
  __main__.py              importer commands and reconciliation dispatch
 tests/                    invented fixtures and evidence-focused tests
 docs/                     dictionary, walkthrough, later learning stages
 data/                     ignored local output (created when commands run)
 local.toml                ignored local paths and expected counts
```

See [collaboration instructions](AGENTS.md) for how implementation changes should be explained and verified. Later stages—SQL, exploratory analysis, statistics, longitudinal work, annotations, search, and evaluation—are outlined in the [learning roadmap](docs/roadmap.md), not implemented yet.

## Reconcile original conversations with a living record

The optional flow is **validated records → readable packets → explicit findings → checked master changes**. Preparing a packet does not mean it was read; recording a review does not mean its findings were integrated. Review decisions and private installation journals belong in a local ignored manifest directory, never in Git.

The [reconciliation walkthrough](docs/reconciliation.md) explains the six commands and includes a complete invented-data exercise. Start with `python3 -m conversation_archive reconcile --help`. The importer and its schema remain unchanged; reconciliation has its own review-format version. It checks source and dataset hashes again, retains branch alternatives and exact text ranges, and refuses stale master changes. Installation is atomic per file and journaled across the master and both reports so interruption can be recovered.

Software can verify that a passage exists and a change preserves recorded evidence. It cannot decide that a recollection is true, infer an emotion, or turn an assistant explanation into an owner-confirmed fact. Those remain explicit review judgments. SQL, visualization, embeddings and automated interpretation remain later stages.
