---
phase: epic
reviewed: 2026-11-28T10:06:29Z
depth: deep
files_reviewed: 16
files_reviewed_list:
  - src/collegium_pipeline/capacity.py
  - src/collegium_pipeline/epics.py
  - src/collegium_pipeline/jira_epics.py
  - src/collegium_pipeline/epic_cloud.py
  - src/collegium_pipeline/delivery.py
  - src/collegium_pipeline/store.py
  - src/collegium_pipeline/config.py
  - src/collegium_pipeline/recovery.py
  - scripts/build_bundle.py
  - scripts/bundle_controller.py
  - config/epic-policy.json
  - tests/test_epics.py
  - tests/test_jira_epics.py
  - tests/test_epic_cloud.py
  - tests/test_bundle.py
  - docs/EPICS.md
findings:
  critical: 12
  warning: 2
  info: 0
  total: 14
  necessity: 0
status: issues_found
---

# Epic Code Review Report

## Summary

The review traced admission and checkpoint replay through the installed entry, native worker polling, the ticket engine, and the GitHub broker. Offline reproductions confirmed stale prerequisite dispatch through both entry paths, early CI failure, stranded integration capacity, paused queue blockage, and regression of an accepted epic under capacity contention. Repository and platform mutations were outside the review.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: A dependent can launch from a base that lacks its prerequisites

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:299-358`, `src/collegium_pipeline/epics.py:367-392`, `src/collegium_pipeline/delivery.py:357-391`  
**Issue:** The round-robin loop uses persisted `merged` proofs before refreshing prerequisites later in the same tick. A capacity-blocked C can retain proofs from a prior tick, run first once capacity frees, and launch on a base that was reset to before A/B merged. The later ancestry error cannot undo C's dispatch. The final integration path also chooses its own base after checking each merge against independent ref observations. A ref change between those reads can select an integrated head that lacks a previously checked merge.  
**Fix:** Verify all required merge commits against one explicit base SHA before acquisition and dispatch. Pass that SHA to Delivery and reject drift before initializing or publishing the child. Bind final integration to the same head whose ancestry was checked for every child. Test with a real rotating cursor, a freed claim, and a simulated ref reset.

#### CR-02: A normal pending integrated check permanently blocks the epic

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:444-452`, `src/collegium_pipeline/ci.py:53-59`  
**Issue:** `inspect_ci` returns `waiting` when a required check is absent or in progress. Integration compares against `pending` and writes terminal `blocked`. The scheduler never observes a subsequent green result for that SHA. This was reproduced with an in-progress base check.  
**Fix:** Map `waiting` to `waiting_integration_ci` and test that the same integration head reaches acceptance once its checks pass.

#### CR-03: Epic checks bypass exact-head CI normalization and coverage

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:252-265`, `src/collegium_pipeline/epics.py:430-436`, `src/collegium_pipeline/broker.py:74-88`  
**Issue:** Epic checks send raw commit status rows to `inspect_ci`, which requires a `sha` on each matching legacy row. The existing `GithubApp.pr_evidence` binds rows to the requested SHA because that endpoint supplies per-commit status rows without a `sha` field. The epic also uses the default check-run filter and a single page, bypassing the existing `filter=all` collector. Valid legacy checks can fail and larger check sets cannot be validated using the existing policy.  
**Fix:** Share exact-commit check/status collection with Delivery. Normalize statuses to the scoped commit and paginate all check runs before classification. Test an accepted legacy status and multiple check runs under a required name.

#### CR-04: Epic attempts can write the recovery store under a foreign controller identity

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epic_cloud.py:92-109`, `src/collegium_pipeline/recovery.py:219-225`, `src/collegium_pipeline/recovery.py:544-547`  
**Issue:** Epic validates that the event belongs to an actual current attempt but never compares its automation ID with `recovery_store.owner`. With the same package and project key in another automation, that automation can fence against its own history and issue checkpoints to the pinned owner's store. If the store initially has no head, its first checkpoint can succeed. Recovery later refuses that same checkpoint as belonging to another controller. The standalone CLI already checks the owner before attaching write-ahead persistence.  
**Fix:** Require the configured owner to equal `identity["automation_id"]` before fencing, recovery, or checkpoint calls. Add an otherwise valid alternate-automation test and assert zero effects.

#### CR-05: Recovery selects the invocation profile instead of each effect's admitted profile

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epic_cloud.py:97-109`, `src/collegium_pipeline/epic_cloud.py:126-138`, `scripts/bundle_controller.py:196-250`, `scripts/bundle_controller.py:1180-1190`, `src/collegium_pipeline/recovery.py:539-543`, `src/collegium_pipeline/recovery.py:673-696`  
**Issue:** Epic admissions pin enabled execution settings, but epic pause/resume passes actual disabled settings to `reconcile_existing`. Any pending epic worker causes a frozen-config rejection, so the operator cannot pause an active epic after using the kill switches. Even when enabled, `reconcile_existing` treats every pending row in the shared journal as if it used the caller's digest. A normal pending standalone run and an epic run therefore block one another. A lost standalone checkpoint followed by an epic event has the same mismatch at restore. The fixed `recovery-reads-v1` scratch identity additionally becomes bound to the first recovery config digest and rejects later calls from the other profile.  
**Fix:** Resolve authenticated frozen profiles by digest for checkpoint origin and relevant unresolved operations. Keep observation-only reconciliation separate from write authorization. Scope scratch reads to the selected profile and exercise recovery in both singleton-to-epic and epic-to-singleton order, including paused and disabled operation.

#### CR-06: Terminal states can strand a repository-wide claim after work finishes

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:295-296`, `src/collegium_pipeline/epics.py:316-321`, `src/collegium_pipeline/epics.py:362-366`, `src/collegium_pipeline/epics.py:387-391`, `src/collegium_pipeline/capacity.py:146-162`, `src/collegium_pipeline/recovery.py:339-347`  
**Issue:** A base advance during an integrated validator turn marks the epic terminal and tries to release its `repository:*` claim. Release correctly refuses while the worker row has a pending intent. Subsequent terminal ticks skip the worker, including a definitively completed validator awaiting collection. `reconcile_workers` skips confirmed launches and never settles that row. Blocked ticket rows have a similar gap when a confirmed native job was pending at the point of failure. The reproduced integration case held its active claim permanently, excluding the entire repository.  
**Fix:** Add a drain path that observes confirmed in-flight identities without starting new work, journals definitive outcomes without accepting stale evidence, and releases claims after all effects settle. Keep ambiguous effects claimed and expose an actionable reconciliation state.

#### CR-07: Paused integration waiters can hold the shared queue indefinitely

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:201-214`, `src/collegium_pipeline/epics.py:367-369`, `src/collegium_pipeline/capacity.py:138-142`  
**Issue:** Pause returns waiting child claims to `dormant` but leaves a waiting integration root queued. When the active ticket releases capacity, the root takes priority in FIFO. A paused tick cannot run that waiting integration, so newer tickets are refused indefinitely. This was reproduced with a competing ticket and a paused epic whose children were all merged.  
**Fix:** Pause the waiting root and children atomically with the epic document. Preserve active claims for draining and requeue dormant claims on authorized resume.

#### CR-08: Integration can knowingly exceed the total epic admission budget

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:301-346`, `src/collegium_pipeline/epics.py:393-418`, `src/collegium_pipeline/delivery.py:254-276`  
**Issue:** The child's last native turn can exceed its reserved token allowance. The scheduler computes actual accumulated ticket usage, but passes none of it to `integrate`, which checks only tokens spent by integration against its reserve. Once finalized ticket usage consumes the epic's total ceiling, the first validation or review can still be newly admitted. The already observed overrun is knowable before the additional paid dispatch.  
**Fix:** Before creating a new integration job, require headroom under both the integration reserve and total budget after actual child usage. Allow observation of jobs already admitted. Cover overrun of the last child and the last integration stage separately.

#### CR-09: Standalone delivery can launch a waiting epic child

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/capacity.py:97-114`, `src/collegium_pipeline/delivery.py:317-331`, `tests/test_epics.py:160-180`  
**Issue:** `activate` checks the epic owner when it queues a child, but `acquire` accepts a waiting or active claim from any caller with its run ID. Matching-profile standalone Delivery can advance an epic child after the first scheduler attempt queued it. That caller bypasses epic prerequisite and token decisions. The dormant-only test misses this. An offline run reproduced standalone dispatch of the waiting C after resetting the base beneath both prerequisites.  
**Fix:** Require the owning epic when an epic-managed claim is acquired or stepped. A standalone attach should report the existing run without advancing it, or route through its owning scheduler.

#### CR-10: The installed entry permits execution outside the verified runtime archive

**Severity:** BLOCKER  
**File:** `scripts/bundle_controller.py:12-17`, `scripts/bundle_controller.py:41-45`, `scripts/bundle_controller.py:1108-1115`, `scripts/build_bundle.py:122-143`  
**Issue:** A generated entry with a nonempty hash returns to fallback if `runtime.b64` is missing. `main` also inserts `root/src` ahead of the verified ZIP, so the unpacked source mirrors win when the generated bundle is run from its full source tree. In either case, a generated entry can execute bytes the hash never authenticated.  
**Fix:** Permit the unbundled import path only when the entry has an empty source-mode pin. Require the archive in packed mode and import from the verified ZIP without registering source mirrors. Test missing archive and a conflicting `root/src` package alongside a valid ZIP.

#### CR-11: Explicit manifests can admit aliases for the same Jira issue

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:16-23`, `src/collegium_pipeline/epics.py:52-73`, `src/collegium_pipeline/jira_epics.py:94-109`, `src/collegium_pipeline/store.py:107-119`  
**Issue:** Canonical admission and graph deduplication compare the raw `source_id`. An exported Jira task accepts an issue key or noncanonical numeric strings such as `"123 "` as the source ID. A later export or Jira import of that same issue with `"123"` admits another run. The default explicit-export mode has no live Jira revalidation to catch the alias.  
**Fix:** Validate canonical Jira immutable issue IDs at manifest intake and use the same canonicalization in the Jira adapter and canonical admission. Keep display keys as labels. Test canonical ID, ID aliases, and issue keys supplied in the ID field.

#### CR-12: Replaying accepted evidence can downgrade readiness on unrelated contention

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:295-296`, `src/collegium_pipeline/epics.py:367-386`, `src/collegium_pipeline/epics.py:428-453`  
**Issue:** A ready epic releases its integration claim. A later tick tries to reacquire the repository-wide claim before checking existing evidence. An unrelated active ticket makes the scheduler replace `ready_for_acceptance` with `waiting_integration_capacity` despite unchanged head and quality evidence. This was reproduced after completing the full fixture.  
**Fix:** Revalidate existing readiness through an observation-only path that does not enter the work queue. Persist invalidation when evidence is actually stale or failing. Cover replay while a standalone delivery owns capacity.

### Warnings

#### WR-01: Rejected or externally changed PRs appear to await a merge indefinitely

**Severity:** WARNING  
**File:** `src/collegium_pipeline/epics.py:233-251`, `src/collegium_pipeline/epics.py:322-325`  
**Issue:** Any unmerged PR returns before its identity is checked. A closed unmerged PR or a pushed replacement head leaves a ready child at `awaiting_merge`, and the scheduler stops calling Delivery for that child. Dependents stay pending without an actionable change-of-head or rejected-PR reason.  
**Fix:** Validate PR identity throughout merge polling and report a closed unmerged or externally modified PR as blocked, preserving the original accepted revision for evidence.

#### WR-02: Tick output reports model launches during observation-only ticks

**Severity:** WARNING  
**File:** `src/collegium_pipeline/epic_cloud.py:146-155`  
**Issue:** Every tick reports `agent_started=true`, including all-paused ticks, CI polls, and replay of a completed epic. Operators cannot use it to distinguish paid dispatch from observation.  
**Fix:** Derive dispatch evidence from confirmed launch events for the current invocation and report unknown effects separately when a launch is ambiguous.
