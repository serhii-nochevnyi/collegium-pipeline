# Epic delivery slice — 2026-11-28

Route: Shipyard bench, ticketless continuation; no pilot/Jira writes or merge authority.
Research: existing Delivery/NativeJobs is asynchronous; one fenced dispatcher can advance
several tickets without threads or shared mutable checkouts. Existing SQLite canonical
identity and signed independent checkpoint are reused. Context7 quota is exhausted;
Collegium's live help and primary platform source specify script MCP stubs and plan/apply.

Implementation decisions:
1. Immutable epic/v1 DAG with normalized Jira task identities, prerequisite validation,
   cycles/empty/unknown references refused. Direct-to-base strategy only: dependents wait
   for independently verified prerequisite merges contained in current base. Never treat
   a green open PR as available dependency code. No automatic merge or Jira Done.
2. Transactional canonical admission and shared ticket/resource capacity across epic and
   standalone Delivery. Explicit path/resource declarations permit concurrency; unknown
   overlap serializes. Each native ticket retains its own branch, sessions and quality
   pipeline. Uncertain launches/actions retain claims; no expiring lease can replace them.
3. Deterministic round-robin ticks start independent native jobs asynchronously. Per-epic,
   project and repository caps, shared fairness, token reservations, pause/drain/resume,
   failed descendants, immutable acceptance/config and checkpoints survive restart.
4. After all children merge, fresh integrated validation, independent review and actual
   exact-base CI are still required. Ready means awaiting owner acceptance, not delivered.
5. Jira intake via the pinned read-only script MCP stub supports pagination and explicit
   site/type/link mappings; missing site configuration fails without selecting a pilot.
   Explicit exported manifests also work. A separate disabled epic settings profile keeps
   historical single-service config digests unchanged.
6. Deterministic compressed Python runtime in the bundle with checked archive hash and
   bounded zipimport; retain readable source mirrors/index. This removes the676byte
   packaging ceiling without removing quality gates. All automations remain paused.

Verify: A/B active at once, C waits for real merged prerequisites; shared paths/resources
serialize, singleton/epic duplicate conflict attaches or refuses, crashed/pending actions
retain ownership, failed A blocks C while B proceeds, pause/resume and replay stable,
changed graph/source/head/config blocks, combined-quality failures cannot finish epic,
isolated packaged runtime and real platform bundle validator. No real epic/pilot run.
Review source changes, publish into existing source PR through the App, show installation
plan, apply only the scoped bundle update, and audit disabled flags/paused configuration.

Completion evidence — 2026-11-28:
- 248 local/remote CI tests PASS; independent targeted final review PASS, all blockers resolved.
- Reviewed source fe91ffbcc9d894e58eb4c186977a5cd186a25e6d published through a new paused,
  exact-58-path GitHub App source helper; existing source PR1, no merge or pilot.
- Exact plan20a6c233...26c5383c applied; installed controller v16, five code files/170547bytes.
- Live v16 readonly epic Atlassian preflight and control-key/eight-worker/six-MCP checks PASS.
- All10 automations paused; both execution profiles disabled. Main, private Claude bindings,
  historical service profile and narrow service broker/store pins unchanged.
- Actual epic paid concurrency remains untested live. Jira mapping and approved working
  scopes remain deferred; inherited service-file scope does not enable arbitrary writes.
See reports/EPIC-DELIVERY.md and reports/epic-verification.json.
