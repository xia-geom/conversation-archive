"""Transient, read-only inspection of entry Markdown and preserved archive bundles.

This recognizes the repository's explicit heading/anchor convention, not arbitrary
CommonMark. Fences and archived source blocks cannot create live entry headings.
No database, embedding index, model call, or semantic inference is made here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

VERSION = "reading-1.0"
MAX_INPUT_BYTES = 64 * 1024 * 1024
ENTRY = re.compile(r"^(E\d{4,})\s+[—–-]\s+(.+?)\s*$")
LINK = re.compile(r"\[([^\]\n]+)\]\(#([^\s)]+)\)")
ANCHOR = re.compile(r'''^ {0,3}<a\s+(?:id|name)=["']([^"']+)["']\s*></a>\s*$''')
DATA = re.compile(r"data:[^\s)]*;base64,", re.I)
ADDITION = re.compile(r"^### .*?(?:original.conversation|original claude|original.message|complement|later addition)", re.I | re.M)
UNAVAILABLE = re.compile(r"(?:original|underlying).{0,100}(?:unavailable|not (?:retrieved|available|recovered))", re.I)


class ReadingError(ValueError):
    """Public error messages contain categories, not private paths or quotations."""


def need(condition, message):
    if not condition:
        raise ReadingError(message)


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def load_json_text(text):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def bad(_):
        raise ReadingError("Non-finite JSON value")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad)


def read_utf8(path, limit=MAX_INPUT_BYTES):
    p = Path(path)
    need(not p.is_symlink() and p.is_file(), "Expected a regular input file, not a symlink")
    need(p.stat().st_size <= limit, "Input exceeds the explicit size limit")
    data = p.read_bytes()
    need(len(data) <= limit, "Input changed beyond the size limit")
    return data.decode("utf-8")


def visible_lines(text):
    """Yield original character offsets, hiding fences and archived source content."""
    fence = archive = None
    offset = 0
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        end = offset + len(line)
        if archive is not None:
            if re.fullmatch(r"\s*<!-- ARCHIVED_TEXT_END " + re.escape(archive) + r" -->\s*", line):
                archive = None
        elif fence is not None:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*\r?\n?", line):
                fence = None
        else:
            marker = re.fullmatch(r"\s*<!-- ARCHIVED_TEXT_BEGIN (\S+) -->\s*", line)
            opening = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
            if marker:
                archive = marker[1]
            elif opening and not (opening[1][0] == "`" and "`" in opening[2]):
                fence = (opening[1][0], len(opening[1]))
            else:
                yield offset, end, number, line
        offset = end
    need(fence is None and archive is None, "Unclosed protected block; inspect boundaries before exporting")


def tokens(text):
    result = []
    for lo, hi, line_no, line in visible_lines(text):
        heading = re.match(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$", line)
        anchor = ANCHOR.fullmatch(line.rstrip("\r\n"))
        if heading:
            result.append(dict(kind="heading", level=len(heading[1]), title=heading[2], start=lo, end=hi, line=line_no))
        elif anchor:
            result.append(dict(kind="anchor", id=anchor[1], start=lo, end=hi, line=line_no))
    return result


def references(text, include_external=False):
    # Entry code/quoted source blocks are historical evidence, not navigation.
    refs = {unquote(m[2]) for _, _, _, line in visible_lines(text) for m in LINK.finditer(line)}
    if include_external:
        refs.update(re.findall(r"external reference `([A-Za-z0-9_-]+)`; not included", text))
    return sorted(refs)


def metadata(text, name):
    match = re.search(r"^\*\*" + re.escape(name) + r":\*\*\s*(.*?)\s*$", text, re.M)
    return match[1] if match else ""


def entry_blocks(text):
    ts = tokens(text)
    entries = {}
    for index, token in enumerate(ts):
        if token["kind"] != "heading" or token["level"] != 2:
            continue
        match = ENTRY.fullmatch(token["title"])
        if not match:
            continue
        eid, title = match.groups()
        need(eid not in entries, "Duplicate live entry ID; select the intended document")
        lo = token["start"]
        if index and ts[index - 1]["kind"] == "anchor" and ts[index - 1]["id"] == eid.lower():
            prior = ts[index - 1]
            need(not text[prior["end"]:lo].strip(), "Unexpected content between entry anchor and heading")
            # The anchor is structural; entry text starts at its heading.
        end_token = next((t for t in ts[index + 1:] if t["kind"] == "heading" and t["level"] <= 2), None)
        hi = end_token["start"] if end_token else len(text)
        # An immediately preceding anchor belongs to the following section.
        if end_token:
            previous = [t for t in ts if token["end"] <= t["start"] < hi]
            if previous and previous[-1]["kind"] == "anchor" and not text[previous[-1]["end"]:hi].strip():
                hi = previous[-1]["start"]
        raw = text[lo:hi].rstrip() + "\n"
        need(not DATA.search(raw), "An entry contains encoded binary data; explicitly separate it before export")
        entries[eid] = dict(entry_id=eid, title=title, start=lo, end=hi, text=raw, sha256=sha(raw),
                            refs=references(raw, include_external=True), period=metadata(raw, "Event period"))
    need(bool(entries), "No supported live entry headings found")
    return entries


def section(text, title):
    ts = tokens(text)
    matches = [(i, t) for i, t in enumerate(ts) if t["kind"] == "heading" and t["title"] == title]
    need(len(matches) <= 1, "Ambiguous named section")
    if not matches:
        return ""
    i, t = matches[0]
    end = next((u["start"] for u in ts[i + 1:] if u["kind"] == "heading" and u["level"] <= t["level"]), len(text))
    return text[t["end"]:end].strip()


def preserved(text):
    """Validate every explicitly embedded document, then select exactly one master."""
    matches = list(re.finditer(r"^<!-- BEGIN PRESERVED ([A-Za-z0-9_.-]+\.md) -->\r?\n", text, re.M))
    if not matches:
        need("<!-- BEGIN PRESERVED" not in text, "Unsupported preserved-document marker")
        return text, "", {}
    docs, spans = {}, []
    for m in matches:
        endings = list(re.finditer(r"^<!-- END PRESERVED " + re.escape(m[1]) + r" -->\s*$", text, re.M))
        need(m[1] not in docs and len(endings) == 1 and endings[0].start() >= m.end(), "Ambiguous preserved-document boundaries")
        hi = endings[0].start()
        need(not any(m.start() < n.start() < hi for n in matches), "Nested preserved documents are unsupported")
        docs[m[1]] = text[m.end():hi]
        spans.append((m.start(), endings[0].end()))
    tail = text[max(hi for _, hi in spans):]
    for name, body in docs.items():
        expected = re.findall(r"^- `" + re.escape(name) + r"`: `([a-f0-9]{64})`\s*$", tail, re.M)
        need(len(expected) == 1 and sha(body) == expected[0], "Preserved document hash is missing or mismatched")
    masters = [name for name in docs if name.endswith("_master.md") or name == "organized.md"]
    need(len(masters) == 1, "Expected exactly one preserved master")
    return docs[masters[0]], text[:min(lo for lo, _ in spans)], {k: sha(v) for k, v in docs.items()}


def appendix_table(text, name):
    m = re.search(r"^### " + re.escape(name) + r"[^\n]*\n\n(`{3,})jsonl\n(.*?)\n\1[ \t]*$", text, re.M | re.S)
    need(m is not None, "A required legacy snapshot table is absent")
    return [load_json_text(line) for line in m[2].splitlines() if line.strip()]


def snapshot_decisions(text, entries, master):
    """Compile only supported active identity rules; no inferred relationships.

The exact answers and original finite mention scopes survive retirement of the
old snapshot. Unknown active operation types block conversion, not get omitted.
"""
    if "## Structured record appendix" not in text:
        return ""
    appendix = text[text.index("## Structured record appendix"):]
    locators = appendix_table(appendix, "entries")
    need({x["entry_id"] for x in locators} == set(entries) and len(locators) == len(entries), "Snapshot and master entry coverage disagree")
    for item in locators:
        lo, hi = item["source_start"], item["source_end"]
        need(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(master), "Invalid master entry locator")
        need(item["source_sha256"] == sha(master), "Snapshot entry names a different master")
        located = re.sub(r'\s*<a id="[A-Za-z0-9_-]+"></a>\s*$', "", master[lo:hi]).strip()
        need(located == entries[item["entry_id"]]["text"].strip(), "Snapshot entry locator does not match preserved entry")
    events = {e["event_id"]: e for e in appendix_table(appendix, "correction_events")}
    rules = appendix_table(appendix, "correction_rules")
    mentions = {m["mention_id"]: m for m in appendix_table(appendix, "mentions")}
    relations = appendix_table(appendix, "relationships")
    entities = {e["entity_id"]: e for e in appendix_table(appendix, "entities")}
    parts = ["These recorded identity decisions apply only to their original quoted mention scopes. They do not confirm every fact in an entry or establish global aliases. Original offsets refer to the preserved master, not this reading copy.\n"]
    active = [r for r in rules if r["active"]]
    need(len({r["rule_id"] for r in rules}) == len(rules), "Duplicate legacy rule IDs")
    for event_id in sorted({r["event_id"] for r in active}):
        need(event_id in events, "Missing decision event")
        event = events[event_id]
        parts.append("## Recorded decision " + event_id + "\n\nRecorded actor: " + event["actor"] + "\n\n" + quote_block(event["answer"]))
        for rule in [r for r in active if r["event_id"] == event_id]:
            need(rule["operation"] in {"bind", "bind_mentions"}, "Unsupported active legacy correction; explicit conversion is required")
            op = rule.get("payload")
            if op is None:
                op = load_json_text(rule["payload_json"])
            eid = op["entity_id"] if rule["operation"] == "bind_mentions" else "entity:" + op["kind"] + ":" + op["entity_id"]
            need(eid in entities, "Missing confirmed entity")
            edges = [e for e in relations if rule["rule_id"] in e.get("rule_ids", [])
                     and e["relation"] == "refers_to" and e["status"] == "user_confirmed" and e["authority"] == "owner_confirmed"]
            need(bool(edges), "Active binding has no explicit supported mention scope")
            parts.append("Rule `" + rule["rule_id"] + "`: " + entities[eid]["label"] + ". Exact original scope:\n")
            seen = set()
            for edge in edges:
                m = mentions.get(edge["source_id"])
                need(m is not None and edge["target_id"] == eid and m["entity_id"] == eid, "Conflicting identity projection")
                entry = entries.get(m["entry_id"])
                need(entry is not None and entry["text"][m["start"]:m["end"]] == m["quote"], "Identity quotation scope changed")
                need(m["entry_id"] in op["entry_ids"], "Binding exceeds its recorded entry scope")
                need(m["mention_id"] not in seen, "Duplicate supported identity mention")
                seen.add(m["mention_id"])
                parts.append("- [" + m["entry_id"] + "](#" + m["entry_id"].lower() + "), original characters " + str(m["start"]) + "–" + str(m["end"]) + ": " + json.dumps(m["quote"], ensure_ascii=False) + "\n")
            if "mention_ids" in op:
                need(seen == set(op["mention_ids"]), "Binding lost or gained explicit mentions")
    return "\n".join(parts).strip()


def quote_block(text):
    fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
    return fence + "text\n" + text + ("" if text.endswith("\n") else "\n") + fence + "\n"


def source_blocks(master):
    ts = tokens(master)
    anchors = [t for t in ts if t["kind"] == "anchor"]
    result = {}
    for n, t in enumerate(anchors):
        if not re.fullmatch(r"(?:src-|cor\d)[A-Za-z0-9_-]*", t["id"], re.I):
            continue
        need(t["id"] not in result, "Duplicate active source or correction anchor")
        hi = anchors[n + 1]["start"] if n + 1 < len(anchors) else len(master)
        body = master[t["end"]:hi]
        result[t["id"]] = dict(source_id=t["id"], text=body, sha256=sha(body), start=t["end"], end=hi,
                                line=t["line"] + 1)
    return result


@dataclass
class Document:
    text: str
    master: str
    entries: dict
    sources: dict
    decisions: str
    hashes: dict
    fingerprint: str

    @classmethod
    def from_text(cls, text):
        master, wrapper, hashes = preserved(text)
        entries = entry_blocks(master)
        sources = source_blocks(master)
        # Preserved sources have their own explicit archive markers. Never parse
        # historical headers as live records, nor trust only header source lists.
        decisions = snapshot_decisions(text, entries, master) if hashes else section(master, "Recorded decisions")
        if hashes and not decisions:
            decisions = section(wrapper, "Owner confirmations")
        return cls(text, master, entries, sources, decisions, hashes, sha(text))

    @classmethod
    def read(cls, path):
        return cls.from_text(read_utf8(path))

    def basis(self, eid):
        entry = self.entries[eid]
        return sha(encoded({"entry": entry["sha256"], "decisions": sha(self.decisions),
            "sources": {ref: self.sources[ref]["sha256"] if ref in self.sources else "unavailable"
                        for ref in entry["refs"] if not re.fullmatch(r"e\d{4,}", ref)}}))

    def audit(self):
        issues = []
        def add(code, eid=None, detail=None, kind="review"):
            issues.append(dict(code=code, entry_id=eid, detail=detail, kind=kind))
        if DATA.search(self.text):
            add("encoded_attachment_excluded", detail="Encoded payloads remain in the preserved input, not reading output", kind="packaging")
        if self.hashes:
            add("preserved_bundle", detail="Full sources, old reports and machine appendices must not be republished wholesale", kind="packaging")
        stop = {"the", "and", "with", "from", "into", "after", "before", "about", "while", "their", "that", "this", "owner", "account", "record", "feeling", "reflection", "later", "original", "conversation", "source", "for", "was", "had", "not", "but", "has", "its", "are", "who", "his", "her", "she", "him", "out"}
        words = lambda t: {w.casefold() for w in re.findall(r"[^\W\d_]{3,}", t) if w.casefold() not in stop}
        titles = {eid: words(e["title"]) for eid, e in self.entries.items()}
        for eid, e in self.entries.items():
            header = re.search(r"^\*\*Source references:\*\*([^\n]*)", e["text"], re.M)
            in_header = references(header[0]) if header else []
            body_sources = {x for x in e["refs"] if x.lower().startswith("src-")}
            missing = sorted(body_sources - set(in_header))
            if missing:
                add("body_sources_missing_from_header", eid, missing, "mechanical")
            addition_headers = list(ADDITION.finditer(e["text"]))
            for addition in addition_headers:
                end = e["text"].find("\n### ", addition.end())
                end = end if end >= 0 else len(e["text"])
                terms = words(e["text"][addition.start():end])
                own = len(terms & titles[eid])
                alternatives = sorted(((len(terms & keys) / max(1, len(keys)), len(terms & keys), other) for other, keys in titles.items() if other != eid), reverse=True)
                alternatives = [item for item in alternatives if item[1] >= max(3, own + 3)]
                if alternatives:
                    add("possible_misplaced_addition", eid, {"candidate_entries": [item[2] for item in alternatives[:3]], "start": addition.start(), "end": end,
                        "basis": "Title-word overlap only; read both complete entries and evidence. This is not a confirmed event match."})
            if addition_headers:
                add("whole_entry_reconciliation", eid, "Read additions together with the entire entry; check placement, chronology, attribution and prior limitations")
                if UNAVAILABLE.search(e["text"]):
                    add("possibly_stale_source_limit", eid, "A source-unavailable statement coexists with later additions; this is a review candidate, not a proven contradiction")
            for ref in e["refs"]:
                if not (ref in self.sources or ref in {x.lower() for x in self.entries}):
                    add("external_or_missing_target", eid, ref, "mechanical")
        for _, _, _, line in visible_lines(self.master):
            m = re.match(r"\| \[(E\d{4,})\]\(#[^)]+\) \| ([^|]+) \|", line)
            if m and m[1] in self.entries and m[2].strip() != self.entries[m[1]]["title"]:
                add("stale_index_title", m[1], "Index title differs from entry title; output index is generated", "mechanical")
        first_source = min((v["start"] for k, v in self.sources.items() if k.startswith("src-")), default=len(self.master))
        headings = [t for t in tokens(self.master) if t["kind"] == "heading" and t["level"] == 1 and t["start"] < first_source]
        context = [dict(title=t["title"], start=t["start"], end=headings[n + 1]["start"] if n + 1 < len(headings) else first_source)
                   for n, t in enumerate(headings) if not any(t["start"] <= e["start"] < (headings[n + 1]["start"] if n + 1 < len(headings) else first_source) for e in self.entries.values())]
        return {"version": VERSION, "input_sha256": self.fingerprint, "input_bytes": len(self.text.encode()),
                "nonentry_context_ranges": context,
                "entries": len(self.entries), "source_blocks": len(self.sources), "preserved_hashes": self.hashes,
                "decisions_sha256": sha(self.decisions), "issues": issues,
                "counts": dict(Counter(x["code"] for x in issues)),
                "semantic_verification": "not performed by deterministic audit"}
