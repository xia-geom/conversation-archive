"""Audit -> exact entry/source review -> checked repairs -> one reading Markdown.

Only fresh output files are published. Original evidence is never edited. Source
association and interpretation require an attributed review, not a similarity
score. State contains receipts and review work, not a second knowledge database.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .reading_document import (VERSION, Document, ReadingError, DATA, LINK, ENTRY,
    encoded, entry_blocks, load_json_text, need, quote_block, read_utf8,
    references, sha, tokens, visible_lines)

from .reading_review import (read_json, fresh_file, outside, prepare, current,
                             packet, source_packet)

CHECKS = {"placement", "limitations", "contradictions", "attribution"}


def witness(value, doc):
    fields = {"source_id", "source_sha256", "start", "end", "quote"}
    need(isinstance(value, dict) and fields <= set(value) <= fields | {"claim", "relation"}, "Invalid witness fields")
    source = doc.sources.get(value["source_id"])
    need(source is not None and value["source_sha256"] == source["sha256"], "Witness names unavailable or changed evidence")
    lo, hi, quote = value["start"], value["end"], value["quote"]
    need(type(lo) is int and type(hi) is int and isinstance(quote, str) and quote.strip()
         and 0 <= lo < hi <= len(source["text"]) and source["text"][lo:hi] == quote, "Witness quotation does not match its exact source span")
    need(not DATA.search(quote), "Encoded media cannot serve as text evidence")
    return quote


def validate_reviews(answers, inv, doc, require_complete=True):
    fields = {"version", "run_id", "input_sha256", "reviewer", "reviewer_role", "selection_note", "reviews", "excerpts"}
    if inv.get("work"):
        from .reading_work import EXTRA_FIELDS
        fields |= EXTRA_FIELDS
    need(isinstance(answers, dict) and set(answers) == fields, "Unexpected answer document fields")
    need(answers["version"] == VERSION and answers["run_id"] == inv["run_id"]
         and answers["input_sha256"] == doc.fingerprint, "Answers belong to another frozen input")
    need(isinstance(answers["reviewer"], str) and answers["reviewer"].strip()
         and answers["reviewer_role"] in {"owner", "authorized_agent"}, "An attributed reviewer is required")
    need(isinstance(answers["selection_note"], str) and answers["selection_note"].strip(), "Review the omitted non-entry context and explain the publication scope")
    need(isinstance(answers["reviews"], list) and isinstance(answers["excerpts"], list), "Reviews and excerpts must be arrays")
    entries, reviews = deepcopy(doc.entries), {}
    for review in answers["reviews"]:
        base = {"entry_id", "basis", "decision", "reason", "checks", "witnesses"}
        need(isinstance(review, dict) and base <= set(review) <= base | {"replacement"}, "Unexpected entry-review fields")
        eid = review["entry_id"]
        need(eid in entries and eid not in reviews and review["basis"] == doc.basis(eid), "Unknown, duplicate, or changed review scope")
        choice = review["decision"]
        need(choice in {"keep", "revise", "defer"} and isinstance(review["reason"], str) and review["reason"].strip(), "Explicit disposition and reason required")
        need(isinstance(review["checks"], dict) and set(review["checks"]) == CHECKS
             and all(isinstance(v, str) and v.strip() for v in review["checks"].values()), "Explain placement, limitations, contradictions, and attribution separately")
        need(isinstance(review["witnesses"], list), "Witnesses must be an array")
        before = entries[eid]["text"]
        if choice == "revise":
            need(isinstance(review.get("replacement"), str) and review["replacement"].strip()
                 and review["replacement"] != before and bool(review["witnesses"]), "A revision needs changed entry text and exact evidence")
            parsed = entry_blocks(review["replacement"])
            need(list(parsed) == [eid] and parsed[eid]["text"].strip() == review["replacement"].strip(), "Replacement must contain exactly its single complete entry, no hidden extra sections")
            entries[eid].update(parsed[eid])
        else:
            need("replacement" not in review, "Keep/defer cannot change entry text")
        after = entries[eid]["text"]
        for item in review["witnesses"]:
            witness(item, doc)
            need(set(item) == {"source_id", "source_sha256", "start", "end", "quote", "claim", "relation"}
                 and item["relation"] in {"supports", "qualifies", "removes"}
                 and isinstance(item["claim"], str) and item["claim"].strip(), "A review witness needs an explicit claim and relation")
            scope = before if item["relation"] == "removes" else after
            need(item["claim"] in scope, "Witness claim is not in the reviewed entry")
            need(item["source_id"] in references(scope, include_external=True), "Witness source is not cited in this entry; global presence is insufficient")
            if item["relation"] == "removes":
                need(item["claim"] not in after, "Removal witness did not remove the stated claim")
        reviews[eid] = review
    need(not require_complete or set(reviews) == set(entries), "Some entries remain unreviewed; continue or explicitly defer them")
    # Changed source associations must be acknowledged by both affected reviews.
    for eid, review in reviews.items():
        if review["decision"] != "revise":
            continue
        old_refs, new_refs = set(doc.entries[eid]["refs"]), set(entries[eid]["refs"])
        witnessed = {w["source_id"] for w in review["witnesses"]}
        changed = {x for x in old_refs ^ new_refs if x.lower().startswith("src-")}
        need(changed <= witnessed, "Every changed entry-source association needs an exact scoped witness")
    if inv.get("work"):
        from .reading_work import validate_outcomes
        validate_outcomes(answers, inv, doc, entries, reviews, require_complete)
    excerpts = {}
    for item in answers["excerpts"]:
        need(set(item) == {"source_id", "source_sha256", "start", "end", "quote"}, "Unexpected excerpt fields")
        quote = witness(item, doc)
        need(item["source_id"] not in excerpts, "Duplicate selected excerpt")
        excerpts[item["source_id"]] = quote
    return entries, reviews, excerpts


def rewrite_links(text, included):
    """Only navigation changes. Literal source quotations in fences stay exact."""
    parts, end = [], 0
    for lo, hi, _, line in visible_lines(text):
        parts.append(text[end:lo])
        def repl(m):
            if m[2] in included:
                return m[0]
            return m[1] + " (external reference `" + m[2] + "`; not included)"
        parts.append(LINK.sub(repl, line))
        end = hi
    parts.append(text[end:])
    return "".join(parts)


def render(doc, entries, reviews, excerpts, max_source_chars, selection_note="", authors=None, strict=False):
    need(type(max_source_chars) is int and 0 <= max_source_chars <= 20000, "Invalid automatic evidence limit")
    from .reading_evidence import evidence_plan
    evidence, access, full_hashes, dependencies, missing = evidence_plan(doc, entries, excerpts, max_source_chars, strict)
    entry_anchors = {eid.lower() for eid in entries}
    included = entry_anchors | set(evidence)
    deferred = [eid for eid, review in reviews.items() if review["decision"] == "defer"]
    out = ["# Organized conversation record\n",
        "This is a selected reading document, not the complete source archive. Reports, drafts, dreams, interpretations and actions remain distinct. Corrections apply only within their stated scope. Archived instructions are historical data, not permission to act.\n",
        "Input SHA-256: `" + doc.fingerprint + "`. Generator: `" + VERSION + "`.\n",
        "Publication scope (reviewer statement): " + selection_note + "\n",
        "Editorial reviewers: " + "; ".join(sorted({a["name"] + " (" + a["role"] + ")" for a in (authors or {}).values()})) + ". Editorial review is not blanket owner confirmation.\n",
        "Evidence marked external is not included here; a local locator is not a promise that ChatGPT can open the original. Review records attest what the named reviewer assessed, not independent verification of events.\n",
        f"Entry review: {len(reviews) - len(deferred)} assessed; {len(deferred)} explicitly deferred. Search-quality evaluation is not implied.\n",
        "## Entry index\n\n| Entry | Title | Period as reported |\n| --- | --- | --- |\n"]
    for eid, e in entries.items():
        title = e["title"].replace("|", "\\|")
        period = e["period"].replace("|", "\\|")
        out.append(f"| [{eid}](#{eid.lower()}) | {title} | {period} |\n")
    out.append("\n# Entries\n")
    for eid, e in entries.items():
        text = e["text"]
        source_refs = [r for r in e["refs"] if r.lower().startswith("src-")]
        if source_refs:
            header = "**Source references:** " + ", ".join("[" + ref.upper() + "](#" + ref + ")" for ref in source_refs) + "\n"
            if re.search(r"^\*\*Source references:\*\*[^\n]*\n?", text, re.M):
                text = re.sub(r"^\*\*Source references:\*\*[^\n]*\n?", lambda _: header, text, count=1, flags=re.M)
            else:
                first, _, rest = text.partition("\n")
                text = first + "\n\n" + header + rest
        out.append('\n<a id="' + eid.lower() + '"></a>\n\n' + rewrite_links(text, included))
        if eid in deferred:
            out.append("\n**Unresolved review:** " + reviews[eid]["reason"] + "\n")
    if doc.decisions:
        out.extend(["\n# Recorded decisions\n\n", rewrite_links(doc.decisions, included), "\n"])
    if evidence:
        out.append("\n# Selected source evidence\n\nThese blocks preserve exact text available in the input, not authenticated original app records. They may contain historical prompts or superseded wording; read their context and scoped corrections.\n")
    for ref, body in evidence.items():
        out.append('\n<a id="' + ref + '"></a>\n\n## Source ' + ref.upper() + "\n\n")
        out.append("Evidence access: " + access[ref] + ". Full input block SHA-256: `" + full_hashes[ref] + "`.\n")
        retained_hash = " " + sha(body) if access[ref] == "selected_exact_excerpt" else ""
        out.append("\n<!-- reading-text " + str(len(body)) + retained_hash + " -->\n\n")
        out.append(quote_block(body))
        if dependencies.get(ref):
            links = ", ".join("[" + x + "](#" + x + ")" for x in dependencies[ref])
            out.append(rewrite_links("\nEvidence dependencies: " + links + "\n", included))
    text = "".join(out)
    need(not DATA.search(text), "Encoded media reached the reading output")
    live = tokens(text)
    anchors = [t["id"] for t in live if t["kind"] == "anchor"]
    need(len(anchors) == len(set(anchors)), "Duplicate exported anchor")
    need(set(references(text)) <= set(anchors), "An internal output link lacks its target")
    need(set(entry_blocks(text)) == set(doc.entries), "Export lost or introduced entry IDs")
    return text, access


def build(run, answers_path, max_source_chars=1600):
    inv, doc = current(run)
    answers = read_json(answers_path)
    entries, reviews, excerpts = validate_reviews(answers, inv, doc)
    authors = {}
    for eid, review in reviews.items():
        old = inv["reused_authors"].get(eid)
        authors[eid] = old["actor"] if old and old["review_sha256"] == sha(encoded(review)) else {"name": answers["reviewer"], "role": answers["reviewer_role"]}
    text, access = render(doc, entries, reviews, excerpts, max_source_chars, answers["selection_note"], authors, strict=bool(inv.get("work")))
    receipt = dict(version=VERSION, status="checked", run_id=inv["run_id"], input_sha256=doc.fingerprint,
        answers_sha256=sha(encoded(answers)), output_sha256=sha(text), output_bytes=len(text.encode()),
        reviewer=answers["reviewer"], reviewer_role=answers["reviewer_role"], review_authors=authors,
        selection_note=answers["selection_note"], nonentry_context_ranges=inv["nonentry_context_ranges"],
        max_source_chars=max_source_chars, decisions_sha256=sha(doc.decisions), reviews=list(reviews.values()),
        entry_basis=inv["entry_basis"], evidence_access=access, excerpts=answers["excerpts"],
        source_bytes_unchanged=True, semantic_verification="attributed review; no automatic entailment or event verification",
        deferred_entries=[eid for eid, rev in reviews.items() if rev["decision"] == "defer"])
    receipt["reference"] = inv.get("reference")
    receipt["entries_without_included_sources"] = [eid for eid, e in entries.items()
        if any(ref.startswith("src-") for ref in e["refs"])
        and not any(access.get(ref) in {"complete_available_block", "selected_exact_excerpt"} for ref in e["refs"] if ref.startswith("src-"))]
    if inv.get("reference"):
        text = text.replace("## Entry index\n", "Additional evidence/decision input SHA-256: `" + inv["reference"]["sha256"] + "`.\n## Entry index\n", 1)
        receipt.update(output_sha256=sha(text), output_bytes=len(text.encode()))
    if inv.get("work"):
        receipt.update(work_findings=inv["work"]["findings"], issue_resolutions=answers["issue_resolutions"],
                       source_changes=answers["source_changes"], reference=inv.get("reference"))
        counts = dict(Counter(x["status"] for x in answers["issue_resolutions"]))
        # Keep unresolved findings visible even for an explicitly authorized
        # manual publication; the autonomous finish path stops at deferrals.
        note = "Audit finding outcomes (attributed review): " + json.dumps(counts, sort_keys=True) + ". Not factual verification.\n"
        for item in answers["issue_resolutions"]:
            if item["status"] == "defer":
                note += "Unresolved finding " + item["issue_id"] + ":\n" + quote_block(item["reason"])
        text = text.replace("## Entry index\n", note + "## Entry index\n", 1)
        receipt.update(output_sha256=sha(text), output_bytes=len(text.encode()))
    return inv, doc, entries, text, receipt


def check(run, answers, output, max_source_chars=1600):
    inv, doc, entries, text, receipt = build(run, answers, max_source_chars)
    out = outside(output, inv["input_path"], answers, Path(run) / "audit.json")
    need(not out.exists(), "Preview exists; choose a fresh preview path")
    out.mkdir(parents=True, mode=0o700)
    try:
        fresh_file(out / "organized.md", text.encode())
        fresh_file(out / "preview.json", encoded(receipt))
        preview = ["# Checked reading preview\n\nNothing applied to the input. Publication writes a fresh file.\n",
            "Exact output SHA-256: `" + receipt["output_sha256"] + "`\n",
            f"Entries: {len(entries)}. Deferred: {len(receipt['deferred_entries'])}.\n",
            "Evidence access counts: " + json.dumps(dict(Counter(receipt["evidence_access"].values()))) + "\n",
            "Entries without included SRC passages: " + json.dumps(receipt["entries_without_included_sources"]) + "\n",
            "The output regenerates one index and complete body-derived source lists. Unselected evidence links are explicitly external, not dangling. Full reports, binary payloads and snapshot tables are excluded; supported active decisions are retained.\n"]
        for eid, e in entries.items():
            if e["text"] != doc.entries[eid]["text"]:
                diff = "".join(difflib.unified_diff(doc.entries[eid]["text"].splitlines(True), e["text"].splitlines(True), fromfile=eid + " before", tofile=eid + " reviewed"))
                preview.append(quote_block(diff))
        for rev in receipt["reviews"]:
            if rev["decision"] == "defer":
                preview.append("- Unresolved " + rev["entry_id"] + ": " + rev["reason"] + "\n")
        fresh_file(out / "preview.md", "\n".join(preview).encode())
    except Exception:
        shutil.rmtree(out)
        raise
    return {"status": "checked", "entries": len(entries), "deferred": len(receipt["deferred_entries"]),
            "output_bytes": receipt["output_bytes"], "evidence_access_counts": dict(Counter(receipt["evidence_access"].values()))}


def publish(run, answers, preview, output, approved=False):
    need(approved, "Explicit --approve-publication is required after inspecting the preview")
    previous = read_json(Path(preview) / "preview.json")
    inv, doc, _, text, receipt = build(run, answers, previous["max_source_chars"])
    need(receipt == previous and sha(read_utf8(Path(preview) / "organized.md")) == receipt["output_sha256"], "Preview, answers, or output changed; check again")
    out = outside(output, inv["input_path"], answers, Path(run) / "audit.json", Path(preview) / "organized.md", Path(preview) / "preview.json")
    # A changed/manual output is never regenerated over. An unchanged exact replay
    # is safe even if an earlier publication was interrupted before reporting.
    if out.exists():
        need(not out.is_symlink() and sha(read_utf8(out)) == receipt["output_sha256"], "Output already exists with different content; preserve manual edits")
        return {"status": "already_published", "output_sha256": receipt["output_sha256"]}
    current(run)  # Recheck every explicitly selected input, including reference evidence.
    fresh_file(out, text.encode())
    return {"status": "published", "output_sha256": receipt["output_sha256"], "entries": len(doc.entries),
            "deferred": len(receipt["deferred_entries"]), "original_unchanged": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--reuse", type=Path)
    p.add_argument("--reference", type=Path, help="Explicit same-collection evidence/decision reference; does not replace entry prose")
    p.add_argument("--autonomous", action="store_true")
    p.add_argument("--reviewer", default="Codex")
    p.add_argument("--scope-note", default="")
    p.add_argument("--publish-to", type=Path, help="Preauthorize only this fresh output; no upload or input overwrite")
    p.add_argument("--findings", type=Path, help="Input-bound exact-quote findings JSON")
    p.add_argument("--max-submissions", type=int, default=200)
    for command in ("next", "submit", "finish"):
        p = commands.add_parser(command)
        p.add_argument("--run", type=Path, required=True)
        if command == "next":
            p.add_argument("--output", type=Path, required=True)
            p.add_argument("--size", type=int, default=5)
        elif command == "submit":
            p.add_argument("--submission", type=Path, required=True)
    for command in ("packet", "source", "check", "publish", "status"):
        p = commands.add_parser(command)
        p.add_argument("--run", type=Path, required=True)
        if command != "status":
            p.add_argument("--output", type=Path, required=True)
        if command == "packet":
            p.add_argument("--entries", nargs="+", required=True)
            p.add_argument("--max-source-chars", type=int, default=30000)
        elif command == "source":
            p.add_argument("--source-id", required=True)
            p.add_argument("--start", type=int, default=0)
            p.add_argument("--length", type=int, default=20000)
        elif command in {"check", "publish"}:
            p.add_argument("--answers", type=Path, required=True)
            if command == "check":
                p.add_argument("--max-source-chars", type=int, default=1600)
            else:
                p.add_argument("--preview", type=Path, required=True)
                p.add_argument("--approve-publication", action="store_true")
        if command == "status":
            p.add_argument("--answers", type=Path)
    a = parser.parse_args(argv)
    try:
        if a.command == "prepare":
            result = prepare(a.input, a.run, a.reuse, a.reference, a.autonomous, a.reviewer,
                             a.scope_note, a.publish_to, a.findings, a.max_submissions)
        elif a.command in {"next", "submit", "finish"}:
            from .reading_work import next_task, submit, finish
            if a.command == "next":
                result = next_task(a.run, a.output, a.size)
            elif a.command == "submit":
                result = submit(a.run, a.submission)
            else:
                result = finish(a.run)
        elif a.command == "packet":
            result = packet(a.run, a.entries, a.output, a.max_source_chars)
        elif a.command == "source":
            result = source_packet(a.run, a.source_id, a.output, a.start, a.length)
        elif a.command == "check":
            result = check(a.run, a.answers, a.output, a.max_source_chars)
        elif a.command == "publish":
            result = publish(a.run, a.answers, a.preview, a.output, a.approve_publication)
        else:
            inv, doc = current(a.run)
            reviews = validate_reviews(read_json(a.answers), inv, doc, False)[1] if a.answers else {}
            result = dict(status="review_status", entries=len(doc.entries), assessed=len(reviews),
                pending=len(doc.entries) - len(reviews), deferred=sum(r["decision"] == "defer" for r in reviews.values()),
                issue_counts=inv["counts"], original_unchanged=True)
        print(json.dumps(result, sort_keys=True))  # No source text, names or local paths.
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc) if isinstance(exc, ReadingError) else "Invalid or inaccessible input; inspect locally"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
