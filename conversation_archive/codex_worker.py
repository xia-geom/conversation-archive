"""Explicit opt-in Codex CLI adapter. No browser automation or credential handling."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile

from .autonomy import USAGE_KEYS, atomic_json, checked_usage
from .extraction import ExtractionError, SCHEMA, prompt_for, strict_json

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REQUIRED_FLAGS = ("--output-schema", "--output-last-message", "--json", "--ephemeral", "--ignore-user-config", "--sandbox")
FORBIDDEN_ITEMS = {"command_execution", "file_change", "mcp_tool_call", "web_search"}


def event_summary(path: Path) -> dict:
    """Observed telemetry, not inferred subscription credits or an API invoice."""
    totals = {key: 0 for key in USAGE_KEYS}
    completed, unknown, forbidden, failed = 0, False, False, False
    if not path.exists() or path.stat().st_size > MAX_RESPONSE_BYTES:
        return {"usage": None, "error": "Missing or oversized event stream"}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = strict_json(line)
            if not isinstance(event, dict):
                raise ExtractionError("Expected event object")
            if event.get("type") == "turn.completed":
                completed += 1
                usage = checked_usage(event.get("usage"))
                if usage is None:
                    unknown = True
                else:
                    for key in USAGE_KEYS:
                        totals[key] += usage[key]
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") in FORBIDDEN_ITEMS:
                forbidden = True
            if event.get("type") in ("turn.failed", "error"):
                failed = True
    except (ExtractionError, UnicodeError):
        return {"usage": None, "error": "Invalid event stream"}
    error = "Unexpected tool activity" if forbidden else "Provider reported failure" if failed else None
    return {"usage": totals if completed and not unknown and not failed else None, "error": error}


class CodexWorker:
    """One fresh read-only session per packet; unsupported flags fail closed.

    These options reduce tool exposure; they are NOT a hermetic read-isolation
    boundary. Run sensitive work in a separately isolated, authenticated account
    or VM, with managed configuration inspected by its operator.
    """
    def __init__(self, executable: str = "codex", timeout: int = 180):
        if type(timeout) is not int or timeout < 1:
            raise ExtractionError("Timeout must be a positive number of seconds")
        if os.name != "posix":
            raise ExtractionError("This worker's process-group cleanup requires macOS or Linux")
        self.executable, self.timeout = executable, timeout
        with tempfile.TemporaryDirectory(prefix="archive-codex-preflight-") as directory:
            try:
                help_result = subprocess.run([executable, "exec", "--help"], cwd=directory,
                                             capture_output=True, text=True, timeout=15, check=True)
                version = subprocess.run([executable, "--version"], cwd=directory,
                                         capture_output=True, text=True, timeout=15, check=True)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ExtractionError("Codex preflight failed; install/authenticate it locally and inspect exec --help") from exc
        if any(flag not in help_result.stdout for flag in REQUIRED_FLAGS):
            raise ExtractionError("Installed Codex lacks required isolation/structured-output flags; no fallback used")
        self.version = version.stdout.strip()

    def command(self, plan: dict, directory: Path) -> list[str]:
        return [self.executable, "exec", "--ignore-user-config", "--ephemeral",
                "--sandbox", "read-only", "--skip-git-repo-check", "--json",
                "--model", plan["model"],
                "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
                "-c", "features.shell_tool=false", "-c", "features.unified_exec=false",
                "-c", "project_doc_max_bytes=0",
                "-c", "model_reasoning_effort=" + json.dumps(plan["effort"]),
                "--output-schema", str(directory / "schema.json"),
                "--output-last-message", str(directory / "response.json"), "-"]

    def __call__(self, request: dict, attempt: Path, plan: dict) -> dict:
        attempt = attempt.resolve()
        atomic_json(attempt / "schema.json", SCHEMA)
        prompt = prompt_for(request)
        (attempt / "prompt.txt").write_text(prompt, encoding="utf-8")
        atomic_json(attempt / "runtime.json", {"codex_version": self.version,
                    "model": plan["model"], "effort": plan["effort"],
                    "mode": "fresh_read_only_candidate_extraction", "timeout_seconds": self.timeout})
        timed_out = False
        # No repository/project instruction files in the working directory.
        with tempfile.TemporaryDirectory(prefix="archive-codex-worker-") as cwd:
            with (attempt / "events.jsonl").open("wb") as stdout, (attempt / "stderr.log").open("wb") as stderr:
                proc = subprocess.Popen(self.command(plan, attempt), cwd=cwd, stdin=subprocess.PIPE,
                                        stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    proc.communicate(prompt.encode("utf-8"), timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.communicate()
                except BaseException:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.communicate()
                    raise
        events = event_summary(attempt / "events.jsonl")
        error = "Worker timeout" if timed_out else "Worker exited unsuccessfully" if proc.returncode else events["error"]
        response = attempt / "response.json"
        proposal = None
        if error is None:
            try:
                if not response.exists() or response.stat().st_size > MAX_RESPONSE_BYTES:
                    raise ExtractionError("Missing or oversized response")
                proposal = strict_json(response.read_text(encoding="utf-8"))
            except (ExtractionError, UnicodeError):
                error = "Invalid final response"
        usage = None if timed_out or proc.returncode else events["usage"]
        return {"proposal": proposal, "usage": usage, "error": error,
                "codex_version": self.version, "returncode": proc.returncode}
