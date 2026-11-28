---
phase: epic
reviewed: 2026-11-28T10:30:52Z
depth: deep
files_reviewed: 21
files_reviewed_list:
  - src/collegium_pipeline/capacity.py
  - src/collegium_pipeline/epics.py
  - src/collegium_pipeline/jira_epics.py
  - src/collegium_pipeline/epic_cloud.py
  - src/collegium_pipeline/delivery.py
  - src/collegium_pipeline/delivery_workers.py
  - src/collegium_pipeline/broker.py
  - src/collegium_pipeline/domain.py
  - src/collegium_pipeline/adapters.py
  - src/collegium_pipeline/store.py
  - src/collegium_pipeline/config.py
  - src/collegium_pipeline/recovery.py
  - scripts/build_bundle.py
  - scripts/bundle_controller.py
  - config/epic-policy.json
  - tests/test_epics.py
  - tests/test_jira_epics.py
  - tests/test_epic_cloud.py
  - tests/test_epic_recovery_profiles.py
  - tests/test_bundle.py
  - docs/EPICS.md
findings:
  critical: 7
  warning: 0
  info: 0
  total: 7
  necessity: 0
status: issues_found
---

# Epic Code Review Report – Second Pass

## Summary

The 77 focused offline tests passed. Separate offline reproductions confirmed seven remaining defects in claim cleanup, terminal integration, budget accounting, emergency pause, and ancestry verification. The recovery fix notes were available. The requested `.planning/EPIC-RUNTIME-FIX.md` was absent, so the runtime changes were reviewed directly in the entry and its packaging tests.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: An ineligible dependency waiter can block all newer admissions

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:392-419`, `src/collegium_pipeline/capacity.py:118-146`  
**Issue:** A ticket activates its claim before attempting acquisition. If it waits for capacity and a prerequisite then becomes invalid, the next tick marks it `blocked_dependency` without clearing its `waiting` claim. Capacity policy sees the obsolete waiter as the oldest eligible row and refuses later requests. The exact reset scenario covered by `tests/test_epics.py:500-522` leaves C's claim queued. Repeating it and then admitting a newer standalone run reproduced the global admission block. A waiting ticket whose reservation is exhausted follows the same pattern.  
**Fix:** Remove waiting claims from the eligible queue when dependency, budget, or pause state prevents their execution. Release terminal blocked claims and use a dormant state for eligibility that can recover. Preserve ownership for actual active or ambiguous work.

#### CR-02: Losing a prerequisite during final validation strands the integrator

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:333-338`, `src/collegium_pipeline/epics.py:345-370`, `src/collegium_pipeline/epics.py:440-464`  
**Issue:** Integration drift drains only inside `integrate`, and that method is skipped whenever a child loses its merge proof. A force-reset after the integrated validator starts marks the child proofs blocked and leaves the epic in `blocked_children`. Future ticks bypass both integration and the terminal settlement branch. The reproduced validator was already definitively completed, yet the epic's repository-wide claim remained active on every tick. A waiting integration claim can likewise survive when eligibility is lost.  
**Fix:** Handle loss of integration eligibility before gating on all proofs. Clear stale readiness, remove a waiting claim, or transition active integration to terminal settlement without accepting the stale result. Test both a normal base advance and a reset that removes the original merges.

#### CR-03: Rejected integrated worker evidence never enters settlement

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:495-518`, `src/collegium_pipeline/delivery_workers.py:168-182`, `src/collegium_pipeline/delivery_workers.py:287-300`  
**Issue:** Integrated `jobs.step` exceptions escape before the epic records a terminal state or releases its claim. A completed validator that omitted its required checkout was marked failed by `NativeJobs`, which raised `CheckoutProtocolError`. Every subsequent tick hit the same recorded rejection and failed again. The claim remained active even though `Capacity.unresolved(root)` was already false.  
**Fix:** Handle definitive protocol rejection as a blocked integration with a recorded reason and settled ownership. Retain an observation-only drain for unresolved failures and preserve retries for transient remote errors. Test a failed validator checkout and a rejected reviewer response.

#### CR-04: Confirmed pre-effect broker refusals keep claims as though a write were uncertain

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/broker.py:173-186`, `src/collegium_pipeline/store.py:54-71`, `src/collegium_pipeline/recovery.py:794-801`, `src/collegium_pipeline/capacity.py:149-165`, `src/collegium_pipeline/epics.py:436-438`  
**Issue:** A failed checkpoint before a broker mutation records `effect_not_started` for the exact operation. Epic delivery blocks the ticket and tries to release its claim. Capacity counts every `broker_intent` without `broker_done` as unresolved, including this proven no-op. Recovery reports the no-op without settling that intent. With a subsequent healthy checkpoint hook, the reproduced ticket still held its claim indefinitely and the blocked state prevented a normal operation retry.  
**Fix:** Persist an explicit, identity-bound broker disposition for definitively unstarted operations and allow terminal capacity release from that disposition. Keep unknown external outcomes claimed. Exercise checkpoint refusal, preflight refusal, and an actual lost mutation response separately.

#### CR-05: A paid rejected checkout escapes both ticket and epic token accounting

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/delivery_workers.py:274-300`, `src/collegium_pipeline/delivery_workers.py:362-423`, `src/collegium_pipeline/delivery.py:254-276`, `src/collegium_pipeline/delivery.py:463-492`, `src/collegium_pipeline/epics.py:238-246`  
**Issue:** Checkout rejection records an observation artifact and clears the child intent without forwarding its observed usage. Delivery retries without updating its tokens. Drain only reads pending children, so it never charges that completed rejection. In the offline fixture a rejected planning turn reported usage above the entire epic ceiling. The journal charged zero and continued launching new turns. Drain also considers an idle event with no usable usage data verified and charges zero.  
**Fix:** Make definitive rejected-turn accounting idempotent and share it between protocol retries and drain. Charge actual authoritative usage even when evidence is rejected, and charge the conservative fallback when there is no usable usage payload. Check aggregate headroom before the next dispatch.

#### CR-06: Emergency pause depends on unrelated launch reconciliation succeeding

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epic_cloud.py:188-209`, `src/collegium_pipeline/recovery.py:761-802`  
**Issue:** A `pause` on an adopted journal runs full `reconcile_existing` before setting the pause flag. That scans all pending work and can raise for an absent or ambiguous session or broker object in the same epic or another run. The new disabled-pause test supplies a `launched` event, so recovery immediately skips the uncertain path. An unconfirmed intent reproduced refusal while both kill switches were disabled, and the epic stayed unpaused.  
**Fix:** For a fenced, adopted journal, persist and checkpoint the pause without requiring outstanding observations to succeed. Keep pending intents and active claims intact. Continue requiring recovery when the journal itself needs to be restored. Verify pause with a genuine unconfirmed launch in both the same and a separate run.

#### CR-07: A finite ancestry walk reports a reachable merge as permanently missing

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epics.py:308-320`, `src/collegium_pipeline/epics.py:351-367`  
**Issue:** The ancestry walk stops after 256 visited commits and gives the same permanent rejection as an exhausted graph with no matching ancestor. The new refresh turns that exception into `blocked` and excludes those nodes from later proof collection. A linear fast-forward of 256 commits above previously verified merges reproduced terminal blockage even though every merge was still reachable. This can occur on a busy repository during a valid epic or recovery delay.  
**Fix:** Query ancestry for both pinned SHAs with complete GitHub evidence, or distinguish a bounded incomplete search from proven non-reachability and support continuation. Keep the immutable head binding and test a reachable ancestor beyond the old limit.
