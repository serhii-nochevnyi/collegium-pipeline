# Epic delivery in the Collegium bundle

The epic coordinator reuses Delivery and NativeJobs for every ticket. A deterministic
single fenced dispatcher advances several tickets per tick; the native sessions run
asynchronously and concurrently in separate sandboxes. No Python threads share a checkout.
This is a durable single-controller design, not a distributed PostgreSQL scheduler.

## Dependency and acceptance contract

The implemented strategy is `direct_to_base`, with human merge authority. Independent
A/B may prepare separate fully validated/reviewed PRs concurrently. C waits until both
PRs are actually merged, still have accepted exact-head quality evidence, and their
merge commits are reachable from the current configured base. A green open PR does
not contain available dependency code. Ancestry checks use existing read-only App
permissions, without extending the broker's write paths or adding merge operations.

After every child merges, a fresh native validator and independent code reviewer inspect
the combined base revision. Actual required CI must pass on that same SHA. Only then
is the epic `ready_for_acceptance`, still `delivered=false`. No Jira Done, final epic PR,
automatic merge, rebase, release or deploy is implied. Integration-branch strategy is
explicitly rejected in this slice. Base drift during combined validation blocks and
requires an explicit replan; historical verdicts never attest the new revision.

## Claims, parallelism and recovery

`config/epic-policy.json` defines project/repository/epic active-ticket limits (default2),
100-ticket graph ceiling,6m token admission budget and1.5m integration reserve. Per-ticket
model/effort/budgets remain the existing immutable private-Claude role configuration.
Token reservations include active tickets' remaining allowance and final quality work;
actual usage can exceed admission estimates in the last admitted native turn, as in
single-ticket delivery. No enforced USD accounting is claimed.

Canonical Jira source/id/repository admission, DAG and claims are committed together.
A standalone request resolves to the same compatible run or an explicit ownership/config
conflict; it never creates a second delivery. Standalone and epic tickets use the same
claim registry. FIFO eligible admission and round-robin progress avoid newer requests
bypassing queued work. Each confirmed uncertain launch/action retains its claim until
reconciled; confirmed terminal stale turns are drained without accepting their results
and their observed usage remains charged. Accepted child PRs keep only resource ownership
until merge, releasing active-ticket capacity; there is no timeout-based ownership replacement.

Ticket path claims are enforced before publication, in addition to the App's unchanged
repository/path ceiling. Explicit disjoint paths and explicit resource lists (`[]` means
no shared contract) permit concurrency. Missing resource knowledge serializes the repository.
Shared schema/lockfiles/contracts should name a common resource. Failed children block
descendants while eligible siblings continue. Pause drains active tickets and stops new
ones; resume retains the graph/run/attempt identities. Configuration, graph or Jira
acceptance/dependency changes require an explicit paused replan, not silent rebinding.

The existing cloud history fence, CAS/HMAC independent checkpoint and uncertain-action
reconciliation now cover epic admission, claims, pauses, child jobs and integration.
All mutations use supported tick/session/prompt/broker checkpoint descriptors.

## Manual controller events

All automations remain paused. `Run now` can be used manually. No operation resumes
schedules, selects a pilot, creates Jira issues, or grants its own execution authority.

| Event | Result |
|---|---|
| `{"action":"epic","operation":"preflight"}` | Real read-only Atlassian connection check, flags and limits; no issue/model/admission |
| `{"action":"epic","operation":"prepare","graph":{...}}` | Atomically admit a validated explicit exported graph, without execution |
| `{"action":"epic","operation":"import-jira","key":"PROJECT-123"}` | Read/paginate configured Jira epic and children into that graph |
| `{"action":"epic","operation":"status","run_id":"..."}` | Compact dependencies, child states and combined quality state |
| `{"action":"epic","operation":"tick","run_id":"...","live":true}` | One bounded tick, only when installed execution AND broker flags are enabled |
| `{"action":"epic","operation":"pause","run_id":"..."}` | Stop new ticket starts, retain active ownership |
| `{"action":"epic","operation":"resume","run_id":"..."}` | Revalidate/reconcile and clear the graph pause; global flags still apply |

Graph shape:

```json
{
  "schema_version": "epic/v1",
  "version": 1,
  "strategy": "direct_to_base",
  "epic": {"source":"jira","source_id":"10000","repository":"OWNER/REPO","title":"Epic","requirements":"Acceptance"},
  "tickets": [{
    "key":"PROJECT-124",
    "task":{"source":"jira","source_id":"10001","repository":"OWNER/REPO","title":"Ticket","requirements":"Acceptance"},
    "depends_on":[], "paths":["src/component/"], "resources":[]
  }]
}
```

Jira source IDs are canonical immutable positive decimal IDs; keys and ID aliases are
rejected. A graph is immutable version1; changing it fails with a replan requirement. Empty,
cyclic, duplicate, unknown-parent and cross-repository graphs are refused before admission.
Do not use these illustrative identifiers as a pilot.

## Jira and installation settings

The script now has the existing `atlassian-rovo` read-only connection. It calls native
`lap_mcp` stubs, not host credentials. Schemas were discovered from the actual project:
`getJiraIssue(cloudId,issueIdOrKey,...)` and `searchJiraIssuesUsingJql(cloudId,jql,...)`.
Both explicitly request full views and lossless HTML bodies; truncated/repeating page
results fail. Directed `inwardIssue` links of the configured blocks type are prerequisites.
References outside the imported graph fail rather than silently discard dependencies.

Jira site/type/link mapping is deliberately `null`: no product epic was selected. Before
an eventual pilot, configure `epic.jira` with `cloud_id`, `epic_type_id`,
`blocks_link_type_id`, and optional `epic.scopes[ISSUE_KEY]` path/resource declarations.
The selected repository/path ceiling must separately cover the intended work. The current
installed App ceiling remains the existing service fixture; it is not silently widened.

The builder emits a separate disabled `controller/epic-settings.json`. It preserves the
historical service profile byte-for-byte. Preparation pins the intended runnable contract
while actual installed enable switches stay off; turning those switches on later does not
rewrite already admitted acceptance/model/budget policy. Every tick still checks both
installed switches before doing anything. Signed checkpoints use the intended contract.
A bounded registry of the two installed profiles and their intended variants resolves
each pending effect and checkpoint origin by its frozen digest; unknown profiles or
foreign controller owners fail before effects. Existing readiness rechecks never acquire
new work capacity, and pending integrated CI waits up to the configured CI deadline.
Prerequisites are refreshed together against one immutable base snapshot before admission;
a standalone call cannot advance an epic-managed child.

Python modules are bundled in deterministic `runtime.b64`, checked by an entry-pinned
SHA256, bounded ZIP member/size/CRC validation, and zipimport without extraction or network
download. Readable source mirrors and source-index hashes remain in the source bundle.
Only the archive, entry and settings are installed as code.files, below the platform cap.

## Verification boundary

Tests use the real Delivery/NativeJobs adapters with stateful fake remote APIs: concurrent
A/B running turns, C merge gating, full three-ticket+combined quality lifecycle, no-effect
replay, resource serialization, singleton sharing, competing SQLite connections, failure
propagation, budget reserve, pause/restart, signed snapshot restore, Jira pagination and
injection refusal, disabled cloud admission/ticks, and isolated archive import/tamper refusal.
Real cloud preflight verifies the installed archive/MCP grant without a product task. A live
paid parallel epic delivery is intentionally deferred until the owner chooses its pilot.

### Verified recovery refinements

Known-unstarted broker calls have identity/attempt-bound dispositions; a later unknown
mutation cannot reuse an old no-op receipt. A checkpoint refusal aborts the whole tick
before another ticket can overwrite its uncertain CAS receipt. Emergency pause on an
adopted journal does not depend on unrelated unknown launches becoming observable.

Rejected native work still consumes budget. Input/output and documented cache counters
are charged once per turn; absent/incomplete usage charges at least the full reservation
and any known higher lower bound. Long immutable commit ancestry is checked in resumable
32-read batches, so a read limit is pending evidence rather than a missing dependency.

Admission checks also apply when recovery resumes an unstarted intent or an existing
session awaiting its first prompt. Only a confirmed immutable session/turn can be polled
without fresh token admission. Missing or partial usage charges a conservative reservation
for accepted and discarded turns alike. Integration waiting for capacity has no pinned
revision yet; it rechecks dependencies against a refreshed base before starting work.
A ready child and its resource-only claim transition commit atomically, with recovery
support for older documents saved before that claim transition.
