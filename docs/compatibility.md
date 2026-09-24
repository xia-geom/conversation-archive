# Existing archives and retired components

This refactor changes repository code, not your personal data. Do not delete, move or reinterpret original exports, Markdown, raw stores, machine snapshots, correction history, or databases as part of updating the checkout.

## Markdown and review runs

New collections use `organize prepare --document ...` and one Markdown output. The old `reconcile` spelling and `--master` option remain for saved three-file review runs. Inventories without `output_files` retain their original master-plus-two-reports contract. Finish or recover an interrupted old batch under that contract; do not change its inventory to make it look new.

A completed legacy Markdown archive may continue as an existing document in a separately prepared single-document run. Keep its original reports and checkpoints as history. A code update alone does not authorize migrating a real collection or prove that every old decision has been accounted for.

## Machine snapshots and graph review

SQL migration/retrieval, knowledge-map code/assets, the separate entity-organization engine, and snapshot/HTML relationship review have been removed from the current product. They are not required to maintain Markdown and are not being rewritten as a collection of new JSON databases.

The last main-branch baseline before this simplification is `954fb223732f88421ff53d1111c02f43c8770837`. Its code and guides remain in [Git history](https://github.com/xia-geom/conversation-archive/tree/954fb223732f88421ff53d1111c02f43c8770837). Use a separate checkout at that version for an archive that still depends on it. Never reset or overwrite a working checkout containing uncommitted personal work. Unmerged feature branches are separate and are not silently incorporated by this refactor.

There is **no automatic conversion of machine-snapshot corrections into Markdown** in this change. A real conversion must explicitly account for existing entries, active/revoked decisions, unresolved questions and source references before changing authority. Preserve a working old version until that is checked.

## Optional raw export storage

`python3 -m conversation_archive.raw_store --help` still exposes exact-export ingest, verify and compare operations. Existing raw stores and receipts remain compatible. These utilities were retained because source backup and later-export comparison support the Markdown goal without a database. They do not update the Markdown or certify semantic coverage.

## Documentation changes

Import, extraction, review and update instructions are combined in [workflow](workflow.md); schemas and source locators in [formats](formats.md); architectural explanations in [ARCHITECTURE.md](../ARCHITECTURE.md). Historical guides are available at the pinned baseline above instead of maintaining duplicate manuals in the current tree. Security, licensing, publication records and historical release notes remain separate.
