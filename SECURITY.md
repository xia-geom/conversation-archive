# Security

## Report privately

Do not include real conversations, credentials, personal paths, or full model logs in a public issue.
Use GitHub's **Security → Report a vulnerability** when available. Private reporting must be enabled by the repository owner; this file does not enable it. Until then, use an existing private contact with the owner, or open an issue containing only “Please enable private vulnerability reporting”, without vulnerability details or attachments.

A useful private report identifies the affected commit, a minimal synthetic reproduction, impact, and any proposed mitigation. Do not send a real archive to reproduce a bug. No response-time guarantee or bug-bounty program is offered.

## Supported scope

This is an experimental alpha. Security fixes target the latest default-branch code and latest alpha; older snapshots are not separately maintained. No claim of production hardening, zero hallucinations, or complete prompt-injection resistance is made.

Original exports are read-only inputs. Model output is untrusted and does not authorize its own promotion. Exact quotes establish provenance, not semantic truth. Keep one canonical writer; the legacy Markdown writer does not acquire a shared cross-process archive lock.

Live Codex extraction sends packet text to the configured provider only after explicit opt-in. Read-only sandbox settings are not hermetic read isolation. Use an isolated, operator-inspected environment for sensitive data. Budget limits are observed between calls, can overshoot one call, and do not measure subscription credits or provide a hard dollar cap.

CI uses synthetic data, hosted runners and minimum job permissions. Do not run outside contributions on machines that contain private archives or account credentials. Release jobs must never check out a contributor's untrusted branch with a write token.

[Data flow and retention](PRIVACY.md) · [Publication gates](docs/public-alpha.md)
