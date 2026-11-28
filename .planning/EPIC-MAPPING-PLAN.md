# Epic Jira mapping and working scope — 2026-11-28

Route: ticketless Shipyard bench, current dirty checkout, no local commits/branches,
no pilot selection or Jira writes. Existing authorized App source publication and paused
bundle installation continue after verification.

Research: live Atlassian metadata identified pdffiller.atlassian.net cloud
3e1c0d80-f6e4-4767-ad1c-f06c182b0f93; shared company-managed Epic10000;
Blockers10000 inward=is blocked by, Depends10400 outward=depends on. Team-managed
project-specific Epic IDs are distinct and fail explicitly until separately mapped.
No actual issue or epic was fetched/selected. Context7 quota unavailable; use official
Collegium help and live operation schemas as the reference.

Implement:
1. Configure cloud/type and both directed dependency links; normalize MCP data envelopes.
2. Separate pinned paused working broker, same repository/App, allow only
   src/collegium_pipeline/, tests/, docs/, README.md, pyproject.toml, uv.lock.
   No .github/config/scripts or secret paths. Keep historical service profile/broker pins.
3. Package/claim working broker and disabled epic profile. Frozen recovery may use each
   explicitly installed profile's own path/broker scope while keeping owner/repo/App fixed.
   Profile mismatch never becomes re-admission or mutation authority.
4. Preflight verifies exact accessible cloud and separate pinned broker scope without
   admitting issues, model sessions or GitHub writes. All automations stay paused.

Verify directed link parsing, unknown epic types, malformed wrappers/scope changes,
shared-capacity behavior with real configured paths, cross-profile readonly recovery,
bundle deterministic pin/membership and unchanged service history. Review diff inline,
run targeted tests; source CI runs full suite. Publish through existing App helper where
within its fixed scope; add separate exact-path helper only if new source paths require it.
Show scoped installation plan before apply; audit live readonly preflight, bindings and
paused state. No epic import/tick, PR pilot, merge or external write test.
