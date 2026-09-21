"""Read-only publication inventory. Raw review material is private, never a release asset.

Requires git, gh and Gitleaks. Network reads are restricted to the named GitHub
repository. No models, deletion, permission changes, or automatic clearance.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

LIMIT = 50 * 1024 * 1024


def run(*args, env=None):
    result = subprocess.run(args, capture_output=True, env=env, timeout=180)
    if result.returncode:
        # Do not echo stderr: endpoints, tokens or fetched source text can appear there.
        raise RuntimeError(f"{args[0]} failed (exit {result.returncode})")
    return result.stdout


def archive_texts(payload):
    """Bound ZIP expansion and read without extracting attacker-controlled paths."""
    if len(payload) > LIMIT:
        raise ValueError("Download exceeds review size limit")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        items = [p for p in z.infolist() if not p.is_dir()]
        if len(items) > 10000 or sum(p.file_size for p in items) > LIMIT:
            raise ValueError("Expanded archive exceeds review size limit")
        return [(p.filename, z.read(p)) for p in items]


def collect(repo, output):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("Expected owner/repository")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    corpus = output / "corpus"
    corpus.mkdir(mode=0o700)
    records, gaps, counts = [], [], {}

    def keep(kind, locator, data):
        digest = hashlib.sha256(data).hexdigest()
        try:
            text = data.decode("utf-8-sig")
            if "\x00" in text:
                raise UnicodeError()
        except UnicodeError:
            gaps.append({"kind": kind, "locator": locator, "reason": "binary_requires_manual_review", "sha256": digest})
            return
        name = f"{len(records):05d}-{kind}.txt"
        (corpus / name).write_text(text, encoding="utf-8")
        records.append({"file": name, "kind": kind, "locator": locator, "sha256": digest, "bytes": len(data)})
        counts[kind] = counts.get(kind, 0) + 1

    def api(endpoint, key=None):
        raw = run("gh", "api", "--paginate", "--slurp", f"repos/{repo}/{endpoint}")
        pages = json.loads(raw)
        keep("github", endpoint, raw)
        values = []
        for page in pages:
            values.extend(page[key] if key else page)
        return values

    def download(endpoint, kind):
        try:
            for member, data in archive_texts(run("gh", "api", f"repos/{repo}/{endpoint}")):
                keep(kind, f"{endpoint}::{member}", data)
        except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            gaps.append({"kind": kind, "locator": endpoint, "reason": type(exc).__name__})

    meta = json.loads(run("gh", "api", f"repos/{repo}"))
    # Raw audit bundles must not become a new publicly available copy of an exposure.
    if not meta["private"]:
        raise ValueError("Raw review-bundle collection requires a private repository")
    keep("github", "repository", json.dumps(meta).encode())
    token = os.environ["GH_TOKEN"]
    env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
               GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode())
    run("git", "fetch", "--no-recurse-submodules", "origin", "+refs/heads/*:refs/remotes/origin/*",
        "+refs/tags/*:refs/tags/*", "+refs/pull/*/head:refs/review-heads/*", "+refs/pull/*/merge:refs/review-merges/*", env=env)
    refs = run("git", "for-each-ref", "--format=%(refname) %(objectname)")
    keep("refs", "advertised-and-pr-refs", refs)
    objects = run("git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)")
    for row in objects.decode().splitlines():
        sha, kind, size = row.split()
        if kind not in ("blob", "commit", "tag"):
            continue
        if int(size) > LIMIT:
            gaps.append({"kind": kind, "locator": sha, "reason": "oversized_object"})
            continue
        keep(kind, sha, run("git", "cat-file", "-p", sha))
    run("git", "bundle", "create", str(output / "repository.bundle"), "--all")
    api("branches?per_page=100")
    api("tags?per_page=100")
    api("issues?state=all&per_page=100")
    api("issues/comments?per_page=100")
    api("pulls/comments?per_page=100")
    api("comments?per_page=100")
    for pr in api("pulls?state=all&per_page=100"):
        api(f"pulls/{pr['number']}/reviews?per_page=100")
    releases = api("releases?per_page=100")
    for release in releases:
        for asset in release.get("assets", []):
            gaps.append({"kind": "release_asset", "locator": asset["id"], "reason": "manual_media_review_required"})
    for workflow in api("actions/runs?per_page=100", "workflow_runs"):
        if str(workflow["id"]) == os.environ.get("GITHUB_RUN_ID"):
            continue  # This audit cannot inspect its own still-running log.
        if workflow["status"] != "completed":
            gaps.append({"kind": "workflow", "locator": workflow["id"], "reason": "still_running"})
            continue
        for attempt in range(1, workflow.get("run_attempt", 1) + 1):
            download(f"actions/runs/{workflow['id']}/attempts/{attempt}/logs", "log")
    for artifact in api("actions/artifacts?per_page=100", "artifacts"):
        if artifact["expired"]:
            gaps.append({"kind": "artifact", "locator": artifact["id"], "reason": "expired_unreadable"})
        elif str(artifact.get("workflow_run", {}).get("id")) != os.environ.get("GITHUB_RUN_ID"):
            download(f"actions/artifacts/{artifact['id']}/zip", "artifact")
    # Preserve original material only in the private review bundle. Console output is counts only.
    report_path = output / "gitleaks.json"
    scan = subprocess.run(["gitleaks", "dir", str(corpus), "--no-banner", "--redact=100",
                           "--report-format", "json", "--report-path", str(report_path)],
                          capture_output=True, timeout=180)
    if scan.returncode not in (0, 1):
        gaps.append({"kind": "scanner", "reason": "execution_failed"})
    findings = json.loads(report_path.read_text()) if report_path.exists() else []
    report = {"repository": repo, "head": run("git", "rev-parse", "HEAD").decode().strip(),
              "counts": counts, "gitleaks_version": run("gitleaks", "version").decode().strip(),
              "secret_findings": len(findings), "gaps": gaps, "records": records,
              "manual_privacy_review": "required", "publication_clearance": False,
              "limits": ["No access to GitHub-unadvertised or server-deleted objects.",
                         "Current running audit log needs post-run review.",
                         "Attachments and non-text media require separate review.",
                         "A zero-finding secret scan is not a privacy certification."]}
    (output / "inventory.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("head", "counts", "gitleaks_version", "secret_findings", "publication_clearance")}))
    print(f"Review gaps: {len(gaps)}. Manual review required; no visibility change performed.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.repo, args.output)
