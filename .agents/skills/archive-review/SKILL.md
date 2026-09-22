---
name: archive-review
description: Prepare evidence-bound archive review questions or structured draft answers, and use the local HTML and checked snapshot workflow. Use for contradiction review, explicit identity grouping, and reusable review forms. Do not use to infer medical facts, bypass authorization, or automatically apply proposed answers.
---

# Archive review

Read `AGENTS.md`, `project.json`, and `docs/flexible-review.md` from the repository root. Use `docs/snapshot-review.md` for exact commands. This skill is an instruction workflow, not an alternate archive writer or access permission.

## Establish the task

Inspect the implemented CLI help, selected snapshot manifest, existing sessions, prior decisions, and authorized source coverage. Reuse completed extraction. Keep originals unchanged and Health/Emotion scopes separate. Repository maintenance alone does not authorize access to a neighboring personal archive.

Private source text and answers must not enter remote model prompts without explicit transfer authorization. If authorization is absent, use local deterministic tooling and a local human-review page; do not read private contents into the agent transcript merely because a file is local. Use synthetic fixtures for code and CI.

## Prepare questions, not conclusions

Prioritize meaningful discrepancies, not approval of every candidate link. Cite exact entry IDs and Unicode-character spans. Preserve attribution, uncertainty, event dates versus message dates, and source coverage. Several sources can support one question; grouping a display is not evidence that events match. Do not manufacture missing text, dates, units, source links, or relationships.

Use registered conflict or relationship cases for their existing outcomes. Identity grouping must use actual saved-question mention IDs and the preparer's checked scope. Use `kind: form` for other questions, combining only the documented choice, multi_choice, text, groups, and visible_when controls. General forms are record-only. Do not supply arbitrary HTML, JavaScript, executable expressions, automatic defaults, or a new archive effect in a form.

A batch is 15 questions by default, adjustable, never padded. Preserve the entire prepared queue. Identity questions are optional unless they materially resolve the user's issue. Surface unknowns instead of forcing a classification.

## Answer and apply

Prefer local HTML for explicit group assignments and repeated review. A user may instead answer in chat; preserve the verbatim answer and compile only its stated finite scope into the same versioned answer JSON. Show that interpretation and require approval before application. Unclear language remains a draft, not a confirmed grouping. Unknown does not mean different. Free text is not automatically an executable correction.

Run prepare, let the user save/export explicit answers, then run preview. Inspect the preview's changed bindings, values, scope, and withdrawals. Apply only actual authorized user decisions with `--confirm-user-answer` to a new output path. Never select answers yourself to clear the queue. Retain unanswered cases, prior decisions, deferrals, and stale drafts. A refusal caused by unsupported independent dependencies must not be bypassed.

## Finish

Report selected snapshot, prepared and answered counts, actual checks, successor path when one was created, unresolved work, and limitations without exposing private passages. Run synthetic unit and browser tests when changing code. Do not claim semantic discovery, completeness, a successful merge, or a personal-data update from schema validity alone.
