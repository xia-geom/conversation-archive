"""Bounded, resumable candidate extraction. Never writes review decisions or masters.

CLI: python -m conversation_archive.autonomy --help
The filesystem is the queue; one controller owns a state directory at a time.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable

from .extraction import (
    ExtractionError, PROMPT_FINGERPRINT, fingerprint, prompt_for, request_for,
    strict_json, validate_proposal,
)

AUTONOMY_VERSION = "1.0"
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")


def load(path: Path):
    return strict_json(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".autonomy-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def controller_lock(root: Path):
    """Advisory lock for this controller only; not a lock on the legacy master writer."""
    try:
        import fcntl
    except ImportError as exc:
        raise ExtractionError("Controller requires POSIX locking (macOS or Linux)") from exc
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".controller.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ExtractionError("Another controller owns this state directory") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize(root: Path, packet_ids: list[str], identity: dict, model: str, effort: str = "medium") -> dict:
    """Freeze a new queue. Identity is local metadata, never sent to the model."""
    root = Path(root)
    if not model.strip() or effort not in ("low", "medium", "high", "xhigh"):
        raise ExtractionError("Specify an explicit model and supported effort")
    if len(set(packet_ids)) != len(packet_ids) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in packet_ids):
        raise ExtractionError("Packet identities must be unique and path-safe")
    with controller_lock(root):
        if any(p.name != ".controller.lock" for p in root.iterdir()):
            raise ExtractionError("Use a new or empty state directory; resume an existing plan")
        plan = {"version": AUTONOMY_VERSION, "prompt_fingerprint": PROMPT_FINGERPRINT,
                "model": model, "effort": effort, "identity": identity,
                "packet_ids": packet_ids}
        state = {"version": AUTONOMY_VERSION, "plan_sha256": fingerprint(plan),
                 "calls_started": 0, "unknown_usage_calls": 0,
                 "usage": {k: 0 for k in USAGE_KEYS}, "stop_reason": "planned",
                 "jobs": {pid: {"status": "pending", "attempts": 0} for pid in packet_ids}}
        atomic_json(root / "plan.json", plan)
        atomic_json(root / "state.json", state)
        return summary(state)


def read_state(root: Path):
    plan, state = load(root / "plan.json"), load(root / "state.json")
    if (plan.get("version") != AUTONOMY_VERSION or state.get("version") != AUTONOMY_VERSION
            or state.get("plan_sha256") != fingerprint(plan)
            or plan.get("prompt_fingerprint") != PROMPT_FINGERPRINT
            or set(state["jobs"]) != set(plan["packet_ids"])):
        raise ExtractionError("Plan, state or extraction contract changed; explicit migration required")
    # These integrity checks detect accidental drift, not malicious rewriting of
    # both receipts and state by an actor who controls the directory.
    for pid, job in state["jobs"].items():
        if job.get("receipt_sha256"):
            receipt = root / "jobs" / pid / f"attempt-{job['attempts']:03}" / "receipt.json"
            if fingerprint(load(receipt)) != job["receipt_sha256"]:
                raise ExtractionError("Saved receipt changed")
        if job["status"] == "extracted":
            if fingerprint(load(root / "jobs" / pid / "candidate.json")) != job["candidate_sha256"]:
                raise ExtractionError("Saved candidate changed")
    return plan, state


def summary(state: dict) -> dict:
    counts = dict(Counter(job["status"] for job in state["jobs"].values()))
    return {"counts": counts, "packets": len(state["jobs"]),
            "calls_started": state["calls_started"], "usage": state["usage"],
            "unknown_usage_calls": state["unknown_usage_calls"],
            "stop_reason": state["stop_reason"],
            "all_candidates_extracted": counts.get("extracted", 0) == len(state["jobs"]),
            "raw_review_or_master_integration_claimed": False}


def checked_usage(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    if any(type(value.get(k)) is not int or value[k] < 0 for k in USAGE_KEYS):
        return None
    if value["cached_input_tokens"] > value["input_tokens"]:
        return None
    return {k: value[k] for k in USAGE_KEYS}


def _finish(root: Path, state: dict, pid: str, packet: dict, receipt: dict) -> None:
    job = state["jobs"][pid]
    request = request_for(packet)
    if receipt["request_sha256"] != fingerprint(request) or job["request_sha256"] != fingerprint(request):
        raise ExtractionError("Attempt refers to different evidence or coverage")
    usage = checked_usage(receipt.get("usage"))
    if usage is None:
        state["unknown_usage_calls"] += 1
    else:
        for key in USAGE_KEYS:
            state["usage"][key] += usage[key]
    try:
        if receipt.get("error"):
            raise ExtractionError(receipt["error"])
        proposal = validate_proposal(request, receipt["proposal"])
        candidate = {
            "kind": "unreviewed_extraction_candidates", "version": AUTONOMY_VERSION,
            "request_sha256": fingerprint(request), "prompt_fingerprint": PROMPT_FINGERPRINT,
            "proposal": proposal,
            # These witnesses are copied by code, not generated by the model.
            "source_pieces": [{k: p.get(k) for k in (
                "piece_id", "message_record_id", "segment_index", "start", "end",
                "text_sha256", "json_pointer", "provenance", "attachments",
            )} for p in packet["pieces"]],
        }
        atomic_json(root / "jobs" / pid / "candidate.json", candidate)
        job.update(status="extracted", candidate_sha256=fingerprint(candidate))
    except (ExtractionError, KeyError, TypeError) as exc:
        job.update(status="blocked", error=str(exc))
    job["receipt_sha256"] = fingerprint(receipt)
    job["usage_known"] = usage is not None
    atomic_json(root / "state.json", state)


def execute(root: Path, packet_loader: Callable[[str], dict], worker: Callable,
            max_calls: int = 20, max_tokens: int = 200000, max_prompt_chars: int = 80000) -> dict:
    """Caps are cumulative for this state, including failed and interrupted calls.

    The observed token cap is checked BETWEEN calls and can overshoot by one call.
    Unknown usage blocks further calls. This is not a provider billing limit.
    Worker(request, attempt_directory, plan) returns proposal/usage/error metadata.
    """
    if any(type(v) is not int or v < 1 for v in (max_calls, max_tokens, max_prompt_chars)):
        raise ExtractionError("Budgets must be positive integers")
    root = Path(root)
    with controller_lock(root):
        plan, state = read_state(root)
        for pid in plan["packet_ids"]:
            job = state["jobs"][pid]
            if any(j["status"] == "in_flight" for j in state["jobs"].values()):
                state["stop_reason"] = "recovery_required"
                break
            if state["unknown_usage_calls"]:
                state["stop_reason"] = "unknown_usage_requires_operator_audit"
                break
            if any(j["status"] == "blocked" for j in state["jobs"].values()):
                state["stop_reason"] = "blocked_attempt_requires_operator_audit"
                break
            if job["status"] == "extracted":
                continue
            if state["calls_started"] >= max_calls:
                state["stop_reason"] = "call_budget"
                break
            if state["usage"]["input_tokens"] + state["usage"]["output_tokens"] >= max_tokens:
                state["stop_reason"] = "observed_token_budget"
                break
            packet = packet_loader(pid)
            request = request_for(packet)
            if request["packet_id"] != pid or not any(not p["already_covered"] for p in request["pieces"]):
                raise ExtractionError("Queue no longer matches pending evidence; make an explicit new plan")
            if len(prompt_for(request)) > max_prompt_chars:
                state["stop_reason"] = "prompt_size_limit_no_truncation"
                break
            attempt = root / "jobs" / pid / f"attempt-{job['attempts'] + 1:03}"
            attempt.mkdir(parents=True, exist_ok=False)
            atomic_json(attempt / "request.json", request)
            job.update(status="in_flight", attempts=job["attempts"] + 1,
                       request_sha256=fingerprint(request))
            state["calls_started"] += 1
            # Write before invoking the provider: a crash never silently resets spend.
            atomic_json(root / "state.json", state)
            started = time.monotonic()
            try:
                result = worker(request, attempt, plan)
            except Exception as exc:
                # Do not publish exception text; SDK errors can contain private input.
                result = {"proposal": None, "usage": None, "error": type(exc).__name__}
            receipt = {**result, "request_sha256": fingerprint(request),
                       "elapsed_seconds": round(time.monotonic() - started, 3),
                       "recorded_at": datetime.now(timezone.utc).isoformat()}
            atomic_json(attempt / "receipt.json", receipt)
            # Recheck source/coverage before accepting a result. On failure, leave
            # in_flight + receipt for explicit recovery; never call the provider again.
            packet = packet_loader(pid)
            _finish(root, state, pid, packet, receipt)
            if state["jobs"][pid]["status"] == "blocked":
                state["stop_reason"] = "blocked_attempt_requires_operator_audit"
                break
            if state["unknown_usage_calls"]:
                state["stop_reason"] = "unknown_usage_requires_operator_audit"
                break
        else:
            state["stop_reason"] = "candidate_queue_complete"
        atomic_json(root / "state.json", state)
        return summary(state)


def recover(root: Path, packet_loader: Callable[[str], dict]) -> dict:
    """Operator must first ensure the interrupted worker is no longer running."""
    root = Path(root)
    with controller_lock(root):
        _, state = read_state(root)
        for pid, job in state["jobs"].items():
            if job["status"] != "in_flight":
                continue
            receipt = root / "jobs" / pid / f"attempt-{job['attempts']:03}" / "receipt.json"
            if receipt.exists():
                _finish(root, state, pid, packet_loader(pid), load(receipt))
            else:
                job.update(status="blocked", error="Interrupted attempt has no completed receipt", usage_known=False)
                state["unknown_usage_calls"] += 1
        state["stop_reason"] = "recovery_checked_no_model_calls"
        atomic_json(root / "state.json", state)
        return summary(state)


def prepare_from_review(run: Path, output: Path, model: str, effort: str = "medium") -> dict:
    from . import reconciliation as r
    run = Path(run).resolve()
    inv = r.checked_inventory(run)
    cov = r.coverage(run)
    ids = [p["packet_id"] for p in inv["packets"] if any(x["piece_id"] not in cov for x in p["pieces"])]
    return initialize(output, ids, {
        "review_run": str(run), "inventory_sha256": fingerprint(inv),
        "coverage_sha256": fingerprint(cov), "provider": inv["selection"]["provider"],
        "selected_conversations": len(inv["conversations"]),
        "already_reviewed_pieces": len(cov),
        "historical_summary_files_are_not_raw_review": True,
    }, model, effort)


def review_loader(plan: dict) -> Callable[[str], dict]:
    from . import reconciliation as r
    identity = plan["identity"]
    run = Path(identity["review_run"])

    def get(pid: str) -> dict:
        inv = r.checked_inventory(run)
        if fingerprint(inv) != identity["inventory_sha256"] or fingerprint(r.coverage(run)) != identity["coverage_sha256"]:
            raise ExtractionError("Frozen review inventory or coverage changed")
        return r.packet(run, packet_id=pid)
    return get


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="Freeze only pending raw-review packets; no model call")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--effort", choices=("low", "medium", "high", "xhigh"), default="medium")
    for command in ("run", "status", "recover"):
        p = sub.add_parser(command)
        p.add_argument("--state", type=Path, required=True)
        if command == "run":
            p.add_argument("--allow-model-transfer", action="store_true")
            p.add_argument("--max-calls", type=int, default=20)
            p.add_argument("--max-tokens", type=int, default=200000)
            p.add_argument("--max-prompt-chars", type=int, default=80000)
            p.add_argument("--timeout", type=int, default=180)
            p.add_argument("--codex", default="codex")
        if command == "recover":
            p.add_argument("--confirm-worker-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = prepare_from_review(args.run, args.output, args.model, args.effort)
        else:
            plan, state = read_state(args.state)
            if args.command == "status":
                result = summary(state)
            elif args.command == "recover":
                if not args.confirm_worker_stopped:
                    raise ExtractionError("Confirm the interrupted worker has stopped before recovery")
                result = recover(args.state, review_loader(plan))
            else:
                if not args.allow_model_transfer:
                    raise ExtractionError("Live extraction sends packet text to the configured Codex provider; require --allow-model-transfer")
                from .codex_worker import CodexWorker
                worker = CodexWorker(args.codex, args.timeout)
                result = execute(args.state, review_loader(plan), worker,
                                 args.max_calls, args.max_tokens, args.max_prompt_chars)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ExtractionError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
