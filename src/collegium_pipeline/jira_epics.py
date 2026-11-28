"""Read-only paginated Jira epic intake through Collegium's pinned MCP stub."""

import json
import re
from dataclasses import asdict

from .adapters import jira_snapshot
from .domain import PolicyError
from .epics import graph_checked


def mcp_value(value):
    if isinstance(value, dict) and value.get("isError"):
        raise PolicyError("Jira MCP returned an error")
    if isinstance(value, dict) and "content" in value:
        value = value.get("structuredContent") or value["content"]
    if isinstance(value, list) and all(
        isinstance(x, dict) and x.get("type") == "text" for x in value
    ):
        text = "".join(x.get("text", "") for x in value if x.get("type") == "text")
        try:
            value = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise PolicyError("Jira returned no structured JSON") from exc
    if isinstance(value, dict) and "data" in value:
        if not isinstance(value["data"], dict) or any(
            k in value for k in ("id", "key", "fields", "issues", "resources")
        ):
            raise PolicyError("Ambiguous Jira MCP data envelope")
        value = value["data"]
    return value


def result_object(value):
    value = mcp_value(value)
    if not isinstance(value, dict):
        raise PolicyError("Unexpected Jira MCP result")
    return value


def resource_ids(value):
    value = mcp_value(value)
    resources = value.get("resources") if isinstance(value, dict) else value
    if not isinstance(resources, list) or any(not isinstance(r, dict) for r in resources):
        raise PolicyError("Incomplete Atlassian resource metadata")
    identities = [r.get("cloudId") or r.get("id") for r in resources]
    if any(not isinstance(i, str) or not i for i in identities):
        raise PolicyError("Atlassian resource identity is missing")
    return set(identities)


def read_graph(key, config, connection=None):
    policy = config.get("epic", {})
    jira = policy.get("jira")
    if (
        not jira
        or not isinstance(key, str)
        or not re.fullmatch(r"(?:[A-Z][A-Z0-9_]*-[1-9][0-9]*|[1-9][0-9]*)", key)
    ):
        raise PolicyError("Configure the Jira site/type/link mapping before importing an epic key")
    if connection is None:
        from lap_mcp import connection as connect

        connection = connect("atlassian-rovo")

    def call(name, **arguments):
        return result_object(
            connection.call(
                name,
                cloudId=jira["cloud_id"],
                view="full",
                responseContentFormat="html",
                **arguments,
            )
        )

    epic = call("getJiraIssue", issueIdOrKey=key, fields=["summary", "description", "issuetype"])
    epic_task = jira_snapshot(epic, config["repository"])
    if (epic_task.source_id != key if key.isdigit() else epic.get("key") != key) or str(
        epic.get("fields", {}).get("issuetype", {}).get("id")
    ) != jira["epic_type_id"]:
        raise PolicyError("Jira issue is not the configured epic type")
    key = epic.get("key", "")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*", key):
        raise PolicyError("Jira returned an invalid epic key")
    issues, token, seen = [], None, set()
    while True:
        args = {
            "jql": f'parent = "{key}" ORDER BY key',
            "fields": ["summary", "description", "parent", "issuelinks"],
            "maxResults": min(100, policy["max_tickets"]),
        }
        if token:
            args["nextPageToken"] = token
        page = call("searchJiraIssuesUsingJql", **args)
        batch = page.get("issues")
        if not isinstance(batch, list) or not all(isinstance(i, dict) for i in batch):
            raise PolicyError("Jira issue page is incomplete")
        issues.extend(batch)
        if len(issues) > policy["max_tickets"]:
            raise PolicyError("Jira epic exceeds max_tickets; refusing truncated graph")
        next_token = page.get("nextPageToken")
        if page.get("isLast") is True or page.get("total") == len(issues):
            if next_token:
                raise PolicyError("Contradictory Jira pagination")
            break
        if not next_token or next_token in seen:
            raise PolicyError("Jira pagination is incomplete or repeated")
        seen.add(next_token)
        token = next_token
    tickets = []
    for issue in issues:
        fields, issue_key = issue.get("fields", {}), issue.get("key")
        parent = fields.get("parent") or {}
        if parent.get("id") != epic_task.source_id or parent.get("key") != key:
            raise PolicyError("Jira child does not belong to the admitted epic")
        deps = set()
        mappings = [{"type_id": jira["blocks_link_type_id"], "direction": "inward"}]
        mappings.extend(jira.get("dependency_links", []))
        for link in fields.get("issuelinks", []):
            for mapping in mappings:
                target = link.get(mapping["direction"] + "Issue")
                if str(link.get("type", {}).get("id")) == mapping["type_id"] and target:
                    deps.add(target["key"])
        scope = policy.get("scopes", {}).get(issue_key, {})
        tickets.append(
            {
                "key": issue_key,
                "task": asdict(jira_snapshot(issue, config["repository"])),
                "depends_on": sorted(deps),
                "paths": scope.get("paths"),
                "resources": scope.get("resources"),
            }
        )
    return graph_checked(
        {
            "schema_version": "epic/v1",
            "version": 1,
            "strategy": "direct_to_base",
            "epic": asdict(epic_task),
            "tickets": tickets,
        },
        config,
    )
