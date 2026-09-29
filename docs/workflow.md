# From exports to organized Markdown

[Architecture](../ARCHITECTURE.md) · [Formats](formats.md) · [Troubleshooting](troubleshooting.md)

The product is one useful Markdown file. An authorized agent normally handles these stages. Import, extraction, review, installation and publication are different completion claims. No SQL, vector index, graph server or HTML framework is required.

## 1. Preserve inputs and import

Original exports may remain where they are. Use `examples/exports.example.toml`; paths are relative to the configuration file. Implemented adapters are ChatGPT and Claude. Unsupported formats need a real adapter rather than relabeling data.

```sh
python3 -m conversation_archive normalize --config /path/to/inputs.toml --output /path/to/collection/.state/dataset-01
python3 -m conversation_archive validate --dataset /path/to/collection/.state/dataset-01
```

Datasets are not overwritten. Import preserves branches, roles, exact text, source locators and attachment availability. Unknown metadata and unavailable media remain explicit. For a new document only:

```sh
python3 -m conversation_archive organize init --document /path/to/collection/organized.md
```

Never initialize over an existing document or replace manual edits with a template.

## 2. Select and read

```sh
python3 -m conversation_archive organize prepare --dataset /path/to/collection/.state/dataset-01 --document /path/to/collection/organized.md --run /path/to/collection/.state/review-01 --provider chatgpt --project-id EXPORTED_PROJECT_ID
python3 -m conversation_archive organize packet --run /path/to/collection/.state/review-01
```

Packets default to Markdown. `--format json`, `--packet-id` and a fresh `--output` support selected reading, including covered evidence. Rendering is not reviewing. For supplied conversation IDs, including Claude, use `--membership /path/to/selection.json` instead of `--project-id`. Membership includes `conversation_ids`, `observed_at`, `evidence` and `project_name`; missing conversations remain reported. Do not guess live app membership.

Read current entries and complete relevant sources. Select useful reports, decisions, projects, preferences and qualifications within scope. Separate plans, actions and assistant suggestions. Do not merge unrelated Health and Emotion collections.

## 3. Optional bounded model extraction

The current authorized agent may review packets directly. The optional controller produces candidates with exact witnesses and usage records:

```sh
python3 -m conversation_archive.autonomy plan --run /path/to/collection/.state/review-01 --output /path/to/collection/.state/extraction-01 --model YOUR_SUPPORTED_MODEL --effort medium
python3 -m conversation_archive.autonomy run --state /path/to/collection/.state/extraction-01 --allow-model-transfer --max-calls 20 --max-tokens 200000 --timeout 180
python3 -m conversation_archive.autonomy status --state /path/to/collection/.state/extraction-01
```

Planning/status make no model call. Running transfers packet text; the flag requires real authorization. Candidates are not automatically installed. Resume the same directory. Budgets are cumulative within it, checked between calls, and can overshoot on the final call; they are not a dollar cap. Unknown telemetry or interrupted paid attempts require audit, not blind retry. Read-only settings are not hermetic isolation.

## 4. Review and compose

Compare proposed information with existing entries: represented, complementary, distinct, uncertain or excluded. Reassess the whole affected entry: placement, limitations, contradictions and attribution. Do not append new evidence while leaving an incompatible earlier conclusion active.

```sh
python3 -m conversation_archive organize record --run /path/to/collection/.state/review-01 --document /path/to/reviewed-findings.json
```

The [format guide](formats.md) specifies covered pieces, findings and quotations. Authorized agent review is not owner confirmation. Ask the owner only about consequential ambiguity the sources cannot settle. Preserve unresolved disagreements rather than inventing dates, motives or identities.

## 5. Ordinary checked updates

An edits JSON names `document_sha256`, `batch_id`, reviewed `decision_ids`, dispositions and exact unique `before`/`after` patches.

```sh
python3 -m conversation_archive organize draft --run /path/to/collection/.state/review-01 --edits /path/to/edits.json --output /path/to/collection/.state/update-01.json
python3 -m conversation_archive organize check --run /path/to/collection/.state/review-01 --batch /path/to/collection/.state/update-01.json --format markdown
python3 -m conversation_archive organize apply --run /path/to/collection/.state/review-01 --batch /path/to/collection/.state/update-01.json --confirm-user-answer
python3 -m conversation_archive organize status --run /path/to/collection/.state/review-01
```

Apply only within actual user authorization. The journal preserves approved changes; new collections need no separate correction reports. Stale edits are refused, exact replay returns `already_applied`, and incomplete installation is recoverable. Cooperating writers share a document lock, not a distributed transaction with arbitrary external editors. Status covers the frozen selection and declared text accounting, not uninspected media or live app completeness.

## 6. Autonomous entry audit and reading publication

Use the [organize-markdown skill](../.agents/skills/organize-markdown/SKILL.md) for delegated quality review. The current Codex session performs editorial reasoning. The commands supply bounded tasks, checked submission and local publication; they do not launch another model.

### Prepare the scope once

```sh
python3 -m conversation_archive reading prepare \
  --input /path/to/collection/organized.md \
  --reference /path/to/preserved-bundle.md \
  --run /path/to/collection/.state/reading-01 \
  --autonomous \
  --scope-note 'Review these supplied records, preserve evidence and scoped decisions.' \
  --publish-to /path/to/collection/organized-reviewed.md
```

`--reference` is optional and must name a compatible evidence/decision file. The maintained document remains the prose baseline. The reference supplies missing sources and compatible prior decisions; conflicting same-ID evidence or different nonempty decision contexts stop the run. Shared entry IDs alone are insufficient. This does not discover the latest records outside the selected files.

Omit `--publish-to` unless the owner authorizes that fresh destination. It cannot name an existing file, either input, or run bookkeeping. It is not permission to upload, overwrite, or change the maintained-document pointer. `--reviewer` defaults to Codex; the role is fixed to authorized_agent.

The run contains a frozen audit, template, and one working `answers.json`. Resume that run. `--max-submissions` bounds accepted changes (default 200), not rejected attempts, tokens or spending. Keep existing external-model budgets and stop repeated no-progress/failure.

Known report findings can be supplied with `--findings /path/to/findings.json`:

```json
{
  "input_sha256": "EXACT_HASH_OF_SELECTED_INPUT",
  "findings": [
    {"entry_id": "E1001", "quote": "An exact passage in that entry.", "reason": "Why this specific passage needs review."}
  ]
}
```

Replace placeholders with real local IDs, text and hashes; keep private findings outside Git. This supplements lexical flags rather than claiming exhaustive discovery. The audit also tracks source associations missing relative to the selected reference and entries with no included SRC evidence.

### Next task, read, submit

```sh
python3 -m conversation_archive reading next --run /path/to/collection/.state/reading-01 --output /path/to/task-01.md
python3 -m conversation_archive reading source --run /path/to/collection/.state/reading-01 --source-id src-202 --start 0 --length 20000 --output /path/to/source-range.md
python3 -m conversation_archive reading submit --run /path/to/collection/.state/reading-01 --submission /path/to/submission-01.json
```

`next` selects five entries by default (`--size` allows 1–10) and can add candidate move destinations up to 20 total. The packet includes complete entry text, explicit source omissions, known findings, prior scoped reviews, a checkpoint hash and an empty submission envelope. Source omissions are not claims of inspection. Use `@master` for non-entry context and `@decisions` for exact recovered decisions. Offsets count Unicode characters, not bytes.

A submission names `run_id`, `base_answers_sha256`, and arrays `reviews`, `issue_resolutions`, `source_changes`, `excerpts`. Each array is bounded at 100 items. Only supplied IDs are replaced; unanswered work survives. Optional `selection_note` refines the publication scope. Optional `discard` removes explicitly named draft items, not evidence or source files. Concurrent stale submissions are rejected; replay returns `already_recorded`; an empty unchanged submission returns `no_progress`.

Each review contains `entry_id`, packet `basis`, `decision` (keep/revise/defer), `reason`, separate `checks` for placement/limitations/contradictions/attribution, and `witnesses`. Only a revision has `replacement`: one complete entry with the same ID. A witness names `source_id`, `source_sha256`, Unicode `start`/`end`, exact `quote`, literal local `claim`, and relation supports/qualifies/removes. Code checks quotation and local association, not semantic entailment.

Each known issue separately needs `issue_id`, `status`, `reason`, and exact source `witnesses` without claim/relation. Resolved passages must actually change; false_positive preserves the disputed passage with relevant counterevidence and explanation; defer prevents autonomous completion. Generic keeps cannot clear issues. Cosmetic rewriting is not a semantic repair. Only noncritical evidence-access gaps can be accepted_limit, visibly distinct from resolved.

Each removed source needs `entry_id`, `source_id`, action move/exclude, `target_entry_id`, and reason. A move needs its destination reviewed and the source locally witnessed there. Exclusion uses a null destination and explains why evidence should not support that entry. The same rule covers inherited losses; do not restore erroneous old links wholesale. A deferred inherited loss stays unresolved.

Select useful short `excerpts` with source_id/source_sha256/start/end/quote when length-based selection omits necessary evidence. Original compact answers supporting retained corrections are included through bounded correction references, including identifiers inside historical quoted text. Missing critical support blocks completion; a larger original may need an exact excerpt. Do not recursively import every old transcript.

### Check and finish

Repeat only while work_pending. For needs_evidence, retrieve the reported source IDs or select appropriate excerpts. For needs_owner, ask only the unresolved consequential questions. Missing publication authorization is a separate stop, not a reason to redo review.

```sh
python3 -m conversation_archive reading check --run /path/to/collection/.state/reading-01 --answers /path/to/collection/.state/reading-01/answers.json --output /path/to/preview-01
python3 -m conversation_archive reading finish --run /path/to/collection/.state/reading-01
```

Inspect the exact proposed Markdown and entry diff before finish. It recomputes a hash-bound preview, then publishes only to the preauthorized fresh destination. Without one it returns awaiting_publication_authorization and the preview path. No pending/deferred findings or missing critical evidence may pass autonomous finish. Noncritical accepted access limits remain counted separately. Inputs, manual output edits and all source bytes stay unchanged; exact replay is idempotent.

Publication creates one current index and body-derived source lists. Full machine tables, old reports and binary payloads stay outside reading output. Existing included sources remain available on a no-edit repeat without nesting their generated wrappers. Excerpts never become complete originals. Critical dependencies are separately navigable without modifying literal quotations.

### Manual and older workflows

The lower-level prepare/packet/source/check/publish/status workflow remains available without `--autonomous`; it does not enforce every new per-finding rule. Do not switch to it merely to evade an autonomous failure. Explicit manual publication uses `reading publish --run RUN --answers ANSWERS --preview PREVIEW_DIR --output FRESH_FILE --approve-publication` under actual authorization.

Use `reading prepare --reuse PREVIOUS_PREVIEW_JSON` only for checked 1.1 receipts and unchanged context. It retains reviewer attribution and selected evidence when the strict scope still matches. Prepare fresh 1.1 work for 1.0 receipts. Complete 1.0 source wrappers remain readable after exact hash verification; unverifiable legacy excerpts require original recovery. Unknown active legacy correction operations still stop conversion. This is not a full snapshot migration engine.

## 7. Later exports and the actual reader

Import changes into fresh datasets/runs and compare with the current maintained document. Previous coverage is not review of changed text. Only the selected Markdown needs to be furnished to ChatGPT; a source ID or local path is not access to original bytes. Test real retrieval before adding infrastructure. Local structural tests do not measure native search ranking or factual accuracy.

All private sources, checkpoints, prompts and answers remain outside Git. Reading commands make no model calls; a cloud agent reading local packets is still a separately authorized transfer. Keep originals and previous corrections. CI uses invented fixtures and the existing demos only.
