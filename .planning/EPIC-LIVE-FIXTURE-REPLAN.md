# Explicit service fixture revision2

The first live graph proved A/B running overlap and cancelled-controller recovery:
root2bdb1491-88ca-4b82-8c95-e01e64d98759, same2session/turn IDs after restore,
C queued and no commits/PRs. Both original planners are now terminal completed.

An avoidable diagnostic fixture bug was then found: literal fixture1 did not pass Ruff
format/import checks. Do not waive CI or rewrite admitted acceptance. Preserve the exact
v18 service settings in config/epic-service-v1-settings.json (intended config digest
1e63c46daddfa892845eecdc0d35fcfb5b0226c43ce03799c23dd1d7a29572ca).

Revision2 fixtures pass actual Ruff check+format. New text source IDs contain :v2:;
old graph stays immutable. Explicit mode retire uses the archived profile to observe/drain
only existing confirmed terminal turns, charge rejected usage, and release old claims only
when no pending intent remains. The original graph becomes blocked/paused with an explicit
fixture_retired marker. New work refuses while that marker is absent. Unknown launches
retain ownership. No automatic replacement of unknown old workers.

The trusted installed recovery registry contains both frozen configurations. The same
independent recovery store retains signed history and can restore either profile; only the
new fixed graph can dispatch. Service broker current policy is revision2, with same3paths,
sameisolatedbase, sameprivatekeygrant; original broker code/history remains versioned.
No GitHub commits/PRs existed for revision1, and base still equals pinned sourceed79.
The existing normal/production profiles and models/effort remain unchanged.

Tests: actual Ruff on3corrected fixtures, changed source identities/graph digest without
altering legacy acceptance, uncertain retirement retains intent/claim, terminal retirement
releases claims. Prior native/bundle/recovery tests retained. No replan means acceptance
silently changed; this explicit new graph is required before continuing live verification.

Resolution verification: both findings in EPIC-LIVE-REPLAN-REVIEW.md are fixed. The retire-mode writer uses the archived profile for its signed checkpoint, and fresh journals check sqlite_master before querying epics. A real HMAC WriteAhead/DiskStore regression retires the old pending worker, preserves both roots, then admits revision2 without another native POST. All281 local tests and bundle validation pass. Installed v19 source d9b79283836cde665bc548365ec3792ade7c909a; native recovery reproduced same2session/turn IDs after a second deliberate cancellation. Full A/B-to-C completion remains under live observation.
