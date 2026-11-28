# Epic implementation verified — installation pending

2026-11-28: 248 tests PASS; third-review CR01–04 independently resolved
(.planning/EPIC-REVIEW-3-RESOLVED.md). All earlier findings are regression-tested.
Bundle validates with disabled single-ticket/epic execution profiles, 8 unchanged private
Claude workers, and the existing read-only Atlassian connection granted to the script.
Exact source publication and paused installation are the next operations; no pilot selected.
Installed/CI evidence is recorded separately in reports/EPIC-DELIVERY.md when completed.

Earlier chronological implementation notes follow; their pending-review statements are
superseded by the verified state above.

# Active epic implementation — NOT INSTALLED YET

2026-11-28 continuation: implement dependencies/parallel tickets in Collegium bundle,
all automations paused/no pilot. Source remains installed4489bd9/controller15 remotely;
NO remote writes, source publication or installation performed in this turn yet.
Current code is ticketless Shipyard bench + GSD review/fix, same shared dirty checkout.

New modules capacity.py/epics.py/jira_epics.py/epic_cloud.py, shared Delivery claims,
atomic nested Journal admission, separate disabled epic-settings profile, deterministic
entry-hash-pinned runtime ZIP, read-only Atlassian script grant. Direct_to_base only:
A/B parallel native stages, C after real prerequisite merges contained in one verified
base snapshot; final integrated validation/independent review/exact-SHA CI, no auto merge.
Legacy service profile hash48ff... preserved, all private Claude role bindings unchanged.

Initial deep Codex Sol/high review .planning/EPIC-REVIEW.md found12blockers+2warnings.
Fixes are implemented and regression-tested; RE-REVIEW PENDING, do NOT install before PASS.
GSD fixer workers completed: fix_runtime_identity (CR10/11), fix_profile_recovery(CR4/5/WR2).
Their .planning/EPIC-RUNTIME-FIX.md and EPIC-RECOVERY-FIX.md record changes. Agent
/root/epic_review is idle after initial BLOCKED report; reuse for read-only re-review.
Parent fixes: fresh single-head prerequisites and owner-bound claims, paginated normalized
CI, pending/timeout CI, terminal read-only drain with charged usage, atomic pause ofroot
andchildren, budgets checked after observed overruns, resource-only PR holds until merge,
readiness replay avoids capacity queue. Intended configs resolve via trusted installed
profile registry during mixed-profile checkpoint/unknown-effect reconciliation.

make check226tests/Ruff/compile PASS: .local/epic-fix-final-check.log. Real lap validator
running/last .local/epic-bundle-validate-final.json, observerexec27192. Generated bundle
just rebuilt, source mirrors and packed ZIP match current code. Do not run services/pilots.
Upcoming: re-review -> fixes if needed -> publish SAME sourcePR1 via narrow App helper
with exact changed paths (existingv5 cannot write new files), show plan -> apply -> verify
actual5installed codefiles/archive and real epic preflight only (Atlassian accessible sites,
no issue/agent/admission), all automations paused. Do not create a new product PR/Jira.

SourcePR1 branchcollegium/9d121af5-f676-4e7b-bb38-b5c571af87c3 at4489bd9 currently.
Existing sourcepublisherv5 .local/recovery-publish-v5.json rootaa342... cycle18done,
next19ONLYNEWpayload; v6 transportpublisher has2paths only. Prefer NEW helperv7 exact
changedpaths in one atomic source commit to avoid half-built bundle. New helper must
startpaused/no triggers/secrets/MCP, same native GitHubApp, never widen servicebroker.
Will increase project automation count9->10 if created; finalaudit must reflect actual.

--- Prior completed single-ticket acceptance below ---

# Current verified result — installed cloud CI repair COMPLETE

2026-11-28: reports/cloud-ci-repair-verification.json and reports/CLOUD-CI-REPAIR.md.
Installed source4489bd9f806150c8fb06bb908ba64f444799b9ef, controller15,
23files/255324bytes; planed3399724977e34a827dd1ea4f34bf3a25fbfec508f69092eabeb49050e95e77.
Synced. Source CI46128366513/170tests/lint/compile/realbundlevalidator/nativev8review PASS.

Cloud root6c6d499d-2fee-41fa-be0c-18660001cca2 READY_FOR_ACCEPTANCE/ci_green true,
deliveredfalse, unchanged config48ffb7870672bfbac4a7a16c45d8bf4f570b19a61737334aa9ef57a560a056c3.
PR4: red56a76e13 CI46127307490/job140924650386, green155133d0 CI46127477065/job140925174307.
Same open non-draft/unmerged PR;2commits/1fixturefile; mainunchanged.
Eight native accepted stages; official journal9jobs/9unique sessions includes1definitively
aborted original executor, preserved and bounded retried. Do not claim8launched or nofailures.
Original2accepted planner/reviewer and actual original rootstarted_at1795852195.9203036
preserved through checkpoint/queuedRPC/HTTPbody/timer fixes. All observed models/effort
and exact-head validation/independent review audited; native App owns CI reads/writes.

The final reviewer completed after dispatchdeadline. New explicit manual finalize mode
collects ONLY existing confirmed review/CI; readonlyHTTP/Github wrappers prohibit new
launch/abort/repositorywrites, failedCI/review blocks; normaldeadline unchanged. Cloud
runf79554854a5f4c0e91bfa9366910b45f accepted8stages; replayruna16eeaa411804257bd89493da3a59926
SUCCEEDED same8workers/head/PR/tokens999776, no extra worker/commit/PR. Official cloud
snapshot and SQLite read-only audit verify rootstate/config/time and4finalizationticks.
No local service Delivery engine; host only RunNow/observe, source maintenance and final
read-only audit. Independent native source reviewv8 PASSses58335fb304a0413ea3ab74826516338b.

ALL9projectautomations PAUSED. Installed productionexecution/brokerfalse. No pilot/Jira,
merge/release/deploy. Existing servicePR2/3 and sourcePR1 retained. Sourcepublisherv5cycle18
completed4489bd9; next19ONLYNEWpayload. Narrow sourcepublisherv6 remainspaused2paths.
Only676bytes runtime code.files headroom remains; build refuses overflow. Ticketless
serial service acceptance complete; investigate/epicparallel remain future scope.

--- Historical progress below (superseded by current header) ---

# Current final transport fix before continuing SAME cloud service

Actual installed still059d50a/version12. Third manual cloud run
run_d56473c439b045c8b72015335ef03187 CLOSED/FAILED with precise reason:
Checkpoint acknowledgement unknown(action=chunk,item=None,run=None). Store head and
begin succeeded; no chunk job reached server. Compressed snapshot81857bytes creates
>100KB inline curl config data line; older runtime curl limits such lines. No executor
session/commit/PR created. Same original root6c6d499d.../intent5398.../config48ff...
retained with2 accepted workers/tokens363303; no Task/budget/model/scope rebinding.

Fix JsonHttp writes exact JSON body to private0600 temporary file +data-binary @file,
keeps key headers stdin, removes files on completion. New200KB/unicode/newline regression
verifies body fidelity/private mode/cleanup and short config lines. All162 tests PASS.
Original source publisher v5 did not allow src/transport.py or its preexisting test file.
Created separate PAUSED source publisher v6 aut_c6f07e880ec84a5b89be65fcfdf2ecf0,
EXACTLY TWO paths only: src/collegium_pipeline/transport.py and
tests/test_config_cli_transport.py. No existing publisher/service broker scope widened.
Native private App same repo/contributor/main protections. Now9 automations ALL paused.
Config.local .local/transport-publish-v6.json; source writer root
d5d83926-1c85-4b0a-881b-7576259f14e3 in .local/transport-publish.sqlite3, immutablecycle0
published973748aaa7f9b6c46f3370621bc38ceb7022758e to existing source PR1 branch.
Next v5cycle14 publishes generated matching transport +source index/docs/state only;
then native read-only focused transport review and controller-only install plan.
Keep service frozen config48ff... unchanged! DO NOT install intermediate source before
generated mirror matches. Root started07:49UTC Nov28,3600sec deadline; continue promptly.
No active service cloud run now. Observer history records all failed runs; no pilot.

--- Earlier state below ---

# Current checkpoint for continuation

Source latest059d50a9f4d8c1be6ece4204f25b56acfd1c4efc on existing PR1;
cycles12=e350e8b7 (queued item receipts),13=059d50a (diagnostics outsideSQLite+tests).
Next publisher cycle14 ONLY new content; frozen maps cloud-service-item-fix-changes
and cloud-service-diagnostic-fix-changes. Installed still e13279c/version11.
All161 tests PASS; source CI46124988628 GREEN; real lap validator PASS.
Plan45feac17108a3b963cb2a9427ca14c8ce250cd778db9c7e7f82489fef2ef2023
complete/appliable, SHOWN to user, NOT APPLIED yet. ONLY controller code + installation
bookkeeping. Source config/scopes/model/MCP unchanged. Runtime integrations omit
build-only role_connections/bindings; source fullconfig, manifest and worker/tool scopes
retained. Controller within256000byte cap.

Native focused review v4 PENDING: rootd747666d-bac8-47ea-a149-e4409ab19cd7,
.local/cloud-service-review-v4.sqlite3/-v4-packet.json/-v4-artifacts, observer exec55770.
Review queued item assignment, durable broker_rpc_queued replay, onePOST, MAC verification,
nonpoisoning policy diagnostics. After PASS apply SHOWN45fe...plan, verify exact code
and CFG hash remains48ffb7870672bfbac4a7a16c45d8bf4f570b19a61737334aa9ef57a560a056c3.
Then .local/invoke-cloud-service.py run (ONLY submits/observes RunNow; NO local engine).

Canonical ACTIVE SERVICE ADMISSION6c6d499d-2fee-41fa-be0c-18660001cca2 is paused at
implementing after2 accepted workers, tokens363303. No service commit/PR/executor session
yet; ORIGINAL intent5398da0b-9e1f-4e42-8c58-c96640474d5c is known NOT STARTED from
effect_not_started marker. Two cloud runs failed on checkpoint acknowledgment, both
closed/adopted, no replacement allowed. Retain same task/config/packet/intent.
New queued item API handling should let existing reconcile_existing resume safely.
Task's3600sec deadline began ~07:49UTC Nov28; continue promptly (no new task to evade it).

Observer history .local/cloud-service-remote-runs.json contains1preflight success,
2run failure (run49d943...),3inspect success (run5d093...),4run failure (run9efb...).
No remote run currently active. Latest result partial .local/cloud-service-remote-result.json;
original2 worker identities saved .local/cloud-service-before-recovery.json.
Read-only OFFICIAL state tar export diagnostic saved .local/cloud-service-state-diagnostic;
SQLite read mode=ro only, NEVER used by local Delivery. Headab109...; pendinguploads
uncommitted can be superseded at same committed parent. Complete session list73 proved
no executor session for original intent. Source priorbugfix reviewsv2/v3 PASS preserved.
All8 project automations PAUSED, productionflagsfalse, no pilot/Jira/merge.

After remote ready: repeat inspect AND run to prove same worker/commit/PR identities,
then .local/verify-cloud-service.py read-only host audit; it retains failed run history.
Do not reuse/modify earlier local PR3 or recoveryPR2.

--- Earlier state below ---

# Cloud continuation: queued item/run receipt handling fix pending

Second cloud run run_9efbfa966c244d66b434fc8ca73f927a failed BEFORE first resumed tick,
with safely recorded reason Checkpoint acknowledgement unknown; external effect refused.
Store head run74491... and begin run841db... both eventually SUCCEEDED; no executor
session has been created for original intent5398... (complete73-session read-only list).
Source currently INSTALLED e13279c2edaa2e0dda5df04d19b6fe58d1806ca1/version11, plan
76be3b4dbb2e1c5fdfa851ca2e0b6aa9f9fedafa8326e9772b521b37593751a0 applied.
Config hash48ff... stays FROZEN, all8paused, same service root6c6d499d... retained.

Actual API contract (official source) permits POST /run -> {item:{id,status:queued},run:null}.
Checkpoint client lost the known item and scanned100 unrelated run details sequentially,
exhausting120sec before refreshing the run list; run summaries include item_id.
Fix now tracks exact returned item_id, waits for its run via summaries without scanning
old details, still verifies final run.item_id, HMAC, request_id, owner, namespace/status.
Native App transport now persists broker_rpc_queued receipt and resumes the SAME queued
item after observation failure instead of another POST. Unknown submissions still never
blindly retry. Tests prove100old summaries ignored, onePOST, queued receipt replay after
failed observation, all160 tests PASS. Runtime integration JSON drops only unused
bindings/role_connections catalog fields; full repository config and manifest/agent scope
unchanged. Runtime keeps status/connections/policy/schema. Controller253250bytes.

Next publisher cycle12 for NEW frozen payload, source review then controller-only plan
and install. Do not use old source plans. Original task/worker packet/config/model/effort
unchanged; continue same remote admission from checkpoint, no local controller.
Partial accepted2workers .local/cloud-service-before-recovery.json. Observer history
.local/cloud-service-remote-runs.json preserves failed modes; no active remote run now.
Current final audit script must not require all historical slices succeeded.
No service commit/PR yet, no pilot/Jira/merge; prior PR2/3 remain untouched.

--- Prior state below ---

# Cloud live continuation: interrupted BEFORE executor creation, same root retained

Actual cloud run run_49d943a76e6e477db1d5fa4fd1d29c9d FAILED with PolicyError before
executor session_create. Read-only cloud inspect run_5d093c32023d4d15815c013fc31b239a
SUCCEEDED, same root6c6d499d-2fee-41fa-be0c-18660001cca2 stateimplementing/tokens363303,
2 accepted workers (planner+plan reviewer), no commit/branch/PR/executor session yet.
Latest source still41fa5dd9/version10, all8paused, no pilot.

Read-only OFFICIAL state tar export (no rollback/local controller) saved selected cloud
namespace into .local/cloud-service-state-diagnostic. SQLite opened mode=ro ONLY.
Executor child92b2aad8-4271-4629-9be0-ab0e2014b7da reconciling, original intent
5398da0b-9e1f-4e42-8c58-c96640474d5c; effect_not_started(session_create) proves checkpoint
failed before session POST. KEEP this exact root/intent; never make a replacement.
Local checkpointheadab109...; pendingbdb610... upload begun, not finished. Store begin
run_d4eeac3687924bafb3145cd2a18265d0 eventually succeeded, no chunk/finish for pending.
Diagnostics .local/cloud-service-store-failure-diagnostic.json and executor-runs-diagnostic
show no new executor. New model/effort/scopes or budget were NOT selected.

Found concrete checkpoint RPC defect: queued/waiting treated as terminal failure.
Local fix polls queued/waiting/running until signed terminal response and keeps one RPC;
regression tests added. Safe PolicyError reason now recorded in service journal/stdout
(no raw HTTP error/key), with guard for inspect before admission. Frozen CLOUD config
digest48ffb7870672bfbac4a7a16c45d8bf4f570b19a61737334aa9ef57a560a056c3
explicitly remains unchanged. Task requirements, worker packets, App/store pins unchanged.
Next source publisher cycle11 for this reviewed payload; controller-only install then
manual same mode run. Existing reconcile_existing should adopt the not-started intent;
uncommitted pending upload can be superseded under the same committed parent.
All execution must remain in installed Collegium bundle. Observer helper only RunNow,
no Delivery/NativeJobs service coordination locally. Final read-only audit must retain
failed run history rather than asserting every slice was successful.

--- Historical state below ---

# LIVE CLOUD SERVICE RUN IN PROGRESS — no local service controller

Installed41fa5dd9e67a76c95425d558fb65384ff34ee1d9/version10 via shown/applied
plan74522c286f99153ba7318173a2407668db7043eb607fde2750c9c7087283a01c.
Exact23files/252898bytes;8 worker bindings and new broker/store pins verified;
all8 automations paused, execution/broker globalflagsfalse. Follow-up native
source review PASS ses_017cfd16a83e4b06a1e62f471b1d3690/
run_7d079e88c865463eb74303d28a7f4554, Opus5.5/high/private; receipt
.local/cloud-service-review-v2.json. Source CI46122448479 green.

Actual CLOUD preflight run_4e81ad82cc8f4e51b61d8897777f376f SUCCEEDED:
App read job140757275431 and full log; digest44b2e083311acfed22aa2a995ffa5c68be41e0831ff7a0240f0d778d716b955a
matches original. agent_startedfalse. No host gh fallback.

First actual manual cloud run run_49d943a76e6e477db1d5fa4fd1d29c9d ACTIVE,
canonical NEW service root6c6d499d-2fee-41fa-be0c-18660001cca2, baseDBE5,
last stateplanning. Observer exec64408 runs .local/invoke-cloud-service.py run;
this helper ONLY submits/observes Run now, never imports Delivery/NativeJobs or
executes service decisions locally. Actual installed cloud code runs full engine
for480sec, preserves state/fence and signed service-namespace checkpoints.
History .local/cloud-service-remote-runs.json; full snapshots
.local/cloud-service-remote-002.json; eventual accepted cloud summary
.local/cloud-service-remote-result.json. Do NOT resubmit while a remote run is
queued/running/waiting or outcome uncertain. Poll SAME remote run. After a
SUCCESSFUL bounded slice still in progress, explicitly invoke same manual input
again (same canonical task/branch/PR). All stage decisions stay in Collegium.

After remote ready_for_acceptance, run inspect and repeat run to prove replay
without new workers/commits/PR, then .local/verify-cloud-service.py read-only
postcompletion audit. Root/new PR MUST differ from earlier local PR3; retain
PR2/PR3 and all old frozen admissions untouched. No pilot/Jira/merge.
Source publisher cycles8/9/10 frozen; nextcycle11 only NEW changes.

--- Historical state below ---

# Cloud acceptance follow-up — pending review/installation

Source cycle10=41fa5dd9e67a76c95425d558fb65384ff34ee1d9 (nextcycle11 only for new content),
frozen .local/cloud-service-recovery-fix-changes.json. Source CI46122448479 GREEN.
Plan v2 74522c286f99153ba7318173a2407668db7043eb607fde2750c9c7087283a01c complete/appliable,
NOT APPLIED; oldf424... plan obsolete. Same3 code-only updates + source bookkeeping.
Broker predicted pin now23b418abee71bcbccd04f0b490e2472730085a9f713f1f77607f2501ccf9ca81;
store92c41331... unchanged. Bundle252898bytes,156 tests PASS.

Initial source review session ses_644df37027bb4b7c84257e1c48538b37 completed with two
real blockers AND invalid prose-prefix result. NativeJobs never accepted that result.
Verified actual runtime+pinned checkout, preserved observation and explicitly failed
only that DEFINITIVELY COMPLETED review child with review_protocol_rejected.
Both source findings fixed BEFORE install: outer no-dispatch/fence receipt guard;
reconcile_existing under lock before first step. Regression now actually rejects a run,
commits then drops its reply, resumes through same-engine red/fix/green and inspects
without duplicate agents/commits/PR. Log route made exact jobs/id/logs.
Fresh revision-bound follow-up native review root5581b32c-259f-4816-94ae-0c7850495e9f,
.local/cloud-service-review-v2.sqlite3, -v2-packet.json, -v2-artifacts; exec40839 active.
No new service PR/admission/worker yet. All8 project automations paused, installed source
still27f71f5/version9/prodflagsfalse. After review PASS show updated plan, apply then
invoke fixed remote preflight/run slices with .local/invoke-cloud-service.py. This operator
only submits/observes Run now; no local Delivery engine. Read-only final audit prepared
.local/verify-cloud-service.py. Do not use the old local service root or PR3 for new test.

--- Prior progress below ---

# Current cloud acceptance continuation

Cloud service source published to existing PR1 via native App immutable cycles8=506d6be,
9=1acd9472bfbc54f37d5a20610694c1d816cf2d81 (summary CI receipt kind correction).
Next publisher cycle10 only for NEW content; never alter frozen cycle payloads.
Source CI46121763548 green. Installation plan f424af5f1c3fc8cc8acce7f3243ac6b393c9715883f79cbcb11b7704b3e6b9e4
complete/appliable, shown to user, NOT APPLIED yet. Updates only code of existing controller,
broker1 and store plus installation bookkeeping. New predicted broker pin7951aec4...,
store92c41331... are frozen in config/claude-service.json and generated settings.
All source/model/MCP/write scopes unchanged; runtime JSON compact for251945byte controller.
Source native Opus/high review pending: rootb81bef56-263d-4ba4-99be-01d3e96cbd2c,
session ses_644df37027bb4b7c84257e1c48538b37, turn run_7c559243406d4bed8c361006163608a8,
frozen .local/cloud-service-review-packet.json and .local/cloud-service-review.sqlite3.
First observation loop ended on read-only GET timeout; retry SAME job/session/turn.
No new service run/admission/worker/PR launched yet. After review PASS apply shown plan,
verify exact code and bindings, then invoke fixed service preflight (no workers) through
.local/invoke-cloud-service.py; it only submits/observes manual Run now, NO Delivery/NativeJobs
service controller locally. It persists submission receipts and refuses ambiguous resubmits.
Then manual run slices until remote ready_for_acceptance, repeat inspect/run to prove no
duplicate agents/commits/PR. All8 automations paused, production flagsfalse, no pilot.

--- Earlier state below ---

# In progress: installed Collegium bundle red/fix/green acceptance (no local controller)

User explicitly authorized actual cloud service cycle, no pilot, all automations paused.
Fixed service-test preflight/run/inspect entry reuses Delivery inside installed controller;
all state/stage decisions/native workers/App writes/CI reads stay in Collegium. Manual
Run now repeats bounded eight-minute slices only when the prior cloud run has ended.
Service journal/fence/checkpoint namespace isolated from production and earlier diagnostics.
Native App gains only read-only Actions run/job/log endpoints; bounded compressed logs
with SHA256 and exact failing assertion, no gh/host-credential fallback in cloud.
Production flagsfalse. Original App write path, worker/model/MCP scopes unchanged.
Predicted new broker/store code digests frozen in source config; install must update
controller+broker+store together before executing the new service. Local tests156 green
including full same-engine cloud fixture/replay, strict payload scope, native-only log
evidence and tamper/expansion limits, namespace isolation; real bundle validation passed.
Packaged JSON compacted (same values) to keep code.files <=256000 bytes.
Source publication/review/installation pending. No new service admission/worker/PR yet.

--- Previous completed proof below ---

# Completed: live red CI -> native fixer -> green CI; corrected bundle installed paused

Current installed source27f71f50a2ffd2ad296f40017406f4d89512fc37, installation ins_c70812fb10c042028e414bb01285f56b synced, plan d9ac1b08ea5746d1689ccbaed16a8daed46e4818c4afb01ff1b26e7a1c3d0067 applied after it was shown. Exact live controller code match23files/245022bytes/version9.8 worker fingerprints/private model connection and6 read-only MCP bindings verified, native App scope unchanged. All8 automations paused; production execution/brokerfalse. No pilot/Jira/merge/deploy/main write. Native independent source-fix review PASS at exact27f71f5, Opus5.5/high, ses_e3b03f5e523d4a5ba45b1311ab65fa86/run_8b20bd659098467a85b951900a73442f.150 local tests,41 delivery regressions, Ruff and real bundle validator pass; source PR1 green CI46075020097, still open/unmerged.

Primary receipt reports/ci-repair-live-verification.json includes actual red/fixer/green, rejected validation+config amendment, exact singlePR/twocommits, source review and installed verification. Service PR3 remains open/non-draft/unmerged at afcbfb4f53a7cd2214cd187fec7b482f36436515, green CI46074131032 after initial red46073983075 at c5276ea200baf08d5982f9c4a6bf94d856d935a9. Root d604c82e-1571-49fd-96de-c31dbedab7aa ready_for_acceptance/deliveredfalse. Native Sonnet5.5/low fixer after confirmed red, new74-test validator, independent Opus5.5/high review. Real controller was MANUAL LOCAL Delivery with native cloud workers/App and local gh CI reads; do not claim scheduled cloud execution or cloud CI-log reading. Original frozen config and bad validator preserved; explicit validated operator correction records PYTHONPATH=src and service budget1m->1.5m with rejected98925 usage, same root/branch/PR. Final usage1302278 including cache. Original9attempts =8accepted/1rejected; no replacement on unknown launch. Source-fix review is a separate explicit read-only review.

Source update used existing exact93-path v5 App publisher, original aa342ea3-1f93-482c-bda3-50d0eb480bbc in .local/bundle-publish.sqlite3, immutable cycle7 payload .local/ci-repair-source-changes.json. Next cycle8 only for NEW changes. Never alter completed identities, source publisher scopes or historical frozen admissions. Local final report/this STATE supplement were written after publication; no new source commit needed just to update their self-reference.

--- Historical snapshots below ---

# Completed live PR red -> native fixer -> green CI; bundle correction pending publication

Service root d604c82e-1571-49fd-96de-c31dbedab7aa reached ready_for_acceptance, delivered=false. SAME PR3 https://github.com/serhii-nochevnyi/collegium-pipeline/pull/3 remains open/unmerged, App actor, exactly two commits and one PR across all states. Initial c5276ea200baf08d5982f9c4a6bf94d856d935a9 quality46073983075 failed with expected assertion; green afcbfb4f53a7cd2214cd187fec7b482f36436515 quality46074131032 passed. One-line ACTUAL red->green only, main unchanged. Fixer native Sonnet5.5/low started AFTER actual red proof; independent native Opus5.5/high reviewer passed repaired head. Full74 baseline tests passed in new native validator. Manual local Delivery coordinator, native private-Claude workers, native App writes, local gh read-only CI observation. All8 automations paused, installed execution/broker flagsfalse, no pilot/Jira/merge. Receipt reports/ci-repair-live-verification.json.

Actual service found an environment/config error: original bare-python full unittest failed imports, native validator incorrectly claimed pass, and controller rejected it. New explicit reconfigure-validation operator method/CLI requires definitive completed runtime/pinned-command failure, preserves old packet/config artifacts, atomically fails that child and records config revision; permits only validation argv/token allowance, then fresh same-head validation/review. Original frozen config/task remain in .local; resumed config explicitly corrects argv with env PYTHONPATH=src and raises service-only budget1m->1.5m, includes rejected98925 tokens. Same root/branch/PR, no duplicate mutation.9 distinct stage attempts (8accepted/1rejected), total1302278 observed tokens including cache. Source profile corrected for future diagnostics. Local150 tests/targeted41 delivery tests and bundle validator pass. Generated bundle prepared; source publication/paused install correction in progress. Do not resume old immutable validation packet or change App/model/MCP scopes.

--- Historical progress below ---

# In progress: live red CI -> native fixer -> green CI service test

User explicitly authorized full live service cycle, all automations paused and no pilot. Running the SAME Delivery state machine manually from local durable SQLite; actual workers are native Collegium private-Claude sessions, writes via existing native GitHub App broker, read-only gh CI/job/log observation. This host distinction was disclosed. No cloud production flags enabled and no schedules resumed. No source code change planned unless the live test exposes a defect.

Frozen .local/ci-repair-live-config.json copied current config/claude-service.json AFTER verifying all8 live fingerprints/private connection/model/effort and App scope; global service profile true is local only, installed settings stay false. Exact initial/red and repaired/green fixture hashes validated. Only tests/test_live_service.py allowed. Initial validation py_compile; initial deliberately failing assertion must reach real GitHub Actions before fixer, then full unittest validation and independent code review required at repaired head. Fresh explicit service admission source_id claude-ci-repair-live-v1; old blocked root281c... and prior GitHub interruption PR2 untouched. Supervisor .local/run-ci-repair-live.py, journal .local/ci-repair-live.sqlite3, artifacts .local/ci-repair-live-artifacts, frozen requirements .local/ci-repair-live-requirements.md, root/result JSON in .local. Inspect recorded native identities; never relaunch on ambiguous failures or edit frozen config/context in place. No merge/deploy/Jira or pilot selection.

# Completed: LIVE GitHub commit/PR interruption and duplicate-prevention proof — paused

Current installed source **5d5d64562c796f5f33ac49dcc7f560b99cb3e699**, installation **ins_c70812fb10c042028e414bb01285f56b**, synced. Applied shown plans **79440a18869723bc6de1fa0a1855395b54580f1298a267f479fbbff98a56f665** (fixed live probe) and **1d1b4697e770b5fef86fea2213b7b4b6fc97b638022cd6ee9ee45782e6937f10** (actual ref URL bug fix). Both changed only controller code/source bookkeeping. Exact live code match, production execution_enabled=false/broker_enabled=false. All EIGHT project automations remain paused. No worker/pilot/Jira changes, source/service PR merge, main write, release or deploy.

Primary receipt **reports/github-live-recovery-verification.json**, full raw resumable progress **.local/github-live-progress.json** and individual github-live-*.json submissions/outputs. REAL service branch **collegium/2a53ecf0-5362-4155-98c8-7f51db8f0cd3**, readiness/service root **2a53ecf0-5362-4155-98c8-7f51db8f0cd3**, base/main **dbe5e20955dee07fab2a7bc9ab93aa0bcd1b0451**. Exactly ONE service commit **45a1316aa2da1111b46b3768917973f696ad5d01**, only changed file tests/test_live_service.py; exactly ONE PR including all states: **https://github.com/serhii-nochevnyi/collegium-pipeline/pull/2**, open/unmerged, created by **airslate-agentic-platform[bot]**. Comparison base..head confirms total_commits1; main still original base. Source PR1 is separate and remains open. Service quality CI46072813206 GREEN at service head; source quality CI46072549321 GREEN at installed5d5d645,147 local tests/Ruff51files/real lap validator passed. Native independent probe review PASS and separate URL-fix review PASS, sessions/observations/runtime proofs in final report. No new model/effort/MCP/connection/secret scopes.

Real post-acceptance/pre-receipt fault window: App mutation completes, wrapper emits ready and withholds return before PRBroker broker_done; manually Cancel controller so its entire attempted journal/RPC identities are discarded. Commit cut **run_5d66a4f463fd4f229723451142302577**; independent restore **run_f356d0d865fe410187abcd519064df3c**, repeat import **run_bb6dfd2a8be842f09aabd485df55d8d7**, same commit action replayed twice (**run_c9ae2893500c413d8c553c67c5d4a0fc**, **run_08324b27ea244ae79ab58d61b1e70f56**) with mutation_calls0 and same SHA. PR cut **run_c0a3a1d98f7c43bc8705d149184908a7**; restore **run_d8cc08f33c0d4d10a4c6192c03b86cc5**, repeat import **run_8ae6cf5a39bf440abf2b4ed8681e3982**, identical PR action replayed twice (**run_73d82d4d98254866aefcacd6e7071789**, **run_5e79d83df4ba45a8b43aac4e9b2b248c**) with mutation_calls0 and same PR2. Final inspect **run_5c20f0cb4d4d484fb65920bd0614c09b** confirms SQLite integrityok, ONE service admission and one broker_done each for commit0/PR. This is now LIVE GitHub fault-window evidence, superseding the older fixture-only limitation. It is not a universal exactly-once guarantee or a red-to-green repair acceptance.

Live test found and fixed an actual native ref bug: first prepare **run_b018467d353842ca8560f91be4b1be13** created the canonical branch201 via App child **run_82fcf13fcad74ccc8f4226577f2013ef**, then GET ref with collegium%2FUUID incorrectly returned404. GithubApp.ref and local-gh matching-ref now preserve literal slash (quote safe=/), retaining escaping and exact identity filter. Regression asserts actual request URL. Continued prepare **run_f54a0d05d465438ebdc63dd8756c0585** observed the SAME existing branch/admission; no replacement branch created. Never treat the first failure as no-effect or resubmit a new random root. Failure diagnosis/raw child receipts preserved locally.

Diagnostic modes recovery-probe/github-prepare, github-commit, github-pr, github-recover, github-inspect are fixed and reject extra event fields. They use the existing shared diagnostic namespace/journal with the native-worker proof preserved; scoped write authority is derived only for the explicit fixed one-file service fixture while packaged production switches stayfalse. Native inspect filters its original admission. Native recover refuses a broker checkpoint and directs to github-recover. The current diagnostic store head now belongs to the PR interruption; use github-recover/inspect or same-mode idempotent replay, never a new native start. Previous native session/turn proof unchanged. Product checkpoints are separate delivery namespace. No need to widen App paths or mint/retrieve a token.

Publication continuity: existing exact93-path v5 publisher aut_f7e1268b1afe4af5a24d942a5e993166, config .local/recovery-publish-v5.json, original root aa342ea3-1f93-482c-bda3-50d0eb480bbc in .local/bundle-publish.sqlite3, same source branch collegium/9d121af5-f676-4e7b-bb38-b5c571af87c3/PR1. Completed cycles4=b12ff789 (probe),5=87fe32f (formatted passing fixture),6=5d5d645 (native refs). Nextcycle7 only for a new reviewed payload. Frozen maps github-probe-source-changes.json, github-probe-fixture-changes.json, github-probe-ref-fix-changes.json layer on previous recovery maps. New report/final STATE are local post-publication supplements. Preserve dirty bootstrap main and historical admissions; never reset/rebind or rewrite completed mutation identities.

--- Older entries below are historical, superseded where noted ---

# In progress: live GitHub interruption/replay service proof

User explicitly authorized actual GitHub commit/PR fault-window test, no pilot, all automations paused. Fixed github-* modes added to existing recovery-probe in scripts/bundle_controller.py. No new scope/automation/secrets/worker changes: same diagnostic journal/store, one new immutable readiness/service admission, existing one-file tests/test_live_service.py App scope. Prepare adopts canonical run/branch; real mutation succeeds then its reply is deliberately withheld before broker_done, with ready signal for real Cancel. Recover uses existing independent snapshot and read-only external reconciliation; repeating identical commit/PR modes must return mutation_calls0. Main production switches remainfalse; only fixed manual service authority derived internally. Tests:19 recovery and20 bundle pass including full fake-cut/whole-state-rollback/real signed store/repeat-mode sequence. Live proof, source CI/review and install pending. Latest installed source remains e86f9df; exact93-path source publisher v5 nextcycle4. Do not alter historical admissions or choose a pilot.

# Completed: independent checkpoint reconciliation and safe resume — all automations paused

Current installed source **e86f9dfffb752268e557f3e87d4a331ab1d0e19d**, installation **ins_c70812fb10c042028e414bb01285f56b**, synced. First recovery install plan **d9c36d8e1728019177d61c7b0b948d2893441043e645673e418505f47acad975** adopted the existing store (no duplicate) and updated controller+store code. Final plan **377df22de0686048d3f97a587074b480d1d235cbad967fac90567f6cf2d104a8** updated only controller code/source bookkeeping. Both shown before apply. Exact live match of23 controller files/227300bytes, plus pinned store scope/code verified. All EIGHT project automations verified **paused**, including auxiliary source publishers. Packaged execution_enabled=false, broker_enabled=false; no product pilot chosen, Jira tasks created, service PR created, source PR merged, schedules resumed, release or deploy.

Primary receipt **reports/external-recovery-verification.json**. Source PR1 open/unmerged, CI **46070730465** green at exacte86f9df. Full144 tests/Ruff51files/compileall and real lap bundle validator pass. Recovery suite18 tests + isolated packaged import. Native full review found CR1 (store committed but ack lost); fixed with exact pending-upload/head adoption and regression cases. Native follow-up CR1 review PASS **ses_1fe1e35b148c498e8b55f3463fd00c8b** at f405f0d, final package review PASS **ses_ee6f0797eae844a4a73af20269a5e9fb** at e86f9df, no blockers. Full receipts .local/recovery-review.json (initial finding), .local/recovery-ack-review.json, .local/recovery-package-review.json. Private Claude Opus/high runtime/served-model proofs in each accepted native result; no provider-internal reasoning claim.

Actual live cloud proof: HMAC authenticated store connection **run_5ec2826be71244dda1202ba30d4190c1**, agent_startedfalse/headnull. Fixed recovery-probe start **run_b5a7c1b9d06642a8858aa84a18614fc7** took independent checkpoints before creating/prompting one native executor, then controller was really Cancelled after ready. Lost-attempt state was restored in fresh sandbox. First/repeat recovery **run_06f3f18d05164017931876a701c8a82c**, **run_20a38a1931c94f4296f3d32390dbda04** retained exactly one session **ses_0fcc9af94f3d4920a4279e94d9a7b804**, one turn **run_c571a994a7be4864a84ce83f7b0d40f5**, one admission, SQLite integrityok. Exact same session/turn verified by full platform lists; native process/served-model proof = **claude-sonnet-5-5/low**, private connection mcn_699c8e51528e4438a359acfd4dced40f. No MCP or GitHub mutations by diagnostic. Final installed code repeated recovery **run_bce2f50826c441589ae27a6879ee00cc** and integrity read **run_a0c5c216218e4e4bb7df237d2ae2751a**, both succeeded without another worker. Full evidence .local/recovery-live-evidence.json and final-* files. Do NOT submit another start: the diagnostic store head already exists; use recover/inspect only.

Independent store **aut_3a938ace3b15451585f1ed87f166625f**, paused, no repo/MCP/model grants, only project/PIPELINE_CONTROL_KEY reference. Actual approved binding **cd7736107a49d5858c8b7e7e5fb21b1d5d1176d54797cee76bafa62228cf4ed8** matches namespace-aware live store code. The Vault key value was never retrieved or published. HMAC request/response auth, owner/project/code/secret pins, immutable120KB chunks, full digest, CAS parent, independent adopted state; 24MB raw/8MB compressed bounds. Separate delivery/diagnostic namespaces. Consistent SQLite+verified artifact snapshot before cloud tick, session creation, prompt and broker mutation; no effect without durable acknowledgement. Persisted pending-upload descriptors plus effect_not_started/unchanged-tick proof can adopt exact self-committed head after lost ACK without discarding newer journal. Different advanced head/stale pending descriptors block. Safe no-effect retry uses the original intent; no new ambiguous session or mutation.

Fixed action reconcile observes adopted journal or imports latest closed attempt's exact frozen-config checkpoint in staging, verifies DB/artifact integrity, identifies named agent/trace/turn and existing commit/PR via original expected parent/tree/action marker/branch/repository/head/base. Import receipt joins a journal checkpoint event; repeat import is idempotent. Live delivery auto-runs read-only reconciliation on uncheckpointed history, then rechecks complete fence; existing uncertainty is also reconciled before next cloud tick. No code/CI acceptance, configuration rebind or model/effort escalation is implied. Workers/MCP config unchanged. Historical admissions (including old service root281c...) are NOT silently rebound to the new recovery_store config.

Limits: live cancellation recovery was proven for a REAL private-Claude worker. GitHub lost-commit/PR response + whole-snapshot recovery was proven with stateful API fixtures/real SQLite/separate signed disk store, NOT live GitHub response fault injection. Actual source publishing still used the dedicated App and same PR with expected-head verification. Unknown/missing/changed external objects, legacy gaps without independent checkpoint, mismatched frozen config, external head drift and history exhaustion remain blocked. Do not call this universal exactly-once execution. Source f405 update plan was refused for >256KB (NOT applied); final builder excludes only cloud-unreachable local doctor/controller/packets/readiness/runner modules, CLI doctor import is lazy, real isolated-package smoke test and conservative256000byte bound added. All local CLI modules remain in source.

Publication continuity: exact93-file v5 source publisher **aut_f7e1268b1afe4af5a24d942a5e993166**, .local/recovery-publish-v5.json, paused, no extra secret. Root **aa342ea3-1f93-482c-bda3-50d0eb480bbc** in .local/bundle-publish.sqlite3 continues existing branch collegium/9d121af5-f676-4e7b-bb38-b5c571af87c3 / PR1. Completed cycles0=48221f0,1=a8ec33f,2=f405f0d,3=e86f9df. Next cycle4 only for a NEW reviewed payload. Frozen maps .local/recovery-source-changes.json, recovery-ack-fix-changes.json, recovery-stale-fix-changes.json, recovery-package-changes.json layer on prior state/bundle maps; package map explicitly deletes five local-only generated modules. Final report/STATE are local post-publication supplements. Never overwrite immutable publication requests, reset local dirty bootstrap main or duplicate existing objects/admissions.

--- Historical entries below superseded where noted ---

# In progress: independent checkpoints and external reconciliation

User authorized read-only reconciliation and safe resume after ambiguous external effects; all automations paused and no pilot. Implemented independent signed/chunked store, tick/effect checkpoints, stable agent intent names, observed session/turn recovery, commit/PR identity/tree reconciliation and atomic import with joined receipt. New recovery-store automation **aut_3a938ace3b15451585f1ed87f166625f** created paused, no repos/MCP/model, only project/PIPELINE_CONTROL_KEY reference. Its next bundle plan updates the exact code to namespace-aware version; config/claude-service.json approved_digest is the EXPECTED post-plan code digest cd7736107a49d5858c8b7e7e5fb21b1d5d1176d54797cee76bafa62228cf4ed8 with unchanged actual target/triggers. It is intentionally not claimed live-ready until install/metadata check. Worker model/effort/private connection and MCP grants untouched.

15 new recovery tests, 140 total, Ruff51 files and real lap bundle validator pass locally. Source publication and native independent review pending. New exact93-file source publisher v5 prepared .local/recovery-publish-v5.json, adding only eight new recovery source/generated/test/plan paths to prior85. Continue existing source PR1/branch. Latest remote before this scope 95503b1014d9f28e8c08111564f2623b525a9e80; original local main remains dirty bootstrap. No tests here create a product ticket or pilot. Existing historical admissions stay frozen, not silently rebound to the new recovery-store config.

Current package has 8 workers +3 paused bundle automations (controller, App broker, recovery store), 10 claims. Recovery-probe fixed modes connection/start/recover/inspect require delivery/broker flags false. It launches at most one fixed Sonnet/low private-Claude runtime diagnostic in separate storage, then holds for manual Cancel. Repeated start with existing diagnostic checkpoint is refused, and recovery is observation-only. Live diagnostic remains pending after installation. Production recovery auto-runs only behind explicit live delivery authority, then rechecks the entire history fence; no generic bypass. The missing/ambiguous object case still blocks instead of replacing it. Checkpoint bounds raw24MB/compressed8MB, signed120KB chunks, independent CAS and local head drift check, separate diagnostic namespace.

# Completed: persistence and interrupted-run verification — all automations paused

Current installed source **95503b1014d9f28e8c08111564f2623b525a9e80**, installation **ins_c70812fb10c042028e414bb01285f56b**. Recovery update applied with plan **904b79053ae5dee137195b592f5354cda33c3c074ef6cd15d821ab61a1577a27**; final pre-dispatch-accounting correction applied with plan **ca3b77a6e0deb8935341d4ca2b6cec7d9df8a13a8df52a14b27a98f871388bc8**. Both plans were shown before apply. Only controller entry/store code changed, plus installation bookkeeping. Installed code is exact-match to all 27 generated files, code version4. Worker configurations/bindings, private Claude connection and MCP grants unchanged. All SIX project automations (including native source publisher helpers) verified **paused** after diagnostics. Packaged execution_enabled=false and broker_enabled=false. No pilot selected, product/service PR created, source PR merged or schedule resumed.

Primary receipt: **reports/state-recovery-verification.json**. Source PR #1 remains open, CI **46066320241** green at exact95503b1. Local125 tests/Ruff47files/real lap bundle validation pass. Final independent native Opus/high/private-Claude review PASSED without blockers: session **ses_fbc2ed0359864a508a73cc8e2513fc5f**, turn run_6f87971fb6e74656a9b8ee3710da9684, observation digest735013dd6928a11e7c99880d7969a96e77bc0ffbe497ac1f15c05f266e0c1c11. It reran125 tests and 11 scratch review tests (including inherited fixtures), confirmed bundle rebuild equality and rejected forged/mismatched no-dispatch records. Earlier review independently reproduced the WAL race and ran25 successful Linux concurrency repetitions after its fix. A previous review's prose-prefixed JSON was NOT accepted as a validated worker result; that completed child was marked failed locally and superseded by a new explicit job/source revision, not silently replayed.

Actual cloud evidence: two initial prepares and a prepare/status after update return the SAME original canonical root **3ddda87d-ad4c-46ed-a584-43eab28004ef**, one admission. Diagnostic state-probe DB holds one distinct canonical diagnostic root83f6fb7d-9706-4f11-b09f-221da927bd54 and one committed effect. Repeated commit, abrupt process exit75 inside SQLite transaction, next-sandbox read, real Cancel after an already-autocommitted attempt marker, and next-sandbox read all passed integrity_check=ok with no duplicate. Platform cancellation discarded the entire attempted snapshot, including its committed marker. Fenced cancelled probe was quarantined on two retries and remained blocked on final95503b1 source: run_d1e87402368c4820966564292b03fca6. Final diagnostic integrity read run_c52bd4532f84419f98e189298204a893 passed.

Final cloud accounting test: malformed delivery (no run_id) **run_9409bc40057d4f12a61d002c08d9549c** recorded no-dispatch; two later intentional `live=false` delivery rejections **run_3b2b5030922f49b59cad323f3ca163ff** and **run_ed2eee86afb14ad3a2dfecde99b7e419** passed the fence and each adopted its own checkpoint, proven by separate preflight reads. No agent/broker dispatch. This distinguishes ordinary adopted failures from ambiguous discarded attempts. Full live receipts .local/state-live-evidence.json, .local/state-accounting-live-evidence.json; all individual submissions/results retained to avoid blind replay.

Fixes: direct immutable intake rather than shared requirements file; bounded retry ONLY for SQLite WAL initialization SQLITE_BUSY/LOCKED (not external mutations); cloud first-attempt identity/history fence with adopted receipt; pagination/history-window refusal; ordinary failure checkpoint in finally; per-run/per-attempt no-dispatch records for harmless failures before dispatch (skip but NEVER anchor past older uncertainty). Missing records, lost/cancelled snapshots and unaccounted retry attempts block replay. Generic errors no longer falsely claim executed=false after possible effects. Stateful PR/commit lost-response tests now close/reopen the real journal and prove single mutation; these are contract fixtures, NOT a live GitHub lost-response injection.

Limits: no automatic reconstruction/import of cloud state after uncertain external actions; these remain quarantined until operator-reviewed reconciliation is implemented. Actual executor_lost infrastructure failure was not forced; n>1 retry refusal is covered by tests and platform contract. Do not describe this as exactly-once external execution or full automatic crash recovery. No new service/pilot task should be chosen without user instruction. Further recovery-interface work is a separate scope.

Source publishing continuity: new paused exact85-file publisher **aut_e98e1ccb28594a938ec7d9815bda7cd5**, pinned .local/state-publish-v4.json, explicitly adds src/collegium_pipeline/store.py to prior84-file scope. New publication admission root **5829f85f-7bad-4761-b2e4-ef4b1302df84** in .local/bundle-publish.sqlite3; it continues the EXISTING branch collegium/9d121af5-f676-4e7b-bb38-b5c571af87c3/PR1. Completed v4 cycles0..3 end at95503b1, next cycle4 only for a NEW reviewed payload. Earlier v3 cycle5 ends4b21195; do not overwrite its immutable payload or silently rebind original admissions. Source snapshots .local/state-fix-changes.json, state-fix-followup-changes.json, state-fix-final-changes.json, state-review-fix-changes.json, state-accounting-changes.json layer on prior bundle snapshots. Final reports/STATE are local post-publication supplements. Original local main remains bootstrap/dirty; never reset or overwrite unrelated edits.

--- Prior entries below are historical and superseded where noted ---

# In progress: cloud state recovery and replay protection

User requested actual interrupted-run persistence and duplicate prevention, fixes, no pilot, automations paused. Two manual installed-controller prepares returned the SAME canonical run 3ddda87d-ad4c-46ed-a584-43eab28004ef across independent sandboxes: run_d3909ff287a6414fb1f96b19dbd13ab7 and run_aead6f42165c418a985595a4ec4c2ab0. No agent or GitHub mutation.

Important platform contract (automations.md): normal failed scripts with exit codes adopt state; cancellation discards attempt writes, executor_lost retries from OLD snapshot. SQLite durability alone is insufficient across discarded snapshots. Fixed controller removes shared intake file; adds independent platform-history cloud fence before delivery; rejects non-first attempts, uncheckpointed prior delivery, mismatched receipts and exhausted history. Receipt travels with the adopted journal. Ambiguous external actions require reconciliation rather than replay. Diagnostic namespace state-probe supports bounded commit/crash/hold and independent fence tests, disabled execution/broker only, no agents or repo writes. Local checks: 121 tests, Ruff47files, actual subprocess crash recovery and four concurrent intakes, DB reopen on lost PR/commit responses. Live cancellation/fence test and source review remain PENDING until source update is installed. Source PR #1 remains open and unmerged. No schedule activation, pilot or service red-to-green claim.

# Completed installed bundle verification — automations paused

User-approved initial plan d5fcf9a012e5e8cd9b804c778075704e5cd23e70df300d9e4e261d9de4c58c28 was applied at ecb584a. The authorized controller-binding/diagnostic refresh was then published in source PR #1 and applied with reviewed plan **e9123f7de7c47e25068ba8c7c7cd0a0b6d03f80d2fa181151d34c81377af7f29**. Current installed source **b239cd572dd022cb2fecf4d776bf8f42e30759a5**, installation **ins_c70812fb10c042028e414bb01285f56b**, status synced/complete. Refresh changed only controller code/settings, with ownership/source bookkeeping. Both **pipeline-controller aut_2ea6d08b772f41d5a9fa236cb19f93d8** and **pipeline-native-broker-1474663859-v1 aut_5b17ddca92424243b1feb5aa8732a7a0** were verified paused after all manual diagnostics. Exported execution_enabled and broker_enabled remain false.

Actual cloud Vault-key authentication PASSED: controller manual verify-control run **run_b738442913dd4a9898f5fc1f002ddfb9**, succeeded/exit0/not truncated. Returned control_key_valid=true, worker_bindings_verified=8, mcp_connections_verified=6, app_broker_scope_verified=true, agent_started=false. Only bounded GETs use the Vault environment key; no host-key fallback or credential value exposure. The controller's installed files match the generated bundle byte for byte; all eight stable worker hashes and paused App broker scope match from both local and cloud checks. Source CI **46062097245** green, 114 tests. Independent final Opus/high review passed without blockers: session **ses_29ca3598d6b3477c9a7dec0832c1f6d4**, turn in .local/bundle-stable-review.json.

All eight installed worker variants have fresh native runtime/served-model/effort proofs in reports/claude-workers.json, stable journal .local/installed-calibrations-stable.sqlite3: planner, plan_reviewer, code_reviewer = claude-opus-5-5/high; executor/fixer = claude-sonnet-5-5/low; sentinel = sonnet-5-5/medium; fixer:high = sonnet-5-5/high; fixer:max = opus-5-5/max. Private model connection mcn_699c8e51528e4438a359acfd4dced40f preserved. This verifies actual launch args and served-model support, not provider-internal reasoning. Six successful MCP tool-use/result pairs (atlassian-rovo, ak-prod, ak-dev, grafana-prod, vmcluster-prod, backstage-prod) were independently inspected. No backend payloads published; event IDs/digest in reports/mcp-connections.json.

Correction to an earlier diagnosis: this actual controller-only sync DID NOT change per-worker provenance.commit; all eight workers retain ecb584a and their API configuration stayed identical. The source-label normalization is a defensive guard tested with synthetic revision changes, not a live observed drift in this apply. Do not claim we observed source labels changing for unchanged workers. A comment in platform.py introduced with that assumption should be clarified in a future documentation-only cleanup; its implemented fingerprint behavior and security-preserving tests are valid. No further repinning or calibration loop is needed: post-apply live bindings match.

Primary final receipt **reports/bundle-installed-verification.json**. Updated reports/bundle-install-preflight.json, reports/bundle-source-verification.json and reports/mcp-live-progress.json reflect installed state; these final receipts/journal edits are local supplements after publication. Full applied plan/output: .local/bundle-controller-refresh-plan.json / .local/bundle-controller-refresh-applied.json. Do not replay completed apply or diagnostic submissions blindly. Existing service admission remains blocked on its original configuration; do not silently resume it with refreshed pins. No product pilot chosen, service red-to-green verified, source PR merged, schedule resumed, release or deploy performed. Six other requested integrations remain pending; see the final receipt.

# Stable post-install fingerprints and live MCP probes

Before applying the controller refresh, identified that agent.provenance.commit/version tracks bundle source labels even when runtime configuration does not change. agent_digest now excludes only those two revision labels, while keeping installation/source/instance identity, source_gone, models, effort, secret and connection permissions pinned. Regression tests cover stable source-label updates and changes to model, effort, secrets and installation identity. Installed runtime configuration is unchanged; fingerprints were rederived from the verified installed objects and checked against fresh API reads. A second frozen calibration pass uses .local/installed-calibrations-stable.sqlite3 with independent receipts; earlier admissions remain immutable. Controller code at bb195231 is reviewed and CI tracked, but not applied because it would carry unstable hashes. The next source update corrects that and the review's two non-blocking test/doc findings.

Native installed-worker MCP probe session **ses_091e22d78d8d4cd981e1e56cee4efda7** successfully called all 6 intended read-only tools; matched all 6 agent.tool_use/agent.tool_result pairs with is_error=false. Proof .local/installed-mcp-probe-evidence.json, observation  digest in that file; no backend data is published. The original controller's manual preflight succeeded, run **run_b715a0c36521415c8b07f71e282e5f61**, reporting control_key_present=true, execution_enabled=false, broker_enabled=false. This proves Vault injection, not yet authenticated API access. Both automations remain paused. No source merge, delivery, Jira write, product pilot or service PR occurred.

# Bundle installed paused; refreshed bindings and runtime calibrations

The owner-authorized plan d5fcf9a012e5e8cd9b804c778075704e5cd23e70df300d9e4e261d9de4c58c28 was applied successfully to installation ins_c70812fb10c042028e414bb01285f56b at source ecb584a62cd997768a8bb1a7687fe094ce5db859. Installation status synced/complete. Controller **aut_2ea6d08b772f41d5a9fa236cb19f93d8** and broker **aut_5b17ddca92424243b1feb5aa8732a7a0** are paused. The secret is bound only to the controller. Actual installed references, all 48 explicit MCP toolsets, owner/project/private Claude connection and unchanged model/effort were checked before repinning the eight worker fingerprints and broker fingerprint. Native MCP references are in agent.references.mcp; config.mcp_servers normalizes names and omits connection IDs. Do not infer exact connection identity from names alone.

New frozen post-install calibration profile is config/claude-calibration.json; service/controller bindings are config/claude-service.json. Original profiles archived under .local/pre-install-claude-*.json; existing service admissions remain blocked on original digests and are not silently rebound. All eight installed variants passed actual process-argument/runtime verification using the private Claude connection, including Opus/max. New receipt report reports/claude-workers.json; journal .local/installed-calibrations.sqlite3, artifacts .local/installed-calibration-artifacts. Binding derivation receipt .local/installed-binding-refresh.json. Only diagnostics ran, no delivery or service PR.

Controller settings refresh and fixed verify-control diagnostic are being published through the existing source App. verify-control accepts no event parameters beyond action, uses only PIPELINE_CONTROL_KEY from the Vault environment, reads the eight exact pinned agents and App broker metadata, and starts no agent or automation. It is needed because original preflight only tested key presence. Cloud authentication remains PENDING until that source update is installed and the manual diagnostic succeeds. Both automations must stay paused, and exported execution/broker flags remain false. Prior sections below are historical where superseded.

# Control secret present; complete unapplied plan

Owner created a separate limited personal Collegium key and saved PIPELINE_CONTROL_KEY in the project's Vault. Metadata only verified: **cred_8757e160da5f44eeb28212fa3c8bcb7c**, scope/level project, delivery **env**, allowed_hosts=[], header_names=[]. Value was never read; validity, actual key limit/expiry and cloud API permissions remain unverified. Important correction to older descriptions: Collegium personal keys can be limited to a SPACE, not a project; personal spaces have no service accounts. Only the secret storage is project-scoped. The manifest's older description saying 'Project-scoped Collegium API key' is imprecise and should be corrected in a future source update; do not ask the owner to find a nonexistent project-key option.

Standard `installations plan` now resolves the existing environment secret automatically as **project/PIPELINE_CONTROL_KEY**, requirement ready. A direct CLI bind returned bundle_binding_refused; no secret was rewritten, no value was retrieved and no permission workaround was used. Source requirements engine explicitly matches delivery:env for declared env secrets; its generic binding-fit check differed. Replanning was sufficient.

Installation **ins_c70812fb10c042028e414bb01285f56b**, source **ecb584a62cd997768a8bb1a7687fe094ce5db859**, new plan digest **d5fcf9a012e5e8cd9b804c778075704e5cd23e70df300d9e4e261d9de4c58c28**: complete=true, appliable=true, no refusals/open choices. Still NOT INSTALLED/APPLIED; applied_commit=null. 43 operations, 9 claims, 8 worker updates, 6 read-only project MCPs, one paused controller and existing paused broker. All 194 field choices retained, including keeping existing worker environments. Verified all 48 planned MCP toolsets have exact explicit tools/default disabled and correct project connection IDs; model/effort/private Claude bindings unchanged. The secret is attached only to the controller via its exact credential ID/ref. Existing source CI and independent review remain valid; source was not changed or republished for this metadata-only plan update.

Full plan: .local/bundle-vault-install-plan.json. Confirmed stored pending plan: .local/bundle-after-secret-replan.json. Summary: reports/bundle-install-preflight.json. Source receipt installation section updated. User requested presence check and plan update only; no apply was performed. Remaining six undeclared/pending MCP integrations and post-install binding refresh/calibration/backend-read/cloud-state tests remain separate work. Earlier incomplete-plan digests below are historical.

# Verified six-MCP bundle source and installation plan

Source PR #1 current head **ecb584a62cd997768a8bb1a7687fe094ce5db859**, native App publication cycle 2 on the existing branch. Exact-head GitHub Actions quality passed, run **46055313584**. Independent incremental Claude Opus/high review passed without blockers: session **ses_395376ad15f0442ba15a6d41c2747e2b**, turn **run_c1866edcdb2f4ea28152fdf5c55f9fa0**, served claude-opus-5-5 with explicit high effort verified. Reviewer independently ran five bundle tests, checked every source-index digest, and reproduced the generated bundle byte for byte; no source-code changes occurred in this increment. Reports: bundle-source-verification.json, bundle-install-preflight.json; native review .local/bundle-ak-review.json. Receipt/journal edits after publication are local supplements.

The unapplied installation **ins_c70812fb10c042028e414bb01285f56b** now has plan digest **ac479a8840ad1cf983e2525bd5fa498895c66fb92e4b4a64249d4b96efdebca9**, source ecb584a. It is appliable, incomplete, no refusals or open choices. 43 operations: 9 claims, 8 agent updates, one new controller, one broker update and 6 MCP bindings plus ownership records. All 194 claimed-field choices answered: take bundle fields except keep the 8 current worker environments. Verified every planned agent uses exactly six project MCP IDs/URLs, six matching explicit toolsets with default_config.enabled=false, and no unresolved/platform MCP. Actual connection ceilings match source. Current private Claude worker digests are unchanged. Model, effort, owner/project and private model connection remain preserved. No install/apply, worker reconfiguration, cloud activation, merge, backend data-read success or service red-to-green is claimed.

Both AK grants are connected and authorized; their actual IDs and six read tools are in config/integrations.json. Remaining integration blockers were rechecked: GitHub MCP lacks configured OAuth client_id; Langfuse PROD needs project Basic keys, project names/links remain pending; Grafana/VM/Backstage/Langfuse DEV endpoints are unreachable. PIPELINE_CONTROL_KEY is missing. After credentials: replan/show exact digest before apply, verify installed state, refresh controller bindings and recalibrate changed workers, then backend read probes/cloud durable-state recovery. Do not apply an old plan digest. The existing source App continues working and no personal-token fallback was used.

# Agents Knowledge DEV/PROD added to bundle catalog

Both AK environments now have authenticated OAuth and discovery. PROD actual connection **mcpc_27eec2a3866b4c26b04bba961bae9159**; DEV **mcpc_b692cbf768e14262a510f49b15337ded**. Both exact platform ceilings: search_docs, get_document, list_workspaces, list_collections, get_document_tree, get_related_documents. The confirmed PROD consent was still on the browser's Approve page; completed that already-confirmed request and observed the platform callback mcp_oauth=connected before verifying auth-status. No repeat authorization was requested. Both integration bindings, status report and bundle source now include these independent identities. Six active needs; six unresolved needs remain excluded from grants. Backend calls and live-worker attachments remain to verify after installation. Earlier four-MCP receipts below belong to the prior source head and are historical.

# Browser recovery and AK DEV authorization

Chrome browser 3 can open/read fresh tabs, but the extension update warning returned on markHandoff; do not claim the extension is consistently fixed. New main tabs: 1255439376 (PROD OAuth parent), 1255439382 (DEV OAuth parent). AK PROD consent tab 1255439379 is pending owner Approve. AK DEV OAuth completed during this turn; actual connection **mcpc_b692cbf768e14262a510f49b15337ded**. Auth-status authorized=true and authenticated discovery succeeded; actual connection ceiling was set to exactly six read-only tools: search_docs, get_document, list_workspaces, list_collections, get_document_tree, get_related_documents. No backend call or live-agent attachment claimed. Receipt: reports/mcp-live-progress.json; raw tools: .local/discovery/ak-dev-auth-tools.json. The published bundle and its unapplied plan still cover the prior four MCPs; include new AK connections and replan after remaining consent. Browser control had to use a fresh tab because the old tab was debugger-unattached. Never click a new sensitive-access consent automatically; use documented takeover and owner action.

# Verified MCP bundle source and prepared install plan

Source PR #1 now has head **6861ff3d7bd6581e9e52903919f052ae8aa6fce6**, published through the native App on the existing branch, commit cycle 1. Exact-head GitHub Actions quality check passed, run **46052214952**. Independent incremental Claude Opus/high review passed without blockers: session **ses_8b6f0393340544a6a123db8df1a50848**, turn **run_3cd7abe291ad40f886f1b169c0abd716**, served claude-opus-5-5 and explicit high effort verified. The reviewer independently ran 111 tests, targeted Ruff and a byte-identical rebuild. Receipts: reports/bundle-source-verification.json, reports/bundle-install-preflight.json, .local/bundle-mcp-review.json. These final receipt/journal updates are local supplements after source publication.

Installation **ins_c70812fb10c042028e414bb01285f56b** is NOT APPLIED. Prepared digest **d69076131b6b83dc213953d0fc40808c8f91e2ecd2790cc457364cfbcf2b9fb6**: 41 operations, 9 claims, 8 agent updates, one new controller and one broker update, four project MCP bindings. All 162 choices answered: bundle values for changed fields, keep for the eight existing explicit worker environments. Agent MCP connection IDs and exact toolset configs with default_config.enabled=false were verified against the 4 live project ceilings. Existing private Claude worker configuration digests were checked, unchanged. No broad platform MCP or pending MCP appears in planned agent grants. See .local/bundle-mcp-install-plan.json and .local/bundle-mcp-install-choices.json. CLI bind on a not-installed installation discarded the pending claim choices; after all bindings completed, all nine claims and choices were restored. Always inspect the final plan, not intermediate bind responses. Refreshing or binding changes invalidates the old digest.

Live auth-status refresh confirms four authorized OAuth grants: Atlassian, Grafana PROD, VictoriaMetrics PROD and Backstage PROD. Eight other catalog entries remain unresolved. No agent attachments, backend data-call success, installation, cloud activation, merge, service red-to-green or product pilot is claimed. PIPELINE_CONTROL_KEY is missing. Chrome extension refuses control until updated; AK DEV/PROD sign-in remains. GitHub MCP requires a configured OAuth client_id (upstream does not support client registration), independent of the working GitHub App. Langfuse project names/links were requested asynchronously; its credentials are project-scoped Basic API keys entered only in console. Four DEV service endpoints are unreachable. Do not bypass browser auth with CLI keys, or substitute PROD for DEV.

# Current MCP and bundle preparation — 2026-11-27

Grafana PROD OAuth completed. Authenticated discovery and actual platform tool ceilings now exist for four project connections: Atlassian mcpc_6922425fd6a845f4b604a8663ab06385 (8), Grafana PROD mcpc_e33ecc0ae7154059b9b17efe5e967331 (38), VictoriaMetrics PROD mcpc_729b8150e4074b0f9164946e27998b40 (16), Backstage PROD mcpc_948ef97eb40d41f5a0b25f1e0240937b (2). No live worker attachments or backend tool-call success is claimed. Integration config/report and generated manifest carry these exact IDs and lists. Every unresolved catalog entry declares tools: []. The real Collegium validator refuses empty manifest toolsets, while absence means ALL. The builder emits only four authenticated nonempty toolsets as manifest needs and agent grants; the eight pending entries remain in the integration catalog. New negative tests cover unrestricted/unverified tools and wrong connection binding.

GitHub MCP OAuth start is concretely blocked: upstream accepts no dynamic client registration and registered server has no client_id. Existing repository App remains independent and functional. Langfuse needs project-scoped Basic public/secret API-key pairs; async question asks only project names/links. Four DEV services still return 502; AK DEV/PROD require sign-in. Chrome extension began refusing control and requires update. Do not retry or work around browser authentication through personal CLI keys.

Installation is still NOT APPLIED; refresh the source/bindings/claim choices before presenting an apply digest. Published source PR #1 at 1595bcd remains the previous independently reviewed version; new local MCP edits have not yet been published. Historical status notes below are retained as history.

# Live MCP authorization update

Atlassian OAuth completed successfully in Chrome. The actual authenticated connection is **mcpc_6922425fd6a845f4b604a8663ab06385**, name default, not the earlier uncredentialed pipeline-readonly metadata ID. It was explicitly narrowed to eight observed read-only tools: getAccessibleAtlassianResources, atlassianUserInfo, getConfluenceContent, searchConfluence, getJiraIssue, listJiraIssueComments, searchJiraIssuesUsingJql and search. No agents are attached yet; update integration bindings/source profiles against this actual ID when the remaining sign-ins are settled. All earlier status snapshots in the source PR are historical to its commit.

Grafana PROD sign-in is now at an explicit ToolHive consent prompt in Chrome browser 3, tab 1255439301. It asks Approve to send the sign-in to agentic-platform.infrateam.xyz, then Okta. Do not click Approve without the owner's action-time confirmation. The project Connections page remains tab 1255439277. A manual takeover will be requested at the end of this turn; when it is pending, make no CUA calls until the owner returns control. No browser completion directive while waiting on that takeover.

The installation plan auto-selected four broad platform DEV connections and has 162 claimed-field choices defaulting to keep. It is NOT APPLIED. Before any apply, rebind MCP needs to the explicitly narrowed actual project connections and review the claimed-field choices so intended bundle fields are used; do not accept the automatic broad platform bindings. Source PR #1 and its green CI/native Opus review remain valid for the published commit; newer local state/report supplements are uncommitted.

---

# Latest verified source publication

Bundle source is in PR #1: https://github.com/serhii-nochevnyi/collegium-pipeline/pull/1, head 1595bcd97904db6503fb8e8a4f56e2a1a69d494a. Created through the native GitHub App; author airslate-agentic-platform[bot]. Actual quality CI is green (run 46046408116). Native independent Claude Opus/high review passed, no blockers: session ses_c966ef65638b4f719361a9be7bfccf5b, turn run_16eda6ac45f34ac8910ec4a0b3474e19. It independently ran all 110 tests, Ruff, compile and byte-for-byte bundle reproducibility. Source receipt: reports/bundle-source-verification.json (local supplemental report after publication).

The default project environment is now pipeline-base, penv_a033dc0b50904b20add0c8136217d304, Aranarium/standard/base image. It was created because the project and space had no default; choosing it moved no existing agents. A real bundle installation PLAN with all nine claims is now prepared: ins_c70812fb10c042028e414bb01285f56b, plan f447c10805077a2c1b11ac6175efaf0f34130f1eadf881ab46f589ef837f1b66. It is appliable, incomplete, and NOT APPLIED. Do not apply an old digest after changing bindings. Missing MCP credentials and PIPELINE_CONTROL_KEY remain; post-install binding refresh/recalibration and cloud-state verification remain activation steps.

Native source publisher v3 is aut_144094f5a49446a1b4de7f8f531d55d9, pinned in .local/bundle-publish-v3.json; source journal .local/bundle-publish.sqlite3, root 9d121af5-f676-4e7b-bb38-b5c571af87c3. Its bounded compressed RPC successfully published all 84 files in one commit. An earlier uncompressed source attempt was definitively refused with 413 before any commit submission; its empty branch was retained, not deleted. No service red-to-green, merge or product pilot is claimed from the source PR.

Chrome tab 1255439277 (browser 3, airslate.com) is on the project's MCP page with the Connect atlassian-rovo form ready. Authentication must be completed by the owner in the console; do not copy host CLI credentials or ask for tokens in chat. The staged MCP connections still deny all tools. The New connection UI creates a credential-bearing connection after sign-in; reconcile its actual ID and narrow to observed read-only tools before binding it to agents. Langfuse PROD is shown as Not set up, so it may require service credentials rather than OAuth; four DEV services are unreachable.

The user also asked how to connect to Lararium from a phone (this is a side question, not a cancellation of bundle work). Official help was checked: company VPN on Mac and phone; https://lar.infrateam-dev.xyz/app/; install lar on Mac (not currently installed), lar login, lar machine pair, scan QR and confirm matching fingerprint on Mac. Do not install it without an action request. Mac must stay online. Current Codex Desktop on macOS is not automatically promised: docs describe Desktop integration on Windows, and ordinary Codex CLI/daemon or Claude Code plugin separately.

---

# Current update — Claude bundle and MCP integrations

2026-11-27. The owner clarified that this repository is the **bundle source**. The deterministic controller remains correct and must be packaged with its workers, rules, configuration and script entry points. Do not replace it with a prompt-only orchestrator. No Jira task or product pilot is selected.

The active requested model policy is Claude Code on the owner's existing private project/claude-code-subscription (mcn_699c8e51528e4438a359acfd4dced40f). Eight version-1 role variants passed real runtime calibration, including Opus/max, and a Claude worker passed an exact private-repository checkout. Reports are reports/claude-workers.json and reports/claude-checkout.json. Prior Sol-only/Codex choices below are historical and superseded for new platform workers.

The GitHub App is installed for serhii-nochevnyi/collegium-pipeline, repository 1474663859. Its dedicated project connection is ghc_7de07519a1e3437a95f98edc4545022d. Main has non-bypassable PR/code-owner/approval/quality rules. Baseline CI passed; no merge or protection weakening is authorized.

A real bundle is generated at .github/lap/collegium-pipeline. It contains eight workers, a shared rule, controller code/entry/settings, a native App broker and twelve MCP needs. It passes the platform's real local-folder validator. Both script automations start paused, and packaged execution/writes are disabled. Claims preserve the existing eight agent IDs and broker ID. The manifest's legacy GitHub needs represent personal tokens, so repository grants directly reference the existing App connection instead.

Created project metadata for GitHub MCP and eleven registered-service connections. The requested core is GitHub/Atlassian/Grafana/Langfuse, supplemented by VictoriaMetrics, Backstage and Agents Knowledge; every observability/knowledge service has distinct DEV and PROD needs. No tools are permitted before authenticated read-only discovery. PROD and Atlassian need authentication; four DEV services returned 502. See reports/mcp-connections.json. Desktop connectors do not authenticate Collegium connections.

The cloud controller separately requires a project-scoped PIPELINE_CONTROL_KEY in the Vault; do not copy the host CLI key or the Claude token. Binding refresh/recalibration after an applied install plan and cloud durable-state interruption tests remain activation requirements. A valid bundle is not yet a production-ready cloud deployment.

Local checks: 110 tests, Ruff and compile pass. Service root 281c201a-b129-4a5d-96f8-6a03f1db5286 is blocked after an operator interrupt during the user's bundle clarification. Both native stages completed; no broker mutation or PR occurred. Reconcile the recorded child session/turn before any resume. Earlier Codex root fdc168a6-97a3-48ee-b5dc-bd243854100c is separately superseded; preserve its budget/config history.

Full investigation, epic scheduling, parallel execution and cloud production storage are later slices. The current implementation is a serial prototype. Source packaging and MCP authentication take precedence over choosing a pilot.

---

# Historical progress (superseded where the current update differs)

# Project state

Updated: 2026-11-27

## Confirmed scope

Independent Collegium pipeline: investigate, epic and single-task delivery, parallel execution, model/effort policy, quality gates and configuration. Jira remains in the product design. Current implementation is ticketless. The owner explicitly deferred selecting a pilot PR task until the pipeline is ready; do not request or invent one now. Connected repository: airslate-common/agents-knowledge. Remote Sessions is outside scope.

## Connected and verified

- Official lap v0.23.1, CLI owner authentication, dedicated project prj_7e76b4e4920141a2abbedd46ccb713da in personal space spc_abd49a5569154751a43c006659d9f535.
- Project GitHub App connection ghc_73f2cf589000496f88519d531e798f23 scopes only airslate-common/agents-knowledge, repository ID 1345007429. Read sessions work. Contributor installation checks pass, but actual write-token issuance fails because main lacks required non-bypassable protection. No protection was changed.
- Main MCP: 27 tools, authenticated list_spaces succeeds. Help MCP: OAuth verified, three help tools. Private local header helper reuses lap credentials; no credentials stored in project files.
- Aranarium 0.78.1, Codex 0.153.4. All dispatches explicitly select Codex.
- Six version-2 read-only readiness workers bound: planner and independent plan/code reviewers use gpt-6.2-sol/high; executor and fixer use gpt-6.2-sol/low; sentinel uses gpt-6-luna/medium.
- Actual model and effort observed from Codex process arguments in authenticated platform tool events for all six roles. This proves client configuration, not provider-internal computation.

## Implemented locally

Python CLI, role routing, content-addressed artifacts, durable SQLite serial journal, launch/session/turn identity, ambiguous-write quarantine, live observation ingestion, independent stage review gates, sandbox validation, token admission and timeout/attempt limits. Model/effort and complete agent configurations are pinned. Completed self-test replay creates no new sessions. Provisioning, calibration and report publication scripts are included.

Readiness and delivery profiles are separate. Only readiness is enabled; its executor/fixer have read-only repository grants and operate on synthetic files in disposable sandboxes. Self-test success never marks a PR or delivery complete.

## Evidence

- make check: Ruff lint/format, 68 unit tests and compile check pass.
- Native run d93b0a8a-0084-48ec-b43f-6c3c1a5dadf4 passed planning, independent plan review, implementation, seven actual sandbox checks and independent code review.
- Separate fixer and sentinel calibrations passed. Six role proofs and five stage receipts are in reports/readiness.json.
- make doctor-readiness: exit 0, execution_ready true, all six checks pass. This is readiness-profile status only.
- One observation was rechecked after allowing AST-equivalent Python formatting within the unchanged pinned shell frame. The same completed turn was reused; the audit records the reason.
- No target source mutation, Jira write, PR, merge, automation, branch, worktree or local commit was created. This directory was not initialized as a Git repository.

## Remaining boundaries

Slice 0 connections and the native worker/controller readiness loop are verified. Slice 1 now includes a resumable product delivery driver, GitHub App-only PR broker, atomic expected-head commits, exact-tree reconciliation, validation/review per candidate and bounded CI repair. Stateful API fixtures pass the full red-to-green lifecycle and recovery scenarios. Eight version-3 read-only workers are provisioned/bound, including fixer low/high/xhigh; live doctor verified their configuration digests. The previous native readiness effort proofs belong to the separate version-2 workers.

The new delivery profile is disabled. A short-lived, single-repository GitHub App installation credential is not configured; no person-key/PAT fallback is used. A native version-3 planner probe and private checkout at an exact commit passed (reports/delivery-checkout.json); native repository-write/PR/CI acceptance and token refresh integration remain to verify. PostgreSQL/action claims and cloud deployment are unfinished, as are epic scheduling and investigation. See docs/DELIVERY.md and reports/delivery-verification.json. A read-only checkout diagnostic may be run independently of any product pilot.

Collegium write-token policy requires protected main: PRs, at least one approving review, code-owner review, stale approval dismissal or last-push approval, no deletion and no force push, with no bypass. The earlier Contributor token failure remains recorded. New workers stay read-only; the broker uses separate installation authority whose eligibility still needs verification. Do not weaken policy or substitute a PAT.

Gateway spend returns uncounted turns, so no USD ceiling is enforced. Token limits are admission checks and can be exceeded by the final admitted turn; they are not a hard provider cap. The report retains both limitations. Continue preparing delivery infrastructure without choosing a pilot task on the owner's behalf.


## Live GitHub App service-test follow-up

The owner explicitly authorized a real service PR/red-to-green CI (no product pilot). A real Contributor session admission was attempted and refused with HTTP 400 repository_not_given before any session/model turn. App main-rule eligibility remains the actual blocker. The current user has push but no maintain/admin, so cannot change the organization ruleset. Main already has the required protection types; the missing condition is Collegium's proof that the App cannot bypass them. The user's own never-bypass result does not prove the App's.

Prepared the exact red/green fixture, requirements and disabled config/service-test.json against the existing dispatcher CI. No target writes or new model calls occurred. reports/github-app-live-test.json records the actual refusal; docs/GITHUB-APP-LIVE-TEST.md contains the administrator handoff and remaining integration work. An asynchronous question requested administrator action or an already eligible connected service repository; no pilot task was requested.

Important correction: Collegium injects repository tokens through native egress; lap has no installation-token export command. The current environment-token broker is not yet connected to that managed credential lifecycle. A scoped deterministic script-executor broker remains to integrate/verify after write admission; do not claim the App is fully connected to the broker or that only the live test is missing.


## Personal remote bootstrap

The owner corrected the destination to their personal account, serhii-nochevnyi. Created private serhii-nochevnyi/collegium-pipeline (repository ID 1474663859), default main, owner admin access. An attempt under airslate-common was refused before creation and is not the target. A separate project App connection ghc_7de07519a1e3437a95f98edc4545022d is created but has no repository row yet. Collegium's App is not installed on the new repository.

The correct platform App is airslate-agentic-platform, owned by airslate-common; its public GitHub App ID is 4976598. A native code-only read probe proved repository REST 200 but GraphQL 403 with managed egress credentials. The new native broker helper therefore uses repository REST and a Git protocol expected-head lease, never token export or GraphQL. Its scope guards have five local tests. The source baseline now passes 73 tests. Native broker transport wiring and live service PR/CI are still unfinished.

Bootstrapping the new remote's source, CODEOWNERS and CI is authorized by the owner's request to create/use this remote for the service test. Prior bench defaults against remote writes are superseded only for this explicitly named repository and test; no product repository mutation or merge is authorized. Historical profiles/proofs are retained unchanged.
