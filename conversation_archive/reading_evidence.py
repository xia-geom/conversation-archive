"""Small evidence adapter: exact publication round trips and explicit references.

No lookup by name, implicit directory scanning, source fetching or model calls.
A reference contributes evidence/recorded decisions, never replacement prose.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .reading_document import DATA, LINK, Document, need, references, sha


def unwrap_source(body, source_id):
    """Decode only the recognized generated wrapper, not arbitrary source fences."""
    prefix = re.match(r"\s*## Source " + re.escape(source_id.upper()) + r"\n\n"
        r"Evidence access: (complete_available_block|selected_exact_excerpt)\. "
        r"Full input block SHA-256: `([a-f0-9]{64})`\.\n", body)
    need(prefix is not None, "Malformed generated source wrapper")
    status, full_sha = prefix.groups()
    rest = body[prefix.end():]
    meta = re.match(r"\n<!-- reading-text (\d+)(?: ([a-f0-9]{64}))? -->\n", rest)
    if meta:
        rest = rest[meta.end():]
    opening = re.match(r"\n*(`{3,})text\n", rest)
    need(opening is not None, "Generated evidence has no exact text fence")
    end = list(re.finditer(r"^" + re.escape(opening[1]) + r"[ \t]*$", rest, re.M))
    need(len(end) == 1, "Ambiguous generated evidence boundary")
    retained = rest[opening.end():end[0].start()]
    suffix = rest[end[0].end():]
    # Only the adapter's navigation line is permitted after the immutable text.
    need(not suffix.strip() or re.fullmatch(r"\s*Evidence dependencies: [^\n]+\n?\s*", suffix),
         "Unexpected text outside generated evidence")
    if meta:
        size = int(meta[1])
        need(size <= len(retained) and retained[size:] in {"", "\n"}, "Generated evidence length mismatch")
        retained = retained[:size]
        digest = meta[2] or (full_sha if status == "complete_available_block" else None)
        need(digest is not None and sha(retained) == digest, "Generated evidence text hash mismatch")
    else:
        need(status == "complete_available_block", "Legacy excerpt lacks a verifiable text hash; recover its original first")
        candidates = {retained, retained[:-1] if retained.endswith("\n") else retained}
        matches = [text for text in candidates if sha(text) == full_sha]
        need(len(matches) == 1, "Legacy generated evidence hash mismatch")
        retained = matches[0]
    complete = status == "complete_available_block"
    need(not complete or sha(retained) == full_sha, "Complete evidence disagrees with its original hash")
    need(not DATA.search(retained), "Encoded media is not a generated text source")
    return dict(text=retained, sha256=sha(retained), full_sha256=full_sha,
                complete=complete, published=True)


def load_document(path, reference=None):
    """Overlay a supplied same-collection reference without replacing manual edits."""
    doc = Document.read(path)
    doc.reference_info = None
    doc.reference_associations = {}
    if reference is None:
        return doc
    older = Document.read(reference)
    need(bool(set(doc.entries) & set(older.entries)), "Reference has no shared entries; check the selected collection")
    declared = re.search(r"^Input SHA-256: `([a-f0-9]{64})`", doc.master[:1500], re.M)
    same_lineage = (doc.fingerprint == older.fingerprint
        or declared is not None and declared[1] in {older.fingerprint, sha(older.master)}
        or any(doc.entries[eid]["sha256"] == older.entries[eid]["sha256"] for eid in set(doc.entries) & set(older.entries))
        or any(source.get("full_sha256", source["sha256"]) == older.sources[ref].get("full_sha256", older.sources[ref]["sha256"])
               for ref, source in doc.sources.items() if ref in older.sources))
    need(same_lineage, "Shared entry IDs alone do not establish the same collection")
    # Distinct decision texts require explicit reconciliation, not last-file-wins.
    need(not (doc.decisions and older.decisions) or doc.decisions == older.decisions,
         "Decision contexts differ; reconcile them explicitly before using this reference")
    if not doc.decisions:
        doc.decisions = older.decisions
    for ref, source in older.sources.items():
        present = doc.sources.get(ref)
        if present:
            if present["sha256"] == source["sha256"]:
                continue
            # A retained excerpt can be restored from its exact original only.
            if not present.get("complete", True) and source.get("complete", True):
                need(present.get("full_sha256") == source["sha256"] and present["text"] in source["text"],
                     "Reference conflicts with an existing source excerpt")
            elif not source.get("complete", True) and present.get("complete", True):
                need(source.get("full_sha256") == present["sha256"] and source["text"] in present["text"],
                     "Reference excerpt conflicts with an existing source")
                continue
            else:
                need(False, "The same source ID has different evidence; do not merge silently")
        doc.sources[ref] = deepcopy(source)
        if present and not present.get("complete", True):
            doc.sources[ref]["preferred_excerpt"] = present["text"]
    doc.reference_info = {"sha256": older.fingerprint, "decisions_sha256": sha(older.decisions)}
    doc.reference_associations = {eid: [ref for ref in entry["refs"] if ref.startswith("src-")]
                                  for eid, entry in older.entries.items() if eid in doc.entries}
    # Source offsets refer to their own document, never to the current master.
    return doc


def correction_dependencies(doc, roots):
    """Return only finite source identifiers; no reading instructions are followed."""
    critical = {ref for ref in roots if re.fullmatch(r"cor\d+", ref)}
    dependencies = {}
    queue = sorted(critical)
    visited = set()
    while queue:
        ref = queue.pop(0)
        if ref in visited:
            continue
        visited.add(ref)
        source = doc.sources.get(ref)
        if source is None:
            continue
        # These are identifiers in historical text, not executable instructions.
        linked = {m[2] for m in LINK.finditer(source["text"])
                  if re.fullmatch(r"(?:src-[A-Za-z0-9_-]+|cor\d+)", m[2])}
        dependencies[ref] = sorted(linked)
        critical.update(linked)
        need(len(critical) <= 512, "Correction dependency limit exceeded; narrow the evidence scope")
        queue.extend(sorted(x for x in linked if re.fullmatch(r"cor\d+", x)))
    return critical, dependencies


def evidence_plan(doc, entries, excerpts, limit, strict=False):
    """Preserve compact correction dependencies; never recursively copy an archive."""
    roots = {ref for e in entries.values() for ref in e["refs"]} | set(references(doc.decisions, True))
    entry_ids = {eid.lower() for eid in entries}
    roots -= entry_ids
    critical, dependencies = correction_dependencies(doc, roots)
    refs = roots | critical
    need(set(excerpts) <= refs, "Selected evidence must be cited by the reading document")
    evidence, access, full_hashes = {}, {}, {}
    critical_bytes = 0
    for ref in sorted(refs):
        source = doc.sources.get(ref)
        if ref in excerpts:
            evidence[ref] = excerpts[ref]
            access[ref] = "selected_exact_excerpt"
        elif source and source.get("preferred_excerpt"):
            evidence[ref] = source["preferred_excerpt"]
            access[ref] = "selected_exact_excerpt"
        elif source and not DATA.search(source["text"]) and (
            source.get("published", False) or len(source["text"]) <= limit
            or ref in critical and len(source["text"]) <= 20000):
            evidence[ref] = source["text"]
            access[ref] = "complete_available_block" if source.get("complete", True) else "selected_exact_excerpt"
        else:
            access[ref] = "external_not_included" if source else "not_available_in_input"
        if source:
            full_hashes[ref] = source.get("full_sha256", source["sha256"])
        if ref in critical and ref in evidence:
            critical_bytes += len(evidence[ref].encode())
    need(critical_bytes <= 2 * 1024 * 1024, "Correction evidence budget exceeded; select shorter exact excerpts")
    missing = sorted(critical - set(evidence))
    need(not strict or not missing, "Critical correction evidence is unavailable; supply the reference or an exact excerpt")
    return evidence, access, full_hashes, dependencies, missing
