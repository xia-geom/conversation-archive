# From exports to organized Markdown

[Architecture](../ARCHITECTURE.md) · [Formats](formats.md) · [Troubleshooting](troubleshooting.md)

The product is one useful Markdown file. An authorized agent normally handles these stages. Import, extraction, review, installation and publication are not interchangeable claims of completion. No SQL, embedding service, graph server or HTML framework is required.

## 1. Preserve inputs and import

Original exports may remain where they are. Use `examples/exports.example.toml`; paths are relative to the configuration file. Implemented adapters are ChatGPT and Claude. Unsupported formats, including Gemini, need a real adapter rather than relabeling data.

```sh
python3 -m conversation_archive normalize --config /path/to/inputs.toml --output /path/to/collection/.state/dataset-01
python3 -m conversation_archive validate --dataset /path/to/collection/.state/dataset-01
```

Datasets are not overwritten. Import preserves branches, roles, exact text, source locators and attachment availability, not organized conclusions. Unknown metadata and unavailable media remain explicit.

For a new document only:

```sh
python3 -m conversation_archive organize init --document /path/to/collection/organized.md
```

Never initialize over an existing document or replace manual edits with a template.

## 2. Select and read

```sh
python3 -m conversation_archive organize prepare --dataset /path/to/collection/.state/dataset-01 --document /path/to/collection/organized.md --run /path/to/collection/.state/review-01 --provider chatgpt --project-id EXPORTED_PROJECT_ID
python3 -m conversation_archive organize packet --run /path/to/collection/.state/review-01
```

Packets default to readable Markdown. `--format json`, `--packet-id` and a fresh `--output` support programmatic or selected reading, including already covered evidence. Rendering is not a review decision.

For supplied conversation IDs, including Claude, use `--membership /path/to/selection.json` instead of `--project-id`. Membership includes `conversation_ids`, `observed_at`, `evidence` and `project_name`. Do not guess live app membership. Missing requested conversations remain reported.

Read the current document and relevant complete source context. Select useful reports, decisions, projects, preferences and qualifications within the user's scope. Separate plans from completed actions and assistant suggestions from user statements. Do not merge unrelated Health and Emotion collections.

## 3. Optional bounded model extraction

An authorized agent can review packets directly. The optional controller produces candidate information with exact witnesses and cumulative usage records:

```sh
python3 -m conversation_archive.autonomy plan --run /path/to/collection/.state/review-01 --output /path/to/collection/.state/extraction-01 --model YOUR_SUPPORTED_MODEL --effort medium
python3 -m conversation_archive.autonomy run --state /path/to/collection/.state/extraction-01 --allow-model-transfer --max-calls 20 --max-tokens 200000 --timeout 180
python3 -m conversation_archive.autonomy status --state /path/to/collection/.state/extraction-01
```

Planning/status make no model call. Running transfers packet text; `--allow-model-transfer` requires real authorization, not permission inferred from this guide. Exact spans and basic attribution can be checked mechanically; paraphrase and interpretation cannot. Candidates are not automatically installed.

Resume the same extraction directory. Budgets are cumulative within it, checked between calls, and can overshoot on the final call. They are not a dollar cap or global subscription counter. Unknown telemetry and interrupted paid attempts require audit, not blind retry. Read-only settings are not hermetic isolation.

## 4. Review and compose

Compare proposed information with existing entries: already represented, complementary, distinct, uncertain or excluded. Read the whole affected entry before incorporating an addition. Reassess placement, prior limitations, contradictions and attribution together; do not leave an old incompatible statement above a new appended correction.

```sh
python3 -m conversation_archive organize record --run /path/to/collection/.state/review-01 --document /path/to/reviewed-findings.json
```

The [format guide](formats.md) describes covered pieces, findings and quotations. An explicitly authorized agent may review; do not present its decisions as human confirmation. Ask the owner only about consequential ambiguity the sources cannot settle. Keep unresolved disagreements visible without inventing dates, motives, identities or outcomes.

## 5. Preview and apply ordinary document updates

An edits JSON names `document_sha256`, `batch_id`, reviewed `decision_ids`, each finding's disposition and exact unique `before`/`after` patches.

```sh
python3 -m conversation_archive organize draft --run /path/to/collection/.state/review-01 --edits /path/to/edits.json --output /path/to/collection/.state/update-01.json
python3 -m conversation_archive organize check --run /path/to/collection/.state/review-01 --batch /path/to/collection/.state/update-01.json --format markdown
python3 -m conversation_archive organize apply --run /path/to/collection/.state/review-01 --batch /path/to/collection/.state/update-01.json --confirm-user-answer
python3 -m conversation_archive organize status --run /path/to/collection/.state/review-01
```

The ordinary diff is not a new UI. Applying needs approval within the user's authorization. The journal preserves approved changes; new collections need no separate correction reports. JSON check output supplies automated status. Stale edits are refused, exact installed replay returns `already_applied`, and incomplete installation is recoverable. Cooperating writers share a document lock; arbitrary external editors are not a distributed transaction.

Status distinguishes pending, partial, reviewed, integrated and unresolved work. It covers the frozen selection and declared text accounting, not uninspected media or live app completeness. These legacy structural checks are not an automatic semantic quality audit; use the next stage for a clean reading publication.

## 6. Entry audit, reconciliation and clean reading publication

Use this for an existing organized document or a recognized preservation bundle. It solves a different problem from initial extraction: text can be copied accurately yet attached to the wrong entry, and valid additions can leave old limitations or indexes stale. The optional [organize-markdown skill](../.agents/skills/organize-markdown/SKILL.md) supplies the editorial workflow.

### Audit and inspect

```sh
python3 -m conversation_archive reading prepare --input /path/to/collection/organized.md --run /path/to/collection/.state/reading-01
python3 -m conversation_archive reading packet --run /path/to/collection/.state/reading-01 --entries E1001 E1002 --output /path/to/collection/.state/packet.md
```

Replace example IDs with IDs from the audit. The run contains `audit.json`, `audit.md` and `answers.template.json`. It binds the original input hash. It reports stale index titles, body citations missing from headers, unavailable targets, possible stale limitations and suspicious additions. The placement heuristic uses title-word overlap only; it never automatically moves or merges events and it is not exhaustive contradiction detection.

Packets include full entry text. Source limits are explicit. When a source does not fit the packet, read its exact character ranges:

```sh
python3 -m conversation_archive reading source --run /path/to/collection/.state/reading-01 --source-id src-202 --start 0 --length 20000 --output /path/to/collection/.state/source-range.md
```

Use `--source-id @master` to read the non-entry context ranges named by the audit. This reaches overviews, prose corrections and source-only navigation that a naive entry-only export would overlook. Offsets count Unicode characters, not UTF-8 bytes. Missing sources remain missing; no model should fabricate their contents.

### Record an attributed review

Copy the answer template to a private working file. Set `reviewer`, `reviewer_role` (`owner` or `authorized_agent`) and `selection_note`. The last field explains why the selected reading content is adequate after inspecting material outside entries; a reduced file is not a lossless archive replacement.

Each `reviews` item contains:

- `entry_id` and the exact `basis` shown in its packet;
- `decision`: `keep`, `revise` or `defer`, with a substantive `reason`;
- `checks`: separate explanations for `placement`, `limitations`, `contradictions` and `attribution`;
- `witnesses`: exact evidence for revised claims; `replacement` only for a revision.

A witness names `source_id`, `source_sha256`, `start`, `end`, exact `quote`, literal `claim` and `relation` (`supports`, `qualifies`, `removes`). The claim and citation must occur in that reviewed entry; finding a quotation elsewhere in the file is insufficient. Changed entry-source associations require witnesses. A replacement contains one complete entry with the same ID, not an unscoped patch that can spill into neighbors. Moving an addition requires assessment of both entries. Code verifies declared scope and exact text, not whether an explanation entails a conclusion.

Every initial entry needs an explicit disposition, but this is authorized editorial work, not a requirement that the owner answer hundreds of questions. Defer genuinely unresolved cases. Do not fill all entries with boilerplate to claim semantic review. Optional `excerpts` use the same exact source fields without `claim` or `relation` and select evidence that is too long for automatic inclusion.

```sh
python3 -m conversation_archive reading status --run /path/to/collection/.state/reading-01 --answers /path/to/collection/.state/answers.json
python3 -m conversation_archive reading check --run /path/to/collection/.state/reading-01 --answers /path/to/collection/.state/answers.json --output /path/to/collection/.state/preview-01
```

`status` can inspect partial review work. `check` refuses missing dispositions. The preview contains the proposed `organized.md`, an entry-level diff in `preview.md`, and a checked receipt in `preview.json`. Deferred entries remain visibly unresolved, not silently confirmed.

### Inspect and publish

The export regenerates one index and source lists from complete entry bodies. It retains selected exact evidence and supported scoped decisions, not whole before/after reports, machine tables or encoded media. Small available source blocks are included by default (1,600 characters); use `--max-source-chars` or explicit excerpts to adjust. Long or absent targets become explicit external references, not dangling internal links. That is an access limitation, not proof that the source is unnecessary.

For recognized old bundles, all explicitly preserved document hashes are checked. Entry locators and supported active `bind`/`bind_mentions` scopes are validated and retained. Other active operation types block conversion. This is not full legacy snapshot migration or certification of every historical table.

```sh
python3 -m conversation_archive reading publish --run /path/to/collection/.state/reading-01 --answers /path/to/collection/.state/answers.json --preview /path/to/collection/.state/preview-01 --output /path/to/collection/reading-approved.md --approve-publication
```

Inspect the exact preview first. Publication recomputes it, checks source and answer hashes, and creates a fresh local file without overwriting originals or manual edits. Exact replay returns `already_published`. There is no remote upload, automatic authority switch or global CURRENT pointer. Keep one selected maintained document; never edit two competing masters. Existing canonical-source changes still use the ordinary checked writer.

For later quality passes, `reading prepare --reuse /path/to/previous/preview.json` reuses only unchanged reviewed entry/evidence/decision context and retains the recorded reviewer. Changed items need reassessment. Keep originals, receipts and actual review answers outside Git; disposable packets can be regenerated.

## 7. Later exports and actual ChatGPT retrieval

Import changed exports into fresh datasets/runs and compare with the current manually maintained document. Do not equate earlier coverage with review of changed source text or claim automatic cross-export semantic deduplication.

Only the selected Markdown needs to be furnished to ChatGPT. Entries must be intelligible without internal JSON. A source ID or local path does not make the original available in ChatGPT. Test a small representative and adversarial question set through the actual reader before assuming improved recall or adding infrastructure. Local structural checks measure neither native search ranking nor factual accuracy.

Original archives, checkpoints, paid-attempt accounting and previous corrections are not removed by cleanup. See [compatibility](compatibility.md) for older stores. The code makes no model calls during reading audit/publication; letting a cloud agent read local packets is still data transfer and needs authorization. CI uses invented fixtures only.
