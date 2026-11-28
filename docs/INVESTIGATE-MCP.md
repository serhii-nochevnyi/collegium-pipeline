# Investigation MCP evidence

The installed `pipeline-investigate` controller collects read-only MCP observations.
Its six connections pin exact project connection IDs, server IDs, HTTPS URLs and76
input-schema fingerprints in `config/investigation-mcp.json`. This catalog is separate
from historical execution settings; existing signed checkpoints and agent fingerprints
retain their configuration identity. Every new source binds the catalog digest.

| Connection | Evidence environment |
|---|---|
| atlassian-rovo (Jira and Confluence) | SHARED |
| ak-dev | DEV |
| ak-prod | PROD |
| grafana-prod | PROD |
| vmcluster-prod | PROD |
| backstage-prod | PROD |

SHARED identifies the Atlassian service, not the environment a ticket describes. A Jira
mention of PROD is not a measured PROD observation. Agents Knowledge environments name
the index queried; a document can discuss other environments. Review must distinguish
source provenance from what a document says. Explicit comparisons cite both environments.

The existing Grafana/VM/Backstage DEV endpoints and Langfuse DEV remain unavailable;
Langfuse PROD still needs project credentials, and GitHub MCP needs OAuth configuration.
They stay outside grants. No DEV/PROD or service substitution is performed.

## Capture and inspect

A normal `prepare` intake may add `mcp_sources`; `sources` may be empty when MCP is used.
Each MCP request supplies exactly these fields:

```json
{
  "connection": "ak-dev",
  "environment": "DEV",
  "tool": "list_workspaces",
  "arguments": {},
  "selector": "",
  "line_limit": 80,
  "max_age_seconds": 3600
}
```

`selector` is an RFC6901 JSON pointer into the returned value (`""` selects its root).
Text content blocks are decoded as JSON when valid, otherwise retained as text. Strings
render as their original lines; structured values render as canonical indented JSON.
The first `line_limit` lines form the explicit excerpt. Coverage records its total lines,
whether the excerpt covers the selected value, and that upstream completeness is not
asserted. Selecting a page/part never establishes that all backend data was retrieved.

A capture refuses unknown connections/tools, mismatched environments, missing/extra
argument fields, changed schemas, tool errors, missing selectors, nonfinite JSON,
responses above256KB and excerpts above16KB. The combined Git/MCP excerpt catalog is
limited to48KB; at most16 MCP requests and200 lines per excerpt are allowed. Choose
narrower server queries/selectors instead of silently truncating a response.

The controller checks its own paused automation grants and server URLs before and after
capture. It checks project connection and native tool schemas before using a connection.
Calls use platform-generated `lap_mcp` stubs and the native attempt key. There is no
personal-key or direct backend-credential fallback. Authentication errors never become
source facts. Upstream exception text is not printed as it can contain sensitive data.

Each full bounded result is stored as a content-addressed artifact in Collegium state,
with exact request, schema/catalog digests, connection identity, native automation/run/
attempt identity and capture interval. The source references that artifact and includes
response/argument digests, selected excerpt and expiry. These snapshots are not shipped
to the bundle's Git repository. Source status lists metadata/digests rather than payloads.

Use managed events on the installed investigation automation:

```json
{"action":"investigate","operation":"mcp-preflight"}
```

This verifies scope and live tool schemas without starting an agent or capturing a tool
result. To inspect one admitted excerpt without a paid turn:

```json
{"action":"investigate","operation":"evidence","run_id":"RUN_UUID","source_id":"SOURCE_DIGEST"}
```

`evidence` returns that source and its excerpt, not the full upstream response. It refuses
a source outside the selected run. Normal `prepare` captures the tool results; an identical
admitted intake reuses its frozen catalog before contacting MCP again. Changed requests
require an explicit new intake identity. Before admission, an interrupted read may be
repeated: it has no backend write or paid worker and no accepted evidence is replaced.

## Citation and decision gates

A fact referencing MCP must explicitly label its exact sorted environment set. Each
reference also labels the environment of its particular source:

```json
{
  "text": "A fact supported by the selected captured lines.",
  "environments": ["DEV"],
  "citations": [{"source_id":"SOURCE_DIGEST","start":2,"end":2,
    "quote":"exact captured line","environment":"DEV"}]
}
```

A comparison may use `environments:["DEV","PROD"]` only when its references actually
cover both. Missing/wrong/duplicate environment labels, altered quotes or absent source
IDs fail validation. Legacy Git-only citations retain their existing shape. Mechanical
checks verify identity, integrity, line bounds and labels; independent review assesses
whether evidence supports the interpretation, temporal claim and comparison.

The controller rechecks source artifacts before dispatch. Expired evidence blocks any
new worker and retains/drains original pending identities; explicit new intake is required
to refresh. Status exposes `evidence_fresh` and source expiry: `ready_for_decision` describes
acceptance at the recorded snapshot time, not an unlimited claim about current PROD.
Snapshots and their raw artifacts are included in the existing signed recovery journal.
Automation schedules and stored execution/write switches remain disabled. ADR/tickets
remain proposals; capture grants no Jira export, merge or deployment authority.
