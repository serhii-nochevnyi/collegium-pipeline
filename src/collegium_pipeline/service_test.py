"""Strict red-before-repair evidence for the explicitly authorized CI diagnostic."""

import re
import subprocess

from .adapters import Github
from .domain import PolicyError, digest


def candidate_gate(config, doc, changes):
    gate = config.get("service_test")
    if not gate:
        return
    phase = "initial" if doc["cycle"] == 0 else "repaired"
    if phase == "repaired" and not doc.get("service_red"):
        raise PolicyError("Service repair requires actual initial-head CI failure evidence")
    if digest(changes) != gate[phase + "_changes_digest"]:
        raise PolicyError(
            "Service candidate differs from the exact authorized " + phase + " fixture"
        )


def failure_evidence(config, doc, checks, ci, *, github=None):
    """Read-only gh diagnostics; all writes still use the separate native App broker."""
    gate = config["service_test"]
    failed_ids = {f["id"] for f in ci["failures"]}
    matching = [
        c
        for c in checks
        if c["id"] in failed_ids
        and c["name"] == gate["check_name"]
        and (c.get("app") or {}).get("id") == 15368
        and c.get("head_sha") == doc["head"]
        and c.get("conclusion") == "failure"
    ]
    if len(matching) != 1:
        raise PolicyError("Service test requires one actual GitHub Actions assertion failure")
    check = matching[0]
    prefix = "https://github.com/" + config["repository"] + "/actions/runs/"
    match = re.fullmatch(re.escape(prefix) + r"([0-9]+)/job/([0-9]+)", check.get("details_url", ""))
    if not match:
        raise PolicyError("Service failing job has an unverified GitHub Actions URL")
    run_id, job_id = map(int, match.groups())
    native = github is not None and config.get("broker_reads") != "local_gh"
    github = github if native else Github(config["repository"])
    job = github.read(f"/actions/jobs/{job_id}")
    run = github.read(f"/actions/runs/{run_id}")
    if (
        job.get("id") != job_id
        or job.get("run_id") != run_id
        or job.get("head_sha") != doc["head"]
        or run.get("head_sha") != doc["head"]
        or job.get("conclusion") != "failure"
        or job.get("name") != gate["check_name"]
        or job.get("check_run_url")
        != f"https://api.github.com/repos/{config['repository']}/check-runs/{check['id']}"
        or run.get("repository", {}).get("id") != config["repository_id"]
        or run.get("event") != "pull_request"
    ):
        raise PolicyError("Service failure job/run/repository revision differs")
    if native:
        logs = github.logs(job_id)
    else:
        result = subprocess.run(
            ["gh", "api", f"repos/{config['repository']}/actions/jobs/{job_id}/logs"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if result.returncode:
            raise PolicyError("Service failure logs unavailable")
        logs = result.stdout
    if len(logs.encode()) > 2_000_000:
        raise PolicyError("Service failure logs exceed the diagnostic limit")
    if not all(s in logs for s in (gate["failure_signature"], gate["test_name"])):
        raise PolicyError("Red CI did not fail on the authorized service assertion")
    return {
        "pr_number": doc["pr"]["number"],
        "head": doc["head"],
        "run_id": run_id,
        "job_id": job_id,
        "check_id": check["id"],
        "logs_digest": digest(logs),
        "failure_signature": gate["failure_signature"],
        "url": check["details_url"],
    }
