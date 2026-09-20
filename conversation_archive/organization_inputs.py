"""Index supported E-numbered Markdown sections; preserve exact entry slices.

This prepares text for a Codex/operator-created catalog. It does not perform NER,
interpret dates, parse arbitrary Markdown layouts, or update the original file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .organization import OrganizationError, VERSION, load, require


def index_markdown(text, catalog=None):
    headings, offset, fence, archive = [], 0, None, None
    for line in text.splitlines(keepends=True):
        start, offset = offset, offset + len(line)
        if archive:
            if f"<!-- ARCHIVED_TEXT_END {archive} -->" in line:
                archive = None
            continue
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*(?:\r?\n)?", line):
                fence = None
            continue
        marker = re.search(r"<!-- ARCHIVED_TEXT_BEGIN (\S+) -->", line)
        if marker:
            archive = marker[1]
            continue
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if marker and not (marker[1][0] == "`" and "`" in marker[2]):
            fence = (marker[1][0], len(marker[1]))
            continue
        heading = re.match(r" {0,3}(#{1,6})\s+(.+)", line)
        if heading:
            eid = re.match(r"(E\d{4})\b", heading[2])
            headings.append((start, len(heading[1]), eid[1] if eid else None))
    require(fence is None and archive is None, "Unclosed historical block")
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    entries = []
    for i, (start, level, eid) in enumerate(headings):
        if not eid:
            continue
        end = next((pos for pos, lev, ident in headings[i + 1:] if ident or lev <= level), len(text))
        entries.append(dict(entry_id=eid, text=text[start:end],
                            source=dict(kind="master_text_snapshot", sha256=source_hash,
                                        start=start, end=end, offsets="Unicode characters")))
    require(entries and len({e["entry_id"] for e in entries}) == len(entries), "No active entries or duplicate IDs; supported headings start with E followed by four digits")
    return dict(version=VERSION, entries=entries, catalog=catalog or [], proposals=[])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # newline='' preserves CRLF in the indexed text and source hash.
        with args.master.open(encoding="utf-8", newline="") as f:
            text = f.read()
        data = index_markdown(text, load(args.catalog) if args.catalog else [])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(json.dumps({"indexed_entries": len(data["entries"]), "semantic_tagging_performed": False}))
        return 0
    except (OrganizationError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
