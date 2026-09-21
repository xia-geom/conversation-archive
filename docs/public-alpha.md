# Public alpha: publication, not new product development

[README](../README.md) · [Security](../SECURITY.md) · [Privacy](../PRIVACY.md) · [Release notes](releases/0.1.2a1.md)

## Scope

This preparation adds licensing, publication review, repository maintenance and a draft alpha. It deliberately excludes the proposed new end-to-end workflow and structured-authority migration. Do not start those tasks as part of release preparation or imply they shipped.

## Required owner settings

These are **server settings**, not effects of adding this document or CODEOWNERS. Verify the live state rather than marking them complete from a file.

| Setting | Intended value |
| --- | --- |
| Main-branch protection | Require pull requests and successful `test (3.11)`, `test (3.13)`, and `secret-scan`; disallow force-pushes/deletion; resolve review conversations |
| Review count | Keep a sole-maintainer workflow operable; require an independent approval once another maintainer is available |
| Actions | Read-only default token; approve outside-contributor runs; no private-archive self-hosted runners |
| Private vulnerability reporting | Enable, then verify the Security reporting route |
| Description | Evidence-preserving conversation archives with contextual questions and reusable corrections |
| Topics | `conversation-archive`, `chatgpt`, `claude`, `ai-agents`, `data-provenance`, `python` |
| Visibility | Remain private until the publication review is signed off; then explicitly switch to public |

The current connector has repository-content and PR operations but no administrative settings-write action. A repository owner must apply the remaining settings with an authorized account. Do not weaken an existing rule while applying this checklist.

## Publication gate

Review all available branches/tags/PR refs and history, author metadata, discussions, Actions logs, artifacts, and the demonstration media. The private inventory workflow collects available material without executing historical code and runs a checksum-pinned Gitleaks scanner. Its successful exit means collection finished, **not that publication was approved**. Check its gaps and inspect relevant source content manually.

The repository's author identity and commit email are publication metadata too. A clean current tree or zero scanner findings is not a certification. Rotate exposed credentials before historical cleanup. GitHub-unadvertised/deleted objects and inaccessible resources need separate attention.

Download the private review bundle, record a sanitized summary, and delete raw review artifacts from GitHub before public visibility. Recheck newly introduced commits/logs after the initial audit. Do not rewrite clean history merely to make it appear new.

## Draft release

`alpha-release.yml` creates only a draft prerelease on a trusted main push affecting its release files, or an explicit manual dispatch. It uses minimum permissions per job, retains existing evidence-format versions, and never changes visibility. It reruns existing tests; it does not add or claim the deferred workflow.

After the owner settings and publication gate are complete, publish the draft alpha. Do not publish a PyPI package, automatically announce the release, or message contacts as a side effect. Those destinations and recipients must be selected explicitly.

## Initial invitation (ready to copy)

> I am opening an experimental Conversation Archive alpha: a Python toolkit for preserving ChatGPT/Claude export evidence and reviewing relationships through contextual question batches. It is designed for agent-assisted use, with an offline synthetic demo and explicit limits on what is automated. Try the demo and tell me where the instructions or output become confusing. Please use invented examples in public feedback, not personal conversations. A star is appreciated when you find it useful.

Begin with three to five willing testers. Record what they attempted, where they stopped, and whether the outputs helped; do not claim a completed trial before replies exist. No invitations or promotional posts are sent by these tools.

## References

[GitHub visibility consequences](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility) · [Actions security](https://docs.github.com/en/actions/reference/security/secure-use) · [MIT license](https://choosealicense.com/licenses/mit/)
