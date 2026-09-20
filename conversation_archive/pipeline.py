"""Build deterministic derived files; no source file is opened for writing."""

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
from .adapters import chatgpt, claude
from .inventory import (
    inventory,
    verify_sources,
    load_source,
    canonical,
    sha_file,
    resolve_pointer,
)
from .model import FormatError, SCHEMA_VERSION, IMPORTER_VERSION

KINDS = ("conversations", "messages", "attachments")


def write_json(path, obj):
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def resolve_attachment(a, source):
    """Check an explicit relative filename under configured roots; never fetch URLs.

    A filename match is a candidate, not proof of an attachment's identity.
    """
    name = a["filename"]
    if (
        not isinstance(name, str)
        or not name
        or a["attachment_kind"] == "multimodal_reference"
    ):
        return
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name:
        a["availability"] = "unsafe_reference"
        return
    roots = sorted(
        {l["attachment_root"] for l in source["locations"] if l.get("attachment_root")}
    )
    if not roots:
        return
    candidates = []
    for root in roots:
        p = (Path(root) / rel).resolve()
        if not p.is_relative_to(Path(root)):
            a["availability"] = "unsafe_reference"
            return
        if p.is_file():
            candidates.append(p)
    if not candidates:
        a["availability"] = "missing"
        return
    if len(candidates) > 1:
        a["availability"] = "ambiguous_candidates"
        return
    a.update(
        availability="local_filename_match",
        resolved_path=str(candidates[0]),
        sha256=sha_file(candidates[0]),
    )


def normalize(config_path, output_path):
    out = Path(output_path).resolve()
    inv = inventory(config_path)
    for root in inv["source_roots"]:
        if out.is_relative_to(Path(root)):
            raise FormatError("Output must be outside source directories")
    for src in inv["sources"]:
        for loc in src["locations"]:
            if Path(loc["path"]).is_relative_to(out):
                raise FormatError("Output would contain an input file")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FormatError(
            "Output already exists and is not empty; choose a new dataset directory"
        )
    verify_sources(inv)
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="." + out.name + "-staging-", dir=out.parent))
    handles = {
        k: (stage / (k + ".jsonl")).open("w", encoding="utf-8", newline="\n")
        for k in KINDS
    }
    counts = Counter()
    issues = []
    try:
        for source in inv["sources"]:
            data = load_source(source)
            adapter = chatgpt if source["provider"] == "chatgpt" else claude
            for i, original in enumerate(data):
                conv, msgs, atts, warnings = adapter.normalize(original, source, i)
                for a in atts:
                    resolve_attachment(a, source)
                issues.extend(warnings)
                for kind, records in [
                    ("conversations", [conv]),
                    ("messages", msgs),
                    ("attachments", atts),
                ]:
                    for r in records:
                        handles[kind].write(canonical(r) + "\n")
                        counts[kind] += 1
        for h in handles.values():
            h.close()
        verify_sources(inv)
        manifest = dict(
            schema_version=SCHEMA_VERSION,
            importer_version=IMPORTER_VERSION,
            inventory=inv,
            files={
                k
                + ".jsonl": dict(
                    sha256=sha_file(stage / (k + ".jsonl")), records=counts[k]
                )
                for k in KINDS
            },
            importer_warnings=issues,
        )
        write_json(stage / "manifest.json", manifest)
        report = validate(stage)
        if report["errors"]:
            codes = Counter(e["code"] for e in report["errors"])
            raise FormatError(
                "Validation failed; output not installed. " + str(dict(codes))
            )
        write_json(stage / "validation_report.json", report)
        if out.exists():
            out.rmdir()  # only the prechecked empty output directory
        stage.rename(out)
        return report
    finally:
        for h in handles.values():
            h.close()
        if stage.exists():
            shutil.rmtree(stage)  # our own incomplete staging output only


def validate(dataset_path):
    from .validation import validate as run

    return run(Path(dataset_path))


def inspect_record(dataset_path, kind="messages", record_id=None, line=None):
    if kind not in KINDS:
        raise FormatError("Unknown record kind")
    if (record_id is None) == (line is None):
        raise FormatError("Specify exactly one record id or line")
    if line is not None and line < 1:
        raise FormatError("Line must be at least 1")
    root = Path(dataset_path)
    manifest = json.loads((root / "manifest.json").read_text())
    p = root / (kind + ".jsonl")
    if sha_file(p) != manifest["files"][p.name]["sha256"]:
        raise FormatError("Clean file hash mismatch")
    selected = None
    with p.open(encoding="utf-8") as f:
        for i, s in enumerate(f, 1):
            obj = json.loads(s)
            if (line == i) or (record_id is not None and obj["record_id"] == record_id):
                selected = obj
                break
    if selected is None:
        raise FormatError("Record not found")
    src = next(
        s
        for s in manifest["inventory"]["sources"]
        if s["source_id"] == selected["provenance"]["source_id"]
    )
    verify_sources({"sources": [src]})
    data = load_source(src)
    return dict(
        clean=selected,
        original=resolve_pointer(data, selected["provenance"]["json_pointer"]),
        source_locations=src["locations"],
    )
