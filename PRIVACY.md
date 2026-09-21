# Data flow and privacy

This document describes the checked-in tools, not a promise about a model provider's retention policy.

| Operation | Data used | Network/model boundary |
| --- | --- | --- |
| Import, normalize, validate, inspect | Configured local exports and attachment references | No model or attachment network fetch |
| Offline demo and ordinary tests | Invented repository fixtures | No model calls or API keys |
| Organization and contextual batches | Supplied entries, candidates, prior scoped answers | Deterministic local processing; an agent may separately propose semantics |
| Live `autonomy run` | Selected packet text, role/context, explicit model/effort | Requires `--allow-model-transfer`; sends packets to the configured Codex provider |
| Publication inventory | Repository Git objects, GitHub discussions, Actions logs and artifact metadata/content | Reads the selected GitHub repository, never a neighboring personal archive; no model |

The live adapter omits local provenance paths from its structured request, but a conversation's own text may contain private details. Consult the actual provider/account configuration before permitting transfer. This alpha has no built-in analytics collector; an externally invoked agent or provider is outside that statement.

Private inputs, snapshots, SQLite databases and journal sidecars, generated views, questions, answers, prompts, responses, receipts, event streams, and stderr belong outside Git or in ignored local directories. Ignore rules are neither encryption nor an assurance that historical copies were never committed.

Live attempts retain evidence and diagnostics locally; no automatic private-data retention/deletion schedule is imposed. The operator controls storage and deletion. Do not delete run state merely to reset spending. Share an invented minimal reproduction, not an archive or full log. Generated views are not new evidence.

The optional raw publication-review bundle contains existing repository history and logs. It is collected only while the repository is private, kept as a short-lived private artifact, and must be removed from GitHub before changing visibility. Retain only a reviewed, sanitized audit summary for publication.

[Security reporting](SECURITY.md) · [Agent contract](AGENTS.md)
