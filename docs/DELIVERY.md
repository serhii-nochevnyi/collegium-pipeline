# PR brokerage and bounded CI repair

Implemented 2026-11-27 in the local serial coordinator. The API adapters and recovery path are covered by stateful transport fixtures. No product task, target branch, commit or PR was created during development. This is not native GitHub-write/CI acceptance evidence.

## Delivery lifecycle

`deliver` consumes a previously admitted text task and resumes a persistent delivery document in the same SQLite journal:

```text
planning → independent plan review → implementation
    → publish candidate on run branch → pinned remote validation
    → independent code review → open PR → observe actual CI
                                          ↓ failure
                                   make PR draft → fixer
                                          ↓
                          publish → validate → review → mark ready → CI
                                          ↓ green
                              ready_for_acceptance
```

Only the coordinator writes to GitHub. All native workers have exactly one read-only repository grant. Executors/fixers return complete UTF-8 file changes; binary, executable, symlink and submodule changes are deliberately unsupported. Allowed paths, validation argv commands and required check names are explicit configuration, fixed before task admission.

Candidates are published to the run branch before validation so each validator/reviewer checks out the actual immutable Git commit. The first PR is opened only after validation and independent code review. Repairs turn the existing PR into a draft before publishing another candidate; each candidate invalidates the prior validation/review. After repair validation/review, the PR becomes ready for review again so CI workflows can run; repository workflows must support the ready_for_review event if they skip draft PRs. Passing CI on that exact head, passing review, unchanged base and known mergeability are required before ready_for_acceptance. There is no merge/release/deploy operation. delivered remains false because acceptance/merge belongs to the owner.

Plan-review findings trigger bounded replanning. Validation/code-review failures and red CI trigger bounded repair. Planning/execution failures that cannot produce an acceptable candidate stop the run. Missing/pending CI waits until a deadline; skipped, cancelled, stale or approval-dependent checks block without inventing a code fix. Distinct Apps with identical check names are evaluated separately; only the latest attempt per App/context counts. The adapter fetches all check runs and pages through checks/statuses, including failure annotations, then refetches the PR to detect revision changes during collection.

The fixer starts at Sol/low. Repeated failure signatures escalate to high, then xhigh. CI signatures include check/App/conclusion and normalized diagnostic text, so a changed diagnostic resets escalation. This is a bounded diagnostic heuristic, not a claim to determine root cause perfectly. Separate immutable variants are required: no silent effort fallback. Sentinel remains Luna/medium; CI polling itself is deterministic and makes no model call.

## Durable effects and recovery

Each branch, candidate commit, PR and draft/ready change has a stable action identity. Intent is journaled before writing. A lost response is resolved by observing the same branch/commit/PR; a pending action with no observable effect is never blindly repeated. The PR carries the run marker and must match the branch, repository ID, base and head. Existing unrelated branches are not adopted.

Commit publication uses GitHub GraphQL createCommitOnBranch with expectedHeadOid. This is an atomic head precondition; REST force=false alone is insufficient. Reconciliation verifies the parent and action marker, then checks the complete recursive tree against the admitted file changes, including unchanged paths. An unexpected push blocks rather than overwrites it. No force push, default-branch write or auto-merge is implemented.

The native adapter journals child jobs, sessions and turns. A resumed job observes its original turn. It verifies actual runtime model/effort through the pinned process-argument probe and authentic platform events, compares the admitted prompt, and requires the exact second checkout/validation tool command. Validation exit codes come from the matching tool result. Worker JSON cannot self-attest model, effort or successful tests.

The CLI holds a nonblocking journal file lock for the whole run. This is single-host serial coordination; do not run multiple hosts against SQLite or call the driver concurrently outside this lock. PostgreSQL fencing/outbox remains a separate production prerequisite.

## Configuration and commands

[delivery.example.json](../config/delivery.example.json) is intentionally disabled. Its eight version-3 role bindings are provisioned and their live configuration digests checked: six base roles plus fixer:high and fixer:xhigh. Provisioning itself made no model call; the separate checkout diagnostic made one. Native effort proofs from the previous readiness run apply to its separate version-2 bindings. A new version-3 planner diagnostic also passed its actual runtime probe and private-repository clone/checkout at the pinned SHA; high/xhigh repair turns still need native validation. See [checkout receipt](../reports/delivery-checkout.json).

Before admission, choose repository-appropriate allowed_paths, validation_commands, required_checks and budgets. The example src/tests paths and Python command are placeholders, not assertions about agents-knowledge. Changing these after admission requires a new task identity/replan. Keep the example disabled; use a reviewed operational configuration for eventual execution.

The broker requires a short-lived GitHub App installation token in COLLEGIUM_GITHUB_APP_TOKEN. The actual token must resolve through /installation/repositories to exactly the configured immutable repository; a PAT, personal gh session or token with multiple repository grants is refused. It needs Contents write and Pull requests write; checks/annotations need read access. The token stays in the transport header, never CLI arguments, worker packets or artifacts. Automatic mint/refresh from the Collegium connection is not implemented; the existing lap person key is not a GitHub token. No key needs to be pasted into chat.

```sh
make check
make test-delivery
make doctor-delivery
uv run --locked python scripts/provision_workers.py \
  --config config/delivery.example.json --broker-workers --version 3
# Explicit paid read-only service diagnostic; resumes its recorded turn:
uv run --locked python scripts/check_delivery_checkout.py --run
```

Provisioning reconciles versioned workers and does not call a model. The current delivery doctor confirms eight worker digests and reports the missing installation credential plus disabled execution. Installation-level Contributor checks still pass even though the earlier actual Contributor session failed its protected-main policy; do not treat that check as token issuance or permission to bypass platform policy. The broker credential/eligibility and repository rules must be validated before any live write.

Commands for a later explicitly chosen task, shown for reference only:

```sh
uv run --locked collegium-pipeline prepare-text \
  --config /absolute/path/operational-config.json --journal .local/delivery.sqlite3 \
  --task-id EXPLICIT_ID --title 'Selected task' --requirements-file /absolute/path/requirements.md
uv run --locked collegium-pipeline deliver --live \
  --config /absolute/path/operational-config.json --journal .local/delivery.sqlite3 \
  --run-id RUN_ID
```

`--once` performs one bounded tick. Restart with the same config/journal/artifacts/run ID. A pending external write can need later observation or explicit operator reconciliation; a new run is not an automatic replacement for an uncertain write. Unknown native launches/cancellation are quarantined. status includes the separate delivery document; the parent admission row is retained by the original journal.

Repair attempts, worker jobs, token admission, per-stage, CI and overall deadlines are bounded. CLI timeout/interrupt requests cancellation and retains unresolved child identities. USD accounting remains unavailable, so max_cost_usd is not an enforced dollar ceiling. The final admitted turn may exceed the token admission threshold.

## Verification and limits

The local suite has 68 tests, including 29 delivery/broker tests. Fixtures exercise the complete native-adapter/state-machine path from planning through a red check, repair, validation, independent review, green CI and ready-for-acceptance; effort mismatch, failed validation, repeat escalation, changed diagnostics, review/replan failures, limits, cancellation, duplicate prevention, lost commit/PR responses, exact-tree verification and external revision changes are also checked.

Read-only live GraphQL introspection confirmed CreateCommitOnBranchInput.expectedHeadOid, CommittableBranch, FileChanges and the draft/ready mutations. Relevant official contracts: [PR endpoints](https://docs.github.com/en/rest/pulls/pulls), [check runs](https://docs.github.com/en/rest/checks/runs), [Git references](https://docs.github.com/en/rest/git/refs), [GraphQL reference](https://docs.github.com/en/graphql/reference).

Not yet verified natively: a real broker credential/write, product validation/review, high/xhigh fixer turns and real red-to-green GitHub CI. No distributed scheduler, automatic rebase, token refresh, external reviewer conversation handling or cloud deployment is claimed. Those limits remain visible; selecting a pilot task is still deferred by the owner.
