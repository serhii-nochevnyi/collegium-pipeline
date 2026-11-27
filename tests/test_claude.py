"""Claude policy and native evidence reject fallback and fabricated completion."""

import copy
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from collegium_pipeline.config import load_config
from collegium_pipeline.domain import PolicyError, Task, digest, select_model
from collegium_pipeline.effort import CLAUDE_PROBE_COMMAND, MARKER, runtime_evidence, tool_result
from collegium_pipeline.platform import Collegium, WorkerBinding, agent_digest
from collegium_pipeline.runner import worker_binding
from collegium_pipeline.store import Journal


class ClaudeTests(unittest.TestCase):
    def setUp(self):
        self.selection = select_model("planner", profile="claude")
        self.agent = {
            "id": "agent",
            "project_id": "project",
            "model": "opus",
            "runtime": "aranarium-aws",
            "harness": "claude-code",
            "model_connection_id": "mcn_private",
            "config": {"effort": "high"},
        }
        self.binding = WorkerBinding(
            "agent",
            "project",
            "aranarium-aws",
            "base",
            "opus",
            self.selection,
            agent_digest(self.agent),
            "claude-code",
            "mcn_private",
        )
        self.observation = {
            "session": {
                "id": "session",
                "agent_id": "agent",
                "project_id": "project",
                "runtime": "aranarium-aws",
                "harness": "claude-code",
                "harness_release": "claude-code-2.1.289-pinned",
            },
            "turn": {
                "id": "turn",
                "session_id": "session",
                "status": "completed",
                "cut_off": False,
                "error": None,
                "trace_id": "trace",
            },
            "events": [
                {"type": "user.message", "traceparent": "00-trace-parent-01"},
                {
                    "type": "agent.tool_use",
                    "tool_use_id": "probe",
                    "name": "Bash",
                    "input": {"command": CLAUDE_PROBE_COMMAND},
                },
                {
                    "type": "agent.tool_result",
                    "tool_use_id": "probe",
                    "id": "result",
                    "is_error": False,
                    "content": MARKER
                    + json.dumps(
                        [{"pid": 42, "harness": "claude-code", "model": "opus", "effort": "high"}]
                    ),
                },
            ],
        }
        self.observation["events"].append(
            {"type": "session.status_idle", "usage": {"models": {"claude-opus-5-5": {}}}}
        )

    def proof(self, observation=None):
        return runtime_evidence(
            observation or self.observation, self.binding, session_id="session", turn_id="turn"
        )

    def test_native_claude_content_proves_launch_without_inventing_exit_code(self):
        proof = self.proof()
        self.assertEqual(proof["harness"], "claude-code")
        self.assertEqual(proof["effort"], "high")
        self.assertEqual(proof["model_connection_id"], "mcn_private")
        _, result = tool_result(
            self.observation, CLAUDE_PROBE_COMMAND, index=0, harness="claude-code"
        )
        self.assertNotIn("exit_code", result)
        self.assertIn(MARKER, result["output"])

    def test_failed_missing_or_ambiguous_bash_result_never_proves_effort(self):
        for change in (
            {"is_error": True},
            {"is_error": None},
            {"exit_code": 1},
            {"content": None},
            {"tool_use_id": "other"},
        ):
            observed = copy.deepcopy(self.observation)
            observed["events"][2].update(change)
            with self.subTest(change=change), self.assertRaises(PolicyError):
                self.proof(observed)
        observed = copy.deepcopy(self.observation)
        observed["events"].append(observed["events"][2])
        with self.assertRaises(PolicyError):
            self.proof(observed)

    def test_wrong_harness_model_effort_or_modified_probe_rejected(self):
        mutations = [
            ("session", "harness", "codex"),
            ("session", "harness_release", "codex-pinned"),
            ("turn", "trace_id", "another"),
            ("turn", "cut_off", True),
        ]
        for section, key, value in mutations:
            observed = copy.deepcopy(self.observation)
            observed[section][key] = value
            with self.subTest(key=key), self.assertRaises(PolicyError):
                self.proof(observed)
        for model, effort in (("sonnet", "high"), ("opus", "low"), ("opus", "auto")):
            observed = copy.deepcopy(self.observation)
            observed["events"][2]["content"] = MARKER + json.dumps(
                [{"pid": 42, "harness": "claude-code", "model": model, "effort": effort}]
            )
            with self.assertRaises(PolicyError):
                self.proof(observed)

    def test_model_telemetry_prevents_silent_fallback_or_unsupported_effort(self):
        for models in (
            {},
            {"claude-sonnet-5-5": {}},
            {"claude-opus-unknown": {}},
            {"claude-opus-5-5": {}, "claude-sonnet-5-5": {}},
        ):
            observed = copy.deepcopy(self.observation)
            observed["events"][-1]["usage"]["models"] = models
            with self.subTest(models=models), self.assertRaises(PolicyError):
                self.proof(observed)

    def test_worker_cannot_hide_unbounded_same_model_delegation(self):
        observed = copy.deepcopy(self.observation)
        observed["events"].append(
            {"type": "agent.tool_use", "name": "Agent", "input": {"prompt": "delegate"}}
        )
        with self.assertRaises(PolicyError):
            self.proof(observed)
        for command in (CLAUDE_PROBE_COMMAND + "\necho injected", "echo " + MARKER):
            observed = copy.deepcopy(self.observation)
            observed["events"][1]["input"]["command"] = command
            with self.assertRaises(PolicyError):
                self.proof(observed)

    def test_private_connection_and_harness_required_before_session_creation(self):
        for field, value in (("model_connection_id", "mcn_shared"), ("harness", "codex")):
            agent = {**self.agent, field: value}
            binding = {**asdict(self.binding), "approved_agent_digest": agent_digest(agent)}
            binding["selection"] = self.selection
            self.dispatch(agent, WorkerBinding(**binding), expect_error=True)

    def dispatch(self, agent, binding, *, expect_error=False):
        calls = []

        class Http:
            def request(self, method, path, payload=None, **kwargs):
                calls.append((method, path, payload))
                if method == "GET":
                    return agent, {}
                return ({"id": "session"} if path == "/session" else {"turn_id": "turn"}), {}

        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(Path(folder) / "journal.sqlite3")
            try:
                root = journal.admit(
                    Task("text", "test", "owner/repo", "Title", "Scope"), digest(1)
                )

                def run():
                    return Collegium(Http()).dispatch(
                        journal,
                        root,
                        0,
                        binding=binding,
                        selection=self.selection,
                        prompt="Scoped diagnostic",
                        execution_enabled=True,
                    )

                if expect_error:
                    with self.assertRaises(PolicyError):
                        run()
                    self.assertFalse(any(c[0] == "POST" for c in calls))
                else:
                    run()
                    self.assertEqual(calls[1][2]["harness"], "claude-code")
                    self.assertEqual(calls[2][2]["model"], {"modelID": "opus"})
            finally:
                journal.close()

    def test_claude_dispatch_is_explicit(self):
        self.dispatch(self.agent, self.binding)

    def test_claude_fixer_escalates_without_losing_private_connection(self):
        profile = {
            "model_policy": "claude",
            "project_id": "project",
            "model_connection_id": "mcn_private",
            "workers": {},
        }
        for repeats, model, effort in (
            (0, "sonnet", "low"),
            (1, "sonnet", "high"),
            (2, "opus", "max"),
        ):
            selection = select_model("fixer", same_cause_failures=repeats, profile="claude")
            self.assertEqual((selection.model, selection.effort), (model, effort))
            key = "fixer" + (":" + effort if repeats else "")
            binding = {**asdict(self.binding), "api_model": model, "selection": asdict(selection)}
            profile["workers"][key] = binding
            self.assertEqual(worker_binding(profile, key).selection, selection)
            profile["workers"][key]["model_connection_id"] = None
            with self.assertRaises(PolicyError):
                worker_binding(profile, key)

    def test_configuration_cannot_select_claude_without_private_connection(self):
        source = json.loads(Path("config/pipeline.example.json").read_text())
        source["model_policy"] = "claude"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps(source))
            with self.assertRaises(PolicyError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
