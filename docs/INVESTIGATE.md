# Investigate in the Collegium bundle

`pipeline-investigate` is a separate, manually invoked, paused script. It shares the
verified native worker protocol with delivery, but has a read-only GitHub grant, no
mutation broker and its own journal, artifacts and signed checkpoint automation.
Stored `execution_enabled` and `broker_enabled` remain false. Only an explicit
manual `tick` grants read-only agent execution for that attempt.

The sequence is assessment → four research perspectives → synthesis → independent
review. Perspectives cover the current system, alternatives, constraints and risks;
at most two native turns are pending in this lane. This is not a shared cross-lane
capacity guarantee. No investigation stage runs delivery or exports Jira tickets.

## Complexity and private Claude variants

An assessor scores scope, uncertainty, contracts, security, persistence and concurrency
from 0 to 3 with registered citations. Sum thresholds are 0–3 simple, 4–8 standard,
9–14 complex and 15–18 critical. Configuration supplies a minimum complexity.
Security/data-migration intake flags force critical; public-API/concurrency/unknowns
flags force complex. Dimension scores of at least 2 force critical for security or
persistence, complex for contracts/concurrency/uncertainty. Confidence below 0.6
forces at least complex. The resolved score, floors and routing reason are retained.

| Stage | Simple | Standard | Complex | Critical |
|---|---|---|---|---|
| Assessment | Sonnet low | Sonnet low | Sonnet low | Sonnet low |
| Research | Sonnet low | Sonnet high | Opus high | Opus max |
| Synthesis | Sonnet high | Opus high | Opus high | Opus max |
| Independent review | Opus high | Opus high | Opus high | Opus max |

All ten role/model/effort variants pin the owner's private Claude connection. The
controller checks the full agent configuration before dispatch. Acceptance requires
authenticated native session/turn identity, actual process arguments and supported
effort, served model, exact prompt, pinned checkout and terminal usage evidence.
Configuration alone does not prove runtime effort. The proof concerns the harness
configuration and served model; it does not measure private model reasoning.

## Intake and manual operations

Run the installed `pipeline-investigate` script with managed event `data`:

```json
{"action":"investigate","operation":"preflight"}
```

`prepare` accepts exactly `action`, `operation` and `intake`. Intake contains:

```json
{
  "task": {"source":"text","source_id":"unique-investigation-id",
    "repository":"serhii-nochevnyi/collegium-pipeline",
    "title":"Question to investigate","requirements":"Required evidence and outcome"},
  "head":"EXACT_40_CHARACTER_COMMIT_SHA",
  "sources":[{"path":"README.md","start":1,"end":20}],
  "risk_flags":[],
  "constraints":["Read-only investigation; ADR and tickets remain proposals"]
}
```

`status`, `pause`, `resume` and `repair` accept exactly `action`, `operation`, `run_id`.
`tick` additionally requires `live:true`. Each tick observes existing turns and may
start the next eligible stages. Pausing drains existing completed work without
starting or replacing turns. Resume preserves those identities. This run-level
pause is distinct from the automation's paused schedule, which remains unchanged.
`repair` never starts an agent. It can reopen only one independently revalidated,
invalid terminal payload in a blocked run, with every external turn settled. It retains
the same intake, head, accepted research, native receipts and retry budgets. Unknown
launches, invalid native envelopes and stale reviewer identities cannot be reset this way.

Prepare is idempotent for identical task/config/head/source snapshots. A changed
admission requires an explicit new identity; it cannot alter an existing run. Signed
write-ahead checkpoints precede session creation and prompt submission. Ambiguous
external outcomes reconcile to their original native identities or block; they never
silently create replacement agents. Cancelled-controller snapshots recover through
the separate checkpoint automation. No commit or PR capability is exposed here.

## Evidence and quality gates

The controller independently captures regular UTF-8 Git blobs at the admitted SHA,
checking repository ID, path ceiling, mode, size and line bounds. Facts cite registered
source IDs, exact line ranges and matching quotes. Citation existence is mechanical;
whether a quote supports the interpretation is checked by the independent reviewer.
The controller also registers native MCP snapshots from the six reviewed connections:
Atlassian (Jira/Confluence), Agents Knowledge DEV/PROD, Grafana PROD, VictoriaMetrics
PROD and Backstage PROD. Workers cite the captured catalog and have no direct MCP
grants. See [MCP evidence protocol](INVESTIGATE-MCP.md) for intake, provenance,
freshness, DEV/PROD labels, scope checks and unavailable connections. Uncaptured
external claims remain assumptions or open questions.

Synthesis must compare at least two alternatives, recommend one, identify sourced
risks, preserve open questions, propose an ADR and propose an acyclic ticket graph.
Paths and validation commands stay within configured ceilings. Review binds the exact
synthesis and four research artifact digests and checks coverage, sources, uncertainty,
alternatives, risks and decomposition. Rejected synthesis payloads (including altered
commands or invalid citations) and failed reviews share at most two synthesis/review
repairs, with the exact rejected artifact and controller findings retained. Research is
reused, paid usage is retained and configured commands never change. Invalid native
envelopes or stale review identities block; exhausting repairs also blocks.
Assessment and each research perspective also receive at most two payload corrections,
within the global job/token budgets. Quote errors report the exact captured line to
correct the response; the citation validator itself remains strict. Only the rejected
perspective is repeated, so already-running sibling packets remain immutable.

Success ends at `ready_for_decision`, or `needs_input` when any blocking question
remains. Both return `decision_approved:false` and `delivered:false`. Human acceptance,
Jira export and delivery admission are separate future actions. Defaults allow 16 jobs,
300 seconds per stage and 2 million observed tokens; an admitted turn may exceed the
token threshold. There is no hard USD/provider token cap. Paid rejected terminal
results are counted once and unresolved turns retain ownership.
