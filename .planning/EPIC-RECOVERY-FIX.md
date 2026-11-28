# Epic recovery review fixes

| Finding | Applied fix |
| --- | --- |
| CR-04 | Require the attempt automation ID to match the pinned recovery owner before fencing, checkpoint access, or admission. Refusals record a local no-dispatch receipt. Status and preflight avoid controller state writes. |
| CR-05 | Build the recovery profile registry from installed singleton and epic settings and their intended-enabled variants. Verify checkpoint origin and journal admission digests against the registry and the pinned controller, repository, and broker scope. Resolve pending worker and broker operations by their own admitted profiles. Key scratch read admissions by profile digest. |
| WR-02 | Derive launch receipts from journal events recorded after reconciliation in the current invocation. Confirmed launches drive `agent_started`. Outstanding session or prompt effects are listed separately, including when a tick fails after an effect attempt. |

## Verification

Ruff formatting and lint checks passed in the shared checkout. Forty-two focused offline tests passed, including eight new cases for mixed-profile observations, cross-profile snapshot recovery, unknown or foreign profiles, disabled pause and resume, and launch evidence. The report and source changes are uncommitted for integration by the parent workflow.
