# Walkthrough: follow the evidence

Every conversation in `tests/fixtures/` is invented. Run these commands from the repository root with Python 3.11+. This exercise needs no GitHub login, model, or external service.

## 1. Inspect raw data and make a prediction

Open `tests/fixtures/chatgpt.json` and `tests/fixtures/claude.json` in your editor. Find:

- A ChatGPT null-message root and two alternative replies to one user message.
- The same original user message ID in another ChatGPT conversation.
- A Chinese/French string with a newline and an emoji.
- Claude's top-level text that differs from its text block.
- An empty Claude conversation, an empty message, and an extracted attachment string.

Predict the result before running code: **four conversations, eight message occurrences, two attachment references, and two branch points**. The repeated original message ID contributes two message rows. A null graph node contributes no message row. An empty message object with an ID still contributes a row.

## 2. Run the importer

```sh
python3 -m conversation_archive normalize --config tests/fixtures/demo.toml --output data/lesson
python3 -m conversation_archive validate --dataset data/lesson
```

Read the printed `counts` and `statistics`. The report should pass with warnings for missing attachment bytes, repeated message IDs, and missing creation metadata. A warning does not mean a failed import; it records something you should not silently assume away.

This configuration uses relative paths resolved beside the TOML file. The importer hashes original bytes, projects records, validates against those same bytes, and installs the dataset only after passing. It does not edit the fixture files.

## 3. Trace a clean record back

```sh
python3 -m conversation_archive inspect --dataset data/lesson --kind messages --line 1
```

Compare `clean.raw` with `original`: they should be equal. Locate `provenance.json_pointer` and follow it into the source. Look at each `text_segments` pointer to see exactly where a string came from. The slash/tilde in one mapping key demonstrates JSON Pointer escaping.

Now inspect the Claude reply without depending on output ordering:

```sh
python3 - <<'PY'
import json
from conversation_archive.pipeline import inspect_record
from pathlib import Path
root = Path('data/lesson')
for line in (root / 'messages.jsonl').open(encoding='utf-8'):
    record = json.loads(line)
    if record['original_id'] == 'invented-c-a':
        pair = inspect_record(root, record_id=record['record_id'])
        print(json.dumps(pair, ensure_ascii=False, indent=2))
PY
```

Why are there two text segments with different wording? They are two representations in the export, not two utterances. Which would you use for a future word count? That is an analysis choice requiring documentation, not something the importer should conceal.

## 4. Check repeatability

```sh
python3 -m conversation_archive normalize --config tests/fixtures/demo.toml --output data/lesson-repeat
python3 - <<'PY'
from pathlib import Path
first = Path('data/lesson')
second = Path('data/lesson-repeat')
for path in sorted(first.iterdir()):
    assert path.read_bytes() == (second / path.name).read_bytes(), path.name
print('All five output files are byte-identical.')
PY
```

The same sources, configuration, file availability, and importer version produce the same dataset bytes. A different output directory does not affect them. Changing source locations affects the manifest; changing source bytes affects source and record IDs.

## 5. Investigate a deliberate failure

Create a **disposable derived copy of invented data**, then change a projected text string. Never do this to a real source.

```sh
python3 - <<'PY'
from pathlib import Path
import json
import shutil
source = Path('data/lesson')
broken = Path('data/lesson-broken')
shutil.copytree(source, broken)  # refuses an existing destination
path = broken / 'messages.jsonl'
rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
rows[0]['text_segments'][0]['text'] = 'A careless paraphrase.'
path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
PY
python3 -m conversation_archive validate --dataset data/lesson-broken
```

This intentionally exits with status 1. Read the error codes: the file hash changed, and the text no longer matches its source. The validator catches the evidence mismatch as well as the byte change. The original fixtures and valid dataset are untouched.

Would a matching hash prove the text describes a true event? No. It establishes a relationship to retained bytes, not historical truth. Would changing the manifest hash conceal a paraphrase? The independent source comparisons should still catch it; that scenario has a dedicated unit test.

## 6. Find the code behind one check

Run:

```sh
python3 -m unittest discover -s tests -v
```

Open `tests/test_pipeline.py` and find `test_fidelity_check_independent_of_manifest_hash`. Read its setup, alteration, and assertion. Then find `text_fidelity` in `conversation_archive/validation.py`. You do not need to memorize the implementation: explain the claim being tested, the evidence it uses, and the failure it would catch.

For another exercise, inspect `test_absent_child_lists_keep_parent_graph`. It distinguishes an omitted field from an explicitly contradictory relationship—an example of why understanding the data matters more than assuming an API shape.
