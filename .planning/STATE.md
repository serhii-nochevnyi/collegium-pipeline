# Project state

Updated: 2026-11-27

## Confirmed scope

Independent Collegium pipeline: investigate, epic and single-task delivery, parallel execution, model/effort policy, quality gates and configuration. Jira remains in the product design. Current implementation is ticketless. The owner explicitly deferred selecting a pilot PR task until the pipeline is ready; do not request or invent one now. Connected repository: airslate-common/agents-knowledge. Remote Sessions is outside scope.

## Connected and verified

- Official lap v0.23.1, CLI owner authentication, dedicated project prj_7e76b4e4920141a2abbedd46ccb713da in personal space spc_abd49a5569154751a43c006659d9f535.
- Project GitHub App connection ghc_73f2cf589000496f88519d531e798f23 scopes only airslate-common/agents-knowledge, repository ID 1345007429. Read sessions work. Contributor installation checks pass, but actual write-token issuance fails because main lacks required non-bypassable protection. No protection was changed.
- Main MCP: 27 tools, authenticated list_spaces succeeds. Help MCP: OAuth verified, three help tools. Private local header helper reuses lap credentials; no credentials stored in project files.
- Aranarium 0.78.1, Codex 0.153.4. All dispatches explicitly select Codex.
- Six version-2 read-only readiness workers bound: planner and independent plan/code reviewers use gpt-6.2-sol/high; executor and fixer use gpt-6.2-sol/low; sentinel uses gpt-6-luna/medium.
- Actual model and effort observed from Codex process arguments in authenticated platform tool events for all six roles. This proves client configuration, not provider-internal computation.

## Implemented locally

Python CLI, role routing, content-addressed artifacts, durable SQLite serial journal, launch/session/turn identity, ambiguous-write quarantine, live observation ingestion, independent stage review gates, sandbox validation, token admission and timeout/attempt limits. Model/effort and complete agent configurations are pinned. Completed self-test replay creates no new sessions. Provisioning, calibration and report publication scripts are included.

Readiness and delivery profiles are separate. Only readiness is enabled; its executor/fixer have read-only repository grants and operate on synthetic files in disposable sandboxes. Self-test success never marks a PR or delivery complete.

## Evidence

- make check: Ruff lint/format, 68 unit tests and compile check pass.
- Native run d93b0a8a-0084-48ec-b43f-6c3c1a5dadf4 passed planning, independent plan review, implementation, seven actual sandbox checks and independent code review.
- Separate fixer and sentinel calibrations passed. Six role proofs and five stage receipts are in reports/readiness.json.
- make doctor-readiness: exit 0, execution_ready true, all six checks pass. This is readiness-profile status only.
- One observation was rechecked after allowing AST-equivalent Python formatting within the unchanged pinned shell frame. The same completed turn was reused; the audit records the reason.
- No target source mutation, Jira write, PR, merge, automation, branch, worktree or local commit was created. This directory was not initialized as a Git repository.

## Remaining boundaries

Slice 0 connections and the native worker/controller readiness loop are verified. Slice 1 now includes a resumable product delivery driver, GitHub App-only PR broker, atomic expected-head commits, exact-tree reconciliation, validation/review per candidate and bounded CI repair. Stateful API fixtures pass the full red-to-green lifecycle and recovery scenarios. Eight version-3 read-only workers are provisioned/bound, including fixer low/high/xhigh; live doctor verified their configuration digests. The previous native readiness effort proofs belong to the separate version-2 workers.

The new delivery profile is disabled. A short-lived, single-repository GitHub App installation credential is not configured; no person-key/PAT fallback is used. A native version-3 planner probe and private checkout at an exact commit passed (reports/delivery-checkout.json); native repository-write/PR/CI acceptance and token refresh integration remain to verify. PostgreSQL/action claims and cloud deployment are unfinished, as are epic scheduling and investigation. See docs/DELIVERY.md and reports/delivery-verification.json. A read-only checkout diagnostic may be run independently of any product pilot.

Collegium write-token policy requires protected main: PRs, at least one approving review, code-owner review, stale approval dismissal or last-push approval, no deletion and no force push, with no bypass. The earlier Contributor token failure remains recorded. New workers stay read-only; the broker uses separate installation authority whose eligibility still needs verification. Do not weaken policy or substitute a PAT.

Gateway spend returns uncounted turns, so no USD ceiling is enforced. Token limits are admission checks and can be exceeded by the final admitted turn; they are not a hard provider cap. The report retains both limitations. Continue preparing delivery infrastructure without choosing a pilot task on the owner's behalf.


## Live GitHub App service-test follow-up

The owner explicitly authorized a real service PR/red-to-green CI (no product pilot). A real Contributor session admission was attempted and refused with HTTP 400 repository_not_given before any session/model turn. App main-rule eligibility remains the actual blocker. The current user has push but no maintain/admin, so cannot change the organization ruleset. Main already has the required protection types; the missing condition is Collegium's proof that the App cannot bypass them. The user's own never-bypass result does not prove the App's.

Prepared the exact red/green fixture, requirements and disabled config/service-test.json against the existing dispatcher CI. No target writes or new model calls occurred. reports/github-app-live-test.json records the actual refusal; docs/GITHUB-APP-LIVE-TEST.md contains the administrator handoff and remaining integration work. An asynchronous question requested administrator action or an already eligible connected service repository; no pilot task was requested.

Important correction: Collegium injects repository tokens through native egress; lap has no installation-token export command. The current environment-token broker is not yet connected to that managed credential lifecycle. A scoped deterministic script-executor broker remains to integrate/verify after write admission; do not claim the App is fully connected to the broker or that only the live test is missing.


## Personal remote bootstrap

The owner corrected the destination to their personal account, serhii-nochevnyi. Created private serhii-nochevnyi/collegium-pipeline (repository ID 1474663859), default main, owner admin access. An attempt under airslate-common was refused before creation and is not the target. A separate project App connection ghc_7de07519a1e3437a95f98edc4545022d is created but has no repository row yet. Collegium's App is not installed on the new repository.

The correct platform App is airslate-agentic-platform, owned by airslate-common; its public GitHub App ID is 4976598. A native code-only read probe proved repository REST 200 but GraphQL 403 with managed egress credentials. The new native broker helper therefore uses repository REST and a Git protocol expected-head lease, never token export or GraphQL. Its scope guards have five local tests. The source baseline now passes 73 tests. Native broker transport wiring and live service PR/CI are still unfinished.

Bootstrapping the new remote's source, CODEOWNERS and CI is authorized by the owner's request to create/use this remote for the service test. Prior bench defaults against remote writes are superseded only for this explicitly named repository and test; no product repository mutation or merge is authorized. Historical profiles/proofs are retained unchanged.
