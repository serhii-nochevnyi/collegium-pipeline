# Local serial controller

Six real Collegium workers are bound to a serial Python coordinator. The five-stage native readiness loop is verified. The product delivery driver/PR broker and CI repair loop are now implemented; their write/CI paths have fixture evidence only. Choosing the pilot task is explicitly deferred. See [delivery commands and limits](DELIVERY.md).

## Commands

Requirements: Python 3.12+, uv, curl, authenticated lap and gh. Versions are locked in uv.lock.

```sh
make check
make doctor-readiness
make doctor
make self-test
uv run --locked collegium-pipeline explain-route executor --critical
python3 scripts/check_codex_mcp.py collegium
python3 scripts/check_codex_mcp.py collegium-help
```

Doctor is read-only: no agents or paid model probes. The readiness profile currently passes all six checks, including current worker digests and the native report. The separate delivery profile remains disabled. Exit 0 means ready for the selected profile, 2 means incomplete, and 1 means a configuration/command error.

`make self-test` uses the stable task ID controller-readiness-live-v1 and resumes the existing completed run without starting additional sessions. A new task ID starts paid native work. Readiness is synthetic and read-only toward the connected repository; it never creates a product PR, Jira issue or successful delivery receipt.

```sh
uv run --locked collegium-pipeline self-test \
  --run-id d93b0a8a-0084-48ec-b43f-6c3c1a5dadf4
uv run --locked collegium-pipeline self-test --run-id RUN_ID --once
uv run --locked python scripts/publish_readiness.py \
  --run-id d93b0a8a-0084-48ec-b43f-6c3c1a5dadf4
```

The first command resumes; --once performs a bounded controller tick. Publication re-verifies existing native observations without calling a model. The report is reports/readiness.json; the private journal and immutable artifacts remain under .local.

To provision or calibrate roles explicitly (these actions may create agents or paid sessions):

```sh
uv run --locked python scripts/provision_workers.py \
  --config config/readiness.json --readiness --version 2
uv run --locked python scripts/calibrate_worker.py --help
```

Provisioning checks existing pinned configurations rather than silently mutating workers. Calibration journals its session and turn; resume observes that same turn. Do not run it again merely to reproduce already-published proof.

## Runtime evidence and quality gates

The native loop executes planning, independent plan review, implementation, seven fixed sandbox validation cases and independent code review. Content-addressed artifacts bind acceptance criteria, producer hashes, role/session identity and configuration. Reviews use different sessions from producers. The terminal state is self_test_passed with delivered false.

Before accepting a stage, the coordinator checks the actual platform session/turn, trace correlation and matching tool events. A pinned first tool reads the Codex process arguments and returns only PID, harness, model and model_reasoning_effort. The verifier compares actual model/effort against the role policy and pinned agent config. Worker final JSON alone cannot prove selection. The unchanged shell/heredoc frame and Python AST must match the pinned probe; formatting-only Python changes are accepted.

This proves client launch configuration, not provider-internal reasoning or a signed attestation. Sol/low, Sol/high and Luna/medium are verified in native sessions. Fixer and sentinel have separate calibration receipts; readiness does not claim that production repair or CI babysitting has been exercised.

## Recovery and bounds

Dispatch intent is durable before session creation. The session is recorded before prompt submission, which uses the intent as Idempotency-Key. Ambiguous writes quarantine the run as reconciling; resume never launches an unobserved replacement. Timeout/interrupt aborts are checked and uncertain cancellation also quarantines.

`recheck-result --config config/readiness.json --journal .local/controller.sqlite3 --run-id ID --reason TEXT` explicitly re-observes a completed rejected result after a verifier correction. It records the reason and cannot repair an ambiguous launch or start a replacement worker. It was used once for AST-equivalent probe formatting.

Attempt/time limits and a remote worker runtime limit are active. Token budgets apply before admission; the final admitted turn can overshoot. Gateway prices are uncounted, so configured USD limits are not enforced. Do not interpret zero listed spend as zero cost.

## Delivery commands and remaining integration

Text admission creates no ticket and launches no worker:

```sh
uv run --locked collegium-pipeline prepare-text \
  --config config/pilot.json --journal .local/runs.sqlite3 \
  --title 'An explicitly selected change' --requirements-file /absolute/path/task.md
uv run --locked collegium-pipeline verify-pr --config config/pilot.json --number NUMBER
```

PR verification reads actual current head/base and required checks, refetches to detect concurrent updates, and explicitly does not evaluate independent review or advance a run. Use the separate `deliver --live` command described in [delivery](DELIVERY.md) for the resumable product driver.

Actual Contributor session creation is blocked until main has the required active, non-bypassable protections: PRs, one approving review, code-owner review, stale dismissal or last-push approval, no deletion and no force push. Readiness workers therefore have read-only grants; no protection was changed.

The broker and bounded repair driver are implemented; workers remain read-only and the broker holds separate installation authority. A separate native read-only private checkout diagnostic passed. Remaining native evidence includes actual broker writes and a selected product change through independent review and real CI. PostgreSQL with transactional action/claim coordination is required before cloud/multi-worker operation. Epic scheduling and investigation remain later slices. See [verification](../.planning/VERIFICATION.md).
