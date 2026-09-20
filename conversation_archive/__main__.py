"""Small, explicit commands: inventory, normalize, validate, inspect."""

import argparse
import json
from pathlib import Path
import sys
from zipfile import BadZipFile
from .inventory import inventory
from .model import FormatError
from .pipeline import normalize, validate, inspect_record, write_json


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("inventory", "normalize"):
        a = sub.add_parser(name)
        a.add_argument("--config", required=True, type=Path)
        a.add_argument("--output", required=True, type=Path)
    a = sub.add_parser("validate")
    a.add_argument("--dataset", required=True, type=Path)
    a.add_argument("--report", type=Path)
    a = sub.add_parser("inspect")
    a.add_argument("--dataset", required=True, type=Path)
    a.add_argument(
        "--kind",
        choices=("messages", "conversations", "attachments"),
        default="messages",
    )
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--record-id")
    g.add_argument("--line", type=int)
    args = p.parse_args(argv)
    try:
        if args.command == "inventory":
            value = inventory(args.config)
            if args.output.exists():
                raise FormatError("Inventory output exists; choose a new path")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, value)
            print(
                json.dumps(
                    {
                        "source_payloads": len(value["sources"]),
                        "output": str(args.output),
                    }
                )
            )
            return 0
        if args.command == "normalize":
            value = normalize(args.config, args.output)
        elif args.command == "validate":
            value = validate(args.dataset)
            if args.report:
                if args.report.resolve().is_relative_to(args.dataset.resolve()):
                    raise FormatError(
                        "Write a fresh validation report outside the immutable dataset directory"
                    )
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
        # Avoid dumping malformed source text into terminal logs.
        print(
            "Error: "
            + (
                str(e)
                if isinstance(e, FormatError)
                else type(e).__name__ + "; check paths and input format"
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
