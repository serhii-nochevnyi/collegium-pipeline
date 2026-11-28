# Authorized service-only conveyor test

Repository: serhii-nochevnyi/collegium-pipeline. This is an explicitly authorized infrastructure diagnostic, NOT a product pilot or Jira ticket. Never merge, tag, release, deploy, alter permissions, edit workflow/config files or create another PR.

Only change tests/test_live_service.py. The existing quality GitHub Actions job runs make check, including unittest discovery, on every PR and push. No workflow or other source changes are allowed. Ignore the historical agents-knowledge examples for task scope.

## Initial implementation and review phase

During the implementing stage create the EXACT file shown below, with ACTUAL equal to red. This intentional failure is explicitly REQUIRED to test CI detection. Do not fix it before an actual red CI observation is supplied by the coordinator. The initial planner, plan reviewer and code reviewer MUST judge the red assertion as the authorized fault injection, not an accidental product bug. Initial configured validation is compilation only and must pass; the test itself is EXPECTED to fail at this initial stage. Return verdict pass when this exact approved initial-phase file is supplied and compiles. Do not add another test or alter the expected value/assertion to make the first PR green.

```python
"""Temporary PR-only fault injection for the Collegium delivery conveyor."""

import unittest

EXPECTED = "green"
ACTUAL = "red"


class LiveServiceTests(unittest.TestCase):
    def test_service_phase(self):
        self.assertEqual(ACTUAL, EXPECTED)
```

## Repair phase (only when the coordinator supplies real red CI feedback)

During the fixing stage change ONLY ACTUAL = "red" to ACTUAL = "green" in the same file. Preserve EXPECTED, the test name, class, assertion and every other line. Return the full repaired file in payload.changes. The validator and independent code reviewer should now accept only the corrected green variant. Do not skip, delete, xfail, weaken or replace the assertion; do not edit workflows or other tests.

## Evidence and stopping rule

The coordinator must observe an actual quality failure on the initial PR head, call an actual fixer session, validate and independently review the repaired commit, then observe quality success at the repaired head of the SAME open, non-draft PR. No fabricated CI status, fixture-only adapter result or local compilation is a green CI outcome. A product pilot remains unselected. Leave the verified PR unmerged for inspection.
