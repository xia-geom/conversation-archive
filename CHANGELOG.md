# Changelog

## Unreleased — Markdown-first simplification

The primary product is one organized, source-attributed Markdown document. Added `ARCHITECTURE.md`; consolidated import/extraction/review/update documentation into workflow, formats and compatibility guides.

`organize prepare --document` freezes one configurable Markdown target, with no separate correction reports. Added exclusive initialization, checked draft compilation, a readable diff, explicit apply confirmation, a shared document lock, and a synthetic end-to-end Markdown demo. Existing source checks, manual-edit baselines, replay, interruption recovery and paid-extraction gates remain.

Removed SQL migration/retrieval, machine-snapshot review, the knowledge-map server/web assets, and the separate entity-organization framework with their dedicated tests and guides. Their history remains at the documented pre-refactor commit. Existing personal data is not deleted or migrated. Old three-file `reconcile --master` runs and optional exact raw-store backups remain compatible.

No new package release, automatic semantic integration, Gemini adapter, model-quality claim or ChatGPT retrieval-quality claim is made by this change.

## Earlier unreleased work — local knowledge map (now retired)

Added a read-only SQLite/FTS5 projection of validated organization state, bounded neighborhood retrieval, a local Cytoscape viewer with evidence/rule panels and accessible navigation, explicit pinned asset installation, stale-source checks, and synthetic browser tests. Existing archive formats and the draft alpha release were unchanged. This did not ship automatic semantic discovery. This implementation is retired by the Markdown-first simplification above.

## 0.1.2a1 — alpha preparation

Added the MIT license and package metadata, security/data-flow guidance, a contributor feedback form, release notes, a draft-release workflow, immutable Actions pins, Dependabot updates, and an independent secret-scan check. Added a private publication inventory for available Git history, discussions, Actions logs and artifacts.

The existing import, extraction, reconciliation, and relationship-batch algorithms were unchanged by that release. Importer/evidence versions remain separate from package version. That release deliberately did not implement the then-proposed new end-to-end workflow or structured-authority migration.

The initial release was prepared as a **draft prerelease**, not an announcement of general availability. Code availability, repository visibility, model quality, and user-trial completion are separate claims. See [release scope and owner settings](docs/public-alpha.md).
