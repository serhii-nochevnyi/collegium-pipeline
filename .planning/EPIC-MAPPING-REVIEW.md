# Epic mapping/scope review — 2026-11-28

Mode: inline source/diff review, not an independent model review. Ticketless bench scope.

Reviewed config/epic-policy.json, scripts/build_bundle.py, jira_epics.py, config.py,
native_broker.py, recovery.py, epic_cloud.py and their mapping/bundle/native/recovery tests.
Compared runtime edits against installed v16 source. No unresolved blocker in this scope.

- Credentials: existing authenticated Atlassian readonly connection, no added Jira token,
  secret, MCP tool grant or model access. Native App credentials stay at platform egress.
- Mapping: metadata-proven cloud/type/blocker IDs; additional Depends10400 direction is
  outward, and unrelated/reverse links do not become dependencies. External references
  continue to fail graph admission. Team-managed unknown Epic types fail explicitly.
- Response formats: normalize MCP content/data envelopes; malformed/ambiguous/error results
  are refused. Accessible-cloud evidence accepts both metadata envelopes and JSON arrays.
- Paths: working broker has distinct pinned identity and nested scope file. Duplicate scope
  files fail. Exact working ceiling excludes .github/config/scripts/secrets and foreign repos.
  Builder cannot reuse historical service broker or override worker/repository authority.
- Recovery: registry is constructed only from installed settings and intended variants.
  Known profiles may differ in broker/path policy; owner/repository/base/App still must
  match. Original frozen digest resolves each effect, and broker reconciliation is strictly
  observation-only. Unknown or foreign profiles remain rejected; no new admission here.
- Bundle: service settings preserve their historical digest; eight private worker bindings
  and six readonly MCP grants unchanged. New working broker is claimed into the bundle,
  paused, with its frozen code/target pin verified after installation before readonly probe.

Verification: targeted mapping/Jira/bundle/native tests pass; readonly recovery tests pass
with genuinely distinct broker/path profiles. Ruff/compile checks pass. Final platform
bundle validation and source CI are required before applying the reviewed install plan.
No actual issue, epic, model session or GitHub work item selected by these checks.
