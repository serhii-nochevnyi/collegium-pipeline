"""Reproducible native process-argument calibration without repository writes."""

import argparse
import json
import time
from pathlib import Path

from collegium_pipeline.artifacts import Artifacts
from collegium_pipeline.config import config_digest, load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.domain import PolicyError, Task
from collegium_pipeline.effort import PROBE_COMMAND, runtime_evidence
from collegium_pipeline.platform import Collegium
from collegium_pipeline.runner import worker_binding
from collegium_pipeline.store import Journal


def calibrate(config, role, journal, artifact_directory, output, *, attempt="v1", timeout=180):
    if (
        config.get("execution_profile") != "readiness"
        or config.get("execution_enabled") is not True
    ):
        raise PolicyError("Calibration requires enabled readiness configuration")
    binding = worker_binding(config, role)
    task = Task(
        "text",
        f"calibration-{role}-{binding.agent_id}-{attempt}",
        config["repository"],
        "Worker runtime calibration",
        "Only the pinned read-only runtime probe is allowed",
    )
    run_id = journal.admit(task, config_digest(config), purpose="calibration")
    run = journal.get(run_id)
    platform = Collegium(local_platform())
    launches = [e["data"] for e in journal.events(run_id) if e["kind"] == "launched"]
    if run["state"] == "calibration_passed":
        receipt = {"run_id": run_id, **launches[-1]}
        Path(output).write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    if run["state"] in {"failed", "reconciling"} or (run["pending_intent"] and not launches):
        raise PolicyError("Earlier calibration needs reconciliation; no replacement is launched")
    if launches:
        launched = launches[-1]
    else:
        packet = {
            "schema_version": "worker-packet/v1",
            "kind": "readiness",
            "run_id": run_id,
            "stage": "runtime_diagnostic",
            "role": role,
            "runtime_probe_command": PROBE_COMMAND,
            "instructions": "Run only the runtime probe as your first tool call; then return JSON.",
            "result_schema": {
                "schema_version": "worker-result/v1",
                "run_id": run_id,
                "stage": "runtime_diagnostic",
                "verdict": "pass or fail",
            },
        }
        launched = platform.dispatch(
            journal,
            run_id,
            run["version"],
            binding=binding,
            selection=binding.selection,
            prompt=json.dumps(packet),
            execution_enabled=True,
        )
    receipt = {"run_id": run_id, **launched}
    Path(output).write_text(json.dumps(receipt, indent=2) + "\n")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        turn = platform.observe(launched["session_id"], launched["turn_id"])
        if turn["status"] not in {"starting", "running"}:
            observed = platform.observations(launched["session_id"], launched["turn_id"])
            proof = runtime_evidence(
                observed, binding, session_id=launched["session_id"], turn_id=launched["turn_id"]
            )
            proof["observation_digest"] = Artifacts(artifact_directory).put(observed)
            journal.complete_calibration(run_id, journal.get(run_id)["version"], proof)
            return {**receipt, "effort": proof["effort"], "model": proof["model"]}
        time.sleep(2)
    answer, _ = platform.http.request("POST", "/session/" + launched["session_id"] + "/abort")
    journal.record(run_id, "stop_requested", answer)
    journal.unknown_launch(run_id, launched["intent"])
    raise PolicyError("Calibration timed out; the original turn is under reconciliation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("role")
    parser.add_argument("--config", default="config/readiness.json")
    parser.add_argument("--journal", default=".local/calibrations.sqlite3")
    parser.add_argument("--artifacts", default=".local/artifacts")
    parser.add_argument("--output")
    parser.add_argument("--attempt", default="v1")
    args = parser.parse_args()
    Path(args.journal).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = args.output or f".local/probe-{args.role}.json"
    journal = Journal(args.journal)
    try:
        print(
            json.dumps(
                calibrate(
                    load_config(args.config),
                    args.role,
                    journal,
                    args.artifacts,
                    output,
                    attempt=args.attempt,
                )
            )
        )
    finally:
        journal.close()
