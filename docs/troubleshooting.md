# Troubleshooting

[Getting started](getting-started.md) · [Workflow](workflow.md) · [Formats](formats.md) · [Compatibility](compatibility.md)

## Python is missing or too old

Run `python3 --version`. This project requires Python 3.11 or newer. If the command is missing, or its version is older, install a supported Python version using your normal system setup. If that version is named `python3.11` or `python3.12`, use that executable in place of `python3` throughout the commands. A missing `tomllib` module usually means you are running an older Python.

## No module named conversation_archive

Run the command from the repository directory containing `README.md` and `conversation_archive/`. After cloning, run `cd conversation-archive`; after downloading a ZIP, enter its extracted directory. The command is `python3 -m conversation_archive`, with an underscore in the module name. No package installation is needed when running from the checkout.

## A file or directory cannot be found

Replace `/path/to/...` placeholders with your actual paths. Quote paths containing spaces, for example `--document "/path/to/My Collection/organized.md"`. Input paths inside a TOML configuration resolve relative to that configuration file; command-line relative paths resolve from your terminal's current directory. Originals must remain accessible for source-hash verification.

## The demo destination already exists

Open the existing `organized.md` if you want to see the previous result. To run a new example, choose a fresh directory:

```sh
python3 -m conversation_archive demo --output data/markdown-demo-2
```

The demo preserves existing output instead of replacing it. Repeating the command is different from its built-in check that the same reviewed update is applied only once.

## Scope selects no conversations

Check `--provider` and inspect your dataset's conversation records. A membership file uses exported `original_id` values; a normalized `record_id` or source-payload ID will not match. `--project-id` uses the exact exported ChatGPT `conversation_template_id`, not a project name. Follow [conversation selection](getting-started.md#select-the-right-conversations) for the inspection command and a complete membership example.

## No supported live entry headings found

The reading workflow expects entries with stable IDs and supported headings such as `## E0001 — Garden` or `### E0001 — Garden`. It does not automatically convert arbitrary notes into that structure. Check [the document format](formats.md#the-document), preserve the original, and review any needed conversion before auditing it. A new empty document created by `organize init` also needs reviewed entries before an entry audit is useful.

## Markdown is unchanged

Import, packet generation and candidate extraction do not install edits. Check `organize status --run ...`. Record actual source review, create a checked draft, inspect the diff, then apply authorized edits. A successful extraction is not a completed document update.

## A stale patch is refused

Read the current Markdown and compare with the draft's expected hash. Preserve manual changes. Prepare revised edits against the current document instead of replacing it with an older generated copy or bypassing the check.

## An interrupted installation is pending

Recover the identical batch and run before starting another installation. Keep its journal and source files. An ambiguous paid model attempt must be audited before retrying; do not delete state or reset budgets to make it disappear.

## A quoted passage or source cannot be found

Check the original message occurrence, exact segment, Unicode offsets, source hash and JSON pointer. A message ID may recur in another conversation. Do not substitute a nearby passage or an AI summary. Missing media and live-app completeness remain separate from exported text coverage.

## A new export seems to repeat information

Use the current Markdown and prior decisions for comparison. Unchanged bytes can be recognized exactly; similar accounts are not automatically the same event. A changed export needs a fresh validated dataset/run. No automatic cross-export semantic deduplication is claimed.

## An old command is missing

The SQL, knowledge-map, organization-engine and snapshot-review components were deliberately retired. Do not install another database to restore the new workflow. Use [compatibility](compatibility.md) for an existing archive that still needs the previous implementation.

## ChatGPT cannot find the information

Check that the correct Markdown version was actually supplied to its available file interface, that the information appears under a meaningful heading with enough context, and that no summary removed the relevant qualification. Test the real search path with synthetic examples. Local file generation or a passing text test is not proof of ChatGPT retrieval quality.
