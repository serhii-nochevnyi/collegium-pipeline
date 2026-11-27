# Local setup

Verified: 2026-11-27. CLI sign-in and both MCP configurations are complete. No further key or password needs to be pasted into chat.

## CLI and skill

- Official checksum-verified `lap v0.23.1`: `/Users/serhii/.local/bin/lap`, on PATH.
- Codex lap skill: `/Users/serhii/.agents/skills/lap/SKILL.md`.
- `lap whoami --json` confirms a valid person key and owner access in the personal space.
- A dedicated `collegium-pipeline` project was created; its IDs are in `config/pilot.json`.
- The project-scoped GitHub App connection lists only `airslate-common/agents-knowledge` at Contributor access. It is the project's default. A direct check passed.

## Main Collegium MCP

The authenticated console endpoint `/api/mcp-connect` reports `https://agentic-platform-mcp.infrateam.xyz/mcp`, header `X-Api-Key`, service reachable. Codex's user configuration now has a `collegium` entry pointing there.

Its `http_headers_helper` is `/Users/serhii/.local/share/collegium-pipeline/lap_mcp_headers.py`. The helper reads the existing server-specific private lap key and emits headers directly to Codex; the key is not copied into this project or Codex configuration. Its stdout is a credential: never execute it for display. The versioned source is `scripts/lap_mcp_headers.py`. The helper refuses a credential file that is not owned by the current user or is readable by other users.

Fresh Codex discovery found 27 tools. An actual `list_spaces` call also succeeded through the project's HTTP/MCP client. Custom-header authentication appears as `unknown` in Codex's OAuth-status field; this does not indicate failure. The successful authenticated read is the evidence.

## Documentation MCP

The `collegium-help` entry points to `https://factum-mcp.infrateam.xyz/mcp/apps/collegium-help`. OAuth credentials are present; fresh Codex discovery returns `search_help`, `read_help_page` and `list_help_pages` without a discovery error. Help was also read through the existing Factum app bridge.

Check either connection without calling a model:

```sh
python3 scripts/check_codex_mcp.py collegium
python3 scripts/check_codex_mcp.py collegium-help
```

These scripts start a temporary Codex app-server for discovery, then terminate that process group. They do not launch a model or a Collegium agent. New Codex sessions can discover the newly configured servers; the current chat's tool list need not update automatically.

## Development

```sh
make check
make doctor-readiness
make doctor
```

Python/package/tool versions are locked by `uv.lock`. See [prototype commands](PROTOTYPE.md) and [verification evidence](../.planning/VERIFICATION.md). The readiness doctor passes all six checks and returns exit 0 after a real five-stage worker/controller run. The delivery doctor remains blocked. A successful GitHub installation check does not prove write-token eligibility: actual Contributor session creation is blocked by required main protections.

## Next integration work

Six readiness role variants, native model/effort observation, artifact ingestion and five-stage controller wiring are complete. Product delivery repair/PR brokerage are implemented and fixture-tested; a broker installation credential, native write/CI verification and production coordination remain. See [delivery setup](DELIVERY.md). The owner deferred selecting the pilot task; do not request it as a prerequisite for infrastructure work. PostgreSQL and production action/claim coordination are required before multi-worker execution. No automations are enabled. Gateway USD pricing is unavailable, so cost limits are not yet enforceable.
