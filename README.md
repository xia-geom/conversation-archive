# Conversation Archive

**Turn conversation exports into traceable records and connected knowledge.**

Preserve the evidence, propose connections, clarify uncertainty in batches, and keep corrections reusable. Related entries stay separate.

## If you are an AI agent or language model

Read [AGENTS.md](AGENTS.md), then [project.json](project.json). Select only the guide for your task; do not load the entire documentation tree or personal archive. Verify your checkout before claiming that a capability exists.

## Try it

Python 3.11+, Git, macOS or Linux. After obtaining repository access:

```sh
git clone https://github.com/xia-geom/conversation-archive.git
cd conversation-archive
```

<!-- smoke:quickstart:start -->
```sh
python3 -m conversation_archive.demo --output data/first-run
python3 -m conversation_archive.autonomy status --state data/first-run/extraction
```
<!-- smoke:quickstart:end -->

Selected output:

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

This is an **offline synthetic demo**, not a model-quality benchmark. No installation, account, API key, or paid model call is needed after cloning. Use a fresh output directory on another run. [Inspect the result](docs/getting-started.md).

## What works, and what comes next

**In this repository:** export preservation and validation; optional bounded Codex candidate extraction; separate checked reconciliation; relationship rules and batches of 15 contextual questions (10 or 20 configurable). Semantic relationship candidates still need an agent or operator. Exact quotations establish provenance, not correct interpretation.

**Target architecture:** authoritative structured records and correction history → rebuildable SQLite retrieval → human-readable views on demand. Markdown becomes an optional export. The owner reports a local migration demonstration; its implementation is not present in the inspected GitHub baseline. Do not confuse that report with a shipped feature. [Migration status and acceptance checks](docs/migration-acceptance.md).

## Choose a task

[Import exports](docs/importing.md) · [Run Codex extraction](docs/autonomy.md) · [Connect entries and answer batches](docs/question-batches.md) · [Develop or migrate](AGENTS.md) · [English companion video](https://github.com/xia-geom/math_video_project/tree/main/miscellaneous/conversation_archive_intro_en)

[All guides](docs/README.md) · [Troubleshooting](docs/troubleshooting.md) · [Contributing](CONTRIBUTING.md)

## Verify and keep private data local

```sh
python3 -m unittest discover -s tests -v
```

Commit code, documentation, and invented examples only. Real exports, snapshots, databases, questions, answers, prompts, logs, and generated views stay local in ignored directories. Live model calls require explicit permission to transfer data. Do not rewrite the master or publish media as a side effect of setup.
