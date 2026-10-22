# Examples

[Read the sample archive](sample-archive.md) before installing anything. It is the exact Markdown produced by the invented garden demo, including the original quotation, uncertain event date, and source location.

Recreate it from the repository root:

```sh
python3 -m conversation_archive demo --output data/markdown-demo
```

Open `data/markdown-demo/organized.md`. Use a fresh output directory on each run. The demo's review decisions are predetermined; no private data or model connection is required.

For your own export, follow [Getting started](../docs/getting-started.md). [exports.example.toml](exports.example.toml) is the input-configuration template. Copy and edit it privately; keep real export locations and content outside Git. `demo-report.json` records the older candidate-extraction fixture used by regression tests.

[Workflow reference](../docs/workflow.md) · [Formats](../docs/formats.md) · [Compatibility with older examples](../docs/compatibility.md)
