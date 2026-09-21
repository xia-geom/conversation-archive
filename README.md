# Conversation Archive

**Turn scattered AI conversations into a traceable knowledge archive.**

Experimental alpha · [MIT license](LICENSE) · [Security](SECURITY.md) · [Data flow](PRIVACY.md)

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

## Explore the knowledge map

[Open a local SQLite + Cytoscape map](docs/knowledge-map.md): search entries, focus on nearby connections, and inspect exact evidence. Read-only, no model calls, and no hosted service. The pinned viewer library needs a one-time explicit download; browsing then works offline.

## What works, and what comes next

**In this repository:** export preservation and validation; optional bounded Codex candidate extraction; separate checked reconciliation; a read-only SQLite/Cytoscape knowledge map; relationship rules and batches of 15 contextual questions (10 or 20 configurable). Semantic relationship candidates still need an agent or operator. Exact quotations establish provenance, not correct interpretation.

**Not shipped in this alpha:** automatic semantic discovery and LLM-generated views. The local structured-authority migration is implemented, but its full [acceptance gates](docs/migration-acceptance.md) remain under review. The target remains structured records → rebuildable SQLite retrieval → optional readable views. [Capability map](project.json) · [Migration gates](docs/migration-acceptance.md).

## Choose a task

[Import exports](docs/importing.md) · [Store and compare later exports](docs/raw-store.md) · [Run Codex extraction](docs/autonomy.md) · [Connect entries and answer batches](docs/question-batches.md) · [Develop or migrate](AGENTS.md) · [Watch the English introduction](https://github.com/xia-geom/math_video_project/releases/download/conversation-archive-intro-v1/conversation_archive_intro_en_silent_preview.mp4)

[Machine archive](docs/machine-archive.md) · [SQLite migration](docs/structured-archive.md) · [All guides](docs/README.md) · [Troubleshooting](docs/troubleshooting.md) · [Contributing](CONTRIBUTING.md)

## Verify and keep private data local

```sh
python3 -m unittest discover -s tests -v
```

Commit code, documentation, and invented examples only. Real exports, snapshots, databases, questions, answers, prompts, logs, and generated views stay local in ignored directories. Live model calls require explicit permission to transfer data. Do not rewrite the master or publish media as a side effect of setup.

## Feedback

Try the existing demo and report confusing steps with invented examples. A star is appreciated when the project is useful. [Alpha scope and invitation](docs/public-alpha.md) · [Changes](CHANGELOG.md)
