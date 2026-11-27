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


def cloud_fence(event, state, environ, http, *, diagnostic=False):
    """Refuse replay when the platform discarded a previous attempt's journal.

    Platform run history is outside the attempt snapshot. A receipt inside the
    adopted snapshot proves that a previous delivery's journal survived with it.
    A lost/cancelled attempt has no such receipt and must be reconciled, not replayed.
    """
    import re

    from collegium_pipeline.domain import PolicyError

    automation, run, attempt = (
        environ.get(k, "") for k in ("LAP_AUTOMATION_ID", "LAP_RUN_ID", "LAP_ATTEMPT_ID")
    )
    for value, prefix in ((automation, "aut"), (run, "run"), (attempt, "att")):
        if not re.fullmatch(prefix + r"_[a-zA-Z0-9]+", value):
            raise PolicyError("Cloud delivery requires platform run and attempt identities")
    path = "/api/automations/" + automation + "/runs"
    current, _ = http.request("GET", path + "/" + run)
    attempts = current.get("attempts", [])
    if (
        current.get("id") != run
        or current.get("automation_id") != automation
        or current.get("status") != "running"
        or current.get("item", {}).get("event", {}).get("data") != event
        or len(attempts) != 1
        or attempts[0].get("id") != attempt
        or attempts[0].get("n") != 1
        or attempts[0].get("status") != "running"
    ):
        raise PolicyError("Uncertain cloud attempt; reconcile before delivery replay")
    receipt_path = state / ("diagnostic-fence.json" if diagnostic else "cloud-fence.json")
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if receipt and receipt.get("automation_id") != automation:
        raise PolicyError("Cloud checkpoint belongs to another automation")
    history, _ = http.request("GET", path + "?limit=100")
    rows = history["runs"]
    if not rows or rows[0]["id"] != run or len({r["id"] for r in rows}) != len(rows):
        raise PolicyError("Incomplete cloud history; delivery replay refused")
    anchored = False
    for row in rows[1:]:
        prior, _ = http.request("GET", path + "/" + row["id"])
        if prior.get("automation_id") != automation or prior.get("status") == "running":
            raise PolicyError("Uncertain previous cloud execution")
        if receipt and row["id"] == receipt.get("run_id"):
            prior_attempts = prior.get("attempts", [])
            if (
                prior.get("status") not in {"succeeded", "failed"}
                or len(prior_attempts) != 1
                or prior_attempts[0].get("id") != receipt.get("attempt_id")
                or prior_attempts[0].get("status") not in {"succeeded", "failed"}
            ):
                raise PolicyError("Cloud checkpoint attempt differs")
            anchored = True
            break
        data = prior.get("item", {}).get("event", {}).get("data", {})
        unsafe = (
            data.get("action") == "state-probe" and data.get("mode") == "fenced-hold"
            if diagnostic
            else data.get("action") == "deliver"
        )
        if unsafe:
            raise PolicyError("Uncheckpointed cloud execution; reconcile before delivery replay")
    if (receipt and not anchored) or (not receipt and len(rows) >= 100):
        raise PolicyError("Cloud history window exhausted; reconcile before delivery replay")
    return receipt_path, {"automation_id": automation, "run_id": run, "attempt_id": attempt}


def save_receipt(path, value):
    # Receipt and SQLite travel in the same adopted snapshot; never publish it to another store.
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True))
    temporary.replace(path)


def state_probe(event, state, config, environ, http):
    """Bounded diagnostic namespace only: no agent, broker or repository mutations."""
    import time

    from collegium_pipeline.domain import PolicyError, Task
    from collegium_pipeline.store import Journal

    if set(event) != {"action", "mode"} or event["mode"] not in {
        "commit",
        "crash",
        "hold",
        "inspect",
        "fenced-hold",
        "fenced-check",
    }:
        raise PolicyError("Unknown fixed state probe")
    if config["execution_enabled"] or config["broker_enabled"]:
        raise PolicyError("State probes require disabled delivery and broker")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if event["mode"].startswith("fenced-"):
        if http is None or not environ.get("PIPELINE_CONTROL_KEY"):
            raise PolicyError("Cloud fence probe requires the controller Vault key")
        path, receipt = cloud_fence(event, state, environ, http, diagnostic=True)
        if event["mode"] == "fenced-check":
            print(json.dumps({"cloud_fence_clear": True, "external_actions": 0}), flush=True)
            return 0
        print(json.dumps({"probe_ready": True, "external_actions": 0}), flush=True)
        time.sleep(120)
        save_receipt(path, receipt)
        return 0
    journal = Journal(state / "diagnostic.sqlite3")
    try:
        journal.connection.execute("CREATE TABLE IF NOT EXISTS probe_effects (id TEXT PRIMARY KEY)")
        if event["mode"] != "inspect":
            run = journal.admit(
                Task(
                    "text",
                    "state-probe-v1",
                    config["repository"],
                    "State probe",
                    "Diagnostic namespace only",
                ),
                "state-probe-v1",
            )
            if event["mode"] == "commit":
                journal.connection.execute(
                    "INSERT OR IGNORE INTO probe_effects VALUES ('committed')"
                )
            else:
                # Simulate a process dying in the middle of a real SQLite transaction.
                journal.connection.execute("BEGIN IMMEDIATE")
                journal.connection.execute("INSERT INTO probe_effects VALUES ('uncommitted')")
                print(json.dumps({"probe_ready": True, "run_id": run}), flush=True)
                if event["mode"] == "crash":
                    os._exit(75)
                time.sleep(120)
                journal.connection.execute("COMMIT")
        result = {
            "integrity": journal.connection.execute("PRAGMA integrity_check").fetchone()[0],
            "runs": [r[0] for r in journal.connection.execute("SELECT id FROM runs")],
            "effects": [
                r[0] for r in journal.connection.execute("SELECT id FROM probe_effects ORDER BY id")
            ],
            "admissions": journal.connection.execute(
                "SELECT count(*) FROM events WHERE kind='admitted'"
            ).fetchone()[0],
            "external_actions": 0,
        }
        print(json.dumps(result), flush=True)
        return 0
    finally:
        journal.close()


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
    if action == "state-probe":
        if event.get("mode", "").startswith("fenced-"):
            from collegium_pipeline.transport import JsonHttp

            key = environ.get("PIPELINE_CONTROL_KEY")
            if key:
                http = http or JsonHttp(config["server"], {"X-Api-Key": key})
        return state_probe(event, state / "diagnostics", config, environ, http)
    if action not in {"prepare", "status", "deliver"}:
        raise PolicyError("Unknown controller action")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    common = ["--config", str(config_path), "--journal", str(state / "journal.sqlite3")]
    if action == "prepare":
        for key in ("task_id", "title", "requirements"):
            if not isinstance(event.get(key), str) or not event[key].strip():
                raise PolicyError("Prepare requires explicit task_id, title and requirements")
        from collegium_pipeline.config import config_digest
        from collegium_pipeline.domain import Task
        from collegium_pipeline.store import Journal

        # Admit the immutable event directly; a shared intake file races concurrent callers.
        task = Task(
            "text", event["task_id"], config["repository"], event["title"], event["requirements"]
        )
        journal = Journal(state / "journal.sqlite3")
        try:
            run_id = journal.admit(task, config_digest(config))
            result = {
                "run_id": run_id,
                "state": journal.get(run_id)["state"],
                "agent_started": False,
                "mode": config["mode"],
                "acceptance_digest": task.acceptance_digest,
            }
        finally:
            journal.close()
        print(json.dumps(result))
        return 0
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
    if not config["execution_enabled"]:
        raise PolicyError("Cloud delivery is disabled")
    from collegium_pipeline.transport import JsonHttp

    http = http or JsonHttp(config["server"], {"X-Api-Key": key})
    receipt_path, receipt = cloud_fence(event, state, environ, http)
    os.environ["LAP_SERVER"] = config["server"]
    os.environ["LAP_API_KEY"] = key
    result = controller(
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
    save_receipt(receipt_path, receipt)
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        # Avoid echoing an event, environment or a provider's credential-bearing error.
        print(json.dumps({"error": type(exc).__name__, "executed": False}), file=sys.stderr)
        raise SystemExit(2) from None
