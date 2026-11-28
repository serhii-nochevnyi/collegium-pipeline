---
phase: epic
reviewed: 2026-11-28T10:59:33Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - src/collegium_pipeline/epics.py
  - src/collegium_pipeline/capacity.py
  - src/collegium_pipeline/delivery.py
  - src/collegium_pipeline/delivery_workers.py
  - src/collegium_pipeline/broker.py
  - src/collegium_pipeline/store.py
  - src/collegium_pipeline/epic_cloud.py
  - src/collegium_pipeline/recovery.py
  - src/collegium_pipeline/platform.py
  - docs/EPICS.md
  - tests/test_epics.py
  - tests/test_epic_recovery_profiles.py
findings:
  critical: 4
  warning: 0
  info: 0
  total: 4
  necessity: 0
status: issues_found
---

# Epic Code Review Report – Third Pass

## Summary

The 182 focused offline tests passed. The seven previously reported scenarios now have passing regressions. Four additional scenarios reproduced failures in the boundary between an admitted intent and an actual dispatch, accepted usage accounting, integration admission under contention, and replay after a readiness write.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: Resuming a proven unstarted intent bypasses the known epic token ceiling

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:297-316`, `src/collegium_pipeline/epics.py:497-509`, `src/collegium_pipeline/delivery_workers.py:259-273`, `src/collegium_pipeline/platform.py:187-242`  
**Issue:** The budget check treats any pending intent as collection of an existing worker. A failed session checkpoint can leave a pending intent with authoritative `effect_not_started` evidence. Recovery correctly makes it resumable, but `resume_dispatch` can create the first session and prompt for that intent. Reproduced with independent A/B/C: C's session checkpoint refused before any session creation, recovery restored C to planning, B's completed turn put actual usage over the epic ceiling, and the same tick then created C's first paid turn.  
**Fix:** Distinguish a confirmed launch that can be observed from a recoverable intent whose next operation can start a paid turn. Enforce the aggregate admission gate before any potentially first prompt submission, including the existing-session resume path. Preserve unresolved intent and claim ownership when observation cannot establish its disposition.

#### CR-02: Accepted paid turns can consume zero tokens when usage is absent

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/delivery_workers.py:63-86`, `src/collegium_pipeline/delivery_workers.py:388-404`, `src/collegium_pipeline/delivery.py:263-286`, `src/collegium_pipeline/epics.py:251-262`  
**Issue:** Conservative handling of missing counters applies to discarded turns only. A valid paid result with a `session.status_idle` event lacking `usage` reaches `worker_completed` with `observed_tokens=0`. The next paid stage can proceed from an understated budget. This was reproduced in the planning fixture with its original accepted result and the usage field removed. The accepted path also counts arbitrary `*tokens` fields while the discard path recognizes the authoritative counters.  
**Fix:** Use one authoritative counter parser for all paid observations. Require complete verified usage before granting more headroom, or record the conservative reservation or known lower bound when settling an incomplete observation. Keep accepted and discarded usage idempotent.

#### CR-03: A base fast-forward while waiting for integration capacity permanently blocks an unstarted epic

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:380-390`, `src/collegium_pipeline/epics.py:539-557`, `docs/EPICS.md:17-22`  
**Issue:** Integration stores `integration_head` before acquiring its work claim. If a standalone delivery holds the repo, the epic waits without creating any native job. A normal fast-forward before capacity frees then reaches the permanent integration drift block. Reproduced with all child merges still reachable and zero integration attempts. The earlier SHA had no validator, review, or reservation that needed to remain pinned.  
**Fix:** Pin the integration SHA when authorized work can start, after capacity acquisition and a final ref check. Preserve that pin once a native effect might have begun. While merely queued, reevaluate eligibility against the current verified head.

#### CR-04: A cut after saving child readiness can reject the original valid merge on replay

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/delivery.py:356-362`, `src/collegium_pipeline/epics.py:393-421`  
**Issue:** Delivery saves `ready_for_acceptance` before changing the claim from `active` to `awaiting_merge`. A cut between those writes leaves an accepted delivery with an active claim. If the owner merges its exact accepted PR before the next tick, the new active-ticket drift branch overwrites readiness with terminal `blocked` because the merge advanced base. That branch runs before merged PR verification. Reproduced by interrupting `hold_ready`, verifying the ready document was durable, and merging the original PR.  
**Fix:** Recover readiness from the durable delivery document before treating an active claim as proof of in-progress work. Verify the PR on its accepted head and transition the claim appropriately. Persist the readiness and claim transition atomically where possible. Add a regression for the exact write boundary and subsequent human merge.
