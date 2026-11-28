"""Controller-owned, attempt-scoped read-only MCP evidence; never accepts caller snapshots."""

import json
import re
import time
from urllib.parse import quote, urlsplit

from .domain import PolicyError, digest

ENVIRONMENTS = {
    "atlassian-rovo": "SHARED",
    "ak-dev": "DEV",
    "ak-prod": "PROD",
    "grafana-prod": "PROD",
    "vmcluster-prod": "PROD",
    "backstage-prod": "PROD",
}
REQUEST_FIELDS = {
    "connection",
    "environment",
    "tool",
    "arguments",
    "selector",
    "line_limit",
    "max_age_seconds",
}


def encoded(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise PolicyError("MCP evidence must be finite bounded JSON") from exc


def validate_catalog(catalog):
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"schema_version", "sources", "unavailable"}
        or catalog["schema_version"] != "investigation-mcp/v1"
    ):
        raise PolicyError("Invalid MCP evidence catalog")
    if set(catalog["sources"]) != set(ENVIRONMENTS):
        raise PolicyError("MCP evidence requires the six reviewed connection identities")
    for name, row in catalog["sources"].items():
        if (
            set(row) != {"connection_id", "server_id", "url", "environment", "tools"}
            or row["environment"] != ENVIRONMENTS[name]
            or not row["tools"]
            or not row["connection_id"].startswith("mcpc_")
            or not row["server_id"].startswith("mcp_")
            or urlsplit(row["url"]).scheme != "https"
            or any(not isinstance(v, str) or len(v) != 64 for v in row["tools"].values())
        ):
            raise PolicyError("MCP identity, environment or tool schema pin differs")


def requests_checked(requests, catalog):
    validate_catalog(catalog)
    if not isinstance(requests, list) or not 1 <= len(requests) <= 16:
        raise PolicyError("Capture 1..16 explicit MCP observations")
    if len(encoded(requests)) > 16000:
        raise PolicyError("MCP requests exceed 16KB")
    seen = set()
    for request in requests:
        if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
            raise PolicyError(
                "MCP request fields differ; snapshots/URLs/credentials are not intake"
            )
        if any(not isinstance(request[k], str) for k in ("connection", "environment", "tool")):
            raise PolicyError("MCP connection, environment and tool must be explicit names")
        row = catalog["sources"].get(request["connection"])
        if not row or request["environment"] != row["environment"]:
            raise PolicyError(
                "MCP connection environment differs or is unavailable; no substitution"
            )
        if request["tool"] not in row["tools"]:
            raise PolicyError("MCP tool is outside the reviewed read-only ceiling")
        if (
            not isinstance(request["arguments"], dict)
            or not isinstance(request["selector"], str)
            or len(request["selector"]) > 1000
            or (request["selector"] and not request["selector"].startswith("/"))
            or re.search(r"~(?![01])", request["selector"])
            or type(request["line_limit"]) is not int
            or not 1 <= request["line_limit"] <= 200
            or type(request["max_age_seconds"]) is not int
            or not 60 <= request["max_age_seconds"] <= 86400
        ):
            raise PolicyError("Invalid MCP selector, line bound or freshness")
        key = digest(request)
        if key in seen:
            raise PolicyError("Duplicate MCP observation request")
        seen.add(key)
    return requests


def normalized(value):
    if isinstance(value, dict) and (
        value.get("isError")
        or value.get("error")
        or (
            isinstance(value.get("status"), str)
            and value["status"] in {"error", "failed", "failure"}
        )
    ):
        raise PolicyError("MCP returned an error, not evidence")
    if (
        isinstance(value, list)
        and value
        and all(isinstance(x, dict) and x.get("type") == "text" for x in value)
    ):
        text = "\n".join(x["text"] for x in value)
        try:
            return normalized(json.loads(text))
        except ValueError:
            return text
    return value


def select(value, pointer):
    for raw in pointer.split("/")[1:] if pointer else []:
        # RFC6901, without URI fragments, negative indexes or silent defaults.
        if any(
            raw[i] == "~" and (i + 1 == len(raw) or raw[i + 1] not in "01") for i in range(len(raw))
        ):
            raise PolicyError("Invalid JSON pointer escape")
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif (
            isinstance(value, list)
            and key.isdigit()
            and str(int(key)) == key
            and int(key) < len(value)
        ):
            value = value[int(key)]
        else:
            raise PolicyError("MCP selector is absent; no invented or truncated evidence")
    return value


def source_from_snapshot(snapshot, artifact, head, repository_id):
    request = snapshot["request"]
    value = select(normalized(snapshot["response"]), request["selector"])
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    )
    lines = text.splitlines()
    if not lines or not text.strip():
        raise PolicyError("MCP selected evidence is empty")
    excerpt = "\n".join(lines[: request["line_limit"]])
    if len(excerpt.encode()) > 16000:
        raise PolicyError("MCP excerpt exceeds 16KB; choose a narrower selector")
    row = {
        "kind": "mcp",
        "head": head,
        "repository_id": repository_id,
        "path": "mcp://" + request["connection"] + "/" + request["tool"],
        "start": 1,
        "end": min(len(lines), request["line_limit"]),
        "text": excerpt,
        "sha256": digest(value),
        "snapshot_digest": artifact,
        "response_digest": digest(snapshot["response"]),
        "request_digest": digest(request),
        "connection": request["connection"],
        "environment": snapshot["connection"]["environment"],
        "connection_id": snapshot["connection"]["connection_id"],
        "server_id": snapshot["connection"]["server_id"],
        "server_url": snapshot["connection"]["url"],
        "tool": request["tool"],
        "arguments_digest": digest(request["arguments"]),
        "selector": request["selector"],
        "catalog_digest": snapshot["catalog_digest"],
        "schema_digest": snapshot["schema_digest"],
        "captured_at": snapshot["captured_at"],
        "capture_started_at": snapshot["capture_started_at"],
        "expires_at": snapshot["captured_at"] + request["max_age_seconds"],
        "native_identity": snapshot["native_identity"],
        "coverage": {
            "selected_lines": len(lines),
            "excerpt_complete": len(lines) <= request["line_limit"],
            "selector_is_root": not request["selector"],
            "upstream_completeness": "not_asserted",
        },
    }
    return {"id": digest(row), **row}


def verify_snapshot(source, artifacts):
    snapshot = artifacts.get(source["snapshot_digest"])
    if (
        snapshot.get("schema_version") != "mcp-snapshot/v1"
        or source_from_snapshot(
            snapshot, source["snapshot_digest"], source["head"], source["repository_id"]
        )
        != source
    ):
        raise PolicyError("MCP evidence no longer matches its immutable native snapshot")
    return source


class McpSources:
    def __init__(
        self, config, catalog, http, environ, identity, artifacts, *, connect=None, clock=time.time
    ):
        validate_catalog(catalog)
        self.config, self.catalog, self.http = config, catalog, http
        self.environ, self.identity, self.artifacts = environ, identity, artifacts
        self.connect, self.clock, self.verified = connect, clock, {}

    def scope(self):
        row, _ = self.http.request("GET", "/api/automations/" + self.identity["automation_id"])
        if row.get("status") != "paused" or row.get("project_id") != self.config["project_id"]:
            raise PolicyError("MCP capture requires its paused project controller")
        entries = row.get("target", {}).get("mcp_servers", [])
        expected = self.catalog["sources"]
        if len(entries) != len(expected) or {x.get("name") for x in entries} != set(expected):
            raise PolicyError("Installed investigation MCP grants differ from catalog")
        for entry in entries:
            pinned = expected[entry["name"]]
            if (
                entry.get("connection") != pinned["connection_id"]
                or entry.get("level") != "project"
                or set(entry.get("tools", [])) != set(pinned["tools"])
            ):
                raise PolicyError("MCP grant connection or read-only tool ceiling drifted")
        hub, _ = self.http.request("GET", "/public/mcp_hub")
        for name, pinned in expected.items():
            rows = [x for x in hub["data"] if x.get("server_id") == pinned["server_id"]]
            if (
                len(rows) != 1
                or rows[0].get("server_name") != name
                or rows[0].get("url") != pinned["url"]
            ):
                raise PolicyError("MCP server URL/identity drifted; DEV/PROD cannot substitute")
        return {
            "connections_verified": len(entries),
            "unavailable": self.catalog["unavailable"],
            "agent_started": False,
            "automation_resumed": False,
        }

    def connection(self, name):
        if name in self.verified:
            return self.verified[name]
        if (
            self.environ.get("LAP_ATTEMPT_ID") != self.identity["attempt_id"]
            or not self.environ.get("LAP_ATTEMPT_KEY")
            or not self.environ.get("LAP_API_URL")
        ):
            raise PolicyError(
                "MCP capture requires native attempt credentials; no personal-key fallback"
            )
        meta, _ = self.http.request(
            "GET",
            "/api/mcp-stubs/"
            + quote(name, safe="")
            + "/tools?project_id="
            + quote(self.config["project_id"], safe="")
            + "&connection="
            + self.catalog["sources"][name]["connection_id"],
        )
        pinned = self.catalog["sources"][name]
        if (
            meta.get("connection", {}).get("id") != pinned["connection_id"]
            or meta.get("connection", {}).get("level") != "project"
            or meta.get("server") != {"id": pinned["server_id"], "name": name}
        ):
            raise PolicyError("MCP discovery resolved a different connection")
        if self.connect is None:
            from lap_mcp import connection

            self.connect = connection
        client = self.connect(name)
        actual = {t["name"]: t.get("inputSchema", t.get("input_schema")) for t in client.tools()}
        if any(
            tool not in actual or digest(actual[tool]) != fingerprint
            for tool, fingerprint in pinned["tools"].items()
        ):
            raise PolicyError("Native MCP tool schema changed; review catalog before capture")
        self.verified[name] = client, actual
        return client, actual

    def capture(self, head, requests):
        requests_checked(requests, self.catalog)  # Check every request before any network call.
        self.scope()
        sources = []
        for request in requests:
            try:
                client, schemas = self.connection(request["connection"])
                schema, args = schemas[request["tool"]], request["arguments"]
                if set(schema.get("required", [])) - set(args) or (
                    schema.get("additionalProperties") is not True
                    and set(args) - set(schema.get("properties", {}))
                ):
                    raise PolicyError("MCP arguments omit required or add unapproved schema fields")
                started = int(self.clock())
                value = client.call(request["tool"], **args)
                captured = int(self.clock())
                if len(encoded(value)) > 256000:
                    raise PolicyError("MCP response exceeds 256KB; it cannot be silently truncated")
                normalized(value)
                snapshot = {
                    "schema_version": "mcp-snapshot/v1",
                    "connection": self.catalog["sources"][request["connection"]],
                    "request": request,
                    "catalog_digest": digest(self.catalog),
                    "schema_digest": self.catalog["sources"][request["connection"]]["tools"][
                        request["tool"]
                    ],
                    "native_identity": self.identity,
                    "captured_at": captured,
                    "capture_started_at": started,
                    "response": value,
                }
                identity = self.artifacts.put(snapshot)
                source = source_from_snapshot(
                    snapshot, identity, head, self.config["repository_id"]
                )
                if self.clock() >= source["expires_at"]:
                    raise PolicyError("MCP evidence expired during capture")
                sources.append(source)
            except PolicyError:
                raise
            except Exception as exc:
                # Upstream errors may embed sensitive backend output. They are never facts.
                raise PolicyError(
                    "MCP read failed for "
                    + request["connection"]
                    + "/"
                    + request["tool"]
                    + " ("
                    + type(exc).__name__
                    + "); no evidence admitted"
                ) from None
        self.scope()
        return sources
