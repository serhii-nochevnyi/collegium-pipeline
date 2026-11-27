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


def cloud_identity(environ):
    import re

    from collegium_pipeline.domain import PolicyError

    identity = {
        "automation_id": environ.get("LAP_AUTOMATION_ID", ""),
        "run_id": environ.get("LAP_RUN_ID", ""),
        "attempt_id": environ.get("LAP_ATTEMPT_ID", ""),
    }
    for key, prefix in (("automation_id", "aut"), ("run_id", "run"), ("attempt_id", "att")):
        if not re.fullmatch(prefix + r"_[a-zA-Z0-9]+", identity[key]):
            raise PolicyError("Cloud delivery requires platform run and attempt identities")
    return identity


def no_dispatch_accounted(prior, state, automation):
    """Skip harmless failures without hiding any older uncertain external effects."""
    attempts = prior.get("attempts", [])
    if not attempts or prior.get("status") not in {"succeeded", "failed"}:
        return False
    for attempt in attempts:
        identity = cloud_identity(
            {
                "LAP_AUTOMATION_ID": automation,
                "LAP_RUN_ID": prior["id"],
                "LAP_ATTEMPT_ID": attempt["id"],
            }
        )
        path = state / "no-dispatch" / (identity["run_id"] + "-" + identity["attempt_id"] + ".json")
        if not path.exists() or json.loads(path.read_text()) != identity:
            return False
    return True


def cloud_delivery(event, state, config, config_path, environ, http, controller):
    from collegium_pipeline.domain import PolicyError
    from collegium_pipeline.transport import JsonHttp

    receipt_path = receipt = None
    entered = False
    try:
        run_id = event.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise PolicyError("An existing run_id is required")
        key = environ.get("PIPELINE_CONTROL_KEY")
        if not key:
            raise PolicyError(
                "Bind PIPELINE_CONTROL_KEY in the project Vault before cloud dispatch"
            )
        http = http or JsonHttp(config["server"], {"X-Api-Key": key})
        from collegium_pipeline.recovery import ExternalRecoveryRequired

        try:
            receipt_path, receipt = cloud_fence(event, state, environ, http)
        except ExternalRecoveryRequired:
            if not (
                event.get("live") is True
                and config["execution_enabled"]
                and config.get("recovery_store")
            ):
                raise
            reconcile_controller(config, state, http, key)
            # Recheck the complete history; recovery never grants a blanket bypass.
            receipt_path, receipt = cloud_fence(event, state, environ, http)
        if event.get("live") is not True:
            raise PolicyError("Delivery requires explicit live=true")
        if not config["execution_enabled"]:
            raise PolicyError("Cloud delivery is disabled")
        os.environ["LAP_SERVER"] = config["server"]
        os.environ["LAP_API_KEY"] = key
        entered = True
        return controller(
            [
                "deliver",
                "--config",
                str(config_path),
                "--journal",
                str(state / "journal.sqlite3"),
                "--run-id",
                run_id,
                "--artifacts",
                str(state / "artifacts"),
                "--live",
                "--once",
            ],
            recovery=(http, key, cloud_identity(environ)),
        )
    finally:
        if receipt is not None:
            # An ordinary failed process adopts this WITH the journal; cancellation
            # or executor loss discards both, preserving the replay fence.
            save_receipt(receipt_path, receipt)
        elif not entered:
            # Never anchor on a rejected pre-dispatch run: older ambiguity must still block.
            # These records also vanish when their attempt snapshot is discarded.
            try:
                identity = cloud_identity(environ)
            except PolicyError:
                identity = None
            if identity:
                folder = state / "no-dispatch"
                folder.mkdir(mode=0o700, exist_ok=True)
                save_receipt(
                    folder / (identity["run_id"] + "-" + identity["attempt_id"] + ".json"), identity
                )


def reconcile_controller(config, state, http, key):
    from collegium_pipeline.config import config_digest
    from collegium_pipeline.domain import Task
    from collegium_pipeline.native_broker import NativeGithubApp
    from collegium_pipeline.recovery import (
        Checkpoints,
        adopt_pending_head,
        reconcile_existing,
        restore_checkpoint,
    )
    from collegium_pipeline.store import Journal

    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = Journal(state / "recovery-reads.sqlite3")
    try:
        root = scratch.admit(
            Task(
                "text",
                "recovery-reads-v1",
                config["repository"],
                "Recovery observations",
                "Read existing GitHub objects only",
            ),
            config_digest(config),
        )
        github = NativeGithubApp(config, http, scratch, root)
        checkpoints = Checkpoints(config, http, key)
        head = checkpoints.head()
        downloaded = checkpoints.get() if head else None
        if downloaded and (state / "journal.sqlite3").is_file():
            current = Journal(state / "journal.sqlite3")
            try:
                if adopt_pending_head(
                    config, current, state / "artifacts", checkpoints, checkpoint_data=downloaded
                ):
                    result = reconcile_existing(config, current, http, github)
                    return result or {"mode": "checkpoint_ack_reconciled", "external_mutations": 0}
            finally:
                current.close()
        fence = (
            json.loads((state / "cloud-fence.json").read_text())
            if (state / "cloud-fence.json").exists()
            else None
        )
        if downloaded and (not fence or fence["run_id"] != downloaded[1]["identity"]["run_id"]):
            # The adopted journal may still contain an older, confirmed pending job.
            # That does not account for the newer lost attempt: import its checkpoint first.
            return restore_checkpoint(
                config, state, checkpoints, http, github, checkpoint_data=downloaded
            )
        result = None
        if (state / "journal.sqlite3").is_file():
            journal = Journal(state / "journal.sqlite3")
            try:
                result = reconcile_existing(config, journal, http, github)
            finally:
                journal.close()
        if result is None:
            if downloaded:
                return {"mode": "no_uncertain_actions", "external_mutations": 0}
            raise ValueError("No independent checkpoint or adopted uncertain action to reconcile")
        return result
    finally:
        scratch.close()


def recovered_attempts_accounted(prior, state, automation):
    from collegium_pipeline.domain import PolicyError

    identity = cloud_identity(
        {
            "LAP_AUTOMATION_ID": automation,
            "LAP_RUN_ID": prior["id"],
            "LAP_ATTEMPT_ID": prior["attempts"][0]["id"],
        }
    )
    path = state / "reconciled" / (identity["run_id"] + ".json")
    if not path.exists():
        return False
    receipt = json.loads(path.read_text())
    if (
        receipt.get("automation_id") != automation
        or receipt.get("run_id") != prior["id"]
        or receipt.get("attempt_ids") != [a["id"] for a in prior["attempts"]]
        or not isinstance(receipt.get("checkpoint"), str)
        or receipt.get("external_mutations") != 0
    ):
        raise PolicyError("Cloud reconciliation receipt identity differs")
    from collegium_pipeline.recovery import validate_import_receipt
    from collegium_pipeline.store import Journal

    journal = Journal(state / "journal.sqlite3")
    try:
        validate_import_receipt(journal, receipt)
    finally:
        journal.close()
    return True


def cloud_fence(event, state, environ, http, *, diagnostic=False):
    """Refuse replay when the platform discarded a previous attempt's journal.

    Platform run history is outside the attempt snapshot. A receipt inside the
    adopted snapshot proves that a previous delivery's journal survived with it.
    A lost/cancelled attempt has no such receipt and must be reconciled, not replayed.
    """
    from collegium_pipeline.domain import PolicyError
    from collegium_pipeline.recovery import ExternalRecoveryRequired

    identity = cloud_identity(environ)
    automation, run, attempt = (identity[k] for k in ("automation_id", "run_id", "attempt_id"))
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
    if any(history.get(k) for k in ("has_more", "next_cursor", "next_page", "next")):
        raise PolicyError("Paginated cloud history; delivery replay refused")
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
        data = prior.get("item", {}).get("event", {}).get("data")
        if not isinstance(data, dict):
            continue  # The entry point rejects non-object data before any action.

        unsafe = (
            data.get("action") == "state-probe" and data.get("mode") == "fenced-hold"
            if diagnostic
            else data.get("action") == "deliver"
        )
        if unsafe and not (
            not diagnostic
            and (
                no_dispatch_accounted(prior, state, automation)
                or recovered_attempts_accounted(prior, state, automation)
            )
        ):
            raise ExternalRecoveryRequired(
                "Uncheckpointed cloud execution; reconcile before delivery replay"
            )
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
                if event["mode"] == "hold":
                    # This autocommit distinguishes whole-snapshot cancellation from
                    # ordinary SQLite transaction rollback after process death.
                    journal.connection.execute(
                        "INSERT OR IGNORE INTO probe_effects VALUES ('attempt-committed')"
                    )
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


def github_recovery_probe(event, state, config, environ, http):
    """Fixed App-backed fixture; drop a real mutation reply before its journal receipt."""
    import time

    from collegium_pipeline.broker import PRBroker
    from collegium_pipeline.config import config_digest
    from collegium_pipeline.domain import PolicyError, Task
    from collegium_pipeline.native_broker import NativeGithubApp
    from collegium_pipeline.recovery import Checkpoints, WriteAhead, restore_checkpoint
    from collegium_pipeline.store import Journal
    from collegium_pipeline.transport import RemoteError

    modes = {"github-prepare", "github-commit", "github-pr", "github-recover", "github-inspect"}
    if set(event) != {"action", "mode"} or event["mode"] not in modes:
        raise PolicyError("Unknown fixed GitHub recovery probe")
    if config["execution_enabled"] or config["broker_enabled"]:
        raise PolicyError("GitHub probes require disabled production delivery and broker")
    if config["allowed_paths"] != ["tests/test_live_service.py"]:
        raise PolicyError("GitHub fixture must match the existing one-file App scope")
    identity = cloud_identity(environ)
    if identity["automation_id"] != config["recovery_store"]["owner"]:
        raise PolicyError("GitHub probe belongs to another controller")
    current, _ = http.request(
        "GET", "/api/automations/" + identity["automation_id"] + "/runs/" + identity["run_id"]
    )
    if (
        current["status"] != "running"
        or current["item"]["event"]["data"] != event
        or len(current["attempts"]) != 1
        or current["attempts"][0]["n"] != 1
        or current["attempts"][0]["id"] != identity["attempt_id"]
    ):
        raise PolicyError("GitHub probe cannot replay an uncertain attempt")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = environ.get("PIPELINE_CONTROL_KEY")
    checkpoints = Checkpoints(config, http, key, namespace="diagnostic")
    fixture = {
        "tests/test_live_service.py": (
            '"""Service-only live GitHub checkpoint recovery fixture."""\n\n'
            "import unittest\n\n\n"
            "class LiveCheckpointRecoveryTest(unittest.TestCase):\n"
            "    def test_fixed_fixture(self):\n"
            '        self.assertEqual(len("checkpoint-recovery"), 19)\n'
        )
    }
    title = "[Service diagnostic] GitHub checkpoint recovery"
    description = (
        "Service-only commit/PR interruption and duplicate-prevention test. "
        "One fixed passing fixture; no product pilot, Jira task, merge or deploy."
    )
    journal = Journal(state / "journal.sqlite3")
    try:
        if event["mode"] == "github-prepare":
            root = journal.admit(
                Task(
                    "text",
                    "github-recovery-probe-v1",
                    config["repository"],
                    title,
                    "Create one fixed service commit and PR; cancel before "
                    "each receipt, reconcile, replay without duplicates; never merge.",
                ),
                config_digest(config),
                purpose="readiness",
            )
        else:
            rows = journal.connection.execute(
                "SELECT id FROM runs WHERE source='text' AND source_id=?",
                ("github-recovery-probe-v1",),
            ).fetchall()
            if len(rows) != 1:
                raise PolicyError("Prepare the canonical GitHub diagnostic first")
            root = rows[0][0]
        if journal.get(root)["config_digest"] != config_digest(config):
            raise PolicyError("GitHub diagnostic configuration changed")
        events = journal.events(root)

        def result_for(key):
            found = [
                e["data"]["result"]
                for e in events
                if e["kind"] == "broker_done" and e["data"]["key"] == key
            ]
            if not found:
                raise PolicyError("Required previous GitHub probe phase has not reconciled")
            return found[-1]

        if event["mode"] == "github-recover":
            journal.close()
            downloaded = checkpoints.get()
            operation = downloaded[1]["operation"]
            if (
                operation["kind"] != "broker"
                or operation["run_id"] != root
                or operation["operation"] not in {"commit", "pr"}
            ):
                raise PolicyError("Checkpoint is not this GitHub diagnostic's uncertain mutation")
            scratch = Journal(state / "github-recovery-reads.sqlite3")
            try:
                scratch_root = scratch.admit(
                    Task(
                        "text",
                        "github-observations-v1",
                        config["repository"],
                        "GitHub recovery observations",
                        "Read existing effects only",
                    ),
                    config_digest(config),
                )
                github = NativeGithubApp(config, http, scratch, scratch_root)
                receipt = restore_checkpoint(
                    config,
                    state,
                    checkpoints,
                    http,
                    github,
                    diagnostic=True,
                    checkpoint_data=downloaded,
                )
            finally:
                scratch.close()
            print(json.dumps(receipt))
            return 0
        if event["mode"] == "github-inspect":
            print(
                json.dumps(
                    {
                        "root": root,
                        "branch": "collegium/" + root,
                        "integrity": journal.connection.execute(
                            "PRAGMA integrity_check"
                        ).fetchone()[0],
                        "admissions": sum(e["kind"] == "admitted" for e in events),
                        "done": [e["data"] for e in events if e["kind"] == "broker_done"],
                        "agent_started": False,
                    }
                )
            )
            return 0
        # Only this fixed fixture receives manual service-test write authority.
        # The original frozen config is checkpointed; production switches stay false.
        authority = {**config, "execution_enabled": True, "broker_enabled": True}
        github = NativeGithubApp(authority, http, journal, root)
        broker = PRBroker(authority, journal, github)
        journal.before_effect = WriteAhead(
            config, journal, state / "artifacts", checkpoints, identity
        ).save
        if event["mode"] == "github-prepare":
            done = [
                e for e in events if e["kind"] == "broker_done" and e["data"]["key"] == "branch"
            ]
            base = done[-1]["data"]["result"]["head"] if done else github.ref(config["base_branch"])
            branch = broker.branch(root, base)
            print(
                json.dumps({"root": root, "branch": branch, "base": base, "agent_started": False})
            )
            return 0
        branch = "collegium/" + root
        base = result_for("branch")["head"]
        operation = "commit" if event["mode"] == "github-commit" else "pr"
        original_mutate = github.mutate
        mutations = []

        def withhold_reply(kind, payload):
            if kind != operation or mutations:
                raise PolicyError("Unexpected GitHub diagnostic mutation")
            mutations.append(kind)
            original_mutate(kind, payload)
            # The remote App run has succeeded, but the caller cannot record broker_done.
            print(
                json.dumps(
                    {
                        "probe_ready": True,
                        "operation": kind,
                        "root": root,
                        "branch": branch,
                        "response_withheld": True,
                    }
                ),
                flush=True,
            )
            time.sleep(120)
            raise RemoteError("Deliberately withheld service mutation reply", unknown_outcome=True)

        github.mutate = withhold_reply
        if operation == "commit":
            result = {"head": broker.commit(root, branch, base, fixture, 0)}
        else:
            head = result_for("commit:0")["head"]
            journal.connection.execute(
                "CREATE TABLE IF NOT EXISTS deliveries("
                "run_id TEXT PRIMARY KEY REFERENCES runs(id),document TEXT NOT NULL)"
            )
            journal.connection.execute(
                "INSERT INTO deliveries VALUES(?,?) ON CONFLICT(run_id) "
                "DO UPDATE SET document=excluded.document",
                (root, json.dumps({"head": head, "base": base})),
            )
            result = broker.open_pr(root, branch, head, base, title, description=description)
        print(
            json.dumps(
                {
                    "root": root,
                    "branch": branch,
                    "operation": operation,
                    "result": result,
                    "mutation_calls": len(mutations),
                    "agent_started": False,
                }
            )
        )
        return 0
    finally:
        journal.close()


def recovery_probe(event, state, config, environ, http):
    """One fixed private-Claude diagnostic, in a separate journal; no GitHub mutations."""
    import time

    from collegium_pipeline.config import config_digest
    from collegium_pipeline.domain import PolicyError, Selection, Task
    from collegium_pipeline.effort import probe_command
    from collegium_pipeline.platform import Collegium, WorkerBinding
    from collegium_pipeline.recovery import Checkpoints, WriteAhead, restore_checkpoint
    from collegium_pipeline.store import Journal

    if isinstance(event.get("mode"), str) and event["mode"].startswith("github-"):
        return github_recovery_probe(event, state, config, environ, http)
    if set(event) != {"action", "mode"} or event["mode"] not in {
        "connection",
        "start",
        "recover",
        "inspect",
    }:
        raise PolicyError("Unknown fixed recovery probe")
    if config["execution_enabled"] or config["broker_enabled"]:
        raise PolicyError("Recovery probes require disabled delivery and broker")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if event["mode"] == "inspect":
        if not (state / "journal.sqlite3").is_file():
            raise PolicyError("No restored diagnostic journal")
        journal = Journal(state / "journal.sqlite3")
        try:
            rows = journal.connection.execute(
                "SELECT id FROM runs WHERE source_id='native-recovery-probe-v1'"
            ).fetchall()
            result = {
                "runs": [r[0] for r in rows],
                "integrity": journal.connection.execute("PRAGMA integrity_check").fetchone()[0],
                "launches": [
                    e["data"] for r in rows for e in journal.events(r[0]) if e["kind"] == "launched"
                ],
                "admissions": sum(
                    e["kind"] == "admitted" for r in rows for e in journal.events(r[0])
                ),
                "github_mutations": 0,
            }
        finally:
            journal.close()
        print(json.dumps(result))
        return 0
    key = environ.get("PIPELINE_CONTROL_KEY")
    checkpoints = Checkpoints(config, http, key, namespace="diagnostic")
    if event["mode"] == "connection":
        print(
            json.dumps(
                {
                    "recovery_store_authenticated": True,
                    "head": checkpoints.head(),
                    "agent_started": False,
                    "github_mutations": 0,
                }
            )
        )
        return 0
    if event["mode"] == "recover":
        downloaded = checkpoints.get()
        if downloaded[1]["operation"]["kind"] == "broker":
            raise PolicyError("Use github-recover for the current GitHub diagnostic checkpoint")
        print(
            json.dumps(
                restore_checkpoint(
                    config,
                    state,
                    checkpoints,
                    http,
                    None,
                    diagnostic=True,
                    checkpoint_data=downloaded,
                )
            )
        )
        return 0
    identity = cloud_identity(environ)
    if identity["automation_id"] != config["recovery_store"]["owner"]:
        raise PolicyError("Recovery probe belongs to another controller")
    current, _ = http.request(
        "GET", "/api/automations/" + identity["automation_id"] + "/runs/" + identity["run_id"]
    )
    if (
        current["status"] != "running"
        or current["item"]["event"]["data"] != event
        or len(current["attempts"]) != 1
        or current["attempts"][0]["n"] != 1
        or current["attempts"][0]["id"] != identity["attempt_id"]
    ):
        raise PolicyError("Recovery probe cannot replay an uncertain attempt")
    if checkpoints.head() is not None:
        raise PolicyError("Recover the existing checkpoint; never launch another probe worker")
    row = config["workers"]["executor"]
    selection = Selection(**row["selection"])
    binding = WorkerBinding(**{**row, "selection": selection})
    prompt = (
        "Recovery service diagnostic only. Run the exact command below as your first Bash tool. "
        'Then reply only {"diagnostic":"checkpoint-recovery-ok"}. '
        "Use no other tools, no MCP, no repository changes or product work.\n"
        + probe_command(binding.harness)
    )
    journal = Journal(state / "journal.sqlite3")
    try:
        run = journal.admit(
            Task(
                "text",
                "native-recovery-probe-v1",
                config["repository"],
                "Native checkpoint recovery diagnostic",
                prompt,
            ),
            config_digest(config),
            purpose="readiness",
        )
        journal.before_effect = WriteAhead(
            config, journal, state / "artifacts", checkpoints, identity
        ).save
        launch = Collegium(http).dispatch(
            journal,
            run,
            0,
            binding=binding,
            selection=selection,
            prompt=prompt,
            execution_enabled=True,
        )
        print(
            json.dumps({"probe_ready": True, "root": run, **launch, "github_mutations": 0}),
            flush=True,
        )
        time.sleep(120)
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
            "cloud_checkpoint": (
                json.loads((state / "cloud-fence.json").read_text())
                if (state / "cloud-fence.json").exists()
                else None
            ),
            "no_dispatch_records": len(list((state / "no-dispatch").glob("*.json"))),
        }
        print(json.dumps(result))
        return 0
    if action == "recovery-probe":
        from collegium_pipeline.transport import JsonHttp

        key = environ.get("PIPELINE_CONTROL_KEY")
        if not key:
            raise PolicyError("Controller Vault key is required for recovery probe")
        http = http or JsonHttp(config["server"], {"X-Api-Key": key})
        return recovery_probe(event, state / "recovery-diagnostics", config, environ, http)
    if action == "reconcile":
        if event != {"action": "reconcile"}:
            raise PolicyError("Reconciliation accepts no event-selected identities or payloads")
        key = environ.get("PIPELINE_CONTROL_KEY")
        if not key:
            raise PolicyError("Controller Vault key is required for recovery")
        from collegium_pipeline.transport import JsonHttp

        http = http or JsonHttp(config["server"], {"X-Api-Key": key})
        result = reconcile_controller(config, state, http, key)
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
    if action == "deliver":
        return cloud_delivery(event, state, config, config_path, environ, http, controller)
    run_id = event.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PolicyError("An existing run_id is required")
    return controller(["status", *common, "--run-id", run_id])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        # Avoid echoing an event, environment or a provider's credential-bearing error.
        print(
            json.dumps({"error": type(exc).__name__, "outcome": "inspect_run_and_journal"}),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
