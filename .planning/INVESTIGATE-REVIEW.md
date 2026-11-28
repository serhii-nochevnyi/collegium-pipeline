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
