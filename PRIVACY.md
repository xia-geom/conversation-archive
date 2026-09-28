# Data flow and privacy

| Operation | Data | Boundary |
| --- | --- | --- |
| Import, normalize, validate, inspect | Configured exports and attachment references | Local; no model or attachment download |
| Organize, preview, checked apply | Current Markdown, reviewed source spans, proposed patches | Local deterministic code; semantic review is a separate human/agent action |
| Demo and ordinary tests | Invented fixtures | No model calls or credentials |
| Optional live extraction | Selected packet text and attribution/context | Requires explicit `--allow-model-transfer`; sends text to the configured provider |
| Optional raw store | Configured export bytes and comparison receipts | Local; does not update the Markdown |
| Publication audit | Selected repository history and logs | Reads GitHub, not a neighboring personal archive |

A local file read by a cloud agent is still model processing. This document is not a provider-retention guarantee. The live worker omits structured local path metadata, but the text itself may contain private details. Inspect the actual account/configuration and authorize transfer explicitly. No automatic upload of `organized.md` to ChatGPT is implemented.

Keep exports, Markdown documents, `.state`, draft edits, questions, answers, source quotations, prompts, provider responses, event streams, receipts, and stderr private and outside Git. Ignore rules are not encryption, a sync control, or proof that older copies were never committed. Inspect storage permissions and synchronization settings separately.

Preserve uncertain or interrupted attempts for recovery and cost accounting; do not reset limits by deleting checkpoints. Retention and deletion remain operator choices. Share only invented examples, not full private logs.

The optional publication-review bundle is collected only from a private repository, kept briefly, and must be removed from GitHub before changing visibility. Successful collection or a secret scan is not publication approval. Historical database/snapshot/view files on a user's machine remain sensitive even though their code has been retired; this refactor neither reads nor deletes them.

[Security](SECURITY.md) · [Architecture](ARCHITECTURE.md) · [Compatibility](docs/compatibility.md)
