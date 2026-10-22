# Getting started

Conversation Archive helps you turn selected ChatGPT or Claude conversations into one readable Markdown document, with important quotations and source references. Python handles imports and checked edits. You or an authorized agent decide what the sources mean and what belongs in the document.

Start with the invented example below. It needs no account, API key, private export or model call.

## 1. Get the code

You need **Python 3.11 or newer**, Git, and a terminal on macOS or Linux. Check Python first:

```sh
python3 --version
```

Then download the repository and enter its directory:

```sh
git clone https://github.com/xia-geom/conversation-archive.git
cd conversation-archive
```

Run the commands in this guide from that directory, which contains `README.md` and the `conversation_archive/` package. No package installation or third-party Python dependencies are needed. If you downloaded a ZIP instead, extract it and enter the extracted directory. See [first-run troubleshooting](troubleshooting.md#python-is-missing-or-too-old) if a command fails.

## 2. Create your first document

```sh
python3 -m conversation_archive demo --output data/markdown-demo
```

Open the printed `organized.md` path in a text editor or Markdown viewer. It is inside `data/markdown-demo/`. The example contains this account and its original quotation:

> **E0001 — Garden**
>
> The owner reported planting mint.
> Event date: not established by the message timestamp.
>
> “I planted mint. 我今天种了薄荷。”

The file also records the original message ID, export hash and JSON location. The assistant's gardening suggestion is kept out of the owner's account. This shows the intended result: useful information, its limits, and the words supporting it.

The demo uses predetermined review decisions. It checks the update, applies it, and verifies that repeating the same update adds nothing. Its success does not mean a model reviewed your conversations. Keep the generated directory if you want to inspect its export and `.state/` records. To run another example, choose a fresh destination such as `data/markdown-demo-2`.

## 3. Choose your next step

| What you have | Where to start | What happens next |
| --- | --- | --- |
| Original ChatGPT or Claude exports | [Import and organize](workflow.md#1-preserve-inputs-and-import) | Import into a dataset, select conversations, review source packets, then check and apply edits. |
| An existing document using this project's entry format | [Audit an existing document](workflow.md#6-entry-audit-reconciliation-and-clean-reading-publication) | Review complete entries and their sources, inspect a preview, then publish a fresh local file. |
| A later export for a maintained document | [Later exports](workflow.md#7-later-exports-and-actual-chatgpt-retrieval) | Import into a fresh dataset/run and compare with the existing document and review history. |
| An archive using older commands or multiple reports | [Compatibility](compatibility.md) | Identify its existing contract before continuing or migrating. |

For your own collection, keep exports, the maintained document, configuration and review state **outside the Git checkout**. Originals may stay where they already are. The demo's `data/` directory is ignored by Git and contains only invented records.

### Starting from exports

Follow [workflow steps 1–5](workflow.md#1-preserve-inputs-and-import). Copy the [input configuration template](../examples/exports.example.toml) to your private collection and set the actual export paths. Paths in that file resolve relative to the configuration file.

After `normalize` and `validate`, select the conversations you want to review. The next section explains the IDs used by that selection. To create a new document, use `organize init --document /path/to/private/organized.md`; keep an existing document as the baseline instead of initializing over it.

### Starting from Markdown

The `reading` commands recognize this project's entry headings, anchors and source references; they do not accept every Markdown document. An entry uses a stable ID and a level-two or level-three heading such as `## E0001 — Garden` or `### E0001 — Garden`, with an anchor such as `<a id="e0001"></a>`. Preserve the source references and exact evidence associated with each entry. See [the format guide](formats.md#the-document) and [the reading workflow](workflow.md#6-entry-audit-reconciliation-and-clean-reading-publication).

To revise an entry, its evidence must be available in a [linked source block](formats.md#sources-for-reading-review). The demo shows this format. Inline-only quotations can be read, but they do not yet supply the named evidence required for a checked reading revision.

If your notes use another structure, agree on a conversion that preserves their content and evidence before starting the audit. `organize init` creates a new empty template; it does not convert existing notes or supply reviewed entries.

## Select the right conversations

These steps follow import and validation. Replace `/path/to/private/dataset-01` with the dataset directory you just created. Inspect a conversation and its original export record:

```sh
python3 -m conversation_archive inspect --dataset /path/to/private/dataset-01 --kind conversations --line 1
```

`--line` is one-based; use `2`, `3`, and so on to inspect other records. The dataset's `conversations.jsonl` contains one normalized conversation per line. The command returns `clean`, `original`, and `source_locations`, and checks the stored record and source hashes.

| Field in the returned `clean` record | Use |
| --- | --- |
| `original_id` | Put this exported conversation ID in `conversation_ids` below. ChatGPT uses its exported `id` or `conversation_id`; Claude uses its exported `uuid`. |
| `record_id` | Identifies this normalized occurrence. Use it with `inspect --record-id` instead of `--line` when retrieving the same record. |
| `raw_metadata.conversation_template_id` | If present and verified for your intended ChatGPT project, use its exact value with `organize prepare --project-id`. |
| `provenance.source_id` | Identifies the export payload in `manifest.json`; it is separate from the conversation and project IDs. |

Check the conversation's identity and original context before selecting it. A title alone does not establish project membership. If the exported project ID is missing or your selection is an explicit list, use a membership file. Claude requires this list.

Save a `selection.json` in your private collection with these four fields. This complete example selects the **invented** demo conversation; replace the ID, observation date, evidence and selection name with your actual selection:

```json
{
  "conversation_ids": ["invented-one"],
  "observed_at": "2026-01-01",
  "evidence": "The owner explicitly selected invented-one for this synthetic example.",
  "project_name": "Invented garden selection"
}
```

Record how you established the selection in `evidence`. `observed_at` is when you established it, not the message or event date. Use the exported `original_id` values, not the normalized `record_id` or `provenance.source_id`. A selection name does not prove membership in a live project.

Then prepare the review using your selected provider:

```sh
python3 -m conversation_archive organize prepare --dataset /path/to/private/dataset-01 --document /path/to/private/organized.md --run /path/to/private/review-01 --provider chatgpt --membership /path/to/private/selection.json
python3 -m conversation_archive organize packet --run /path/to/private/review-01
```

For Claude, change `--provider chatgpt` to `--provider claude`. Prepare separate runs for each provider. Use either `--membership` or the verified ChatGPT `--project-id`, never both. Inspect reported missing IDs before claiming your selection is covered.

The packet is the next material to read. Continue with [review and composition](workflow.md#4-review-and-compose), followed by the checked preview and update. Importing or generating a packet does not complete that review.

## A few terms

| Term | Meaning |
| --- | --- |
| Document | The one Markdown file you maintain and read. |
| Dataset | Imported records and source locations derived from an export. |
| Run | A directory holding one review's scope, decisions and progress. |
| Packet | Source or entry text prepared for a reviewer to read. |
| Preview | Proposed Markdown and a diff to inspect before an authorized write. |
| Publish | Create a checked local reading file. Uploading it to ChatGPT is a separate action. |
