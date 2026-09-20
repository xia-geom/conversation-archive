# Bounded Codex extraction

## What is implemented

This is an optional **candidate-extraction controller**, not an autonomous personal-master editor. The existing importer and reconciliation commands keep their behavior. The new commands consume a frozen review inventory, call a worker on pending evidence, check its output, and save attributed candidates with exact source witnesses. They do not call `reconcile record` or `reconcile apply`.

```text
read-only exports -> validated JSONL -> frozen review inventory -> exact packets
                                                                  |
                                     bounded controller -> Codex worker
                                                                  |
                                   JSON schema + exact evidence validation
                                                                  |
                                   unreviewed candidate files + receipts
                                                                  |
                    separate reconciliation review -> staged master changes
                                                                  |
                            existing check / journaled apply / reports
```

The first five steps through candidate files are runnable without live browser prompting. The last two remain an explicit review/integration workflow. No database, embedding service, browser robot, background daemon, or multi-agent framework is required.

## Four records with different authority

| Record | What it establishes | What it does not establish |
| --- | --- | --- |
| Original message and source hash | A particular export contained particular bytes/text | That the account is objectively true |
| Historical downloaded summary | An earlier extraction product exists | Complete original-message review |
| New extraction candidate | A schema-valid proposal cites exact available text | Correct interpretation, novelty, or master integration |
| Review decision plus completed installation journal | Documented review and installed dispositions in the frozen scope | Missing-media inspection or complete account history |

Do not add the counts of these records together as if they were disjoint conversations. Old summaries stay useful as an index and supporting history; they must not silently become raw-review decisions. A completed frozen review produces an empty pending extraction queue, not another pass through all conversations.

## Local commands

Python 3.11+; controller locking and process cleanup require macOS or Linux. Start with the offline invented-data demonstration:

```sh
python3 -m unittest discover -s tests -v
python3 -m conversation_archive.demo --output data/autonomy-demo
```

For real work, first use the existing importer and `reconcile prepare` procedure in [reconciliation.md](reconciliation.md). Keep all paths below local and ignored. Use an actual model identifier supported by your installed Codex; the example intentionally does not prescribe a model or price.

```sh
python3 -m conversation_archive.autonomy plan \
  --run /path/to/private/review-run \
  --output /path/to/private/extraction-run \
  --model YOUR_SUPPORTED_MODEL --effort medium

python3 -m conversation_archive.autonomy run \
  --state /path/to/private/extraction-run \
  --allow-model-transfer \
  --max-calls 20 --max-tokens 200000 --timeout 180

python3 -m conversation_archive.autonomy status \
  --state /path/to/private/extraction-run
```

Planning and status do not invoke a model. Running requires explicit permission to send packet text to the configured Codex provider. A new state directory must be empty. Reuse that same state directory to resume; do not create fresh directories to hide earlier spending. Budgets apply cumulatively to that state, not globally to every Codex session on the machine.

`--max-calls` limits started attempts, including failures. Increasing it explicitly permits more attempts. `--max-tokens` uses observed input plus output tokens; cached input is a subset, not an extra count. It is checked **between calls**, so the last call may overshoot. Missing or incomplete telemetry stops further calls. This is not a dollar cap, subscription-credit counter, or provider-enforced output-token limit. Raw provider events remain available locally for a later billing audit.

`--max-prompt-chars` refuses an oversized prompt rather than truncating source text. A character limit is not a token estimate. Packet count, conversation count, and model call count are distinct: a long conversation may need many packets.

## State and recovery

```text
pending -> in_flight -> extracted
                   \-> blocked
```

`extracted` means candidates only, never `reviewed` or `integrated`. The controller owns one state-directory lock and starts one worker at a time. Before a worker starts, it persists the request and increments the attempt counter. Successful candidate and receipt hashes are checked on resume. Model, effort, prompt/schema fingerprint, inventory, and raw-review coverage are frozen; changing them requires an explicit new plan/migration, not a silent continuation.

An interrupted attempt is not automatically retried. First stop/confirm termination of the old process; then:

```sh
python3 -m conversation_archive.autonomy recover \
  --state /path/to/private/extraction-run --confirm-worker-stopped
```

A saved completed receipt can be validated without another model call. An attempt without a receipt becomes blocked with unknown usage. Invalid proposals, forbidden tool activity, and unknown usage require operator audit. This release has no automatic retry or reset command. Preserve the failed attempt and its costs when designing a remedial run. Hashes detect accidental drift, not tampering by someone who can rewrite both data and hashes.

State files include `plan.json`, `state.json`, `jobs/<packet>/candidate.json`, and per-attempt request, response, runtime, and receipt files. Live attempts additionally retain prompt, provider event stream, and stderr. These can contain sensitive text: keep the entire directory private and outside published examples. Newly created controller roots request owner-only directory permissions; inherited filesystem permissions still need inspection.

## Prompt and validation contract

`extraction.py` owns a versioned prompt and a closed JSON schema. Each pending piece needs one disposition: candidate, context only, no extractable content, or needs context. A candidate contains a local ID, category, attributed statement, uncertainty, and exact evidence spans. It cannot allocate permanent master IDs.

Evidence offsets are Python Unicode character offsets **within a cited piece**. The controller preserves the original piece offset and source locator, allowing translation back to the original segment. It rejects nonexistent quotes, mismatched spans, missing/duplicate coverage, incorrect links, and basic speaker-role violations. Assistant text cannot be relabeled as an owner statement. Structured placeholders cannot become textual evidence.

These checks do not prove that a paraphrase follows from its quotation, that a first-person passage was authored by the owner, that two events are identical, or that no important fact was omitted. Those are semantic evaluation and reconciliation problems. The `needs_context` outcome is preferable to confident guessing when a packet contains only part of a conversation. Previously reviewed pieces can provide context but are not counted again.

## Codex adapter and trust boundary

`codex_worker.py` uses non-interactive `codex exec` with a JSON output schema, JSONL events, an ephemeral session, read-only sandbox, explicit model/effort, disabled shell/search options, and an empty temporary working directory. It does not reuse a browser conversation or ask ChatGPT to download a summary. The request omits local path metadata and the master; source text itself may still mention private details.

The installed CLI is preflighted for required flags and its version is recorded. Unsupported installations fail rather than falling back to broader permissions. No real-model compatibility or quality result is implied by mocked adapter tests.

Read-only is **not read isolation**. User-config suppression and disabled tools reduce exposure but do not prove hermetic isolation from managed configuration or host integrations. Before sensitive live use, inspect configuration and use a separately isolated account/container/VM with only necessary data. Do not describe prompt-injection resistance as solved. Tool-event rejection occurs after observation; it is not a substitute for runtime isolation. Event/response size checks occur after execution; the process timeout, not those checks, bounds runtime.

Official interface references (consulted 2026-09-20):
- [Non-interactive mode](https://developers.openai.com/codex/noninteractive/)
- [CLI reference](https://developers.openai.com/codex/cli/reference/)
- [Configuration reference](https://developers.openai.com/codex/config-reference/)

## Compatibility and next boundary

The autonomy/extraction formats are independently versioned at 1.0; normalized schema and reconciliation format are unchanged. Commands are separate modules, preserving existing CLI interfaces. The controller lock does **not** lock the legacy master writer. Unattended master promotion, cross-export incremental identity, calibrated semantic evaluation, and operator-approved retries are future work; see the [audit](audit-2026-09-20.md) and [interview demonstration](interview-demo.md).
