"""Publish a redacted report from reverified native observations and artifacts."""

import json
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import Artifacts
from .config import config_digest
from .domain import STAGE_ROLES, PolicyError, digest, verify_selection
from .effort import runtime_evidence
from .platform import Collegium
from .runner import worker_binding

REQUIRED_STAGES = ("planning", "plan_review", "implementing", "validating", "reviewing")
REQUIRED_ROLES = ("planner", "plan_reviewer", "executor", "code_reviewer", "fixer", "sentinel")


def publish_readiness(
    config, journal, run_id, http, *, artifact_directory, calibration_directory, output
):
    run = journal.get(run_id)
    if run["state"] != "self_test_passed" or run["config_digest"] != config_digest(config):
        raise PolicyError("No successful self-test exists for this exact configuration")
    artifacts = Artifacts(artifact_directory)
    events = journal.events(run_id)
    accepted = [e["data"] for e in events if e["kind"] == "stage_accepted"]
    if tuple(e["stage"] for e in accepted) != REQUIRED_STAGES:
        raise PolicyError("Required self-test stages are missing or duplicated")
    workers, stages = {}, []
    for stage in accepted:
        role = STAGE_ROLES[stage["stage"]]
        binding = worker_binding(config, role)
        stored = next(
            e["data"]
            for e in events
            if e["kind"] == "runtime_verified" and e["data"]["stage"] == stage["stage"]
        )
        proof_file = artifacts.get(stored["artifact_digest"])
        observation = artifacts.get(proof_file["observation_digest"])
        proof = runtime_evidence(
            observation, binding, session_id=stored["session_id"], turn_id=stored["turn_id"]
        )
        workers[role] = proof
        stages.append(
            {
                "stage": stage["stage"],
                "role": role,
                "result_digest": stage["evidence"]["artifact_digest"],
                "observation_digest": proof_file["observation_digest"],
                **proof,
            }
        )
    for role in REQUIRED_ROLES:
        if role in workers:
            continue
        receipt = json.loads((Path(calibration_directory) / f"probe-{role}.json").read_text())
        observation = Collegium(http).observations(receipt["session_id"], receipt["turn_id"])
        proof = runtime_evidence(
            observation,
            worker_binding(config, role),
            session_id=receipt["session_id"],
            turn_id=receipt["turn_id"],
        )
        proof["observation_digest"] = artifacts.put(observation)
        workers[role] = proof
    report = {
        "schema_version": "readiness-report/v1",
        "created_at": datetime.now(UTC).isoformat(),
        "profile": "readiness",
        "state": "self_test_passed",
        "run_id": run_id,
        "config_digest": config_digest(config),
        "worker_set_digest": digest(config["workers"]),
        "delivered": False,
        "repository_modified": False,
        "stages": stages,
        "workers": workers,
        "cost_accounting": "unavailable; gateway reports uncounted turns",
        "budget_enforcement": "stage-attempt, observed-token admission and runtime time limits",
        "usd_limit_enforced": False,
        "observed_tokens": sum(
            e["data"]["observed_tokens"] for e in events if e["kind"] == "stage_usage"
        ),
        "observation_rechecks": [e["data"] for e in events if e["kind"] == "observation_recheck"],
        "limitations": [
            "No product PR or production deployment was exercised",
            "Process-argument proof verifies client configuration, not provider internals",
            "Repository Contributor sessions require branch protections",
            "USD costs are uncounted; no hard dollar-budget claim is made",
        ],
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(path)
    return report


def verify_report(config, report):
    if (
        report.get("schema_version") != "readiness-report/v1"
        or report.get("state") != "self_test_passed"
        or report.get("delivered") is not False
        or report.get("config_digest") != config_digest(config)
        or report.get("worker_set_digest") != digest(config["workers"])
    ):
        raise PolicyError("Readiness report is absent, stale or has the wrong purpose")
    if tuple(s["stage"] for s in report.get("stages", [])) != REQUIRED_STAGES:
        raise PolicyError("Readiness report does not cover all required stages")
    for role in REQUIRED_ROLES:
        binding = worker_binding(config, role)
        proof = report.get("workers", {}).get(role, {})
        verify_selection(binding.selection, proof)
        if (
            proof.get("agent_id") != binding.agent_id
            or proof.get("model") != binding.selection.model
            or proof.get("effort") != binding.selection.effort
            or not proof.get("tool_result_event_id")
            or proof.get("proof_kind")
            != "first_tool_" + binding.harness.replace("-", "_") + "_process_arguments"
        ):
            raise PolicyError(f"Readiness has no matching native proof for {role}")
