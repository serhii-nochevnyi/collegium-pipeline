# Claude workers on the owner's subscription

The active worker profile is Claude Code on Aranarium, explicitly using the existing project connection `project/claude-code-subscription` (`mcn_699c8e51528e4438a359acfd4dced40f`). Its token stays in managed egress. No key is copied to an agent, the repository, a packet or a report. Gateway and Codex substitution is rejected before session creation.

| Role | Subscription alias | Effort |
| --- | --- | --- |
| Planner and independent plan/code reviewers | opus | high |
| Executor and initial fixer | sonnet | low |
| Repeated same-cause fixer | sonnet | high |
| Exhausted repeat fixer | opus | max |
| Sentinel calibration | sonnet | medium |

Eight immutable version-1 agent bindings are in `config/claude-service.json`. All eight were calibrated in real fresh sessions. Actual served models were `claude-opus-5-5` and `claude-sonnet-5-5`; runtime release was `claude-code-2.1.289-9162edd4`. Evidence is in `reports/claude-workers.json`, with session/turn identities and content-addressed observations. `reports/claude-checkout.json` separately proves a native Claude worker's exact private-repository checkout. Neither report proves PR delivery.

The first pinned Bash diagnostic prints only the harness process's PID, model and effort arguments. The controller matches tool identity, command AST and shell frame, the correlated turn trace and completed native result. It then checks served-model telemetry and an explicit effort-support table, rejecting unknown resolutions or a different model family. This verifies launch configuration and model support; provider-internal reasoning cannot be measured this way. Claude's Bash content/is_error protocol is verified directly; a Codex-style exit code is never invented.

The workers have read-only grants to `serhii-nochevnyi/collegium-pipeline`. The separate pinned script broker uses the GitHub App's Contributor grant. Local `gh` is explicitly selected for repository/check/log reads in this service profile; every branch, commit and PR mutation still uses native App authority without a person-token fallback. The native broker remains manual-only and paused.

The service profile enforces exact initial and repaired fixture digests. The initial PR must fail on the authorized assertion in a verified GitHub Actions job at its exact head. Only then can a fixer run. The repaired head needs fresh actual unittest validation, independent review and green CI on the same PR. Initial green, unrelated failures and local pre-CI failures cannot satisfy this diagnostic. It never merges, releases or deploys.

Previous Codex profiles and receipts remain historical. Run `fdc168a6-97a3-48ee-b5dc-bd243854100c` was marked blocked/superseded after the owner's model-policy change; all its native turns had already completed and no GitHub writes had occurred. A fresh admission is used for the Claude service test.

## Reproduce

```sh
uv run python scripts/provision_workers.py --config config/claude-service.json --broker-workers --version 1
uv run python scripts/publish_calibrations.py
uv run collegium-pipeline deliver --config config/claude-service.json \
  --journal .local/claude-service.sqlite3 --artifacts .local/claude-service-artifacts \
  --run-id 281c201a-b129-4a5d-96f8-6a03f1db5286 --live
```

The last command resumes the recorded admission; it does not create a new one. Never change its pinned config to bypass a deadline, budget or reconciliation failure. Provisioning checks existing agents instead of silently repinning drift. Calibration receipts bind to the separate calibration config, so changing service gates does not rewrite their evidence.

Subscription telemetry includes list-price estimates, which are not an invoice or the owner's subscription charge. The current token ceiling is an admission limit, not a hard provider cap. A final admitted turn may exceed it. The USD ceiling is not enforced.

Sources: [Collegium model connections](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/model-connections.md), [Aranarium Claude adapter](https://github.com/airslate-common/aranarium/blob/main/internal/adapter/claudecode/claudecode.go), [Claude model and effort configuration](https://code.claude.com/docs/en/model-config), [GitHub Actions job/log API](https://docs.github.com/en/rest/actions/workflow-jobs).
