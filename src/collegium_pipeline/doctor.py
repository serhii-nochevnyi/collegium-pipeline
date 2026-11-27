"""Read-only checks: no agent turn, model probe, tracker write or repository write."""

import json
from pathlib import Path

from .adapters import Github, command_json
from .broker import GithubApp
from .credentials import local_platform
from .domain import Selection, select_model
from .platform import WorkerBinding, agent_digest
from .readiness import verify_report
from .runner import worker_binding


def doctor(config: dict) -> dict:
    results = []
    profile = config.get("execution_profile", "delivery")

    def check(name, operation):
        try:
            details = operation()
            results.append({"name": name, "ok": True, "details": details})
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            results.append({"name": name, "ok": False, "reason": str(exc)})

    def identity():
        row = command_json(["lap", "whoami", "--server", config["server"], "--json"])
        if not any(g["space_id"] == config["space_id"] for g in row.get("grants", [])):
            raise ValueError("CLI identity has no grant for the configured space")
        return {"user_id": row["user_id"], "space_grant": True}

    def project():
        data = command_json(["lap", "projects", "--space", config["space_id"], "--json"])
        row = next((r for r in data["projects"] if r["id"] == config["project_id"]), None)
        if row is None or row.get("archived"):
            raise ValueError("Configured project is unavailable or archived")
        return {"id": row["id"], "name": row["name"], "role": row["my_role"]}

    def repository():
        row = Github(config["repository"]).read()
        permission = "pull" if profile == "readiness" else "push"
        if row["id"] != config["repository_id"] or not row.get("permissions", {}).get(permission):
            raise ValueError("Repository identity or local GitHub write access differs")
        return {"id": row["id"], "default_branch": row["default_branch"], permission: True}

    def connection():
        row = command_json(
            [
                "lap",
                "github-connections",
                "check",
                "https://github.com/" + config["repository"],
                "--project",
                config["project_id"],
                "--connection",
                config["github_connection_id"],
                "--access",
                "read" if profile == "readiness" else "contributor",
                "--json",
            ]
        )
        if not row.get("checks") or not all(c.get("ok") is True for c in row["checks"]):
            raise ValueError("Collegium connection has no confirmed Contributor access")
        return {"access": "read" if profile == "readiness" else "contributor"}

    def workers():
        http = local_platform()
        for role in config["workers"]:
            if ":" in role:
                base, effort = role.split(":", 1)
                repeats = {"high": 1, "xhigh": 2}.get(effort)
                if base != "fixer" or repeats is None:
                    raise ValueError("Unrecognized worker variant")
                row = dict(config["workers"][role])
                row["selection"] = Selection(**row["selection"])
                binding = WorkerBinding(**row)
                if binding.selection != select_model(base, same_cause_failures=repeats):
                    raise ValueError("Variant does not match effort policy")
            else:
                binding = worker_binding(config, role)
            agent, _ = http.request("GET", "/api/agents/" + binding.agent_id)
            if agent_digest(agent) != binding.approved_agent_digest:
                raise ValueError(f"Pinned worker configuration changed: {role}")
        return {"bound_and_current": list(config["workers"])}

    def report():
        value = json.loads(Path("reports/readiness.json").read_text())
        verify_report(config, value)
        return {
            "run_id": value["run_id"],
            "stages": len(value["stages"]),
            "usd_limit_enforced": value["usd_limit_enforced"],
        }

    check("cli_identity", identity)
    check("collegium_project", project)
    check("local_github", repository)
    check("collegium_github", connection)
    if config["workers"]:
        check("worker_bindings", workers)
    if profile == "readiness":
        check("native_readiness", report)
    if "broker_enabled" in config:
        check(
            "broker_installation_scope",
            lambda: GithubApp.from_environment(config).scope() or {"scoped": True},
        )
    blockers = []
    if profile == "delivery":
        blockers.append(
            "Product PR delivery is not enabled; "
            "installation credential, repository eligibility and a native PR/CI run need validation"
        )
    if not config["execution_enabled"]:
        blockers.append("Live execution is disabled")
    if not config["workers"]:
        blockers.append("Role workers and actual runtime selection evidence are not bound")
    if config["max_cost_usd"] is None:
        blockers.append("No execution cost ceiling is configured")
    return {
        "mode": config["mode"],
        "profile": profile,
        "checks": results,
        "connections_ok": all(r["ok"] for r in results),
        "execution_ready": not blockers and all(r["ok"] for r in results),
        "blockers": blockers,
        "notes": ["Gateway costs are uncounted; USD ceiling is not enforced"]
        if profile == "readiness"
        else [],
    }
