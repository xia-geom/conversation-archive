"""Executable onboarding and local Markdown navigation checks; no network/model calls.

The link parser intentionally supports this repository's inline Markdown links,
ATX headings and explicit HTML anchors. It is not a complete Markdown renderer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def prose(text: str) -> str:
    """Remove fenced examples so historical headings/links are not live navigation."""
    result = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence is not None:
            char, size = fence
            if re.fullmatch(r"\s{0,3}" + re.escape(char) + "{" + str(size) + r",}\s*", line):
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]))
            continue
        result.append(line)
    return "\n".join(result)


def anchors(text: str) -> set[str]:
    text = prose(text)
    found = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', text))
    for heading in re.findall(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", text, flags=re.M):
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        heading = re.sub(r"<[^>]*>", "", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        candidate, number = slug, 0
        while candidate in found:
            number += 1
            candidate = f"{slug}-{number}"
        found.add(candidate)
    return found


def local_link_errors(root: Path, files: list[Path]) -> list[str]:
    root = root.resolve()
    errors = []
    for source in files:
        text = prose(source.read_text(encoding="utf-8"))
        # External URLs, code-fenced samples and reference-style links are not fetched.
        for link in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", text):
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            path = unquote(parsed.path)
            target = (source.parent / path).resolve() if path else source.resolve()
            label = f"{source.relative_to(root)}: {link}"
            if not target.is_relative_to(root):
                errors.append(label + " escapes repository")
            elif not target.exists():
                errors.append(label + " missing target")
            elif parsed.fragment and target.is_file() and target.suffix.lower() == ".md":
                if unquote(parsed.fragment) not in anchors(target.read_text(encoding="utf-8")):
                    errors.append(label + " missing anchor")
    return errors


def marked_block(text: str, name: str, language: str) -> str:
    pattern = (r"<!-- smoke:" + re.escape(name) + r":start -->\s*```"
               + re.escape(language) + r"\n(.*?)\n```\s*<!-- smoke:"
               + re.escape(name) + r":end -->")
    matches = re.findall(pattern, text, flags=re.S)
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one {name} smoke block")
    return matches[0]


class DocumentationTests(unittest.TestCase):
    def test_repository_relative_links_and_anchors(self):
        files = list(ROOT.glob("*.md"))
        for folder in ("docs", "examples", ".github"):
            files.extend((ROOT / folder).rglob("*.md"))
        self.assertEqual(local_link_errors(ROOT, sorted(set(files))), [])

    def test_parser_ignores_historical_fences_and_keeps_real_anchors(self):
        text = "# Real heading\n```md\n# Not live\n[x](missing.md)\n```\n# Real heading\n<a id=\"explicit\"></a>\n"
        self.assertEqual(anchors(text), {"real-heading", "real-heading-1", "explicit"})
        self.assertNotIn("missing.md", prose(text))

    def test_checker_detects_missing_targets_and_fragments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            page = root / "README.md"
            page.write_text("# Present\n[bad](missing.md)\n[bad anchor](#absent)\n[good](#present)\n", encoding="utf-8")
            errors = local_link_errors(root, [page])
        self.assertEqual(len(errors), 2)
        self.assertIn("missing target", errors[0])
        self.assertIn("missing anchor", errors[1])

    def test_checker_rejects_repository_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            page = root / "README.md"
            page.write_text("[outside](../outside.md)\n", encoding="utf-8")
            self.assertIn("escapes repository", local_link_errors(root, [page])[0])

    def test_legacy_document_paths_are_preserved(self):
        for name in ("walkthrough.md", "data-dictionary.md", "reconciliation.md", "autonomy.md",
                     "audit-2026-09-20.md", "interview-demo.md", "roadmap.md"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / "docs" / name).is_file())

    def test_template_contains_no_required_credentials(self):
        value = tomllib.loads((ROOT / "examples" / "exports.example.toml").read_text(encoding="utf-8"))
        self.assertEqual(value, {"sources": [{"provider": "chatgpt", "path": "/path/to/chatgpt-export/conversations.json"}]})

    def test_quickstart_and_inspection_commands_as_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")
        expected = json.loads((ROOT / "examples" / "demo-report.json").read_text(encoding="utf-8"))
        excerpt = json.loads(marked_block(readme, "expected", "json"))
        outputs = []
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp) / "checkout"
            checkout.mkdir()
            # Copy only the package, never local data, credentials, or real archives.
            shutil.copytree(ROOT / "conversation_archive", checkout / "conversation_archive",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            blocks = [marked_block(readme, "quickstart", "sh"),
                      marked_block(guide, "inspect", "sh"),
                      marked_block(guide, "evidence", "sh")]
            for block in blocks:
                for line in block.splitlines():
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    command = shlex.split(line)
                    self.assertEqual(command[:2], ["python3", "-m"])
                    self.assertIn(command[2], {"conversation_archive.demo", "conversation_archive.autonomy",
                                               "conversation_archive", "json.tool"})
                    result = subprocess.run([sys.executable, *command[1:]], cwd=checkout,
                                            capture_output=True, text=True, encoding="utf-8",
                                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60)
                    self.assertEqual(result.returncode, 0, msg=f"{line}\n{result.stderr}")
                    outputs.append(result.stdout)
            actual = json.loads(outputs[0])
            self.assertEqual(actual, expected)
            self.assertEqual({key: actual[key] for key in excerpt}, excerpt)
            self.assertIn(json.dumps(expected, indent=2), guide)
            self.assertTrue(json.loads(outputs[1])["all_candidates_extracted"])
            self.assertEqual(json.loads(outputs[2]), expected)
            self.assertEqual(json.loads(outputs[4])["kind"], "unreviewed_extraction_candidates")
            self.assertIn("# Review packet P0001-0001", outputs[5])
            self.assertIn("Source SHA-256", outputs[5])
            self.assertEqual(actual["raw_reviewed_pieces"], 0)
            self.assertTrue(actual["canonical_files_unchanged"])

    def test_smoke_markers_are_required(self):
        with self.assertRaises(AssertionError):
            marked_block("no marker", "quickstart", "sh")
