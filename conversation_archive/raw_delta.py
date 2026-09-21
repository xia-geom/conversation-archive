"""Conservative cross-export comparison, not a review or extraction checkpoint."""
from __future__ import annotations

from collections import Counter, defaultdict, deque

from .raw_json import RawStoreError, fingerprint


def _groups(manifest):
    groups, unknown = defaultdict(list), []
    for payload in manifest["payloads"]:
        for conversation in payload["conversations"]:
            record = {**conversation, "payload_sha256": payload["sha256"]}
            if record["conversation_id"] is None:
                unknown.append(record)
            else:
                groups[record["conversation_id"]].append(record)
    return groups, unknown


def _location(conversation, node=None):
    value = {"payload_sha256": conversation["payload_sha256"],
             "json_pointer": conversation["json_pointer"], "byte_span": conversation["byte_span"]}
    if node is not None:
        value.update(json_pointer=node["message_pointer"], byte_span=node["message_byte_span"],
                     message_sha256=node["message_sha256"], message_id=node["message_id"])
    return value


def compare(store, before: str, after: str):
    from .raw_store import load_export
    old_manifest, new_manifest = load_export(store, before), load_export(store, after)
    if old_manifest["namespace"] != new_manifest["namespace"]:
        raise RawStoreError("Cannot compare different account namespaces")
    old, unknown_old = _groups(old_manifest)
    new, unknown_new = _groups(new_manifest)
    changes, ambiguities = [], []
    counts = Counter({"new_messages": 0, "changed_messages": 0, "unchanged_messages": 0,
                      "not_present_messages": 0, "context_changed_messages": 0,
                      "new_conversations": 0, "not_present_conversations": 0,
                      "conversation_metadata_changed": 0, "ambiguous_conversations": 0})
    for side, unknown in (("before", unknown_old), ("after", unknown_new)):
        for c in unknown:
            ambiguities.append({"side": side, "issues": c["issues"], "source": _location(c)})
            counts["ambiguous_conversations"] += 1
    for cid in sorted(set(old) | set(new)):
        left, right = old.get(cid, []), new.get(cid, [])
        if len(left) > 1 or len(right) > 1:
            ambiguities.append({"conversation_id": cid, "issues": ["duplicate_conversation_id"],
                                "before": [_location(c) for c in left], "after": [_location(c) for c in right]})
            counts["ambiguous_conversations"] += 1
            continue
        a, b = (left[0] if left else None), (right[0] if right else None)
        if a is None:
            counts["new_conversations"] += 1
        if b is None:
            counts["not_present_conversations"] += 1
            changes.append({"kind": "conversation_not_present", "conversation_id": cid, "before": _location(a)})
        if a and b and a["metadata_sha256"] != b["metadata_sha256"]:
            counts["conversation_metadata_changed"] += 1
            changes.append({"kind": "conversation_metadata_changed", "conversation_id": cid,
                            "before": _location(a), "after": _location(b),
                            "note": "Includes title, project membership, timestamps or branch selection; inspect before reusing downstream review."})
        nodes_a = {n["node_id"]: n for n in a["nodes"]} if a else {}
        nodes_b = {n["node_id"]: n for n in b["nodes"]} if b else {}
        node_changes, dirty = {}, set()
        for nid in sorted(set(nodes_a) | set(nodes_b)):
            x, y = nodes_a.get(nid), nodes_b.get(nid)
            issues = sorted(set((x or {}).get("issues", []) + (y or {}).get("issues", [])))
            if issues:
                ambiguities.append({"conversation_id": cid, "node_id": nid, "issues": issues,
                                    "before": _location(a, x) if x else None,
                                    "after": _location(b, y) if y else None})
                dirty.add(nid)
                continue
            prev, curr = (x or {}).get("message_sha256"), (y or {}).get("message_sha256")
            status = None
            if curr is not None:
                if prev is None:
                    status = "new_messages"
                elif prev != curr:
                    status = "changed_messages"
                elif x["context_sha256"] != y["context_sha256"]:
                    status = "context_changed_messages"
                else:
                    status = "unchanged_messages"
            elif prev is not None:
                status = "not_present_messages"
            if status:
                node_changes[nid] = status
            if x is None or y is None or prev != curr or x["context_sha256"] != y["context_sha256"]:
                dirty.add(nid)
        # An unchanged reply can have different meaning after an ancestor edit.
        children = defaultdict(set)
        for nodes in (nodes_a, nodes_b):
            for nid, node in nodes.items():
                if node["parent_id"] is not None:
                    children[node["parent_id"]].add(nid)
        queue, visited = deque(dirty), set(dirty)
        while queue:
            nid = queue.popleft()
            for child in children[nid]:
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
                if node_changes.get(child) == "unchanged_messages":
                    node_changes[child] = "context_changed_messages"
        for nid, status in sorted(node_changes.items()):
            counts[status] += 1
            if status == "unchanged_messages":
                continue
            changes.append({"kind": status, "conversation_id": cid, "node_id": nid,
                            "logical_key": fingerprint(["chatgpt", new_manifest["namespace"], cid, nid]),
                            "before": _location(a, nodes_a[nid]) if nid in nodes_a else None,
                            "after": _location(b, nodes_b[nid]) if nid in nodes_b else None})
    return {"version": "1.0", "before_export_id": before, "after_export_id": after,
            "counts": dict(counts), "changes": changes, "ambiguities": ambiguities,
            "deletions_applied": 0, "model_calls": 0, "review_coverage_claimed": False,
            "limitations": ["Not-present does not mean deleted; export completeness is unknown.",
                            "Changed graph/context may require previously unchanged text to be reviewed.",
                            "Exact parsed-JSON comparison only; no fuzzy identity or automatic rule migration.",
                            "No extraction dispatch, accepted-entry update or historical-summary coverage claim."]}
