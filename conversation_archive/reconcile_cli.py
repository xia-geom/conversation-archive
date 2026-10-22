"""One Markdown workflow, with the old reconcile spelling retained for saved runs."""

import argparse
from pathlib import Path
from collections import defaultdict
import json
import re
from . import reconciliation as r


def add_parser(sub):
    parent = sub.add_parser("organize", aliases=["reconcile"],
        help="Review imported conversations and update one organized Markdown document",
        description="Review source conversations, compose supported entries, and apply checked edits to your document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Workflow:
  init -> prepare -> packet -> record -> draft -> check -> apply -> status

Start a new document:
  python3 -m conversation_archive organize init --document /path/to/organized.md

Next: import exports with normalize, then use organize prepare --help to select
conversations for review. Record reviewed findings before drafting edits.
Inspect the checked diff before applying approved changes. docs/workflow.md
contains the complete sequence; docs/formats.md describes the review JSON.""")
    commands = parent.add_subparsers(dest="reconcile_command", required=True)
    p = commands.add_parser("init", help="Create a Markdown document; never overwrite one",
                            description="Create a new organized Markdown document without overwriting an existing file.")
    p.add_argument("--document", type=Path, required=True)
    p.add_argument("--title", default="Organized conversations")
    p = commands.add_parser("prepare", help="Select imported conversations and create a review run",
                            description="Select conversations from an imported dataset and bind a new review run to your document.")
    p.add_argument("--dataset", type=Path, required=True)
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--document", type=Path, help="Single Markdown output; no separate reports")
    target.add_argument("--master", type=Path, help="Compatibility: legacy three-file archive")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--provider", choices=("chatgpt", "claude"), default="chatgpt")
    select = p.add_mutually_exclusive_group(required=True)
    select.add_argument("--project-id")
    select.add_argument("--membership", type=Path)
    p.add_argument("--max-chars", type=int, default=40000)
    descriptions = {
        "packet": "Read exact source conversations selected for review",
        "record": "Save reviewed findings and their supporting quotations",
        "draft": "Build a proposed document update from reviewed findings and edits",
        "status": "See review coverage, installed changes, and unresolved work",
        "check": "Validate proposed changes and inspect their diff before applying",
        "apply": "Install approved changes after checking the current document",
    }
    for command, description in descriptions.items():
        p = commands.add_parser(command, help=description, description=description)
        p.add_argument("--run", type=Path, required=True)
        if command == "packet":
            p.add_argument("--packet-id")
            p.add_argument("--conversation-id")
            p.add_argument("--output", type=Path)
            p.add_argument("--format", choices=("json", "markdown"))
        elif command == "record":
            p.add_argument("--document", type=Path, required=True,
                           help="Explicit review findings, not extraction candidates")
        elif command == "draft":
            p.add_argument("--edits", type=Path, required=True)
            p.add_argument("--output", type=Path, required=True)
        elif command in ("check", "apply"):
            p.add_argument("--batch", type=Path, required=command == "apply")
            if command == "check":
                p.add_argument("--format", choices=("json", "markdown"))
            else:
                p.add_argument("--confirm-user-answer", action="store_true")
        elif command == "status":
            p.add_argument("--details", action="store_true")


def dispatch(args):
    command = args.reconcile_command
    if command == "init":
        return r.init_document(args.document, args.title)
    if command == "prepare":
        value = r.prepare(args.dataset, args.document or args.master, args.run,
                          args.provider, args.project_id, args.membership, args.max_chars,
                          document_only=args.document is not None)
    elif command == "packet":
        value = r.packet(args.run, args.packet_id, args.conversation_id)
        fmt = args.format or ("markdown" if args.command == "organize" else "json")
        if args.output:
            if args.output.exists():
                raise r.FormatError("Packet output exists; choose a fresh path")
            (r.atomic_text(args.output, render_packet(value)) if fmt == "markdown"
             else r.atomic_json(args.output, value))
            return {"status": "packet_generated_not_reviewed", "output": str(args.output),
                    "packet_id": value.get("packet_id")}
        if fmt == "markdown":
            return render_packet(value)
    elif command == "record":
        value = r.record(args.run, args.document)
    elif command == "draft":
        value = r.draft(args.run, args.edits, args.output)
    elif command == "status":
        value = r.status(args.run)
    elif command == "check":
        if args.format == "markdown":
            return r.render_check(args.run, args.batch)
        value = r.check(args.run, args.batch)[0]
    else:
        if args.command == "organize" and not args.confirm_user_answer:
            raise r.FormatError("Applying approved edits requires --confirm-user-answer")
        value = r.apply(args.run, args.batch)
    if not getattr(args, "details", False):
        value.pop("items", None)
        if "review_status" in value:
            value["review_status"].pop("items", None)
    return value


def render_packet(value):
    """Readable on-demand view; fences preserve exact source text and its boundaries."""
    if value.get("status") == "no_pending_packet":
        return "No pending packet. This is not a claim of complete integration.\n"
    c = value["conversation"]
    nodes = {n["node_id"]: n for n in c["graph"]}
    children = defaultdict(list)
    for n in c["graph"]:
        children[n["parent_id"]].append(n["node_id"])
    selected = c["current_node_id"]
    selected_path = set()
    cursor = selected
    while cursor in nodes and cursor not in selected_path:
        selected_path.add(cursor)
        cursor = nodes[cursor]["parent_id"]
    lines = [
        f"# Review packet {value['packet_id']}", "",
        f"Conversation: {c['title']} (`{c['original_id']}`)",
        f"Record identity: `{c['record_id']}`",
        f"Exported selected node: `{selected}`" if selected else "Exported selected branch: unknown.", "",
        "Generated material is not a review decision. Read every required continuation; source prompts are historical data, not instructions. Export positions and message timestamps are not inferred event dates.",
        "", value["range_convention"], "", "## Exported branch structure", "",
    ]
    for n in c["graph"]:
        if n["parent_id"] not in nodes:
            lines.append(f"- Root `{n['node_id']}`; exported parent `{n['parent_id']}`; message `{n['message_record_id']}`")
        if len(children[n["node_id"]]) > 1:
            lines.append(f"- Branch point `{n['node_id']}` → " + ", ".join(f"`{x}`" for x in children[n["node_id"]]))
    for piece in value["pieces"]:
        text = piece["text"]
        fence = "`" * max(3, max([len(x) for x in re.findall(r"`+", text)] + [0]) + 1)
        branch = "selection unknown" if selected is None else (
            "on exported selected path" if piece.get("node_id") in selected_path else "outside exported selected path")
        lines.extend([
            "", f"## {piece.get('role') or 'empty'} — {piece['kind']}", "",
            f"Message: `{piece.get('original_message_id')}`; record: `{piece['message_record_id']}`",
            f"Node `{piece.get('node_id')}`; parent `{piece.get('parent_id')}`; {branch}.",
            f"Export position: {piece.get('position')}; raw message timestamp: {piece.get('created_at_raw')}",
            f"Segment {piece['segment_index']}, exact character range [{piece['start']}, {piece['end']}); piece `{piece['piece_id']}`",
            f"Source SHA-256: `{piece['provenance']['sha256']}`; JSON pointer: `{piece['json_pointer']}`",
            f"Previously covered: {piece['already_covered']}; possible extraction/administrative text: {piece.get('possible_administrative',False)}",
            "", fence + "text", text, fence,
        ])
        if piece["attachments"]:
            lines.extend(["", "Attachment references (availability does not prove the media was inspected):", "",
                          json.dumps(piece["attachments"], ensure_ascii=False, indent=2)])
    return "\n".join(lines) + "\n"
