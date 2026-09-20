"""Resumable evidence review over a frozen, validated conversation dataset.

Reading packets is a human/agent action. This module never infers that a packet
was read, or that a personal account is true, merely because it was generated.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .inventory import canonical, sha_file, strict_loads, verify_sources
from .model import FormatError
from .pipeline import validate as validate_dataset

REVIEW_VERSION = "1.1"
OUTCOMES = {
    "already_represented",
    "complementary_detail",
    "distinct_episode",
    "uncertain_overlap",
    "excluded",
}
FILES = (
    "emotion_master.md",
    "correction_review_report.md",
    "corrections_before_after.md",
)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load(path):
    return strict_loads(Path(path).read_bytes())


def atomic_json(path, value):
    atomic_text(
        Path(path),
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def original_record(dataset, kind, offset):
    with (Path(dataset) / (kind + ".jsonl")).open("rb") as f:
        f.seek(offset)
        return strict_loads(f.readline())


def iter_records(path):
    with Path(path).open("rb") as f:
        while True:
            offset = f.tell()
            line = f.readline()
            if not line:
                break
            yield offset, strict_loads(line)


def graph_order(conversation):
    """Parent-first DFS. Sibling order is exported position, not event chronology."""
    nodes = conversation["graph"]
    by_id = {n["node_id"]: n for n in nodes}
    children = defaultdict(list)
    roots = []
    for n in nodes:
        if n["parent_id"] in by_id:
            children[n["parent_id"]].append(n["node_id"])
        else:
            roots.append(n["node_id"])
    order = []
    seen = set()
    stack = list(reversed(roots))
    while stack:
        nid = stack.pop()
        if nid in seen:
            raise FormatError("Graph cycle or repeated node")
        seen.add(nid)
        order.append(by_id[nid])
        stack.extend(reversed(children[nid]))
    if len(seen) != len(nodes):
        raise FormatError("Unreachable graph nodes")
    return order


def units(message):
    result = [
        dict(
            segment_index=i,
            json_pointer=s["json_pointer"],
            kind=s["kind"],
            text=s["text"],
        )
        for i, s in enumerate(message["text_segments"])
    ]
    content = message["raw"].get("content")
    pointer = message["provenance"]["json_pointer"] + "/content"
    if message["role"] == "assistant" and message["content_kind"] in (
        "thoughts",
        "reasoning_recap",
    ):
        return [
            dict(
                segment_index=-1,
                json_pointer=pointer,
                kind="internal_assistant_content",
                text="",
            )
        ]
    if (
        message["provider"] == "chatgpt"
        and isinstance(content, dict)
        and message["content_kind"] in ("text", "multimodal_text")
    ):
        for i, part in enumerate(content.get("parts", [])):
            if isinstance(part, str) or (
                isinstance(part, dict)
                and part.get("content_type") == "audio_transcription"
                and isinstance(part.get("text"), str)
            ):
                continue
            result.append(
                dict(
                    segment_index=-2 - i,
                    json_pointer=pointer + f"/parts/{i}",
                    kind="multimodal_or_unrecognized_content",
                    text=json.dumps(part, ensure_ascii=False, sort_keys=True),
                )
            )
    elif message["provider"] == "claude" and isinstance(content, list):
        for i, block in enumerate(content):
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                continue
            internal = isinstance(block, dict) and block.get("type") in (
                "thinking",
                "token_budget",
                "flag",
            )
            result.append(
                dict(
                    segment_index=-2 - i,
                    json_pointer=pointer + f"/{i}",
                    kind=(
                        "internal_assistant_content"
                        if internal
                        else "unprojected_content"
                    ),
                    text=(
                        ""
                        if internal
                        else json.dumps(block, ensure_ascii=False, sort_keys=True)
                    ),
                )
            )
    if not result:
        result = [
            dict(
                segment_index=-1,
                json_pointer=pointer,
                kind="unprojected_content",
                text=json.dumps(content, ensure_ascii=False, sort_keys=True),
            )
        ]
    return result


def time_key(value):
    if value is None:
        return (0, 0)
    if isinstance(value, (int, float)):
        return (1, value)
    return (1, datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def prepare(
    dataset,
    master,
    run,
    provider="chatgpt",
    project_id=None,
    membership=None,
    max_chars=40000,
):
    dataset = Path(dataset).resolve()
    master = Path(master).resolve()
    run = Path(run).resolve()
    if max_chars < 1:
        raise FormatError("max_chars must be positive")
    if bool(project_id) == bool(membership):
        raise FormatError("Specify project_id or an observed membership file, not both")
    if project_id and provider != "chatgpt":
        raise FormatError("Claude membership must be supplied as observed IDs")
    if run.exists() and any(run.iterdir()):
        raise FormatError("Run directory must be new or empty")
    if run.is_relative_to(dataset) or dataset.is_relative_to(run):
        raise FormatError("Review run must be separate from the dataset")
    report = validate_dataset(dataset)
    if report["errors"]:
        raise FormatError("Input dataset failed validation")
    membership_data = load(membership) if membership else None
    if membership_data and not all(
        membership_data.get(k)
        for k in ("conversation_ids", "observed_at", "evidence", "project_name")
    ):
        raise FormatError(
            "Membership requires IDs, observed_at, evidence, and project_name"
        )
    selected = []
    for offset, c in iter_records(dataset / "conversations.jsonl"):
        if c["provider"] != provider:
            continue
        match = (
            c["raw_metadata"].get("conversation_template_id") == project_id
            if project_id
            else c["original_id"] in membership_data["conversation_ids"]
        )
        if match:
            selected.append((offset, c))
    if not selected:
        raise FormatError("Scope selects no conversations")
    selected.sort(
        key=lambda x: (
            time_key(x[1]["created_at_raw"]),
            x[1]["original_id"],
            x[1]["record_id"],
        )
    )
    selected_ids = {c["record_id"] for _, c in selected}
    messages = {}
    attachments = defaultdict(list)
    for offset, m in iter_records(dataset / "messages.jsonl"):
        if m["conversation_record_id"] in selected_ids:
            messages[m["record_id"]] = (offset, m)
    for _, a in iter_records(dataset / "attachments.jsonl"):
        if a["conversation_record_id"] in selected_ids:
            attachments[a["message_record_id"]].append(
                {
                    k: a[k]
                    for k in (
                        "record_id",
                        "attachment_kind",
                        "availability",
                        "provenance",
                    )
                }
            )
    conversations = []
    packets = []
    message_index = {}
    for rank, (offset, c) in enumerate(selected, 1):
        order = graph_order(c)
        parts = []
        chars = 0
        number = 1

        def flush():
            nonlocal parts, chars, number
            if parts:
                packets.append(
                    dict(
                        packet_id=f"P{rank:04}-{number:04}",
                        conversation_record_id=c["record_id"],
                        pieces=parts,
                        text_characters=chars,
                    )
                )
                parts = []
                chars = 0
                number += 1

        for node in order:
            mid = node["message_record_id"]
            if mid is None:
                continue
            mo, m = messages[mid]
            message_index[mid] = dict(
                offset=mo,
                conversation_record_id=c["record_id"],
                original_id=m["original_id"],
                provenance=m["provenance"],
                role=m["role"],
                content_kind=m["content_kind"],
                attachments=attachments[mid],
            )
            for unit in units(m):
                text = unit["text"]
                spans = [
                    (i, min(i + max_chars, len(text)))
                    for i in range(0, len(text), max_chars)
                ] or [(0, 0)]
                for start, end in spans:
                    size = end - start
                    if chars + size > max_chars:
                        flush()
                    piece = dict(
                        message_record_id=mid,
                        segment_index=unit["segment_index"],
                        kind=unit["kind"],
                        json_pointer=unit["json_pointer"],
                        start=start,
                        end=end,
                        text_sha256=digest(text[start:end]),
                    )
                    piece["piece_id"] = "piece:" + digest(canonical(piece))
                    parts.append(piece)
                    chars += size
        if not any(n["message_record_id"] for n in order):
            piece = dict(
                message_record_id=None,
                segment_index=-1,
                kind="empty_conversation",
                json_pointer=c["provenance"]["json_pointer"],
                start=0,
                end=0,
                text_sha256=digest(""),
            )
            piece["piece_id"] = "piece:" + digest(c["record_id"] + canonical(piece))
            parts.append(piece)
        flush()
        conversations.append(
            dict(
                rank=rank,
                record_id=c["record_id"],
                original_id=c["original_id"],
                title=c["title"],
                created_at_raw=c["created_at_raw"],
                provenance=c["provenance"],
                offset=offset,
                message_count=c["message_count"],
                graph=c["graph"],
                current_node_id=c["current_node_id"],
            )
        )
    from .master_validation import validate_master

    base = validate_master(master.read_text())
    if base["errors"]:
        raise FormatError("Master baseline failed: " + str(base["errors"]))
    frozen = load(dataset / "manifest.json")
    inv = dict(
        review_version=REVIEW_VERSION,
        created_at=stamp(),
        dataset=str(dataset),
        master=str(master),
        dataset_hashes={
            n: sha_file(dataset / n)
            for n in [
                "manifest.json",
                "conversations.jsonl",
                "messages.jsonl",
                "attachments.jsonl",
            ]
        },
        source_inventory=frozen["inventory"],
        master_initial_sha256=sha_file(master),
        selection=dict(
            provider=provider,
            project_id=project_id,
            membership=membership_data,
            missing_conversation_ids=(
                sorted(
                    set(membership_data["conversation_ids"])
                    - {c["original_id"] for _, c in selected}
                )
                if membership_data
                else []
            ),
        ),
        max_chars=max_chars,
        conversations=conversations,
        messages=message_index,
        packets=packets,
    )
    run.mkdir(parents=True, exist_ok=True)
    atomic_json(run / "inventory.json", inv)
    return status(run)


def checked_inventory(run):
    inv = load(Path(run) / "inventory.json")
    if inv["review_version"] != REVIEW_VERSION:
        raise FormatError("Unsupported review version")
    for name, h in inv["dataset_hashes"].items():
        if sha_file(Path(inv["dataset"]) / name) != h:
            raise FormatError("Frozen dataset changed: " + name)
    verify_sources(inv["source_inventory"])
    return inv


def decisions(run):
    docs = [load(p) for p in sorted((Path(run) / "decisions").glob("*.json"))]
    superseded = {d["supersedes"] for d in docs if d.get("supersedes")}
    return [d for d in docs if d["decision_id"] not in superseded]


def coverage(run):
    result = {}
    for d in decisions(run):
        for item in d["coverage"]:
            if item["piece_id"] in result:
                raise FormatError("Overlapping active review decisions")
            result[item["piece_id"]] = {**item, "decision_id": d["decision_id"]}
    return result


def packet(run, packet_id=None, conversation_id=None):
    inv = checked_inventory(run)
    covered = coverage(run)
    choices = [
        p
        for p in inv["packets"]
        if (not packet_id or p["packet_id"] == packet_id)
        and (
            not conversation_id
            or p["conversation_record_id"] == conversation_id
            or next(
                c
                for c in inv["conversations"]
                if c["record_id"] == p["conversation_record_id"]
            )["original_id"]
            == conversation_id
        )
    ]
    if packet_id:
        chosen = next(iter(choices), None)
    else:
        chosen = next(
            (
                p
                for p in choices
                if any(x["piece_id"] not in covered for x in p["pieces"])
            ),
            None,
        )
    if chosen is None:
        return {"status": "no_pending_packet"}
    c = next(
        c
        for c in inv["conversations"]
        if c["record_id"] == chosen["conversation_record_id"]
    )
    pieces = []
    cache = {}
    for piece in chosen["pieces"]:
        mid = piece["message_record_id"]
        if mid is None:
            pieces.append(
                {
                    **piece,
                    "text": "",
                    "role": None,
                    "provenance": c["provenance"],
                    "attachments": [],
                    "already_covered": piece["piece_id"] in covered,
                }
            )
            continue
        if mid not in cache:
            cache[mid] = original_record(
                inv["dataset"], "messages", inv["messages"][mid]["offset"]
            )
        m = cache[mid]
        u = next(u for u in units(m) if u["segment_index"] == piece["segment_index"])
        text = u["text"][piece["start"] : piece["end"]]
        if digest(text) != piece["text_sha256"]:
            raise FormatError("Piece changed")
        possible_admin = any(
            s in text.casefold()
            for s in (
                "extraction cutoff",
                "extract the emotionally",
                "master entry ids",
                "downloadable markdown",
                "source conversation",
            )
        )
        pieces.append(
            {
                **piece,
                "text": text,
                "role": m["role"],
                "original_message_id": m["original_id"],
                "parent_id": m["parent_id"],
                "node_id": m["node_id"],
                "position": m["position"],
                "created_at_raw": m["created_at_raw"],
                "provenance": m["provenance"],
                "content_kind": m["content_kind"],
                "attachments": inv["messages"][mid]["attachments"],
                "possible_administrative": possible_admin,
                "already_covered": piece["piece_id"] in covered,
            }
        )
    return dict(
        packet_id=chosen["packet_id"],
        conversation=c,
        pieces=pieces,
        range_convention="Python Unicode character offsets, start inclusive/end exclusive within the identified text segment; Negative segment indices mean rendered unprojected or structured content, not an exported text-segment index. Internal-content placeholders do not establish substantive reading.",
    )


def quote_check(inv, q):
    mid = q["message_record_id"]
    if mid not in inv["messages"]:
        raise FormatError("Finding references message outside review scope")
    m = original_record(inv["dataset"], "messages", inv["messages"][mid]["offset"])
    if q["segment_index"] < 0:
        raise FormatError("Accepted narrative requires an exact exported text segment")
    seg = m["text_segments"][q["segment_index"]]
    if (
        not (0 <= q["start"] < q["end"] <= len(seg["text"]))
        or seg["text"][q["start"] : q["end"]] != q["text"]
    ):
        raise FormatError("Finding quotation does not match original segment")


def record(run, document):
    run = Path(run)
    inv = checked_inventory(run)
    doc = load(document) if not isinstance(document, dict) else document
    did = doc.get("decision_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", did):
        raise FormatError("Unsafe or missing decision ID")
    target = run / "decisions" / f"{did}.json"
    if target.exists():
        if load(target) != doc:
            raise FormatError("Decision ID exists with different content")
        return {"status": "already_recorded", "decision_id": did}
    if not doc.get("reviewer") or not doc.get("reviewed_at"):
        raise FormatError("Record reviewer and review date")
    existing = coverage(run)
    all_pieces = {
        p["piece_id"]: p for packet in inv["packets"] for p in packet["pieces"]
    }
    if not doc.get("coverage"):
        raise FormatError("Empty review coverage")
    active = decisions(run)
    old = next((d for d in active if d["decision_id"] == doc.get("supersedes")), None)
    if doc.get("supersedes") and not old:
        raise FormatError("Superseded decision not active")
    if old:
        if any(
            old["decision_id"] in j["decision_ids"]
            for j in journals(run)
            if j.get("status") in ("installing", "complete")
        ):
            raise FormatError(
                "Cannot supersede a decision in an installation journal; recover or record a subsequent correction instead"
            )
        existing = {
            k: v for k, v in existing.items() if v["decision_id"] != old["decision_id"]
        }
    findings = doc.get("findings", [])
    fids = {f["finding_id"] for f in findings}
    if len(fids) != len(findings):
        raise FormatError("Duplicate finding IDs")
    seen = set()
    for item in doc["coverage"]:
        pid = item["piece_id"]
        if pid not in all_pieces or pid in seen or pid in existing:
            raise FormatError("Unknown, repeated, or already reviewed piece")
        seen.add(pid)
        if item["outcome"] not in OUTCOMES or not item.get("reason"):
            raise FormatError("Coverage requires an outcome and reason")
        if not set(item.get("finding_ids", [])).issubset(fids):
            raise FormatError("Unknown linked finding")
        if item["outcome"] in (
            "complementary_detail",
            "distinct_episode",
            "uncertain_overlap",
        ) and not item.get("finding_ids"):
            raise FormatError("Material coverage requires a linked finding")
    linked = {fid for item in doc["coverage"] for fid in item.get("finding_ids", [])}
    if fids - linked:
        raise FormatError("Finding lacks a covered piece link")
    for f in findings:
        if f["outcome"] not in OUTCOMES or not f.get("reason"):
            raise FormatError("Finding requires outcome and reason")
        if f["outcome"] in (
            "complementary_detail",
            "distinct_episode",
            "uncertain_overlap",
        ) and not f.get("quotes"):
            raise FormatError("Material finding needs original quotations")
        if not f.get("attribution"):
            raise FormatError("Finding attribution is required")
        for q in f.get("quotes", []):
            quote_check(inv, q)
            matching = [
                p
                for p in all_pieces.values()
                if p["message_record_id"] == q["message_record_id"]
                and p["segment_index"] == q["segment_index"]
                and p["start"] < q["end"]
                and p["end"] > q["start"]
            ]
            if not matching or any(
                p["piece_id"] not in seen and p["piece_id"] not in existing
                for p in matching
            ):
                raise FormatError(
                    "Quotation includes text without explicit review coverage"
                )
    atomic_json(target, doc)
    return {"status": "recorded", "decision_id": did, "covered_pieces": len(seen)}


def journals(run):
    return [load(p) for p in sorted((Path(run) / "changes").glob("*.json"))]


def completed_journal_time(journal):
    try:
        when = datetime.fromisoformat(journal["completed_at"].replace("Z", "+00:00"))
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("Timezone required")
        return when.astimezone(timezone.utc)
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise FormatError(
            "Completed journal needs an unambiguous timezone-aware completed_at"
        ) from exc


def latest_completed_dispositions(run):
    """Read current finding outcomes without rewriting their installation history.

    Compare timezone-aware completion instants, not filenames or timestamp strings.
    Two completed journals disposing of the same finding at the same instant have
    no established precedence, so refuse a potentially false completion claim.
    """
    installed = set()
    latest = {}
    observed = {}
    for journal in journals(run):
        if journal.get("status") != "complete":
            continue
        when = completed_journal_time(journal)
        installed.update(journal["decision_ids"])
        for key, outcome in journal.get("finding_dispositions", {}).items():
            if (key, when) in observed:
                raise FormatError(
                    "Ambiguous completed journal order for finding: " + key
                )
            observed[key, when] = journal["batch_id"]
            if key not in latest or when > latest[key][0]:
                latest[key] = (when, outcome)
    return installed, {key: value[1] for key, value in latest.items()}


def media_gap_summary(inv, active):
    """Count declared media gaps by source occurrence in active review decisions.

    Neither a completed installation nor repeated application inspects media.
    Resolve original message IDs within that decision's covered conversation
    membership so the same ID in another conversation cannot erase a gap.
    """
    pieces = {
        piece["piece_id"]: piece
        for packet in inv["packets"]
        for piece in packet["pieces"]
    }
    gaps = set()
    conversations = set()
    for decision in active:
        covered = {
            pieces[item["piece_id"]]["message_record_id"]
            for item in decision["coverage"]
        }
        covered.discard(None)
        for gap in decision.get("media_gaps", []):
            candidates = [
                mid
                for mid in covered
                if (
                    gap.get("message_record_id") == mid
                    or gap.get("message_id") == inv["messages"][mid]["original_id"]
                )
            ]
            pointer = gap.get("json_pointer")
            if pointer:
                candidates = [
                    mid
                    for mid in candidates
                    if pointer.startswith(
                        inv["messages"][mid]["provenance"]["json_pointer"] + "/"
                    )
                ]
            if len(candidates) != 1:
                raise FormatError(
                    "Media gap must identify exactly one covered message occurrence"
                )
            mid = candidates[0]
            message = inv["messages"][mid]
            if pointer:
                locator = pointer
            elif isinstance(gap.get("part_index"), int) and gap["part_index"] >= 0:
                prefix = (
                    "/content/parts/"
                    if inv["selection"]["provider"] == "chatgpt"
                    else "/content/"
                )
                locator = (
                    message["provenance"]["json_pointer"]
                    + prefix
                    + str(gap["part_index"])
                )
            else:
                locator = gap.get("asset_pointer") or canonical(gap)
            gaps.add((mid, locator))
            conversations.add(message["conversation_record_id"])
    return len(gaps), len(conversations)


def status(run):
    inv = checked_inventory(run)
    cov = coverage(run)
    active = decisions(run)
    installed, current_dispositions = latest_completed_dispositions(run)
    media_gap_count, conversations_with_media_gaps = media_gap_summary(inv, active)
    unresolved = {
        key.split("/", 1)[0]
        for key, value in current_dispositions.items()
        if value["outcome"] == "unresolved"
    }
    stats = Counter()
    packets = defaultdict(list)
    for p in inv["packets"]:
        packets[p["conversation_record_id"]].extend(p["pieces"])
    results = []
    for c in inv["conversations"]:
        parts = packets[c["record_id"]]
        n = sum(p["piece_id"] in cov for p in parts)
        if not parts:
            state = "pending"  # Empty conversations need explicit inventory disposition in a later review; do not infer completion.
        elif n == 0:
            state = "pending"
        elif n < len(parts):
            state = "partial"
        elif any(cov[p["piece_id"]]["decision_id"] in unresolved for p in parts):
            state = "reviewed_with_gaps"
        elif all(cov[p["piece_id"]]["decision_id"] in installed for p in parts):
            state = "integrated"
        else:
            state = "reviewed_not_integrated"
        stats[state] += 1
        results.append(
            dict(
                rank=c["rank"],
                conversation_id=c["original_id"],
                title=c["title"],
                state=state,
                covered_pieces=n,
                total_pieces=len(parts),
            )
        )
    return dict(
        conversations=len(results),
        messages=len(inv["messages"]),
        packets=len(inv["packets"]),
        media_gap_count=media_gap_count,
        conversations_with_media_gaps=conversations_with_media_gaps,
        counts=dict(stats),
        covered_pieces=len(cov),
        total_pieces=sum(len(p["pieces"]) for p in inv["packets"]),
        complete=stats["integrated"] == len(results)
        and not inv["selection"].get("missing_conversation_ids"),
        missing_membership_ids=inv["selection"].get("missing_conversation_ids", []),
        decisions=len(active),
        findings=sum(len(d.get("findings", [])) for d in active),
        items=results,
    )


def patch_text(text, patches, reverse=False):
    for p in reversed(patches) if reverse else patches:
        before, after = (
            (p["after"], p["before"]) if reverse else (p["before"], p["after"])
        )
        if not before or text.count(before) != 1:
            raise FormatError("Patch must match exactly one nonempty passage")
        text = text.replace(before, after, 1)
    return text


def guard_decision_reuse(run, doc, active):
    """An installed decision cannot authorize another ordinary installation.

    An explicit resolution revision may resolve specified still-open findings.
    It must name the latest completed batch for every reused decision, retaining
    all other finding dispositions exactly. The same batch can be checked again
    or recovered without being mistaken for a second installation.
    """
    latest = {}
    for journal in journals(run):
        if journal["batch_id"] == doc["batch_id"]:
            if journal["batch"] != doc:
                raise FormatError("Batch ID already used for different changes")
            continue
        if journal.get("status") != "complete":
            continue
        when = completed_journal_time(journal)
        for did in journal["decision_ids"]:
            if did not in doc["decision_ids"]:
                continue
            if did in latest and when == latest[did][0]:
                raise FormatError(
                    "Ambiguous completed journal order for decision: " + did
                )
            if did not in latest or when > latest[did][0]:
                latest[did] = (when, journal)
    revision = doc.get("resolution_revision")
    if not latest:
        if revision is not None:
            raise FormatError("Resolution revision requires an installed decision")
        return
    if not isinstance(revision, dict):
        raise FormatError(
            "Decision already installed; use an explicit resolution_revision for unresolved findings"
        )
    if (
        not isinstance(revision.get("prior_batch_id"), str)
        or not isinstance(revision.get("reason"), str)
        or not revision["reason"].strip()
        or not isinstance(revision.get("finding_ids"), list)
        or not revision["finding_ids"]
        or any(not isinstance(key, str) for key in revision["finding_ids"])
    ):
        raise FormatError(
            "Resolution revision needs prior_batch_id, finding_ids, and a reason"
        )
    keys = set(revision["finding_ids"])
    if len(keys) != len(revision["finding_ids"]):
        raise FormatError("Repeated resolution finding ID")
    available = set()
    changed = set()
    for did, (_, prior) in latest.items():
        if prior["batch_id"] != revision["prior_batch_id"]:
            raise FormatError(
                "Resolution revision must reference the latest completed batch for every reused decision"
            )
        did_changed = False
        for finding in active[did].get("findings", []):
            key = did + "/" + finding["finding_id"]
            available.add(key)
            before = prior.get("finding_dispositions", {}).get(key)
            after = doc.get("finding_dispositions", {}).get(key)
            if key in keys:
                if (
                    not before
                    or before.get("outcome") != "unresolved"
                    or not after
                    or after.get("outcome")
                    not in ("integrated", "already_represented", "excluded")
                ):
                    raise FormatError(
                        "Resolution revisions may only change unresolved findings to resolved outcomes"
                    )
                changed.add(key)
                did_changed = True
            elif after != before:
                raise FormatError(
                    "Resolution revision changes an undeclared finding: " + key
                )
        if not did_changed:
            raise FormatError(
                "Each reused decision must resolve at least one declared unresolved finding"
            )
    if keys - available or changed != keys:
        raise FormatError(
            "Resolution revision references an unknown or non-reused finding"
        )


def check(run, batch=None):
    inv = checked_inventory(run)
    from .master_validation import validate_master, validate_reports

    root = Path(inv["master"]).parent
    before = {n: (root / n).read_text() for n in FILES}
    after = dict(before)
    errors = []
    doc = load(batch) if batch and not isinstance(batch, dict) else batch
    if doc:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", doc.get("batch_id", "")):
            raise FormatError("Unsafe or missing batch ID")
        active = {d["decision_id"]: d for d in decisions(run)}
        if not doc.get("decision_ids") or any(
            d not in active for d in doc["decision_ids"]
        ):
            raise FormatError("Batch must reference active decisions")
        if len(set(doc["decision_ids"])) != len(doc["decision_ids"]):
            raise FormatError("Repeated decision ID in batch")
        if set(doc["files"]) != set(FILES):
            raise FormatError("Batch must account for master and both reports")
        dispositions = doc.get("finding_dispositions", {})
        for did in doc["decision_ids"]:
            for f in active[did].get("findings", []):
                key = did + "/" + f["finding_id"]
                out = dispositions.get(key)
                if (
                    not out
                    or out.get("outcome")
                    not in (
                        "integrated",
                        "already_represented",
                        "excluded",
                        "unresolved",
                    )
                    or not out.get("reason")
                ):
                    raise FormatError("Every finding needs an integration disposition")
                if out["outcome"] == "integrated" and not out.get("entry_ids"):
                    raise FormatError("Integrated finding needs entry links")
        guard_decision_reuse(run, doc, active)
        for name, spec in doc["files"].items():
            current = before[name]
            h = digest(current)
            if h == spec["before_sha256"]:
                after[name] = patch_text(current, spec["patches"])
            elif h == spec["after_sha256"]:
                before[name] = patch_text(current, spec["patches"], reverse=True)
                after[name] = current
            else:
                raise FormatError("Stale or partially unknown canonical file: " + name)
            if (
                digest(before[name]) != spec["before_sha256"]
                or digest(after[name]) != spec["after_sha256"]
            ):
                raise FormatError("Patch hash mismatch")
    a = validate_master(after[FILES[0]], before[FILES[0]])
    b = validate_reports(
        after[FILES[0]],
        after[FILES[1]],
        after[FILES[2]],
        before[FILES[1]],
        before[FILES[2]],
    )
    errors.extend(a["errors"])
    errors.extend(b["errors"])
    if doc:
        for did in doc["decision_ids"]:
            for finding in active[did].get("findings", []):
                disposition = doc["finding_dispositions"][
                    did + "/" + finding["finding_id"]
                ]
                if disposition["outcome"] == "integrated":
                    for q in finding.get("quotes", []):
                        if q["text"] not in after[FILES[0]]:
                            errors.append(
                                "Integrated quote missing from master: "
                                + did
                                + "/"
                                + finding["finding_id"]
                            )
                        mid = q["message_record_id"]
                        meta = inv["messages"][mid]
                        for witness in (
                            meta["original_id"],
                            meta["provenance"]["sha256"],
                            meta["provenance"]["json_pointer"],
                        ):
                            if witness not in after[FILES[0]]:
                                errors.append(
                                    "Integrated provenance missing from master: "
                                    + witness
                                )
        active_ids = set(re.findall(r'<a id="(e\d{4})"></a>', after[FILES[0]]))
        for out in doc.get("finding_dispositions", {}).values():
            for eid in out.get("entry_ids", []):
                if eid.lower() not in active_ids:
                    errors.append("Finding links nonexistent entry: " + eid)
    return (
        {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "master_validation": a,
            "report_validation": b,
            "review_status": status(run),
        },
        before,
        after,
    )


def apply(run, batch):
    run = Path(run)
    doc = load(batch) if not isinstance(batch, dict) else batch
    bid = doc.get("batch_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", bid):
        raise FormatError("Unsafe batch ID")
    for pending in journals(run):
        if pending["status"] == "installing" and pending["batch_id"] != bid:
            raise FormatError(
                "Recover pending installation before applying another batch"
            )
    journal = run / "changes" / f"{bid}.json"
    if journal.exists():
        prior = load(journal)
        if prior["batch"] != doc:
            raise FormatError("Batch ID already used for different changes")
        if prior["status"] == "complete":
            return {"status": "already_applied", "batch_id": bid}
    result, before, after = check(run, doc)
    if result["errors"]:
        raise FormatError(
            "Prospective files failed validation: " + str(result["errors"])
        )
    root = Path(load(run / "inventory.json")["master"]).parent
    j = dict(
        batch_id=bid,
        batch=doc,
        decision_ids=doc["decision_ids"],
        finding_dispositions=doc.get("finding_dispositions", {}),
        status="installing",
        installed_files=[],
        started_at=stamp(),
    )
    atomic_json(journal, j)
    for name in FILES:
        current = (root / name).read_text()
        if digest(current) not in (digest(before[name]), digest(after[name])):
            raise FormatError("Canonical file changed during installation")
        if current != after[name]:
            atomic_text(root / name, after[name])
        j["installed_files"].append(name)
        atomic_json(journal, j)
    result, _, _ = check(run, doc)
    if result["errors"]:
        raise FormatError("Installed files failed validation")
    j.update(status="complete", completed_at=stamp())
    atomic_json(journal, j)
    return {"status": "applied", "batch_id": bid, "review_status": status(run)}
