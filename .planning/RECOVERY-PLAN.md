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
