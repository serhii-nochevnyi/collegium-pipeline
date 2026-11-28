"""Independent write-ahead checkpoints and conservative external reconciliation."""

import base64
import hashlib
import hmac
import json
import re
import sqlite3
import tempfile
import time
import zlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from .domain import PolicyError, digest
from .native_broker import binding_digest

CHUNK = 120_000
MAX_RAW = 24_000_000
MAX_COMPRESSED = 8_000_000


class ExternalRecoveryRequired(PolicyError):
    """A previous attempt has no adopted journal/receipt."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def mac(value, key):
    return hmac.new(key.encode(), canonical(value), hashlib.sha256).hexdigest()


def unpack(data):
    if len(data) > MAX_COMPRESSED:
        raise PolicyError("Recovery checkpoint exceeds the compressed bound")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(data, MAX_RAW + 1)
    if len(raw) > MAX_RAW or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise PolicyError("Recovery checkpoint is oversized or incomplete")
    return json.loads(raw)


class Checkpoints:
    def __init__(
        self, config, http, key, *, namespace="delivery", clock=time.monotonic, pause=time.sleep
    ):
        self.config, self.http, self.key = config, http, key
        if namespace not in {"delivery", "diagnostic", "service"}:
            raise PolicyError("Unknown recovery namespace")
        self.namespace = namespace
        self.binding = config.get("recovery_store")
        if not self.binding or not key:
            raise PolicyError("Independent checkpoint store must be bound before cloud delivery")
        self.path = "/api/automations/" + self.binding["automation_id"]
        self.clock, self.pause = clock, pause
        self.checked = False

    def scope(self):
        if self.checked:
            return
        row, _ = self.http.request("GET", self.path)
        code, _ = self.http.request("GET", self.path + "/code")
        target = row["target"]
        if (
            binding_digest(row, code) != self.binding["approved_digest"]
            or row["project_id"] != self.config["project_id"]
            or row["status"] != "paused"
            or target.get("kind") != "script"
            or target.get("secrets") != ["project/PIPELINE_CONTROL_KEY"]
            or any(target.get(k) for k in ("repositories", "mcp_servers", "variables"))
            or json.loads(code["current"]["files"]["recovery_scope.json"])
            != {"owner": self.binding["owner"]}
        ):
            raise PolicyError("Recovery store scope/code differs from its binding")
        self.checked = True

    def call(self, action, **fields):
        self.scope()
        event = {
            "action": action,
            "owner": self.binding["owner"],
            "namespace": self.namespace,
            "request_id": uuid4().hex,
            **fields,
        }
        body = {**event, "mac": mac(event, self.key)}
        # An unknown submission is looked up, never blindly resubmitted.
        from .transport import RemoteError

        item_id = None
        try:
            started, _ = self.http.request("POST", self.path + "/run", {"data": body})
            run = (started.get("run") or {}).get("id")
            item_id = (started.get("item") or {}).get("id")
        except RemoteError as exc:
            if not exc.unknown_outcome:
                raise
            run = None
        deadline = self.clock() + 120
        while self.clock() < deadline:
            if not run:
                history, _ = self.http.request("GET", self.path + "/runs?limit=100")
                if item_id:
                    matches = [r for r in history["runs"] if r.get("item_id") == item_id]
                    if len(matches) > 1:
                        raise PolicyError("Checkpoint queue identity is ambiguous")
                    run = matches[0]["id"] if matches else None
                else:
                    for summary in history["runs"]:
                        detail, _ = self.http.request("GET", self.path + "/runs/" + summary["id"])
                        if detail.get("item", {}).get("event", {}).get("data") == body:
                            run = detail["id"]
                            break
            if run:
                detail, _ = self.http.request("GET", self.path + "/runs/" + run)
                if item_id and detail.get("item_id") != item_id:
                    raise PolicyError("Checkpoint run differs from its queued item")
                if detail["status"] not in {"queued", "waiting", "running"}:
                    if detail["status"] != "succeeded" or detail.get("output_cut") is not False:
                        raise PolicyError(
                            "Independent checkpoint call failed; external effect refused"
                        )
                    result = json.loads(detail["output_tail"])
                    signature = result.pop("mac", "")
                    if (
                        not hmac.compare_digest(mac(result, self.key), str(signature))
                        or result.get("request_id") != event["request_id"]
                        or result.get("owner") != self.binding["owner"]
                        or result.get("namespace") != self.namespace
                    ):
                        raise PolicyError("Checkpoint response authentication differs")
                    return result
            self.pause(1)
        raise PolicyError(
            f"Checkpoint acknowledgement unknown (action={action}, item={item_id}, run={run}); "
            "external effect refused"
        )

    def head(self):
        return self.call("head")["head"]

    def put(self, value, parent):
        raw = canonical(value)
        if len(raw) > MAX_RAW:
            raise PolicyError("Recovery state exceeds the uncompressed checkpoint bound")
        data = zlib.compress(raw, 9)
        if len(data) > MAX_COMPRESSED:
            raise PolicyError("Recovery state exceeds the compressed checkpoint bound")
        identity = hashlib.sha256(data).hexdigest()
        result = self.call("begin", checkpoint=identity, parent=parent, size=len(data))
        if not result.get("committed"):
            for index in range((len(data) + CHUNK - 1) // CHUNK):
                self.call(
                    "chunk",
                    checkpoint=identity,
                    index=index,
                    data=base64.b64encode(data[index * CHUNK : (index + 1) * CHUNK]).decode(),
                )
            result = self.call("finish", checkpoint=identity)
        if not result.get("committed") or result["head"]["checkpoint"] != identity:
            raise PolicyError("Independent checkpoint was not adopted")
        return identity

    def get(self):
        head = self.head()
        if not head:
            raise PolicyError("No independent recovery checkpoint")
        if type(head["size"]) is not int or not 0 < head["size"] <= MAX_COMPRESSED:
            raise PolicyError("Invalid recovery size")
        data = b"".join(
            base64.b64decode(
                self.call("read", checkpoint=head["checkpoint"], index=index)["data"], validate=True
            )
            for index in range((head["size"] + CHUNK - 1) // CHUNK)
        )
        if len(data) != head["size"] or hashlib.sha256(data).hexdigest() != head["checkpoint"]:
            raise PolicyError("Checkpoint download digest differs")
        return head["checkpoint"], unpack(data)


class WriteAhead:
    def __init__(self, config, journal, artifacts, checkpoints, identity):
        self.config, self.journal = config, journal
        self.artifacts, self.checkpoints, self.identity = Path(artifacts), checkpoints, identity
        head = checkpoints.head()
        self.parent = head["checkpoint"] if head else None
        self.local_head = self.artifacts.parent / "checkpoint-head.json"
        local = json.loads(self.local_head.read_text()) if self.local_head.exists() else None
        if local != self.parent:
            adopted = adopt_pending_head(config, journal, self.artifacts, checkpoints)
            if not adopted:
                raise PolicyError(
                    "Independent checkpoint advanced; reconcile before another effect"
                )

    def save(self, operation):
        from .config import config_digest

        if self.journal.connection.in_transaction:
            raise PolicyError("Checkpoint cannot capture an open journal transaction")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "journal.sqlite3"
            backup = sqlite3.connect(path)
            self.journal.connection.backup(backup)
            backup.close()
            data = base64.b64encode(path.read_bytes()).decode()
        artifacts = {}
        if self.artifacts.exists():
            from .artifacts import Artifacts

            store = Artifacts(self.artifacts)
            for path in self.artifacts.iterdir():
                if not re.fullmatch(r"[a-f0-9]{64}\.json", path.name) or path.is_symlink():
                    raise PolicyError("Unexpected recovery artifact path")
                artifacts[path.stem] = store.get(path.stem)
        value = {
            "schema_version": "checkpoint/v1",
            "identity": self.identity,
            "config_digest": config_digest(self.config),
            "operation": operation,
            "journal": data,
            "artifacts": artifacts,
        }
        expected = hashlib.sha256(zlib.compress(canonical(value), 9)).hexdigest()
        pending = {
            "checkpoint": expected,
            "parent": self.parent,
            "identity": self.identity,
            "config_digest": config_digest(self.config),
            "operation_digest": digest(operation),
        }
        pending_path = self.artifacts.parent / "checkpoint-pending.json"
        pending_tmp = pending_path.with_suffix(".tmp")
        pending_tmp.write_bytes(canonical(pending))
        pending_tmp.replace(pending_path)
        self.parent = self.checkpoints.put(value, self.parent)
        temporary = self.local_head.with_suffix(".tmp")
        temporary.write_bytes(canonical(self.parent))
        temporary.replace(self.local_head)
        pending_path.unlink(missing_ok=True)
        return self.parent


def adopt_pending_head(config, journal, artifacts, checkpoints, *, checkpoint_data=None):
    """Adopt only our exact committed upload whose actual effect was never called."""
    from .config import config_digest

    state = Path(artifacts).parent
    pending_path = state / "checkpoint-pending.json"
    if not pending_path.exists():
        return False
    pending = json.loads(pending_path.read_text())
    local_path = state / "checkpoint-head.json"
    local = json.loads(local_path.read_text()) if local_path.exists() else None
    if local == pending["checkpoint"]:
        current = checkpoints.head()
        if not current or current["checkpoint"] != local:
            return False
        pending_path.unlink()
        return True
    if local != pending["parent"] or pending["config_digest"] != config_digest(config):
        return False
    head = checkpoints.head()
    if not head or head["checkpoint"] != pending["checkpoint"] or head["parent"] != local:
        return False
    checkpoint, value = checkpoint_data if checkpoint_data is not None else checkpoints.get()
    if (
        checkpoint != pending["checkpoint"]
        or value["identity"] != pending["identity"]
        or value["identity"]["automation_id"] != config["recovery_store"]["owner"]
        or value["config_digest"] != config_digest(config)
        or digest(value["operation"]) != pending["operation_digest"]
    ):
        return False
    operation = value["operation"]
    if not journal.effect_not_started(operation):
        if operation["kind"] != "tick":
            return False
        # Initial tick failure happens before the state machine. Require the captured
        # run rows/events and delivery documents to remain exactly unchanged.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.sqlite3"
            path.write_bytes(base64.b64decode(value["journal"], validate=True))
            saved = sqlite3.connect(path)
            saved.row_factory = sqlite3.Row
            try:
                for row in saved.execute("SELECT * FROM runs"):
                    if dict(row) != journal.get(row["id"]):
                        return False
                    events = saved.execute(
                        "SELECT * FROM events WHERE run_id=? ORDER BY sequence", (row["id"],)
                    ).fetchall()
                    current = journal.connection.execute(
                        "SELECT * FROM events WHERE run_id=? ORDER BY sequence", (row["id"],)
                    ).fetchall()
                    if [dict(e) for e in events] != [dict(e) for e in current]:
                        return False
                if saved.execute("SELECT 1 FROM sqlite_master WHERE name='deliveries'").fetchone():
                    for row in saved.execute("SELECT * FROM deliveries"):
                        current = journal.connection.execute(
                            "SELECT * FROM deliveries WHERE run_id=?", (row["run_id"],)
                        ).fetchone()
                        if current is None or dict(row) != dict(current):
                            return False
            finally:
                saved.close()
    temporary = local_path.with_suffix(".tmp")
    temporary.write_bytes(canonical(checkpoint))
    temporary.replace(local_path)
    pending_path.unlink()
    journal.record(
        operation["run_id"],
        "checkpoint_ack_reconciled",
        {
            "checkpoint": checkpoint,
            "origin": pending["identity"],
            "external_effect_started": False,
        },
    )
    return True


def session_name(intent):
    if not re.fullmatch(r"[a-f0-9-]{36}", intent):
        raise PolicyError("Invalid launch intent")
    return "pipeline-" + intent.replace("-", "")


def reconcile_workers(config, journal, http):
    """Observe identities only. No new session, prompt or quality acceptance."""
    from .domain import Selection
    from .platform import Collegium, WorkerBinding, agent_digest

    sessions = None
    recovered = []
    for row in journal.connection.execute(
        "SELECT id FROM runs WHERE pending_intent IS NOT NULL"
    ).fetchall():
        run = journal.get(row[0])
        events = journal.events(run["id"])
        intent = run["pending_intent"]
        launch = [e for e in events if e["kind"] == "launched" and e["data"]["intent"] == intent]
        if launch:
            continue
        dispatch = [
            e["data"]
            for e in events
            if e["kind"] == "dispatch_intent" and e["data"]["intent"] == intent
        ]
        if len(dispatch) != 1:
            raise PolicyError("Recovery launch intent is ambiguous")
        selection = Selection(**dispatch[0]["selection"])
        rows = [b for b in config["workers"].values() if b["selection"] == asdict(selection)]
        if len(rows) != 1:
            raise PolicyError("Recovery worker binding is ambiguous")
        binding = WorkerBinding(**{**rows[0], "selection": selection})
        agent, _ = http.request("GET", "/api/agents/" + binding.agent_id)
        if agent_digest(agent) != binding.approved_agent_digest:
            raise PolicyError("Recovery worker configuration changed")
        requests = [
            e["data"]
            for e in events
            if e["kind"] == "dispatch_request" and e["data"]["intent"] == intent
        ]
        if len(requests) != 1 or digest(requests[0]["request"]) != dispatch[0]["request_digest"]:
            raise PolicyError("Original recovery request is missing or changed")
        request = requests[0]["request"]
        if (
            request["binding"] != asdict(binding)
            or request["config"] != run["config_digest"]
            or request["acceptance"] != run["task"]
        ):
            raise PolicyError("Original recovery request scope differs")
        if sessions is None:
            sessions, headers = http.request(
                "GET", "/session?project_id=" + config["project_id"] + "&foreign=none"
            )
            if headers.get("x-next-after") or not isinstance(sessions, list):
                raise PolicyError("Incomplete recovery session listing")
        found = [
            s
            for s in sessions
            if s.get("name") == session_name(intent) and s.get("agent_id") == binding.agent_id
        ]
        if not found and journal.effect_not_started(
            {"kind": "session_create", "run_id": run["id"], "intent": intent}
        ):
            if run["state"] == "reconciling":
                with journal.transaction():
                    journal.connection.execute(
                        "UPDATE runs SET state=?,version=version+1 WHERE id=?",
                        (requests[0]["stage"], run["id"]),
                    )
                    journal._event(
                        run["id"], "launch_reconciled", {"intent": intent, "not_started": True}
                    )
            recovered.append({"session_id": None, "turn_id": None, "not_started": True})
            continue
        if len(found) != 1:
            raise PolicyError("Named session absent or ambiguous; no replacement launched")
        session = found[0]
        if any(
            session.get(k) != v
            for k, v in {
                "project_id": binding.project_id,
                "runtime": binding.runtime,
                "harness": binding.harness,
                "environment_id": binding.environment_id,
            }.items()
        ):
            raise PolicyError("Recovery session identity differs")
        known = [
            e["data"]["session_id"]
            for e in events
            if e["kind"] == "session_created" and e["data"]["intent"] == intent
        ]
        if known and known != [session["id"]]:
            raise PolicyError("Recovery session differs from the journal")
        # The user.message is the server's stored exact request and trace joins it to its turn.
        history, _ = http.request("GET", "/session/" + session["id"] + "/runtime_events/list")
        if history.get("has_more"):
            raise PolicyError("Recovery runtime events are incomplete")
        prompt = request["prompt"]
        messages = [e for e in history["data"] if e.get("type") == "user.message"]
        matching = [
            e
            for e in messages
            if "".join(p.get("text", "") for p in e.get("content", []) if p.get("type") == "text")
            == prompt
        ]
        if len(messages) > 1 or len(matching) != len(messages):
            raise PolicyError("Recovery prompt differs or is ambiguous")
        turn_id = None
        if matching:
            trace = matching[0].get("traceparent", "").split("-")
            if len(trace) != 4 or not re.fullmatch(r"[a-f0-9]{32}", trace[1]):
                raise PolicyError("Recovery prompt trace is absent")
            turns, _ = http.request("GET", "/api/agents/" + binding.agent_id + "/runs?limit=100")
            found_turns = [
                r
                for r in turns["runs"]
                if r.get("session_id") == session["id"] and r.get("trace_id") == trace[1]
            ]
            if len(found_turns) > 1:
                raise PolicyError("Recovery turn identity is ambiguous")
            if found_turns:
                turn_id = found_turns[0]["id"]
                turn = Collegium(http).observe(session["id"], turn_id)
                if turn.get("trace_id") != trace[1] or turn.get("session_id") != session["id"]:
                    raise PolicyError("Recovery turn trace differs")
        if run["state"] == "reconciling":
            with journal.transaction():
                journal.connection.execute(
                    "UPDATE runs SET state=?,version=version+1 WHERE id=?",
                    (requests[0]["stage"], run["id"]),
                )
                journal._event(run["id"], "launch_reconciled", {"intent": intent})
        if not known:
            journal.record_session(run["id"], intent, session["id"])
        if turn_id:
            journal.record_launch(run["id"], intent, session["id"], turn_id)
        recovered.append({"session_id": session["id"], "turn_id": turn_id})
    return recovered


def reconcile_broker(config, journal, github, operation):
    from .broker import PRBroker

    broker = PRBroker(config, journal, github, observation_only=True)
    root, payload = operation["run_id"], operation["payload"]
    kind = operation["operation"]
    if kind == "branch":
        return {"branch": broker.branch(root, payload["sha"])}
    if kind == "commit":
        changes = {
            r["path"]: base64.b64decode(r["contents"], validate=True).decode()
            for r in payload["fileChanges"]["additions"]
        }
        changes.update({r["path"]: None for r in payload["fileChanges"]["deletions"]})
        return {
            "head": broker.commit(
                root,
                payload["branch"]["branchName"],
                payload["expectedHeadOid"],
                changes,
                int(operation["key"].split(":")[1]),
            )
        }
    row = journal.connection.execute(
        "SELECT document FROM deliveries WHERE run_id=?", (root,)
    ).fetchone()
    if not row:
        raise PolicyError("Recovery delivery document is missing")
    doc = json.loads(row[0])
    if kind == "pr":
        prefix = "<!-- collegium-run:" + root + " -->\n\n"
        if not payload["body"].startswith(prefix):
            raise PolicyError("Recovery PR body identity differs")
        return broker.open_pr(
            root,
            payload["head"],
            doc["head"],
            doc["base"],
            payload["title"],
            description=payload["body"][len(prefix) :],
        )
    if kind in {"draft", "ready"}:
        return broker.draft(
            root,
            doc["pr"]["number"],
            payload["pullRequestId"],
            draft=kind == "draft",
            cycle=int(operation["key"].split(":")[1]),
        )
    raise PolicyError("Unknown recovery broker action")


def validate_import_receipt(journal, receipt):
    root = journal.get(receipt["root"])
    if root["config_digest"] != receipt["config_digest"] or not any(
        e["kind"] == "checkpoint_recovered" and e["data"]["checkpoint"] == receipt["checkpoint"]
        for e in journal.events(receipt["root"])
    ):
        raise PolicyError("Recovery receipt is detached from the imported journal")


def restore_checkpoint(
    config, state, checkpoints, http, github, *, diagnostic=False, checkpoint_data=None
):
    """Verify a lost attempt independently, reconcile in staging, then atomically import."""
    from .artifacts import Artifacts
    from .config import config_digest
    from .store import Journal

    state = Path(state)
    checkpoint, value = checkpoint_data if checkpoint_data is not None else checkpoints.get()
    if value.get("schema_version") != "checkpoint/v1" or value.get(
        "config_digest"
    ) != config_digest(config):
        raise PolicyError("Recovery checkpoint configuration differs; no implicit rebind")
    identity = value["identity"]
    owner = config["recovery_store"]["owner"]
    if identity.get("automation_id") != owner:
        raise PolicyError("Recovery checkpoint belongs to another controller")
    for key, prefix in (("automation_id", "aut"), ("run_id", "run"), ("attempt_id", "att")):
        if not re.fullmatch(prefix + r"_[A-Za-z0-9]+", identity.get(key, "")):
            raise PolicyError("Invalid recovery origin identity")
    prior, _ = http.request("GET", "/api/automations/" + owner + "/runs/" + identity["run_id"])
    data = prior.get("item", {}).get("event", {}).get("data") or {}
    allowed = data.get("action") == ("recovery-probe" if diagnostic else "deliver")
    if getattr(checkpoints, "namespace", "delivery") == "service":
        allowed = data in (
            {"action": "service-test", "mode": "run"},
            {"action": "service-test", "mode": "finalize"},
        )
    attempts = prior.get("attempts") or []
    if (
        prior.get("automation_id") != owner
        or prior.get("id") != identity["run_id"]
        or prior.get("status") not in {"cancelled", "failed"}
        or not allowed
        or not attempts
        or attempts[0].get("id") != identity["attempt_id"]
        or attempts[0].get("n") != 1
        or len(attempts) > 2
    ):
        raise PolicyError("Checkpoint origin is not a closed recoverable first attempt")
    receipts = state / "reconciled"
    receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt_path = receipts / (identity["run_id"] + ".json")
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("checkpoint") != checkpoint:
            raise PolicyError("Recovery checkpoint changed after import")
        if not (state / "journal.sqlite3").is_file():
            raise PolicyError("Recovery receipt has no imported journal")
        restored = Journal(state / "journal.sqlite3")
        try:
            validate_import_receipt(restored, receipt)
        finally:
            restored.close()
        return {**receipt, "already_imported": True}
    # A valid adopted checkpoint after this lost run must never be rolled back.
    fence_path = state / "cloud-fence.json"
    if fence_path.exists():
        fence = json.loads(fence_path.read_text())
        anchor, _ = http.request("GET", "/api/automations/" + owner + "/runs/" + fence["run_id"])
        if anchor["started_at"] >= prior["started_at"]:
            raise PolicyError("Adopted controller state is newer than the lost attempt")
    with tempfile.TemporaryDirectory(prefix="recovery-stage-", dir=state) as folder:
        folder = Path(folder)
        database = folder / "journal.sqlite3"
        database.write_bytes(base64.b64decode(value["journal"], validate=True))
        # Opening untrusted SQLite can execute views/triggers: the signed store is the trust
        # boundary; snapshots are created only from the controller's own consistent backup.
        journal = Journal(database)
        try:
            if journal.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise PolicyError("Recovered SQLite integrity check failed")
            store = Artifacts(folder / "artifacts")
            for artifact, content in value["artifacts"].items():
                if store.put(content) != artifact:
                    raise PolicyError("Recovery artifact digest differs")
            workers = reconcile_workers(config, journal, http)
            broker = None
            if value["operation"]["kind"] == "broker":
                broker = reconcile_broker(config, journal, github, value["operation"])
            elif value["operation"]["kind"] not in {"session_create", "prompt", "tick"}:
                raise PolicyError("Unknown checkpoint effect type")
            journal.record(
                value["operation"]["run_id"],
                "checkpoint_recovered",
                {
                    "checkpoint": checkpoint,
                    "origin": identity,
                },
            )
            journal.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            journal.close()
        # An import is restartable: immutable artifacts first, database replace second,
        # receipt last. Repeating after any cut repeats observations, never mutations.
        target_artifacts = Artifacts(state / "artifacts")
        for path in (folder / "artifacts").glob("*.json"):
            if target_artifacts.put(json.loads(path.read_text())) != path.stem:
                raise PolicyError("Imported artifact digest differs")
        target = state / "journal.sqlite3"
        if target.exists():
            # Keep a consistent prior database for an operator, never copy a live WAL file.
            original = sqlite3.connect(target)
            backup = sqlite3.connect(state / "before-recovery.sqlite3")
            try:
                original.backup(backup)
            finally:
                backup.close()
                original.close()
        for suffix in ("-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        database.replace(target)
        head_path = state / "checkpoint-head.json"
        temporary_head = head_path.with_suffix(".tmp")
        temporary_head.write_bytes(canonical(checkpoint))
        temporary_head.replace(head_path)
        receipt = {
            "automation_id": owner,
            "root": value["operation"]["run_id"],
            "config_digest": config_digest(config),
            "run_id": identity["run_id"],
            "attempt_ids": [a["id"] for a in attempts],
            "checkpoint": checkpoint,
            "workers": workers,
            "broker": broker,
            "external_mutations": 0,
        }
        temporary = receipt_path.with_suffix(".tmp")
        temporary.write_bytes(canonical(receipt))
        temporary.replace(receipt_path)
        return receipt


def reconcile_existing(config, journal, http, github):
    """Reconcile an adopted journal; return None when only a lost snapshot can help."""
    from .config import config_digest

    pending = journal.connection.execute(
        "SELECT id FROM runs WHERE pending_intent IS NOT NULL"
    ).fetchall()
    unresolved = []
    for row in journal.connection.execute("SELECT id FROM runs").fetchall():
        events = journal.events(row[0])
        done = {e["data"]["key"] for e in events if e["kind"] == "broker_done"}
        for e in events:
            if e["kind"] == "effect_attempt" and e["data"]["operation"]["kind"] == "broker":
                operation = e["data"]["operation"]
                if operation["key"] not in done and operation not in unresolved:
                    unresolved.append(operation)
    if not pending and not unresolved:
        return None
    roots = {r[0] for r in pending} | {o["run_id"] for o in unresolved}
    if any(journal.get(root)["config_digest"] != config_digest(config) for root in roots):
        raise PolicyError("Existing recovery admission has a different frozen configuration")
    workers = reconcile_workers(config, journal, http)
    broker = []
    for operation in unresolved:
        if journal.effect_not_started(operation):
            broker.append({"key": operation["key"], "not_started": True})
        else:
            broker.append(reconcile_broker(config, journal, github, operation))
    return {
        "mode": "adopted_journal",
        "workers": workers,
        "broker": broker,
        "external_mutations": 0,
    }
