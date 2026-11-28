# Investigation review

GSD review performed inline; no delegated review was requested. Scope: the new
read-only investigation policy, native packet adapter, engine, cloud entry point,
provisioning and bundle declarations; shared dispatch/recovery changes reviewed
against existing delivery and epic behavior.

Resolved findings:

- High security/persistence dimensions could have a low total score. Added mandatory
  dimension floors and regressions alongside explicit intake risk floors.
- Agent refresh could repin an unexpected permission/system change. It now verifies
  exact system, read grant, runtime, private connection, role model/effort, installed
  ownership/rule and absence of MCP/subagent/secret/setup grants before repinning.
- Moving test assertions had placed validation-command rejection under an unrelated
  malformed-JSON test. Restored the assertions to the decomposition guard test.

Verified failure paths include stale review, citation forgery, review repair limits,
pending-turn pause/drain, admission limits, rejected paid usage counted once, unknown
prompt outcome and real signed snapshot restoration without repeated session/prompt
creation. Source tests use real temporary Git objects and refuse symlinks, executables,
noncanonical paths and unpinned revisions. Bundle validation passes with 18 agents and
8 automations. Prior delivery, recovery and epic regression suites pass.

Known boundaries are explicit in docs/INVESTIGATE.md: Git-only registered evidence,
per-lane concurrency, proposal-only ADR/tickets, no hard provider spending cap. Runtime
proof and installation results must be recorded separately after native verification.

Live follow-up: the first native synthesis substituted grep checks for the configured
unit-test argv. The controller refused it without publishing/executing anything. Added
bounded synthesis-payload repair with exact controller feedback, immutable rejection
artifacts and retained usage; the same two-repair budget is shared with review failures.
Added regressions for successful correction without repeated research and exhaustion
without review/admission. The blocked v1 service run is retained as negative evidence;
the updated code receives a separate, explicit service replan, never a silent reset.

The explicit v2 service replan revealed a one-character assessment quote typo. Added
bounded per-perspective/assessment payload correction with exact registered-quote
feedback. A manual repair operation handles a previously blocked known terminal payload:
it revalidates it, refuses pending/unknown launches, preserves all existing receipts and
budgets, and launches no agent itself. This permits repairing v1 synthesis while retaining
its four accepted research artifacts. Invalid native JSON/identities remain hard-blocked.
Added tests for quote correction, previous-version repair without repeated research,
unresolved-launch refusal and inability to reset exhausted retry budgets. Reviewed shared
checkpoint admission for the new repair origin; original delivery/epic origins unchanged.

Native verification completed from installed v5: repaired v1 reaches ready_for_decision,
independent Opus/high review passes all 6 exact-artifact checks, all 8 paid turns' usage
reconciles and two terminal replays create no native sessions. All 23 automations remain
paused. Source CI passes 315 tests. See reports/INVESTIGATE.md and machine evidence.
