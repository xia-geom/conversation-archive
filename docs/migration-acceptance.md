# Structured authority: migration acceptance

[Agent contract](../AGENTS.md) · [Task map](../project.json) · [Documentation](README.md)

## Decision

Make structured machine-readable entries, relationship assertions, and correction history the authoritative working archive. Keep SQLite rebuildable from that archive. Generate exact navigation with code and narrative explanations with an LLM on demand. Markdown is an optional export, not the ongoing primary store. “Authoritative” identifies the maintained record; it does not mean every recollection is objectively true.

## Evidence boundary

The inspected GitHub baseline is `a4df7afbc21b8ccf293faef047c463e1892de586`. It contains extraction, the legacy Markdown reconciler, relationship rules, and contextual question batches. It does not contain the migration implementation described in the owner's local report.

The owner reports exact-slice preservation, a scoped prior-confirmation binding, a successor structured snapshot, and SQLite/view reconstruction without reading or modifying the master. Treat these as **reported local results**, not as a reproduced CI result or a reason to recreate the existing local work. No personal names, entry selections, private paths, source hashes, or archive contents are included here.

On a local checkout with migration code, inspect and test that implementation first. Publish code and synthetic tests through a focused change; do not copy the real snapshots into Git. Update the task map only when the implementation and its validation are present.

## Acceptance gates

| Gate | Demonstration required |
| --- | --- |
| Preservation | Exact input hashes before/after; every active entry mapped with stable ID, exact slice, source locator, and character convention. No silent omissions or renumbering. |
| Correction accounting | Map every original correction/source ID to retained evidence and, where applicable, an operational rule. Retained notes need not all become executable rules. Event/rule counts alone do not establish complete history. |
| Authority | Origin and review status are separate. Derived retrieval links stay derived; explicit links keep their stated meaning; owner-confirmed assertions reference active scoped support. |
| Independent update | A synthetic accepted correction creates a successor structured snapshot. Rebuild and query SQLite and views with the master inaccessible, not merely unchanged. |
| Replay and stale input | Reapplying the identical correction adds no duplicate event/rule/link. Reject ID reuse with different content and stale snapshot references. |
| Revocation | Remove support-dependent links, retain independent support and the old answer history, then rebuild queries/views. Extend the schema explicitly when only binding is currently supported. |
| Rebuild | Recreate derived SQLite and views solely from the structured archive. Check integrity, foreign keys, endpoints, scopes, hashes, and active rule dependencies. |
| No evidence feedback | Generated Markdown/navigation/LLM prose is labeled with source snapshot and view revision and cannot be reimported as independent confirmation. |
| Cutover | Record the designated authority, compatibility/migration version, exceptions, update command, and recovery procedure. Do not operate two independently editable masters. |

Use synthetic corrections for acceptance tests. Do not add a new personal confirmation merely to demonstrate a feature. Test repetition and reversal in the **new authoritative archive**, not only the older organization sidecar.

Unresolved question families and undiscovered implicit relationships are not migration corruption. Keep them explicit. Storage cutover does not establish semantic completeness, live-model accuracy, or a working LLM view service.

## Next implementation order

First recover and validate the already-developed local migration code. Then close correction-accounting and lifecycle gaps. Finally integrate bounded retrieval and the semantic proposer with the existing context-rich batches. Do not restart the historical extraction.

Every completion report should separate repository commit, local archive revision, tests actually run, reported-only results, unresolved cases, and generated views. Database creation alone is not completion.
