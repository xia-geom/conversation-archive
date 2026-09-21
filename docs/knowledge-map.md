# Local knowledge map: SQLite + Cytoscape.js

[Overview](../README.md) · [Agent contract](../AGENTS.md) · [Question batches](question-batches.md)

**Find an entry, follow a recorded connection, inspect its evidence.** This is a read-only local explorer of the existing organization state, not a new canonical archive, relationship-discovery model, or cloud service.

## Try the invented example

From a checkout, use Python 3.11+ with SQLite FTS5, macOS or Linux, and a modern browser:

```sh
python3 -m conversation_archive.knowledge_map demo --output data/map-demo
python3 -m conversation_archive.knowledge_map assets --output data/map-assets --download
python3 -m conversation_archive.knowledge_map serve --database data/map-demo/map.sqlite3 --run data/map-demo/organization --assets data/map-assets
```

Open the **complete session URL** printed by `serve`, including its fragment. Stop the foreground server with Ctrl+C. No model account or paid call is required. The demo creates seven invented entries with a project, a person, a contextual period, proposals and a rejected relationship. Its confirmations are fixture data, not actual user answers.

`assets --download` is an explicit, one-time download of the pinned Cytoscape.js library and license from GitHub. It sends no archive data. Files are checked against committed SHA-256 values before installation and every server start. There is no CDN, analytics, remote font, package installation, or model request during browsing. For an offline machine, copy those two verified files from another machine:

```sh
python3 -m conversation_archive.knowledge_map assets --output data/map-assets --from-directory /path/to/verified-assets
```

An existing valid asset directory is reused. A mismatched directory is refused rather than silently repaired. The upstream MIT license remains with the library; see [third-party notices](../THIRD_PARTY_NOTICES.md).

## What you can do

Search an entry ID, name, project or phrase. Filter search results by entry, person, project, place, period, topic, organization, event or mention. FTS5 uses literal prefix tokens, not semantic similarity; it does not resolve ambiguous names. CJK tokenization is basic, not a language-specific segmenter. Entries without any catalog match remain searchable.

Select a result to focus the map on one or two steps around it. Select a node to inspect exact stored entry text; select a link to inspect its direction, original status, provenance, quoted spans and supporting correction rules. Double-click a node, or use its inspector button, to make it the new focus. The list below the canvas offers the same navigation with keyboard-accessible buttons.

By default, only observed-text and user-confirmed connections are traversed. Explicitly include proposals or rejected links when investigating uncertainty. Status and relationship filters apply **before traversal**, not merely after layout. Dotted/dashed lines and textual labels supplement color. Rejected links are never traversed by default.

The overview hides mention plumbing by projecting `entry → mention → entity` into an entry/entity display shortcut. That shortcut retains every primitive edge ID, exact quotation and active rule. It is not new evidence and does not merge entries. **Show mentions** displays the original structure instead. Distances are steps in the selected display representation, not real-world causal distance.

Queries show at most 100 nodes and 300 edges by default; hard caps are 200 and 500. A partial neighborhood is labeled, never claimed complete. Search is paginated. Arrows retain the assertion's direction, while neighborhood exploration follows either direction for navigation. A path never establishes transitivity, event identity, chronology or cause.

## Use an existing organization run

This first adapter consumes the already implemented **organization state format 1.0**, through its existing validator. It reads `state.json`, checks its data and answer history, and regenerates its graph. It never reads or modifies the legacy Markdown master.

```sh
python3 -m conversation_archive.knowledge_map build --run /path/to/private/organization-run --database data/private-map-v1.sqlite3
python3 -m conversation_archive.knowledge_map serve --database data/private-map-v1.sqlite3 --run /path/to/private/organization-run --assets data/map-assets
```

Keep real indexes in ignored local storage. The database contains exact private text and answer history; it is not encrypted. Newly created database files are owner-readable/writable only. Inspect parent-directory permissions and keep them out of cloud publishing or public artifacts.

The authoritative-migration implementation reported locally is not in this GitHub baseline. **This adapter does not guess that snapshot's schema or replace it.** A future adapter must validate its version, authority/status, source evidence and correction lifecycle before projecting it into the same retrieval interface. It must not reparse Markdown to recover authority already available structurally.

## Staleness, corrections and rebuild

With `--run`, each query checks the recorded source-file hash. If the source changes or disappears, the map refuses queries and asks for a rebuild. Source checking involves no model call. The running server also rejects a modified/replaced database.

Record answers and revocations using the existing [reviewed batch workflow](question-batches.md), then build **a new database path** and restart the viewer. Existing different databases are never overwritten. Rebuilding the same unchanged input at the same path returns `already_current`; it does not duplicate entries. Revocation removes support-dependent links from the new projection while retaining rule history and independent support.

For intentional historical inspection when the source state is unavailable, use `--snapshot-only` instead of `--run`. The interface labels this as a historical, unwatched snapshot. It does not imply freshness.

```sh
python3 -m conversation_archive.knowledge_map search --database data/map-demo/map.sqlite3 --run data/map-demo/organization --query Orchard
python3 -m conversation_archive.knowledge_map neighbors --database data/map-demo/map.sqlite3 --run data/map-demo/organization --id entity:project:orchard --depth 2
```

These commands provide the same bounded retrieval to an agent without running a browser. They are deterministic retrieval primitives, **not an automatic natural-language question-answering or LLM explanation service**.

## Design and authority

```text
Validated structured organization state (read only)
             │
    existing graph + active rules
             │
       SQLite projection
       nodes / edges / rules / FTS5 / source fingerprint
             │
       bounded read API + CLI
             │
       local Cytoscape.js viewer
       search / neighborhood / evidence / accessible list
```

Origin and status are stored separately. Original graph records remain intact in payloads. Literal observations, supplied proposals and recorded answers retain their meanings. A generated display shortcut has `display_projection` origin and explicit dependencies; it is not counted as a newly confirmed historical claim. Snapshot metadata explicitly disclaims complete knowledge.

The projection and API are independently versioned at 1.0. Existing importer, organization, batch and reconciliation formats are unchanged. SQLite remains disposable: the structured source and correction history govern updates. Neither browser layout coordinates nor generated navigation feed back into evidence.

## Local-server boundary

The server binds only to `127.0.0.1` on a random port by default; it has no LAN-host option. Data endpoints require a random per-session header token. The bootstrap page contains no archive data. Host, Origin and browser fetch-site checks reject foreign-origin and DNS-rebinding-style requests. There is no CORS grant, arbitrary file route, SQL execution endpoint, upload route or archive-write API.

The token remains in the URL fragment, which is not sent as a request URL. Request logging is suppressed, and responses use no-store, no-referrer and a restrictive content-security policy. Archive strings are rendered as text, never HTML. Inline style permission is limited to styling needed by Cytoscape; executable inline scripts and external scripts are not allowed.

This is not a hardened internet server, authenticated multi-user application, encryption system or defense against a compromised browser extension or local account. Do not expose it through a proxy or tunnel. Stop it when finished.

## Verification

The normal dependency-free suite includes storage, exact provenance, source drift, failed imports, replay, revocation, search boundaries, SQL/FTS query handling, status-before-traversal, loopback API and asset-integrity tests:

```sh
python3 -m unittest discover -s tests -v
```

The separate [browser workflow](../.github/workflows/knowledge-map.yml) installs pinned Playwright, downloads the checked library, and exercises real Chromium on invented data. It checks rendering, evidence/rule inspection, rejected-edge filters, mention expansion, a narrow viewport, stale-source handling and inert hostile HTML. External page requests are blocked and counted. Screenshots/report are synthetic; ordinary CI never receives a personal archive.

References: [Cytoscape.js documentation](https://js.cytoscape.org/), [SQLite FTS5](https://sqlite.org/fts5.html), [SQLite read-only opening](https://sqlite.org/c3ref/open.html). The project does not require Neo4j, a JavaScript application framework, a vector database, or a new Python runtime dependency.
