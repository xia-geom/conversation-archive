"""Release metadata and publication-tool safety; no live calls or private data."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('publication_audit', ROOT / 'tools/publication_audit.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class PublicationTests(unittest.TestCase):
    def test_license_and_metadata_agree(self):
        meta = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
        self.assertEqual(meta['license'], {'file': 'LICENSE'})
        self.assertIn('MIT License', (ROOT / 'LICENSE').read_text())
        self.assertIn('Copyright (c) 2026 Xia Xiao and contributors', (ROOT / 'LICENSE').read_text())
        self.assertEqual(meta['dependencies'], [])

    def test_release_does_not_change_evidence_version(self):
        import conversation_archive
        from conversation_archive.model import IMPORTER_VERSION
        meta = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
        self.assertEqual(conversation_archive.__version__, meta['version'])
        self.assertEqual(IMPORTER_VERSION, '0.1.1')

    def test_actions_have_immutable_references(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            for uses in re.findall(r'uses:\s*(\S+)', path.read_text()):
                self.assertRegex(uses, r'^[\w./-]+@[0-9a-f]{40}$', path.name)

    def test_no_privileged_outside_pr_trigger_or_private_runners(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            text = path.read_text()
            self.assertNotIn('pull_request_target:', text)
            self.assertNotIn('self-hosted', text)
            self.assertNotIn('persist-credentials: true', text)

    def test_release_is_draft_and_main_scoped(self):
        text = (ROOT / '.github/workflows/alpha-release.yml').read_text()
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn('needs: verify', text)
        self.assertIn('--draft --prerelease', text)
        self.assertIn('preserved', text.lower())
        self.assertNotIn('repo edit', text)

    def test_audit_is_private_and_not_self_approving(self):
        text = (ROOT / '.github/workflows/publication-audit.yml').read_text()
        self.assertIn('github.event.repository.private == true', text)
        self.assertIn('retention-days: 3', text)
        self.assertNotIn('contents: write', text)
        source = (ROOT / 'tools/publication_audit.py').read_text()
        self.assertIn('"publication_clearance": False', source)

    def test_default_scanner_cannot_use_repository_allowlist(self):
        text = (ROOT / '.github/workflows/secret-scan.yml').read_text()
        self.assertIn('sha256sum --check --status', text)
        self.assertIn('--redact=100', text)
        self.assertIn('--log-opts=', text)
        self.assertIn('no-gitleaks-ignore', text)
        self.assertIn('useDefault = true', text)

    def test_archive_reader_never_extracts_paths(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('../../escape.txt', 'invented')
        self.assertEqual(audit.archive_texts(buffer.getvalue()), [('../../escape.txt', b'invented')])

    def test_archive_expansion_is_bounded(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('large.txt', 'a' * 4000)
        with patch.object(audit, 'LIMIT', 1000), self.assertRaises(ValueError):
            audit.archive_texts(buffer.getvalue())

    def test_invalid_archive_is_not_success(self):
        with self.assertRaises(zipfile.BadZipFile):
            audit.archive_texts(b'invalid')

    def test_tool_failure_does_not_echo_private_stderr(self):
        with patch.object(audit.subprocess, 'run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = b'private fixture text'
            with self.assertRaises(RuntimeError) as caught:
                audit.run('gh', 'api', 'invented-endpoint')
        self.assertNotIn('private fixture text', str(caught.exception))

    def test_invalid_repository_rejected_before_calls(self):
        with patch.object(audit, 'run') as run:
            with self.assertRaises(ValueError):
                audit.collect('bad\nrepository', Path('not-created'))
            run.assert_not_called()

    def test_raw_collection_refuses_public_repository(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'run', return_value=b'{"private":false}') as run:
            with self.assertRaises(ValueError):
                audit.collect('example/repo', Path(temp) / 'review')
            self.assertEqual(run.call_count, 1)

    def test_existing_review_directory_preserved(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'run') as run:
            path = Path(temp)
            (path / 'keep.txt').write_text('preserve')
            with self.assertRaises(FileExistsError):
                audit.collect('example/repo', path)
            self.assertEqual((path / 'keep.txt').read_text(), 'preserve')
            run.assert_not_called()

    def test_historical_release_scope_and_current_removals_are_explicit(self):
        meta = json.loads((ROOT / 'project.json').read_text())
        self.assertEqual(meta['publication']['workflow_and_migration_development'], 'explicitly_deferred')
        self.assertNotIn('migrate_authority', meta['tasks'])
        self.assertIn('machine snapshots', meta['retired_components'])
        self.assertFalse(meta['tasks']['raw_store']['automatic_master_update'])
        self.assertIn('server settings', (ROOT / 'docs/public-alpha.md').read_text())
