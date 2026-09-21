"""Synthetic storage, provenance, queries, correction lifecycle and loopback boundary."""
from contextlib import closing
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from conversation_archive import organization as org
from conversation_archive.knowledge_map import demo, main
from conversation_archive.knowledge_server import MapHTTPServer, install_assets, verified_assets
from conversation_archive.knowledge_store import MapError, Store, build, file_hash, projection


class MapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "demo"
        self.report = demo(self.root)
        self.run = self.root / "organization"
        self.database = self.root / "map.sqlite3"
        self.store = Store(self.database, self.run)

    def event(self, operations):
        return {"event_id": "invented-next", "actor": "Test reviewer", "answer": "Synthetic correction",
                "expected_state_sha256": org.digest(org.read_state(self.run)), "operations": operations}

    def test_exact_entries_and_counts(self):
        source = org.read_state(self.run)
        self.assertEqual(self.report["entry_count"], 7)
        self.assertFalse(self.report["complete_knowledge_claimed"])
        for entry in source["data"]["entries"]:
            row = self.store.node("entry:" + entry["entry_id"])
            self.assertEqual(row["text"], entry["text"])
            self.assertEqual(row["source_record"], entry)

    def test_build_preserves_input_and_repeat_is_idempotent(self):
        before, database = file_hash(self.run / "state.json"), file_hash(self.database)
        self.assertEqual(build(self.run, self.database)["status"], "already_current")
        self.assertEqual(before, file_hash(self.run / "state.json"))
        self.assertEqual(database, file_hash(self.database))

    def test_read_only_database(self):
        with closing(self.store.connect()) as db, self.assertRaises(sqlite3.OperationalError):
            db.execute("DELETE FROM nodes")

    def test_integrity_and_foreign_keys(self):
        with closing(self.store.connect()) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_foreign_key_endpoint_validation(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO edges VALUES ('bad','absent','absent','continues','proposed','test',0,'{}')")

    def test_exact_id_and_prefix_search(self):
        self.assertEqual(self.store.search("E0004")["nodes"][0]["id"], "entry:E0004")
        self.assertTrue(any(n["kind"] == "project" for n in self.store.search("orch")["nodes"]))

    def test_unicode_and_unmatched_entry_is_searchable(self):
        result = self.store.search("薄荷")
        self.assertEqual(result["nodes"][0]["entry_id"], "E0007")
        self.assertEqual(self.store.neighborhood("entry:E0007")["edges"], [])

    def test_literal_query_not_sql_or_fts_syntax(self):
        self.assertEqual(self.store.search("\" OR 1=1 --")["nodes"], [])
        self.assertEqual(self.store.search("*")["nodes"], [])
        self.assertEqual(self.store.search("' OR DROP TABLE nodes;")["nodes"], [])
        self.assertEqual(self.store.metadata()["entry_count"], 7)

    def test_kind_filter_and_pagination(self):
        first = self.store.search(kind="entry", limit=2)
        second = self.store.search(kind="entry", limit=2, offset=2)
        self.assertTrue(first["has_more"])
        self.assertFalse({n["id"] for n in first["nodes"]} & {n["id"] for n in second["nodes"]})
        self.assertTrue(all(n["kind"] == "entry" for n in first["nodes"]))

    def test_bounds_reject_boolean_and_bad_values(self):
        for kwargs in ({"limit": True}, {"limit": 101}, {"offset": -1}, {"kind": "unrecognized"}, {"query": "x" * 201}):
            with self.assertRaises(MapError):
                self.store.search(**kwargs)
        for kwargs in ({"depth": 3}, {"depth": True}, {"node_limit": 201}, {"edge_limit": 501},
                       {"statuses": ("user_confirmed", "user_confirmed")}, {"statuses": ()}, {"relation": "same_everything"}):
            with self.assertRaises(MapError):
                self.store.neighborhood("entry:E0001", **kwargs)

    def test_default_filters_do_not_traverse_rejected_or_proposed(self):
        graph = self.store.neighborhood("entry:E0004", depth=2)
        self.assertTrue(all(e["status"] in ("observed_text", "user_confirmed") for e in graph["edges"]))
        self.assertNotIn("entry:E0006", {n["id"] for n in graph["nodes"]})
        graph = self.store.neighborhood("entry:E0004", statuses=("rejected",))
        self.assertIn("entry:E0006", {n["id"] for n in graph["nodes"]})

    def test_proposals_explicitly_opted_in(self):
        graph = self.store.neighborhood("entry:E0005", statuses=("proposed",))
        self.assertEqual([e["relation"] for e in graph["edges"]], ["revises"])

    def test_collapsed_links_retain_every_primitive_witness(self):
        graph = self.store.neighborhood("entity:project:orchard")
        self.assertEqual(len(graph["nodes"]), 6)
        edge = next(e for e in graph["edges"] if e["source"] == "entry:E0001")
        full = self.store.edge(edge["id"])
        self.assertEqual(full["origin"], "display_projection")
        self.assertEqual(len(full["payload"]["derived_from"]), 2)
        self.assertEqual(full["supporting_answers"][0]["rule_id"], "demo-project")
        q = full["payload"]["evidence"][0]
        self.assertEqual(self.store.node("entry:" + q["entry_id"])["text"][q["start"]:q["end"]], q["quote"])

    def test_raw_mention_mode_uses_real_edges(self):
        graph = self.store.neighborhood("entity:project:orchard", depth=2, mentions=True)
        self.assertTrue(any(n["kind"] == "mention" for n in graph["nodes"]))
        self.assertFalse(any(e["projected"] for e in graph["edges"]))

    def test_same_spelling_not_merged(self):
        graph = self.store.neighborhood("entity:person:workshop-rowan", depth=2)
        self.assertNotIn("entry:E0006", {n["id"] for n in graph["nodes"]})
        self.assertEqual(len(self.store.search("Rowan", kind="person")["nodes"]), 1)

    def test_context_association_has_answer_not_fabricated_quote(self):
        edge = self.store.neighborhood("entity:period:first-phase")["edges"][0]
        detail = self.store.edge(edge["id"])
        self.assertEqual(detail["payload"].get("evidence", []), [])
        self.assertEqual(detail["supporting_answers"][0]["rule_id"], "demo-context")

    def test_caps_are_disclosed(self):
        graph = self.store.neighborhood("entity:project:orchard", node_limit=2)
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertTrue(graph["truncated"])
        graph = self.store.neighborhood("entity:project:orchard", edge_limit=1)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertTrue(graph["truncated"])

    def test_relation_filter_precedes_traversal(self):
        graph = self.store.neighborhood("entry:E0004", relation="continues", depth=2)
        self.assertEqual({n["id"] for n in graph["nodes"]}, {"entry:E0004", "entry:E0005"})

    def test_missing_nodes_and_edges(self):
        with self.assertRaises(MapError):
            self.store.node("absent")
        with self.assertRaises(MapError):
            self.store.edge("absent")

    def test_source_drift_rejected_and_snapshot_only_explicit(self):
        org.apply(self.run, self.event([{"op": "revoke", "rule_id": "revoke-demo", "target": "demo-project"}]))
        with self.assertRaises(MapError):
            self.store.search("Orchard")
        self.assertTrue(Store(self.database).search("Orchard")["nodes"])
        with self.assertRaises(MapError):
            build(self.run, self.database)

    def test_revocation_rebuild_removes_only_dependent_links(self):
        org.apply(self.run, self.event([{"op": "revoke", "rule_id": "revoke-demo", "target": "demo-project"}]))
        new = self.root / "new.sqlite3"
        build(self.run, new)
        store = Store(new, self.run)
        self.assertEqual(store.search("Orchard", kind="project")["nodes"], [])
        self.assertTrue(store.search("Rowan", kind="person")["nodes"])
        with closing(store.connect()) as db:
            self.assertEqual(db.execute("SELECT active FROM rules WHERE id='demo-project'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM rules").fetchone()[0], 6)

    def test_database_mutation_is_detected(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE nodes SET text='changed' WHERE id='entry:E0001'")
            db.commit()
        with self.assertRaises(MapError):
            self.store.search()
        with self.assertRaises(MapError):
            Store(self.database)

    def test_search_index_mutation_is_detected(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("DELETE FROM search")
            db.commit()
        with self.assertRaises(MapError):
            Store(self.database)

    def test_no_absolute_path_in_public_metadata(self):
        self.assertNotIn(str(self.run), json.dumps(self.store.metadata()))
        self.assertNotIn("source_path", self.report)

    def test_output_file_owner_only(self):
        self.assertEqual(self.database.stat().st_mode & 0o077, 0)

    def test_cli_refuses_implicit_historical_mode(self):
        with self.assertRaises(SystemExit):
            main(["search", "--database", str(self.database)])

    def test_unsupported_or_corrupt_source_is_not_installed(self):
        path = self.run / "state.json"
        value = org.load(path)
        value["version"] = "future-version"
        org.atomic_write(path, value)
        output = self.root / "bad.sqlite3"
        with self.assertRaises(org.OrganizationError):
            build(self.run, output)
        self.assertFalse(output.exists())


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "demo"
        demo(self.root)
        store = Store(self.root / "map.sqlite3", self.root / "organization")
        with patch("conversation_archive.knowledge_server.verified_assets", return_value={"cytoscape.min.js": b"/* test */", "LICENSE.cytoscape": b"Test license"}):
            self.server = MapHTTPServer(store, self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)

    def get(self, path, headers=None, method="GET"):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        client.close()
        return result

    def auth(self, **extra):
        return {"X-Archive-Token": self.server.token, **extra}

    def test_host_binding_and_random_token(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertGreaterEqual(len(self.server.token), 40)
        self.assertIn("#token=", self.server.launch_url)

    def test_api_needs_token_static_does_not_expose_archive(self):
        status, _, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertNotIn(b'"source_record"', body)
        self.assertEqual(self.get("/api/meta")[0], 403)
        self.assertEqual(self.get("/api/meta", self.auth())[0], 200)

    def test_cross_origin_and_rebinding_rejected(self):
        self.assertEqual(self.get("/api/meta", self.auth(Origin="https://example.invalid"))[0], 403)
        self.assertEqual(self.get("/api/meta", self.auth(Host="attacker.invalid"))[0], 403)
        self.assertEqual(self.get("/api/meta", self.auth(**{"Sec-Fetch-Site": "cross-site"}))[0], 403)
        self.assertEqual(self.get("/api/meta", self.auth(Origin="null"))[0], 403)

    def test_no_writes_and_no_file_server(self):
        self.assertEqual(self.get("/api/meta", self.auth(), method="POST")[0], 405)
        for path in ("/../state.json", "/state.json", "/map.sqlite3", "/api/sql?query=SELECT+1"):
            self.assertEqual(self.get(path, self.auth())[0], 404)

    def test_security_headers(self):
        _, headers, _ = self.get("/")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_duplicate_and_unknown_parameters_rejected(self):
        self.assertEqual(self.get("/api/search?q=a&q=b", self.auth())[0], 409)
        self.assertEqual(self.get("/api/search?sql=SELECT", self.auth())[0], 409)
        self.assertEqual(self.get("/api/search?limit=no", self.auth())[0], 400)

    def test_http_search_and_graph(self):
        status, _, body = self.get("/api/search?q=E0004", self.auth())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["nodes"][0]["entry_id"], "E0004")
        status, _, body = self.get("/api/graph?id=entity:project:orchard&depth=1", self.auth())
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["nodes"]), 6)


class AssetTests(unittest.TestCase):
    def test_network_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp, patch("conversation_archive.knowledge_server.urlopen") as fetch:
            with self.assertRaises(MapError):
                install_assets(Path(tmp) / "assets")
            fetch.assert_not_called()

    def test_corrupt_assets_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cytoscape.min.js").write_text("malicious replacement")
            with self.assertRaises(MapError):
                verified_assets(tmp)

    def test_offline_copy_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"; source.mkdir()
            data = b"test fixture only"
            (source / "test.js").write_bytes(data)
            assets = {"test.js": ("unused", hashlib.sha256(data).hexdigest())}
            with patch("conversation_archive.knowledge_server.ASSETS", assets), patch("conversation_archive.knowledge_server.urlopen") as fetch:
                destination = Path(tmp) / "dest"
                self.assertEqual(install_assets(destination, source=source)["status"], "installed")
                self.assertEqual(install_assets(destination)["status"], "already_verified")
                fetch.assert_not_called()

    def test_frontend_never_interprets_archive_strings_as_html(self):
        root = Path(__file__).resolve().parents[1] / "conversation_archive/map_web"
        script = (root / "app.js").read_text()
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)
        self.assertNotIn("https://", script)
        self.assertIn("textContent", script)
