# Examples

[Overview](../README.md) · [Quickstart](../docs/getting-started.md) · [Documentation](../docs/README.md)

All committed example conversations are invented. No file here is a personal export or a real-model accuracy benchmark.

## Run the full offline example

From the repository root:

```sh
python3 -m conversation_archive.demo --output data/example-run
```

Use a new output directory. The demo builds its own branched, multilingual source, runs a deterministic test worker, tests resumption and replay, and leaves its miniature master unchanged. [demo-report.json](demo-report.json) is the expected deterministic report; tests compare it with the CLI output.

Follow [the quickstart](../docs/getting-started.md) to inspect the actual generated candidate and source packet. Generated evidence identities and filesystem paths belong in the local output, not in a screenshot presented as universal output.

## Try the importer without the controller

This separate fixture includes both providers. It does not call a model:

```sh
python3 -m conversation_archive normalize --config tests/fixtures/demo.toml --output data/import-example
python3 -m conversation_archive validate --dataset data/import-example
```

Browse the [ChatGPT fixture](../tests/fixtures/chatgpt.json), [Claude fixture](../tests/fixtures/claude.json), and [fixture configuration](../tests/fixtures/demo.toml). These are also used by regression tests, so they stay in `tests/fixtures/` rather than being copied into a second source of truth.

## Configure real data separately

[exports.example.toml](exports.example.toml) contains placeholder paths only. Copy its contents into a new ignored `local.toml`, replace the paths, and follow [the import guide](../docs/importing.md). Do not replace this committed template with private paths or exports.
