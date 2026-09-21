# SQLite structured archive

This layer migrates the preserved Markdown master into a queryable local SQLite database. The Markdown file remains the evidence source; the database and every rendered Markdown page are reproducible derivatives.

```text
preserved emotion_master.md
          + append-only owner confirmations
          + optional derived relationship graph
                         |
                         v
                 archive.sqlite3
                         |
             +-----------+-----------+
             |                       |
       SQL retrieval          generated views
```

## Authority levels

The schema keeps materially different claims separate:

| Authority | Meaning |
| --- | --- |
| `explicit_master_metadata` | Exact value parsed from an active master entry field |
| `explicit_text_observation` | A catalog phrase occurs at an exact source span |
| `explicit_master_relationship` | A cross-entry relationship is written in the master |
| `owner_confirmed` | A finite, append-only owner answer supports the link |
| `proposed_inference` | A relationship proposal remains undecided |
| `generated_retrieval` | A derived similarity link helps search and establishes no identity, event equivalence, chronology, or cause |
| `owner_rejected` | A proposal was explicitly rejected and remains in history |

Generated navigation text never enters an evidence table. Rebuild it from SQLite instead of copying it into the master.

## Migrate a frozen master

Use a new database path. Migration refuses an existing database, a stale master hash, mismatched entry IDs, or entry text that differs from the frozen organization state.

```sh
python3 -m conversation_archive.structured_archive migrate \
  --master /path/to/emotion_master.md \
  --organization-state /path/to/organization/run/state.json \
  --questions /path/to/prioritized_questions.json \
  --derived-graph /path/to/facet_graph.json \
  --database /path/to/private/archive.sqlite3
```

The database stores exact entry Markdown and character ranges, explicit metadata, source references, literal mentions, accepted and proposed relationships, append-only correction events, reusable rules, and unresolved questions. Real databases remain under ignored local data or manifest directories and never belong in Git.

## Validate and retrieve

```sh
python3 -m conversation_archive.structured_archive validate \
  --database /path/to/private/archive.sqlite3 \
  --master /path/to/emotion_master.md

python3 -m conversation_archive.structured_archive query \
  --database /path/to/private/archive.sqlite3 --entry E0037

python3 -m conversation_archive.structured_archive query \
  --database /path/to/private/archive.sqlite3 --text Anne
```

Validation runs SQLite integrity and foreign-key checks, verifies the schema and optional current master hash, and reports counts. Text search is intentionally simple and inspectable; later FTS or embeddings can be added as separate retrieval indexes without changing evidence authority.

## Generate readable views

```sh
python3 -m conversation_archive.structured_archive render \
  --database /path/to/private/archive.sqlite3 \
  --output /path/to/private/generated-views
```

Rendering creates `navigation.md`, `people.md`, `themes.md`, `relationships.md`, `map.json`, and `summary.json`. The output directory must be new, so an earlier view is not silently overwritten. These files are presentations of database rows and must not be cited as new personal evidence.

## Resolve ambiguity

Use `organization_batches prepare` against the append-only organization state. A contextual batch freezes its numbering, source excerpts, known references, and source-state hash. Preview and apply only the owner's actual response. Then create a new SQLite migration version from the updated state and regenerate views. This preserves correction history and avoids editing generated prose as though it were evidence.
