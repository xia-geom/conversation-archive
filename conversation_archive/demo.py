"""Offline synthetic raw-export -> candidate demonstration, NOT a model evaluation."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from . import autonomy as a
from .extraction import ExtractionError, request_for, validate_proposal

MASTER = '''---
entry_count: 1
distinct_retained_sources: 0
correction_count: 0
next_entry_id: "E0002"
next_source_id: "SRC-001"
next_correction_id: "COR0001"
---
# Invented archive
<a id="e0001"></a>
## E0001 — Invented garden
The owner planted mint.
'''


def synthetic_export() -> list:
    def node(nid, parent, children, role, text):
        return {"id": nid, "parent": parent, "children": children,
                "message": {"id": "shared-id" if role == "user" else nid,
                            "author": {"role": role}, "create_time": 1700000000,
                            "content": {"content_type": "text", "parts": [text]}, "metadata": {}}}
    first = {"id": "invented-one", "title": "Invented garden", "create_time": 1700000000,
             "conversation_template_id": "invented-project", "current_node": "b",
             "mapping": {"u": node("u", None, ["a", "b"], "user", "I planted mint. 我今天种了薄荷。"),
                         "a": node("a", "u", [], "assistant", "You may enjoy gardening."),
                         "b": node("b", "u", [], "assistant", "An alternative suggestion, not an owner fact.")}}
    second = {"id": "invented-two", "title": "Invented draft and media", "create_time": 1700000001,
              "conversation_template_id": "invented-project", "current_node": "u",
              "mapping": {"u": node("u", None, [], "user", "Draft: I will plant basil tomorrow. The photo is unavailable.")}}
    content = second["mapping"]["u"]["message"]["content"]
    content["content_type"] = "multimodal_text"
    content["parts"].append({"content_type": "image_asset_pointer", "asset_pointer": "invented-missing-image"})
    return [first, second]


def fixture_worker(request: dict, attempt: Path, plan: dict) -> dict:
    """Echo source spans with unknown attribution; never pretend to reason about them."""
    coverage, candidates = [], []
    for p in request["pieces"]:
        if p["already_covered"]:
            continue
        usable = bool(p["text"]) and p["segment_index"] >= 0
        cid = "fixture-" + str(len(candidates) + 1)
        coverage.append({"piece_id": p["piece_id"], "disposition": "candidate" if usable else "no_extractable_content",
                         "reason": "Synthetic echo fixture; not semantic review.", "candidate_ids": [cid] if usable else []})
        if usable:
            candidates.append({"candidate_id": cid, "category": "other",
                               "attribution": "assistant_content" if p["role"] == "assistant" else "unknown",
                               "statement": p["text"], "uncertainty": "Offline fixture; human review needed.",
                               "evidence": [{"piece_id": p["piece_id"], "start": 0, "end": len(p["text"]), "quote": p["text"]}]})
    return {"proposal": {"packet_id": request["packet_id"], "coverage": coverage, "candidates": candidates},
            "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}, "error": None,
            "provider": "synthetic-echo-not-an-llm"}


def run_demo(output: Path) -> dict:
    from .pipeline import normalize
    from . import reconciliation as r
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ExtractionError("Demo output must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw.json").write_text(json.dumps(synthetic_export(), ensure_ascii=False), encoding="utf-8")
    (output / "local.toml").write_text('[[sources]]\nprovider = "chatgpt"\npath = "raw.json"\n', encoding="utf-8")
    normalize(output / "local.toml", output / "dataset")
    master_root = output / "archive"
    master_root.mkdir()
    master = master_root / r.FILES[0]
    master.write_text(MASTER, encoding="utf-8")
    for name in r.FILES[1:]:
        (master_root / name).write_text("# Invented report\n", encoding="utf-8")
    before = {name: r.sha_file(master_root / name) for name in r.FILES}
    r.prepare(output / "dataset", master, output / "review", project_id="invented-project", max_chars=40)
    state = output / "extraction"
    a.prepare_from_review(output / "review", state, "synthetic-echo-not-an-llm")
    plan, _ = a.read_state(state)
    loader = a.review_loader(plan)
    first = a.execute(state, loader, fixture_worker, max_calls=1)
    completed = a.execute(state, loader, fixture_worker, max_calls=1000)
    replay = a.execute(state, loader, fixture_worker, max_calls=1000)
    request = request_for(loader(plan["packet_ids"][0]))
    invalid = copy.deepcopy(fixture_worker(request, output, plan)["proposal"])
    invalid["candidates"][0]["evidence"][0]["quote"] = "A fabricated quotation."
    rejected = False
    try:
        validate_proposal(request, invalid)
    except ExtractionError:
        rejected = True
    result = {"fixture_only_not_model_accuracy": True, "selected_conversations": 2,
              "packets": completed["packets"], "first_pass_calls": first["calls_started"],
              "total_fixture_calls": completed["calls_started"],
              "replay_extra_calls": replay["calls_started"] - completed["calls_started"],
              "all_candidates_extracted": completed["all_candidates_extracted"],
              "fabricated_quote_rejected": rejected,
              "raw_reviewed_pieces": r.status(output / "review")["covered_pieces"],
              "canonical_files_unchanged": before == {name: r.sha_file(master_root / name) for name in r.FILES}}
    a.atomic_json(output / "demo-report.json", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_demo(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
