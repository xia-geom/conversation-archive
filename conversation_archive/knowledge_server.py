"""Loopback-only read API and local Cytoscape viewer; no archive writes or LLM calls."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from .knowledge_store import MapError, Store, bounded, encoded, sha

ASSET_COMMIT = "716a1cb6c6015d57b674abe626deaeb5e817ee30"
ASSET_VERSION = "3.34.3"
ASSETS = {
    "cytoscape.min.js": ("dist/cytoscape.min.js", "5f3b5b529546d5af1fc5628590af033b74511a5b6f789f5f4682845863228b91"),
    "LICENSE.cytoscape": ("LICENSE", "eb319c6e6f233607f71e8e2f450391751883cfc0eeb3ca7ef574c13d1d9c2203"),
}
STATIC = Path(__file__).with_name("map_web")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


def verified_assets(directory):
    output = {}
    for name, (_, expected) in ASSETS.items():
        path = Path(directory) / name
        if path.is_symlink() or not path.is_file():
            raise MapError("Install the pinned map assets before starting the viewer")
        data = path.read_bytes()
        if sha(data) != expected:
            raise MapError("Map asset checksum mismatch; do not execute an unverified library")
        output[name] = data
    return output


def install_assets(output, download=False, source=None):
    """Explicit one-time public-library download, or verified offline copy; never archive data."""
    import os
    import tempfile
    output = Path(output)
    if output.exists():
        verified_assets(output)
        return {"status": "already_verified", "cytoscape_version": ASSET_VERSION}
    if (not download and source is None) or (download and source is not None):
        raise MapError("Choose --download or --from-directory for the one-time asset installation")
    payloads = verified_assets(source) if source is not None else {}
    if download:
        for name, (upstream_path, expected) in ASSETS.items():
            url = f"https://raw.githubusercontent.com/cytoscape/cytoscape.js/{ASSET_COMMIT}/{upstream_path}"
            with urlopen(url, timeout=30) as response:
                if response.geturl() != url:
                    raise MapError("Unexpected asset redirect")
                payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024 or sha(payload) != expected:
                raise MapError("Upstream asset does not match the pinned checksum")
            payloads[name] = payload
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # A directory is installed only after both pinned files have been verified.
    with tempfile.TemporaryDirectory(prefix=".map-assets-", dir=output.parent) as temporary:
        staged = Path(temporary) / "assets"
        staged.mkdir(mode=0o700)
        for name, payload in payloads.items():
            (staged / name).write_bytes(payload)
        if output.exists():
            raise MapError("Asset directory appeared during installation; nothing replaced")
        os.rename(staged, output)
    return {"status": "installed", "cytoscape_version": ASSET_VERSION}


class MapHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, store, assets, port=0):
        bounded(port, 0, 65535, "port")
        self.store = store
        self.token = secrets.token_urlsafe(32)
        checked = verified_assets(assets)
        self.files = {
            "/": ("text/html; charset=utf-8", (STATIC / "index.html").read_bytes()),
            "/app.js": ("text/javascript; charset=utf-8", (STATIC / "app.js").read_bytes()),
            "/styles.css": ("text/css; charset=utf-8", (STATIC / "styles.css").read_bytes()),
            "/cytoscape.min.js": ("text/javascript; charset=utf-8", checked["cytoscape.min.js"]),
            "/LICENSE.cytoscape": ("text/plain; charset=utf-8", checked["LICENSE.cytoscape"]),
        }
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(5)
        return sock, address

    @property
    def launch_url(self):
        return self.origin + "/#token=" + self.token


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # No query text, archive contents, or access token in request logs.

    def send(self, code, body, mime="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else encoded(body).encode("utf-8")
        self.send_response(code)
        for name, value in {
            "Content-Type": mime, "Content-Length": str(len(data)), "Cache-Control": "no-store",
            "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "Cross-Origin-Resource-Policy": "same-origin",
            "Connection": "close",
        }.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        expected_host = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get("Origin")
        if (self.headers.get("Host") != expected_host
                or (origin is not None and origin != self.server.origin)
                or self.headers.get("Sec-Fetch-Site", "none") not in ("none", "same-origin")):
            return self.send(403, {"error": "Local same-origin requests only"})
        if len(self.path) > 4096:
            return self.send(414, {"error": "Request too large"})
        parsed = urlsplit(self.path)
        if parsed.path in self.server.files and not parsed.query:
            mime, body = self.server.files[parsed.path]
            return self.send(200, body, mime)
        if not parsed.path.startswith("/api/"):
            return self.send(404, {"error": "Unknown route"})
        supplied = self.headers.get("X-Archive-Token", "")
        if not secrets.compare_digest(supplied, self.server.token):
            return self.send(403, {"error": "Open the complete session URL printed by the local server"})
        try:
            params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=16)
            if any(len(values) != 1 for values in params.values()):
                raise MapError("Duplicate query parameter")
            params = {k: v[0] for k, v in params.items()}
            route = parsed.path.removeprefix("/api/")
            permitted = {"meta": set(), "search": {"q", "kind", "limit", "offset"},
                         "node": {"id"}, "edge": {"id"},
                         "graph": {"id", "depth", "statuses", "mentions", "relation", "node_limit", "edge_limit"}}
            if route not in permitted:
                return self.send(404, {"error": "Unknown API route"})
            if not set(params) <= permitted[route]:
                raise MapError("Unknown query parameter")
            store = self.server.store
            if route == "meta":
                result = store.metadata()
            elif route == "search":
                result = store.search(params.get("q", ""), params.get("kind", ""),
                                      int(params.get("limit", "25")), int(params.get("offset", "0")))
            elif route in ("node", "edge"):
                result = getattr(store, route)(params.get("id", ""))
            else:
                if params.get("mentions", "0") not in ("0", "1"):
                    raise MapError("mentions must be 0 or 1")
                result = store.neighborhood(params.get("id", ""), int(params.get("depth", "1")),
                    tuple(params.get("statuses", "observed_text,user_confirmed").split(",")),
                    params.get("mentions", "0") == "1", params.get("relation", ""),
                    int(params.get("node_limit", "100")), int(params.get("edge_limit", "300")))
            self.send(200, result)
        except MapError as exc:
            self.send(409, {"error": str(exc)})
        except ValueError:
            self.send(400, {"error": "Invalid query parameters"})
        except Exception:
            self.send(500, {"error": "The local query failed; verify the index and rebuild if needed"})

    def do_POST(self):
        self.send(405, {"error": "Read-only viewer; use the reviewed correction workflow"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST
