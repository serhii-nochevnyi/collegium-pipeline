# GitHub REST2026 merge metadata compatibility

Actual service PR7(A) and PR6(B) are closed/merged, at15:42:18Z and15:42:30Z.
Native App reads use2026-03-10 and omit merge_commit_sha; host gh's older API still returns
actual14c29e.../256a47... integration commits. This is the documented GitHub breaking change:
https://docs.github.com/en/rest/about-the-rest-api/breaking-changes?apiVersion=2026-03-10

Keep actual merged=true, closed lifecycle, merged_at, unchanged repo/branch/head and
independent accepted validation/review, exact-head green CI mandatory. If REST omits merge
SHA, prove accepted head is in selected base Git ancestry. Record merge_commit=null and
ancestry_proof=accepted_head, never fabricate the removed API value. Squash/rebase with no
accepted-head ancestry fails closed until a separate authoritative merge lookup is added.
An ancestry edge directly naming the target terminates traversal; no need to walk older
mainline history before examining the other parent.

Fixed service reconcile-merges only observes the recorded A/B metadata failures, verifies
signed isolated history, actual PR lifecycle +head ancestry+CI and unchanged base, and clears
those two local blocks without a new worker, commit or PR. C stays queued. A durable incident
marker makes replay idempotent and prevents later rewind. All ordinary bindings unchanged.
Inline review plus regressions cover successful absent-field ancestry, closed-unmerged PR,
missing accepted-head ancestry, retained malformed-field rejection and prior graph gates.
