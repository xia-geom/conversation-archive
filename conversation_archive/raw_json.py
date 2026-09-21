"""Lossless JSON segmentation plus conservative ChatGPT occurrence indexing.

Bytes are evidence; canonical hashes are only comparison keys. No text extraction,
semantic identity inference, attachment download, or archive/master update occurs.
"""
from __future__ import annotations

import hashlib
import json
import re

from .inventory import strict_loads
from .model import FormatError

VERSION = "1.0"
DECODER = json.JSONDecoder()
SPACE = re.compile(r"[ \t\r\n]*")


class RawStoreError(ValueError):
    """Refuse incomplete, incompatible or unsafe raw-store operations."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    # ASCII escaping also permits exported lone surrogate escape sequences.
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def fingerprint(value) -> str:
    return digest(encoded(value))


def _members(text: str, start: int):
    """Yield immediate JSON value spans; full strict parsing happens first."""
    is_object = text[start] == "{"
    close = "}" if is_object else "]"
    at, index = start + 1, 0
    while True:
        at = SPACE.match(text, at).end()
        if text[at] == close:
            return
        if is_object:
            key, at = DECODER.raw_decode(text, at)
            at = SPACE.match(text, at).end() + 1  # colon, checked by strict_loads
            at = SPACE.match(text, at).end()
        else:
            key = index
        _, end = DECODER.raw_decode(text, at)
        yield key, at, end
        at = SPACE.match(text, end).end()
        if text[at] == close:
            return
        at += 1  # comma
        index += 1


def _identifier(value):
    return value if isinstance(value, str) and value.strip() else None


def _pointer(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def analyze(payload: bytes):
    """Return an index/part recipe and unique exact-byte blobs.

    Structural bounds separate message values from their node envelopes. Identical
    message bytes can be reused even when children or conversation order change.
    Formatting changes are retained as new bytes but do not imply new messages.
    """
    try:
        data = strict_loads(payload)
        text = payload.decode("utf-8")
        if not isinstance(data, list):
            raise RawStoreError("ChatGPT export must be a JSON array")
        start = SPACE.match(text, 1 if text.startswith("\ufeff") else 0).end()
        cuts = {0, len(text)}
        occurrences = []
        for index, begin, end in _members(text, start):
            conversation = data[index]
            if not isinstance(conversation, dict) or not isinstance(conversation.get("mapping"), dict):
                raise RawStoreError("Each conversation requires an object-valued mapping")
            cuts.update((begin, end))
            fields = {k: (s, e) for k, s, e in _members(text, begin)}
            ids = [_identifier(conversation.get(k)) for k in ("id", "conversation_id")]
            issues = []
            cid = ids[0] or ids[1]
            if cid is None:
                issues.append("missing_conversation_id")
            elif all(ids) and ids[0] != ids[1]:
                issues.append("conflicting_conversation_ids")
                cid = None
            nodes = []
            for nid, ns, ne in _members(text, fields["mapping"][0]):
                cuts.update((ns, ne))
                node = conversation["mapping"][nid]
                if not isinstance(node, dict):
                    raise RawStoreError("Graph nodes must be JSON objects")
                nf = {k: (s, e) for k, s, e in _members(text, ns)}
                raw = node.get("message")
                if raw is not None and not isinstance(raw, dict):
                    raise RawStoreError("A message must be an object or null")
                if "message" in nf:
                    cuts.update(nf["message"])
                mid = _identifier(raw.get("id")) if raw is not None else None
                node_issues = []
                if not _identifier(nid) or (node.get("id") is not None and node["id"] != nid):
                    node_issues.append("ambiguous_node_id")
                if raw is not None and mid is None:
                    node_issues.append("missing_message_id")
                parent = node.get("parent")
                if parent is not None and not isinstance(parent, str):
                    node_issues.append("invalid_parent_reference")
                elif parent is not None and parent not in conversation["mapping"]:
                    node_issues.append("unavailable_parent_context")
                children = node.get("children")
                if children is not None and (not isinstance(children, list) or any(
                        not isinstance(child, str) or child not in conversation["mapping"] for child in children)):
                    node_issues.append("invalid_children_reference")
                nodes.append({"node_id": nid, "message_id": mid,
                              "parent_id": parent if isinstance(parent, str) else None,
                              "message_sha256": fingerprint(raw) if raw is not None else None,
                              "context_sha256": fingerprint({k: v for k, v in node.items() if k != "message"}),
                              "message_pointer": f"/{index}/mapping/{_pointer(nid)}/message" if "message" in nf else None,
                              "message_char_span": list(nf["message"]) if "message" in nf else None,
                              "issues": node_issues})
            by_id = {node["node_id"]: node for node in nodes}
            done = set()
            for nid in by_id:
                trail, positions, current = [], {}, nid
                while current in by_id and current not in done and current not in positions:
                    positions[current] = len(trail)
                    trail.append(current)
                    current = by_id[current]["parent_id"]
                if current in positions:
                    for member in trail[positions[current]:]:
                        by_id[member]["issues"].append("cyclic_parent_context")
                done.update(trail)
            occurrences.append({"conversation_id": cid, "json_pointer": f"/{index}",
                                "char_span": [begin, end], "issues": issues,
                                "metadata_sha256": fingerprint({k: v for k, v in conversation.items() if k != "mapping"}),
                                "nodes": sorted(nodes, key=lambda n: n["node_id"])})
        parts, blobs, byte_positions = [], {}, {0: 0}
        points = sorted(cuts)
        cursor = 0
        for left, right in zip(points, points[1:]):
            value = text[left:right].encode("utf-8")
            if not value:
                continue
            sha = digest(value)
            parts.append({"sha256": sha, "bytes": len(value)})
            blobs[sha] = value
            byte_positions[left] = cursor
            cursor += len(value)
            byte_positions[right] = cursor
        for occurrence in occurrences:
            occurrence["byte_span"] = [byte_positions[x] for x in occurrence["char_span"]]
            for node in occurrence["nodes"]:
                span = node["message_char_span"]
                node["message_byte_span"] = [byte_positions[x] for x in span] if span else None
        return {"sha256": digest(payload), "bytes": len(payload), "parts": parts,
                "conversations": occurrences}, blobs
    except (FormatError, UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise RawStoreError("Invalid, excessively nested, or unsupported UTF-8 JSON") from exc
