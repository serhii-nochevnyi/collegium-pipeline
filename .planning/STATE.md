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
