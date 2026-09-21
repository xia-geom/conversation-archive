"""Build a local SQLite relationship archive from a preserved Markdown master.

The master is read-only evidence. SQLite and rendered views are derived artifacts.
No generated description is imported as evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from .organization import active_rules, graph as build_graph, load as load_json
from .organization_inputs import index_markdown

SCHEMA_VERSION = "1.0"
FIELDS = {
    "Event period": "event_period",
    "Date basis": "date_basis",
    "Record kind": "record_kind",
    "People / roles": "people_role",
    "Topic labels": "topic",
    "Source references": "source_references",
}


class ArchiveError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def create_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    PRAGMA journal_mode=DELETE;
    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE migration_sources(
      source_id TEXT PRIMARY KEY, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
      byte_count INTEGER NOT NULL, schema_version TEXT NOT NULL
    );
    CREATE TABLE entries(
      entry_id TEXT PRIMARY KEY, title TEXT NOT NULL, raw_markdown TEXT NOT NULL,
      source_sha256 TEXT NOT NULL, source_start INTEGER NOT NULL, source_end INTEGER NOT NULL
    );
    CREATE TABLE entry_metadata(
      entry_id TEXT NOT NULL REFERENCES entries(entry_id), field TEXT NOT NULL,
      ordinal INTEGER NOT NULL, value TEXT NOT NULL, authority TEXT NOT NULL,
      evidence_start INTEGER NOT NULL, evidence_end INTEGER NOT NULL,
      PRIMARY KEY(entry_id, field, ordinal)
    );
    CREATE TABLE source_references(
      entry_id TEXT NOT NULL REFERENCES entries(entry_id), source_ref TEXT NOT NULL,
      PRIMARY KEY(entry_id, source_ref)
    );
    CREATE TABLE entities(
      entity_id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL,
      authority TEXT NOT NULL
    );
    CREATE TABLE mentions(
      mention_id TEXT PRIMARY KEY, entry_id TEXT NOT NULL REFERENCES entries(entry_id),
      kind TEXT NOT NULL, label TEXT NOT NULL, family TEXT NOT NULL,
      start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL,
      status TEXT NOT NULL, entity_id TEXT REFERENCES entities(entity_id)
    );
    CREATE TABLE relationships(
      relationship_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
      relation TEXT NOT NULL, authority TEXT NOT NULL, status TEXT NOT NULL,
      evidence_json TEXT NOT NULL, rule_ids_json TEXT NOT NULL, origin TEXT NOT NULL
    );
    CREATE TABLE correction_events(
      event_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL UNIQUE,
      actor TEXT NOT NULL, answer TEXT NOT NULL
    );
    CREATE TABLE correction_rules(
      rule_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES correction_events(event_id),
      ordinal INTEGER NOT NULL, operation TEXT NOT NULL, active INTEGER NOT NULL,
      payload_json TEXT NOT NULL
    );
    CREATE TABLE unresolved_questions(
      question_id TEXT PRIMARY KEY, kind TEXT NOT NULL, family TEXT,
      prompt TEXT NOT NULL, evidence_json TEXT NOT NULL,
      authority TEXT NOT NULL DEFAULT 'unresolved_candidate'
    );
    CREATE INDEX idx_entry_metadata_lookup ON entry_metadata(field, value, entry_id);
    CREATE INDEX idx_mentions_entry ON mentions(entry_id);
    CREATE INDEX idx_mentions_entity ON mentions(entity_id);
    CREATE INDEX idx_relationship_source ON relationships(source_id, relation);
    CREATE INDEX idx_relationship_target ON relationships(target_id, relation);
    CREATE VIEW entry_overview AS
      SELECT e.entry_id, e.title,
             group_concat(DISTINCT CASE WHEN m.field='people_role' THEN m.value END) people_roles,
             group_concat(DISTINCT CASE WHEN m.field='topic' THEN m.value END) topics,
             max(CASE WHEN m.field='event_period' THEN m.value END) event_period,
             max(CASE WHEN m.field='record_kind' THEN m.value END) record_kind
      FROM entries e LEFT JOIN entry_metadata m ON m.entry_id=e.entry_id
      GROUP BY e.entry_id, e.title;
    """)


def parse_entry(entry: dict) -> tuple[str, list[dict], list[str]]:
    text = entry["text"]
    first = text.splitlines()[0]
    match = re.match(r"^#{1,6}\s+E\d{4}\s*[—:–-]?\s*(.*)$", first)
    title = (match.group(1).strip() if match else first.strip()) or "Untitled entry"
    values, refs = [], []
    for line_match in re.finditer(r"(?m)^\*\*([^*]+):\*\*\s*(.*?)(?:\s{2})?$", text):
        label, raw = line_match.group(1).strip(), line_match.group(2).strip()
        if label not in FIELDS:
            continue
        field = FIELDS[label]
        base_start = line_match.start(2)
        if field in {"people_role", "topic"}:
            items = [x.strip() for x in raw.split(",") if x.strip()]
        elif field == "source_references":
            items = re.findall(r"\[(SRC-[^\]]+)\]", raw)
            refs.extend(items)
        else:
            items = [raw] if raw else []
        cursor = 0
        for ordinal, value in enumerate(items):
            local = raw.find(value, cursor)
            cursor = local + len(value) if local >= 0 else cursor
            values.append({
                "field": field, "ordinal": ordinal, "value": value,
                "authority": "explicit_master_metadata",
                "evidence_start": base_start + max(local, 0),
                "evidence_end": base_start + max(local, 0) + len(value),
            })
    return title, values, refs


def read_master(path: Path) -> tuple[bytes, dict]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return raw, index_markdown(text)


def migrate(master: Path, organization_state: Path, database: Path,
            questions: Path | None = None, derived_graph: Path | None = None) -> dict:
    if database.exists():
        raise ArchiveError("Database already exists; migration never overwrites an archive")
    raw, indexed = read_master(master)
    master_hash = sha256(raw)
    state = load_json(organization_state)
    if any(e.get("source", {}).get("sha256") != master_hash for e in state["data"]["entries"]):
        raise ArchiveError("Organization state is not frozen from this master")
    database.parent.mkdir(parents=True, exist_ok=True)
    db = connect(database)
    try:
        create_schema(db)
        db.execute("INSERT INTO metadata VALUES (?,?)", ("schema_version", SCHEMA_VERSION))
        db.execute("INSERT INTO metadata VALUES (?,?)", ("master_sha256", master_hash))
        db.execute("INSERT INTO metadata VALUES (?,?)", ("evidence_policy", "master_and_owner_confirmations_only"))
        db.execute("INSERT INTO migration_sources VALUES (?,?,?,?,?)",
                   ("master", "preserved_markdown_master", master_hash, len(raw), "indexed-exactly"))
        state_raw = organization_state.read_bytes()
        db.execute("INSERT INTO migration_sources VALUES (?,?,?,?,?)",
                   ("organization_state", "append_only_confirmation_state", sha256(state_raw), len(state_raw), state["version"]))
        indexed_ids = {e["entry_id"] for e in indexed["entries"]}
        state_ids = {e["entry_id"] for e in state["data"]["entries"]}
        if indexed_ids != state_ids:
            raise ArchiveError("Master entry IDs differ from the frozen organization state")
        indexed_text = {e["entry_id"]: e["text"] for e in indexed["entries"]}
        state_text = {e["entry_id"]: e["text"] for e in state["data"]["entries"]}
        if indexed_text != state_text:
            raise ArchiveError("Organization state does not preserve the exact current master entry slices")
        for entry in indexed["entries"]:
            title, fields, refs = parse_entry(entry)
            db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?)", (
                entry["entry_id"], title, entry["text"], master_hash,
                entry["source"]["start"], entry["source"]["end"],
            ))
            for item in fields:
                db.execute("INSERT INTO entry_metadata VALUES (?,?,?,?,?,?,?)", (
                    entry["entry_id"], item["field"], item["ordinal"], item["value"], item["authority"],
                    item["evidence_start"], item["evidence_end"],
                ))
            for ref in refs:
                db.execute("INSERT OR IGNORE INTO source_references VALUES (?,?)", (entry["entry_id"], ref))

        active = active_rules(state)
        for event_no, event in enumerate(state["events"]):
            db.execute("INSERT INTO correction_events VALUES (?,?,?,?)", (
                event["event_id"], event_no, event["actor"], event["answer"],
            ))
            for rule_no, rule in enumerate(event["operations"]):
                db.execute("INSERT INTO correction_rules VALUES (?,?,?,?,?,?)", (
                    rule["rule_id"], event["event_id"], rule_no, rule["op"],
                    int(rule["rule_id"] in active), json.dumps(rule, ensure_ascii=False, sort_keys=True),
                ))

        org_graph = build_graph(state)
        for entity in org_graph["entities"]:
            db.execute("INSERT INTO entities VALUES (?,?,?,?)", (
                entity["node_id"], entity["kind"], entity["label"], "owner_confirmed",
            ))
        assignments = org_graph["assignments"]
        for mention in org_graph["mentions"]:
            assignment = assignments.get(mention["mention_id"])
            db.execute("INSERT INTO mentions VALUES (?,?,?,?,?,?,?,?,?,?)", (
                mention["mention_id"], mention["entry_id"], mention["kind"], mention["label"], mention["family"],
                mention["start"], mention["end"], mention["quote"],
                "owner_confirmed" if assignment else ("deferred" if mention["mention_id"] in org_graph["deferred"] else "observed_text"),
                assignment["entity"] if assignment else None,
            ))
        for edge in org_graph["edges"]:
            authority = "owner_confirmed" if edge["status"] == "user_confirmed" else (
                "owner_rejected" if edge["status"] == "rejected" else
                "explicit_text_observation" if edge["status"] == "observed_text" else "proposed_inference"
            )
            rid = "org-" + stable_id(edge["source"], edge["target"], edge["relation"], json.dumps(edge, sort_keys=True))
            db.execute("INSERT INTO relationships VALUES (?,?,?,?,?,?,?,?,?)", (
                rid, edge["source"], edge["target"], edge["relation"], authority, edge["status"],
                json.dumps(edge.get("evidence", []), ensure_ascii=False, sort_keys=True),
                json.dumps(edge.get("rule_ids", []), ensure_ascii=False), "organization_state",
            ))

        if derived_graph:
            derived = load_json(derived_graph)
            if derived.get("master_sha256") != master_hash:
                raise ArchiveError("Derived graph is stale for this master")
            derived_raw = derived_graph.read_bytes()
            db.execute("INSERT INTO migration_sources VALUES (?,?,?,?,?)", (
                "derived_graph", "generated_relationship_view", sha256(derived_raw), len(derived_raw), derived.get("schema_version", "unknown"),
            ))
            for edge in derived["edges"]:
                authority = {
                    "explicit_cross_reference": "explicit_master_relationship",
                    "mentions_confirmed_entity": "owner_confirmed",
                    "has_facet": "generated_from_explicit_metadata",
                    "related_by_shared_facets": "generated_retrieval",
                }.get(edge["relation"], "generated_inference")
                rid = "derived-" + stable_id(edge["source"], edge["target"], edge["relation"], json.dumps(edge, sort_keys=True))
                db.execute("INSERT OR IGNORE INTO relationships VALUES (?,?,?,?,?,?,?,?,?)", (
                    rid, edge["source"], edge["target"], edge["relation"], authority, "derived",
                    json.dumps(edge, ensure_ascii=False, sort_keys=True),
                    json.dumps(edge.get("rule_ids", []), ensure_ascii=False), "derived_graph",
                ))
        if questions:
            for q in load_json(questions):
                db.execute("INSERT INTO unresolved_questions VALUES (?,?,?,?,?,?)", (
                    q["question_id"], q["kind"], q.get("hypothesis_family"), q["prompt"],
                    json.dumps(q.get("evidence", []), ensure_ascii=False, sort_keys=True), "unresolved_candidate",
                ))
        db.commit()
        result = validate(database, master)
        if result["status"] != "passed":
            raise ArchiveError("Post-migration validation failed")
        return result
    except Exception:
        db.close()
        database.unlink(missing_ok=True)
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def validate(database: Path, master: Path | None = None) -> dict:
    db = connect(database)
    try:
        errors = []
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok": errors.append(integrity)
        fk = [dict(x) for x in db.execute("PRAGMA foreign_key_check")]
        if fk: errors.append("foreign key violations")
        meta = dict(db.execute("SELECT key,value FROM metadata"))
        if meta.get("schema_version") != SCHEMA_VERSION: errors.append("schema version mismatch")
        if master and sha256(master.read_bytes()) != meta.get("master_sha256"): errors.append("master hash mismatch")
        counts = {}
        for table in ("entries", "entry_metadata", "source_references", "entities", "mentions", "relationships", "correction_events", "correction_rules", "unresolved_questions"):
            counts[table] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        missing_metadata = db.execute("SELECT count(*) FROM entries e WHERE NOT EXISTS (SELECT 1 FROM entry_metadata m WHERE m.entry_id=e.entry_id)").fetchone()[0]
        if counts["entries"] == 0: errors.append("no entries")
        return {"status": "failed" if errors else "passed", "errors": errors, "counts": counts,
                "entries_without_explicit_metadata": missing_metadata, "master_sha256": meta.get("master_sha256")}
    finally:
        db.close()


def render(database: Path, output: Path) -> dict:
    if output.exists(): raise ArchiveError("Render output exists; choose a new directory")
    output.mkdir(parents=True, mode=0o700)
    db = connect(database)
    try:
        overview = [dict(x) for x in db.execute("SELECT * FROM entry_overview ORDER BY entry_id")]
        people = [dict(x) for x in db.execute("SELECT value label, count(*) entries FROM entry_metadata WHERE field='people_role' GROUP BY value HAVING count(*)>1 ORDER BY entries DESC, label")]
        topics = [dict(x) for x in db.execute("SELECT value label, count(*) entries FROM entry_metadata WHERE field='topic' GROUP BY value HAVING count(*)>1 ORDER BY entries DESC, label")]
        confirmed = [dict(x) for x in db.execute("SELECT entity_id,label,kind FROM entities ORDER BY kind,label")]
        relation_counts = [dict(x) for x in db.execute("SELECT authority,relation,status,count(*) count FROM relationships GROUP BY authority,relation,status ORDER BY authority,relation,status")]
        summary = {"schema_version": SCHEMA_VERSION, "entries": len(overview), "recurrent_people_roles": len(people),
                   "recurrent_topics": len(topics), "confirmed_entities": len(confirmed),
                   "relationship_counts": relation_counts,
                   "generated_text_is_evidence": False,
                   "master_sha256": dict(db.execute("SELECT key,value FROM metadata"))["master_sha256"]}
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        (output / "map.json").write_text(json.dumps({"entries": overview, "confirmed_entities": confirmed, "relationship_counts": relation_counts}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        nav = ["# Entry navigation", "", "Generated from SQLite. This text is a view, not new evidence.", ""]
        for e in overview:
            nav.append(f"- **[{e['entry_id']}](../../../../emotion_master.md#{e['entry_id'].lower()}) — {e['title']}** — people/roles: {e['people_roles'] or 'none'}; topics: {e['topics'] or 'none'}; period: {e['event_period'] or 'unknown'}")
        (output / "navigation.md").write_text("\n".join(nav)+"\n", encoding="utf-8")
        def grouped(filename, heading, field, groups):
            lines=[f"# {heading}", "", "Generated from exact master metadata. Repeated labels do not create new identity claims.", ""]
            for g in groups:
                ids=[r[0] for r in db.execute("SELECT entry_id FROM entry_metadata WHERE field=? AND value=? ORDER BY entry_id",(field,g['label']))]
                lines.append(f"- **{g['label']}** ({g['entries']}): "+", ".join(f"[{x}](../../../../emotion_master.md#{x.lower()})" for x in ids))
            (output/filename).write_text("\n".join(lines)+"\n",encoding="utf-8")
        grouped("people.md", "People and role index", "people_role", people)
        grouped("themes.md", "Theme index", "topic", topics)
        lines=["# Relationship authority report", "", "Generated from SQLite. Authority levels remain separate.", ""]
        for row in relation_counts:
            lines.append(f"- `{row['authority']}` / `{row['relation']}` / `{row['status']}`: {row['count']}")
        lines += ["", "## Confirmed entities", ""]
        for e in confirmed: lines.append(f"- `{e['entity_id']}` — {e['label']} ({e['kind']})")
        (output/"relationships.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        return summary
    finally:
        db.close()


def query(database: Path, entry_id: str | None, text: str | None) -> list[dict]:
    db=connect(database)
    try:
        if entry_id:
            rows=db.execute("SELECT * FROM entry_overview WHERE entry_id=?",(entry_id,))
        elif text:
            rows=db.execute(
                "SELECT o.* FROM entry_overview o JOIN entries e USING(entry_id) WHERE e.raw_markdown LIKE ? ORDER BY o.entry_id", (f"%{text}%",))
        else: raise ArchiveError("Use --entry or --text")
        return [dict(x) for x in rows]
    finally: db.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True)
    m=sub.add_parser("migrate"); m.add_argument("--master",type=Path,required=True); m.add_argument("--organization-state",type=Path,required=True); m.add_argument("--questions",type=Path); m.add_argument("--derived-graph",type=Path); m.add_argument("--database",type=Path,required=True)
    v=sub.add_parser("validate"); v.add_argument("--database",type=Path,required=True); v.add_argument("--master",type=Path)
    r=sub.add_parser("render"); r.add_argument("--database",type=Path,required=True); r.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("query"); q.add_argument("--database",type=Path,required=True); g=q.add_mutually_exclusive_group(required=True); g.add_argument("--entry"); g.add_argument("--text")
    a=p.parse_args(argv)
    try:
        if a.command=="migrate": result=migrate(a.master,a.organization_state,a.database,a.questions,a.derived_graph)
        elif a.command=="validate": result=validate(a.database,a.master)
        elif a.command=="render": result=render(a.database,a.output)
        else: result=query(a.database,a.entry,a.text)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if not isinstance(result,dict) or result.get("status")!="failed" else 1
    except (OSError,sqlite3.Error,ArchiveError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({"error":str(exc)})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
