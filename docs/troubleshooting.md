# Troubleshooting

[Overview](../README.md) · [Quickstart](getting-started.md) · [Documentation](README.md)

Start with the symptom below. Preserve real run state and source files while investigating; do not delete checkpoints or disable validation just to get a successful status.

## Getting started

| Symptom | What it means | What to do |
| --- | --- | --- |
| Clone reports not found or access denied | The URL is wrong or the current account cannot access the repository | Check the repository URL and authenticate with an authorized account; do not paste credentials into an issue |
| Python reports a version below 3.11 | The selected interpreter is too old for this project | Select Python 3.11 or newer and rerun `python3 --version` |
| `No module named conversation_archive` | Python cannot see the package from the current directory | Run from the cloned repository root, where `conversation_archive/` and `pyproject.toml` are present |
| The demo requires POSIX locking | The candidate controller needs macOS or Linux | Use a supported environment for the demo; do not remove the locking checks |
| `Demo output must be new or empty` | That example was already initialized | Inspect the existing output or use a different demo directory, such as `data/second-run` |
| Status says candidates are complete but raw review is zero | Extraction and review are different stages | Follow the separate reconciliation exercise; this is expected in the offline demo |

## Importing and reading evidence

| Symptom | What it means | What to do |
| --- | --- | --- |
| A configured source cannot be found | A path may be wrong or resolved relative to the config unexpectedly | Check `local.toml` and use explicit absolute source paths |
| A ZIP in an export directory was not imported | Directory discovery does not open ZIPs automatically | Add that ZIP as its own configured source |
| Validation reports changed source/dataset hashes | The frozen evidence no longer matches the saved run | Preserve both versions and investigate; make an explicit new dataset/run rather than editing the old hashes |
| An expected count fails | The source census differs from an independently supplied count | Verify scope and source files; do not change the count merely to suppress the error |
| Attachment text or an image is absent | A pointer is not proof that the bytes are available | Keep the gap visible; do not infer the missing content |
| Claude project membership is unknown | Available metadata may not identify the intended project | Supply independently observed membership; do not select chats by title similarity and call that verified |

## Live Codex extraction

| Symptom or stop reason | Safe next step |
| --- | --- |
| `--allow-model-transfer` is required | Decide whether this data may be sent to the configured provider before opting in |
| CLI preflight rejects required flags | Inspect the installed `codex exec --help` and local setup; do not fall back to broader permissions |
| `call_budget` | The limit counts all attempts in this state; explicitly increase the cumulative allowance only after reviewing usage |
| `observed_token_budget` | Review recorded usage before permitting another call; the threshold is not a hard dollar cap |
| `prompt_size_limit_no_truncation` | Revisit packet sizing through an explicit plan; never silently cut off source text |
| `blocked_attempt_requires_operator_audit` | Inspect the local receipt and response; the controller has no automatic retry/reset command |
| `unknown_usage_requires_operator_audit` | Preserve the unknown cost and inspect provider records; do not substitute zero |
| `recovery_required` | Confirm the old worker has stopped, then use the runbook's explicit recovery command |
| Another controller owns the directory | Check whether another run is active; do not bypass its lock |

A saved successful extraction is skipped on resume. An interrupted attempt is different: the provider may have consumed usage before a response was saved. Blind retries can duplicate spending, which is why recovery is explicit. Full commands and limitations are in the [autonomy runbook](autonomy.md#state-and-recovery).

## Report a reproducible problem

Run the offline demo and tests first when they are relevant:

```sh
python3 -m conversation_archive.demo --output data/support-demo
python3 -m unittest discover -s tests -v
```

Use a fresh demo path. Include the repository commit, Python version, operating system, command with private paths replaced, expected behavior, and a minimal invented input that reproduces the issue. Live-worker issues should also include the CLI version and a redacted error category, not conversation content or credentials.

See [contributing](../CONTRIBUTING.md) and the repository's issue templates. Requests, prompts, responses, event streams, and stderr can all contain private text; uploading the entire run directory is not an acceptable bug report.
