# Conversation Archive

Maintain **one organized Markdown file of the important information in your chats**, with source references and your corrections preserved. The file is intended to be useful to you and to a reader such as ChatGPT—not to reproduce every message.

```text
Chat exports + current organized.md
           ↓
Select important information and compare with existing entries
           ↓
Check evidence, resolve important ambiguities, apply approved edits
           ↓
organized.md
```

The normal collection has `organized.md`, preserved exports, and a private `.state/` folder for progress and update history. There is **no SQL database, knowledge graph, snapshot migration, or HTML application to maintain**.

## Use it

Ask your authorized local agent:

> Update organized.md from the supplied chat exports. Follow AGENTS.md. Reuse completed work, preserve my edits and original evidence, organize by useful topics, and raise only important contradictions or ambiguities. Show checked changes before applying them. Do not upload the result automatically.

The implemented importer supports ChatGPT and Claude. Gemini requires a separately tested adapter; do not pretend a Gemini export was processed. Live model processing requires explicit transfer authorization. Adding the resulting Markdown to ChatGPT is a separate user action; local file creation does not upload it.

## Try it without private data or a model

Python 3.11+ on macOS or Linux. From the checkout:

<!-- smoke:quickstart:start -->
```sh
python3 -m conversation_archive.demo --markdown --output data/markdown-demo
```
<!-- smoke:quickstart:end -->

Open `data/markdown-demo/organized.md`. The demo uses predetermined **invented** review decisions. It exercises import, exact quotations, single-document updates and safe replay; it does not claim automatic model accuracy.

## Work on real exports

The [workflow guide](docs/workflow.md) covers import, optional bounded extraction, review, preview, and update. These are internal stages of one workflow, not products you must maintain separately. `organize --help` lists the actual commands; it is not an unattended summarization service.

[Architecture](ARCHITECTURE.md) · [Agent instructions](AGENTS.md) · [Compatibility with existing archives](docs/compatibility.md)
