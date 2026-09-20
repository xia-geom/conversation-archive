"""Small shared record conventions; original JSON always remains evidence."""

import hashlib

SCHEMA_VERSION = "1.0"
IMPORTER_VERSION = "0.1.1"


class FormatError(ValueError):
    """An export cannot be represented safely without guessing."""


def pointer_token(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def record_id(kind, source_id, pointer):
    return (
        kind
        + ":"
        + hashlib.sha256((source_id + "\n" + pointer).encode("utf-8")).hexdigest()
    )


def provenance(source, pointer):
    return {
        "source_id": source["source_id"],
        "sha256": source["sha256"],
        "json_pointer": pointer,
    }


def base(kind, source, pointer):
    return {
        "schema_version": SCHEMA_VERSION,
        "importer_version": IMPORTER_VERSION,
        "record_id": record_id(kind, source["source_id"], pointer),
        "provider": source["provider"],
        "provenance": provenance(source, pointer),
    }


def warning(code, record_id, detail):
    return {"code": code, "record_id": record_id, "detail": detail}


def require_id(value, label):
    if not isinstance(value, str) or not value:
        raise FormatError(f"{label} must be a nonempty string")
    return value
