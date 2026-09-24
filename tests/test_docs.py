"""Executable Markdown onboarding and local link checks; no network/model calls."""
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
    result, fence = [], None
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence is not None:
            char, size = fence
            if re.fullmatch(r"\s{0,3}" + re.escape(char) + "{" + str(size) + r",}\s*", line):
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1])); continue
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
            number += 1; candidate = f"{slug}-{number}"
        found.add(candidate)
    return found


def local_link_errors(root: Path, files: list[Path]) -> list[str]:
    root = root.resolve(); errors = []
    for source in files:
        text = prose(source.read_text(encoding="utf-8"))
        for link in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", text):
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc: continue
            path = unquote(parsed.path)
            target = (source.parent / path).resolve() if path else source.resolve()
            label = f"{source.relative_to(root)}: {link}"
            if not target.is_relative_to(root): errors.append(label + " escapes repository")
            elif not target.exists(): errors.append(label + " missing target")
            elif parsed.fragment and target.is_file() and target.suffix.lower() == ".md":
                if unquote(parsed.fragment) not in anchors(target.read_text(encoding="utf-8")):
                    errors.append(label + " missing anchor")
    return errors


def marked_block(text: str, name: str, language: str) -> str:
    pattern = (r"<!-- smoke:" + re.escape(name) + r":start -->\s*```"
               + re.escape(language) + r"\n(.*?)\n```\s*<!-- smoke:"
               + re.escape(name) + r":end -->")
    matches = re.findall(pattern, text, flags=re.S)
    if len(matches) != 1: raise AssertionError(f"Expected exactly one {name} smoke block")
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
            root = Path(temp); page = root / "README.md"
            page.write_text("# Present\n[bad](missing.md)\n[bad anchor](#absent)\n[good](#present)\n")
            errors = local_link_errors(root, [page])
        self.assertEqual(len(errors), 2)
        self.assertIn("missing target", errors[0]); self.assertIn("missing anchor", errors[1])

    def test_checker_rejects_repository_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); page = root / "README.md"
            page.write_text("[outside](../outside.md)\n")
            self.assertIn("escapes repository", local_link_errors(root, [page])[0])

    def test_guides_are_consolidated_with_explicit_compatibility(self):
        for name in ("workflow.md", "formats.md", "compatibility.md", "troubleshooting.md"):
            self.assertTrue((ROOT / "docs" / name).is_file())
        for name in ("machine-archive.md", "structured-archive.md", "knowledge-map.md", "question-batches.md"):
            self.assertFalse((ROOT / "docs" / name).exists())
        text = (ROOT / "docs/compatibility.md").read_text()
        self.assertIn("Git history", text)
        self.assertIn("no automatic conversion", text)

    def test_template_contains_no_required_credentials(self):
        value = tomllib.loads((ROOT / "examples/exports.example.toml").read_text())
        self.assertEqual(value, {"sources": [{"provider": "chatgpt", "path": "/path/to/chatgpt-export/conversations.json"}]})

    def test_published_demo_produces_the_actual_markdown_product(self):
        block = marked_block((ROOT / "README.md").read_text(), "quickstart", "sh")
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp) / "checkout"; checkout.mkdir()
            shutil.copytree(ROOT / "conversation_archive", checkout / "conversation_archive",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            commands = [line for line in block.splitlines() if line.strip() and not line.lstrip().startswith("#")]
            self.assertEqual(len(commands), 1)
            command = shlex.split(commands[0])
            self.assertEqual(command[:3], ["python3", "-m", "conversation_archive.demo"])
            result = subprocess.run([sys.executable, *command[1:]], cwd=checkout, capture_output=True,
                text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report, {"fixture_only_not_model_accuracy": True, "document": "organized.md",
                "entries": 1, "checked": "passed", "replay": "already_applied", "original_unchanged": True,
                "database_files": 0})
            output = checkout / "data/markdown-demo"
            text = (output / "organized.md").read_text()
            self.assertIn("The owner reported planting mint.", text)
            self.assertIn("我今天种了薄荷。", text)
            self.assertIn("JSON pointer", text)
            self.assertNotIn("You may enjoy gardening.", text)
            self.assertEqual([p.name for p in output.glob("*.md")], ["organized.md"])
            self.assertFalse(list(output.rglob("*.sqlite*")))

    def test_smoke_markers_are_required(self):
        with self.assertRaises(AssertionError): marked_block("no marker", "quickstart", "sh")
