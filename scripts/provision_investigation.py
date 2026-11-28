"""Prepare immutable private-Claude investigation workers and paused lane dependencies."""

import argparse
import copy
import json
from dataclasses import asdict
from pathlib import Path

from collegium_pipeline.adapters import command_json
from collegium_pipeline.config import load_config
from collegium_pipeline.credentials import local_platform
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.investigation_policy import binding_key, variants
from collegium_pipeline.native_broker import binding_digest
from collegium_pipeline.platform import agent_digest

ROOT = Path(__file__).resolve().parents[1]


def agent_name(selection):
    return (
        f"pipeline-investigation-{selection.role.removeprefix('investigation_').replace('_', '-')}-"
        f"{selection.model}-{selection.effort}-v1"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    base = load_config(ROOT / "config/claude-service.json")
    path = ROOT / "config/investigation.json"
    if not args.apply and not args.refresh:
        print(
            json.dumps(
                {
                    "agents": len(variants()),
                    "model_connection": base["model_connection_id"],
                    "automations": ["pipeline-investigate", "pipeline-investigation-recovery-v1"],
                    "status": "paused",
                    "repository_access": "read",
                    "paid_calls": 0,
                }
            )
        )
        return
    http = local_platform()
    if args.refresh:
        config = load_config(path)
        previous = json.loads(path.read_text())
        environments, _ = http.request(
            "GET", "/api/projects/" + base["project_id"] + "/environments"
        )
        defaults = [r for r in environments["environments"] if r["is_default"]]
        if len(defaults) != 1 or any(
            defaults[0].get(k) != v
            for k, v in {
                "runtime": "aranarium-aws",
                "environment": None,
                "size": "standard",
            }.items()
        ):
            raise PolicyError("Installed project-default environment differs from reviewed plan")
        for binding in config["workers"].values():
            row, _ = http.request("GET", "/api/agents/" + binding["agent_id"])
            selection = binding["selection"]
            if (
                row.get("model") != selection["model"]
                or row.get("config", {}).get("effort") != selection["effort"]
                or row.get("model_connection_id") != base["model_connection_id"]
                or row.get("harness") != "claude-code"
                or row.get("project_id") != base["project_id"]
                or row.get("runtime") != binding["runtime"]
                or row.get("environment") != "project-default"
                or (row.get("system") or "").strip()
                != (
                    (ROOT / "agents/investigation-worker.md").read_text()
                    + f"\nYour fixed role is {selection['role']}.\n"
                ).strip()
                or row.get("max_runtime_minutes") != 5
                or row.get("status") != "paused"
                or row.get("config", {}).get("repositories")
                != [
                    {
                        "type": "github_repository",
                        "url": "https://github.com/" + base["repository"],
                        "connection": base["github_connection_id"],
                        "access": "read",
                    }
                ]
                or row.get("config", {}).get("mcp_servers", [])
                or row.get("rule_ids") != ["project/pipeline-investigation-quality"]
                or any(row.get(k) for k in ("skill_ids", "setup_commands", "vault_keys"))
                or any(
                    row.get("references", {}).get(k)
                    for k in ("mcp", "skills", "secrets", "variables", "sub_agents")
                )
                or any(
                    t.get("type")
                    not in {
                        "bash",
                        "read",
                        "write",
                        "edit",
                        "glob",
                        "grep",
                        "web_fetch",
                        "web_search",
                    }
                    for t in row.get("config", {}).get("tools", [])
                )
                or row.get("provenance", {}).get("installation", {}).get("id")
                != "ins_c70812fb10c042028e414bb01285f56b"
                or row.get("provenance", {}).get("source_gone") is not False
            ):
                raise PolicyError("Refresh cannot repin changed investigation authority or policy")
            rules = row.get("references", {}).get("rules", [])
            if len(rules) != 1 or rules[0].get("name") != "pipeline-investigation-quality":
                raise PolicyError("Investigation rule identity differs")
            rule, _ = http.request("GET", "/api/rules/" + rules[0]["id"])
            expected_rule = ROOT / ".github/lap/collegium-pipeline/rules/investigation-quality.md"
            if rule.get("content") != expected_rule.read_text().strip():
                raise PolicyError("Investigation rule content differs")
            binding["approved_agent_digest"] = agent_digest(row)
        recovery = config["recovery_store"]
        row, _ = http.request("GET", "/api/automations/" + recovery["automation_id"])
        code, _ = http.request("GET", "/api/automations/" + recovery["automation_id"] + "/code")
        expected_files = {
            "investigation-recovery/recovery_store.py": (
                ROOT / "scripts/recovery_store.py"
            ).read_text(),
            "investigation-recovery/recovery_scope.json": json.dumps(
                {"owner": recovery["owner"]}, sort_keys=True
            ),
        }
        if (
            code["current"]["files"] != expected_files
            or row["status"] != "paused"
            or row["project_id"] != base["project_id"]
            or row.get("target", {}).get("command")
            != "cd investigation-recovery && python3 recovery_store.py"
            or row.get("target", {}).get("repositories", [])
            or row.get("target", {}).get("mcp_servers", [])
            or row.get("target", {}).get("variables", [])
            or row.get("target", {}).get("secrets") != ["project/PIPELINE_CONTROL_KEY"]
        ):
            raise PolicyError("Refresh cannot repin changed checkpoint code or scope")
        recovery["approved_digest"] = binding_digest(row, code)
        path.with_suffix(".before-refresh.json").write_text(json.dumps(previous, indent=2) + "\n")
        path.write_text(json.dumps(config, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "refreshed": len(config["workers"]),
                    "execution_enabled": False,
                    "broker_enabled": False,
                }
            )
        )
        return
    autos, _ = http.request("GET", "/api/automations?project_id=" + base["project_id"])

    def automation(body):
        found = [a for a in autos["automations"] if a["name"] == body["name"]]
        if len(found) > 1:
            raise PolicyError("Ambiguous prepared investigation automation")
        if found:
            row, _ = http.request("GET", "/api/automations/" + found[0]["id"])
        else:
            row, _ = http.request("POST", "/api/automations", body)
            autos["automations"].append(row)
        if row["status"] != "paused":
            raise PolicyError("Prepared investigation automation must stay paused")
        return row

    common = {
        "project_id": base["project_id"],
        "target_kind": "script",
        "executor": "aranarium",
        "environment": "base",
        "size": "small",
        "status": "paused",
        "triggers": [],
        "notify": "none",
        "secrets": ["project/PIPELINE_CONTROL_KEY"],
    }
    controller = automation(
        {
            **common,
            "name": "pipeline-investigate-staged",
            "command": "python3 controller/investigation_entry.py",
            "repositories": [
                {
                    "type": "github_repository",
                    "url": "https://github.com/" + base["repository"],
                    "connection": base["github_connection_id"],
                    "access": "read",
                }
            ],
            "code": {
                "files": {
                    "controller/investigation_entry.py": (
                        "raise RuntimeError('Investigation bundle not installed')\n"
                    )
                }
            },
        }
    )
    recovery_files = {
        "investigation-recovery/recovery_store.py": (
            ROOT / "scripts/recovery_store.py"
        ).read_text(),
        "investigation-recovery/recovery_scope.json": json.dumps(
            {"owner": controller["id"]}, sort_keys=True
        ),
    }
    recovery = automation(
        {
            **common,
            "name": "pipeline-investigation-recovery-v1-staged",
            "command": "cd investigation-recovery && python3 recovery_store.py",
            "repositories": [],
            "code": {"files": recovery_files},
        }
    )
    code, _ = http.request("GET", "/api/automations/" + recovery["id"] + "/code")
    if code["current"]["files"] != recovery_files:
        raise PolicyError("Prepared checkpoint code differs")
    config = copy.deepcopy(base)
    config.pop("service_test", None)
    config.update(
        execution_enabled=False,
        broker_enabled=False,
        broker_reads="native_script",
        max_total_tokens=2000000,
        max_worker_jobs=16,
        workers={},
        validation_commands=base["repair_validation_commands"],
        recovery_store={
            "automation_id": recovery["id"],
            "owner": controller["id"],
            "approved_digest": binding_digest(recovery, code),
        },
        investigation={
            "schema_version": "investigation-policy/v1",
            "parallelism": 2,
            "max_jobs": 16,
            "minimum_complexity": "simple",
            "source_paths": ["src/collegium_pipeline/", "tests/", "docs/", "README.md", "SPEC.md"],
        },
    )
    identity = command_json(["lap", "whoami", "--json"])
    agents = command_json(["lap", "agents", "ls", "--project", base["project_id"], "--json"])
    rows = agents["agents"] if isinstance(agents, dict) else agents
    old = load_config(path) if path.exists() else None
    for selection in variants():
        name = agent_name(selection) + "-staged"
        found = [r for r in rows if r["name"] == name]
        if len(found) > 1:
            raise PolicyError("Ambiguous investigation worker name")
        body = {
            "name": name,
            "owner_id": identity["user_id"],
            "space_id": base["space_id"],
            "project_id": base["project_id"],
            "runtime": "aranarium-aws",
            "environment": "penv_abd958a7f24748afbd55ae6580112147",
            "harness": "claude-code",
            "model": selection.model,
            "model_connection": base["model_connection"],
            "max_runtime_minutes": 5,
            "system": (ROOT / "agents/investigation-worker.md").read_text()
            + f"\nYour fixed role is {selection.role}.\n",
            "config": {
                "effort": selection.effort,
                "repositories": [
                    {
                        "type": "github_repository",
                        "url": "https://github.com/" + base["repository"],
                        "connection": base["github_connection_id"],
                        "access": "read",
                    }
                ],
            },
        }
        if found:
            row, _ = http.request("GET", "/api/agents/" + found[0]["id"])
        else:
            row, _ = http.request("POST", "/api/agents", body)
            row, _ = http.request("GET", "/api/agents/" + row["id"])
        if (
            any(
                row.get(k) != body[k]
                for k in ("model", "system", "max_runtime_minutes", "project_id")
            )
            or row.get("model_connection_id") != base["model_connection_id"]
            or row.get("config", {}).get("effort") != selection.effort
        ):
            raise PolicyError("Existing immutable investigation worker differs")
        key = binding_key(selection)
        binding = {
            "agent_id": row["id"],
            "project_id": base["project_id"],
            "runtime": "aranarium-aws",
            "environment_id": "base",
            "api_model": selection.model,
            "selection": asdict(selection),
            "approved_agent_digest": agent_digest(row),
            "harness": "claude-code",
            "model_connection_id": base["model_connection_id"],
        }
        if old and key in old["workers"] and old["workers"][key] != binding:
            raise PolicyError(
                "Pinned worker changed; use explicit refresh after reviewed installation"
            )
        config["workers"][key] = binding
        # Store each known identity even if a later creation fails.
        path.write_text(json.dumps(config, indent=2) + "\n")
        print(json.dumps({"worker": key, "agent_id": row["id"], "paid_calls": 0}), flush=True)
    print(
        json.dumps(
            {
                "controller": controller["id"],
                "recovery": recovery["id"],
                "workers": len(config["workers"]),
                "status": "paused",
            }
        )
    )


if __name__ == "__main__":
    main()
