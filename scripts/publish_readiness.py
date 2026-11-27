"""Read native observations and publish their redacted readiness report."""

import argparse

from collegium_pipeline.config import load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.readiness import publish_readiness
from collegium_pipeline.store import Journal

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", default="config/readiness.json")
    parser.add_argument("--journal", default=".local/controller.sqlite3")
    parser.add_argument("--artifacts", default=".local/artifacts")
    parser.add_argument("--calibrations", default=".local")
    parser.add_argument("--output", default="reports/readiness.json")
    args = parser.parse_args()
    journal = Journal(args.journal)
    try:
        report = publish_readiness(
            load_config(args.config),
            journal,
            args.run_id,
            local_platform(),
            artifact_directory=args.artifacts,
            calibration_directory=args.calibrations,
            output=args.output,
        )
        print(
            f"Published {len(report['stages'])} native stages "
            f"and {len(report['workers'])} worker proofs"
        )
    finally:
        journal.close()
