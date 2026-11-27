"""Read-only code-executor probe: credential injection, never token extraction."""

import json
import subprocess

REPOSITORY = "airslate-common/agents-knowledge"


def request(path, payload=None):
    command = ["curl", "--silent", "--show-error", "--max-time", "30"]
    if payload is not None:
        command += ["-H", "Content-Type: application/json", "--data", json.dumps(payload)]
    command += ["--write-out", "\n%{http_code}", "https://api.github.com" + path]
    result = subprocess.run(command, capture_output=True, text=True, timeout=35, check=True)
    body, status = result.stdout.rsplit("\n", 1)
    try:
        value = json.loads(body)
    except ValueError:
        value = {}
    return int(status), value


def main():
    status, repo = request("/repos/" + REPOSITORY)
    graph_status, graph = request(
        "/graphql",
        {"query": '{repository(owner:"airslate-common",name:"agents-knowledge"){databaseId}}'},
    )
    print(
        "COLLEGIUM_EGRESS_PROBE="
        + json.dumps(
            {
                "repository": REPOSITORY,
                "rest_status": status,
                "rest_repository_id": repo.get("id"),
                "graphql_status": graph_status,
                "graphql_repository_id": graph.get("data", {})
                .get("repository", {})
                .get("databaseId"),
                "graphql_errors_present": bool(graph.get("errors")),
                "credentials_printed": False,
                "repository_modified": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
