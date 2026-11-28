"""Manual cloud epic entry: same fence, journal and signed checkpoint as tickets."""

import json
import sqlite3
from contextlib import closing

from .config import config_digest
from .delivery import serial_lock
from .domain import PolicyError
from .epics import Epics
from .jira_epics import read_graph
from .native_broker import NativeGithubApp
from .recovery import (
    Checkpoints,
    ExternalRecoveryRequired,
    WriteAhead,
    intended_execution,
    reconcile_existing,
    recovery_owner,
)
from .store import Journal


def summary(result):
    return {k: v for k, v in result.items() if k not in {"graph", "validation", "review"}} | {
        "dependencies": {n["key"]: n["depends_on"] for n in result["graph"]["tickets"]}
    }


def read_status(state, config, root):
    path = state / "journal.sqlite3"
    row = None
    if path.is_file():
        with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='epics'").fetchone():
                row = db.execute(
                    "SELECT epics.document FROM epics JOIN runs ON runs.id=epics.run_id "
                    "WHERE runs.id=? AND runs.config_digest=?",
                    (root, config_digest(config)),
                ).fetchone()
    if row is None:
        raise PolicyError("Epic missing or its configuration changed")
    return {"run_id": root, **json.loads(row[0])}


def launch_evidence(journal, after):
    confirmed = []
    uncertain = {}
    rows = journal.connection.execute(
        "SELECT sequence, run_id, kind, data FROM events WHERE sequence>? "
        "AND kind IN ('effect_attempt', 'effect_not_started', 'session_created', 'launched') "
        "ORDER BY sequence",
        (after,),
    )
    for sequence, run_id, kind, raw in rows:
        data = json.loads(raw)
        if kind in {"effect_attempt", "effect_not_started"}:
            operation = data["operation"]
            effect = operation["kind"]
            if effect not in {"session_create", "prompt"}:
                continue
            key = (run_id, operation["intent"], effect)
            if kind == "effect_attempt":
                uncertain[key] = {
                    "run_id": run_id,
                    "intent": operation["intent"],
                    "effect": effect,
                    "sequence": sequence,
                }
            else:
                uncertain.pop(key, None)
        elif kind == "session_created":
            uncertain.pop((run_id, data["intent"], "session_create"), None)
        elif kind == "launched":
            confirmed.append({"run_id": run_id, "sequence": sequence, **data})
            uncertain.pop((run_id, data["intent"], "session_create"), None)
            uncertain.pop((run_id, data["intent"], "prompt"), None)
    return {
        "agent_started": bool(confirmed),
        "confirmed_launches": confirmed,
        "uncertain_launches": list(uncertain.values()),
    }


def dispatch(event, state, config, environ, http, hooks, *, profiles=None):
    guard = {}
    try:
        return _dispatch(event, state, config, environ, http, hooks, guard, profiles)
    finally:
        if not guard.get("fenced") and event.get("operation") not in {"status", "preflight"}:
            try:
                identity = hooks["cloud_identity"](environ)
            except PolicyError:
                identity = None
            if identity:
                path = (
                    state
                    / "no-dispatch"
                    / (identity["run_id"] + "-" + identity["attempt_id"] + ".json")
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                hooks["save_receipt"](path, identity)


def _dispatch(event, state, config, environ, http, hooks, guard, profiles):
    operation = event.get("operation")
    fields = {
        "preflight": {"action", "operation"},
        "prepare": {"action", "operation", "graph"},
        "import-jira": {"action", "operation", "key"},
        "status": {"action", "operation", "run_id"},
        "tick": {"action", "operation", "run_id", "live"},
        "pause": {"action", "operation", "run_id"},
        "resume": {"action", "operation", "run_id"},
    }
    if operation not in fields or set(event) != fields[operation]:
        raise PolicyError("Unknown epic operation or event fields")
    if operation == "preflight":
        from lap_mcp import connection

        resources = connection("atlassian-rovo").call("getAccessibleAtlassianResources")
        jira = config["epic"]["jira"]
        if jira is not None:
            from .jira_epics import resource_ids
            from .native_broker import ScriptTransport

            if jira["cloud_id"] not in resource_ids(resources):
                raise PolicyError("Configured Jira cloud is not accessible through the pinned MCP")
            if http is None:
                raise PolicyError("Working broker preflight requires the controller Vault key")
            ScriptTransport(config, http, None, None).scope()
        print(
            "COLLEGIUM_EPIC_PREFLIGHT="
            + json.dumps(
                {
                    "epic_scheduler_packaged": True,
                    "jira_connection_read_verified": True,
                    "jira_site_configured": config["epic"]["jira"] is not None,
                    "jira_mapping": jira,
                    "working_broker_scope_verified": jira is not None,
                    "allowed_paths": config["allowed_paths"],
                    "strategy": "direct_to_base",
                    "scheduling": config["scheduling"],
                    "execution_enabled": config["execution_enabled"],
                    "broker_enabled": config["broker_enabled"],
                    "agent_started": False,
                    "pilot_selected": False,
                }
            )
        )
        return 0
    if operation == "tick" and (
        event["live"] is not True or not config["execution_enabled"] or not config["broker_enabled"]
    ):
        raise PolicyError("Epic execution is disabled; explicit live and enabled policy required")
    # Pin intended execution independently of the emergency enable switches.
    # Only the tick gate above grants dispatch; paused preparation grants no writes.
    execution = intended_execution(config)
    # Read-only status does not dispatch, reconcile, or acquire capacity.
    if operation == "status":
        print(json.dumps(summary(read_status(state, execution, event["run_id"]))))
        return 0
    identity = hooks["cloud_identity"](environ)
    recovery_owner(config, identity)
    key = environ.get("PIPELINE_CONTROL_KEY")
    if not key or http is None:
        raise PolicyError("Epic persistence requires the controller Vault key")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        receipt_path, receipt = hooks["cloud_fence"](event, state, environ, http)
    except ExternalRecoveryRequired:
        hooks["reconcile_controller"](execution, state, http, key, profiles=profiles)
        receipt_path, receipt = hooks["cloud_fence"](event, state, environ, http)
    guard["fenced"] = True
    try:
        with serial_lock(state / "journal.sqlite3"):
            journal = Journal(state / "journal.sqlite3")
            after = None
            try:
                store = Checkpoints(execution, http, key)
                journal.before_effect = WriteAhead(
                    execution, journal, state / "artifacts", store, identity, profiles=profiles
                ).save
                engine = Epics(
                    execution,
                    journal,
                    lambda root: NativeGithubApp(execution, http, journal, root),
                    http,
                    state / "artifacts",
                )
                if operation in {"prepare", "import-jira"}:
                    graph = (
                        event["graph"]
                        if operation == "prepare"
                        else read_graph(event["key"], config)
                    )
                    after = journal.connection.execute(
                        "SELECT COALESCE(MAX(sequence),0) FROM events"
                    ).fetchone()[0]
                    result = engine.admit(graph)
                elif operation == "pause":
                    # An adopted journal can always stop new epic work. Unknown worker
                    # and broker effects stay recorded for recovery before execution resumes.
                    after = journal.connection.execute(
                        "SELECT COALESCE(MAX(sequence),0) FROM events"
                    ).fetchone()[0]
                    result = engine.pause(event["run_id"], True)
                else:
                    root = event["run_id"]
                    doc = engine.load(root)
                    if config["epic"]["jira"]:
                        source = doc["graph"]["epic"]
                        if source["source"] == "jira":
                            # Match the configured epic's immutable ID without trusting its text.
                            graph = read_graph(source["source_id"], config)
                            if graph != doc["graph"]:
                                raise PolicyError(
                                    "Jira acceptance/dependencies changed; pause and replan"
                                )
                    scratch = NativeGithubApp(execution, http, journal, root)
                    reconcile_existing(execution, journal, http, scratch, profiles=profiles)
                    after = journal.connection.execute(
                        "SELECT COALESCE(MAX(sequence),0) FROM events"
                    ).fetchone()[0]
                    journal.checkpoint({"kind": "tick", "run_id": root})
                    result = engine.step(root) if operation == "tick" else engine.pause(root, False)
                # Admission/pauses are durable too, even though they dispatch nothing.
                journal.checkpoint({"kind": "tick", "run_id": result["run_id"]})
                print(
                    "COLLEGIUM_EPIC_RESULT="
                    + json.dumps(
                        {
                            **summary(result),
                            "admission_config_digest": config_digest(execution),
                            "authorization_config_digest": config_digest(config),
                            "controller_host": "Collegium installed bundle",
                            **launch_evidence(journal, after),
                        }
                    )
                )
                return 0
            except Exception:
                if after is not None:
                    evidence = launch_evidence(journal, after)
                    if evidence["confirmed_launches"] or evidence["uncertain_launches"]:
                        print("COLLEGIUM_EPIC_LAUNCH=" + json.dumps(evidence))
                raise
            finally:
                journal.close()
    finally:
        hooks["save_receipt"](receipt_path, receipt)
