"""Plan/apply a manual-only App-scoped broker; credentials never leave Collegium."""

import argparse
import json
from pathlib import Path

from collegium_pipeline.config import load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.native_broker import binding_digest


def manifest(config, *, version=1):
    root = Path(__file__).resolve().parents[1]
    scope = {k: config[k] for k in ("repository", "base_branch", "allowed_paths")}
    return {
        "name": f"pipeline-native-broker-{config['repository_id']}-v{version}",
        "project_id": config["project_id"],
        "target_kind": "script",
        "executor": "aranarium",
        "environment": "base",
        "size": "small",
        "command": "python3 native_github_broker.py",
        "code": {
            "files": {
                "native_github_broker.py": (root / "scripts/native_github_broker.py").read_text(),
                "broker_scope.json": json.dumps(scope, sort_keys=True),
            }
        },
        "repositories": [
            {
                "type": "github_repository",
                "url": "https://github.com/" + config["repository"],
                "connection": config["github_connection_id"],
                "access": "contributor",
            }
        ],
        "triggers": [],
        "status": "paused",
        "notify": "none",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/personal-service.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--version", type=int, default=1)
    args = parser.parse_args()
    path = Path(args.config)
    config = load_config(path)
    if args.version < 1:
        parser.error("--version must be positive")
    body = manifest(config, version=args.version)
    if not args.apply:
        print(
            json.dumps(
                {
                    "name": body["name"],
                    "repository": config["repository"],
                    "access": "contributor",
                    "triggers": [],
                    "status": "paused",
                    "model_calls": 0,
                    "applied": False,
                },
                indent=2,
            )
        )
        return
    http = local_platform()
    rows, _ = http.request("GET", "/api/automations?project_id=" + config["project_id"])
    existing = [r for r in rows["automations"] if r["name"] == body["name"]]
    if len(existing) > 1:
        raise PolicyError("Multiple native brokers have the same name")
    if existing:
        row, _ = http.request("GET", "/api/automations/" + existing[0]["id"])
    else:
        row, _ = http.request("POST", "/api/automations", body)
    code, _ = http.request("GET", "/api/automations/" + row["id"] + "/code")
    if code["current"]["files"] != body["code"]["files"]:
        raise PolicyError("Existing broker source differs; use an explicit new version")
    pin = binding_digest(row, code)
    previous = config.get("native_broker")
    if previous and previous != {"automation_id": row["id"], "approved_digest": pin}:
        raise PolicyError("Pinned native broker changed; refusing automatic repin")
    config.update(
        broker_transport="collegium_script",
        repair_pr_mode="keep_ready",
        native_broker={"automation_id": row["id"], "approved_digest": pin},
    )
    path.write_text(json.dumps(config, indent=2) + "\n")
    print(
        json.dumps(
            {
                "automation_id": row["id"],
                "approved_digest": pin,
                "status": row["status"],
                "applied": True,
            }
        )
    )


if __name__ == "__main__":
    main()
