# Contributing

[Overview](README.md) · [Documentation](docs/README.md) · [Architecture](docs/concepts.md)

Start by running the [offline quickstart](docs/getting-started.md). You should be able to explain one candidate's source and why the demo leaves the master unchanged before changing extraction or reconciliation behavior.

## Development setup

Use Python 3.11 or newer. The candidate controller requires macOS or Linux. From the repository root, no package installation or third-party test dependency is needed:

```sh
python3 -m unittest discover -s tests -v
python3 -m conversation_archive.demo --output data/contributor-demo
```

Choose a fresh demo directory. For command details, use `python3 -m conversation_archive --help` and `python3 -m conversation_archive.autonomy --help`. Read [AGENTS.md](AGENTS.md) before an agent-assisted change.

## Choose a small change

| Area | Good starting point |
| --- | --- |
| Onboarding | Reproduce a confusing step and improve its example or error explanation |
| Source fidelity | Add an invented fixture for a previously untested content or graph shape |
| Controller reliability | Reproduce a failure with a fake worker and add a regression test |
| Evaluation | Define supported/unsupported interpretations in an invented annotated example |

Check [the audit](docs/audit-2026-09-20.md) before taking on automatic promotion, shared writer locking, or incremental export identity. Those need scoped design work, not an incidental documentation change. Do not claim a roadmap item is implemented without code and tests.

## What a pull request should show

Explain the user-visible problem, the changed behavior, and how you tested it. Preserve existing interfaces and source formats unless the change explicitly documents compatibility. New provider calls need test doubles; ordinary CI must not require credentials or spend model usage.

For data/model changes, include a minimal invented input, expected behavior, and a failing regression test that the change fixes. Test more than the happy path: omissions, branches, exact quotations, interruptions, stale hashes, or replay may be relevant. An AI-generated implementation still needs review and evidence; explain which parts you inspected and tested.

Before submitting, inspect `git diff --check`, `git diff --cached`, and every commit being published. Never commit real exports, private paths, credentials, personal masters, or provider request/response logs. Ignored files are not a complete privacy boundary.

## Maintain the documentation layout

The README is a front door: purpose, one runnable example, visible output, implemented/planned boundaries, and links. Put detailed setup in the import guide, operational controls in the autonomy runbook, and design explanations in concepts. Preserve established guide paths when reorganizing navigation.

Use descriptive links, ordinary text headings, fenced commands with language tags, and text equivalents for any future figures. Do not rely on screenshots, emoji, badge colors, or a diagram alone to explain a required step. Keep the offline and paid paths visibly separate. Use invented examples only.

`tests/test_docs.py` checks local Markdown links/anchors, runs the marked post-clone README commands and quickstart inspection commands, and compares the demo output with its committed expectation. Keep its smoke markers around runnable offline commands only. It does not check external website availability or measure LLM accuracy.

## Layout inspiration

The onboarding borrows presentation patterns, not code or claims:

- [sqlite-utils](https://github.com/simonw/sqlite-utils): short purpose statement, concrete commands beside results, and links to deeper CLI/library references.
- [dlt](https://github.com/dlt-hub/dlt): a small end-to-end pipeline before the larger capability and configuration reference.

Both were consulted on 2026-09-20. Here those patterns become an account-free synthetic demo, inspectable evidence, task-based guides, and explicit current limitations. No affiliation or endorsement is implied.
