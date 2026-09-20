# Import your own exports

[Overview](../README.md) · [Quickstart](getting-started.md) · [Documentation](README.md)

**Goal:** produce a validated, inspectable dataset from local ChatGPT or Claude export files. This stage does not invoke a model, rewrite your source files, or update a personal master.

Start with the [invented demo](getting-started.md) before using private material. You need Python 3.11 or newer. Run the commands below from the repository root.

## Configure local sources

Create an ignored `local.toml` in the repository root. Use [examples/exports.example.toml](../examples/exports.example.toml) as a template; do not overwrite an existing local configuration. Replace the illustrative paths with your own absolute paths:

```toml
[[sources]]
provider = "chatgpt"
path = "/path/to/chatgpt-export/conversations.json"
# attachment_root = "/path/to/chatgpt-export" # optional

[[sources]]
provider = "claude"
path = "/path/to/claude-export/conversations.json"
```

Remove any source block you do not have. Paths resolve relative to the configuration file when they are not absolute. Keep exports in their original local location, outside the repository; only the template with placeholder paths belongs in Git.

## Import and inspect

Choose a new output path; existing nonempty datasets are not overwritten:

```sh
python3 -m conversation_archive inventory --config local.toml --output data/inventory.json
python3 -m conversation_archive normalize --config local.toml --output data/clean-v1
python3 -m conversation_archive validate --dataset data/clean-v1 --report data/recheck.json
python3 -m conversation_archive inspect --dataset data/clean-v1 --kind messages --line 1
```

`normalize` already validates before installing its output. `validate` reruns those checks explicitly. `inspect` displays a clean record, its original source object, and the recorded locations after checking hashes. Use `--record-id` instead of `--line` when you know a record identity. Inspection output may contain private text; do not publish a terminal capture.

A failed check is not permission to discard difficult messages or bypass validation. Use the reported error to inspect the source and the [troubleshooting guide](troubleshooting.md).

## Supported source formats

A configured source may be a UTF-8 JSON array file, a directory of `conversations.json` / `conversations-NNN.json` files, or a ZIP containing those names. Directory scanning is nonrecursive and does not automatically open ZIP files: list each ZIP explicitly. ZIP members are read without extracting files onto disk.

Duplicate JSON keys and nonfinite numeric values are rejected because ordinary parsing could silently lose information. Unsupported structural shapes stop the import rather than producing a partial dataset. Unknown content shapes that can be retained are preserved and reported.

Only conversation payloads are imported. HTML views, account/login metadata, project documents, library sidecars, and derived memories are not silently counted as conversation messages. The importer does not infer project membership from titles or content similarity.

When you have independently observed acceptance counts, optional `[expected]` fields can check them. Do not invent counts to satisfy validation; the [synthetic configuration](../tests/fixtures/demo.toml) shows a real fixture example.

## Understand the output

Each JSONL line is one JSON object; no database is required to read it.

| File | One record or purpose |
| --- | --- |
| `conversations.jsonl` | One conversation occurrence in a source, including exported metadata and graph |
| `messages.jsonl` | One message occurrence, its original object, and readable text segments |
| `attachments.jsonl` | One attachment or multimodal reference, not necessarily the referenced bytes |
| `manifest.json` | Source locations/hashes, duplicate aliases, importer version, output hashes, and counts |
| `validation_report.json` | Errors, warnings, counts, and limitations for the completed import |

A message retains `raw`, the complete original JSON object, plus exact `text_segments` with source pointers. Claude can export both `text` and text-block representations: both remain available, but they are not automatically two separate utterances. Exported transcriptions are labeled and are not verified against the original speech. Internal assistant content stays separate from user statements.

Read the [data dictionary](data-dictionary.md) for field definitions and the [walkthrough](walkthrough.md) for inspection exercises.

## What preservation means

**Source fidelity.** Sources are read in place and hashed before and after processing and during validation. The validator rereads the original JSON and performs its own census and field/graph checks; it does not merely trust adapter counts. Missing records, changed text, cycles, or invalid graph references prevent installation. Original strings, Unicode, punctuation, and unknown content remain accessible. Clean JSON does not reproduce original whitespace, key order, or numeric spelling; original source bytes remain available in place.

**Membership and branches.** A reused message ID is not a global identity. Record IDs include provider/source evidence and the JSON pointer, so occurrences remain separate. Only byte-identical source payloads for the same provider are imported once; all file/ZIP locations remain recorded. Parent links, empty graph nodes, and exported branch-selection information survive. Unknown selection stays unknown.

**Attachments.** An exact relative filename may identify a local candidate, but that alone does not prove the file is the original attachment. Missing, ambiguous, unsafe, and unverified references remain visible. The importer does not fetch attachments over the network.

**Reproducibility.** The same bytes, locations/configuration, attachment state, and importer version produce identical normalized outputs without generated wall-clock timestamps. Moving sources changes manifest paths but not source-based record identities. Changing any byte of a source payload produces new evidence identities for that payload. Those are versioned evidence IDs, not lifetime message IDs.

Warnings permit an import but still need interpretation; errors stop it. Validation establishes structural fidelity, not the truth of personal accounts or completeness of provider history.

## Continue to extraction or review

For original-message review, follow [reconciliation](reconciliation.md) to select verified project membership, prepare a frozen inventory, and render packets. The master workflow requires the existing Markdown schema and specific canonical filenames; start with its synthetic exercise rather than pointing it at an arbitrary document.

For model-generated candidates, follow [bounded Codex extraction](autonomy.md) after preparing a review inventory. The live worker needs local Codex setup and explicit permission to transfer packet text. It is not a browser download workflow, and candidate generation does not automatically update the master.

A new export needs a new normalized dataset. Automatic matching of unchanged messages across export versions is **not implemented yet**; do not describe same-run resumption as cross-export deduplication.

## Privacy and access

Keep real exports, local configuration, datasets, review decisions, prompts, candidates, provider logs, and personal masters out of Git. `data/`, `work/`, and local configurations are ignored, but arbitrary directories are not automatically protected. Ignore rules are not encryption or access control. Inspect staged files and the commits being published.

Importing and the offline demo make no model calls. Live extraction sends packet text to the configured provider and may consume paid or subscription usage. Read-only execution settings are not a guarantee of complete read isolation; see the [runbook](autonomy.md#codex-adapter-and-trust-boundary).

Repository visibility and collaborator access are controlled separately from this documentation. A restricted repository requires an authorized account to clone; no access or visibility change is implied by these instructions.
