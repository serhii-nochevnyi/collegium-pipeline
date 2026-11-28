---
phase: epic-live-service
reviewed: 2026-11-28T14:15:43Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - src/collegium_pipeline/epic_service.py
  - scripts/epic_service_broker.py
  - scripts/bundle_controller.py
  - src/collegium_pipeline/recovery.py
  - src/collegium_pipeline/delivery_workers.py
  - src/collegium_pipeline/config.py
  - scripts/build_bundle.py
  - tests/test_epic_service.py
  - config/epic-service.json
  - scripts/native_github_broker.py
findings:
  critical: 4
  warning: 1
  info: 0
  total: 5
  necessity: 0
status: issues_found
---

# Live Epic Service Code Review

## Summary

The 103 focused offline tests passed. Additional fixture checks confirmed that the service broker delegates a direct commit to its integration branch and accepts a merge without an admitted PR receipt or matching baseline. The review found four blockers in the new diagnostic's merge and baseline controls, plus one warning about measuring overlap.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: Ordinary broker writes bypass the isolated merge gate and can target other runs

**Severity:** BLOCKER  
**File:** `scripts/epic_service_broker.py:84-91`, `scripts/native_github_broker.py:96-110`, `scripts/native_github_broker.py:227-252`, `scripts/native_github_broker.py:286-296`  
**Issue:** The service wrapper checks that a commit contains one literal fixture and delegates branch policy to the ordinary broker. The latter accepts any UUID-shaped `collegium/` branch. The integration branch uses that shape, so a caller can commit directly to the integration branch and bypass the manual merge, accepted revision, and CI gates. Existing ordinary or other service task branches are in the same accepted namespace. An offline fixture passed a direct integration-branch commit through both guards.  
**Fix:** Reserve the integration base from ordinary mutations and bind branch creation, commit, and PR operations to admitted task-branch identities for this suite. Enforce the recipient branch at the broker boundary. Cover the base branch and a foreign task branch in the write-routing tests.

#### CR-02: The merge request does not bind the target branch that was authorized

**Severity:** BLOCKER  
**File:** `scripts/epic_service_broker.py:26-54`, `scripts/epic_service_broker.py:66-81`, `scripts/epic_service_broker.py:99-105`  
**Issue:** The script reads the PR's base and main ref, collects files and CI, then sends a merge request containing only the expected head SHA. The head precondition survives a PR retarget. A concurrent retarget to `main` between the proof reads and PUT can therefore make GitHub merge into `main`, which the diagnostic explicitly excludes. A second read would narrow the window without binding the actual write.  
**Fix:** Use a mutation that is constrained to the pinned isolated ref with an atomic expected-base condition, or enforce App-level denial of writes to `main` independently of the PR object. Verify that PR retarget drift cannot redirect an approved mutation to another branch.

#### CR-03: Manual merge authorization accepts unadmitted PRs with a matching fixture

**Severity:** BLOCKER  
**File:** `scripts/epic_service_broker.py:43-81`, `src/collegium_pipeline/epic_service.py:76-125`  
**Issue:** The helper consumes a caller-selected PR number and head. Its provenance check is a UUID-like branch name and an HTML marker in the editable PR body. No check joins the PR, branch, fixture key or head to the admitted service graph, a ticket's ready receipt, or its native validation and independent review. A matching fixture and a green `quality` check can therefore satisfy the gate for an unrelated PR even though the service coordinator never accepted that revision. The test boundary currently accepts a synthetic PR with no coordinator evidence.  
**Fix:** Bind each allowed service merge to the coordinator's durable ready evidence, including the suite, fixture key, managed ticket, PR node, validated and reviewed head, and expected base. An explicit manual approve step can pin those identities before broker execution. Test rejection of a matching but unadmitted PR.

#### CR-04: The service starts on any commit found under the isolated branch name

**Severity:** BLOCKER  
**File:** `scripts/build_bundle.py:198-208`, `scripts/build_bundle.py:388-392`, `src/collegium_pipeline/epic_service.py:167-180`, `src/collegium_pipeline/epic_service.py:211-231`, `scripts/epic_service_broker.py:13-25`  
**Issue:** The plan fixes the seed SHA. The builder copies `baseline` into the merge policy, but neither the controller nor the helper reads that field. The controller accepts the first branch head observed by Epics and can launch workers from unrelated preexisting code. The merge helper also accepts arbitrary base SHA evidence as long as the branch name and current main SHA match. The offline fixture verified that an unrelated base SHA is accepted.  
**Fix:** Carry the fixed seed into the service admission profile and verify the isolated branch against it before the first dispatch. On later service operations, require the current head to be that seed or an authorized fixture integration descendant with the expected receipt. Fail before paid work if the initial branch was advanced or reseeded.

### Warnings

#### WR-01: The crash-ready marker does not establish actual A/B overlap

**Severity:** WARNING  
**File:** `src/collegium_pipeline/epic_service.py:93-117`, `src/collegium_pipeline/epic_service.py:228-240`, `src/collegium_pipeline/delivery_workers.py:157-172`  
**Issue:** The controller prints `CRASH_READY` after seeing two local launch receipts. That confirms two submissions with turn IDs, while a turn can still be queued or the first can finish before the second starts. The checkout hold increases the chance of overlap but does not establish it. Inspection exposes the coordinator launch time and accepted proof rather than the platform turn start and finish times. Consuming the one-shot crash run from that marker could leave the requested parallelism unverified.  
**Fix:** Observe the exact two turns through the platform and require a positive overlap interval, or include their actual timeline in the service output and require the operator to verify overlap before cancellation. Keep crash recovery and overlap as distinct evidence checks.
