"""Collegium script entry point for the packaged serial controller."""

import json
import os
import sys
from pathlib import Path


def main(event=None, *, root=None, environ=None):
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
