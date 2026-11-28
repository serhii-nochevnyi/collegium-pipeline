"""Manual, read-only cloud investigation lane with independent signed recovery."""

import json

from .config import config_digest
from .delivery import serial_lock
from .domain import PolicyError
from .investigation_sources import GitSources
from .investigation_workers import InvestigationJobs
from .investigations import Investigations
from .native_broker import NativeGithubApp
from .platform import agent_digest
from .recovery import (
    Checkpoints,
    ExternalRecoveryRequired,
    WriteAhead,
    intended_execution,
    reconcile_existing,
    recovery_owner,
)
from .store import Journal


def preflight(config, http, sources):
    if config["broker_enabled"] or config["execution_enabled"]:
        raise PolicyError("Installed investigation authority must stay disabled at rest")
    import tempfile

    from .artifacts import Artifacts

    with tempfile.TemporaryDirectory() as directory:
        journal = Journal(directory + "/journal.sqlite3")
        try:
            jobs = InvestigationJobs(config, journal, http, Artifacts(directory + "/artifacts"))
            from .investigation_policy import variants

            for selection in variants():
                binding = jobs.binding(selection)
                row, _ = http.request("GET", "/api/agents/" + binding.agent_id)
                if agent_digest(row) != binding.approved_agent_digest:
                    raise PolicyError("Investigation worker binding drifted")
                if (
                    row.get("model_connection_id") != config["model_connection_id"]
                    or row.get("model") != selection.model
                    or row.get("config", {}).get("effort") != selection.effort
                    or row.get("harness") != "claude-code"
                ):
                    raise PolicyError("Investigation private model/effort configuration differs")
                grants = row.get("config", {}).get("repositories", [])
                if grants != [
                    {
                        "type": "github_repository",
                        "url": "https://github.com/" + config["repository"],
                        "connection": config["github_connection_id"],
                        "access": "read",
                    }
                ]:
                    raise PolicyError(
                        "Investigation workers require the exact read-only repository grant"
                    )
            return {
                **sources.metadata(),
                "worker_bindings_verified": len(variants()),
                "agent_started": False,
                "runtime_effort_verified": False,
                "automation_resumed": False,
                "publication_allowed": False,
            }
        finally:
            journal.close()


def dispatch(event, state, config, environ, http, hooks, *, sources=None):
    fields = {
        "preflight": {"action", "operation"},
        "prepare": {"action", "operation", "intake"},
        "status": {"action", "operation", "run_id"},
        "tick": {"action", "operation", "run_id", "live"},
        "pause": {"action", "operation", "run_id"},
        "resume": {"action", "operation", "run_id"},
    }
    operation = event.get("operation")
    if (
        event.get("action") != "investigate"
        or operation not in fields
        or set(event) != fields[operation]
    ):
        raise PolicyError("Unknown investigation operation or event fields")
    if config["broker_enabled"] or config["execution_enabled"]:
        raise PolicyError("Investigation requires disabled installed authority")
    if operation == "tick" and event["live"] is not True:
        raise PolicyError("Paid investigation dispatch requires explicit live=true")
    identity = hooks["cloud_identity"](environ)
    recovery_owner(config, identity)
    key = environ.get("PIPELINE_CONTROL_KEY")
    if not key or http is None:
        raise PolicyError("Investigation requires its project Vault control key")
    sources = sources or GitSources(config)
    if operation == "preflight":
        print("COLLEGIUM_INVESTIGATION_PREFLIGHT=" + json.dumps(preflight(config, http, sources)))
        return 0
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    execution = intended_execution(config)
    fence = receipt = None
    entered = False
    try:
        try:
            fence, receipt = hooks["cloud_fence"](event, state, environ, http, investigation=True)
        except ExternalRecoveryRequired:
            hooks["reconcile_controller"](execution, state, http, key)
            fence, receipt = hooks["cloud_fence"](event, state, environ, http, investigation=True)
        entered = True
        with serial_lock(state / "journal.sqlite3"):
            journal = Journal(state / "journal.sqlite3")
            try:
                journal.before_effect = WriteAhead(
                    execution,
                    journal,
                    state / "artifacts",
                    Checkpoints(execution, http, key),
                    identity,
                ).save
                engine = Investigations(execution, journal, http, state / "artifacts")
                if operation == "prepare":
                    intake = event["intake"]
                    # Shape is checked before network or source capture.
                    if not isinstance(intake, dict) or set(intake) != {
                        "task",
                        "head",
                        "sources",
                        "risk_flags",
                        "constraints",
                    }:
                        raise PolicyError("Investigation intake schema differs")
                    from .domain import Task

                    if Task(**intake["task"]).repository != config["repository"]:
                        raise PolicyError("Intake repository differs")
                    result = engine.admit(
                        intake, sources.capture(intake["head"], intake["sources"])
                    )
                else:
                    root = event["run_id"]
                    engine.load(root)
                    if operation == "tick":
                        reconcile_existing(
                            execution,
                            journal,
                            http,
                            NativeGithubApp(execution, http, journal, root),
                        )
                        journal.checkpoint({"kind": "tick", "run_id": root})
                        engine.step(root)
                    elif operation in {"pause", "resume"}:
                        engine.pause(root, operation == "pause")
                    result = {"run_id": root}
                if operation != "status":
                    journal.checkpoint({"kind": "tick", "run_id": result["run_id"]})
                print(
                    "COLLEGIUM_INVESTIGATION_RESULT="
                    + json.dumps(
                        {
                            **engine.status(result["run_id"]),
                            "controller_host": "Collegium installed bundle",
                            "config_digest": config_digest(execution),
                            "jira_writes": 0,
                            "github_mutations": 0,
                            "pilot_selected": False,
                        }
                    ),
                    flush=True,
                )
            finally:
                journal.close()
    finally:
        if entered:
            hooks["save_receipt"](fence, receipt)
        elif operation not in {"status", "preflight"}:
            target = (
                state
                / "no-dispatch"
                / (identity["run_id"] + "-" + identity["attempt_id"] + ".json")
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            hooks["save_receipt"](target, identity)
    return 0
