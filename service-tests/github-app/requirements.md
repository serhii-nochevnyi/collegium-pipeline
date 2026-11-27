# Service-only GitHub App / PR / CI repair test

This is an explicitly authorized conveyor diagnostic, not a product pilot or a Jira ticket. Do not merge it, tag it, deploy anything or change production code, workflows, rulesets, secrets or repository access.

Use airslate-common/agents-knowledge, repository ID 1345007429, base main at a pinned SHA. Only change bundles/ak-team/dispatcher/test_collegium_pipeline_service.py. The existing dispatcher CI detects that path and runs its own locked uv lint/format/pytest; the gate check reports the suite outcome. Do not add or alter a workflow or create synthetic success statuses.

During the initial implementation, return exactly this file:

```python
"""Temporary PR-only CI fault injection for the Collegium delivery conveyor."""

EXPECTED = "green"
ACTUAL = "red"


def test_collegium_pipeline_service():
    """The initial PR fails; the fixer changes only ACTUAL to green."""
    assert ACTUAL == EXPECTED
```

The initial deliberate assertion failure is the approved fault injection. Planning, independent review and pre-publication validation must recognize this initial phase explicitly: compilation and formatting must pass, but the new assertion is expected to fail in CI. Do not fix it before recording actual red GitHub Actions evidence.

Once the controller supplies real red CI feedback, the fixer changes only ACTUAL = "red" to ACTUAL = "green". Preserve EXPECTED, the assertion and the test name. Repeat pinned validation and independent review for the repaired exact commit, then observe real gate and dispatcher / test checks for that head until both succeed. No missing/skipped/pending check is success.

Acceptance evidence must include the same PR number before/after repair, App author identity, pinned base and both head SHAs, real failed/passed check IDs, distinct producer/reviewer sessions, actual runtime effort proof, unchanged scope and no merge. A failure before token issuance is not a successful service test.
