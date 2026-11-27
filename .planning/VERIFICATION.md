# Verification — native worker/controller readiness

Date: 2026-11-27. Current development is ticketless; the product PR pilot is deferred by the owner.

## Live evidence

CLI owner identity, the dedicated Collegium project and the repository-scoped GitHub App connection were checked. Main MCP discovery found 27 tools and an authenticated list_spaces call succeeded; help MCP OAuth discovery found all three help tools. Credentials are resolved from the private lap configuration and never included in receipts.

Six version-2 workers are provisioned and bound in config/readiness.json. Actual sessions verify Sol/high for planner/plan reviewer/code reviewer, Sol/low for executor/fixer, and Luna/medium for sentinel. Runtime is aranarium 0.78.1 with explicitly selected Codex 0.153.4.

Native run `d93b0a8a-0084-48ec-b43f-6c3c1a5dadf4` completed five stages: planning, independent plan review, implementation, validation and independent code review. Validation executed seven pinned cases against generated solution.py in the remote sandbox. It did not execute generated code on the coordinator or alter the connected repository.

[Readiness report](../reports/readiness.json) contains stage/session/turn identities, configuration digests, all six role proofs, usage limitations and observation rechecks. Raw authenticated observations and content-addressed artifacts remain private under .local. [Replay evidence](../reports/replay-check.json) records completed-run replay with no additional sessions. `make doctor-readiness` returns exit 0, execution_ready true, with all six checks passing; the separate delivery profile remains disabled.

## Effort evidence boundary

The verifier checks actual platform session/turn identity, user-message trace correlation, the first tool command, its matching successful result, agent configuration digest and selected model/effort. The pinned probe reads only Codex process command lines and returns filtered PID/harness/model/effort fields. It does not expose complete arguments, environment or keys. Worker final JSON is not accepted as runtime proof.

The shell/heredoc frame must match; the Python body may differ only by AST-equivalent formatting. A native executor collapsed a dictionary over fewer lines: the initial exact-text verifier rejected it. After correcting the verifier and adding negative tests, the existing completed turn was explicitly re-observed with an audit reason. No replacement run was launched for that correction.

Proof kind is first_tool_codex_process_arguments: it proves the Codex client's launch selection, not provider-internal reasoning, consumed compute or a signed remote attestation. Official runtime source also forwards effort into Codex turn/start.

## Local verification

`make check` passed Ruff lint/format, 68 unit tests and compile checks. Coverage includes duplicate/replay admission, stage provenance, independent reviews, configuration pinning, stale revisions/CI, launch ambiguity, remote observations, effort mismatch and forged output rejection, pinned probe/validation commands, readiness report rejection, timeout cancellation/quarantine and credential-safe transport.

Inline implementation review corrected provenance, configuration pinning, replay and cancellation boundaries. Real independent workers reviewed the synthetic plan and generated solution; that does not constitute an independent audit of the coordinator implementation.

## Material limitations

Actual Contributor session creation returned repository_not_given: main lacks the active, non-bypassable protection rules needed for a write token. Installation-level connection checks alone did not catch this. Readiness therefore uses separate read-only executor/fixer variants. No protections were modified or bypassed.

Gateway accounting reports uncounted turns and zero listed USD; zero is not evidence of free execution. USD budget enforcement remains unavailable. Token limits apply before admission and may be exceeded by the final turn; time/attempt bounds and the worker runtime limit are separate controls.

No product task-to-PR run, external CI delivery, PR creation, Jira write, merge, cloud automation, PostgreSQL coordination, parallel epic scheduling or investigation workflow is claimed complete. No target source files or local Git history were changed.

## PR broker and CI repair implementation

The ticketless follow-up implemented broker.py, delivery.py, delivery_workers.py and ci.py, plus explicit deliver/status CLI wiring, disabled delivery configuration, eight version-3 read-only worker bindings and variant-aware provisioning/doctor checks.

Twenty-nine delivery tests exercise the complete driver through the native observation adapter using stateful API fixtures: planning/review, implementation, candidate commit, actual-command validation evidence, independent review, PR, red CI, bounded fixer, fresh validation/review, green CI and ready-for-acceptance. These are local contract tests, not real GitHub Actions or native repository-write evidence. The full 68-test suite, lint/format and compilation pass.

Crash/recovery cases cover a lost commit response and lost PR response with no duplicate mutation, unobservable pending effects, concurrent base/head changes, unchanged failure effort low/high/xhigh versus changed-diagnostic reset, review/plan rejection, missing/skipped CI, job/attempt limits, validation-result forgery, disabled writes, occupied branches, stale-green replay and cancellation quarantine. Inline review added exact-tree verification, because a commit message marker alone cannot prove candidate contents. Each final status re-observes GitHub.

Read-only live GraphQL introspection confirmed expectedHeadOid, CommittableBranch and FileChanges, plus createCommitOnBranch and draft/ready mutations. The broker rejects PAT/personal gh fallback and multi-repository installation scope. Live doctor verified eight worker configuration digests; it correctly reports execution_ready false because the installation credential is absent and the profile remains disabled.

No product task was selected. No target branch/commit/PR, Jira issue, merge or cloud automation was created, and local changes remain uncommitted. Native broker-write/CI acceptance, token mint/refresh integration and production coordination remain unverified. See [delivery design and commands](../docs/DELIVERY.md).

A separate read-only native delivery checkout diagnostic passed using version-3 planner agent_75df2208ac524fc292399f09c10e0b27: session ses_4b6612872c61470697fcc245781c4bb5, turn run_a94d566b489c40fb8a72d7da15dd24b4. Authenticated tool events prove Sol/high and the exact checkout command successfully cloned the private repository and checked out dd3c5a022c46d749e146776f43c5266a512011c4. This was a service diagnostic with no product implementation, target writes or PR. Filtered evidence is in [delivery-checkout.json](../reports/delivery-checkout.json); raw observations remain private. It does not verify native candidate publication or CI repair.
