# Collegium pipeline bundle

The repository is the source of an installable bundle; the controller remains a deterministic program, packaged alongside its workers and the separate GitHub App writer. Build with `uv run python scripts/build_bundle.py`, then validate with `lap bundle validate .github/lap/collegium-pipeline`. The generated `lap.yaml` uses JSON syntax, which is valid YAML.

## Contents

- Eight Claude Code worker variants and one shared quality rule. Model/effort and private model-connection needs are explicit.
- `controller/src/collegium_pipeline/`: the actual controller modules, not a prompt pretending to orchestrate them.
- `controller/entry.py`: a script entry with preflight, admission, status and one-step delivery actions. Its SQLite journal and artifacts use `ARANARIUM_STATE_DIR`.
- A separate deterministic native App broker. Its scope file permits only the configured repository, base and file paths.
- Twelve MCP entries in the integration catalog with distinct DEV/PROD URLs and explicit connection IDs. Six authenticated entries are emitted as manifest needs and agent grants; six unresolved entries remain in the catalog.
- `claims.json`: claims for the existing eight agents and broker. The controller automation is new. A claim adopts an existing object; it does not duplicate it.

The GitHub repository grants directly reference the dedicated existing **App** connection ID. The platform's `github_connections` manifest needs currently describe personal tokens and reject an `access` level. We do not replace the App with a token just to fit that field. GitHub MCP is a separate read-only connection to the official remote server.

## Current integration state

`config/integrations.json` and `reports/mcp-connections.json` record project connection identities, authenticated tool discovery and exact tool ceilings. Six connections have completed OAuth and authenticated discovery:

| Need | Project connection | Read-only tools |
|---|---|---:|
| Atlassian | mcpc_6922425fd6a845f4b604a8663ab06385 | 8 |
| Grafana PROD | mcpc_e33ecc0ae7154059b9b17efe5e967331 | 38 |
| VictoriaMetrics PROD | mcpc_729b8150e4074b0f9164946e27998b40 | 16 |
| Backstage PROD | mcpc_948ef97eb40d41f5a0b25f1e0240937b | 2 |
| Agents Knowledge PROD | mcpc_27eec2a3866b4c26b04bba961bae9159 | 6 |
| Agents Knowledge DEV | mcpc_b692cbf768e14262a510f49b15337ded | 6 |

These authenticated connections replace the earlier uncredentialed staging IDs. Their platform ceilings and the bundle's `connections[].tools` both name explicit lists. The integration catalog records `tools: []` for unresolved needs. Collegium rejects an empty manifest toolset, while omitting it asks for all tools. The builder therefore emits only authenticated, nonempty explicit toolsets as manifest needs and agent grants; pending services remain outside those grants until discovery and a rebuild. The builder refuses inconsistent or implicit all-tools catalog entries. They are now attached to the eight installed workers; the post-install runtime calibrations are recorded separately. Discovery proves authorization and tool availability; successful backend data calls remain to verify after attachment.

GitHub MCP cannot start OAuth: the authorization server does not support dynamic client registration, and the registered server has no `client_id`. A configured OAuth client is required; the dedicated repository GitHub App already works independently. Langfuse requires project-scoped Basic authentication using its public/secret API-key pair; the owner must identify the PROD and DEV projects and enter credentials in the console, never in chat or source. The official [Langfuse MCP documentation](https://langfuse.com/docs/api-and-data-platform/features/mcp-server) describes this authentication.

DEV Grafana, Langfuse, VictoriaMetrics and Backstage return HTTP 502 from Collegium. Agents Knowledge DEV/PROD have separate authorized grants and identical six-tool read-only ceilings; neither environment substitutes for the other. No DEV service is substituted for PROD. No broader platform connection may replace the recorded project connection during installation.

## Installation and activation

1. Publish the bundle source to a review branch of this repository.
2. Finish connections in Collegium's project Connections page and discover their actual tools. Save explicit read-only lists and rebuild the bundle. This needs a person's sign-in; no token should be pasted into a chat or the repository.
3. Plan `lap bundle install --project <project> --repo <this repository> --path .github/lap/collegium-pipeline --ref <review branch> --connection <App connection>` with every mapping from `claims.json` as `--claim KEY=ID`. Read the exact plan and digest before applying it. The earlier plan automatically selected broad platform DEV connections and must not be applied unchanged.
4. Bind `claude-code-subscription` to the existing private project connection and each emitted MCP need to its recorded **project** connection with `--connection <connection_id>`. Review claimed-field choices: `drop` takes the bundle field, while the default `keep` preserves the live field. Verify MCP entries and tool lists in the resulting operations; do not assume a claim installs the bundle configuration. Only the controller and repository-free recovery store receive `PIPELINE_CONTROL_KEY`, a separate space-limited Collegium key stored at project level, distinct from the Claude token. Do not copy the host's personal CLI key into the cloud.
5. Apply the reviewed plan. Validate declared models, effort, harness, owner/project, repository grants, MCP tool ceilings and installed source; refresh controller bindings only against this applied plan. Recalibrate changed worker configurations. The controller settings shipped in this initial bundle intentionally disable execution/writes.
6. Verify a cloud preflight, persistent state and interrupted-run recovery before enabling a cloud service test. Continue the explicitly authorized PR → assertion failure → repair → green CI test; leave its PR unmerged.

The manifest requires a trigger even for a manually used script. All three automations therefore declare schedules **and start paused**. The broker permits such a configuration only with explicit `broker_allow_paused_triggers`, an exact digest pin and status `paused`; an active broker is rejected. No automation is resumed by the builder.

## Boundaries

This packages the implemented serial prototype. It does not complete epic scheduling, parallel execution or the investigation engine. Cloud activation also needs verified control credentials, post-install bindings and durable checkpoint behavior; a syntactically valid bundle does not prove those. The narrow built-in attempt API cannot supply all the authenticated runtime/configuration evidence required by this controller, so its attempt key is not substituted for a control API key.

The owner's initial service admission is retained in `.local/claude-service.sqlite3`, root `281c201a-b129-4a5d-96f8-6a03f1db5286`. It was interrupted after two native stages completed, before any broker mutation. Its known child identities must be reconciled before resuming; do not create replacements for an ambiguous launch.

Large native broker requests use an explicitly enabled zlib/base64 envelope. The native script verifies the original canonical digest and a bounded decompression size before any operation. This addresses Collegium's managed-event size limit without splitting a candidate across commits. Older uncompressed broker bindings remain separate.

## Installed control verification

The six-MCP bundle was installed from ecb584a with the owner's approved plan. Both automations remain paused. Installation changes worker configuration fingerprints and the broker's code fingerprint; the refreshed settings are derived only after verifying installed object identities, private Claude binding, model/effort and exact MCP connection/tool ceilings against that applied plan. Previous service admissions and calibration configurations remain historical; they are not rebound in place.

A manual `verify-control` event authenticates with only PIPELINE_CONTROL_KEY from the controller's Vault environment, reads the eight pinned worker configurations and native broker metadata, and checks exact project MCP identities/tool ceilings. It accepts no other event parameters and never starts an agent or broker run. `preflight` still checks presence only. An authenticated metadata check does not establish successful backend MCP data reads. Delivery remains disabled until its separate acceptance checks are complete.

A post-install native worker successfully called all six bound MCPs: Atlassian getAccessibleAtlassianResources; AK DEV and PROD list_workspaces; Grafana PROD list_datasources; VictoriaMetrics PROD query(vector(1)); Backstage PROD validate-entity with disposable YAML. No entity was saved. reports/mcp-connections.json records tool/result event identities and an observation digest, not backend data. Worker fingerprints ignore only provenance.commit/version source labels so syncing controller code cannot invalidate unchanged runtime configuration; installation identity, permissions, model, effort and all other fields remain pinned.


## Persistence and interrupted attempts

Collegium starts each automation attempt from its last adopted state snapshot. SQLite WAL
commits survive a normal failed process, but the platform discards the entire attempted
snapshot on cancellation or executor loss. Therefore local SQLite alone cannot guarantee
exactly-once external effects. The platform retries a lost executor from the old snapshot.

The cloud delivery entry point checks the platform's independent run history before any
worker or broker call. Only the first, currently running attempt is eligible. Every earlier
delivery since the last receipt must be accounted for by a receipt in the adopted snapshot,
which contains the same journal and artifact directory. Ordinary failures after the fence save a receipt in `finally`, so an adopted journal
can resume by observing existing effects. Disabled delivery is also recorded this way.
Failures before dispatch (including invalid run ID, missing key and transient history-read
failure) save a separate per-attempt `no-dispatch` record in the snapshot. A later fence
checks each attempt identity and skips only that harmless run, then continues checking older
runs; this record never establishes an anchor. A cancelled/lost attempt discards it too.
An unaccounted attempt with possible external effects blocks replay for reconciliation. An explicitly paginated history response, or a full history window (100 runs) without an anchor,
a mismatched automation/attempt, or unavailable history also blocks. The fence is paired with the independent
checkpoint service below. Never clear receipts or roll back state to bypass it. A legacy
lost attempt without an independent checkpoint remains blocked. Both execution switches remain disabled and all three automations stay paused.

Prepare admits event data directly, with no shared intake file. Repeated identical intake
returns the same run; changed acceptance/configuration requires explicit replan. Unique
SQLite keys and transactions also protect concurrent local admissions. Broker reconciliation
tests reopen the database after lost PR/commit responses and confirm a single external write.

The fixed manual `state-probe` action uses a separate diagnostic database and requires both
execution switches off. Modes: `commit`/`inspect` test a single admission/effect;
`crash` exits 75 inside an uncommitted SQLite transaction; `hold` first commits a disposable
attempt marker, then pauses 120 seconds inside another transaction for a real platform
cancellation. The next adopted snapshot must contain neither attempted write. `fenced-hold` and `fenced-check` exercise the same cloud fence in
a separate receipt namespace without agents or repository writes. Cancel the held run only
after `probe_ready` appears. A cancelled fenced probe remains intentionally quarantined;
it does not affect the product journal. No mode accepts arbitrary commands or enables delivery.


## Independent checkpoints and external reconciliation

The third bundle automation, `pipeline-recovery-store-v1`, is a paused script with no
repository, MCP or model grants. It shares only the controller's environment-delivered
`project/PIPELINE_CONTROL_KEY` reference, used in memory to authenticate checkpoint RPCs
and their responses with HMAC. No key value is put in events, state, artifacts or output.
Both scripts and the exact store owner/project/secret scope are pinned before use.

Cloud delivery saves a consistent SQLite backup and all verified content-addressed
artifacts before each tick, session creation, prompt submission and broker mutation.
The store's separate run must finish and adopt that checkpoint before the external effect
is called. Uploads use immutable 120 KB chunks, a digest and CAS on the previous head;
partial uploads cannot replace the committed head. Delivery and diagnostic namespaces are
separate. Bounds are 24 MB raw JSON and 8 MB compressed per checkpoint. Oversized state
or missing acknowledgement refuses the effect; no evidence is silently truncated. The
store retains two committed generations and one pending upload. The local head must match
the independent head before another tick; a late old writer cannot be silently overwritten.
A persisted pending-upload descriptor allows adoption of this controller's exact committed
checkpoint after a lost acknowledgement: parent, owner, attempt, configuration and operation
must match, and the journal must prove the effect never started (or a tick remained unchanged).
This advances only the local checkpoint head, preserves the newer journal and never dispatches.

`{"action":"reconcile"}` accepts no caller-selected checkpoint, task, paths or endpoints.
It reconciles an adopted journal or verifies the latest signed checkpoint's original closed
controller run/attempt and exact frozen configuration, imports into staging, checks SQLite
and artifact integrity, and then restores the original journal identities with an audit
receipt. Importing it twice is idempotent; the receipt must remain joined to the journal's
checkpoint event. A lost snapshot is imported before an older pending local job can be
mistaken for its state. Live delivery automatically tries this read-only reconciliation when
the history fence identifies an uncheckpointed attempt, and then checks the entire fence
again. Paused schedules are never resumed by recovery.

Agent session names derive from the recorded launch intent. Recovery checks exact agent,
project, runtime, harness, environment, frozen request and actual prompt trace/turn identity.
It never creates a replacement session while a previous creation is unknown. If a known
session's prompt needs continuation, delivery reuses the original Idempotency-Key and exact
request, which returns its existing turn or sends the first one once. A checkpoint failure
recorded before the external call is separate from an ambiguous response, so an adopted
journal may safely retry an action known never to have started.

Commit reconciliation retains the original expected parent, action marker and full tree
comparison. PR reconciliation checks repository IDs, branch, base/head and the original run
marker. It records the observed existing result; it never republishes an uncertain mutation.
Missing or ambiguous objects, changed configuration, an advancing checkpoint, incomplete
history or external branch/PR drift remain blocked. Reconciliation does not approve code,
accept CI, change model/effort, merge, release or deploy.

The fixed `recovery-probe` supports `connection`, `start`, `recover`, `inspect`, with both
execution switches disabled. `start` can launch one fixed private-Claude executor diagnostic,
checkpoint it, then hold for a real controller cancellation. It refuses a second worker
while a diagnostic checkpoint exists. `recover` restores that same session/turn in a separate
journal, without agents or GitHub writes; repeated recovery/inspect proves idempotence.
This is a service diagnostic, never a product pilot or acceptance shortcut.


## Live GitHub interruption diagnostic

The fixed `recovery-probe` modes `github-prepare`, `github-commit`, `github-pr`,
`github-recover`, `github-inspect` use the existing diagnostic namespace and preserve the
native-worker proof. No new connection, secret, automation or widened App scope is needed.
Production execution/broker switches must be false. The only service write is a fixed
passing fixture at the existing allowed `tests/test_live_service.py` path, on its canonical
run branch. No event-selected file, payload, root, repository or endpoint is accepted.

Prepare successfully adopts the fixed task and branch before either fault. Commit/PR mode
performs the real App mutation, then withholds its reply from PRBroker and emits
`probe_ready` before holding. Cancel the controller at that signal: GitHub and the independent
checkpoint survive, while the attempt's local receipt/RPC identities are discarded. Recover
uses the existing observation-only import, then the identical commit/PR mode can be run
again; a successful replay reports `mutation_calls: 0`. Inspect counts the service admission
and exposes its recorded receipts. No code is merged and no worker/pilot is started.
The service PR remains a reviewable diagnostic artifact.

After the GitHub probe advances the diagnostic checkpoint, use `github-recover` for that
head. Native `inspect` still selects its own original admission; native `recover` refuses a
broker checkpoint rather than importing it without a GitHub observer. Production checkpoints
remain in their separate delivery namespace.

## Correcting a failed validation command

The service repair command uses `env PYTHONPATH=src python3 -m unittest discover -s tests -v`
so a fresh source checkout can import this repository's package. A worker's `pass` cannot
override a nonzero exit code from the pinned command.

For an existing local run stopped at validation, `reconfigure-validation --apply` accepts
`--previous-config`, `--config`, `--journal`, `--artifacts`, `--run-id` and `--reason`.
It requires the original completed turn, verified runtime and pinned nonzero command
evidence. Only validation argv and token allowance may change. It preserves the failed
packet and configuration artifacts, accounts rejected usage, and atomically records the
correction before admitting a fresh validation attempt on the same candidate and PR.
Running, unknown or unobserved launches cannot be replaced. Task, scope, worker bindings,
credentials and CI requirements cannot change through this command. This is an explicit
operator correction, not automatic acceptance or an automatic budget increase.


## Manual installed-bundle CI repair diagnostic

On the paused installed controller, invoke `{"action":"service-test","mode":"preflight"}`
to prove actual native GitHub App access to an existing failing Actions job and bounded logs,
without launching a worker. `mode: "run"` runs the fixed one-file red/fix/green contract
using the normal Delivery engine entirely in Collegium. No event-selected task, payload,
model, command or scope is accepted. Global execution/broker settings must remain false.
The controller itself derives authority only for this fixed service diagnostic.

A cloud run works for a bounded eight-minute slice and emits `COLLEGIUM_SERVICE_RESULT`.
If still running, invoke the same manual input again after the previous run has ended;
state, stage decisions, workers, App writes, Actions observation and signed write-ahead
checkpoints remain in Collegium. `mode: "inspect"` reads the canonical admission without
launching workers or publishing. The service state/checkpoint namespace is isolated from
production delivery and prior interruption diagnostics. Lost attempts require the same
external reconciliation and replay fence as ordinary cloud delivery. Never resume schedules
or choose a product pilot to run this diagnostic.

CI job/run metadata and compressed logs are read through the native App broker with
repository/endpoint restrictions, bounded decoding and SHA-256 verification. The cloud
path has no host gh fallback, exported GitHub token or desktop state machine.

A manual RPC may return a queued item with no run id. Both checkpoint and App clients
track that exact item in run summaries, wait for its assigned run and retain the receipt
through observation failures. They never submit a replacement mutation. Checkpoint
responses still require the signed request/owner/namespace identity and a succeeded run.
Policy diagnostics stay outside SQLite so an unacknowledged tick snapshot can still be
adopted exactly. Runtime integration JSON omits only build-time bindings and role matrices;
the full source config, manifest, connection catalogue/status and tool ceilings are retained.
