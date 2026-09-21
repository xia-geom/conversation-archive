# Authoritative machine archive

The staged migration has three layers with different authority:

```text
preserved migration source          authoritative archive          rebuildable views
emotion_master.md + confirmations -> versioned JSON/JSONL snapshot -> SQLite + Markdown
```

After the initial migration, the versioned JSON/JSONL snapshot is the ongoing structured record. SQLite is a disposable retrieval projection. The Markdown master remains preserved for provenance and comparison; generated Markdown never becomes evidence.

## Snapshot contents

Each immutable snapshot contains:

- `entries.jsonl`: existing entry IDs, exact Markdown slices, source hash and character bounds;
- `entry_metadata.jsonl` and `source_references.jsonl`: explicit fields separated from narrative text;
- `nodes.jsonl`, `mentions.jsonl`, `entities.jsonl`, and `relationships.jsonl`: graph records with explicit authority and status;
- `correction_events.jsonl` and `correction_rules.jsonl`: append-only owner answers and reusable finite-scope rules;
- `unresolved_questions.jsonl`: uncertainties that have not been promoted;
- `migration_sources.jsonl`: hashes and versions of migration inputs;
- `manifest.json`: snapshot ID, parent snapshot, per-file hashes and counts, authority policy, and migration exceptions.

The validator checks every file hash and record count, exact entry-snapshot hashes, metadata and mention character spans, relationship endpoints, active rule support for owner-confirmed links, and exact master quotations for imported explicit cross-entry links. A relationship imported with a generated authority remains generated. Import alone can never make it accepted evidence.

## Create the initial snapshot

First produce a checked migration SQLite database as documented in [structured archive](structured-archive.md). Then freeze its normalized records:

```sh
python3 -m conversation_archive.machine_archive snapshot \
  --database /path/to/private/migration.sqlite3 \
  --derived-graph /path/to/private/facet_graph.json \
  --snapshot-version 2026-09-20.1 \
  --output /path/to/private/archive-v1

python3 -m conversation_archive.machine_archive validate \
  --archive /path/to/private/archive-v1
```

The output directory must not exist. Snapshots are immutable; corrections create successors.

## Record an accepted correction

A correction decision names its exact basis snapshot and finite mention scope. Schema 1.0 supports `bind_mentions`; it refuses unknown mentions, entries, dependencies, conflicting identities, stale snapshots, and empty scope.

```json
{
  "version": "1.0",
  "decision_id": "owner-confirmed-example",
  "basis_snapshot_id": "AS-...",
  "actor": "Owner",
  "answer": "These displayed references identify the same person.",
  "operations": [{
    "op": "bind_mentions",
    "rule_id": "confirmed-example-scope",
    "depends_on": [],
    "kind": "person",
    "entity_id": "entity:person:example",
    "entity_label": "Example",
    "entry_ids": ["E0001", "E0002"],
    "mention_ids": ["M-...", "M-..."]
  }]
}
```

```sh
python3 -m conversation_archive.machine_archive correct \
  --archive /path/to/private/archive-v1 \
  --decision /path/to/private/accepted-decision.json \
  --snapshot-version 2026-09-20.2 \
  --output /path/to/private/archive-v2
```

The successor records the parent snapshot, correction event, rule, confirmed entity, changed mention assignments, and supported relationship edges. It copies unchanged evidence bytes rather than rewriting entries.

## Rebuild retrieval and views

```sh
python3 -m conversation_archive.machine_archive build-sqlite \
  --archive /path/to/private/archive-v2 \
  --database /path/to/private/rebuilt.sqlite3

python3 -m conversation_archive.machine_archive render \
  --database /path/to/private/rebuilt.sqlite3 \
  --output /path/to/private/views-v2
```

The rebuilt database records the archive snapshot ID. Queries and generated views reflect accepted corrections while the master remains byte-identical. Future correction operations, richer relationship assertions, FTS, or embeddings must preserve this authority model and create a new versioned snapshot.
