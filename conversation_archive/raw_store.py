"""Local content-addressed ChatGPT evidence store; no model or master writes.

python3 -m conversation_archive.raw_store --help
Original JSON/ZIP inputs stay in place. Only exact conversation JSON fragments
are deduplicated; ZIP containers, media and other members are not archived here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from .inventory import CONVERSATIONS, sha_file, strict_loads
from .model import FormatError
from .raw_json import VERSION, RawStoreError, analyze, digest, encoded, fingerprint

MAX_PAYLOAD = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_FILES = 1000
MAX_ZIP_MEMBERS = 100000
HEX = re.compile(r"[0-9a-f]{64}")


def _read(path: Path, cap=MAX_TOTAL) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RawStoreError("Expected a regular file, not a symlink")
    with path.open("rb") as stream:
        value = stream.read(cap + 1)
    if len(value) > cap:
        raise RawStoreError("File exceeds the configured byte bound; no truncation used")
    return value


def _json(path):
    try:
        return strict_loads(_read(path))
    except FormatError as exc:
        raise RawStoreError("Invalid store JSON") from exc


def _safe(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.absolute().is_relative_to(root.absolute()) or ".." in Path(relative).parts:
        raise RawStoreError("Path escapes raw store")
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise RawStoreError("Symlinks are not supported inside raw-store paths")
        if parent == root:
            break
    return path


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(path: Path, value: bytes) -> bool:
    """Immutable, no-clobber publication; a crash can leave unreferenced objects."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink():
        if _read(path) != value:
            raise RawStoreError("Existing content differs; never overwrite stored evidence")
        return False
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _read(path) != value:
                raise RawStoreError("Concurrent immutable-file conflict")
            return False
        _sync_dir(path.parent)
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def _config(root: Path, namespace=None):
    if root.is_symlink():
        raise RawStoreError("Raw-store root cannot be a symlink")
    config = _json(_safe(root, "store.json"))
    if set(config) != {"version", "provider", "namespace"} or config["version"] != VERSION or config["provider"] != "chatgpt":
        raise RawStoreError("Unsupported raw-store format")
    if namespace is not None and config["namespace"] != namespace:
        raise RawStoreError("Store account namespace differs; use a separate store")
    return config


@contextmanager
def _writer(root: Path, namespace: str):
    try:
        import fcntl
    except ImportError as exc:
        raise RawStoreError("Raw-store writer requires macOS or Linux") from exc
    if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", namespace):
        raise RawStoreError("Namespace must be a short path-free account label")
    if root.is_symlink():
        raise RawStoreError("Raw-store root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (root / "store.json").exists() and any(p.name != ".writer.lock" for p in root.iterdir()):
        raise RawStoreError("Use a new raw-store directory; unrelated files are preserved")
    lock = _safe(root, ".writer.lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RawStoreError("Another writer owns this raw store") from exc
        config = {"version": VERSION, "provider": "chatgpt", "namespace": namespace}
        _publish(_safe(root, "store.json"), encoded(config) + b"\n")
        _config(root, namespace)
        yield config
    finally:
        os.close(fd)


def _blob_path(root: Path, sha: str) -> Path:
    if not isinstance(sha, str) or HEX.fullmatch(sha) is None:
        raise RawStoreError("Invalid content hash")
    return _safe(root, f"blobs/sha256/{sha[:2]}/{sha[2:]}")


def _export_path(root: Path, export_id: str) -> Path:
    if not isinstance(export_id, str) or not export_id.startswith("EX-") or not HEX.fullmatch(export_id[3:]):
        raise RawStoreError("Invalid export ID")
    return _safe(root, f"exports/{export_id}.json")


def _source_files(sources, root):
    found = []
    for source in sources:
        path = Path(source).expanduser().absolute()
        if path.is_dir():
            found.extend(sorted(p for p in path.iterdir() if CONVERSATIONS.fullmatch(p.name) and p.is_file()))
        else:
            found.append(path)
    paths = sorted(set(found))
    if not paths or len(paths) > MAX_FILES:
        raise RawStoreError("No supported inputs or too many input files")
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.resolve().is_relative_to(root.resolve()):
            raise RawStoreError("Inputs must be regular files outside the raw store")
        if path.suffix.lower() not in (".json", ".zip"):
            raise RawStoreError("Use conversation JSON files, a directory, or a ChatGPT ZIP")
    return paths


def _payloads(path, remaining):
    """Read bounded conversation members without extracting any ZIP paths."""
    if path.suffix.lower() != ".zip":
        yield None, _read(path, min(MAX_PAYLOAD, remaining)), 0
        return
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(infos) > MAX_ZIP_MEMBERS or len(set(names)) != len(names):
            raise RawStoreError("ZIP has duplicate names or too many members")
        selected = sorted((i for i in infos if CONVERSATIONS.fullmatch(PurePosixPath(i.filename).name)), key=lambda i: i.filename)
        if not selected or len(selected) > MAX_FILES:
            raise RawStoreError("ZIP contains no supported conversation payloads or too many")
        if sum(i.file_size for i in selected) > remaining:
            raise RawStoreError("Selected ZIP payloads exceed total byte bound")
        for info in selected:
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename or info.flag_bits & 1:
                raise RawStoreError("Unsafe or encrypted conversation member")
            if info.file_size > MAX_PAYLOAD:
                raise RawStoreError("ZIP conversation payload exceeds byte bound")
            with archive.open(info) as stream:
                value = stream.read(min(MAX_PAYLOAD, remaining) + 1)
            if len(value) > min(MAX_PAYLOAD, remaining) or len(value) != info.file_size:
                raise RawStoreError("ZIP expanded beyond its declared size or allowed bound")
            remaining -= len(value)
            yield info.filename, value, len(infos) - len(selected)


def ingest(sources, store, namespace: str):
    """Import exact bytes once per distinct fragment, then commit a receipt.

    Source paths/container hashes are local receipt metadata, not evidence IDs.
    Retrying the same import completes interrupted work without replacing blobs.
    No latest pointer is inferred from file dates; comparisons use explicit IDs.
    """
    root = Path(store).expanduser().absolute()
    paths = _source_files(sources, root)
    with _writer(root, namespace) as config:
        payloads, blobs, locations, source_hashes = {}, {}, [], {}
        total = 0
        for path in paths:
            before = sha_file(path)
            source_hashes[path] = before
            for member, data, ignored in _payloads(path, MAX_TOTAL - total):
                total += len(data)
                if total > MAX_TOTAL:
                    raise RawStoreError("Export exceeds total byte bound")
                sha = digest(data)
                if sha not in payloads:
                    description, chunks = analyze(data)
                    payloads[sha] = description
                    if len(payloads) > MAX_FILES:
                        raise RawStoreError("Too many selected payloads in one export")
                    blobs.update(chunks)
                locations.append({"path": str(path), "member": member,
                                  "container_sha256": before, "payload_sha256": sha,
                                  "unarchived_member_count": ignored})
            if sha_file(path) != before:
                raise RawStoreError("Source changed during import")
        body = {**config, "payloads": [payloads[k] for k in sorted(payloads)],
                "preservation": "exact_selected_json_bytes_not_zip_or_media"}
        export_id = "EX-" + fingerprint(body)
        manifest = {**body, "export_id": export_id}
        added, added_bytes = 0, 0
        for sha, value in blobs.items():
            if _publish(_blob_path(root, sha), value):
                added += 1
                added_bytes += len(value)
        for path, before in source_hashes.items():
            if sha_file(path) != before:
                raise RawStoreError("Source changed before manifest commit; unreferenced blobs retained")
        new_export = _publish(_export_path(root, export_id), encoded(manifest) + b"\n")
        receipt = {"version": VERSION, "export_id": export_id, "locations": locations,
                   "originals_moved_or_deleted": False, "media_archived": False}
        receipt_id = "IN-" + fingerprint(receipt)
        _publish(_safe(root, f"receipts/{receipt_id}.json"), encoded(receipt) + b"\n")
        return {"status": "imported" if new_export else "already_present", "export_id": export_id,
                "receipt_id": receipt_id, "payloads": len(payloads),
                "conversation_occurrences": sum(len(p["conversations"]) for p in payloads.values()),
                "message_occurrences": sum(n["message_sha256"] is not None for p in payloads.values() for c in p["conversations"] for n in c["nodes"]),
                "new_blobs": added, "reused_blobs": len(blobs) - added,
                "new_blob_bytes": added_bytes, "model_calls": 0, "master_modified": False}


def load_export(store, export_id: str):
    root = Path(store).expanduser().absolute()
    config = _config(root)
    manifest = _json(_export_path(root, export_id))
    if not isinstance(manifest, dict) or manifest.get("export_id") != export_id:
        raise RawStoreError("Invalid export manifest")
    body = {k: v for k, v in manifest.items() if k != "export_id"}
    if "EX-" + fingerprint(body) != export_id or any(manifest.get(k) != v for k, v in config.items()):
        raise RawStoreError("Export manifest identity or namespace mismatch")
    if set(manifest) != {"version", "provider", "namespace", "payloads", "preservation", "export_id"}:
        raise RawStoreError("Unexpected export manifest fields")
    if not isinstance(manifest.get("payloads"), list) or not manifest["payloads"]:
        raise RawStoreError("Missing payload inventory")
    if len(manifest["payloads"]) > MAX_FILES:
        raise RawStoreError("Too many manifest payloads")
    seen, total = set(), 0
    for payload in manifest["payloads"]:
        if payload["sha256"] in seen:
            raise RawStoreError("Duplicate payload description")
        seen.add(payload["sha256"])
        if type(payload.get("bytes")) is not int or not 0 < payload["bytes"] <= MAX_PAYLOAD:
            raise RawStoreError("Invalid payload byte count")
        if not isinstance(payload.get("parts"), list) or len(payload["parts"]) > 1000000:
            raise RawStoreError("Invalid or oversized recipe")
        parts = []
        size = 0
        for part in payload["parts"]:
            if type(part.get("bytes")) is not int or not 0 < part["bytes"] <= MAX_PAYLOAD:
                raise RawStoreError("Invalid blob byte count")
            data = _read(_blob_path(root, part["sha256"]), MAX_PAYLOAD)
            if digest(data) != part["sha256"] or len(data) != part["bytes"]:
                raise RawStoreError("Corrupt or mismatched evidence blob")
            size += len(data)
            if size > MAX_PAYLOAD:
                raise RawStoreError("Reconstructed payload exceeds byte bound")
            parts.append(data)
        raw = b"".join(parts)
        total += len(raw)
        if total > MAX_TOTAL:
            raise RawStoreError("Reconstructed export exceeds total bound")
        # Independent reconstruction prevents a drifted occurrence index being trusted.
        description, _ = analyze(raw)
        if encoded(description) != encoded(payload):
            raise RawStoreError("Manifest recipe/index does not match reconstructed evidence")
    return manifest


def verify(store, export_id: str):
    manifest = load_export(store, export_id)
    unique = {x["sha256"]: x["bytes"] for p in manifest["payloads"] for x in p["parts"]}
    return {"status": "passed", "export_id": export_id, "payloads": len(manifest["payloads"]),
            "unique_blobs_referenced": len(unique), "unique_blob_bytes_referenced": sum(unique.values()),
            "original_locations_required": False, "complete_export_or_media_claimed": False}


def restore(store, export_id: str, payload_sha: str, output):
    """Explicitly reconstruct one original JSON payload, never an original ZIP."""
    manifest = load_export(store, export_id)
    selected = [p for p in manifest["payloads"] if p["sha256"] == payload_sha]
    if len(selected) != 1:
        raise RawStoreError("Payload hash is not in this export")
    root, output = Path(store).absolute(), Path(output).absolute()
    if output.resolve().is_relative_to(root.resolve()) or output.exists() or output.is_symlink():
        raise RawStoreError("Restore requires a new output path outside the store")
    data = b"".join(_read(_blob_path(root, p["sha256"]), MAX_PAYLOAD) for p in selected[0]["parts"])
    if digest(data) != payload_sha:
        raise RawStoreError("Evidence changed during restoration")
    _publish(output, data)
    return {"status": "restored", "payload_sha256": payload_sha, "bytes": len(data)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ingest", help="Read existing files in place; no inbox copy needed")
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--source", action="append", type=Path, required=True)
    p.add_argument("--namespace", required=True, help="Stable account label; never mix accounts in one store")
    for command in ("verify", "restore", "diff"):
        p = sub.add_parser(command)
        p.add_argument("--store", type=Path, required=True)
        if command == "diff":
            p.add_argument("--before", required=True)
            p.add_argument("--after", required=True)
        else:
            p.add_argument("--export", dest="export_id", required=True)
        if command == "restore":
            p.add_argument("--payload", required=True)
            p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            result = ingest(args.source, args.store, args.namespace)
        elif args.command == "verify":
            result = verify(args.store, args.export_id)
        elif args.command == "restore":
            result = restore(args.store, args.export_id, args.payload, args.output)
        else:
            from .raw_delta import compare
            result = compare(args.store, args.before, args.after)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (RawStoreError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
        # Paths and input snippets in third-party errors remain out of routine output.
        message = str(exc) if isinstance(exc, RawStoreError) else type(exc).__name__
        print(json.dumps({"error": message}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
