# Add later exports without storing every message again

**AI agents:** read this contract before ingesting new exports. Use `python3 -m conversation_archive.raw_store --help`. This is an offline evidence-storage and comparison layer, not an automatic master updater.

## What it does

Read an existing ChatGPT JSON file, conversation directory, or export ZIP **in place**. No copy into an inbox is necessary. Store exact JSON fragments by SHA-256 and write a manifest describing their order. Identical message bytes are shared across exports, while each conversation/node occurrence keeps its own source reference. A changed message is new evidence; old bytes remain available.

```text
Existing JSON / ZIP (read-only, kept where it is)
                      |
            lossless JSON segmentation
                      |
       raw/blobs/sha256/<prefix>/<remaining hash>
                      |
       exports/EX-<hash>.json     exact payload recipes + occurrence index
       receipts/IN-<hash>.json    original locations + container hashes
                      |
           explicit old/new export comparison
                      |
       new / changed / unchanged / context changed / not present / ambiguous
```

The design borrows the content-keyed object/manifest idea from [Git objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects); it does **not** place private raw objects inside source Git.

## Commands

Try the existing invented fixture first:

```sh
python3 -m conversation_archive.raw_store ingest --source tests/fixtures/chatgpt.json --store data/raw-example --namespace example-account
python3 -m conversation_archive.raw_store ingest --source tests/fixtures/chatgpt.json --store data/raw-example --namespace example-account
```

The second call reports `already_present`, `new_blobs: 0`, and `new_blob_bytes: 0`. It does not make a second receipt for the identical path/container. A new source location or ZIP repackaging gets a distinct receipt but can reuse the same export manifest and all blobs.

For actual work, keep the store local and ignored. The namespace is an explicit stable account label, not an email address or credential. Use different stores for different accounts; the label cannot detect an incorrectly supplied account export.

```sh
python3 -m conversation_archive.raw_store ingest \
  --source /path/to/latest-chatgpt-export.zip \
  --store /path/to/private/raw-store --namespace personal-chatgpt
```

`--source` can be repeated for split files. Directory scanning is nonrecursive and selects only `conversations.json` and `conversations-NNN.json`; list ZIPs explicitly. ZIPs select matching basenames. Full archive scope is caller-supplied, not inferred from a filename or modification time.

Save the returned export ID. Compare two explicitly chosen exports, in the intended order:

```sh
python3 -m conversation_archive.raw_store diff \
  --store /path/to/private/raw-store --before EX-OLD_HASH --after EX-NEW_HASH
python3 -m conversation_archive.raw_store verify \
  --store /path/to/private/raw-store --export EX-NEW_HASH
```

Replace the placeholder IDs with the full IDs from ingestion. No implicit `latest` pointer is used: importing an older or partial export must not silently become the new authority. Comparison has no model calls and grants no review coverage.

An explicit recovery/export command recreates one selected JSON payload byte-for-byte, without the original source file:

```sh
python3 -m conversation_archive.raw_store restore \
  --store /path/to/private/raw-store --export EX-NEW_HASH \
  --payload PAYLOAD_SHA256 --output /path/to/new-restored-conversations.json
```

The payload hash is in the export manifest. The output must be a new path outside the store. Restoring creates a full copy only when explicitly requested and can supply the existing normalizer. It does not reconstruct a ZIP container or its media.

## Three different identities

| Identity | Role |
| --- | --- |
| Exact-byte blob hash | Physical deduplication; original whitespace, escaping, Unicode, numeric spelling and BOM are retained |
| Export ID + payload hash + JSON pointer / byte span | Immutable source occurrence in a particular export; repeated text and IDs never erase membership |
| Provider + account namespace + conversation ID + mapping-node key | Conservative logical comparison key across exports; the message ID and all message fields are checked for changes |

Canonical parsed-JSON hashes are **comparison keys**, not replacements for source bytes. Reordered conversations, object keys or changed indentation can produce a new raw export while leaving message meaning candidates unchanged. Whitespace inside strings, role changes, message IDs, metadata and content changes remain changes. No fuzzy deduplication or person/event merging occurs.

The index preserves null-message graph nodes, unknown content and attachment pointers. Duplicate/missing/conflicting conversation identifiers, unusable node/message IDs, cyclic parent context, and missing referenced context remain visible ambiguities; affected cases are not automatically matched. Malformed JSON, duplicate JSON keys and unsupported structural shapes stop ingestion rather than silently dropping records.

## What a delta means

| Comparison result | Meaning / next-stage behavior |
| --- | --- |
| `new_messages` | New source occurrence; eligible for later extraction |
| `changed_messages` | A new version at a comparable node; retain the previous evidence |
| `unchanged_messages` | Same message and graph context in this comparison, not proof it was previously extracted or integrated |
| `context_changed_messages` | Message text can be unchanged, but node topology or an ancestor changed; reassess context before reusing interpretation |
| `conversation_metadata_changed` | Inspect changes such as project membership or selected branch before trusting earlier scope decisions |
| `not_present_messages` / conversation absent | Not observed in this export; **not deletion** and never a reason to remove earlier evidence |
| `ambiguities` | Preserve each source occurrence and request review; do not guess a global identity |

Comparison includes all exported graph branches; branch selection remains metadata. The logical key does not migrate previous extraction checkpoints or correction scopes. A future controller must separately track `seen`, `extracted`, `reviewed` and `integrated` and dispatch only relevant unresolved work. Existing authoritative snapshots, SQLite projections and portable ChatGPT views are **not automatically rewritten by these commands**.

## Storage and recovery boundaries

Repeated byte-identical fragments occupy one blob within a store. Export manifests carry references and comparison metadata, not another full message body. However, **the original download plus this store still coexist**. This release never moves or deletes input files. Do not describe it as zero duplicate bytes on the entire computer, or claim that existing machine-archive snapshots have been converted to shared-blob storage.

Only selected conversation JSON bytes are archived. ZIP compression metadata, account sidecars, HTML, images, audio and project files are not stored; receipts disclose omitted member counts. Attachment pointers are not attachment backups. Keep original ZIPs while those materials remain relevant. Media-content changes with an unchanged pointer are not detected by this layer.

The first implementation favors inspectability over minimal filesystem overhead. Tiny fragments, manifest indexes and filesystem blocks can outweigh savings for small records. Large formatting changes create new byte fragments even when the logical comparison skips re-extraction. `new_blob_bytes` excludes manifests, receipts, filesystem allocation, original downloads and organized snapshots. No universal compression/savings percentage is claimed.

The writer uses an advisory per-store lock, owner-only new files, fsynced temporary writes, and no-clobber hard-link publication. A receipt is installed after its manifest and blobs. Interrupted imports may leave valid unreferenced blobs/manifests or temporary files; rerun the same command to finish without replacing evidence. No automatic garbage collection or history deletion is implemented. Hashes catch corruption/drift, not a malicious actor who controls both content and hashes.

`verify` reconstructs each selected payload and recomputes its occurrence index. It validates the named export, not every orphan object, receipt location, missing media or real-world truth. It works with original input locations unavailable. Source hashes are checked before/after reading and again before manifest publication.

Writing requires Python 3.11+ on macOS/Linux and a local filesystem supporting hard links, file locking and fsync. Inputs are bounded to 128 MiB per uncompressed payload and 512 MiB per ingest, with 1,000 selected payload files and 100,000 ZIP directory entries. Parsing is in memory; these are byte bounds, not a guarantee of low peak memory. The importer refuses excessive input rather than truncate. ZIP members are never extracted to their named paths; duplicate, traversal-shaped or encrypted members are rejected. See Python's [ZIP resource limitations](https://docs.python.org/3/library/zipfile.html#decompression-pitfalls).

## Compatibility and tests

Raw-store format 1.0 is independent of the normalizer, organization and machine-archive schemas. No existing interfaces or IDs change. Ordinary code resolves export/payload/pointer references; a future machine-archive schema may carry those references only through a versioned extension.

Run `python3 -m unittest discover -s tests -p test_raw_store.py -v`. The invented tests exercise exact reconstruction, repeat/no-clobber behavior, cross-export membership, contextual changes, missing/ambiguous IDs, source mutation, interrupted writes, namespaces, Unicode, ZIP bounds and unsafe paths. They do not evaluate LLM extraction or an end-to-end personal-archive update.
