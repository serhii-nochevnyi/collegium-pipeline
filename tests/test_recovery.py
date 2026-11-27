"""Lose the whole controller snapshot, retain independent store and external effects."""

import copy
import hashlib
import json
import runpy
import shutil
import tempfile
import unittest
import zlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from test_delivery import BASE, Repository

from collegium_pipeline.artifacts import Artifacts
from collegium_pipeline.broker import PRBroker
from collegium_pipeline.config import config_digest
from collegium_pipeline.domain import PolicyError, Task, select_model
from collegium_pipeline.platform import Collegium, WorkerBinding, agent_digest
from collegium_pipeline.recovery import (
    Checkpoints,
    WriteAhead,
    mac,
    restore_checkpoint,
    unpack,
)
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError

ROOT = Path(__file__).resolve().parents[1]
STORE = runpy.run_path(str(ROOT / "scripts/recovery_store.py"))["handle"]


class DiskStore:
    """Same signed/chunked server handler on a filesystem independent of the controller."""

    def __init__(self, path):
        self.path = path
        self.key = "test-control-secret-never-in-checkpoint"
        self.owner = "aut_owner"
        self.refuse = False

    def call(self, action, **fields):
        if self.refuse:
            raise PolicyError("No adopted checkpoint acknowledgement")
        event = {
            "action": action,
            "namespace": "delivery",
            "owner": self.owner,
            "request_id": uuid4().hex,
            **fields,
        }
        return STORE({**event, "mac": mac(event, self.key)}, self.path, self.owner, self.key)

    def head(self):
        return self.call("head")["head"]

    put = Checkpoints.put
    get = Checkpoints.get


class AgentsHttp:
    def __init__(self, agent, *, lose=None):
        self.agent = agent
        self.sessions = []
        self.messages = []
        self.turns = []
        self.lose = lose
        self.posts = []
        self.prior = {
            "id": "run_lost",
            "automation_id": "aut_owner",
            "status": "cancelled",
            "started_at": 1,
            "item": {"event": {"data": {"action": "deliver"}}},
            "attempts": [{"id": "att_lost", "n": 1, "status": "cancelled"}],
        }

    def request(self, method, path, payload=None, **kwargs):
        if method == "POST":
            self.posts.append((path, payload, kwargs))
            if path == "/session":
                session = {
                    "id": "ses_known",
                    "project_id": "project",
                    "agent_id": "agent_test",
                    "environment_id": "base",
                    **payload,
                }
                self.sessions.append(session)
                result = session
                kind = "session"
            elif path == "/session/ses_known/prompt_async":
                key = kwargs["headers"]["Idempotency-Key"]
                if not self.turns:
                    self.messages.append(
                        {
                            "type": "user.message",
                            "content": payload["parts"],
                            "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
                        }
                    )
                    self.turns.append(
                        {
                            "id": "run_turn",
                            "session_id": "ses_known",
                            "trace_id": "a" * 32,
                            "idempotency_key": key,
                        }
                    )
                else:
                    assert self.turns[0]["idempotency_key"] == key
                result = {"turn_id": "run_turn"}
                kind = "prompt"
            else:
                raise AssertionError(path)
            if self.lose == kind:
                self.lose = None
                raise RemoteError("Response lost after effect", unknown_outcome=True)
            return result, {}
        if path == "/api/agents/agent_test":
            return self.agent, {}
        if path.startswith("/session?project_id="):
            return self.sessions, {}
        if path == "/session/ses_known/runtime_events/list":
            return {"data": self.messages, "has_more": False}, {}
        if path == "/session/ses_known":
            return self.sessions[0], {}
        if path.startswith("/api/agents/agent_test/runs"):
            return {"runs": self.turns}, {}
        if path == "/session/ses_known/turns/run_turn":
            return self.turns[0], {}
        if path == "/api/automations/aut_owner/runs/run_lost":
            return self.prior, {}
        raise AssertionError((method, path))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.state = self.path / "controller"
        self.state.mkdir()
        self.store = DiskStore(self.path / "independent")
        self.selection = select_model("executor", profile="claude")
        self.agent = {
            "id": "agent_test",
            "project_id": "project",
            "model": "sonnet",
            "runtime": "aranarium-aws",
            "harness": "claude-code",
            "model_connection_id": "mcn_private",
            "config": {"effort": "low"},
        }
        self.binding = WorkerBinding(
            "agent_test",
            "project",
            "aranarium-aws",
            "base",
            "sonnet",
            self.selection,
            agent_digest(self.agent),
            "claude-code",
            "mcn_private",
        )
        self.config = {
            "repository": "owner/repo",
            "repository_id": 123,
            "project_id": "project",
            "base_branch": "main",
            "execution_enabled": True,
            "broker_enabled": True,
            "execution_profile": "delivery",
            "allowed_paths": ["src/"],
            "recovery_store": {
                "automation_id": "aut_store",
                "owner": "aut_owner",
                "approved_digest": "d" * 64,
            },
            "workers": {"executor": asdict(self.binding)},
        }
        self.journal = Journal(self.state / "journal.sqlite3")
        self.root = self.journal.admit(
            Task("text", "test", "owner/repo", "Recovery", "Acceptance"), config_digest(self.config)
        )
        self.artifacts = Artifacts(self.state / "artifacts")
        self.artifact = self.artifacts.put({"candidate": "immutable"})
        self.identity = {
            "automation_id": "aut_owner",
            "run_id": "run_lost",
            "attempt_id": "att_lost",
        }
        self.write = WriteAhead(
            self.config, self.journal, self.artifacts.directory, self.store, self.identity
        )
        self.journal.before_effect = self.write.save
        self.github = Repository()
        self.http = AgentsHttp(self.agent)

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def lose_snapshot(self):
        self.journal.close()
        shutil.rmtree(self.state)
        self.state.mkdir()
        self.journal = Journal(self.state / "journal.sqlite3")

    def restore(self):
        self.journal.close()
        try:
            return restore_checkpoint(self.config, self.state, self.store, self.http, self.github)
        finally:
            self.journal = Journal(self.state / "journal.sqlite3")

    def dispatch(self):
        return Collegium(self.http).dispatch(
            self.journal,
            self.root,
            0,
            binding=self.binding,
            selection=self.selection,
            prompt="Exact diagnostic prompt",
            execution_enabled=True,
        )

    def test_lost_session_response_and_snapshot_recover_one_existing_session(self):
        self.http.lose = "session"
        with self.assertRaises(RemoteError):
            self.dispatch()
        self.assertEqual(len(self.http.sessions), 1)
        self.lose_snapshot()
        receipt = self.restore()
        self.assertEqual(receipt["external_mutations"], 0)
        self.assertEqual(receipt["workers"][0]["session_id"], "ses_known")
        self.assertEqual(
            self.artifact, Artifacts(self.state / "artifacts").put({"candidate": "immutable"})
        )
        self.assertEqual(len(self.http.posts), 1)
        result = Collegium(self.http).resume_dispatch(
            self.journal,
            self.root,
            binding=self.binding,
            selection=self.selection,
            prompt="Exact diagnostic prompt",
            execution_enabled=True,
        )
        self.assertEqual(result["turn_id"], "run_turn")
        self.assertEqual(len(self.http.sessions), 1)
        self.assertEqual(len(self.http.turns), 1)
        self.assertTrue(self.restore()["already_imported"])
        self.assertEqual(len(self.http.turns), 1)

    def test_lost_prompt_response_and_whole_snapshot_recover_original_turn(self):
        self.http.lose = "prompt"
        with self.assertRaises(RemoteError):
            self.dispatch()
        self.lose_snapshot()
        result = self.restore()
        self.assertEqual(result["workers"][0]["turn_id"], "run_turn")
        self.assertEqual(len(self.http.posts), 2)
        prior_posts = len(self.http.posts)
        for _ in range(2):
            Collegium(self.http).resume_dispatch(
                self.journal,
                self.root,
                binding=self.binding,
                selection=self.selection,
                prompt="Exact diagnostic prompt",
                execution_enabled=True,
            )
        self.assertEqual(len(self.http.posts), prior_posts)
        self.assertEqual(len(self.http.turns), 1)

    def test_checkpoint_ack_failure_prevents_even_session_creation(self):
        self.store.refuse = True
        with self.assertRaises(PolicyError):
            self.dispatch()
        self.assertEqual(self.http.posts, [])

    def test_no_effect_checkpoint_failure_can_resume_without_duplicate_agent(self):
        from collegium_pipeline.recovery import reconcile_existing

        self.store.refuse = True
        with self.assertRaises(PolicyError):
            self.dispatch()
        self.store.refuse = False
        result = reconcile_existing(self.config, self.journal, self.http, self.github)
        self.assertTrue(result["workers"][0]["not_started"])
        Collegium(self.http).resume_dispatch(
            self.journal,
            self.root,
            binding=self.binding,
            selection=self.selection,
            prompt="Exact diagnostic prompt",
            execution_enabled=True,
        )
        self.assertEqual(len(self.http.sessions), 1)
        self.assertEqual(len(self.http.turns), 1)

    def test_no_effect_checkpoint_failure_can_resume_one_commit(self):
        from collegium_pipeline.recovery import reconcile_existing

        self.journal.before_effect = None
        branch = self.broker().branch(self.root, BASE)
        self.journal.before_effect = self.write.save
        self.store.refuse = True
        changes = {"src/app.py": "value=1"}
        with self.assertRaises(PolicyError):
            self.broker().commit(self.root, branch, BASE, changes, 0)
        self.store.refuse = False
        result = reconcile_existing(self.config, self.journal, self.http, self.github)
        self.assertTrue(result["broker"][0]["not_started"])
        self.broker().commit(self.root, branch, BASE, changes, 0)
        self.assertEqual(sum(op == "commit" for op, _ in self.github.writes), 1)

    def test_absent_or_mismatched_named_session_stays_blocked(self):
        self.http.lose = "session"
        with self.assertRaises(RemoteError):
            self.dispatch()
        self.http.sessions[0]["project_id"] = "another"
        self.lose_snapshot()
        with self.assertRaises(PolicyError):
            self.restore()
        self.assertFalse((self.state / "reconciled/run_lost.json").exists())
        self.http.sessions.clear()
        with self.assertRaises(PolicyError):
            self.restore()
        self.assertEqual(len(self.http.posts), 1)

    def broker(self):
        return PRBroker(self.config, self.journal, self.github)

    def test_lost_commit_response_and_snapshot_never_create_second_commit(self):
        self.journal.before_effect = None
        branch = self.broker().branch(self.root, BASE)
        self.journal.before_effect = self.write.save
        self.github.lose = "commit"
        changes = {"src/app.py": "value = 1\n"}
        with self.assertRaises(RemoteError):
            self.broker().commit(self.root, branch, BASE, changes, 0)
        head = self.github.ref(branch)
        self.lose_snapshot()
        self.assertEqual(self.restore()["broker"]["head"], head)
        self.assertEqual(self.broker().commit(self.root, branch, BASE, changes, 0), head)
        self.assertEqual(sum(op == "commit" for op, _ in self.github.writes), 1)

    def test_lost_pr_response_and_snapshot_never_create_second_pr(self):
        self.journal.before_effect = None
        branch = self.broker().branch(self.root, BASE)
        head = self.broker().commit(self.root, branch, BASE, {"src/app.py": "value = 1\n"}, 0)
        self.journal.connection.execute(
            "CREATE TABLE deliveries(run_id TEXT PRIMARY KEY,document TEXT)"
        )
        self.journal.connection.execute(
            "INSERT INTO deliveries VALUES(?,?)",
            (self.root, json.dumps({"head": head, "base": BASE})),
        )
        self.journal.before_effect = self.write.save
        self.github.lose = "pr"
        with self.assertRaises(RemoteError):
            self.broker().open_pr(self.root, branch, head, BASE, "Diagnostic")
        self.lose_snapshot()
        receipt = self.restore()
        self.assertEqual(receipt["broker"]["number"], 1)
        self.assertEqual(
            self.broker().open_pr(self.root, branch, head, BASE, "Diagnostic")["number"], 1
        )
        self.assertEqual(sum(op == "pr" for op, _ in self.github.writes), 1)
        self.assertTrue(self.restore()["already_imported"])

    def test_store_cas_authentication_incomplete_upload_and_decompression_bounds(self):
        first = self.store.put({"first": True}, None)
        with self.assertRaises(ValueError):
            self.store.put({"stale": True}, None)
        self.assertEqual(self.store.get(), (first, {"first": True}))
        event = {"owner": "aut_owner", "request_id": uuid4().hex, "action": "head", "mac": "forged"}
        with self.assertRaises(ValueError):
            STORE(event, self.store.path, self.store.owner, self.store.key)
        blob = b"not-complete"
        identity = hashlib.sha256(blob).hexdigest()
        self.store.call("begin", checkpoint=identity, parent=first, size=len(blob))
        with self.assertRaises(OSError):
            self.store.call("finish", checkpoint=identity)
        self.assertEqual(self.store.head()["checkpoint"], first)
        with self.assertRaises(PolicyError):
            unpack(zlib.compress(b"{}") + b"trailing")
        self.assertNotIn(self.store.key, (self.store.path / "delivery/head.json").read_text())

    def test_authenticated_rpc_recovers_lost_submit_without_resubmitting(self):
        from collegium_pipeline.native_broker import binding_digest

        owner = self
        row = {
            "project_id": "project",
            "status": "paused",
            "triggers": [],
            "target": {
                "kind": "script",
                "secrets": ["project/PIPELINE_CONTROL_KEY"],
                "repositories": [],
                "variables": [],
                "mcp_servers": [],
            },
        }
        code = {"current": {"files": {"recovery_scope.json": json.dumps({"owner": "aut_owner"})}}}
        cfg = copy.deepcopy(self.config)
        cfg["recovery_store"]["approved_digest"] = binding_digest(row, code)

        class Http:
            submissions = 0
            kept = None

            def request(self, method, path, payload=None):
                if method == "POST":
                    self.submissions += 1
                    event = payload["data"]
                    result = STORE(event, owner.store.path, owner.store.owner, owner.store.key)
                    self.kept = {
                        "id": "run_rpc",
                        "status": "succeeded",
                        "output_cut": False,
                        "item": {"event": {"data": event}},
                        "output_tail": json.dumps({**result, "mac": mac(result, owner.store.key)}),
                    }
                    raise RemoteError("Submission response lost", unknown_outcome=True)
                if path.endswith("/code"):
                    return code, {}
                if path.endswith("?limit=100"):
                    return {"runs": [{"id": "run_rpc"}]}, {}
                if path.endswith("/runs/run_rpc"):
                    return self.kept, {}
                return row, {}

        http = Http()
        self.assertIsNone(Checkpoints(cfg, http, self.store.key).head())
        self.assertEqual(http.submissions, 1)
        self.assertNotIn(self.store.key, json.dumps(http.kept))

    def test_missing_broker_effect_does_not_publish_a_replacement(self):
        self.journal.before_effect = None
        branch = self.broker().branch(self.root, BASE)
        self.journal.before_effect = self.write.save

        def lose_before_effect(operation, payload):
            raise RemoteError("No observable effect", unknown_outcome=True)

        self.github.mutate = lose_before_effect
        with self.assertRaises(RemoteError):
            self.broker().commit(self.root, branch, BASE, {"src/app.py": "value=1"}, 0)
        self.lose_snapshot()
        with self.assertRaisesRegex(PolicyError, "Unresolved external action"):
            self.restore()
        self.assertEqual(sum(op == "commit" for op, _ in self.github.writes), 0)

    def test_detached_import_receipt_is_rejected(self):
        self.http.lose = "prompt"
        with self.assertRaises(RemoteError):
            self.dispatch()
        self.lose_snapshot()
        self.restore()
        self.journal.connection.execute("DELETE FROM events WHERE kind='checkpoint_recovered'")
        with self.assertRaisesRegex(PolicyError, "detached"):
            self.restore()

    def test_read_only_tick_can_be_restored_without_external_effects(self):
        self.write.save({"kind": "tick", "run_id": self.root})
        self.lose_snapshot()
        result = self.restore()
        self.assertEqual(result["workers"], [])
        self.assertIsNone(result["broker"])
        self.assertEqual(self.http.posts, [])
        WriteAhead(self.config, self.journal, self.state / "artifacts", self.store, self.identity)

    def test_external_checkpoint_advance_cannot_be_silently_overwritten(self):
        current = self.write.save({"kind": "tick", "run_id": self.root})
        self.store.put({"advanced": True}, current)
        with self.assertRaisesRegex(PolicyError, "advanced"):
            WriteAhead(
                self.config, self.journal, self.state / "artifacts", self.store, self.identity
            )
        with self.assertRaises(ValueError):
            self.write.save({"kind": "tick", "run_id": self.root})
        self.assertEqual(self.http.posts, [])

    def test_committed_checkpoint_with_lost_ack_can_resume_one_agent(self):
        from collegium_pipeline.recovery import reconcile_existing

        original = self.store.call
        lost = [False]

        def call(action, **fields):
            result = original(action, **fields)
            if action == "finish" and not lost[0]:
                lost[0] = True
                raise PolicyError("Checkpoint acknowledgement unknown")
            return result

        self.store.call = call
        with self.assertRaises(PolicyError):
            self.dispatch()
        self.assertEqual(self.http.posts, [])
        self.assertTrue((self.state / "checkpoint-pending.json").exists())
        self.journal.close()
        self.journal = Journal(self.state / "journal.sqlite3")
        self.write = WriteAhead(
            self.config, self.journal, self.state / "artifacts", self.store, self.identity
        )
        self.journal.before_effect = self.write.save
        reconcile_existing(self.config, self.journal, self.http, self.github)
        self.write.save({"kind": "tick", "run_id": self.root})
        Collegium(self.http).resume_dispatch(
            self.journal,
            self.root,
            binding=self.binding,
            selection=self.selection,
            prompt="Exact diagnostic prompt",
            execution_enabled=True,
        )
        self.assertEqual(len(self.http.sessions), 1)
        self.assertEqual(len(self.http.turns), 1)

    def test_lost_tick_checkpoint_ack_can_be_adopted_without_rolling_back_state(self):
        original = self.store.call

        def call(action, **fields):
            result = original(action, **fields)
            if action == "finish":
                raise PolicyError("Checkpoint acknowledgement unknown")
            return result

        self.store.call = call
        with self.assertRaises(PolicyError):
            self.write.save({"kind": "tick", "run_id": self.root})
        self.store.call = original
        WriteAhead(self.config, self.journal, self.state / "artifacts", self.store, self.identity)
        self.assertEqual(self.http.posts, [])
        self.assertFalse((self.state / "checkpoint-pending.json").exists())

    def test_config_drift_and_still_running_origin_prevent_import(self):
        self.http.lose = "session"
        with self.assertRaises(RemoteError):
            self.dispatch()
        self.lose_snapshot()
        self.http.prior["status"] = "running"
        with self.assertRaises(PolicyError):
            self.restore()
        self.http.prior["status"] = "cancelled"
        self.config["allowed_paths"].append("broader/")
        with self.assertRaises(PolicyError):
            self.restore()
        self.assertEqual(
            self.journal.connection.execute("SELECT count(*) FROM runs").fetchone()[0], 0
        )


if __name__ == "__main__":
    unittest.main()
