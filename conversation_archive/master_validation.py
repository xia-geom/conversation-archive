"""Structural checks for the living Markdown archive, never factual verification."""

from collections import Counter
import hashlib
import re
import unicodedata
from urllib.parse import unquote


def _scan(text):
    active, protected, errors = [], [], []
    fence = None
    archive = None
    block = []
    for line in text.splitlines(keepends=True):
        if archive is not None:
            block.append(line)
            if f"<!-- ARCHIVED_TEXT_END {archive} -->" in line:
                protected.append("".join(block))
                archive = None
                block = []
            continue
        if fence:
            block.append(line)
            if re.fullmatch(
                r" {0,3}"
                + re.escape(fence[0])
                + "{"
                + str(fence[1])
                + r",}[ \t]*(?:\n)?",
                line,
            ):
                protected.append("".join(block))
                fence = None
                block = []
            continue
        marker = re.search(r"<!-- ARCHIVED_TEXT_BEGIN (\S+) -->", line)
        if marker:
            archive = marker[1]
            block = [line]
            continue
        match = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if match and not (match[1][0] == "`" and "`" in match[2]):
            fence = (match[1][0], len(match[1]))
            block = [line]
            continue
        active.append(line)
    if fence or archive:
        errors.append(
            {
                "code": "unclosed_protected_block",
                "detail": "Unclosed fence or archive marker",
            }
        )
    protected.extend(re.findall(r"data:[^\s)]+", text))
    # Owner-confirmation sources are immutable evidence, including questions outside fences.
    for match in re.finditer(r'<a id="src-(027|028)"></a>', text):
        tail = text[match.end() :]
        end = re.search(r'<a id="src-\d{3}"></a>|<a id="coverage"></a>', tail)
        protected.append(
            text[
                match.start() : match.end() + (end.start() if end else len(tail))
            ].rstrip()
        )
    return "".join(active), protected, errors


def _slug(title):
    title = re.sub(r"<[^>]+>", "", title).lower()
    title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", title)
    return "".join(
        c for c in title if c in "-_ " or unicodedata.category(c)[0] in "LN"
    ).replace(" ", "-")


def master_snapshot(text):
    active, protected, errors = _scan(text)
    anchors = re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)["\']\s*>', active)
    headings = re.findall(r"^ {0,3}#{1,6}\s+(.+?)\s*#*$", active, re.M)
    entries = re.findall(r"^ {0,3}#{1,6}\s+(E\d{4})\b", active, re.M)
    corrections = re.findall(r"^ {0,3}#{1,6}\s+(COR\d{4})\b", active, re.M)
    sources = [a.upper() for a in anchors if re.fullmatch(r"src-\d{3}", a)]
    slugs, seen = [], Counter()
    for heading in headings:
        slug = _slug(heading)
        n = seen[slug]
        seen[slug] += 1
        slugs.append(slug + (f"-{n}" if n else ""))
    metadata = {}
    if text.startswith("---\n"):
        front = text.split("---", 2)[1]
        metadata = dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", front, re.M))
        metadata = {k: v.strip("\"'") for k, v in metadata.items()}
    return {
        "entries": entries,
        "sources": sources,
        "corrections": corrections,
        "anchors": anchors,
        "heading_slugs": slugs,
        "metadata": metadata,
        "links": re.findall(r"\]\(#([^\s)]+)\)", active),
        "protected_hashes": [hashlib.sha256(b.encode()).hexdigest() for b in protected],
        "scan_errors": errors,
    }


def validate_master(text, before=None):
    snap = master_snapshot(text)
    errors, warnings = list(snap["scan_errors"]), []

    def error(code, detail):
        errors.append({"code": code, "detail": detail})

    for key in ("entries", "sources", "corrections", "anchors"):
        for value, n in Counter(snap[key]).items():
            if n > 1:
                error("duplicate_" + key, value)
    targets = set(snap["anchors"] + snap["heading_slugs"])
    for target in sorted(set(snap["links"])):
        if unquote(target) not in targets:
            error("broken_internal_link", target)
    counts = {key: len(snap[key]) for key in ("entries", "sources", "corrections")}
    fields = [
        ("entries", "entry_count", "next_entry_id", r"E(\d+)"),
        ("sources", "distinct_retained_sources", "next_source_id", r"SRC-(\d+)"),
        ("corrections", "correction_count", "next_correction_id", r"COR(\d+)"),
    ]
    for key, countfield, nextfield, pattern in fields:
        meta = snap["metadata"]
        if countfield in meta and meta[countfield] != str(counts[key]):
            error("counter_mismatch", countfield)
        if nextfield in meta:
            match = re.fullmatch(pattern, meta[nextfield])
            high = max((int(re.fullmatch(pattern, v)[1]) for v in snap[key]), default=0)
            if not match or int(match[1]) <= high:
                error("next_id_collision", nextfield)
            elif int(match[1]) != high + 1:
                warnings.append({"code": "next_id_gap", "detail": nextfield})
    if before is not None:
        old = master_snapshot(before)
        for key in ("entries", "sources", "corrections"):
            for missing in sorted(set(old[key]) - set(snap[key])):
                error("removed_" + key, missing)
        missing = Counter(old["protected_hashes"]) - Counter(snap["protected_hashes"])
        if missing:
            error(
                "protected_material_changed",
                f"{sum(missing.values())} protected blocks lost or changed",
            )
    return {
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
        "status": "failed" if errors else "passed",
    }


def _report_sections(text):
    # Preserve source quotations but detect only active report headings.
    active, _, _ = _scan(text)
    return re.findall(r"^#{1,6}\s+(R\d{4})\b", active, re.M)


def validate_reports(
    master, detailed, simple, before_detailed=None, before_simple=None
):
    errors, warnings = [], []
    ids = [_report_sections(t) for t in (detailed, simple)]
    for name, values in zip(("detailed", "simple"), ids):
        if len(values) != len(set(values)):
            errors.append({"code": "duplicate_report_id", "detail": name})
    if set(ids[0]) != set(ids[1]):
        errors.append(
            {
                "code": "report_id_mismatch",
                "detail": str(sorted(set(ids[0]) ^ set(ids[1]))),
            }
        )
    for name, new, old in [
        ("detailed", detailed, before_detailed),
        ("simple", simple, before_simple),
    ]:
        if old is not None and not new.startswith(old):
            errors.append(
                {
                    "code": "report_history_changed",
                    "detail": name + " must retain the exact old prefix",
                }
            )
    sections = re.split(r"(?m)^#{1,6}\s+R\d{4}\b", _scan(simple)[0])[1:]
    for ident, section in zip(ids[1], sections):
        if not (
            re.search(r"\|\s*Before\s*\|\s*After\s*\|", section, re.I)
            or (
                re.search(r"^#{2,6} Before\s*$", section, re.M)
                and re.search(r"^#{2,6} After\s*$", section, re.M)
            )
        ):
            errors.append({"code": "simple_comparison_missing", "detail": ident})
    if not ids[0]:
        warnings.append(
            {"code": "no_report_changes", "detail": "No change register headings"}
        )
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "counts": {"detailed_changes": len(ids[0]), "simple_changes": len(ids[1])},
    }
