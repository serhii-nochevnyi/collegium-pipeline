---
phase: epic-live-fixture-replan
reviewed: 2026-11-28T15:01:57Z
depth: quick
files_reviewed: 8
files_reviewed_list:
  - src/collegium_pipeline/epic_service.py
  - src/collegium_pipeline/config.py
  - src/collegium_pipeline/recovery.py
  - src/collegium_pipeline/delivery_workers.py
  - scripts/build_bundle.py
  - scripts/bundle_controller.py
  - tests/test_epic_service.py
  - config/epic-service-v1-settings.json
findings:
  critical: 2
  warning: 0
  info: 0
  total: 2
status: issues_found
---

# Live Epic Fixture Replan Review

## Summary

All 75 focused offline tests passed under the repository's existing virtual environment, including the actual Ruff checks on the corrected fixtures. The archived intended configuration reproduces the recorded v1 digest. Two additional offline cases found failures at the live retirement checkpoint and the first admission against an empty journal.

## Narrative Findings (AI reviewer)

### Critical issues

#### CR-01: Retirement saves a local marker and then fails its signed checkpoint

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epic_service.py:360-372`, `src/collegium_pipeline/epic_service.py:456-473`, `src/collegium_pipeline/recovery.py:250-274`  
**Issue:** The controller binds `WriteAhead.save` to the revision 2 config. The retirement function writes a checkpoint for the revision 1 root. `WriteAhead.save` checks the operation's root against its own configuration without a profile registry for that write. The registry supplied to its constructor only resolves prior head adoption. The actual `retire` route reproduced `CheckpointError` with the real signed store handler. The local graph already contained `fixture_retired=true`, but there was no signed retirement checkpoint and the mode failed. Existing retirement tests call the function without installing a checkpoint callback.  
**Fix:** Bind the retirement writer to the archived profile and keep the trusted registry for prior head recovery. Ensure the resulting snapshot identifies the same archived root and can be restored by revision 2. Add an end-to-end offline test of the `retire` route with real `WriteAhead` persistence, the terminal worker case, and subsequent revision 2 admission.

#### CR-02: First revision 2 admission queries the epic schema before initialization

**Severity:** BLOCKER  
**File:** `src/collegium_pipeline/epic_service.py:318-327`, `src/collegium_pipeline/epic_service.py:475-489`, `src/collegium_pipeline/epics.py:120-133`  
**Issue:** With an archive present, the new admission path calls `legacy_roots` before constructing `Epics`, which creates the `epics` table. A genuinely empty service journal fails with `no such table: epics` even though it has no legacy work to retire. The offline reproduction opened a standard fresh `Journal` and invoked the deployed lookup.  
**Fix:** Initialize the epic schema before checking archived roots or make `legacy_roots` return no admissions when its table is absent. Keep signed lost-snapshot recovery ahead of that check. Cover first revision 2 admission with an archive and empty state.
