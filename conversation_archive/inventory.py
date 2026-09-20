"""Read sources in place; identify payload bytes separately from ZIP containers."""

import hashlib
import json
import math
from pathlib import Path
import re
import tomllib
import zipfile
from .model import FormatError, SCHEMA_VERSION, IMPORTER_VERSION

CONVERSATIONS = re.compile(r"^conversations(?:-\d+)?\.json$")


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def strict_loads(data):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise FormatError(
                    "Duplicate JSON object key: import refused rather than losing a value"
                )
            out[k] = v
        return out

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise FormatError("Non-finite JSON numeric value")
        return number

    def invalid(_):
        raise FormatError("Non-finite JSON numeric value")

    try:
        return json.loads(
            data.decode("utf-8-sig") if isinstance(data, bytes) else data,
            object_pairs_hook=pairs,
            parse_constant=invalid,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError) as e:
        raise FormatError("Invalid UTF-8 JSON source") from e


def read_location(location):
    path = Path(location["path"])
    if location["member"] is None:
        return path.read_bytes()
    with zipfile.ZipFile(path) as z:
        return z.read(location["member"])


def inventory(config_path):
    config_path = Path(config_path).resolve()
    with config_path.open("rb") as f:
        config = tomllib.load(f)
    inputs = config.get("sources")
    if not isinstance(inputs, list) or not inputs:
        raise FormatError("Config requires one or more [[sources]]")
    groups = {}
    source_roots = []
    for item in inputs:
        provider = item.get("provider")
        if provider not in ("chatgpt", "claude"):
            raise FormatError("Provider must be chatgpt or claude")
        if not isinstance(item.get("path"), str):
            raise FormatError("Source path must be a string")
        p = (config_path.parent / Path(item["path"]).expanduser()).resolve()
        if not p.exists():
            raise FormatError(f"Source does not exist: {p}")
        ar = item.get("attachment_root")
        ar = str((config_path.parent / Path(ar).expanduser()).resolve()) if ar else None
        if ar and not Path(ar).is_dir():
            raise FormatError("Attachment root must be an existing directory")
        if p.is_dir():
            source_roots.append(str(p))
            files = sorted(
                x
                for x in p.iterdir()
                if x.is_file() and CONVERSATIONS.fullmatch(x.name)
            )
        else:
            files = [p]
        found = 0
        for f in files:
            container_hash = sha_file(f)
            if f.suffix.lower() == ".zip":
                with zipfile.ZipFile(f) as z:
                    members = sorted(
                        n for n in z.namelist() if CONVERSATIONS.fullmatch(Path(n).name)
                    )
                    if len(members) != len(set(members)):
                        raise FormatError("Duplicate ZIP member names")
                    payloads = [(n, z.read(n)) for n in members]
            elif f.suffix.lower() == ".json":
                payloads = [(None, f.read_bytes())]
            else:
                raise FormatError(
                    "Only JSON files, conversation directories, or ZIP containers are supported"
                )
            if sha_file(f) != container_hash:
                raise FormatError("Source changed while inventorying")
            for member, payload in payloads:
                found += 1
                h = hashlib.sha256(payload).hexdigest()
                key = provider + ":" + h
                loc = dict(
                    path=str(f),
                    member=member,
                    container_sha256=container_hash,
                    attachment_root=ar,
                )
                if key not in groups:
                    groups[key] = dict(
                        source_id=key,
                        provider=provider,
                        sha256=h,
                        bytes=len(payload),
                        locations=[],
                    )
                if loc not in groups[key]["locations"]:
                    groups[key]["locations"].append(loc)
        if not found:
            raise FormatError(f"No conversation JSON payloads found in {p}")
    for s in groups.values():
        s["locations"].sort(
            key=lambda x: (x["path"], x["member"] or "", x["attachment_root"] or "")
        )
    expected = config.get("expected", {})
    allowed = {
        f"{p}_{k}" for p in ("chatgpt", "claude") for k in ("conversations", "messages")
    }
    if not isinstance(expected, dict) or any(
        k not in allowed or type(v) != int or v < 0 for k, v in expected.items()
    ):
        raise FormatError(
            "Expected counts must be nonnegative integers for provider conversations/messages"
        )
    return dict(
        schema_version=SCHEMA_VERSION,
        importer_version=IMPORTER_VERSION,
        sources=[groups[k] for k in sorted(groups)],
        expected=expected,
        source_roots=sorted(set(source_roots)),
    )


def verify_sources(inv):
    """Every alias must still match, even when only one duplicate was imported."""
    seen = {}
    for s in inv["sources"]:
        for loc in s["locations"]:
            path = loc["path"]
            if path not in seen:
                seen[path] = sha_file(path)
            if seen[path] != loc["container_sha256"]:
                raise FormatError("Source container changed: " + path)
            data = read_location(loc)
            if (
                len(data) != s["bytes"]
                or hashlib.sha256(data).hexdigest() != s["sha256"]
            ):
                raise FormatError("Source payload changed: " + path)


def load_source(source):
    payload = read_location(source["locations"][0])
    if hashlib.sha256(payload).hexdigest() != source["sha256"]:
        raise FormatError("Source hash mismatch")
    data = strict_loads(payload)
    if not isinstance(data, list):
        raise FormatError("Conversation export must be a JSON array")
    return data


def resolve_pointer(obj, pointer):
    if pointer == "":
        return obj
    if not pointer.startswith("/"):
        raise FormatError("Invalid JSON pointer")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        obj = obj[int(token)] if isinstance(obj, list) else obj[token]
    return obj
