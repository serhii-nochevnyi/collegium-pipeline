# GitHub App live service-test admission

Checked 2026-11-27. The owner explicitly authorized a real service PR and red-to-green CI, while deferring any product pilot. That permission covers the service branch/commits/PR; it does not turn a policy refusal into write access.

## Actual result

The existing project GitHub App connection is present: ghc_73f2cf589000496f88519d531e798f23, with exactly airslate-common/agents-knowledge (repository ID 1345007429) at Contributor. A real `POST /session` for its existing Contributor executor was attempted. Collegium rejected it with HTTP 400, code repository_not_given, before a session ID or model turn existed. The platform cannot establish main protections that the App's write token cannot bypass. See [machine-readable result](../reports/github-app-live-test.json).

This is stronger evidence than a successful connection installation check. It is not a successful write or native CI test. No branch, commit, PR, tag, release, merge or Jira issue was created, and no target permissions/protections were changed.

GitHub metadata confirms the current user has push but not maintain/admin. The active organization ruleset 26681051 already requires PR, one approving review, code-owner review, stale approval dismissal, no deletion and no force push on main. The user's own ruleset response says current_user_can_bypass never; that response describes the user, not the App. Collegium's own attempt still rejects the App. Do not claim that all repository protections are absent or that the App's exact bypass list was readable to us.

## Administrator handoff

The relevant rule is implemented in Collegium's official [rules judgment](https://github.com/airslate-common/litellm-acp-platform/blob/main/services/litellm-acp/src/http/github_app/rules/judged.rs): rules count only when the write token's ruleset response says current_user_can_bypass never. It also requires an active non-bypassable release-tag ruleset covering the connection's v* pattern against creation, updates and deletion. The main rejection is the first observed gate; release-tag admission has not been reached yet.

A repository/organization administrator should inspect the [repository rules](https://github.com/airslate-common/agents-knowledge/settings/rules) and the organization ruleset named agents-knowledge (26681051). Ensure the platform App is not a bypass actor for the required main/tag protections, or provide a dedicated service repository where the existing App already passes the same checks. Preserve the current protection requirements and unrelated actors; do not weaken rules, use a PAT fallback or ask the owner to paste a private key/token into chat.

If the App's token already reports never but Collegium rejects it, the platform administrator should inspect the ruleset lookup/verdict for repository ID 1345007429 rather than changing user access. Viewing App configuration through lap github-connections app info was also explicitly refused: platform admin role is required.

## Prepared service case

The local red fixture is [test_collegium_pipeline_service.py](../service-tests/github-app/test_collegium_pipeline_service.py), and [requirements](../service-tests/github-app/requirements.md) describe both phases and evidence. The test is planned for the temporary PR path bundles/ak-team/dispatcher/test_collegium_pipeline_service.py. Existing ci.yml already routes that directory to the dispatcher reusable workflow; no workflow changes or custom success statuses are needed.

Initial ACTUAL red versus EXPECTED green deliberately fails pytest. The fixer changes only ACTUAL to green. Both local phases were checked: the original assertion fails as expected; the single-constant repair passes. Ruff lint and formatting pass for the fixture. Those checks are preparation only, not native GitHub Actions evidence.

[service-test.json](../config/service-test.json) pins just that path, gate and dispatcher / test, and compilation for initial local validation. The intentional initial failing assertion is explicitly accepted only for this service case; final acceptance still requires both actual GitHub checks to pass on the repaired SHA, independent review and at least one recorded red-to-green repair. Keep this profile disabled until App write admission and the actual broker transport are ready.

## Integration correction still needed

The current local broker accepts an explicitly supplied single-repository installation token. The Collegium App does not expose a supported CLI command to export that token: `github-connections token` replaces a personal-token connection, it does not mint an installation token. Official source and [GitHub help](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/github-connections.md) show repository credentials are injected into the native sandbox by its egress proxy; the sandbox never needs to print their values.

A Collegium-managed broker must therefore run deterministic broker code in a repository-scoped script executor, or use an explicitly provisioned supported broker credential. It must preserve the App's repository eligibility check. That runtime broker integration is not yet complete; we did not label an exported-token environment variable as an installed App connection. The current gate prevents testing the write-enabled executor at all. No alternative account, connector or raw token was used to bypass this refusal.

After eligibility is fixed: recheck admission, complete/verify the broker's supported scoped execution, admit the prepared service task, record the App-authored PR and actual red check IDs, run the fixer/review/validation cycle, verify green checks at the repaired head, and leave the PR unmerged. The product pilot remains unselected.
