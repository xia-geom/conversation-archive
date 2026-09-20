"""Check derived records against original sources, not just importer assertions."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from .inventory import (
    canonical,
    load_source,
    resolve_pointer,
    sha_file,
    strict_loads,
    verify_sources,
)
from .model import (
    FormatError,
    SCHEMA_VERSION,
    IMPORTER_VERSION,
    record_id,
    pointer_token,
)
from .adapters.claude import ROOT


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a timestamp")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Nonfinite timestamp")
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Timestamp has no timezone")
        return dt
    raise ValueError("Unsupported timestamp")


def validate(root):
    report = {
        "status": "failed",
        "schema_version": SCHEMA_VERSION,
        "importer_version": IMPORTER_VERSION,
        "errors": [],
        "warnings": [],
        "limitations": [
            "Structural fidelity is not verification that a reported event happened.",
            "Message timestamps are recording metadata, not inferred event dates.",
            "Claude selected branches and project membership are not established by these exports.",
            "Shared message IDs or branch titles do not establish cross-conversation ancestry.",
            "Attachment filename matches are local candidates, not proof of identity; no files are fetched.",
            "Exported assistant thoughts, tool output, memories, and user statements are not interchangeable evidence.",
        ],
        "counts": {},
        "statistics": {},
    }
    errors = report["errors"]
    warnings = report["warnings"]
    stats = Counter()
    counts = Counter()

    def problem(code, detail, rid=None):
        errors.append(dict(code=code, record_id=rid, detail=detail))

    def check(condition, code, detail, rid=None):
        if not condition:
            problem(code, detail, rid)

    def warn(code, detail, rid=None):
        warnings.append(dict(code=code, record_id=rid, detail=detail))

    try:
        manifest = strict_loads((root / "manifest.json").read_bytes())
        inv = manifest["inventory"]
        check(
            manifest.get("schema_version") == SCHEMA_VERSION,
            "schema_version",
            "Unsupported schema version",
        )
        check(
            manifest.get("importer_version") == IMPORTER_VERSION,
            "importer_version",
            "Importer version differs from current code",
        )
        verify_sources(inv)
        sources = {s["source_id"]: s for s in inv["sources"]}
        check(
            len(sources) == len(inv["sources"]),
            "source_collision",
            "Duplicate source identity",
        )
        for s in sources.values():
            check(
                s["source_id"] == s["provider"] + ":" + s["sha256"],
                "source_identity",
                "Source identity does not match bytes/provider",
            )
        expected = {k: set() for k in ("conversations", "messages", "attachments")}
        expected_counts = Counter()
        # Independent source census. This deliberately does not call normalize().
        for src in inv["sources"]:
            data = load_source(src)
            p = src["provider"]
            sid = src["source_id"]
            ids = set()
            for i, c in enumerate(data):
                cp = f"/{i}"
                expected["conversations"].add((sid, cp))
                expected_counts[p + "_conversations"] += 1
                cid = (
                    (c.get("id") or c.get("conversation_id"))
                    if p == "chatgpt"
                    else c.get("uuid")
                )
                check(
                    cid not in ids,
                    "conversation_id_collision",
                    "Repeated conversation id within source",
                )
                ids.add(cid)
                if p == "chatgpt":
                    rawmsgs = [
                        (
                            cp + "/mapping/" + pointer_token(nid) + "/message",
                            node["message"],
                        )
                        for nid, node in c["mapping"].items()
                        if node.get("message") is not None
                    ]
                else:
                    rawmsgs = [
                        (f"{cp}/chat_messages/{j}", m)
                        for j, m in enumerate(c["chat_messages"])
                    ]
                for ptr, m in rawmsgs:
                    expected["messages"].add((sid, ptr))
                    expected_counts[p + "_messages"] += 1
                    if p == "chatgpt":
                        for j, _ in enumerate(
                            m.get("metadata", {}).get("attachments", []) or []
                        ):
                            expected["attachments"].add(
                                (sid, f"{ptr}/metadata/attachments/{j}")
                            )
                        content = m.get("content", {})
                        if isinstance(content, dict) and content.get(
                            "content_type"
                        ) in ("text", "multimodal_text"):
                            for j, part in enumerate(content.get("parts", [])):
                                if isinstance(part, dict) and not (
                                    part.get("content_type") == "audio_transcription"
                                    and isinstance(part.get("text"), str)
                                ):
                                    expected["attachments"].add(
                                        (sid, f"{ptr}/content/parts/{j}")
                                    )
                    else:
                        for field in ("attachments", "files"):
                            for j, _ in enumerate(m.get(field, []) or []):
                                expected["attachments"].add((sid, f"{ptr}/{field}/{j}"))
        cache_sid = None
        cache_data = None

        def raw_at(sid, ptr):
            nonlocal cache_sid, cache_data
            if cache_sid != sid:
                cache_data = load_source(sources[sid])
                cache_sid = sid
            return resolve_pointer(cache_data, ptr)

        seen_global = set()
        convs = {}
        message_links = {}
        message_sources = {}
        original_memberships = Counter()
        for kind in ("conversations", "messages", "attachments"):
            path = root / (kind + ".jsonl")
            spec = manifest["files"][path.name]
            check(
                sha_file(path) == spec["sha256"],
                "clean_hash_mismatch",
                f"{path.name} bytes changed",
            )
            seen = set()
            n = 0
            with path.open(encoding="utf-8") as f:
                for line in f:
                    n += 1
                    r = strict_loads(line)
                    rid = r["record_id"]
                    prov = r["provenance"]
                    sid = prov["source_id"]
                    ptr = prov["json_pointer"]
                    src = sources[sid]
                    provider = src["provider"]
                    check(
                        rid not in seen_global,
                        "record_id_collision",
                        "Repeated record identity",
                        rid,
                    )
                    seen_global.add(rid)
                    check(
                        (sid, ptr) not in seen,
                        "source_pointer_collision",
                        "Repeated source location",
                        rid,
                    )
                    seen.add((sid, ptr))
                    singular = {
                        "conversations": "conversation",
                        "messages": "message",
                        "attachments": "attachment",
                    }[kind]
                    check(
                        rid == record_id(singular, sid, ptr),
                        "record_identity",
                        "Record identity does not match its source",
                        rid,
                    )
                    check(
                        r.get("schema_version") == SCHEMA_VERSION
                        and r.get("importer_version") == IMPORTER_VERSION,
                        "record_version",
                        "Record version mismatch",
                        rid,
                    )
                    check(
                        r["provider"] == provider and prov["sha256"] == src["sha256"],
                        "provenance",
                        "Source provenance mismatch",
                        rid,
                    )
                    raw = raw_at(sid, ptr)
                    if kind == "conversations":
                        counts[provider + "_conversations"] += 1
                        convs[rid] = r
                        field = "mapping" if provider == "chatgpt" else "chat_messages"
                        check(
                            r["raw_metadata"]
                            == {k: v for k, v in raw.items() if k != field},
                            "metadata_fidelity",
                            "Original conversation metadata changed",
                            rid,
                        )
                        check(
                            r["original_id"]
                            == (
                                (raw.get("id") or raw.get("conversation_id"))
                                if provider == "chatgpt"
                                else raw.get("uuid")
                            ),
                            "conversation_identity",
                            "Conversation original id mismatch",
                            rid,
                        )
                        check(
                            r["title"]
                            == raw.get("title" if provider == "chatgpt" else "name"),
                            "title_fidelity",
                            "Original title changed",
                            rid,
                        )
                        check(
                            r["created_at_raw"]
                            == raw.get(
                                "create_time" if provider == "chatgpt" else "created_at"
                            )
                            and r["updated_at_raw"]
                            == raw.get(
                                "update_time" if provider == "chatgpt" else "updated_at"
                            ),
                            "timestamp_fidelity",
                            "Original timestamp changed",
                            rid,
                        )
                        if provider == "chatgpt":
                            wanted = []
                            for nid, node in raw["mapping"].items():
                                mp = ptr + "/mapping/" + pointer_token(nid) + "/message"
                                wanted.append(
                                    dict(
                                        node_id=nid,
                                        parent_id=node.get("parent"),
                                        children_ids=node.get("children"),
                                        message_record_id=(
                                            record_id("message", sid, mp)
                                            if node.get("message") is not None
                                            else None
                                        ),
                                        node_fields={
                                            k: v
                                            for k, v in node.items()
                                            if k != "message"
                                        },
                                    )
                                )
                            check(
                                r["current_node_id"] == raw.get("current_node")
                                and r["root_parent_ids"] == [],
                                "branch_selection",
                                "Current node or root markers changed",
                                rid,
                            )
                        else:
                            children = defaultdict(list)
                            for m in raw["chat_messages"]:
                                children[m.get("parent_message_uuid")].append(m["uuid"])
                            wanted = [
                                dict(
                                    node_id=m["uuid"],
                                    parent_id=m.get("parent_message_uuid"),
                                    children_ids=children[m["uuid"]],
                                    message_record_id=record_id(
                                        "message", sid, f"{ptr}/chat_messages/{j}"
                                    ),
                                    node_fields={},
                                )
                                for j, m in enumerate(raw["chat_messages"])
                            ]
                            roots = (
                                [ROOT]
                                if any(
                                    m.get("parent_message_uuid") == ROOT
                                    for m in raw["chat_messages"]
                                )
                                else []
                            )
                            check(
                                r["current_node_id"] is None
                                and r["root_parent_ids"] == roots,
                                "branch_selection",
                                "Claude selected branch must remain unknown and exported roots preserved",
                                rid,
                            )
                        check(
                            r["graph"] == wanted,
                            "graph_fidelity",
                            "Exported graph was changed",
                            rid,
                        )
                    elif kind == "messages":
                        counts[provider + "_messages"] += 1
                        check(
                            canonical(r["raw"]) == canonical(raw),
                            "raw_fidelity",
                            "Original message object changed",
                            rid,
                        )
                        cid = r["conversation_record_id"]
                        conv = convs.get(cid)
                        check(
                            conv is not None,
                            "conversation_reference",
                            "Missing parent conversation",
                            rid,
                        )
                        if conv:
                            check(
                                r["conversation_original_id"] == conv["original_id"],
                                "conversation_membership",
                                "Conversation membership changed",
                                rid,
                            )
                            check(
                                ptr.startswith(conv["provenance"]["json_pointer"] + "/")
                                and sid == conv["provenance"]["source_id"],
                                "conversation_membership",
                                "Message source is outside its conversation",
                                rid,
                            )
                        role_raw = (
                            raw.get("author", {}).get("role")
                            if provider == "chatgpt"
                            else raw.get("sender")
                        )
                        role = (
                            role_raw
                            if provider == "chatgpt"
                            and role_raw in ("user", "assistant", "system", "tool")
                            else (
                                {"human": "user", "assistant": "assistant"}.get(
                                    role_raw, "unknown"
                                )
                                if provider == "claude"
                                else "unknown"
                            )
                        )
                        check(
                            r["role_raw"] == role_raw and r["role"] == role,
                            "role_fidelity",
                            "Speaker role changed",
                            rid,
                        )
                        if role == "unknown":
                            warn(
                                "unknown_role",
                                "Unrecognized speaker retained as unknown",
                                rid,
                            )
                        check(
                            r["created_at_raw"]
                            == raw.get(
                                "create_time" if provider == "chatgpt" else "created_at"
                            )
                            and r["updated_at_raw"]
                            == raw.get(
                                "update_time" if provider == "chatgpt" else "updated_at"
                            ),
                            "timestamp_fidelity",
                            "Original timestamp changed",
                            rid,
                        )
                        check(
                            r["original_id"]
                            == raw.get("id" if provider == "chatgpt" else "uuid"),
                            "message_identity",
                            "Original message id changed",
                            rid,
                        )
                        original_memberships[(provider, r["original_id"])] += 1
                        segments = []
                        if provider == "chatgpt":
                            content = raw.get("content")
                            ctype = (
                                content.get("content_type")
                                if isinstance(content, dict)
                                else None
                            )
                            check(
                                r["content_kind"] == ctype,
                                "content_kind",
                                "Content type changed",
                                rid,
                            )
                            if ctype not in (
                                "text",
                                "multimodal_text",
                                "thoughts",
                                "reasoning_recap",
                            ):
                                warn(
                                    "unknown_content",
                                    "Unrecognized content retained in raw.",
                                    rid,
                                )
                            if ctype in ("text", "multimodal_text"):
                                for j, v in enumerate(content.get("parts", [])):
                                    if isinstance(v, str):
                                        segments.append(
                                            dict(
                                                json_pointer=f"{ptr}/content/parts/{j}",
                                                text=v,
                                                kind="text",
                                            )
                                        )
                                    elif isinstance(v, dict):
                                        part_kind = v.get("content_type")
                                        if (
                                            part_kind == "audio_transcription"
                                            and isinstance(v.get("text"), str)
                                        ):
                                            segments.append(
                                                dict(
                                                    json_pointer=f"{ptr}/content/parts/{j}/text",
                                                    text=v["text"],
                                                    kind="transcription_text",
                                                )
                                            )
                                            stats["audio_transcription_segments"] += 1
                                        elif part_kind not in {
                                            "image_asset_pointer",
                                            "audio_asset_pointer",
                                            "real_time_user_audio_video_asset_pointer",
                                        }:
                                            warn(
                                                "unknown_multimodal_content",
                                                "Unrecognized multimodal block retained in raw and references.",
                                                rid,
                                            )
                                    else:
                                        warn(
                                            "unknown_part",
                                            "Non-string content part retained in raw.",
                                            rid,
                                        )
                            stats["chatgpt_content_" + str(ctype)] += 1
                        else:
                            check(
                                r["content_kind"] == "blocks",
                                "content_kind",
                                "Claude blocks marker changed",
                                rid,
                            )
                            if isinstance(raw.get("text"), str):
                                segments.append(
                                    dict(
                                        json_pointer=ptr + "/text",
                                        text=raw["text"],
                                        kind="text",
                                    )
                                )
                            blocks = raw.get("content", []) or []
                            for j, b in enumerate(blocks):
                                t = b.get("type") if isinstance(b, dict) else None
                                stats["claude_block_" + str(t)] += 1
                                if t not in (
                                    "text",
                                    "thinking",
                                    "tool_use",
                                    "tool_result",
                                    "token_budget",
                                    "flag",
                                ):
                                    warn(
                                        "unknown_content",
                                        "Unrecognized block retained in raw.",
                                        rid,
                                    )
                                if t == "text" and isinstance(b.get("text"), str):
                                    segments.append(
                                        dict(
                                            json_pointer=f"{ptr}/content/{j}/text",
                                            text=b["text"],
                                            kind="text",
                                        )
                                    )
                            for field in ("attachments", "files"):
                                for j, a in enumerate(raw.get(field, []) or []):
                                    if isinstance(a, dict) and isinstance(
                                        a.get("extracted_content"), str
                                    ):
                                        segments.append(
                                            dict(
                                                json_pointer=f"{ptr}/{field}/{j}/extracted_content",
                                                text=a["extracted_content"],
                                                kind="attachment_text",
                                            )
                                        )
                            if isinstance(raw.get("text"), str) and raw[
                                "text"
                            ] != "".join(
                                b.get("text", "")
                                for b in blocks
                                if isinstance(b, dict)
                                and b.get("type") == "text"
                                and isinstance(b.get("text"), str)
                            ):
                                stats["claude_text_differs_from_text_blocks"] += 1
                        check(
                            r["text_segments"] == segments,
                            "text_fidelity",
                            "Text projection or original-language string changed",
                            rid,
                        )
                        for seg in r["text_segments"]:
                            check(
                                raw_at(sid, seg["json_pointer"]) == seg["text"],
                                "text_pointer",
                                "Text differs from source pointer",
                                rid,
                            )
                        if not any(
                            s["text"]
                            for s in segments
                            if s["kind"] in ("text", "transcription_text")
                        ):
                            stats["messages_without_projected_text"] += 1
                        stats["role_" + role] += 1
                        message_links[rid] = (
                            cid,
                            r["node_id"],
                            r["parent_id"],
                            r["position"],
                        )
                        message_sources[rid] = (sid, ptr)
                    else:
                        counts["attachments"] += 1
                        check(
                            canonical(r["raw"]) == canonical(raw),
                            "attachment_fidelity",
                            "Original attachment reference changed",
                            rid,
                        )
                        cid = r["conversation_record_id"]
                        mid = r["message_record_id"]
                        link = message_links.get(mid)
                        check(
                            link is not None and link[0] == cid,
                            "attachment_membership",
                            "Attachment message/conversation mismatch",
                            rid,
                        )
                        msid, mptr = message_sources.get(mid, (None, ""))
                        check(
                            sid == msid and ptr.startswith(mptr + "/"),
                            "attachment_source_membership",
                            "Attachment source is outside its message",
                            rid,
                        )
                        suffix = ptr[len(mptr) :]
                        wanted_kind = (
                            "multimodal_reference"
                            if provider == "chatgpt"
                            and suffix.startswith("/content/parts/")
                            else (
                                "file_reference"
                                if provider == "claude" and suffix.startswith("/files/")
                                else "attachment"
                            )
                        )
                        check(
                            r["attachment_kind"] == wanted_kind,
                            "attachment_kind",
                            "Attachment kind changed",
                            rid,
                        )
                        # Re-check the explicit path under the configured roots, without accessing the network.
                        from .pipeline import resolve_attachment

                        a = dict(r)
                        a.update(
                            availability="unverified_reference",
                            resolved_path=None,
                            sha256=None,
                        )
                        obj = raw if isinstance(raw, dict) else {}
                        filename = obj.get("file_name", obj.get("name"))
                        check(
                            r["filename"] == filename
                            and r["original_id"]
                            == obj.get("file_id", obj.get("file_uuid", obj.get("id"))),
                            "attachment_metadata",
                            "Attachment metadata changed",
                            rid,
                        )
                        resolve_attachment(a, src)
                        check(
                            all(
                                r[k] == a[k]
                                for k in ("availability", "resolved_path", "sha256")
                            ),
                            "attachment_availability",
                            "Attachment bytes or availability changed",
                            rid,
                        )
                        stats["attachment_" + r["availability"]] += 1
                    if kind != "attachments":
                        for field in ("created_at_raw", "updated_at_raw"):
                            if r[field] is None:
                                stats["missing_" + field] += 1
                            else:
                                try:
                                    timestamp(r[field])
                                except (ValueError, OverflowError, OSError):
                                    problem(
                                        "invalid_timestamp",
                                        "Cannot interpret exported timestamp without guessing",
                                        rid,
                                    )
            counts[kind] = n
            check(
                n == spec["records"],
                "file_count",
                kind + " count differs from manifest",
            )
            check(
                seen == expected[kind],
                "source_coverage",
                f"{kind}: missing {len(expected[kind]-seen)}, unexpected {len(seen-expected[kind])} source locations",
            )
        # Graph integrity and message-to-node membership; no recursive depth assumption.
        for cid, c in convs.items():
            graph = c["graph"]
            nodes = {n["node_id"]: n for n in graph}
            roots = set(c["root_parent_ids"])
            emitted = 0
            parent_child_counts = Counter(
                n["parent_id"] for n in graph if n["parent_id"] in nodes
            )
            check(len(nodes) == len(graph), "node_collision", "Repeated node id", cid)
            if c["current_node_id"] is not None:
                check(
                    c["current_node_id"] in nodes,
                    "missing_current_node",
                    "Selected node missing",
                    cid,
                )
            for pos, n in enumerate(graph):
                nid = n["node_id"]
                p = n["parent_id"]
                children = n["children_ids"]
                mid = n["message_record_id"]
                if children is None:
                    stats["nodes_without_exported_child_lists"] += 1
                    children = []
                check(
                    p is None or p in nodes or p in roots,
                    "dangling_parent",
                    "Unresolved parent reference",
                    cid,
                )
                check(
                    len(children) == len(set(children)),
                    "duplicate_child",
                    "Repeated child link",
                    cid,
                )
                for child in children:
                    check(
                        child in nodes and nodes[child]["parent_id"] == nid,
                        "child_link",
                        "Child/parent relationship mismatch",
                        cid,
                    )
                if p in nodes and nodes[p]["children_ids"] is not None:
                    check(
                        nid in nodes[p]["children_ids"],
                        "parent_link",
                        "Parent missing child link",
                        cid,
                    )
                if mid is not None:
                    emitted += 1
                    check(
                        message_links.get(mid) == (cid, nid, p, pos),
                        "node_message_link",
                        "Message node, parent, position, or membership changed",
                        cid,
                    )
                if parent_child_counts[nid] > 1:
                    stats["branch_points"] += 1
            done = set()
            for nid in nodes:
                path = set()
                cur = nid
                while cur in nodes and cur not in done:
                    if cur in path:
                        problem("graph_cycle", "Cycle in conversation graph", cid)
                        break
                    path.add(cur)
                    cur = nodes[cur]["parent_id"]
                done.update(path)
            check(
                emitted == c["message_count"],
                "conversation_message_count",
                "Conversation message count mismatch",
                cid,
            )
            if not emitted:
                stats["empty_conversations"] += 1
            stats["graph_nodes"] += len(graph)
        for key, n in expected_counts.items():
            check(
                counts[key] == n,
                "provider_count",
                key + " does not reconcile to source census",
            )
        for key, n in inv["expected"].items():
            check(
                counts[key] == n,
                "expected_count",
                f"{key}: expected {n}, found {counts[key]}",
            )
        stats["repeated_message_ids_across_memberships"] = sum(
            n > 1 for n in original_memberships.values()
        )
        stats["source_payloads"] = len(sources)
        stats["source_locations"] = sum(len(s["locations"]) for s in sources.values())
        stats["exact_duplicate_source_locations"] = (
            stats["source_locations"] - stats["source_payloads"]
        )
        if stats["nodes_without_exported_child_lists"]:
            warn(
                "missing_child_lists",
                "Some child lists were not exported. Parent links are preserved; branch counts use explicit parent relationships.",
            )
        if stats["attachment_unverified_reference"] or stats["attachment_missing"]:
            warn(
                "attachment_gaps",
                "Some references have no verified local bytes; see availability statistics.",
            )
        if stats["repeated_message_ids_across_memberships"]:
            warn(
                "repeated_message_ids",
                "Repeated original IDs retained in each conversation/source membership; no inferred merging.",
            )
        if stats["missing_created_at_raw"]:
            warn("missing_creation_times", "Missing creation times retained as null.")
        verify_sources(inv)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        problem(
            "validation_exception",
            f"{type(e).__name__}: validation could not complete; inspect source/schema or file availability. "
            + (str(e) if isinstance(e, FormatError) else ""),
        )
    report["counts"] = dict(sorted(counts.items()))
    report["statistics"] = dict(sorted(stats.items()))
    report["status"] = "passed" if not errors else "failed"
    return report
