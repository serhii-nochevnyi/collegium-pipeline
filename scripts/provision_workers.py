"""Provision/reconcile only this pipeline's versioned, explicitly scoped workers."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from collegium_pipeline.adapters import command_json
from collegium_pipeline.config import load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.domain import PolicyError, select_model
from collegium_pipeline.platform import WorkerBinding, agent_digest

ROLES = ("planner", "plan_reviewer", "executor", "code_reviewer", "fixer", "sentinel")


def provision(config_path, readiness=False, version=2, broker_workers=False):
    path = Path(config_path)
    config = load_config(path)
    http = local_platform()
    identity = command_json(["lap", "whoami", "--json"])
    listing = command_json(["lap", "agents", "ls", "--project", config["project_id"], "--json"])
    known = {a["name"]: a for a in listing["agents"]}
    system = (Path(__file__).resolve().parents[1] / "agents/worker.md").read_text()
    bindings = {}
    variants = [(role, 0) for role in ROLES]
    if broker_workers:
        variants += [("fixer", 1), ("fixer", 2)]
    for role, repeats in variants:
        claude = config.get("model_policy") == "claude"
        selection = select_model(
            role,
            same_cause_failures=repeats,
            profile=config.get("model_policy", "codex"),
        )
        binding_key = role if not repeats else role + ":" + selection.effort
        name = f"pipeline-{role.replace('_', '-')}-{selection.effort}-v{version}"
        if claude:
            name = name.replace("pipeline-", "pipeline-claude-", 1)
        if broker_workers:
            name = name.removesuffix(f"-v{version}") + f"-broker-v{version}"
        if readiness and not broker_workers and role in {"executor", "fixer"}:
            name = name.removesuffix(f"-v{version}") + f"-readiness-v{version}"
        body = {
            "name": name,
            "owner_id": identity["user_id"],
            "project_id": config["project_id"],
            "space_id": config["space_id"],
            "runtime": "aranarium-aws",
            "environment": "penv_abd958a7f24748afbd55ae6580112147",
            "harness": "claude-code" if claude else "codex",
            "model": selection.model if claude else "openai/" + selection.model,
            "model_connection": config["model_connection"] if claude else "platform/litellm",
            "system": (
                (Path(__file__).resolve().parents[1] / "agents/claude-worker.md").read_text()
                if claude
                else system
            )
            + f"\nYour fixed role is {role}.\n",
            "max_runtime_minutes": 5 if broker_workers else 2,
            "config": {
                "effort": selection.effort,
                "repositories": [
                    {
                        "type": "github_repository",
                        "url": "https://github.com/" + config["repository"],
                        "connection": config["github_connection_id"],
                        "access": "contributor"
                        if role in {"executor", "fixer"} and not readiness and not broker_workers
                        else "read",
                    }
                ],
            },
        }
        if name in known:
            row, _ = http.request("GET", "/api/agents/" + known[name]["id"])
            pinned = config["workers"].get(binding_key, {})
            if pinned.get("agent_id") == row["id"] and pinned.get(
                "approved_agent_digest"
            ) != agent_digest(row):
                raise PolicyError(f"Pinned worker {name} drifted; refusing to repin it")
            for key in ("model", "system", "max_runtime_minutes"):
                if row.get(key) != body[key]:
                    raise PolicyError(f"Existing versioned worker {name} changed: {key}")
            if row.get("config", {}).get("effort") != selection.effort:
                raise PolicyError(f"Existing versioned worker {name} has different effort")
            if (
                row.get("project_id") != config["project_id"]
                or row.get("owner_id") != identity["user_id"]
                or row.get("runtime") != body["runtime"]
                or row.get("config", {}).get("repositories") != body["config"]["repositories"]
            ):
                raise PolicyError(f"Worker {name} has a different owner, scope or repository grant")
        else:
            row, _ = http.request("POST", "/api/agents", body)
            if not row.get("id"):
                raise PolicyError(f"Worker creation returned no identity for {name}")
            row, _ = http.request("GET", "/api/agents/" + row["id"])
        if claude and (
            row.get("model_connection_id") != config["model_connection_id"]
            or row.get("harness") != "claude-code"
        ):
            raise PolicyError("Claude agent did not acknowledge its private connection/harness")
        binding = WorkerBinding(
            row["id"],
            config["project_id"],
            "aranarium-aws",
            "base",
            body["model"],
            selection,
            agent_digest(row),
            body["harness"],
            config["model_connection_id"] if claude else None,
        )
        bindings[binding_key] = asdict(binding)
        print(json.dumps({"role": role, "agent_id": row["id"], "effort": selection.effort}))
        # Persist each successful registration before attempting the next one.
        config["workers"].update(bindings)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config, indent=2) + "\n")
        temporary.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/pilot.json")
    parser.add_argument("--readiness", action="store_true")
    parser.add_argument("--version", type=int, default=2)
    parser.add_argument("--broker-workers", action="store_true")
    args = parser.parse_args()
    provision(
        args.config,
        readiness=args.readiness,
        version=args.version,
        broker_workers=args.broker_workers,
    )
