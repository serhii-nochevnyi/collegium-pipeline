---
phase: epic-live-service
reviewed: 2026-11-28T14:32:15Z
depth: deep
scope: targeted verification of the three items in EPIC-LIVE-SERVICE-REVIEW-2
files_reviewed: 4
files_reviewed_list:
  - src/collegium_pipeline/epic_service.py
  - src/collegium_pipeline/epics.py
  - scripts/epic_service_broker.py
  - tests/test_epic_service.py
findings:
  critical: 1
  warning: 0
  info: 0
  total: 1
  necessity: 0
status: issues_found
---

# Live Epic Service Review – Targeted Resolution Verification

## Summary

All 180 focused offline tests passed. Both ancestry validators reject an unrelated file tree despite a valid ready receipt and matching parents. The dispatcher preserves the verified SHA and refuses a substituted head before any worker submission. The closed-unmerged reproduction also fails safely. The same PR lifecycle gate still authorizes a redrafted PR and allows a closed merged PR to push again after its head is lost from the base.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: The merge guard still permits writes from stale PR lifecycle states

**Severity:** BLOCKER  
**File:** `scripts/epic_service_broker.py:119-155`, `scripts/epic_service_broker.py:181-231`, `tests/test_epic_service.py:378-382`  
**Issue:** The new check refuses a closed unmerged PR. An open PR with `draft=true` still passes with its old approval and may be pushed by the Git merge helper. A previously merged closed PR also passes. If a ref reset removes its accepted head from the current base, `merge_isolated` falls through from the missing ancestry check and creates a new push. Both cases were reproduced through the merge guard. The closed-merged case reached the push in a mocked Git transport.  
**Fix:** Require `open`, `draft=false`, and `merged=false` for any new merge. Treat an already merged PR as observation-only and refuse if its head is no longer contained in the verified service base. Keep the separately authorized probe-close replay idempotent. Add regressions for a redrafted PR and a closed merged PR after the isolated ref loses its head.
