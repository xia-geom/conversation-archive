"""Maintain organized Markdown; preserve explicit import and inspection commands."""

import argparse
import json
from pathlib import Path
import sys
from zipfile import BadZipFile
from .inventory import inventory
from .model import FormatError
from .pipeline import normalize, validate, inspect_record, write_json


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "reading":
        from .reading import main as reading_main
        return reading_main(argv[1:])
    p = argparse.ArgumentParser(
        prog="conversation-archive",
        description="Turn conversation exports into one useful, source-attributed Markdown document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Start here:
  python3 -m conversation_archive demo --output /tmp/conversation-demo

Choose your next step:
  organize --help  Review imported conversations and update your document.
  reading --help   Audit an existing document and create a checked reading copy.

First run: docs/getting-started.md. Full workflow: docs/workflow.md
Use COMMAND --help for options.
Run commands as conversation-archive or python3 -m conversation_archive.""")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("demo", help="Try the full Markdown workflow with invented conversations",
                       description="Create an offline example with invented conversations and predetermined review decisions.")
    a.add_argument("--output", required=True, type=Path,
                   help="New directory for the example; existing paths are never overwritten")
    sub.add_parser("reading", help="Audit existing entries and publish a checked local Markdown copy")
    from .reconcile_cli import add_parser, dispatch
    add_parser(sub)
    descriptions = {
        "inventory": "List export files and their source identities before importing",
        "normalize": "Import ChatGPT or Claude exports into a fresh review dataset",
    }
    for name, description in descriptions.items():
        a = sub.add_parser(name, help=description, description=description)
        a.add_argument("--config", required=True, type=Path)
        a.add_argument("--output", required=True, type=Path)
    a = sub.add_parser("validate", help="Check an imported dataset for structural and source integrity",
                       description="Check an imported dataset for structural and source integrity.")
    a.add_argument("--dataset", required=True, type=Path)
    a.add_argument("--report", type=Path)
    a = sub.add_parser("inspect", help="Read an exact message, conversation, or attachment record",
                       description="Read an exact message, conversation, or attachment record from a dataset.")
    a.add_argument("--dataset", required=True, type=Path)
    a.add_argument("--kind", choices=("messages", "conversations", "attachments"), default="messages")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--record-id")
    g.add_argument("--line", type=int)
    if not argv:
        p.print_help()
        return 0
    args = p.parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import run_markdown_demo
            from .extraction import ExtractionError
            try:
                report = run_markdown_demo(args.output)
            except ExtractionError as exc:
                raise FormatError(str(exc)) from exc
            print("Created an example organized Markdown document.")
            print(f"\nOpen: {args.output.resolve() / 'organized.md'}")
            print(f"\nChecks: {report['checked']}")
            print("Original export: " + ("unchanged" if report["original_unchanged"] else "changed"))
            print(f"Safe replay: {report['replay']}")
            print("\nThis offline demo uses invented conversations and predetermined review decisions.")
            print("Next: open the document, then read docs/getting-started.md to use your own exports.")
            print("Command help: python3 -m conversation_archive organize --help")
            print("Full workflow: docs/workflow.md")
            return 0
        if args.command in {"organize", "reconcile"}:
            value = dispatch(args)
            if isinstance(value, str):
                print(value, end="")
                return getattr(value, "exit_code", 0)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 1 if value.get("status") == "failed" else 0
        if args.command == "inventory":
            value = inventory(args.config)
            if args.output.exists():
                raise FormatError("Inventory output exists; choose a new path")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, value)
            print(json.dumps({"source_payloads": len(value["sources"]), "output": str(args.output)}))
            return 0
        if args.command == "normalize":
            value = normalize(args.config, args.output)
        elif args.command == "validate":
            value = validate(args.dataset)
            if args.report:
                if args.report.resolve().is_relative_to(args.dataset.resolve()):
                    raise FormatError("Write a fresh validation report outside the immutable dataset directory")
                if args.report.exists():
                    raise FormatError("Report exists; choose a new report path")
                args.report.parent.mkdir(parents=True, exist_ok=True)
                write_json(args.report, value)
        else:
            value = inspect_record(args.dataset, args.kind, args.record_id, args.line)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["status"] == "passed" else 1
    except (OSError, ValueError, KeyError, TypeError, BadZipFile) as e:
        print("Error: " + (str(e) if isinstance(e, FormatError)
              else type(e).__name__ + "; check paths and input format"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
