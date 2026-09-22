"""Versioned authoritative machine archive with rebuildable SQLite views.

Snapshots are immutable directories of deterministic JSON/JSONL records. SQLite
is a disposable retrieval projection. Generated Markdown is never evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from . import organization as org
from .structured_archive import ArchiveError, connect, create_schema, render as render_sqlite

VERSION = "1.0"
TABLES = (
    "migration_sources", "entries", "entry_metadata", "source_references",
    "entities", "mentions", "relationships", "correction_events",
    "correction_rules", "unresolved_questions",
)
PRIMARY = {
    "migration_sources": ("source_id",), "entries": ("entry_id",),
    "entry_metadata": ("entry_id", "field", "ordinal"),
    "source_references": ("entry_id", "source_ref"), "entities": ("entity_id",),
    "mentions": ("mention_id",), "relationships": ("relationship_id",),
    "correction_events": ("ordinal", "event_id"),
    "correction_rules": ("event_id", "ordinal", "rule_id"),
    "unresolved_questions": ("question_id",),
}


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(value) -> str:
    return digest_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False).encode())


def dump_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False) + "\n")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ArchiveError(f"Invalid JSONL in {path.name} line {number}") from exc
    return records


def archive_records(root: Path) -> dict[str, list[dict]]:
    return {table: load_jsonl(root / f"{table}.jsonl") for table in TABLES}


def row_records(db: sqlite3.Connection, table: str) -> list[dict]:
    fields = [x[1] for x in db.execute(f"PRAGMA table_info({table})")]
    rows = [dict(zip(fields, row)) for row in db.execute(f"SELECT * FROM {table}")]
    return sorted(rows, key=lambda row: tuple(row[k] for k in PRIMARY[table]))


def confirmed_precedes_cycle(relationships: list[dict]) -> bool:
    graph = {}
    for relation in relationships:
        if (relation["relation"] == "precedes" and relation["authority"] == "owner_confirmed"
                and relation["status"] == "user_confirmed"):
            graph.setdefault(relation["source_id"], set()).add(relation["target_id"])
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(next_node) for next_node in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False
    return any(visit(node) for node in graph)


def relationship_nodes(records: dict, derived_graph: Path | None) -> list[dict]:
    nodes = {}
    for entry in records["entries"]:
        for node_id in (entry["entry_id"], "entry:" + entry["entry_id"]):
            nodes[node_id] = {"node_id": node_id, "node_type": "entry", "label": entry["title"],
                             "authority": "exact_entry_snapshot"}
    for mention in records["mentions"]:
        nodes[mention["mention_id"]] = {"node_id": mention["mention_id"], "node_type": "mention",
                                        "label": mention["quote"], "authority": "explicit_text_observation"}
    for entity in records["entities"]:
        nodes[entity["entity_id"]] = {"node_id": entity["entity_id"], "node_type": entity["kind"],
                                      "label": entity["label"], "authority": entity["authority"]}
    if derived_graph:
        graph = load_json(derived_graph)
        for node in graph["nodes"]:
            node_id = node["id"]
            nodes[node_id] = {"node_id": node_id, "node_type": node.get("type", "derived"),
                              "label": node.get("label", node_id),
                              "authority": "generated_view_node"}
    return [nodes[k] for k in sorted(nodes)]


def snapshot(database: Path, output: Path, snapshot_version: str,
             derived_graph: Path | None = None, parent_snapshot_id: str | None = None,
             migration_exceptions: list[dict] | None = None) -> dict:
    if output.exists():
        raise ArchiveError("Snapshot output exists; authoritative snapshots are immutable")
    output.mkdir(parents=True, mode=0o700)
    db = connect(database)
    try:
        meta = dict(db.execute("SELECT key,value FROM metadata"))
        records = {table: row_records(db, table) for table in TABLES}
    finally:
        db.close()
    for table, rows in records.items():
        dump_jsonl(output / f"{table}.jsonl", rows)
    nodes = relationship_nodes(records, derived_graph)
    dump_jsonl(output / "nodes.jsonl", nodes)
    files = {}
    for path in sorted(output.glob("*.jsonl")):
        files[path.name] = {"sha256": digest_bytes(path.read_bytes()), "bytes": path.stat().st_size,
                            "records": len(load_jsonl(path))}
    body = {
        "schema_version": VERSION, "snapshot_version": snapshot_version,
        "parent_snapshot_id": parent_snapshot_id, "master_sha256": meta["master_sha256"],
        "files": files, "migration_exceptions": migration_exceptions or [],
        "authority_policy": {
            "evidence": ["exact_entry_snapshot", "explicit_master_metadata", "explicit_text_observation",
                         "explicit_master_relationship", "owner_confirmed"],
            "non_evidence": ["proposed_inference", "generated_from_explicit_metadata",
                             "generated_retrieval", "generated_inference", "generated_view_node"],
            "rule": "Import preserves authority; derived links never become accepted evidence by import.",
        },
    }
    manifest = dict(body, snapshot_id="AS-" + digest_json(body)[:32])
    dump_json(output / "manifest.json", manifest)
    report = validate(output)
    if report["status"] != "passed":
        shutil.rmtree(output)
        raise ArchiveError("New authoritative snapshot failed validation")
    return report


def validate(root: Path) -> dict:
    manifest = load_json(root / "manifest.json")
    errors, warnings = [], []
    if manifest.get("schema_version") != VERSION:
        errors.append("schema version mismatch")
    body = {k: v for k, v in manifest.items() if k != "snapshot_id"}
    if manifest.get("snapshot_id") != "AS-" + digest_json(body)[:32]:
        errors.append("snapshot ID mismatch")
    for name, expected in manifest.get("files", {}).items():
        path = root / name
        if not path.is_file():
            errors.append(f"missing {name}"); continue
        if digest_bytes(path.read_bytes()) != expected["sha256"]:
            errors.append(f"hash mismatch {name}")
        try:
            if len(load_jsonl(path)) != expected["records"]:
                errors.append(f"record count mismatch {name}")
        except ArchiveError as exc:
            errors.append(str(exc))
    try:
        records = archive_records(root); nodes = load_jsonl(root / "nodes.jsonl")
    except (OSError, ArchiveError) as exc:
        return {"status": "failed", "errors": errors + [str(exc)], "warnings": warnings}
    node_ids = {n["node_id"] for n in nodes}
    if len(node_ids) != len(nodes): errors.append("duplicate relationship node")
    valid_entries = [e for e in records["entries"] if isinstance(e, dict) and
                     {"entry_id", "raw_markdown", "source_sha256"} <= set(e)]
    if len(valid_entries) != len(records["entries"]): errors.append("invalid entry record")
    entries = {e["entry_id"]: e for e in valid_entries}
    if len(entries) != len(records["entries"]): errors.append("duplicate entry ID")
    master_hash = manifest.get("master_sha256")
    if any(e["source_sha256"] != master_hash for e in entries.values()):
        errors.append("entry snapshot master hash mismatch")
    for m in records["entry_metadata"]:
        entry = entries.get(m["entry_id"]); start, end = m["evidence_start"], m["evidence_end"]
        if not entry or not (0 <= start <= end <= len(entry["raw_markdown"])) or entry["raw_markdown"][start:end] != m["value"]:
            errors.append(f"metadata evidence mismatch {m.get('entry_id')}:{m.get('field')}")
    active_rules = {r["rule_id"] for r in records["correction_rules"] if r["active"]}
    for rel in records["relationships"]:
        if rel["source_id"] not in node_ids or rel["target_id"] not in node_ids:
            errors.append(f"unresolved relationship endpoint {rel['relationship_id']}")
        try:
            evidence = json.loads(rel["evidence_json"]); rule_ids = json.loads(rel["rule_ids_json"])
        except json.JSONDecodeError:
            errors.append(f"invalid relationship JSON {rel['relationship_id']}"); continue
        if rel["authority"] == "owner_confirmed" and not rule_ids:
            errors.append(f"owner-confirmed relation lacks rule {rel['relationship_id']}")
        if rel["authority"] == "owner_confirmed" and any(r not in active_rules for r in rule_ids):
            errors.append(f"owner-confirmed relation references inactive rule {rel['relationship_id']}")
        if rel["authority"] == "explicit_master_relationship":
            source = rel["source_id"].removeprefix("entry:")
            quote = evidence.get("quote") if isinstance(evidence, dict) else None
            if source not in entries or not quote or quote not in entries[source]["raw_markdown"]:
                errors.append(f"explicit relationship evidence mismatch {rel['relationship_id']}")
        if rel["authority"].startswith("generated") and rel["status"] in {"user_confirmed", "accepted"}:
            errors.append(f"derived relation promoted on import {rel['relationship_id']}")
        if rel["origin"] == "machine_archive_relation_answer":
            if (rel["authority"] != "owner_confirmed" or rel["status"] not in {"user_confirmed", "rejected"}
                    or rel["relation"] not in org.RELATIONS or rel["source_id"] == rel["target_id"]):
                errors.append(f"invalid answered relation {rel['relationship_id']}")
            if not isinstance(evidence, list) or {item.get("entry_id") for item in evidence if isinstance(item, dict)} != {rel["source_id"], rel["target_id"]}:
                errors.append(f"relation evidence scope mismatch {rel['relationship_id']}")
            else:
                for item in evidence:
                    entry = entries.get(item["entry_id"])
                    start, end, quote = item.get("start"), item.get("end"), item.get("quote")
                    if (not entry or type(start) is not int or type(end) is not int or not isinstance(quote, str)
                            or not quote.strip() or not 0 <= start < end <= len(entry["raw_markdown"])
                            or entry["raw_markdown"][start:end] != quote):
                        errors.append(f"relation quotation mismatch {rel['relationship_id']}")
    if confirmed_precedes_cycle(records["relationships"]):
        errors.append("confirmed precedes relationships form a cycle")
    for mention in records["mentions"]:
        entry = entries.get(mention["entry_id"])
        if not entry or entry["raw_markdown"][mention["start"]:mention["end"]] != mention["quote"]:
            errors.append(f"mention evidence mismatch {mention['mention_id']}")
    mention_index = {m["mention_id"]: m for m in records["mentions"]}
    for question in records["unresolved_questions"]:
        try:
            evidence = json.loads(question["evidence_json"])
            if not evidence or any(mention_index[item["mention_id"]]["entry_id"] != item["entry_id"]
                                   or mention_index[item["mention_id"]]["kind"] != question["kind"]
                                   for item in evidence):
                errors.append(f"question evidence mismatch {question['question_id']}")
        except (KeyError, TypeError, json.JSONDecodeError):
            errors.append(f"invalid question evidence {question['question_id']}")
    if manifest.get("migration_exceptions"):
        warnings.append(f"{len(manifest['migration_exceptions'])} unresolved migration exception(s)")
    return {"status": "failed" if errors else "passed", "errors": errors, "warnings": warnings,
            "snapshot_id": manifest.get("snapshot_id"), "counts": {k: len(v) for k, v in records.items()} | {"nodes": len(nodes)},
            "master_sha256": master_hash, "migration_exceptions": manifest.get("migration_exceptions", [])}


def build_sqlite(root: Path, database: Path) -> dict:
    report = validate(root)
    if report["status"] != "passed": raise ArchiveError("Refusing to build from invalid snapshot")
    if database.exists(): raise ArchiveError("SQLite output exists; rebuild to a new path")
    records = archive_records(root)
    database.parent.mkdir(parents=True, exist_ok=True)
    db = connect(database)
    try:
        create_schema(db)
        manifest = load_json(root / "manifest.json")
        for key, value in (("schema_version", "1.0"), ("master_sha256", manifest["master_sha256"]),
                           ("evidence_policy", "authoritative_machine_archive"),
                           ("archive_snapshot_id", manifest["snapshot_id"])):
            db.execute("INSERT INTO metadata VALUES (?,?)", (key, value))
        for table in TABLES:
            columns = [x[1] for x in db.execute(f"PRAGMA table_info({table})")]
            sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
            for record in records[table]:
                db.execute(sql, tuple(record[c] for c in columns))
        db.commit()
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        fk = list(db.execute("PRAGMA foreign_key_check"))
        if integrity != "ok" or fk: raise ArchiveError("Rebuilt SQLite failed integrity checks")
        counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLES}
        return {"status": "passed", "snapshot_id": manifest["snapshot_id"], "counts": counts}
    except Exception:
        db.close(); database.unlink(missing_ok=True); raise
    finally:
        try: db.close()
        except Exception: pass


def apply_correction(root: Path, decision_path: Path, output: Path,
                     snapshot_version: str) -> dict:
    report = validate(root)
    if report["status"] != "passed": raise ArchiveError("Cannot correct invalid snapshot")
    if output.exists(): raise ArchiveError("Successor snapshot already exists")
    decision = load_json(decision_path); manifest = load_json(root / "manifest.json")
    required = {"version", "decision_id", "basis_snapshot_id", "actor", "answer", "operations"}
    if set(decision) != required or decision["version"] != VERSION or decision["basis_snapshot_id"] != manifest["snapshot_id"]:
        raise ArchiveError("Invalid or stale correction decision")
    if not all(isinstance(decision[k], str) and decision[k].strip() for k in ("decision_id", "actor", "answer")):
        raise ArchiveError("Correction requires decision ID, actor, and verbatim answer")
    records = archive_records(root); nodes = load_jsonl(root / "nodes.jsonl")
    if decision["decision_id"] in {event["event_id"] for event in records["correction_events"]}:
        raise ArchiveError("Correction decision ID already exists")
    mentions = {m["mention_id"]: m for m in records["mentions"]}; entries = {e["entry_id"] for e in records["entries"]}
    questions = {q["question_id"]: q for q in records["unresolved_questions"]}
    referenced_questions = set()
    rules = {r["rule_id"] for r in records["correction_rules"]}; relationships = {r["relationship_id"] for r in records["relationships"]}
    active_rules = {r["rule_id"] for r in records["correction_rules"] if r["active"]}
    event_ordinal = max((e["ordinal"] for e in records["correction_events"]), default=-1) + 1
    records["correction_events"].append({"event_id": decision["decision_id"], "ordinal": event_ordinal,
                                          "actor": decision["actor"], "answer": decision["answer"]})
    node_ids = {n["node_id"] for n in nodes}
    for ordinal, op in enumerate(decision["operations"]):
        if op.get("op") == "assert_relation":
            required_relation = {"op", "rule_id", "depends_on", "source_entry_id", "target_entry_id",
                                 "relation", "decision", "evidence"}
            if set(op) != required_relation or op["decision"] not in {"confirm", "reject"}:
                raise ArchiveError("Invalid relation decision operation")
            if (op["rule_id"] in rules or not set(op["depends_on"]) <= active_rules
                    or not op["source_entry_id"] in entries or not op["target_entry_id"] in entries
                    or op["source_entry_id"] == op["target_entry_id"] or op["relation"] not in org.RELATIONS):
                raise ArchiveError("Unknown relation scope, dependency, or duplicate rule")
            entry_index = {e["entry_id"]: e for e in records["entries"]}
            if (not isinstance(op["evidence"], list) or
                    {item.get("entry_id") for item in op["evidence"] if isinstance(item, dict)} !=
                    {op["source_entry_id"], op["target_entry_id"]}):
                raise ArchiveError("Relation decision must cite both entries")
            for item in op["evidence"]:
                if not isinstance(item, dict) or set(item) != {"entry_id", "start", "end", "quote"}:
                    raise ArchiveError("Invalid relation evidence span")
                start, end, quote = item["start"], item["end"], item["quote"]
                if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(entry_index[item["entry_id"]]["raw_markdown"])
                        or not isinstance(quote, str) or not quote.strip()
                        or entry_index[item["entry_id"]]["raw_markdown"][start:end] != quote):
                    raise ArchiveError("Relation evidence is not an exact entry quotation")
            if any(r["source_id"] == op["source_entry_id"] and r["target_id"] == op["target_entry_id"]
                   and r["relation"] == op["relation"] and r["authority"] == "owner_confirmed"
                   and r["origin"] == "machine_archive_relation_answer" for r in records["relationships"]):
                raise ArchiveError("Relation already has an owner decision")
            rid = "relation-answer-" + digest_json([decision["decision_id"], op["rule_id"]])[:24]
            records["relationships"].append({"relationship_id": rid,
                "source_id": op["source_entry_id"], "target_id": op["target_entry_id"],
                "relation": op["relation"], "authority": "owner_confirmed",
                "status": "user_confirmed" if op["decision"] == "confirm" else "rejected",
                "evidence_json": json.dumps(op["evidence"], ensure_ascii=False, sort_keys=True),
                "rule_ids_json": json.dumps([op["rule_id"]]), "origin": "machine_archive_relation_answer"})
            records["correction_rules"].append({"rule_id": op["rule_id"], "event_id": decision["decision_id"],
                "ordinal": ordinal, "operation": "assert_relation", "active": 1,
                "payload_json": json.dumps(op, ensure_ascii=False, sort_keys=True)})
            rules.add(op["rule_id"])
            active_rules.add(op["rule_id"])
            continue
        required_op = {"op", "rule_id", "depends_on", "kind", "entity_id", "entity_label", "entry_ids", "mention_ids"}
        if set(op) not in (required_op, required_op | {"question_id"}) or op["op"] != "bind_mentions":
            raise ArchiveError("Only explicit bind_mentions corrections are supported in schema 1.0")
        if op["rule_id"] in rules or not set(op["depends_on"]) <= active_rules:
            raise ArchiveError("Duplicate rule or unknown dependency")
        selected=[]
        for mid in op["mention_ids"]:
            m=mentions.get(mid)
            if not m or m["entry_id"] not in op["entry_ids"] or m["kind"] != op["kind"]:
                raise ArchiveError("Correction mention is outside declared scope")
            if m["entity_id"] and m["entity_id"] != op["entity_id"]:
                raise ArchiveError("Correction conflicts with an existing identity")
            selected.append(m)
        if not selected or not set(op["entry_ids"]) <= entries:
            raise ArchiveError("Correction has empty or unknown scope")
        if "question_id" in op:
            question = questions.get(op["question_id"])
            if not question or question["kind"] != op["kind"]:
                raise ArchiveError("Correction cites an unknown or mismatched question")
            question_mentions = {item["mention_id"] for item in json.loads(question["evidence_json"])}
            if not set(op["mention_ids"]) <= question_mentions:
                raise ArchiveError("Correction extends beyond the cited question")
            referenced_questions.add(op["question_id"])
        if op["entity_id"] not in {e["entity_id"] for e in records["entities"]}:
            records["entities"].append({"entity_id": op["entity_id"], "kind": op["kind"],
                                         "label": op["entity_label"], "authority": "owner_confirmed"})
        if op["entity_id"] not in node_ids:
            nodes.append({"node_id": op["entity_id"], "node_type": op["kind"], "label": op["entity_label"],
                          "authority": "owner_confirmed"}); node_ids.add(op["entity_id"])
        for m in selected:
            m["status"]="owner_confirmed"; m["entity_id"]=op["entity_id"]
            rid="correction-"+digest_json([decision["decision_id"],op["rule_id"],m["mention_id"],op["entity_id"]])[:24]
            if rid not in relationships:
                records["relationships"].append({"relationship_id":rid,"source_id":m["mention_id"],"target_id":op["entity_id"],
                    "relation":"refers_to","authority":"owner_confirmed","status":"user_confirmed",
                    "evidence_json":json.dumps([{"entry_id":m["entry_id"],"start":m["start"],"end":m["end"],"quote":m["quote"]}],ensure_ascii=False,sort_keys=True),
                    "rule_ids_json":json.dumps([op["rule_id"]]),"origin":"machine_archive_correction"})
                relationships.add(rid)
        records["correction_rules"].append({"rule_id":op["rule_id"],"event_id":decision["decision_id"],"ordinal":ordinal,
            "operation":"bind_mentions","active":1,"payload_json":json.dumps(op,ensure_ascii=False,sort_keys=True)})
        rules.add(op["rule_id"])
        active_rules.add(op["rule_id"])
    records["unresolved_questions"] = [q for q in records["unresolved_questions"]
        if q["question_id"] not in referenced_questions or not all(
            mentions[item["mention_id"]]["entity_id"] is not None
            for item in json.loads(q["evidence_json"]))]
    if confirmed_precedes_cycle(records["relationships"]):
        raise ArchiveError("Confirmed precedes relationships would form a cycle")
    output.mkdir(parents=True, mode=0o700)
    for table, rows in records.items():
        dump_jsonl(output/f"{table}.jsonl",sorted(rows,key=lambda r:tuple(r[k] for k in PRIMARY[table])))
    dump_jsonl(output/"nodes.jsonl",sorted(nodes,key=lambda n:n["node_id"]))
    files={}
    for path in sorted(output.glob("*.jsonl")):
        files[path.name]={"sha256":digest_bytes(path.read_bytes()),"bytes":path.stat().st_size,"records":len(load_jsonl(path))}
    body={"schema_version":VERSION,"snapshot_version":snapshot_version,"parent_snapshot_id":manifest["snapshot_id"],
          "master_sha256":manifest["master_sha256"],"files":files,"migration_exceptions":manifest["migration_exceptions"],
          "authority_policy":manifest["authority_policy"]}
    successor=dict(body,snapshot_id="AS-"+digest_json(body)[:32]); dump_json(output/"manifest.json",successor)
    checked=validate(output)
    if checked["status"]!="passed": shutil.rmtree(output); raise ArchiveError("Corrected snapshot failed validation")
    return checked


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True)
    s=sub.add_parser("snapshot"); s.add_argument("--database",type=Path,required=True); s.add_argument("--output",type=Path,required=True); s.add_argument("--snapshot-version",required=True); s.add_argument("--derived-graph",type=Path)
    v=sub.add_parser("validate"); v.add_argument("--archive",type=Path,required=True)
    b=sub.add_parser("build-sqlite"); b.add_argument("--archive",type=Path,required=True); b.add_argument("--database",type=Path,required=True)
    c=sub.add_parser("correct"); c.add_argument("--archive",type=Path,required=True); c.add_argument("--decision",type=Path,required=True); c.add_argument("--output",type=Path,required=True); c.add_argument("--snapshot-version",required=True)
    r=sub.add_parser("render"); r.add_argument("--database",type=Path,required=True); r.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.command=="snapshot": result=snapshot(a.database,a.output,a.snapshot_version,a.derived_graph)
        elif a.command=="validate": result=validate(a.archive)
        elif a.command=="build-sqlite": result=build_sqlite(a.archive,a.database)
        elif a.command=="correct": result=apply_correction(a.archive,a.decision,a.output,a.snapshot_version)
        else: result=render_sqlite(a.database,a.output)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result.get("status","passed")!="failed" else 1
    except (OSError,sqlite3.Error,ArchiveError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({"error":str(exc)})); return 2


if __name__=="__main__": raise SystemExit(main())
