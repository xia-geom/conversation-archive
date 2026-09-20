"""Keep Claude's parent links and both original text representations."""

from ..model import base, FormatError, require_id, warning
from .chatgpt import attachment

ROOT = "00000000-0000-4000-8000-000000000000"
KNOWN = {"text", "thinking", "tool_use", "tool_result", "token_budget", "flag"}


def normalize(conversation, source, index):
    if not isinstance(conversation, dict):
        raise FormatError("Claude conversation must be an object")
    cid = require_id(conversation.get("uuid"), "conversation uuid")
    cp = f"/{index}"
    records = conversation.get("chat_messages")
    if not isinstance(records, list):
        raise FormatError("Claude chat_messages must be a list")
    conv = base("conversation", source, cp)
    conv.update(
        original_id=cid,
        title=conversation.get("name"),
        created_at_raw=conversation.get("created_at"),
        updated_at_raw=conversation.get("updated_at"),
        current_node_id=None,
        raw_metadata={k: v for k, v in conversation.items() if k != "chat_messages"},
    )
    messages, attachments, issues, graph = [], [], [], []
    for i, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise FormatError("Claude message must be an object")
        mid = require_id(raw.get("uuid"), "message uuid")
        ptr = f"{cp}/chat_messages/{i}"
        role = raw.get("sender")
        parent = raw.get("parent_message_uuid")
        msg = base("message", source, ptr)
        msg.update(
            conversation_record_id=conv["record_id"],
            conversation_original_id=cid,
            original_id=mid,
            node_id=mid,
            parent_id=parent,
            position=i,
            role={"human": "user", "assistant": "assistant"}.get(role, "unknown"),
            role_raw=role,
            created_at_raw=raw.get("created_at"),
            updated_at_raw=raw.get("updated_at"),
            content_kind="blocks",
            raw=raw,
            text_segments=[],
        )
        if isinstance(raw.get("text"), str):
            msg["text_segments"].append(
                dict(json_pointer=ptr + "/text", text=raw["text"], kind="text")
            )
        blocks = raw.get("content", [])
        if blocks is None:
            blocks = []
        if not isinstance(blocks, list):
            raise FormatError("Claude content must be a list")
        for j, b in enumerate(blocks):
            if not isinstance(b, dict) or b.get("type") not in KNOWN:
                issues.append(
                    warning(
                        "unknown_content",
                        msg["record_id"],
                        "Unrecognized block retained in raw.",
                    )
                )
            if (
                isinstance(b, dict)
                and b.get("type") == "text"
                and isinstance(b.get("text"), str)
            ):
                msg["text_segments"].append(
                    dict(
                        json_pointer=f"{ptr}/content/{j}/text",
                        text=b["text"],
                        kind="text",
                    )
                )
        for field, kind in [("attachments", "attachment"), ("files", "file_reference")]:
            refs = raw.get(field, [])
            if refs is None:
                refs = []
            if not isinstance(refs, list):
                raise FormatError("Claude attachment references must be lists")
            for j, item in enumerate(refs):
                ap = f"{ptr}/{field}/{j}"
                attachments.append(attachment(source, ap, item, conv, msg, kind))
                if isinstance(item, dict) and isinstance(
                    item.get("extracted_content"), str
                ):
                    msg["text_segments"].append(
                        dict(
                            json_pointer=ap + "/extracted_content",
                            text=item["extracted_content"],
                            kind="attachment_text",
                        )
                    )
        graph.append(
            dict(
                node_id=mid,
                parent_id=parent,
                children_ids=[],
                message_record_id=msg["record_id"],
                node_fields={},
            )
        )
        messages.append(msg)
    by_id = {n["node_id"]: n for n in graph}
    if len(by_id) != len(graph):
        raise FormatError("Duplicate Claude message uuid within a conversation")
    for n in graph:
        if n["parent_id"] in by_id:
            by_id[n["parent_id"]]["children_ids"].append(n["node_id"])
    conv.update(
        graph=graph,
        root_parent_ids=[ROOT] if any(n["parent_id"] == ROOT for n in graph) else [],
        message_count=len(messages),
    )
    return conv, messages, attachments, issues
