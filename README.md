# Conversation Archive

Maintain **one organized Markdown file of important conversation information**, with source references, qualifications and corrections preserved. It is for you and ChatGPT—not a reproduction of every message.

```text
Chat exports + current organized.md
    → select information and reconcile whole entries
    → check evidence and review important ambiguities
    → publish one useful Markdown document
```

The normal collection has `organized.md`, preserved exports and a private `.state/` folder for progress and recovery. No SQL database, knowledge graph, embedding service or HTML application is required.

## Use it

Ask your authorized local agent:

> Use the organize-markdown skill to audit and update the supplied document. Read full entries and their evidence. Prioritize misplaced additions, stale uncertainty, contradictions and corrections. Preserve my edits, historical nuance and original sources. Use the checked reading pipeline; show the proposed Markdown before publishing. Ask me only about consequential ambiguity and do not upload anything automatically.

The [workflow](docs/workflow.md) connects existing source imports and checked edits with the `reading` audit/review/publication commands. The [skill](.agents/skills/organize-markdown/SKILL.md) guides editorial work; it does not replace deterministic checks or grant permissions. Mechanical scans flag candidates, not verified contradictions.

Implemented export adapters are ChatGPT and Claude. Gemini needs a separately tested adapter. Live model processing requires explicit transfer authorization; adding the result to ChatGPT remains a separate action.

## Try it without private data or a model

Python 3.11+ on macOS or Linux, from the checkout:

<!-- smoke:quickstart:start -->
```sh
python3 -m conversation_archive.demo --markdown --output data/markdown-demo
```
<!-- smoke:quickstart:end -->

Open `data/markdown-demo/organized.md`. This uses predetermined invented review decisions, not an automatic claim of model accuracy. The test suite also exercises a misplaced-source repair, clean publication, deferral and interruption recovery with invented records.

`python3 -m conversation_archive reading --help` lists the reading commands. Original evidence remains unchanged, and publication refuses to overwrite a manually edited output. Existing legacy collections are not silently migrated.

[Architecture](ARCHITECTURE.md) · [Agent instructions](AGENTS.md) · [Compatibility with existing archives](docs/compatibility.md)
