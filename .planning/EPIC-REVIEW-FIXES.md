# Epic review resolution ledger

Both initial independent reviews remain in EPIC-REVIEW.md and EPIC-REVIEW-2.md.
Fixes have240 offline tests passing; final independent re-review is pending.

First pass:
- One captured base for all prerequisite proofs and child/integration revisions; no cached
  prerequisite state authorizes a new dispatch. Only the owning epic can advance children.
- Shared paginated filter=all exact-head CI/status normalization; waiting and CI deadlines.
- Foreign controller owners refused before effects; bounded trusted installed profile
  registry resolves each pending operation and checkpoint origin, including disabled pause.
- Terminal observed-only drain discards stale results, charges usage, releases safe claims.
- Atomic pause of waiting root/children; active claims remain until confirmed settlement.
- Actual aggregate/reserved budgets checked before new ticket/stage/integration dispatch.
- Packed archive required in pinned mode; canonical Jira IDs; ready replay avoids queue.
- Closed/replaced PR explicit blockage; truthful per-invocation launch receipts.

Second pass:
- Ineligible dependency/budget waiters become dormant rather than ghost FIFO contenders.
- Integration base/prerequisite loss enters terminal settlement even when it removes proofs.
- Definitive integrated protocol rejection blocks and drains; no repeated failed job loop.
- Broker no-effect disposition binds identity and latest intent sequence. It authorizes
  safe release/retry only before mutation, never hides a later unknown write.
- CheckpointError aborts the complete tick before unrelated actions overwrite unknown CAS
  receipts. Existing signed ack-adoption and no-blind-replay tests remain passing.
- Rejected native turns charge idempotent authoritative input/output/cache usage; partial
  usage charges at least the reservation/known lower bound. Drain shares the ledger.
- Adopted-journal emergency pause checkpoints without unrelated reconciliation success.
- Immutable ancestry search is resumable in32-read batches and prioritizes first parents;
  an incomplete proof waits rather than declaring absence. Positive results are cached.

No remote epic, pilot issue, merge, schedule resume, model/effort changes, or broader App
write grant has occurred. Source publication and installed-bundle preflight follow only
once final source review passes.

## Third-pass boundary fixes

- CR-01: one verified pending-launch identity distinguishes observation from first prompt
  submission. Ticket and integration admission gates both check resumed jobs; an exhausted
  budget preserves uncertain ownership and never submits the first paid prompt.
- CR-02: accepted/rejected/drained turns use the same authoritative four token counters.
  Missing/partial/invalid counters charge the reservation or known larger lower bound;
  accepted artifacts persist that charge exactly once.
- CR-03: integration head is pinned after capacity admission and a fresh ref check. Merely
  queued integrations may refresh to a new base after rechecking every prerequisite merge.
- CR-04: ready Delivery documents and managed claim holds now commit atomically. Legacy
  readiness with a stale active claim is recovered before active-work drift handling.

Targeted independent confirmation PASS: .planning/EPIC-REVIEW-3-RESOLVED.md; 131 focused tests plus independent reproductions. Full suite: 248 tests PASS.
