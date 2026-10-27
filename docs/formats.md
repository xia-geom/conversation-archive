# File contracts

[Workflow](workflow.md) · [Architecture](../ARCHITECTURE.md)

## The document

`organized.md` is ordinary UTF-8 Markdown. Organize it by useful subjects, not by every source file. Use stable entry headings and anchors such as:

````md
<a id="e0001"></a>
### E0001 — Garden
The owner reported planting mint. The event date was not established.

Source: provider, original message ID, export SHA-256 and JSON pointer.

```text
Exact supporting words, in their original language.
```
````

The nested fences above are illustrative; choose a longer enclosing fence when copying an example. Quoted/fenced evidence is protected by the writer. Preserve original wording there; later corrections belong in the surrounding account with their own sources. Entry headings/IDs, internal links and optional frontmatter counters are checked. A source locator identifies a record; it is not a promise that a local path opens from ChatGPT.

The reading workflow accepts both `## E0001 — Title` and `### E0001 — Title`. An entry ends at a heading of the same or shallower level, or at another supported entry heading. Use deeper headings for sections within an entry. Headings inside fenced quotations or archived text remain evidence, not active entries.

### Sources for reading review

An inline quotation is readable, but a `reading` revision needs an exact witness from a named source block. Link the entry to that block, then keep the original text and provenance together:

````md
<a id="e0001"></a>
### E0001 — Garden

The owner reported planting mint. [Source quotation](#src-0001)

## Source archive

<a id="src-0001"></a>
### Source SRC-0001

Role: user. Provider: ChatGPT. Message: original-message-id.
Export SHA-256: exact-export-hash. JSON pointer: /0/mapping/u/message.

```text
Exact supporting words, in their original language.
```
````

Use real source identities and exact wording in your private document; the values above are placeholders. Source IDs must be unique. Each source block extends to the next anchor or the end of the document, so put unrelated sections before the source archive. `reading packet` supplies the source hash and text needed to construct exact character-range witnesses. See the [reading review contract](workflow.md#record-an-attributed-review).

Existing inline-only documents can be inspected and kept or deferred. For repairs, use the ordinary `organize` writer or first establish linked source blocks without changing the preserved evidence. A reference to an unavailable source does not supply its contents.

## Import state

The importer writes `manifest.json`, `conversations.jsonl`, `messages.jsonl`, `attachments.jsonl`, and a validation report. These are validated source representations, not a competing editorial archive. Records retain original IDs alongside unambiguous occurrence IDs, source hashes/pointers, graph/branch data, raw fields, roles, timestamps, text segments and media availability. Source offsets refer back to exported text. Exact schemas are exercised by `tests/test_pipeline.py`; `inspect --record-id` or `--line` retrieves records.

## Review decision

A decision JSON contains `decision_id`, `reviewer`, `reviewed_at`, `coverage`, and `findings`. Each coverage item names `piece_id`, an outcome, a reason and `finding_ids` when relevant. Outcomes are `already_represented`, `complementary_detail`, `distinct_episode`, `uncertain_overlap`, or `excluded`.

Each finding has its local `finding_id`, outcome, reason, attribution, and exact quotes when it makes a material addition. Quotes contain `message_record_id`, `segment_index`, `start`, `end`, and `text`. Offsets are Unicode characters within the original segment, not bytes or packet-relative offsets. The quoted range must have explicit review coverage. Internal-content placeholders are not narrative evidence. Optional `media_gaps` record missing or uninspected attachments separately from text coverage.

`supersedes` is limited to uninstalled review decisions. Installed decisions need subsequent checked correction/resolution work, not an overwritten history. Repeating an identical record is idempotent; an overlapping or altered record is rejected.

## Single-document edits

`organize draft` accepts:

```json
{
  "batch_id": "update-01",
  "document_sha256": "HASH_OF_CURRENT_MARKDOWN",
  "decision_ids": ["review-01"],
  "finding_dispositions": {
    "review-01/F1": {
      "outcome": "integrated",
      "reason": "Checked against the cited source.",
      "entry_ids": ["E0001"]
    }
  },
  "patches": [
    {"before": "A unique existing passage.", "after": "The reviewed replacement passage."}
  ]
}
```

This is a contract illustration, not an approved decision. Dispositions can be `integrated`, `already_represented`, `excluded`, or `unresolved`. Every finding needs one. A material integrated finding must retain its exact quotation and source witnesses in the document and point to an existing entry anchor. Missing support does not get replaced by guessed text.

The draft helper creates the legacy-compatible checked batch envelope internally: `files` has exactly the configured Markdown basename with before/after hashes and patches. The single-document format is opt-in through `prepare --document`; an existing three-file run is never reinterpreted. Unexpected output paths are rejected.

For an unresolved finding already installed, an optional `resolution_revision` identifies its latest `prior_batch_id`, explicit `finding_ids`, and reason. Only declared unresolved findings can change to resolved dispositions; unrelated prior outcomes remain unchanged. Reusing an installed decision to append it again is not allowed.

## State and recovery

A review inventory freezes its validated dataset and source scope; new single-document inventories also freeze `output_files`. Decisions live under `decisions/`; installation journals under `changes/` contain exact approved patches, dispositions, and installation state. These records replace the need for two separate correction-report documents in the normal workflow.

There is no database schema, entity registry, graph projection, or canonical `entries.jsonl` for the maintained knowledge document. See [compatibility](compatibility.md) for older machine snapshots.
