"""Real read adapters. Credentials are resolved by installed authenticated clients."""

import json
import re
import subprocess
from urllib.parse import quote

from .domain import PolicyError, Task


def command_json(arguments: list[str], *, timeout=30):
    try:
        result = subprocess.run(
            arguments, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{arguments[0]} unavailable or timed out") from exc
    if result.returncode:
        # Do not forward raw client errors that may contain credentials or URLs.
        raise RuntimeError(f"{arguments[0]} request failed (exit {result.returncode})")
    return json.loads(result.stdout)


class Github:
    def __init__(self, repository: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise PolicyError("Invalid repository")
        self.repository = repository

    def read(self, path=""):
        return command_json(["gh", "api", f"repos/{self.repository}" + path])

    def pr_evidence(self, number: int):
        if type(number) is not int or number <= 0:
            raise PolicyError("A positive PR number is required")
        pr = self.read(f"/pulls/{number}")
        head = pr["head"]["sha"]
        checks = command_json(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{self.repository}/commits/{quote(head)}/check-runs?per_page=100",
            ]
        )
        statuses = command_json(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{self.repository}/commits/{quote(head)}/statuses?per_page=100",
            ]
        )
        # Refetch after checks: a push or base update during observation must not
        # yield an internally inconsistent acceptance packet.
        current = self.read(f"/pulls/{number}")
        if current["head"]["sha"] != head or current["base"]["sha"] != pr["base"]["sha"]:
            raise PolicyError("PR changed while collecting evidence")
        return (
            current,
            [c for page in checks for c in page["check_runs"]],
            [{**s, "sha": head} for page in statuses for s in page],
        )


def jira_snapshot(issue: dict, repository: str) -> Task:
    """Normalize an exported Jira REST issue; this does not claim a live connection."""
    if not issue.get("id") or not issue.get("key"):
        raise PolicyError("Jira issue identity is missing")
    fields = issue.get("fields", {})
    requirements = fields.get("description")
    if isinstance(requirements, dict):  # Preserve ADF structurally, without dropping requirements.
        requirements = json.dumps(requirements, sort_keys=True)
    return Task("jira", issue["id"], repository, fields.get("summary", ""), requirements or "")
