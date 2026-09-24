# Agent operating contract

Maintain **one organized Markdown file containing the key information from chats**, useful to the user and ChatGPT. Start with [ARCHITECTURE.md](ARCHITECTURE.md), then the relevant part of [the workflow](docs/workflow.md). Do not turn this into a database, graph, or general review-application project.

## Work from actual evidence and current state

Inspect the branch, diff, CLI help, current document, authorized inputs, and existing checkpoints. Preserve uncommitted work. Do not restart completed extraction or reset budgets. Repository changes do not authorize reading or changing a neighboring personal archive.

Keep original exports unchanged. Read exact source passages through the existing packet/inspection tools; do not substitute an earlier summary. Preserve attribution, language, event-date uncertainty, message IDs and source locators. Separate owner reports, pasted quotations, plans, dreams, assistant suggestions, and interpretations. A timestamp is not an event date; similarity is not identity or causation.

## Produce useful Markdown

Organize by meaningful subjects and, where helpful, chronology. Keep self-contained entries with stable IDs, important qualifications, exact supporting excerpts and source references. Do not copy every chat or reduce useful information to vague summaries. Connect related information in the document without constructing a separate entity registry.

Compare with the current Markdown before adding anything. Preserve manual edits and prior corrections; record later corrections without erasing earlier evidence. Do not promote repeated assistant claims into corroborated facts. Surface contradictions that change a meaningful account, not every uncertain link. Ask contextual questions in small batches only when necessary; unanswered or deferred items stay unresolved.

Use the same reviewed patch contract for answers collected in chat or any optional interface. A proposed answer is not an approved decision. Do not automatically apply extraction candidates. Apply only authorized reviewed edits with the checked writer and show the diff first.

## Updates and privacy

New collections use `organize prepare --document ...`; no SQL, machine-snapshot migration or separate correction-report files are required. Resume old `--master` runs under their existing contract; see [compatibility](docs/compatibility.md). Do not delete or silently migrate real snapshots, decisions, databases or exports when code is retired.

Run the check before application, retain expected hashes, and recover incomplete installation before proceeding. The document lock coordinates this writer, not arbitrary editors. Keep history and replay idempotent.

Real exports, Markdown, state, prompts, drafts and generated views stay outside Git. Local files are not automatically offline model processing. Obtain explicit authorization before sending contents to a remote model or uploading to ChatGPT. Preserve existing transfer and cumulative-budget gates; do not retry ambiguous paid attempts blindly. No credentials in code, reports or logs.

## Challenge the design

Do not agree with architectural proposals merely because they are stated confidently. Test the primary reader's actual search → entry → context → source path before adding infrastructure. Poor access is a design defect, not something an agent should compensate for. Do not assume Markdown indexes better than JSONL without a real test; Markdown is the requested deliverable, not a claim of universal retrieval superiority.

Keep one editorial authority and only necessary bookkeeping. Prefer removing an unnecessary feature over disguising it behind another adapter. Do not add a second index, schema registry, service, skill or representation without a demonstrated workflow need.

## Verify and report

Run `python3 -m unittest discover -s tests -v` and the Markdown demo. Use synthetic fixtures in Git and CI. Test quotation/provenance checks, source preservation, manual edits, changed exports, stale drafts, replay, interruption and no SQL dependency—not only valid schemas.

Report actual changes, removed/consolidated files, commands run, observed test results, commit/PR state, and limits. Do not claim a merge, live-model evaluation, ChatGPT retrieval test, or personal-data update without evidence.
