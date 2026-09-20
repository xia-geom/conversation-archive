"""Project ChatGPT's exported graph without flattening or rewriting it."""

from ..model import base, FormatError, record_id, pointer_token, require_id, warning

KNOWN = {"text", "multimodal_text", "thoughts", "reasoning_recap"}


def normalize(conversation, source, index):
    if not isinstance(conversation, dict):
        raise FormatError("ChatGPT conversation must be an object")
    cid = require_id(
        conversation.get("id") or conversation.get("conversation_id"), "conversation id"
    )
    cp = f"/{index}"
    conv = base("conversation", source, cp)
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        raise FormatError("ChatGPT mapping must be an object")
    conv.update(
        original_id=cid,
        title=conversation.get("title"),
        created_at_raw=conversation.get("create_time"),
        updated_at_raw=conversation.get("update_time"),
        current_node_id=conversation.get("current_node"),
        root_parent_ids=[],
        raw_metadata={k: v for k, v in conversation.items() if k != "mapping"},
    )
    messages, attachments, issues, graph = [], [], [], []
    for position, (nid, node) in enumerate(mapping.items()):
        require_id(nid, "node id")
        if not isinstance(node, dict) or (
            node.get("children") is not None and not isinstance(node["children"], list)
        ):
            raise FormatError("Invalid ChatGPT graph node")
        raw = node.get("message")
        ptr = f"{cp}/mapping/{pointer_token(nid)}/message"
        graph.append(
            dict(
                node_id=nid,
                parent_id=node.get("parent"),
                children_ids=node.get("children"),
                message_record_id=(
                    record_id("message", source["source_id"], ptr)
                    if raw is not None
                    else None
                ),
                node_fields={k: v for k, v in node.items() if k != "message"},
            )
        )
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise FormatError("ChatGPT message must be an object or null")
        mid = require_id(raw.get("id"), "message id")
        author = raw.get("author", {})
        if not isinstance(author, dict):
            raise FormatError("ChatGPT author must be an object")
        role = author.get("role")
        content = raw.get("content")
        kind = content.get("content_type") if isinstance(content, dict) else None
        msg = base("message", source, ptr)
        msg.update(
            conversation_record_id=conv["record_id"],
            conversation_original_id=cid,
            original_id=mid,
            node_id=nid,
            parent_id=node.get("parent"),
            position=position,
            role=role if role in {"user", "assistant", "system", "tool"} else "unknown",
            role_raw=role,
            created_at_raw=raw.get("create_time"),
            updated_at_raw=raw.get("update_time"),
            content_kind=kind,
            raw=raw,
            text_segments=[],
        )
        if kind not in KNOWN:
            issues.append(
                warning(
                    "unknown_content",
                    msg["record_id"],
                    "Unrecognized content retained in raw.",
                )
            )
        if isinstance(content, dict) and kind in {"text", "multimodal_text"}:
            parts = content.get("parts", [])
            if not isinstance(parts, list):
                raise FormatError("ChatGPT content parts must be a list")
            for i, part in enumerate(parts):
                pp = f"{ptr}/content/parts/{i}"
                if isinstance(part, str):
                    msg["text_segments"].append(
                        dict(json_pointer=pp, text=part, kind="text")
                    )
                elif isinstance(part, dict):
                    part_kind = part.get("content_type")
                    if part_kind == "audio_transcription" and isinstance(
                        part.get("text"), str
                    ):
                        msg["text_segments"].append(
                            dict(
                                json_pointer=pp + "/text",
                                text=part["text"],
                                kind="transcription_text",
                            )
                        )
                    else:
                        attachments.append(
                            attachment(
                                source, pp, part, conv, msg, "multimodal_reference"
                            )
                        )
                        if part_kind not in {
                            "image_asset_pointer",
                            "audio_asset_pointer",
                            "real_time_user_audio_video_asset_pointer",
                        }:
                            issues.append(
                                warning(
                                    "unknown_multimodal_content",
                                    msg["record_id"],
                                    "Unrecognized multimodal block retained in raw and references.",
                                )
                            )
                else:
                    issues.append(
                        warning(
                            "unknown_part",
                            msg["record_id"],
                            "Non-string content part retained in raw.",
                        )
                    )
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            raise FormatError("ChatGPT metadata must be an object")
        items = metadata.get("attachments", [])
        if items is None:
            items = []
        if not isinstance(items, list):
            raise FormatError("ChatGPT attachments must be a list")
        for i, item in enumerate(items):
            attachments.append(
                attachment(
                    source,
                    f"{ptr}/metadata/attachments/{i}",
                    item,
                    conv,
                    msg,
                    "attachment",
                )
            )
        messages.append(msg)
    conv.update(graph=graph, message_count=len(messages))
    return conv, messages, attachments, issues


def attachment(source, ptr, raw, conv, msg, kind):
    a = base("attachment", source, ptr)
    obj = raw if isinstance(raw, dict) else {}
    a.update(
        conversation_record_id=conv["record_id"],
        message_record_id=msg["record_id"],
        attachment_kind=kind,
        raw=raw,
        filename=obj.get("file_name", obj.get("name")),
        original_id=obj.get("file_id", obj.get("file_uuid", obj.get("id"))),
        availability="unverified_reference",
        resolved_path=None,
        sha256=None,
    )
    return a
