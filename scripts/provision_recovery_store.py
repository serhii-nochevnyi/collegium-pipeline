"""Create a paused, signed checkpoint service; bind metadata, never retrieve secrets."""

import argparse
import json
from pathlib import Path

from collegium_pipeline.config import load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.native_broker import binding_digest

ROOT = Path(__file__).resolve().parents[1]
OWNER = "aut_2ea6d08b772f41d5a9fa236cb19f93d8"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/claude-service.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    files = {
        "recovery_store.py": (ROOT / "scripts/recovery_store.py").read_text(),
        "recovery_scope.json": json.dumps({"owner": OWNER}, sort_keys=True),
    }
    body = {
        "name": "pipeline-recovery-store-v1",
        "project_id": config["project_id"],
        "target_kind": "script",
        "executor": "aranarium",
        "environment": "base",
        "size": "small",
        "command": "python3 recovery_store.py",
        "code": {"files": files},
        "secrets": ["project/PIPELINE_CONTROL_KEY"],
        "repositories": [],
        "triggers": [{"kind": "schedule", "cron": "0 0 1 1 *", "timezone": "UTC"}],
        "status": "paused",
        "notify": "none",
    }
    if not args.apply:
        print(
            json.dumps(
                {
                    "name": body["name"],
                    "status": "paused",
                    "owner": OWNER,
                    "repositories": [],
                    "secrets": body["secrets"],
                    "applied": False,
                }
            )
        )
        return
    http = local_platform()
    found, _ = http.request("GET", "/api/automations?project_id=" + config["project_id"])
    found = [r for r in found["automations"] if r["name"] == body["name"]]
    if len(found) > 1:
        raise PolicyError("Ambiguous checkpoint service")
    if found:
        row, _ = http.request("GET", "/api/automations/" + found[0]["id"])
    else:
        row, _ = http.request("POST", "/api/automations", body)
    code, _ = http.request("GET", "/api/automations/" + row["id"] + "/code")
    if code["current"]["files"] != files or row["status"] != "paused":
        raise PolicyError("Checkpoint service differs; review an explicit update")
    binding = {
        "automation_id": row["id"],
        "owner": OWNER,
        "approved_digest": binding_digest(row, code),
    }
    if config.get("recovery_store") and config["recovery_store"] != binding:
        raise PolicyError("Checkpoint service binding changed; no implicit repin")
    config["recovery_store"] = binding
    Path(args.config).write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps({**binding, "status": "paused", "applied": True}))


if __name__ == "__main__":
    main()
