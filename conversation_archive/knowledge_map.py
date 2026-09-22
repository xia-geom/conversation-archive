"""Local knowledge map: checked organization state → SQLite → Cytoscape viewer."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from . import organization as org
from .knowledge_store import MapError, Store, build, build_archive
from .knowledge_server import MapHTTPServer, install_assets


def demo(output):
    """Create only invented state, rules, and a derived database; no model calls."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    texts = [
        "In spring 2024, Rowan and I planned Orchard in Riverton.",
        "The summer build needed a smaller prototype.",
        "Orchard: Rowan reviewed the prototype.",
        "I postponed the summer build after the budget review.",
        "I restarted Orchard and changed the test plan.",
        "Another Rowan helped with a separate class in Lakeside.",
        "A note with no catalog match remains searchable. 薄荷 🌱",
    ]
    entries = [{"entry_id": f"E{i:04d}", "text": text,
                "source": {"kind": "invented_example", "record": i}} for i, text in enumerate(texts, 1)]
    catalog = [
        {"kind": "project", "label": "Orchard", "family": "project"},
        {"kind": "project", "label": "summer build", "family": "project"},
        {"kind": "person", "label": "Rowan", "family": "rowan"},
        {"kind": "place", "label": "Riverton", "family": "place"},
    ]
    def proposal(pid, source, target, relation):
        evidence = []
        for i in (source, target):
            evidence.append({"entry_id": entries[i-1]["entry_id"], "start": 0,
                             "end": len(texts[i-1]), "quote": texts[i-1]})
        return {"proposal_id": pid, "source": entries[source-1]["entry_id"],
                "target": entries[target-1]["entry_id"], "relation": relation,
                "reason": "Invented relation for exercising review states.", "evidence": evidence}
    data = {"version": "1.0", "entries": entries, "catalog": catalog, "proposals": [
        proposal("restart", 4, 5, "continues"), proposal("rethink", 2, 5, "revises"),
        proposal("unsupported-cause", 6, 4, "reported_cause")]}
    run = output / "organization"
    org.prepare(data, run)
    state = org.read_state(run)
    event = {"event_id": "synthetic-map-answer", "actor": "Invented demo reviewer",
             "answer": "Fixture only: Orchard is one project; workshop Rowan is not class Rowan. Confirm the restart, reject the cause.",
             "expected_state_sha256": org.digest(state), "operations": [
        {"op": "bind", "rule_id": "demo-project", "depends_on": [], "kind": "project",
         "aliases": ["Orchard", "summer build"], "entry_ids": [f"E{i:04d}" for i in range(1, 6)],
         "entity_id": "orchard", "entity_label": "Orchard project"},
        {"op": "bind", "rule_id": "demo-person", "depends_on": [], "kind": "person",
         "aliases": ["Rowan"], "entry_ids": ["E0001", "E0003"],
         "entity_id": "workshop-rowan", "entity_label": "Workshop Rowan"},
        {"op": "associate", "rule_id": "demo-context", "depends_on": [], "kind": "period",
         "entry_ids": ["E0001", "E0002", "E0003", "E0004", "E0005"],
         "entity_id": "first-phase", "entity_label": "First project phase"},
        {"op": "relation", "rule_id": "demo-restart", "depends_on": [], "proposal_id": "restart", "accept": True},
        {"op": "relation", "rule_id": "demo-reject", "depends_on": [], "proposal_id": "unsupported-cause", "accept": False},
    ]}
    org.apply(run, event)
    report = build(run, output / "map.sqlite3")
    report["synthetic_only"] = True
    (output / "demo-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo", help="Create an invented local map without a model or network")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("assets", help="Install pinned Cytoscape files once, separate from private data")
    p.add_argument("--output", type=Path, required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--download", action="store_true")
    g.add_argument("--from-directory", type=Path)
    p = sub.add_parser("build", help="Project checked organization state; never rewrite the master")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--database", type=Path, required=True)
    p = sub.add_parser("build-archive", help="Project a validated authoritative machine snapshot")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--database", type=Path, required=True)
    for command in ("search", "neighbors", "serve"):
        p = sub.add_parser(command)
        p.add_argument("--database", type=Path, required=True)
        source = p.add_mutually_exclusive_group(required=True)
        source.add_argument("--run", type=Path, help="Watch this source state and reject stale queries")
        source.add_argument("--archive", type=Path, help="Watch an authoritative machine snapshot")
        source.add_argument("--snapshot-only", action="store_true", help="Explicitly inspect a historical index without a live-source check")
        if command == "serve":
            p.add_argument("--assets", type=Path, required=True)
            p.add_argument("--port", type=int, default=0)
        elif command == "search":
            p.add_argument("--query", default="")
            p.add_argument("--kind", default="")
            p.add_argument("--limit", type=int, default=25)
        else:
            p.add_argument("--id", required=True)
            p.add_argument("--depth", type=int, default=1)
            p.add_argument("--include-proposed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo(args.output)
        elif args.command == "assets":
            result = install_assets(args.output, args.download, args.from_directory)
        elif args.command == "build":
            result = build(args.run, args.database)
        elif args.command == "build-archive":
            result = build_archive(args.archive, args.database)
        else:
            store = Store(args.database, run=args.run, archive_root=args.archive)
            if args.command == "serve":
                with MapHTTPServer(store, args.assets, args.port) as server:
                    print("Read-only local map. Open this session URL; stop with Ctrl+C:", flush=True)
                    print(server.launch_url, flush=True)
                    try:
                        server.serve_forever()
                    except KeyboardInterrupt:
                        pass
                return 0
            elif args.command == "search":
                result = store.search(args.query, args.kind, args.limit)
            else:
                statuses = ("observed_text", "user_confirmed", "proposed") if args.include_proposed else ("observed_text", "user_confirmed")
                result = store.neighborhood(args.id, args.depth, statuses)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MapError, org.OrganizationError, OSError, sqlite3.DatabaseError, ValueError, KeyError) as exc:
        # No source text or provider error bodies in routine diagnostics.
        print(json.dumps({"error": str(exc) if isinstance(exc, MapError) else type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
