# Collegium pipeline bundle

The repository is the source of an installable bundle; the controller remains a deterministic program, packaged alongside its workers and the separate GitHub App writer. Build with `uv run python scripts/build_bundle.py`, then validate with `lap bundle validate .github/lap/collegium-pipeline`. The generated `lap.yaml` uses JSON syntax, which is valid YAML.

## Contents

- Eight Claude Code worker variants and one shared quality rule. Model/effort and private model-connection needs are explicit.
- `controller/src/collegium_pipeline/`: the actual controller modules, not a prompt pretending to orchestrate them.
- `controller/entry.py`: a script entry with preflight, admission, status and one-step delivery actions. Its SQLite journal and artifacts use `ARANARIUM_STATE_DIR`.
- A separate deterministic native App broker. Its scope file permits only the configured repository, base and file paths.
- Twelve MCP requirements with distinct DEV/PROD URLs and explicit connection IDs in the integration catalog.
- `claims.json`: claims for the existing eight agents and broker. The controller automation is new. A claim adopts an existing object; it does not duplicate it.

The GitHub repository grants directly reference the dedicated existing **App** connection ID. The platform's `github_connections` manifest needs currently describe personal tokens and reject an `access` level. We do not replace the App with a token just to fit that field. GitHub MCP is a separate read-only connection to the official remote server.

## Current integration state

`config/integrations.json` and `reports/mcp-connections.json` record the actual project connection IDs and probe results. GitHub MCP was registered in this project; eleven connections to existing registered servers were also created. No tools are permitted on these staged connections until authenticated discovery establishes a concrete read-only allowlist. They have not been silently attached to the previously calibrated live agents.

PROD Grafana, Langfuse, VictoriaMetrics, Backstage and Agents Knowledge returned `mcp_authorization_required`. Atlassian also needs authorization. DEV Grafana, Langfuse, VictoriaMetrics and Backstage returned HTTP 502; Agents Knowledge DEV needs authorization. GitHub MCP needs its own sign-in. A desktop-app connector's sign-in is not a Collegium connection's credential. No DEV service is substituted for PROD.

## Installation and activation

1. Publish the bundle source to a review branch of this repository.
2. Finish connections in Collegium's project Connections page and discover their actual tools. Save explicit read-only lists and rebuild the bundle. This needs a person's sign-in; no token should be pasted into a chat or the repository.
3. Plan `lap bundle install --project <project> --repo <this repository> --path .github/lap/collegium-pipeline --ref <review branch> --connection <App connection>` with every mapping from `claims.json` as `--claim KEY=ID`. Read the exact plan and digest before applying it.
4. Bind `claude-code-subscription` to the existing private project connection and each MCP need to its recorded connection. Only the controller receives `PIPELINE_CONTROL_KEY`, a project-scoped platform-control key distinct from the Claude token. Do not copy the host's personal CLI key into the cloud.
5. Apply the reviewed plan. Validate declared models, effort, harness, owner/project, repository grants, MCP tool ceilings and installed source; refresh controller bindings only against this applied plan. Recalibrate changed worker configurations. The controller settings shipped in this initial bundle intentionally disable execution/writes.
6. Verify a cloud preflight, persistent state and interrupted-run recovery before enabling a cloud service test. Continue the explicitly authorized PR → assertion failure → repair → green CI test; leave its PR unmerged.

The manifest requires a trigger even for a manually used script. Both automations therefore declare schedules **and start paused**. The broker permits such a configuration only with explicit `broker_allow_paused_triggers`, an exact digest pin and status `paused`; an active broker is rejected. No automation is resumed by the builder.

## Boundaries

This packages the implemented serial prototype. It does not complete epic scheduling, parallel execution or the investigation engine. Cloud activation also needs verified control credentials, post-install bindings and durable checkpoint behavior; a syntactically valid bundle does not prove those. The narrow built-in attempt API cannot supply all the authenticated runtime/configuration evidence required by this controller, so its attempt key is not substituted for a control API key.

The owner's initial service admission is retained in `.local/claude-service.sqlite3`, root `281c201a-b129-4a5d-96f8-6a03f1db5286`. It was interrupted after two native stages completed, before any broker mutation. Its known child identities must be reconciled before resuming; do not create replacements for an ambiguous launch.

Large native broker requests use an explicitly enabled zlib/base64 envelope. The native script verifies the original canonical digest and a bounded decompression size before any operation. This addresses Collegium's managed-event size limit without splitting a candidate across commits. Older uncompressed broker bindings remain separate.
