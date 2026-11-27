# Implementation plan

Status: planned sequence, not exported Jira issues. Slice 0 connections and Slice 1's native worker/controller readiness loop are verified: six role bindings, actual Codex model/effort proofs, five native stages, seven sandbox checks and 39 local tests. The serial product delivery driver, PR brokerage and bounded CI repair are implemented and fixture-tested. Native product delivery to PR, production coordination and later slices remain unfinished. See [verification](../.planning/VERIFICATION.md). Current implementation is ticketless and the product pilot is deliberately deferred. Every slice needs appropriate checks; no production release is claimed from readiness.

## Slice 0 — Platform readiness and contracts

Install `lap` and its Codex skill; authenticate; select the actual Collegium space/project and pilot Jira/GitHub scope. Configure the platform MCP and documentation access. Discover runtime, model connection, actual model IDs, effort support, environment packages and connector permissions. Inspect API/tool schemas for launch, observation, cancellation, correlation and script identity. Determine whether immutable agent versions and actual selection evidence are accessible.

Produce `doctor` as a read-only command with redacted machine-readable results. It must perform no model probe without an explicit paid-probe option. Confirm database/artifact hosting and a network policy through the supported console workflow. Resolve deploy-blocking unknowns in PLATFORM-EVIDENCE.md before constructing a live bundle.

Acceptance: A19; verified prerequisite matrix; no remote agents/automations created as a side effect of discovery.

## Slice 1 — Single-ticket vertical slice, PR-only

Implement normalized Jira/GitHub/Collegium adapters, configuration validation, PostgreSQL run/attempt/action tables, artifact envelopes and a deterministic ticket state machine. Add immutable role prompts and variant selection. Admit one manually selected Jira ticket; run planning, independent plan review, implementation, local checks, independent code review and PR creation/observation. Stop at `pr_ready` for human acceptance. Export actual evidence and project Jira status through discovered transitions.

Use one isolated pilot repository with meaningful CI. Do not enable merge authority in this slice. First verify with fake adapters, then read-only real adapter contracts, then one explicitly scoped real ticket.

Acceptance: A01, A08, A10, A11, A16, A17; confirmed actual model/effort evidence or explicit strict-mode blocking.

## Slice 2 — Durable recovery and action brokerage

Implement transactional admission, outbox/inbox, resource claims, fencing, heartbeats and launch/action reconciliation. Add pause/drain, cancel and bounded retry/repair. Restrict worker write permissions; route final external actions through the coordinator. The restart path must recover pending effects before launching replacements.

Test crash windows around database commit, launch request, lost response, branch/PR creation, merge acknowledgment and Jira transition. Exercise real PostgreSQL concurrency, not only an in-memory fake. Verify provider-specific conditional merge/update behavior and the quarantine path for unresolved operations.

Acceptance: A04, A06, A07, A09, A14, A15, A18. This slice precedes real parallel execution.

## Slice 3 — Epic DAG and parallel delivery

Implement versioned graph validation, ready-node selection, resource conflict rules, fair shared admission for epic and single-ticket requests, per-scope concurrency limits and integration serialization. Add integration branches, dependent-ticket base selection and epic-level acceptance. Show partial completion and blocked descendants.

Integration must revalidate the actual current head/base. Test at least a three-node graph with independent A/B and dependent C, overlapping resources, competing coordinators and a failed child. Only enable configured ticket-to-epic merges after supported conditional operations and protected-branch behavior pass their checks. Keep the final epic PR under human merge authority initially.

Acceptance: A02, A03, A05, A13, A20 plus Slice 2's recovery checks under parallel execution.

## Slice 4 — Investigation and Jira decomposition

Implement intake, bounded research perspectives, sourced synthesis, proposed ADR and authenticated decision checkpoint. Decompose accepted decisions into a validated graph with acceptance/check mapping. Export Jira tickets through stable action identities; replay must reconcile instead of duplicating them. Support graph revision and impact analysis for active epics.

Acceptance: A12, A03, A17 and export crash/replay scenarios from A06/A18.

## Slice 5 — Policy, quality integrations and operations

Complete complexity explanations, role-specific escalation, budgets, audit UI/report, configured external reviewers, waiver records and emergency stop. Add repository-specific quality profiles and operational metrics. Version the Collegium bundle and test plan/apply/update behavior in the pilot project with automations initially paused.

Acceptance: all A01–A20, actual end-to-end pilot evidence, restore/reconciliation drill and reviewed install/update plan. Configuration and manual/native checks that remain unverified must stay visible.

## Suggested implementation layout

```text
src/collegium_pipeline/
  domain/          # state machines, DAG, model and quality policy
  coordinator/     # admission, reconciliation, outbox, integration
  adapters/        # Jira, GitHub, Collegium, PostgreSQL, artifacts
  cli/             # commands and doctor
agents/            # prompts and immutable role variants
bundle/            # Collegium manifest and dispatcher, after schema verification
schemas/           # config and result contracts
tests/             # policy, PostgreSQL concurrency, adapter contracts, crash scenarios
```

Use Python as the proposed coordinator language and avoid choosing an SDK/framework until Slice 0 confirms the runtime image and API contracts. Packaging and dependencies must be pinned. Do not embed personal platform credentials in the bundle or use a personal provisioning key as an unexamined production service identity.
