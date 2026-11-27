import tempfile
import unittest
from pathlib import Path

from collegium_pipeline.domain import PolicyError, Task, digest, select_model
from collegium_pipeline.platform import Collegium, WorkerBinding, agent_digest
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.journal = Journal(Path(self.directory.name) / "journal.sqlite3")
        self.run = self.journal.admit(
            Task("text", "one", "owner/repo", "Task", "Scope"), digest("c")
        )
        self.selection = select_model("planner")
        self.agent = {
            "id": "agent",
            "model": "openai/gpt-6.2-sol",
            "project_id": "project",
            "runtime": "aranarium-aws",
            "config": {"approved": "fixture", "effort": "high"},
        }
        self.binding = WorkerBinding(
            "agent",
            "project",
            "aranarium-aws",
            "base",
            self.agent["model"],
            self.selection,
            agent_digest(self.agent),
        )

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def test_codex_is_explicit_and_prompt_key_is_durable(self):
        calls = []
        test = self

        class Http:
            def request(self, method, path, payload=None, **kwargs):
                calls.append((method, path, payload, kwargs))
                if method == "GET":
                    return test.agent, {}
                if path == "/session":
                    return {"id": "session"}, {}
                events = test.journal.events(test.run)
                test.assertTrue(any(e["kind"] == "session_created" for e in events))
                test.assertEqual(
                    kwargs["headers"]["Idempotency-Key"],
                    test.journal.get(test.run)["pending_intent"],
                )
                return {"turn_id": "turn"}, {}

        result = Collegium(Http()).dispatch(
            self.journal,
            self.run,
            0,
            binding=self.binding,
            selection=self.selection,
            prompt="Scoped fixture",
            execution_enabled=True,
        )
        self.assertEqual(result["turn_id"], "turn")
        self.assertEqual(calls[1][2]["harness"], "codex")
        with self.assertRaises(PolicyError):
            Collegium(Http()).dispatch(
                self.journal,
                self.run,
                0,
                binding=self.binding,
                selection=self.selection,
                prompt="Scoped fixture",
                execution_enabled=True,
            )
        self.assertEqual(len([c for c in calls if c[1] == "/session"]), 1)

    def test_lost_creation_response_quarantines_without_second_launch(self):
        test = self

        class Http:
            def request(self, method, path, payload=None, **kwargs):
                if method == "GET":
                    return test.agent, {}
                raise RemoteError("response lost", unknown_outcome=True)

        platform = Collegium(Http())
        with self.assertRaises(RemoteError):
            platform.dispatch(
                self.journal,
                self.run,
                0,
                binding=self.binding,
                selection=self.selection,
                prompt="Scoped fixture",
                execution_enabled=True,
            )
        self.assertEqual(self.journal.get(self.run)["state"], "reconciling")
        with self.assertRaises(PolicyError):
            platform.dispatch(
                self.journal,
                self.run,
                2,
                binding=self.binding,
                selection=self.selection,
                prompt="Scoped fixture",
                execution_enabled=True,
            )

    def test_default_does_not_make_any_network_request(self):
        class Http:
            def request(self, *args, **kwargs):
                raise AssertionError("Network access forbidden")

        with self.assertRaises(PolicyError):
            Collegium(Http()).dispatch(
                self.journal,
                self.run,
                0,
                binding=self.binding,
                selection=self.selection,
                prompt="Scope",
            )

    def test_permission_changes_invalidate_pinned_agent(self):
        self.assertNotEqual(
            agent_digest(self.agent), agent_digest({**self.agent, "vault_keys": ["new-secret"]})
        )
        self.assertEqual(
            agent_digest(self.agent), agent_digest({**self.agent, "updated_at_ms": 123})
        )

    def test_lost_prompt_response_retains_the_created_session(self):
        test = self

        class Http:
            def request(self, method, path, payload=None, **kwargs):
                if method == "GET":
                    return test.agent, {}
                if path == "/session":
                    return {"id": "known-session"}, {}
                raise RemoteError("Prompt response lost", unknown_outcome=True)

        with self.assertRaises(RemoteError):
            Collegium(Http()).dispatch(
                self.journal,
                self.run,
                0,
                binding=self.binding,
                selection=self.selection,
                prompt="Scope",
                execution_enabled=True,
            )
        self.assertEqual(self.journal.get(self.run)["state"], "reconciling")
        sessions = [
            e["data"]["session_id"]
            for e in self.journal.events(self.run)
            if e["kind"] == "session_created"
        ]
        self.assertEqual(sessions, ["known-session"])
