# Collegium Delivery Pipeline

Source and bundle repository: [serhii-nochevnyi/collegium-pipeline](https://github.com/serhii-nochevnyi/collegium-pipeline). No product pilot or Jira ticket has been selected.

The controller coordinates stage workers, model/effort policy, durable receipts, independent review and a separate GitHub App PR broker. It is packaged with its workers as a Collegium **Bundle**, whose source is [.github/lap/collegium-pipeline](.github/lap/collegium-pipeline). Separate lanes handle single tickets, dependency-aware epic delivery and read-only investigation with bounded parallel research.

Eight Claude Code variants use the owner's existing private `project/claude-code-subscription`. All eight passed live model/effort calibration, including Sonnet low/high/medium and Opus high/max; Claude also passed an exact private-repository checkout. Historical Codex profiles and reports are retained separately.

The bundle declares eighteen agents (eight delivery and ten investigation variants), eight paused scripts, separate checkpoint stores, quality rules and an integration catalog for twelve MCP services: GitHub, Atlassian, plus DEV/PROD pairs of Grafana, Langfuse, VictoriaMetrics, Backstage and Agents Knowledge. Atlassian, Grafana PROD, VictoriaMetrics PROD, Backstage PROD and Agents Knowledge DEV/PROD completed authorization and authenticated discovery, with explicit read-only tool ceilings. Six authenticated MCP needs are included in the manifest; the remaining catalog entries are excluded from agent grants until connected. GitHub MCP needs OAuth client configuration; Langfuse needs project credentials; four DEV services return gateway errors. The six connections are attached to the eight delivery workers; harmless read-only MCP tool calls succeeded for all six. Investigation registers Git and controller-captured MCP evidence with explicit DEV/PROD labels; its workers cite immutable snapshots and retain no direct MCP grants.

All bundle automations start paused. Packaged execution and writes are disabled. No credential is stored in the bundle: Claude uses a model-connection binding; cloud controllers and their repository-free checkpoint stores need a separate space-limited control key stored as `PIPELINE_CONTROL_KEY` in the project Vault. Existing agent/broker IDs have a claims map. Applying an installation can change their configuration digests, so activation requires fresh binding validation.

```sh
make check
uv run python scripts/build_bundle.py
lap bundle validate .github/lap/collegium-pipeline
```

The local suite includes snapshot-loss recovery, lost session/prompt/commit/PR responses and repeat-import tests. The bundle passed the platform's real local-folder validator. The service PR/red-to-green run is paused after planning/review while the bundle and integrations are prepared; no service PR has been created.

- [Specification](SPEC.md) and [implementation slices](docs/IMPLEMENTATION.md).
- [Claude workers and verified runtime evidence](docs/CLAUDE-WORKERS.md).
- [Bundle and integration status](docs/BUNDLE.md).
- [PR brokerage and repair](docs/DELIVERY.md).
- [Claude calibration report](reports/claude-workers.json), [checkout report](reports/claude-checkout.json), [MCP status](reports/mcp-connections.json).
- [Current state](.planning/STATE.md).

Remote Sessions is outside this project's scope. No merge, release or deployment is performed by this prototype.

## Epic DAG delivery

The bundle includes a shared-capacity epic scheduler over the existing ticket engine:
independent tickets may run concurrently, dependencies wait for verified prerequisite
merges, and combined validation/review/CI gate epic acceptance. The current strategy is
`direct_to_base` with human merges. See [epic protocol and configuration](docs/EPICS.md).
Automations and both execution profiles remain disabled/paused; no pilot is selected.
## Investigation bundle

The separate paused investigation lane scores complexity, selects immutable private
Claude model/effort variants, runs bounded parallel research and validates an ADR/ticket
proposal through independent review. See [docs/INVESTIGATE.md](docs/INVESTIGATE.md).

