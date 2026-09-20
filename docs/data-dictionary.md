# Data dictionary — schema 1.0

All outputs are UTF-8. JSONL has one object per line. Original strings are not normalized, translated, joined, or trimmed. A absent field and a JSON null can share a null projected value; consult `raw`, `raw_metadata`, or graph `node_fields` to distinguish original presence. Original files remain authoritative for byte-level representation.

## Shared record fields

| Field | Evidence / meaning | Limitation |
| --- | --- | --- |
| `schema_version` | Structure version (`1.0`) | Changing schema requires an explicit migration or new build |
| `importer_version` | Code's declared interpretation version (`0.1.1`) | Bump when projection/validation behavior changes |
| `record_id` | Kind prefix and SHA-256 of `source_id + newline + JSON pointer` | Stable within the same payload; not a cross-export identity |
| `provider` | Explicit source configuration: `chatgpt` or `claude` | Not inferred from filenames or prose |
| `provenance.source_id` | Provider plus original payload SHA-256 | Same bytes under different providers are different sources |
| `provenance.sha256` | SHA-256 of source JSON bytes, not a pretty-printed version | Exact duplicates only |
| `provenance.json_pointer` | RFC 6901 path into original JSON | Array indices are zero-based; `/` and `~` in keys are escaped |

Example: `/0/mapping/user~1~0node/message` points into the first ChatGPT conversation, then mapping key `user/~node`, then its message. Each projected string has a deeper pointer to its actual source location.

## Conversations

| Field | ChatGPT origin | Claude origin / interpretation |
| --- | --- | --- |
| `original_id` | `id`, otherwise `conversation_id` | `uuid` |
| `title` | `title` | `name`; no rewriting |
| `created_at_raw`, `updated_at_raw` | `create_time`, `update_time` | `created_at`, `updated_at` |
| `raw_metadata` | All conversation fields except `mapping` | All except `chat_messages`; may include exported summaries/account metadata |
| `message_count` | Number of non-null messages in mapping | Number of items in `chat_messages` |
| `graph` | All mapping nodes, including null-message nodes | One node per exported message |
| `current_node_id` | Exported `current_node`, else null | Always null: selection is not established |
| `root_parent_ids` | Empty list | Explicit Claude root sentinel, when present |

`raw_metadata` can contain machine-generated summaries. They are preserved metadata, not user testimony. Keeping whole original objects means the local dataset can still include personal/account fields present inside conversations. Code-only publishing excludes the entire real dataset.

Graph nodes:

| Field | Meaning |
| --- | --- |
| `node_id` | ChatGPT mapping key; Claude message UUID |
| `parent_id` | Exported parent; no guessed missing links |
| `children_ids` | ChatGPT exported list or null if absent/null; Claude list derived strictly from explicit parent links |
| `message_record_id` | Link to clean message; null for a null/absent ChatGPT message |
| `node_fields` | Original ChatGPT node fields except its message; empty for Claude |

Claude's root sentinel is `00000000-0000-4000-8000-000000000000`; it is an explicit exported marker, not a missing message. Arbitrary other missing parent IDs are errors. Node order follows the source mapping/list and is not assumed chronological. Branch-point statistics count nodes with multiple children according to explicit parent links. Contradictory exported child lists fail validation; absent lists produce a warning.

## Messages

| Field | Meaning and evidence |
| --- | --- |
| `conversation_record_id` | Link to clean conversation occurrence |
| `conversation_original_id` | Original provider conversation identifier |
| `original_id` | ChatGPT message `id` or Claude `uuid`; may recur in other memberships |
| `node_id`, `parent_id` | Graph identity and exact exported parent |
| `position` | Zero-based source graph/list position; ChatGPT null nodes count toward this position |
| `role_raw` | ChatGPT `author.role` / Claude `sender` |
| `role` | `user`, `assistant`, `system`, `tool`, or `unknown`; Claude `human` maps to `user` |
| `created_at_raw`, `updated_at_raw` | Exact original timestamp values or null when unavailable |
| `content_kind` | ChatGPT `content.content_type`; Claude uses `blocks` |
| `raw` | Complete original message JSON, including unfamiliar fields and content |
| `text_segments` | Exact readable strings with their original paths and evidence kind |

Each segment has `json_pointer`, `text`, and `kind` (`text`, `transcription_text`, or `attachment_text`). ChatGPT strings come from `parts` of `text`/`multimodal_text`. Exported audio-transcription blocks project their exact `text` as `transcription_text`; this is exported transcription, not a verification against speech. Claude strings come from top-level `text` and text blocks, which are **alternative exported representations** that may repeat or differ. Extracted attachment strings are separately tagged. The segment pointer identifies which representation you are reading; no canonical representation is chosen.

`thoughts`, `reasoning_recap`, `thinking`, `tool_use`, `tool_result`, `token_budget`, and `flag` remain in original content. Their presence is counted where applicable; they are not flattened into ordinary text segments. A speaker being `assistant` does not make every content block a visible assistant reply. Human-written text may quote other people or contain drafts; the pipeline does not infer quotation authorship.

Epoch numbers are validated as finite Unix seconds; ISO strings require timezone information. Exact timestamp values remain unchanged. These are message/conversation metadata, not dates of described events. Missing creation times warn; null update times are normal. Empty messages remain records; no text does not necessarily mean no content.

## Attachment references

| Field | Meaning |
| --- | --- |
| `conversation_record_id`, `message_record_id` | Owning message occurrence and conversation |
| `attachment_kind` | `attachment`, Claude `file_reference`, or ChatGPT non-transcription dictionary-part `multimodal_reference` |
| `raw` | Entire exported reference, including extracted text or unknown properties |
| `filename` | `file_name`, otherwise `name`; null if unavailable |
| `original_id` | `file_id`, `file_uuid`, or `id` when exported |
| `availability` | Status below; never an invented download success |
| `resolved_path` | Local candidate path only for an exact safe filename match |
| `sha256` | Candidate bytes' hash, otherwise null; not a provider-certified attachment identity |

| Availability | Meaning |
| --- | --- |
| `unverified_reference` | No usable filename/root, or multimodal pointer that this importer does not resolve |
| `missing` | No file at the exact relative filename in configured roots |
| `local_filename_match` | One local candidate found and hashed; identity not proven |
| `ambiguous_candidates` | More than one root contains a candidate; none chosen |
| `unsafe_reference` | Absolute/traversal path or symlink escaping configured roots; not followed |

A multimodal dictionary is kept as a reference even if it contains an unfamiliar shape; its raw block remains authoritative. No fuzzy file search, remote fetch, OCR, or attachment extraction is performed. The number of references is not the number of unique files.

## Inventory, manifest, validation

The inventory contains `schema_version`, `importer_version`, `sources`, `expected`, and `source_roots`. Each source has `source_id`, `provider`, `sha256`, payload `bytes`, and `locations`. Each location has absolute `path`, ZIP `member` (or null), `container_sha256`, and optional `attachment_root`. Exact duplicate payload aliases remain listed and are all checked. The manifest embeds this inventory, plus `files` (output hash and record count for each JSONL file) and `importer_warnings`.

The validation report has `status`, versions, `errors`, `warnings`, `limitations`, `counts`, and `statistics`. Issue objects have `code`, `record_id` (nullable), and `detail`. It distinguishes record counts, provider counts, source payload/location counts, branch points, content/role counts, missing metadata, and attachment availability. `repeated_message_ids_across_memberships` counts distinct original IDs seen more than once, not extra rows or proven duplicated conversations. Unknown content stays in raw and generates warnings. Invalid container/record structure or unsupported timestamps fail rather than being silently repaired.

Hashes detect changes against the retained manifest; they do not authenticate the exporter or protect against someone rewriting both inputs and manifests. Fidelity is checked against the currently retained original bytes. Commit importer code separately; keep evidence datasets and their manifests together locally.
