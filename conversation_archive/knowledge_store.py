"""Rebuildable SQLite projection of organization format 1.0; never a new authority."""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from . import organization as org
from . import machine_archive as archive

VERSION = "1.0"
STATUSES = ("observed_text", "user_confirmed", "derived", "proposed", "rejected")
KINDS = ("entry", "mention", "source", "period_text", "person_role", "topic",
         "record_kind", "period_bucket", "confirmed_entity", *sorted(org.KINDS))
MAX_SOURCE_BYTES = 64 * 1024 * 1024


class MapError(ValueError):
    """A projection, query, or source does not satisfy the map contract."""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise MapError(f"{name} must be between {low} and {high}")
    return value


def file_hash(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise MapError("Source exceeds the 64 MiB map-input limit")
    return sha(data)


def title(text):
    first = next((line.strip() for line in text.splitlines() if line.strip()), "Untitled entry")
    return re.sub(r"^#{1,6}\s*", "", first)[:120]


def projection(state):
    """Preserve primitive edges; add clearly marked entry/entity display shortcuts."""
    graph = org.graph(state)
    nodes, edges, rules = [], [], []
    entry_ids = {e["entry_id"] for e in graph["entries"]}
    mention_ids = {m["mention_id"] for m in graph["mentions"]}
    if entry_ids & mention_ids or (entry_ids | mention_ids) & {e["node_id"] for e in graph["entities"]}:
        raise MapError("Input node identities collide")
    mapping = {eid: "entry:" + eid for eid in entry_ids}
    mapping.update({mid: "mention:" + mid for mid in mention_ids})
    mapping.update({e["node_id"]: e["node_id"] for e in graph["entities"]})
    for entry in graph["entries"]:
        nodes.append((mapping[entry["entry_id"]], "entry", entry["entry_id"], title(entry["text"]),
                      entry["text"], encoded(entry)))
    for mention in graph["mentions"]:
        nodes.append((mapping[mention["mention_id"]], "mention", mention["entry_id"],
                      mention["quote"], mention["quote"], encoded(mention)))
    for entity in graph["entities"]:
        nodes.append((entity["node_id"], entity["kind"], "", entity["label"], "", encoded(entity)))
    primitive = {}
    for edge in graph["edges"]:
        eid = "edge:" + sha(encoded(edge).encode())[:32]
        primitive[(edge["source"], edge["target"], edge["relation"])] = eid
        origin = ("literal_catalog_match" if edge["relation"] == "mentions" else
                  "supplied_proposal" if "proposal_id" in edge else "recorded_owner_answer")
        edges.append((eid, mapping[edge["source"]], mapping[edge["target"]], edge["relation"],
                      edge["status"], origin, 0, encoded(edge)))
    groups = defaultdict(list)
    by_mention = {m["mention_id"]: m for m in graph["mentions"]}
    for mid, assignment in graph["assignments"].items():
        groups[(by_mention[mid]["entry_id"], assignment["entity"])].append(mid)
    for (entry, entity), mids in sorted(groups.items()):
        evidence, support, derived = [], set(), []
        for mid in sorted(mids):
            evidence.append(by_mention[mid])
            support.update(graph["assignments"][mid]["rule_ids"])
            derived.extend([primitive[(entry, mid, "mentions")], primitive[(mid, entity, "refers_to")]])
        payload = dict(source=entry, target=entity, relation="refers_to", status="user_confirmed",
                       evidence=evidence, rule_ids=sorted(support), derived_from=derived,
                       note="Display shortcut for entry → mention → entity; not an additional assertion.")
        eid = "projection:" + sha(encoded(payload).encode())[:32]
        edges.append((eid, mapping[entry], entity, "refers_to", "user_confirmed",
                      "display_projection", 1, encoded(payload)))
    active = set(graph["active_rule_ids"])
    for event in state["events"]:
        for rule in event["operations"]:
            payload = dict(event_id=event["event_id"], actor=event["actor"], answer=event["answer"], operation=rule)
            rules.append((rule["rule_id"], int(rule["rule_id"] in active), encoded(payload)))
    return {"nodes": sorted(nodes), "edges": sorted(edges), "rules": sorted(rules)}


def archive_fingerprint(root):
    """Watch every immutable snapshot file, not just its manifest."""
    root = Path(root)
    manifest = archive.load_json(root / "manifest.json")
    expected = {f"{name}.jsonl" for name in (*archive.TABLES, "nodes")}
    if set(manifest.get("files", {})) != expected:
        raise MapError("Snapshot file inventory is incomplete or unfamiliar")
    parts = [("manifest.json", file_hash(root / "manifest.json"))]
    for name in sorted(manifest.get("files", {})):
        if (root / name).is_symlink():
            raise MapError("Snapshot source file cannot be a symlink")
        parts.append((name, file_hash(root / name)))
    return sha(encoded(parts).encode())


def archive_projection(root):
    """Project a validated machine snapshot without changing its authority labels."""
    report = archive.validate(root)
    if report["status"] != "passed":
        raise MapError("Authoritative snapshot failed validation")
    records = archive.archive_records(root)
    source_nodes = archive.load_jsonl(Path(root) / "nodes.jsonl")
    entries = {e["entry_id"]: e for e in records["entries"]}
    mentions = {m["mention_id"]: m for m in records["mentions"]}
    nodes, edges, rules = [], [], []
    # The archive has both E0001 and entry:E0001 graph aliases. The map uses
    # one entry node, retaining original endpoint IDs inside edge payloads.
    def canonical(node_id):
        if node_id in entries:
            return "entry:" + node_id
        if node_id in mentions:
            return "mention:" + node_id
        return node_id
    seen = set()
    for source in source_nodes:
        node_id = canonical(source["node_id"])
        if node_id in seen:
            continue
        seen.add(node_id)
        entry = entries.get(node_id.removeprefix("entry:")) if node_id.startswith("entry:") else None
        mention = mentions.get(node_id.removeprefix("mention:")) if node_id.startswith("mention:") else None
        kind = "entry" if entry else "mention" if mention else source["node_type"]
        label = entry["title"] if entry else source["label"]
        text = entry["raw_markdown"] if entry else mention["quote"] if mention else ""
        payload = entry if entry else mention if mention else source
        nodes.append((node_id, kind, entry["entry_id"] if entry else mention["entry_id"] if mention else "",
                      label, text, encoded(payload)))
    for relation in records["relationships"]:
        payload = dict(relation)
        payload["evidence"] = json.loads(relation["evidence_json"])
        payload["rule_ids"] = json.loads(relation["rule_ids_json"])
        edges.append((relation["relationship_id"], canonical(relation["source_id"]),
                      canonical(relation["target_id"]), relation["relation"], relation["status"],
                      relation["authority"], 0, encoded(payload)))
    entry_mention = defaultdict(list)
    for relation in records["relationships"]:
        if (relation["relation"] == "mentions" and relation["source_id"] in entries
                and relation["target_id"] in mentions):
            entry_mention[relation["target_id"]].append(relation)
    shortcuts = defaultdict(list)
    for relation in records["relationships"]:
        if (relation["relation"] != "refers_to" or relation["status"] != "user_confirmed"
                or relation["source_id"] not in mentions):
            continue
        mention = mentions[relation["source_id"]]
        for witness in entry_mention[relation["source_id"]]:
            if witness["source_id"] == mention["entry_id"]:
                shortcuts[(mention["entry_id"], relation["target_id"])].append((mention, witness, relation))
    for (entry_id, entity_id), witnesses in sorted(shortcuts.items()):
        payload = {"source": entry_id, "target": entity_id, "relation": "refers_to",
                   "status": "user_confirmed", "authority": "display_projection",
                   "evidence": [dict(entry_id=m["entry_id"], start=m["start"],
                                     end=m["end"], quote=m["quote"]) for m, _, _ in witnesses],
                   "rule_ids": sorted({rid for _, _, r in witnesses for rid in json.loads(r["rule_ids_json"])}),
                   "derived_from": [edge["relationship_id"] for _, first, second in witnesses
                                    for edge in (first, second)],
                   "note": "Display shortcut for entry → mention → confirmed entity; not an additional assertion."}
        edge_id = "projection:" + sha(encoded(payload).encode())[:32]
        edges.append((edge_id, "entry:" + entry_id, entity_id, "refers_to",
                      "user_confirmed", "display_projection", 1, encoded(payload)))
    events = {e["event_id"]: e for e in records["correction_events"]}
    for rule in records["correction_rules"]:
        payload = dict(rule)
        payload["operation_payload"] = json.loads(rule["payload_json"])
        payload["event"] = events[rule["event_id"]]
        rules.append((rule["rule_id"], int(rule["active"]), encoded(payload)))
    return {"nodes": sorted(nodes), "edges": sorted(edges), "rules": sorted(rules)}


SCHEMA = """
PRAGMA user_version=1;
PRAGMA foreign_keys=ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, entry_id TEXT NOT NULL,
                    label TEXT NOT NULL, text TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX nodes_kind ON nodes(kind, label);
CREATE TABLE edges (id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES nodes(id),
                    target TEXT NOT NULL REFERENCES nodes(id), relation TEXT NOT NULL,
                    status TEXT NOT NULL, origin TEXT NOT NULL, projected INTEGER NOT NULL,
                    payload TEXT NOT NULL);
CREATE INDEX edges_source ON edges(source, status, projected);
CREATE INDEX edges_target ON edges(target, status, projected);
CREATE TABLE rules (id TEXT PRIMARY KEY, active INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, label, text, tokenize='unicode61 remove_diacritics 2');
"""


def build(run, database):
    """Read a checked organization state; publish a new owner-readable DB."""
    run, database = Path(run).resolve(), Path(database).absolute()
    source = run / "state.json"
    before = file_hash(source)
    state = org.read_state(run)
    records = projection(state)
    if before != file_hash(source):
        raise MapError("Source changed while indexing")
    metadata = {"format_version": VERSION, "source_format": "organization-1.0",
                "state_sha256": org.digest(state), "source_file_sha256": before,
                "source_path": str(source), "projection_sha256": sha(encoded(records).encode()),
                "entry_count": len(state["data"]["entries"]), "node_count": len(records["nodes"]),
                "edge_count": len(records["edges"]), "rule_count": len(records["rules"]),
                "authority": "derived_read_only_index", "complete_knowledge_claimed": False}
    return publish(records, metadata, database, lambda: file_hash(source))


def build_archive(root, database):
    """Index a checked authoritative snapshot; the output is only a view."""
    root, database = Path(root).resolve(), Path(database).absolute()
    before = archive_fingerprint(root)
    records = archive_projection(root)
    if before != archive_fingerprint(root):
        raise MapError("Snapshot changed while indexing")
    manifest = archive.load_json(root / "manifest.json")
    metadata = {"format_version": VERSION, "source_format": "machine_archive-1.0",
                "state_sha256": manifest["snapshot_id"], "source_file_sha256": before,
                "source_path": str(root), "projection_sha256": sha(encoded(records).encode()),
                "entry_count": len([n for n in records["nodes"] if n[1] == "entry"]),
                "node_count": len(records["nodes"]), "edge_count": len(records["edges"]),
                "rule_count": len(records["rules"]), "authority": "derived_read_only_index",
                "complete_knowledge_claimed": False}
    return publish(records, metadata, database, lambda: archive_fingerprint(root))


def publish(records, metadata, database, current_fingerprint):
    """Install a verified projection once; refuse a changed existing output."""
    if database.exists() or database.is_symlink():
        if database.is_symlink():
            raise MapError("Database output cannot be a symlink")
        previous = Store(database)
        if previous.meta == metadata:
            return {"status": "already_current", **previous.public_metadata()}
        raise MapError("Existing index differs; build into a new database path")
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".map-", suffix=".sqlite3", dir=database.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temp)) as db:
            db.executescript(SCHEMA)
            db.executemany("INSERT INTO metadata VALUES (?,?)", [(k, encoded(v)) for k, v in metadata.items()])
            db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?)", records["nodes"])
            db.executemany("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?)", records["edges"])
            db.executemany("INSERT INTO rules VALUES (?,?,?)", records["rules"])
            db.executemany("INSERT INTO search VALUES (?,?,?)", [(n[0], n[3], n[4]) for n in records["nodes"]])
            db.commit()
        Store(Path(temp))
        if metadata["source_file_sha256"] != current_fingerprint():
            raise MapError("Source changed before index installation")
        with open(temp, "rb") as stream:
            os.fsync(stream.fileno())
        # Hard-link publication refuses races and preserves any existing destination.
        os.link(temp, database)
    finally:
        Path(temp).unlink(missing_ok=True)
    return {"status": "built", **Store(database).public_metadata()}


def signature(path):
    st = Path(path).stat()
    return st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


class Store:
    def __init__(self, database, run=None, archive_root=None):
        self.path = Path(database).resolve(strict=True)
        self.signature = signature(self.path)
        if run is not None and archive_root is not None:
            raise MapError("Choose one watched source")
        self.run = Path(run).resolve() if run is not None else None
        self.archive_root = Path(archive_root).resolve() if archive_root is not None else None
        with closing(self.connect()) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise MapError("Unsupported map database format")
            self.meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}
            if self.meta.get("format_version") != VERSION:
                raise MapError("Unsupported map projection version")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
                raise MapError("Database integrity or foreign-key check failed")
            actual = {t: [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY id")] for t in ("nodes", "edges", "rules")}
            if sha(encoded(actual).encode()) != self.meta["projection_sha256"]:
                raise MapError("Index content changed; rebuild from the source state")
            expected_search = sorted((n[0], n[3], n[4]) for n in actual["nodes"])
            if sorted(tuple(r) for r in db.execute("SELECT id,label,text FROM search")) != expected_search:
                raise MapError("Search projection does not match nodes")
            for table, key in (("nodes", "node_count"), ("edges", "edge_count"), ("rules", "rule_count")):
                if len(actual[table]) != self.meta[key]:
                    raise MapError("Index count does not match metadata")
            if sum(n[1] == "entry" for n in actual["nodes"]) != self.meta["entry_count"]:
                raise MapError("Entry census mismatch")
        self.check_source()

    def connect(self):
        if signature(self.path) != self.signature:
            raise MapError("Database changed during this session; restart with a rebuilt index")
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        return db

    def check_source(self):
        if self.run is not None:
            try:
                current = file_hash(self.run / "state.json")
            except OSError as exc:
                raise MapError("Bound source is unavailable; rebuild or explicitly use snapshot-only mode") from exc
            if current != self.meta["source_file_sha256"]:
                raise MapError("Source state changed; rebuild the index before continuing")
        if self.archive_root is not None:
            if self.meta.get("source_format") != "machine_archive-1.0":
                raise MapError("Map index does not match an authoritative snapshot")
            try:
                current = archive_fingerprint(self.archive_root)
            except (OSError, ValueError, KeyError) as exc:
                raise MapError("Bound snapshot is unavailable; rebuild or explicitly use snapshot-only mode") from exc
            if current != self.meta["source_file_sha256"]:
                raise MapError("Snapshot changed; rebuild the index before continuing")

    def public_metadata(self):
        return {k: v for k, v in self.meta.items() if k != "source_path"}

    def metadata(self):
        self.check_source()
        with closing(self.connect()) as db:
            kinds = [dict(r) for r in db.execute("SELECT kind,COUNT(*) AS count FROM nodes GROUP BY kind ORDER BY kind")]
            hubs = [self.summary(r) for r in db.execute("SELECT * FROM nodes WHERE kind NOT IN ('entry','mention') ORDER BY kind,label LIMIT 20")]
            relations = [r[0] for r in db.execute("SELECT DISTINCT relation FROM edges ORDER BY relation")]
        return {**self.public_metadata(), "kinds": kinds, "hubs": hubs, "relations": relations,
                "source_watch": self.run is not None or self.archive_root is not None, "statuses": list(STATUSES)}

    @staticmethod
    def summary(row):
        return {k: row[k] for k in ("id", "kind", "entry_id", "label")}

    def search(self, query="", kind="", limit=25, offset=0):
        self.check_source()
        bounded(limit, 1, 100, "limit")
        bounded(offset, 0, 10000, "offset")
        if not isinstance(query, str) or len(query) > 200 or kind not in ("", *KINDS):
            raise MapError("Invalid search text or node kind")
        params, conditions = [], []
        tokens = re.findall(r"\w+", query, re.UNICODE)[:12]
        if tokens:
            phrase = " AND ".join('"' + word + '"*' for word in tokens)
            conditions.append("(n.id IN (SELECT id FROM search WHERE search MATCH ?) OR n.id=? OR n.entry_id=?)")
            params.extend([phrase, query, query])
        elif query.strip():
            return {"nodes": [], "has_more": False}
        if kind:
            conditions.append("n.kind=?")
            params.append(kind)
        else:
            conditions.append("n.kind!='mention'")
        where = " WHERE " + " AND ".join(conditions)
        with closing(self.connect()) as db:
            rows = db.execute("SELECT n.* FROM nodes n" + where + " ORDER BY (kind='entry'),kind,label,id LIMIT ? OFFSET ?",
                              (*params, limit + 1, offset)).fetchall()
        return {"nodes": [self.summary(r) for r in rows[:limit]], "has_more": len(rows) > limit}

    def node(self, node_id):
        self.check_source()
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
            if row is None:
                raise MapError("Unknown node")
        return {**self.summary(row), "text": row["text"], "source_record": json.loads(row["payload"])}

    def edge(self, edge_id):
        self.check_source()
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM edges WHERE id=?", (edge_id,)).fetchone()
            if row is None:
                raise MapError("Unknown relationship")
            payload = json.loads(row["payload"])
            rules = []
            for rid in payload.get("rule_ids", []):
                rule = db.execute("SELECT * FROM rules WHERE id=?", (rid,)).fetchone()
                if rule is None or not rule["active"]:
                    raise MapError("Relationship references inactive or missing support")
                rules.append({"rule_id": rid, **json.loads(rule["payload"])})
        return {**dict(row), "payload": payload, "supporting_answers": rules}

    def neighborhood(self, focus, depth=1, statuses=("observed_text", "user_confirmed"),
                     mentions=False, relation="", node_limit=100, edge_limit=300):
        self.check_source()
        bounded(depth, 1, 2, "depth")
        bounded(node_limit, 1, 200, "node_limit")
        bounded(edge_limit, 1, 500, "edge_limit")
        if (type(mentions) is not bool or not statuses or len(statuses) != len(set(statuses))
                or not set(statuses) <= set(STATUSES)):
            raise MapError("Choose distinct supported relationship statuses")
        if relation:
            with closing(self.connect()) as db:
                if db.execute("SELECT 1 FROM edges WHERE relation=? LIMIT 1", (relation,)).fetchone() is None:
                    raise MapError("Unknown relationship type")
        focus_node = self.node(focus)
        seen, frontier, selected, truncated = {focus}, {focus}, {}, False
        with closing(self.connect()) as db:
            for _ in range(depth):
                if not frontier:
                    break
                slots = ",".join("?" for _ in frontier)
                conditions = [f"(source IN ({slots}) OR target IN ({slots}))",
                              "status IN (" + ",".join("?" for _ in statuses) + ")",
                              "projected=0" if mentions else "(projected=1 OR (source NOT LIKE 'mention:%' AND target NOT LIKE 'mention:%'))"]
                params = [*sorted(frontier), *sorted(frontier), *statuses]
                if relation:
                    conditions.append("relation=?")
                    params.append(relation)
                rows = db.execute("SELECT * FROM edges WHERE " + " AND ".join(conditions) + " ORDER BY id LIMIT ?",
                                  (*params, edge_limit + 1)).fetchall()
                if len(rows) > edge_limit:
                    truncated = True
                next_frontier = set()
                for row in rows[:edge_limit]:
                    if row["id"] in selected:
                        continue
                    new = {row["source"], row["target"]} - seen
                    if len(seen) + len(new) > node_limit or len(selected) >= edge_limit:
                        truncated = True
                        continue
                    seen.update(new)
                    next_frontier.update(new)
                    selected[row["id"]] = {k: row[k] for k in ("id", "source", "target", "relation", "status", "origin", "projected")}
                frontier = next_frontier
            slots = ",".join("?" for _ in seen)
            nodes = [self.summary(r) for r in db.execute(f"SELECT * FROM nodes WHERE id IN ({slots}) ORDER BY id", sorted(seen))]
        return {"focus": focus_node["id"], "nodes": nodes, "edges": list(selected.values()),
                "truncated": truncated, "depth": depth, "state_sha256": self.meta["state_sha256"],
                "note": "Undirected neighborhood exploration; arrows retain assertion direction. Paths do not establish new facts."}
