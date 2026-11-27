"""Explicit paid, read-only native checkout diagnostic; no broker or product task."""

import argparse
import json
import time
from pathlib import Path

from collegium_pipeline.adapters import Github
from collegium_pipeline.artifacts import Artifacts
from collegium_pipeline.config import config_digest, load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.delivery_workers import NativeJobs
from collegium_pipeline.domain import Task
from collegium_pipeline.store import Journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/delivery.example.json")
    parser.add_argument(
        "--run", action="store_true", help="Start/resume a paid read-only diagnostic"
    )
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; this diagnostic calls a model")
    config = load_config(args.config)
    folder = Path(".local")
    folder.mkdir(mode=0o700, exist_ok=True)
    journal = Journal(folder / "delivery-diagnostic.sqlite3")
    task = Task(
        "text",
        "delivery-checkout-v3",
        config["repository"],
        "Read-only checkout diagnostic",
        (
            "Only verify the pinned runtime probe and checkout. Do not change files or "
            "implement a product task. Return a minimal plan and acceptance list recording "
            "that checkout was observed. Never push, open a PR or run the broker."
        ),
    )
    root = journal.admit(task, config_digest(config), purpose="calibration")
    artifacts = Artifacts(folder / "delivery-diagnostic-artifacts")
    jobs = NativeJobs(config, journal, local_platform(), artifacts)
    bound = [e["data"] for e in journal.events(root) if e["kind"] == "checkout_revision"]
    if not bound:
        head = Github(config["repository"]).read("/commits/" + config["base_branch"])["sha"]
        journal.record(root, "checkout_revision", {"head": head})
    else:
        head = bound[0]["head"]
    deadline = time.monotonic() + 360
    try:
        while time.monotonic() < deadline:
            result = jobs.step(root, "checkout", "planning", head, head, {"diagnostic": True})
            if result is not None:
                report = {
                    "schema_version": "delivery-checkout/v1",
                    "scope": "native read-only service diagnostic; no product task",
                    "run_id": root,
                    "head": head,
                    "verdict": result["verdict"],
                    "session_id": result["session_id"],
                    "runtime_evidence": result["runtime_evidence"],
                    "artifact_digest": artifacts.put(result),
                    "repository_modified": False,
                    "pr_created": False,
                }
                Path("reports/delivery-checkout.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
                print(json.dumps(report))
                return 0 if result["verdict"] == "pass" else 2
            time.sleep(2)
        jobs.stop_root(root)
        raise RuntimeError("Checkout diagnostic deadline exceeded")
    except KeyboardInterrupt:
        jobs.stop_root(root)
        return 130
    finally:
        journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
