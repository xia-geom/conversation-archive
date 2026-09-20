# Get started with an invented archive

[Overview](../README.md) · [Documentation](README.md) · [Troubleshooting](troubleshooting.md)

**Goal:** run the pipeline, inspect what it saved, and see the distinction between an extracted candidate and an accepted master entry. Nothing in this exercise is personal data. The worker echoes source text with conservative attribution; it does not perform semantic AI extraction.

## 1. Get the code and run the demo

Use Python 3.11 or newer and macOS or Linux. The controller uses POSIX file locking; its demo is not a native Windows workflow. The pure importer does not need Codex, and neither does this exercise.

```sh
git clone https://github.com/xia-geom/conversation-archive.git
cd conversation-archive
python3 --version
python3 -m conversation_archive.demo --output data/first-run
```

If you already ran the README commands, keep that output and start at step 2. The demo requires a new or empty output directory. There is no installation step or runtime dependency download.

The demo uses two invented conversations containing Unicode text, alternative assistant branches, a repeated original message ID, an unsent draft, and an unavailable image pointer. It intentionally uses tiny packets to make stopping and resuming visible.

Expected first-command output:

```json
{
  "fixture_only_not_model_accuracy": true,
  "selected_conversations": 2,
  "packets": 9,
  "first_pass_calls": 1,
  "total_fixture_calls": 9,
  "replay_extra_calls": 0,
  "all_candidates_extracted": true,
  "fabricated_quote_rejected": true,
  "raw_reviewed_pieces": 0,
  "canonical_files_unchanged": true
}
```

The same expectation is stored in [examples/demo-report.json](../examples/demo-report.json) and compared with the actual CLI output in tests. The test worker reports zero model usage because no model is called; this is not a forecast of live cost.

## 2. See what was created

```text
data/first-run/
  raw.json                 invented source export
  local.toml               configuration for that export
  dataset/                 validated JSONL records and import manifest
  review/inventory.json    frozen evidence selection and packet boundaries
  extraction/plan.json     frozen extraction configuration and queue
  extraction/state.json    attempt counts, usage, and job states
  extraction/jobs/         candidates plus per-attempt requests and receipts
  archive/                 miniature master and reports; unchanged by extraction
  demo-report.json         result of the demonstration
```

Open the report and current status:

<!-- smoke:inspect:start -->
```sh
python3 -m json.tool data/first-run/demo-report.json
python3 -m conversation_archive.autonomy status --state data/first-run/extraction
```
<!-- smoke:inspect:end -->

`all_candidates_extracted: true` means the candidate queue is finished. It does not mean a person or agent has reconciled the findings with the master. That is why the demo also reports `raw_reviewed_pieces: 0` and `canonical_files_unchanged: true`.

## 3. Follow a candidate to its source

Display the first saved candidate, then render the exact source packet:

<!-- smoke:evidence:start -->
```sh
python3 -m json.tool data/first-run/extraction/jobs/P0001-0001/candidate.json
python3 -m conversation_archive reconcile packet --run data/first-run/review --packet-id P0001-0001 --format markdown
```
<!-- smoke:evidence:end -->

In `proposal.candidates`, find a `statement`, its `attribution`, and its quoted `evidence`. In `source_pieces`, find the corresponding message occurrence, source hash, JSON pointer, and original character range. The packet command displays the actual source text and branch information.

An evidence span uses start-inclusive, end-exclusive Unicode character offsets within the cited piece. A piece can be only part of a long message. The saved original range tells you how to map it back; see the [contract reference](autonomy.md#prompt-and-validation-contract).

The fixture labels user text as `unknown`, rather than pretending to understand whether it is an account or draft. A live worker is expected to propose more useful attribution, but that behavior requires evaluation and review.

## 4. Check repeatability and the next boundary

The demo itself performs a one-call first pass, resumes the remaining work, then replays the completed queue. `replay_extra_calls: 0` is the observed replay result. Running `autonomy status` only reads state; it is not a new extraction call.

Run the test suite:

```sh
python3 -m unittest discover -s tests -v
```

To repeat the whole exercise, choose a fresh directory such as `data/second-run`. Do not use fresh state directories to evade budgets in real work: each real extraction run's attempt history must remain visible.

**Next:** follow [the import guide](importing.md) for your own exports, or [the reconciliation exercise](reconciliation.md#run-a-small-synthetic-review) to learn how an explicit review differs from extraction. The [autonomy runbook](autonomy.md) is the separate, opt-in path for an actual Codex model call.
