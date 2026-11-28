# Independent checkpoint and external reconciliation

Scope: continue the existing ticketless implementation, no pilot, all automations paused.
Use the existing private Claude workers; no changes to their model/effort/MCP configuration.

Research: Collegium discards controller attempt state on cancel/executor loss. Named agent
sessions are unique per agent, and prompt_async supports Idempotency-Key. Neither local WAL
nor a checkpoint in the same cancelled attempt can recover the missing journal/artifacts.
The platform's run-step notes are bounded to 2000 characters and are not a blob store.

Implementation:
1. Add a separate paused, repository-free checkpoint script automation. Signed, bounded,
   chunked writes commit independently before any worker or broker mutation. CAS on the
   prior checkpoint and content digests prevent stale overwrite. Vault key is used in memory
   for request/response authentication; never written to checkpoint/output.
2. Export SQLite consistently plus content-addressed artifacts. Checkpoint before session
   creation, prompt submission and native broker submission. No external call if persistence
   acknowledgement is missing. Restore only a pinned checkpoint for the unresolved cloud
   run, exact config/owner and original task identity. Stage the import and preserve backup.
3. Reconcile existing named sessions and their recorded turn identity/prompt. Reconcile
   commits by expected parent, complete tree and action marker; PRs by exact repository,
   branch, base and run marker. Never create a replacement while outcome remains uncertain.
4. Import with an audit receipt and let the existing delivery state machine resume its
   recorded identities. Keep task/config/quality gates and scopes. Legacy gaps with no
   independent checkpoint remain explicitly blocked.
5. Test real state loss, lost session/prompt/commit/PR responses, tampering, stale CAS,
   missing/ambiguous objects, repeated reconciliation/import and unchanged paused settings.
   Publish into the existing source PR via its scoped App, install reviewed bundle plan,
   and run service-only interruption diagnostics; never choose a product pilot.

## Live GitHub continuation

Add fixed github-* modes to the existing recovery-probe. Reuse the diagnostic namespace
and its adopted journal, adding one immutable service-only admission. Keep the previous
native-agent diagnostic intact. The existing App scope already permits only
`tests/test_live_service.py`; the fixed passing fixture stays in that scope on a new
run-owned branch. Controller global execution/writes remain disabled. A narrowly derived
broker authority exists only inside this explicit service diagnostic.

Prepare persists the canonical root/branch. Commit/PR modes call the real App mutation,
then deliberately withhold the returned result and hold before PRBroker records done.
Cancel the controller after its ready signal, restore from the independent checkpoint,
then run the exact same modes twice. Observe one commit by base comparison/branch SHA,
and one PR including closed PRs by exact branch. Leave both source/service PRs unmerged.

## Live CI repair acceptance

Run existing Delivery engine under a local manual supervisor with native private-Claude workers
and App-only writes. Freeze a fresh service config/task; do not rebind historical admissions.
Initial exact red fixture compiles locally and must fail the actual PR quality job with the
expected assertion. Only this evidence admits the native fixer; repaired exact green fixture
needs full validation, independent revision-bound review and actual same-PR green CI.
Keep every automation paused; no source/product pilot or merge.


Live CI repair found a misconfigured src-layout test command. The controller correctly
refused a worker pass contradicting actual exit1. Add an explicit audited validation-only
configuration correction: require original completed/pinned runtime evidence, preserve failed
job and both configs, account all usage, atomically amend the parent configuration and
start a fresh attempt at the same head. Never replace an uncertain launch or allow changes
to scope/models/CI gates through this operation. Correct service argv with PYTHONPATH=src;
retain the complete test discovery. Explicit manual budget amendment records1m->1.5m.
The real diagnostic then completed: PR3, initial red46073983075, repaired green46074131032;
native fixer and fresh independent reviewer, main unchanged, all automations paused.

Final result: full live repair acceptance completed and receipt persisted. Source fix27f71f5
passed independent native Opus/high review and source CI46075020097, then shown plan
d9ac1b08ea5746d1689ccbaed16a8daed46e4818c4afb01ff1b26e7a1c3d0067 applied.
Installed exact23files/245022bytes/version9; all8 automations paused,8 worker and6 MCP
bindings unchanged, production execution/broker false. No product pilot or merge.


## Installed-bundle red/fix/green acceptance

Current scope: execute the same full service cycle in Collegium, no local Delivery engine.
Fixed service-test manual entry, isolated service state/checkpoint namespace, strict event
ceiling and production flagsfalse. Existing native App gains only Actions run/job/log reads;
no write ceiling/credentials change. Bound compressed log evidence and verify raw hashes.
First prove read access without workers, then run bounded cloud slices manually while all
automations remain paused; collect native model/effort, actual initial red assertion, fixer,
fresh full validation/independent review and samePR green. Preserve all prior service proofs.
