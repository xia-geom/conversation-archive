# Conversation Archive

**Turn ChatGPT and Claude exports into structured records you can trace back to the original messages.**

Preserve conversations, branches, and attachment references. Optionally use Codex to propose evidence-backed findings, then review them before changing a living record.

[Get started](docs/getting-started.md) · [Use your own exports](docs/importing.md) · [How it works](docs/concepts.md) · [Documentation](docs/README.md) · [Contribute](CONTRIBUTING.md)

## Try it first

You need **Python 3.11 or newer**, Git, and macOS or Linux for this demo. No package installation, Codex account, API key, or paid model call is needed. If repository access is restricted, authenticate with an account that has access before cloning.

```sh
git clone https://github.com/xia-geom/conversation-archive.git
cd conversation-archive
python3 --version
```

Run from the repository root, using a new output directory:

<!-- smoke:quickstart:start -->
```sh
python3 -m conversation_archive.demo --output data/first-run
python3 -m conversation_archive.autonomy status --state data/first-run/extraction
```
<!-- smoke:quickstart:end -->

The first command creates an invented archive, extracts candidates, resumes unfinished work, and checks that a repeat run does not duplicate calls. Selected fields from its output:

<!-- smoke:expected:start -->
```json
{
  "selected_conversations": 2,
  "packets": 9,
  "replay_extra_calls": 0,
  "fabricated_quote_rejected": true,
  "canonical_files_unchanged": true
}
```
<!-- smoke:expected:end -->

**This demo uses a deterministic test worker, not an AI model.** Its output demonstrates the pipeline's behavior, not extraction accuracy. Generated files stay under `data/first-run/`. To repeat the demo, choose a fresh path such as `data/second-run`; do not overwrite an earlier run.

[Open your first result and follow its evidence →](docs/getting-started.md)

## What does the project actually do?

| Stage | What you get | Status |
| --- | --- | --- |
| Import exports | Readable JSONL records with original text, identities, branches, and source locations | Implemented; no model required |
| Extract candidates | Attributed proposals with exact quotations and resumable attempt records | Implemented; live Codex adapter needs local setup and calibration |
| Review and integrate | Explicit decisions, checked master changes, and an installation journal | Implemented as a separate review workflow, not automatic candidate promotion |
| Process only changes in a new export | Cross-export matching and incremental extraction | Planned; same-run resumption already works |

The current master writer expects the project's specific Markdown schema and three canonical filenames. It is not a general-purpose editor for arbitrary Markdown. See [review and integration](docs/reconciliation.md).

## Why not just ask for a summary?

A summary alone does not tell you whether a statement was a user's account, an unsent draft, a dream, or an assistant's suggestion. It also does not tell you which messages were omitted or what to do after an interrupted run.

This project keeps those questions inspectable:

```text
Read-only exports → validated records → bounded evidence packets
                                             ↓
                                  optional Codex extraction
                                             ↓
                                  unreviewed candidates
                                             ↓
                             separate review → checked master update
```

Generated, reviewed, and integrated are different states. Matching a quotation proves where the words came from; it does not prove that the model interpreted them correctly. [Read the outcome rules](docs/concepts.md#how-a-finding-becomes-an-outcome).

## Choose your next step

| Your goal | Start here |
| --- | --- |
| Run and inspect a small example | [Hands-on quickstart](docs/getting-started.md) |
| Import your ChatGPT or Claude export locally | [Import guide](docs/importing.md) |
| Configure optional live Codex extraction | [Autonomy runbook](docs/autonomy.md) |
| Understand the design or present the project | [Concepts](docs/concepts.md) and [interview demo](docs/interview-demo.md) |
| Fix a problem or contribute a change | [Troubleshooting](docs/troubleshooting.md) and [contributing](CONTRIBUTING.md) |

## Development and privacy

```sh
python3 -m unittest discover -s tests -v
```

CI runs the tests and offline demo. Tests also execute the post-clone quickstart commands and check local documentation links. [View workflow runs](https://github.com/xia-geom/conversation-archive/actions/workflows/tests.yml).

Only code, documentation, and invented examples belong in this repository. Real exports, prompts, generated candidates, logs, and personal masters stay local. Live extraction sends packet text to the configured provider and requires explicit opt-in; importing and the offline demo do not. See the [privacy and access notes](docs/importing.md#privacy-and-access) and [known limitations](docs/concepts.md#current-boundaries).
