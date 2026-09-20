# From conversations to supported master entries

The importer makes original exports consistently structured and traceable. Reconciliation connects reviewed evidence to the living master. These are different operations: valid JSON does not tell us whether an account is true, whether two memories concern the same event, or whether a feeling is still current.

## The workflow

Use the implemented CLI help to see arguments for the `reconcile` command group. Its stages are:

| Command | Result | Does not establish |
| --- | --- | --- |
| `prepare` | Frozen selection and provenance inventory | That any conversation was read |
| `packet` | Readable source spans with branch and attribution labels | That a review occurred |
| `record` | Explicit findings and reviewed coverage | That the master was updated |
| `status` | Pending, partial, completed, or blocked state | Coverage outside the frozen selection |
| `check` | Structural and preservation checks for a proposed update | Historical or psychological truth |
| `apply` | Checked installation and recorded integration state | Resolution of facts the evidence leaves uncertain |

Real inputs, paths, inventories, findings, and reports stay local and outside Git. This example is invented; use synthetic fixtures for practice.

## An invented conversation

A user writes: “On Tuesday I waited outside the studio. I felt embarrassed and went home.” An assistant replies: “Perhaps you feared rejection.” Later the user writes: “I returned on Friday and enjoyed the class.”

Before reading the clean representation, predict what belongs in the record. The Tuesday and Friday events were reported by the user. Fear of rejection is an assistant interpretation. The message timestamps tell us when those reports were recorded; without more evidence, they do not establish the calendar dates of Tuesday and Friday.

1. Prepare an inventory that identifies the invented conversation and its source hash. Generate its reading packet. Check the speaker labels, source locations, and parent links against the source.
2. Read the entire packet, including the later message. If an extraction request appeared between the Tuesday and Friday messages, it would not justify discarding Friday.
3. Compare with the relevant master entry. Suppose it already records Tuesday's visit and embarrassment. Record Tuesday as already represented, and Friday as complementary detail if the evidence establishes the same continuing account. Keep the assistant interpretation separate; it is not a confirmed motive.
4. Record the exact supporting passage and source locator for Friday. A proposed addition might read: “In a later message, the owner reported returning on Friday and enjoying the class. The calendar date remains unspecified.” Preserve the original wording alongside it.
5. Check the proposed update and reports. Confirm that the old entry ID remains, source references resolve, and no archived wording changes. Apply only after those checks pass. Repeat the completed application and verify that no duplicate addition appears.

If the Friday message instead describes another studio and the relationship is uncertain, record uncertain overlap. Do not turn an attractive narrative into a factual connection.

## Branches and interruptions

A revised branch may describe a different feeling. Keep both versions, their ancestry when exported, and their source locations. Similar text is not sufficient to merge them. If the provider does not identify a selected branch, label it unknown.

Long messages are split into exact labeled character ranges. A conversation stays partially reviewed until every required span has an outcome. Missing attachment bytes stay an access gap, even if the attachment's name is available.

Review records survive interrupted work. Installation uses checked per-file replacement with a journal; it is not one atomic operation across the master and reports. Recover any partial installation before claiming the batch integrated. Preserve historical findings through dated superseding records instead of silently changing their meaning.

## What to learn from the checks

Try a synthetic stale-patch case: after preparing a patch, change its expected starting text in the synthetic master. The check must reject the mismatch. Investigate whether the source, the proposed edit, or the master changed; do not bypass the check merely to finish.

A successful check establishes traceability and structural consistency. It cannot decide whether the remembered events happened exactly as described or whether an assistant's interpretation is appropriate. Those questions require evidence, careful attribution, and sometimes the owner's answer. Keep that boundary visible in both the master and the coverage report.

## Run a small synthetic review

Run these commands from the repository root. They use only the invented fixtures, create an isolated miniature archive under ignored `data/demo-review/`, and never open the personal master. Start with a fresh demo directory; initialization refuses to overwrite an earlier exercise.

First create the miniature master, empty reports, and a synthetic membership observation:

```sh
python3 - <<'PY'
import json
from pathlib import Path

root = Path('data/demo-review')
root.mkdir(parents=True, exist_ok=False)
archive = root / 'archive'
archive.mkdir()
(archive / 'emotion_master.md').write_text('''---
entry_count: 1
distinct_retained_sources: 0
correction_count: 0
next_entry_id: "E0002"
next_source_id: "SRC-001"
next_correction_id: "COR0001"
---
# Invented practice archive
<a id="e0001"></a>
## E0001 — An invented garden
This is an exercise, not a personal record.
''', encoding='utf-8')
for name in ('correction_review_report.md', 'corrections_before_after.md'):
    (archive / name).write_text('# Invented practice report\n', encoding='utf-8')
(root / 'membership.json').write_text(json.dumps({
    'conversation_ids': ['invented-gpt-two'],
    'observed_at': '2026-01-01T00:00:00Z',
    'evidence': 'Invented fixture selection for this exercise; no real UI observation.',
    'project_name': 'Invented practice project'
}, indent=2) + '\n', encoding='utf-8')
PY
python3 -m conversation_archive normalize --config tests/fixtures/demo.toml --output data/demo-review/dataset
python3 -m conversation_archive reconcile prepare --dataset data/demo-review/dataset --master data/demo-review/archive/emotion_master.md --run data/demo-review/run --provider chatgpt --membership data/demo-review/membership.json --max-chars 40000
python3 -m conversation_archive reconcile packet --run data/demo-review/run --output data/demo-review/packet.json
python3 -m conversation_archive reconcile status --run data/demo-review/run --details
```

The inventory selects one invented conversation. The status should still be `pending`: creating its packet does not mean anyone read it.

Now display and **read every piece**. Check the Chinese/French garden sentence, its role and source location, and the explicitly labeled internal-assistant-content placeholder. The placeholder means that material is excluded from substantive owner evidence; it does not mean hidden reasoning was read.

```sh
python3 - <<'PY'
import json
from pathlib import Path

packet = json.loads(Path('data/demo-review/packet.json').read_text())
print(packet['conversation']['title'])
for piece in packet['pieces']:
    print('\nRole:', piece['role'], '| Kind:', piece['kind'])
    print('Source:', piece['json_pointer'])
    print('Range:', piece['start'], piece['end'])
    print(piece['text'] or '[Explicit empty/internal-content placeholder]')
PY
```

After reading, record the exercise's explicit decision: none of this invented material belongs in a personal archive. This exclusion is specific to these synthetic fixtures. Do not reuse this blanket decision for real conversations; their outcomes require individual comparison with the actual master.

```sh
python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path('data/demo-review')
packet = json.loads((root / 'packet.json').read_text())
assert packet['conversation']['original_id'] == 'invented-gpt-two'
decision = {
    'decision_id': 'demo-explicit-review',
    'reviewer': 'Reader completing the synthetic walkthrough',
    'reviewed_at': datetime.now(timezone.utc).isoformat(),
    'coverage': [{
        'piece_id': piece['piece_id'],
        'outcome': 'excluded',
        'reason': ('Internal assistant content is a labeled excluded placeholder, not owner evidence.'
                   if piece['kind'] == 'internal_assistant_content' else
                   'Read the invented garden text; excluded because this exercise is not personal history.'),
        'finding_ids': []
    } for piece in packet['pieces']],
    'findings': []
}
(root / 'decision.json').write_text(json.dumps(decision, indent=2) + '\n', encoding='utf-8')
PY
python3 -m conversation_archive reconcile record --run data/demo-review/run --document data/demo-review/decision.json
python3 -m conversation_archive reconcile status --run data/demo-review/run --details
python3 -m conversation_archive reconcile check --run data/demo-review/run
```

The conversation should now be `reviewed_not_integrated`, with `complete: false`. The check validates the miniature master and reports; it does not install anything. Repeating the identical `record` command returns `already_recorded` without increasing coverage. A future integration batch must specify exact before/after patches and hashes for the master and both reports, then use `check --batch ...` before `apply --batch ...`.

## Resolving a finding without importing its decision twice

Applying the identical batch ID and document again returns `already_applied`. A different batch cannot ordinarily reuse an installed decision: that could append the same addition twice even when its file hashes and report IDs are valid.

To resolve a previously `unresolved` finding, add this field to the new batch document, alongside its existing `decision_ids`, `finding_dispositions`, and checked file patches:

```json
{
  "resolution_revision": {
    "prior_batch_id": "invented-prior-batch",
    "finding_ids": ["invented-decision/F1"],
    "reason": "Additional review established the disposition of this formerly open finding."
  }
}
```

These are invented identifiers, not a runnable batch. Each finding ID here is the full `decision_id/finding_id` key. The referenced prior batch must be the latest completed batch for every reused decision. Every reused decision must resolve at least one declared open finding. Only declared `unresolved` outcomes may change, to `integrated`, `already_represented`, or `excluded`; all other finding dispositions must remain exactly unchanged. The normal quotation, entry-link, source, file-hash, and report checks still apply. Group revisions with different prior batches into separate batches.

Use a separately reviewed correction for changes to an already resolved account; this narrow field cannot silently reopen it or import it again. The journal retains the earlier unresolved outcome. Status uses the latest completed disposition by timezone-aware completion instant, rejecting ambiguous tied orders. An interrupted resolution must be recovered before another batch proceeds.

## Text completion and media gaps

`complete` describes the frozen selection's exported-text/record accounting and installed dispositions; it does not certify that images, audio, or attachment bytes were inspected. Status separately reports `media_gap_count` and `conversations_with_media_gaps` from active review decisions. Repeating an application does not increment these counts, and repeated declarations of the same source occurrence count once. Original message IDs reused in separate conversation memberships remain distinct.

Declare such gaps in a decision's `media_gaps` list. Prefer `message_record_id` plus the source `json_pointer`; this identifies the exact occurrence. Existing original `message_id` plus `part_index` records are also recognized within that decision's covered membership. These counts describe declared gaps, not an automated certification that every attachment was examined. Preserve the gap description and report it alongside any text-completion claim.

### Read a packet as Markdown

Add `--format markdown` to `reconcile packet` for a readable view on stdout, or combine it with `--output` and a fresh temporary path. JSON remains the default for programmatic use. Both views include exact segment character ranges, source hashes and pointers, branch alternatives, and the exported selection when known. Rendering either view does not record coverage. Delete temporary packets when no longer needed; the frozen inventory and decisions remain the durable record.
