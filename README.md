# Collegium Delivery Pipeline

Source and bundle repository: [serhii-nochevnyi/collegium-pipeline](https://github.com/serhii-nochevnyi/collegium-pipeline). No product pilot or Jira ticket has been selected.

The controller coordinates stage workers, model/effort policy, durable receipts, independent review and a separate GitHub App PR broker. It is packaged with its workers as a Collegium **Bundle**, whose source is [.github/lap/collegium-pipeline](.github/lap/collegium-pipeline). The current engine is a serial prototype; investigation, epic scheduling and parallel delivery remain planned slices.

Eight Claude Code variants use the owner's existing private `project/claude-code-subscription`. All eight passed live model/effort calibration, including Sonnet low/high/medium and Opus high/max; Claude also passed an exact private-repository checkout. Historical Codex profiles and reports are retained separately.

The bundle contains eight agents, a controller script, the App broker, a shared quality rule and an integration catalog for twelve MCP services: GitHub, Atlassian, plus DEV/PROD pairs of Grafana, Langfuse, VictoriaMetrics, Backstage and Agents Knowledge. Atlassian, Grafana PROD, VictoriaMetrics PROD, Backstage PROD and Agents Knowledge DEV/PROD completed authorization and authenticated discovery, with explicit read-only tool ceilings. Six authenticated MCP needs are included in the manifest; the remaining catalog entries are excluded from agent grants until connected. GitHub MCP needs OAuth client configuration; Langfuse needs project credentials; four DEV services return gateway errors. The six connections are attached to the eight installed workers; backend data reads remain to verify.

Both bundle automations start paused. Packaged execution and writes are disabled. No credential is stored in the bundle: Claude uses a model-connection binding; the cloud controller separately needs a project-scoped `PIPELINE_CONTROL_KEY` in the Vault. Existing agent/broker IDs have a claims map. Applying an installation can change their configuration digests, so activation requires fresh binding validation.

```sh
make check
uv run python scripts/build_bundle.py
lap bundle validate .github/lap/collegium-pipeline
```

The local suite has 113 tests. The bundle passed the platform's real local-folder validator. The service PR/red-to-green run is paused after planning/review while the bundle and integrations are prepared; no service PR has been created.

- [Specification](SPEC.md) and [implementation slices](docs/IMPLEMENTATION.md).
- [Claude workers and verified runtime evidence](docs/CLAUDE-WORKERS.md).
- [Bundle and integration status](docs/BUNDLE.md).
- [PR brokerage and repair](docs/DELIVERY.md).
- [Claude calibration report](reports/claude-workers.json), [checkout report](reports/claude-checkout.json), [MCP status](reports/mcp-connections.json).
- [Current state](.planning/STATE.md).

Remote Sessions is outside this project's scope. No merge, release or deployment is performed by this prototype.
