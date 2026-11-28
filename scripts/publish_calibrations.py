"""Reverify native role calibrations without exposing keys or starting model turns."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from collegium_pipeline.artifacts import Artifacts
from collegium_pipeline.config import config_digest, load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.domain import PolicyError, digest
from collegium_pipeline.effort import runtime_evidence
from collegium_pipeline.platform import Collegium, agent_digest
from collegium_pipeline.runner import worker_binding
from collegium_pipeline.store import Journal


def publish(config, journal, artifacts, receipt_directory, output):
    http = local_platform()
    workers = {}
    for role in config["workers"]:
        receipt = json.loads(
            (
                Path(receipt_directory) / ("claude-probe-" + role.replace(":", "-") + ".json")
            ).read_text()
        )
        run = journal.get(receipt["run_id"])
        if run["state"] != "calibration_passed" or run["config_digest"] != config_digest(config):
            raise PolicyError("Calibration is absent or belongs to another configuration")
        binding = worker_binding(config, role)
        agent, _ = http.request("GET", "/api/agents/" + binding.agent_id)
        if agent_digest(agent) != binding.approved_agent_digest:
            raise PolicyError("Calibrated worker configuration changed")
        observed = Collegium(http).observations(receipt["session_id"], receipt["turn_id"])
        proof = runtime_evidence(
            observed, binding, session_id=receipt["session_id"], turn_id=receipt["turn_id"]
        )
        workers[role] = {**proof, "observation_digest": artifacts.put(observed)}
    report = {
        "schema_version": "worker-calibrations/v1",
        "created_at": datetime.now(UTC).isoformat(),
        "state": "workers_verified",
        "config_digest": config_digest(config),
        "worker_set_digest": digest(config["workers"]),
        "model_connection_id": config.get("model_connection_id"),
        "workers": workers,
        "repository_modified": False,
        "pr_created": False,
        "delivered": False,
        "limitations": [
            "Calibration verifies workers, not a delivered PR",
            "Effort evidence verifies launch configuration and served-model support; "
            "provider internal reasoning is not observable",
            "Subscription list-price telemetry is not the amount billed to the owner",
        ],
    }
    Path(output).write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/claude-calibration.json")
    parser.add_argument("--journal", default=".local/claude-calibrations.sqlite3")
    parser.add_argument("--artifacts", default=".local/claude-calibration-artifacts")
    parser.add_argument("--receipts", default=".local")
    parser.add_argument("--output", default="reports/claude-workers.json")
    args = parser.parse_args()
    journal = Journal(args.journal)
    try:
        report = publish(
            load_config(args.config), journal, Artifacts(args.artifacts), args.receipts, args.output
        )
        print(json.dumps({k: report[k] for k in ("state", "worker_set_digest", "delivered")}))
    finally:
        journal.close()
