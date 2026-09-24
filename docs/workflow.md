# From exports to organized Markdown

[Architecture](../ARCHITECTURE.md) · [Formats](formats.md) · [Troubleshooting](troubleshooting.md)

The user-facing product is one Markdown file. An authorized agent normally handles the commands below. They are explicit internal steps so that extraction, review and installation cannot be confused with one another. No SQL, embedding service, graph server or HTML framework is required.

## 1. Preserve inputs and import

Original exports can remain in their existing folder. Use `examples/exports.example.toml` as a template. Paths are resolved relative to that configuration file. Implemented adapters are ChatGPT and Claude; unsupported formats, including Gemini, need a real adapter rather than relabeling data.

```sh
python3 -m conversation_archive normalize --config /path/to/inputs.toml --output /path/to/collection/.state/dataset-01
python3 -m conversation_archive validate --dataset /path/to/collection/.state/dataset-01
```

An existing dataset is not overwritten. Import preserves exported branches, roles, exact text, and attachment availability. It produces locators for later evidence checks, not organized conclusions. Missing files, unreadable media and unknown source fields stay explicit.

For a new document only:

```sh
python3 -m conversation_archive organize init --document /path/to/collection/organized.md
```

Do not run initialization on an existing document or replace it with a fresh template.

## 2. Select and read

```sh
python3 -m conversation_archive organize prepare --dataset /path/to/collection/.state/dataset-01 --document /path/to/collection/organized.md --run /path/to/collection/.state/review-01 --provider chatgpt --project-id EXPORTED_PROJECT_ID
python3 -m conversation_archive organize packet --run /path/to/collection/.state/review-01
```

`organize packet` defaults to readable Markdown with exact source text and context. Add `--format json` for programmatic use. `--packet-id` reads a particular packet, including already covered evidence. Optional `--output` writes a fresh temporary packet. Rendering does not record review.

Use `--membership /path/to/selection.json` instead of `--project-id` for explicitly supplied conversation IDs, including Claude. Membership contains `conversation_ids`, `observed_at`, `evidence`, and `project_name`. Do not guess live app membership. Missing requested conversations are reported separately.

Read the current `organized.md` and relevant complete source context. Select useful facts, decisions, ongoing projects, preferences and qualified reports according to the user's scope. Keep assistant suggestions and plans distinct from completed events. Do not force unrelated health/Emotion material into a common collection.

## 3. Optional bounded model extraction

An authorized agent can review packets directly. The optional controller creates proposals with exact witnesses and cumulative usage receipts:

```sh
python3 -m conversation_archive.autonomy plan --run /path/to/collection/.state/review-01 --output /path/to/collection/.state/extraction-01 --model YOUR_SUPPORTED_MODEL --effort medium
python3 -m conversation_archive.autonomy run --state /path/to/collection/.state/extraction-01 --allow-model-transfer --max-calls 20 --max-tokens 200000 --timeout 180
python3 -m conversation_archive.autonomy status --state /path/to/collection/.state/extraction-01
```

Planning/status make no model call. Running transmits packet text to the configured provider. `--allow-model-transfer` requires actual permission; it is not granted by this guide. The controller validates exact spans and basic attribution but cannot prove a paraphrase or interpretation correct. Candidates are not automatically installed.

Resume the same extraction directory; do not make a new one to hide spending. Budgets are cumulative within that state, checked between calls, and can overshoot on the final call. They are not a dollar cap or global subscription counter. Unknown telemetry or interrupted attempts require audit. Read-only settings do not constitute hermetic isolation; inspect local configuration and authorized data scope.

## 4. Review and compose the document

Compare proposed information with existing entries: already represented, complementary, distinct, uncertain, or excluded. Record an explicit decision with covered piece IDs, findings, attribution, and exact quotations:

```sh
python3 -m conversation_archive organize record --run /path/to/collection/.state/review-01 --document /path/to/reviewed-findings.json
```

The [format guide](formats.md) describes the contract. A draft or extraction candidate must not be passed off as an owner decision. The reviewer may be an explicitly authorized agent; this is not an automatic claim that the human reviewed every source.

Put the important content in ordinary Markdown sections, with stable entry IDs, qualifications, source references and short exact evidence. Preserve manual edits. Ask the owner only about ambiguities that materially affect the account. Open contradictions remain visible rather than being forced into one answer. No blanket classification of all mentions is required.

## 5. Preview and apply a single-document update

Prepare an edits JSON containing the current `document_sha256`, `batch_id`, reviewed `decision_ids`, every finding's disposition, and exact unique `before`/`after` patches. The helper calculates the new hash and runs existing evidence/preservation checks:

```sh
python3 -m conversation_archive organize draft --run /path/to/collection/.state/review-01 --edits /path/to/edits.json --output /path/to/collection/.state/update-01.json
python3 -m conversation_archive organize check --run /path/to/collection/.state/review-01 --batch /path/to/collection/.state/update-01.json --format markdown
python3 -m conversation_archive organize apply --run /path/to/collection/.state/review-01 --batch /path/to/collection/.state/update-01.json --confirm-user-answer
python3 -m conversation_archive organize status --run /path/to/collection/.state/review-01
```

The Markdown preview is an ordinary diff, not a new UI. Applying requires actual approval within the user's authorization. The existing internal journal records approved changes and before/after patches; two additional public-facing correction reports are unnecessary.

`check` with default JSON is suitable for automated validation and exit status. Stale edits are refused. Repeating the same installed batch returns `already_applied`; it does not overwrite later manual changes. Incomplete installation stays recoverable. A lock coordinates this writer across review runs for the same output document.

Status distinguishes pending, partial, reviewed, integrated and unresolved findings. Completion covers only the frozen selection and declared text accounting—not uninspected media or live app completeness.

## 6. Later exports and ChatGPT

Keep new exports separate from old ones. Import a changed export into a fresh dataset/run, preserve the existing Markdown, and compare before adding information. Reuse completed work and recorded decisions; when a raw source has changed, old coverage alone does not prove the new text reviewed. Do not claim automatic cross-export semantic deduplication.

Only the selected Markdown needs to be furnished to ChatGPT. Its headings, self-contained entries, qualifications and source locators must be useful without internal JSON files. Actual upload is a separate authorized action; local paths do not make files available inside ChatGPT. Test representative synthetic questions through the real reader before adding another index or representation.

Optional exact raw-store utilities are retained for existing backups and later-export comparison, but are not part of this required workflow. See [compatibility](compatibility.md) before changing an existing store or snapshot.
