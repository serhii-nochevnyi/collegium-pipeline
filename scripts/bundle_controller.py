"""Collegium script entry point for the packaged serial controller."""

import json
import os
import sys
from pathlib import Path


def verify_control(config, integrations, http):
    """Authenticate with the controller's key; inspect only pinned, read-only metadata."""
    from collegium_pipeline.domain import PolicyError
    from collegium_pipeline.native_broker import ScriptTransport
    from collegium_pipeline.platform import agent_digest

    needs = {s["need"]: s for s in integrations["status"] if s["allowed_tools"]}
    for binding in config["workers"].values():
        agent, _ = http.request("GET", "/api/agents/" + binding["agent_id"])
        if agent_digest(agent) != binding["approved_agent_digest"]:
            raise PolicyError("Installed worker differs from the refreshed binding")
        refs = agent.get("references", {}).get("mcp", [])
        if len(refs) != len(needs) or any(
            r["name"] not in needs
            or r["level"] != "project"
            or r["id"] != needs[r["name"]]["connection_id"]
            for r in refs
        ):
            raise PolicyError("Installed MCP connection identities differ")
        toolsets = [t for t in agent["config"]["tools"] if t["type"] == "mcp_toolset"]
        if len(toolsets) != len(needs) or any(
            t["mcp_server_name"] not in needs
            or t["default_config"] != {"enabled": False}
            or t["configs"]
            != {name: {"enabled": True} for name in needs[t["mcp_server_name"]]["allowed_tools"]}
            for t in toolsets
        ):
            raise PolicyError("Installed MCP tool ceilings differ")
    ScriptTransport(config, http, None, None).scope()
    return {
        "control_key_valid": True,
        "worker_bindings_verified": len(config["workers"]),
        "mcp_connections_verified": len(needs),
        "app_broker_scope_verified": True,
        "agent_started": False,
        "execution_enabled": config["execution_enabled"],
        "broker_enabled": config["broker_enabled"],
    }


def main(event=None, *, root=None, environ=None, http=None):
    environ = os.environ if environ is None else environ
    root = Path(root or Path(__file__).resolve().parent)
    sys.path.insert(0, str(root / "src"))
    from collegium_pipeline.cli import main as controller
    from collegium_pipeline.config import load_config
    from collegium_pipeline.domain import PolicyError

    config_path = root / "settings.json"
    config = load_config(config_path)
    if event is None:
        event = json.loads(Path("/job/event.json").read_text()).get("data", {})
    if not isinstance(event, dict):
        raise PolicyError("Controller event data must be an object")
    action = event.get("action", "preflight")
    state = Path(environ.get("ARANARIUM_STATE_DIR", "/state")) / "collegium-pipeline"
    if action == "verify-control":
        if event != {"action": "verify-control"}:
            raise PolicyError("Control verification accepts no event parameters")
        key = environ.get("PIPELINE_CONTROL_KEY")
        if not key:
            raise PolicyError("Controller Vault key is required; no host credential fallback")
        from collegium_pipeline.transport import JsonHttp

        http = http or JsonHttp(config["server"], {"X-Api-Key": key})
        integrations = json.loads((root / "integrations.json").read_text())
        print(json.dumps(verify_control(config, integrations, http)))
        return 0
    if action == "preflight":
        result = {
            "controller_packaged": True,
            "execution_enabled": config["execution_enabled"],
            "broker_enabled": config.get("broker_enabled", False),
            "worker_count": len(config["workers"]),
            "model_policy": config.get("model_policy"),
            "control_key_present": bool(environ.get("PIPELINE_CONTROL_KEY")),
            "state_directory": str(state),
            "agent_started": False,
        }
        print(json.dumps(result))
        return 0
    if action not in {"prepare", "status", "deliver"}:
        raise PolicyError("Unknown controller action")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    common = ["--config", str(config_path), "--journal", str(state / "journal.sqlite3")]
    if action == "prepare":
        for key in ("task_id", "title", "requirements"):
            if not isinstance(event.get(key), str) or not event[key].strip():
                raise PolicyError("Prepare requires explicit task_id, title and requirements")
        # Requirements are JSON data passed to the existing admission path, never shell text.
        requirements = state / "intake-requirements.txt"
        requirements.write_text(event["requirements"])
        return controller(
            [
                "prepare-text",
                *common,
                "--task-id",
                event["task_id"],
                "--title",
                event["title"],
                "--requirements-file",
                str(requirements),
            ]
        )
    run_id = event.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PolicyError("An existing run_id is required")
    if action == "status":
        return controller(["status", *common, "--run-id", run_id])
    if event.get("live") is not True:
        raise PolicyError("Delivery requires explicit live=true")
    key = environ.get("PIPELINE_CONTROL_KEY")
    if not key:
        raise PolicyError("Bind PIPELINE_CONTROL_KEY in the project Vault before cloud dispatch")
    os.environ["LAP_SERVER"] = config["server"]
    os.environ["LAP_API_KEY"] = key
    return controller(
        [
            "deliver",
            *common,
            "--run-id",
            run_id,
            "--artifacts",
            str(state / "artifacts"),
            "--live",
            "--once",
        ]
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        # Avoid echoing an event, environment or a provider's credential-bearing error.
        print(json.dumps({"error": type(exc).__name__, "executed": False}), file=sys.stderr)
        raise SystemExit(2) from None
