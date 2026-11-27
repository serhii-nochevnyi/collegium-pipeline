# Platform evidence and open capability checks

Checked: 2026-11-27. Sources were read through the live Collegium Help application in Factum (`imported-jeep-9r`). The source links below are returned by that application. The Codex GitHub connector returned 404, but authenticated `gh` can access both repositories. Relevant session-launch, model-effort and agent-schema source files were subsequently inspected through `gh`; this is a targeted contract inspection, not a full source audit.

## Documented capabilities

| Capability | Finding | Source |
|---|---|---|
| CLI | Official installer supplies a checksummed macOS/Linux binary; `lap` manages configuration and reads/runs agents. | [CLI](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/cli.md) |
| Main MCP | Discover/run/observe/stop sessions; inspect activity; plan/apply bundle installation. Many configuration writes belong to CLI instead. | [MCP](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/mcp-from-claude-code.md) |
| Main MCP authentication | Personal key in `X-Api-Key`; authoritative server address is shown by the console's “Use from your IDE” page. | [MCP connection instructions](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/mcp-from-claude-code.md) |
| Agent configuration | Full agents carry runtime/environment/harness/model/effort configuration; sub-agent execution selects an agent. No per-call model override was established. | [Agents](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/agents.md), [platform tools](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/platform-tools.md) |
| Models | Model connections and provider model checks exist; support depends on runtime and connection. A name can be typed without proving it works. | [Model connections](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/model-connections.md) |
| Environment | Runtime/harness and sandbox capabilities must be selected and verified. | [Environments and runtimes](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/environments-and-runtimes.md) |
| Dispatch scripts | Script automations run code in a fresh sandbox without a model; a dispatcher may start due work. | [Automations](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/automations.md), [bundle script example](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/bundles.md) |
| Queue semantics | An automation has its own serial execution/queue limits. This is distinct from an application scheduler admitting multiple ticket jobs. | [Automations](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/automations.md) |
| Event limitations | GitHub App-originated events may not trigger the platform's GitHub automation. Durable periodic reconciliation is needed. | [Automations](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/automations.md) |
| Bundles | Git-versioned manifest, agents/skills/rules, requirements and scripts; installation plans have a digest; automations can start paused. | [Bundles](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/bundles.md) |
| Local validation | `lap bundle validate FOLDER` reads the folder and sends it to the platform for checking; it is not an offline-only linter and needs a personal key. | [Bundles](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/bundles.md) |
| Human boundaries | Approvals, new access and network policy changes have console-only operations. CLI/MCP cannot decide approvals for the person. | [MCP boundaries](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/mcp-from-claude-code.md), [CLI](https://github.com/airslate-common/litellm-acp-platform/blob/main/docs/help/cli.md) |
| Documentation access | Help tools `search_help`, `read_help_page`, `list_help_pages` are available through Factum. | [Collegium Help](https://factum.infrateam.xyz/collegium-help) |
| Codex MCP config | HTTP connections support URL, static/environment headers and a local header helper. OAuth login requires a server that supports OAuth. | [Official MCP reference](https://learn.chatgpt.com/docs/extend/mcp) |

## Unverified deployment prerequisites

The following deployment checklist includes verified local-readiness items and remaining production questions; readiness does not establish production support:

1. Verified for local readiness: personal space/project owner, runtime/environment and scoped connection IDs.
2. Verified in native sessions: Sol/high, Sol/low and Luna/medium; complete agent config digests are pinned. No provider-internal reasoning attestation is available.
3. Launch, turn, trace and event contracts are implemented. Session creation lacks the prompt idempotency contract; ambiguous writes/cancellation quarantine locally. Cloud-wide fencing is unimplemented.
4. Whether the selected runtime supplies isolation, repository credentials, required toolchains and artifact access for each worker.
5. Actual Jira tool/API permissions, epic hierarchy, dependency links, acceptance fields and transition IDs.
6. Repository scope/read access verified. Actual Contributor session launch fails without required non-bypassable main protections. Conditional production writes/merge remain unverified.
7. PostgreSQL and object storage availability, network routes, backup/restore and service identity.
8. Production script authentication to Collegium: how platform-supported workload credentials are obtained, scoped and rotated.
9. Direct documentation MCP OAuth is now verified: fresh Codex discovery lists all three help tools with `authStatus: oAuth`. Main MCP is configured using the console-reported endpoint and a private local header helper; an authenticated `list_spaces` read succeeded.

Do not deploy a live dispatcher until launch ambiguity, fencing and action brokerage have a tested implementation. A successful prompt, bundle syntax check or agent run alone does not prove scheduler correctness.

## Application design, not platform features

The following are proposed pipeline code: DAG scheduling, complexity classification, effort escalation, claim fencing, transactional outbox, durable recovery, exact-revision quality verdicts, epic integration and Jira status projection. PostgreSQL/Python and separate immutable role variants are design proposals. The CLI installation did not create these capabilities.

## Reference policy

The installed Shipyard policy was inspected as a local reference: `/Users/serhii/.codex/shipyard/scripts/model-policy-internal.cjs` and `runtime-adapters.cjs`. Its Sol/Luna role ladder informed the proposed model table. This project does not import Shipyard's hosts, receipts, ticket graph or active runs, and no formal Shipyard investigation gate has been claimed complete.

Context7 was attempted first for documentation lookup and returned a monthly quota error. Current vendor help, local CLI help and official OpenAI MCP documentation were used instead.

## Implementation-time findings

- The platform source uses `config.effort`, passed to the runtime as `metadata.effort`. It is not a guessed `reasoning_effort` key. See [agent reasoning](https://github.com/airslate-common/litellm-acp-platform/blob/main/services/litellm-acp/src/ui/src/lib/agent-reasoning.ts) and [runtime inputs](https://github.com/airslate-common/litellm-acp-platform/blob/main/services/litellm-acp/src/http/sessions/runtime_inputs.rs). Native tool-event evidence now also verifies Codex launch arguments for all six readiness roles; this does not expose provider-internal reasoning.
- [Session client source](https://github.com/airslate-common/litellm-acp-platform/blob/main/services/acp-mcp/src/lap/sessions.py) verifies `POST /session`, then `POST /session/{id}/prompt_async` with `Idempotency-Key`, and `GET /session/{id}/turns/{id}`. Session creation itself does not supply the same idempotency contract; a lost creation response must remain under reconciliation.
- Actual capabilities report aranarium 0.78.1, Codex 0.153.4 and base environment support. Codex must be requested explicitly because the runtime default is Claude Code.
- Native sessions ran `openai/gpt-6.2-sol` at low/high and `openai/gpt-6-luna` at medium. The cached model list alone did not establish availability.
- [Codex launch source](https://github.com/airslate-common/aranarium/blob/main/internal/adapter/codex/spec.go) passes model_reasoning_effort; [turn source](https://github.com/airslate-common/aranarium/blob/main/internal/adapter/codex/serve.go) forwards effort into turn/start. The pinned probe matches actual process arguments from authenticated platform tool events. See [native report](../reports/readiness.json).
- Actual write-token issuance requires active non-bypassable main protections: PR, at least one approving review, code-owner review, stale approval dismissal or last-push approval, no deletion and no force push. Connection installation checks can still pass when issuance is blocked.
- Gateway spend returns uncounted turns and zero listed USD. Actual dollar cost and USD budget enforcement are unavailable; token admission is not a hard turn cap.

## PR-broker contract follow-up

Read-only authenticated GitHub GraphQL schema introspection confirmed CreateCommitOnBranchInput.expectedHeadOid, CommittableBranch (repositoryNameWithOwner/branchName), FileChanges (additions/deletions), createCommitOnBranch, convertPullRequestToDraft and markPullRequestReadyForReview. The broker uses the expected-head mutation rather than treating REST force=false as compare-and-set. Official references: [GraphQL](https://docs.github.com/en/graphql/reference), [check runs](https://docs.github.com/en/rest/checks/runs), [PRs](https://docs.github.com/en/rest/pulls/pulls).

Eight version-3 workers with read-only repository grants were provisioned and configuration-pinned for the new serial delivery driver. Low/high/xhigh fixer routing and PR/CI recovery are verified through local API fixtures; these are not native effort proofs or real GitHub write/CI evidence. The broker requires a separate short-lived installation token scoped to one repository; automatic issuance/refresh from the Collegium connection has not been established. No permission workaround or PAT is used. Delivery remains disabled pending native validation.
