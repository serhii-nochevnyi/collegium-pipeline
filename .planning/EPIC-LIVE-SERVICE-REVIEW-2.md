---
phase: epic-live-service
reviewed: 2026-11-28T14:26:36Z
depth: deep
scope: targeted verification of the live service review fixes
files_reviewed: 8
files_reviewed_list:
  - src/collegium_pipeline/epic_service.py
  - src/collegium_pipeline/epics.py
  - src/collegium_pipeline/native_broker.py
  - src/collegium_pipeline/config.py
  - scripts/epic_service_broker.py
  - scripts/native_github_broker.py
  - scripts/build_bundle.py
  - tests/test_epic_service.py
findings:
  critical: 3
  warning: 0
  info: 0
  total: 3
  necessity: 0
status: issues_found
---

# Live Epic Service Review – Fix Verification

## Summary

All 134 focused offline tests passed. The signed ordinary-write guard, fixed leased merge destination, and actual turn-overlap observation resolve CR-01, CR-02, and WR-01 from the first review. Missing and forged ready receipts now fail. A stable wrong initial seed also fails. Three additional offline cases reproduced remaining failures in the ready-PR and baseline gates from CR-03 and CR-04.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: An approval for a source head can bless an unrelated integration tree

**Severity:** BLOCKER  
**File:** `scripts/epic_service_broker.py:55-79`, `scripts/epic_service_broker.py:175-202`, `src/collegium_pipeline/epic_service.py:108-144`  
**Issue:** A ready receipt signs the accepted PR head. It does not attest the merge result. The receipt is emitted in controller output and recorded in the Git commit message. Both baseline walkers accept a commit based on this receipt and the two parent SHAs, without verifying its resulting tree or a broker-issued merge attestation. An external writer to the isolated ref can reuse the receipt in a commit with the expected parents and unrelated content, and the next service tick can treat that content as its authorized base. Both real validators accepted a mocked commit with the original receipt, exact parents, and an unverified tree.  
**Fix:** Bind the exact merge result to independent broker evidence. For example, sign a separate merge attestation over the suite, graph and task identity, old tip, accepted source SHA, and resulting tree SHA, then require it in both walkers. Cover receipt reuse with a different tree and a legitimate two-parent merge.

#### CR-02: A ref change can substitute an unchecked base between proof and dispatch

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epic_service.py:108-144`, `src/collegium_pipeline/epic_service.py:351-371`, `src/collegium_pipeline/epics.py:376-392`, `src/collegium_pipeline/epics.py:517-520`  
**Issue:** The service verifies the isolated ref in `baseline`, then runs reconciliation and writes a checkpoint. `Epics.step` independently reads the ref and uses that different observation as the first root base. The verified SHA is unused by the scheduler. An offline run verified the proper seed, changed the ref, and submitted both A/B planning turns on the unverified SHA. The child guard compared against the scheduler's new snapshot and allowed the submissions.  
**Fix:** Return the exact verified service tip and require the scheduler to use it. Reject a mismatch before pinning the epic base or dispatching jobs. Repeat the same check for later ticks so the authorized ancestry proof always applies to the selected revision.

#### CR-03: A previously approved PR can still be merged after it is closed without merge

**Severity:** BLOCKER  
**File:** `scripts/epic_service_broker.py:104-148`, `scripts/epic_service_broker.py:151-202`, `src/collegium_pipeline/epic_service.py:71-104`  
**Issue:** The manual merge guard checks receipt, PR identity, head, fixture, and CI. It ignores current PR state and draft status. A PR closed unmerged after readiness still satisfies the guard with its earlier receipt. Since the mutation is now a direct Git push, normal closed-PR merge refusal does not protect the isolated branch. The offline fixture reproduced acceptance with `state=closed` and `merged=false`.  
**Fix:** Require a currently open, non-draft PR for any new merge. Keep replay of an already merged head observation-only and verify it against the attested integration history. Test closed, redrafted, and already-merged PRs separately.
