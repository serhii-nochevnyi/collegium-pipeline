# PR broker and bounded repair — 2026-11-27

Ticketless Shipyard bench: implement locally; no pilot task, target writes, commits or PRs during development.

1. Add a GitHub App-only broker with exact repository identity, durable action intent/reconciliation, run-owned branches/PR markers, and atomic expected-head commit updates. Never merge or force push.
2. Add a resumable serial delivery driver and native worker jobs. Each candidate gets remote pinned validation and independent review. CI reads actual exact head/base; pending waits, failures trigger bounded fixes with the existing low/high/xhigh effort policy.
3. Pin validation commands and allowed change paths in a disabled delivery profile. Preserve the readiness profile/report. Test crash/restart, lost responses, duplicate PRs, changed revisions, pending/missing CI, repeated failures, review rejection and limits using local API fixtures.
4. Review code and update verification/docs. Native repository-write/CI validation remains pending repository eligibility and the deferred pilot; fixture success must not be presented as a live PR.

Research: Context7 quota exhausted. GitHub REST docs and read-only live GraphQL schema confirm createCommitOnBranch expectedHeadOid (atomic compare-and-set), file changes and draft/ready mutations. REST ref force=false alone is not an expected-head compare-and-set, so it is insufficient for repaired commits.
