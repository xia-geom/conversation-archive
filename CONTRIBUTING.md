# Contributing

[Architecture](ARCHITECTURE.md) · [Workflow](docs/workflow.md) · [Agent instructions](AGENTS.md)

Keep the product small: original exports, a maintained Markdown document, and enough bookkeeping to update it safely. A new database, graph, service, or representation needs a demonstrated reader problem—not an abstract preference for architecture.

Use Python 3.11+ on macOS or Linux. From the checkout:

```sh
python3 -m unittest discover -s tests -v
python3 -m conversation_archive.demo --markdown --output data/contributor-demo
```

Use a new demo directory. The demo is a predetermined synthetic exercise, not a model-quality evaluation. Ordinary tests must not use private archives, credentials, or live model calls.

A pull request should explain the user-visible change and tests actually run. Preserve source bytes, attribution, unknown dates, manual edits, prior decisions, and repeat/interruption behavior. Do not lower safeguards to make tests pass. Retired-feature tests can be removed with their implementation; retained source/update/security behavior still needs coverage.

README is the front door. ARCHITECTURE owns structure and boundaries; `docs/workflow.md` owns normal operation; `docs/formats.md` owns data contracts. Consolidate overlapping explanations rather than adding another guide. Keep compatibility decisions explicit. The Markdown link and executable-demo tests must pass.

Inspect the diff and all published commits for private data. Ignore rules are not encryption or proof that historical copies never existed. Use invented minimal reproductions. Do not change visibility, force-push, publish a release, or access a neighboring personal archive as a side effect of maintenance.

Contributions use the [MIT license](LICENSE). Report vulnerabilities through [SECURITY.md](SECURITY.md); keep [privacy](PRIVACY.md) and historical third-party attribution intact.
