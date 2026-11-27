import copy
import json
import shlex
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from collegium_pipeline.artifacts import Artifacts
from collegium_pipeline.domain import PolicyError, select_model
from collegium_pipeline.effort import MARKER, PROBE_COMMAND, commands_equal, runtime_evidence
from collegium_pipeline.platform import WorkerBinding, agent_digest
from collegium_pipeline.readiness import publish_readiness, verify_report
from collegium_pipeline.runner import Runner
from collegium_pipeline.store import Journal


class FakeGithub:
    def read(self, path):
        return {"sha": "a" * 40}


class FakeHttp:
    """Fixture transport only; this never calls Collegium or a real model."""

    def __init__(self):
        self.agents, self.sessions = {}, {}
        self.created = 0
        self.mutate = lambda packet, observation: None

    def request(self, method, path, payload=None, **kwargs):
        if path.startswith("/api/agents/"):
            return self.agents[path.rsplit("/", 1)[1]], {}
        if path == "/session" and method == "POST":
            self.created += 1
            identity = f"session-{self.created}"
            self.sessions[identity] = {"agent_id": payload["agent_id"]}
            return {"id": identity}, {}
        session_id = path.split("/")[2]
        row = self.sessions[session_id]
        if path.endswith("/prompt_async"):
            row["packet"] = json.loads(payload["parts"][0]["text"])
            row["turn_id"] = f"turn-{session_id}"
            row["observation"] = self.observation(session_id, row)
            self.mutate(row["packet"], row["observation"])
            return {"turn_id": row["turn_id"]}, {}
        if "/turns/" in path:
            return row["observation"]["turn"], {}
        if path.endswith("/runtime_events/list"):
            return {"data": row["observation"]["events"], "has_more": False}, {}
        return row["observation"]["session"], {}

    def observation(self, session_id, row):
        packet = row["packet"]
        agent = self.agents[row["agent_id"]]
        result = copy.deepcopy(packet["result_schema"])
        result.update(verdict="pass", summary="Fixture result")
        if packet["stage"] == "planning":
            result["payload"] = {"plan": ["Implement"], "acceptance": ["Run tests"]}
        if packet["stage"] == "implementing":
            result["payload"] = {"files": {"solution.py": "def normalize_names(x): return []\n"}}
        events = [
            {
                "type": "user.message",
                "traceparent": "00-trace-id-parent-01",
                "content": [{"type": "text", "text": json.dumps(packet)}],
            }
        ]
        command = PROBE_COMMAND
        output = MARKER + json.dumps(
            [
                {
                    "pid": 8,
                    "harness": "codex",
                    "model": agent["model"],
                    "effort": agent["config"]["effort"],
                }
            ]
        )
        events.extend(self.tool(command, output, "probe"))
        if packet["stage"] == "validating":
            events.extend(
                self.tool(
                    packet["validation_command"],
                    'COLLEGIUM_VALIDATION={"passed": true, "cases": 7}',
                    "validation",
                )
            )
        events.append(
            {"type": "session.status_idle", "usage": {"input_tokens": 30, "output_tokens": 40}}
        )
        return {
            "session": {
                "id": session_id,
                "agent_id": row["agent_id"],
                "project_id": "project",
                "runtime": "aranarium-aws",
                "harness": "codex",
                "harness_release": "codex-test",
            },
            "turn": {
                "id": row["turn_id"],
                "session_id": session_id,
                "status": "completed",
                "cut_off": False,
                "error": None,
                "trace_id": "trace-id",
                "answer": json.dumps(result),
            },
            "events": events,
        }

    @staticmethod
    def tool(command, output, identity):
        return [
            {
                "type": "agent.tool_use",
                "tool_use_id": identity,
                "input": {"command": "/bin/bash -c " + shlex.quote(command)},
            },
            {
                "type": "agent.tool_result",
                "tool_use_id": identity,
                "id": "event-" + identity,
                "exit_code": 0,
                "is_error": False,
                "output": output,
            },
        ]


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.http = FakeHttp()
        self.config = {
            "project_id": "project",
            "repository_id": 123,
            "repository": "owner/repo",
            "base_branch": "main",
            "execution_profile": "readiness",
            "execution_enabled": True,
            "workers": {},
            "max_stage_attempts": 8,
        }
        for role in ("planner", "plan_reviewer", "executor", "code_reviewer", "fixer", "sentinel"):
            selection = select_model(role)
            agent = {
                "id": role,
                "project_id": "project",
                "runtime": "aranarium-aws",
                "model": "openai/" + selection.model,
                "config": {"effort": selection.effort, "repositories": [{"access": "read"}]},
            }
            self.http.agents[role] = agent
            binding = WorkerBinding(
                role,
                "project",
                "aranarium-aws",
                "base",
                agent["model"],
                selection,
                agent_digest(agent),
            )
            self.config["workers"][role] = asdict(binding)
        self.journal = Journal(Path(self.temp.name) / "journal.sqlite3")
        self.runner = Runner(
            self.config,
            self.journal,
            self.http,
            Path(self.temp.name) / "artifacts",
            github=FakeGithub(),
        )

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def complete(self):
        run_id = self.runner.prepare_readiness("fixture")
        for _ in range(12):
            result = self.runner.step(run_id)
            if result["state"] in {"failed", "self_test_passed"}:
                return run_id, result
        self.fail("Fixture pipeline failed to reach a bounded terminal state")

    def test_full_controller_loop_preserves_delivery_ci_gate(self):
        run_id, result = self.complete()
        self.assertEqual(result["state"], "self_test_passed")
        self.assertIs(result["delivered"], False)
        self.assertEqual(self.http.created, 5)
        stages = self.runner._events(run_id, "stage_accepted")
        self.assertEqual(
            [s["stage"] for s in stages],
            ["planning", "plan_review", "implementing", "validating", "reviewing"],
        )
        self.assertEqual(len(self.runner._events(run_id, "runtime_verified")), 5)
        self.runner.step(run_id)
        self.assertEqual(self.http.created, 5)

    def test_resume_observes_the_existing_turn_without_relaunch(self):
        run = self.runner.prepare_readiness("fixture")
        first = self.runner.step(run)
        self.assertEqual(first["action"], "dispatched")
        resumed = Runner(
            self.config,
            self.journal,
            self.http,
            Path(self.temp.name) / "artifacts",
            github=FakeGithub(),
        )
        self.assertEqual(resumed.step(run)["action"], "accepted")
        self.assertEqual(self.http.created, 1)

    def test_forged_final_message_cannot_replace_runtime_probe(self):
        def mutate(packet, observation):
            observation["events"] = [
                e for e in observation["events"] if not e["type"].startswith("agent.tool_")
            ]

        self.http.mutate = mutate
        _, result = self.complete()
        self.assertEqual(result["state"], "failed")
        self.assertIn("Required tool command", result["reason"])

    def test_modified_probe_and_wrong_model_are_rejected(self):
        for change in ("command", "model"):
            with self.subTest(change=change):
                observation = self.http.observation(
                    "session",
                    {
                        "agent_id": "planner",
                        "turn_id": "turn",
                        "packet": {
                            "stage": "planning",
                            "result_schema": {},
                            "runtime_probe_command": PROBE_COMMAND,
                        },
                    },
                )
                binding = self.config["workers"]["planner"].copy()
                binding["selection"] = select_model("planner")
                binding = WorkerBinding(**binding)
                if change == "command":
                    observation["events"][1]["input"]["command"] += " && echo fake"
                else:
                    observation["events"][2]["output"] = MARKER + json.dumps(
                        [{"pid": 8, "harness": "codex", "model": "other", "effort": "high"}]
                    )
                with self.assertRaises(PolicyError):
                    runtime_evidence(observation, binding, session_id="session", turn_id="turn")

    def test_budget_and_configuration_changes_prevent_new_starts(self):
        self.config["max_stage_attempts"] = 1
        run = self.runner.prepare_readiness("fixture")
        self.runner.step(run)
        self.runner.step(run)
        with self.assertRaises(PolicyError):
            self.runner.step(run)
        self.assertEqual(self.http.created, 1)
        self.config["max_stage_attempts"] = 2
        with self.assertRaises(PolicyError):
            self.runner.step(run)

    def test_artifact_modification_is_detected(self):
        artifacts = Artifacts(Path(self.temp.name) / "other")
        identity = artifacts.put({"value": 1})
        (artifacts.directory / (identity + ".json")).write_text('{"value":2}')
        with self.assertRaises(PolicyError):
            artifacts.get(identity)

    def test_delivery_admission_cannot_enter_readiness_loop(self):
        from collegium_pipeline.config import config_digest
        from collegium_pipeline.domain import Task

        run = self.journal.admit(
            Task("text", "product", "owner/repo", "Product", "Requirements"),
            config_digest(self.config),
            purpose="delivery",
        )
        with self.assertRaises(PolicyError):
            self.runner.step(run)
        self.assertEqual(self.http.created, 0)

    def test_product_run_cannot_be_completed_as_worker_calibration(self):
        run = self.runner.prepare_readiness("fixture")
        self.runner.step(run)
        with self.assertRaises(PolicyError):
            self.journal.complete_calibration(run, self.journal.get(run)["version"], {})

    def test_probe_formatting_is_allowed_but_shell_or_program_changes_are_not(self):
        reformatted = PROBE_COMMAND.replace("import glob,json,os", "import glob, json, os")
        self.assertTrue(commands_equal(PROBE_COMMAND, reformatted))
        for changed in (
            PROBE_COMMAND.replace("/proc/", "/other/"),
            PROBE_COMMAND + "\necho fake",
            PROBE_COMMAND.replace("python3 -", "python3 -I -"),
            PROBE_COMMAND.replace("<<'PIPELINE_RUNTIME_PROBE'", "<<PIPELINE_RUNTIME_PROBE"),
        ):
            self.assertFalse(commands_equal(PROBE_COMMAND, changed))

    def test_report_reverifies_all_workers_and_rejects_config_drift(self):
        run, result = self.complete()
        self.assertEqual(result["state"], "self_test_passed")
        for role in ("fixer", "sentinel"):
            created, _ = self.http.request("POST", "/session", {"agent_id": role})
            packet = {"stage": "runtime_diagnostic", "result_schema": {"verdict": "pass"}}
            started, _ = self.http.request(
                "POST",
                "/session/" + created["id"] + "/prompt_async",
                {"parts": [{"text": json.dumps(packet)}]},
            )
            Path(self.temp.name, f"probe-{role}.json").write_text(
                json.dumps({"session_id": created["id"], "turn_id": started["turn_id"]})
            )
        report = publish_readiness(
            self.config,
            self.journal,
            run,
            self.http,
            artifact_directory=Path(self.temp.name) / "artifacts",
            calibration_directory=self.temp.name,
            output=Path(self.temp.name) / "report.json",
        )
        verify_report(self.config, report)
        for altered in (
            {**report, "delivered": True},
            {**report, "config_digest": "other"},
            {**report, "stages": []},
        ):
            with self.assertRaises(PolicyError):
                verify_report(self.config, altered)
        corrupted = copy.deepcopy(report)
        corrupted["workers"]["executor"]["effort"] = "xhigh"
        with self.assertRaises(PolicyError):
            verify_report(self.config, corrupted)
        corrupted = copy.deepcopy(report)
        corrupted["workers"]["executor"]["verified_by_platform"] = False
        with self.assertRaises(PolicyError):
            verify_report(self.config, corrupted)

    def test_recheck_reobserves_existing_result_and_never_relauches(self):
        def mutate(packet, observed):
            observed["events"][1]["input"]["command"] += " && echo invalid"

        self.http.mutate = mutate
        run, result = self.complete()
        self.assertEqual(result["state"], "failed")
        count = self.http.created
        self.journal.recheck_result(
            run, self.journal.get(run)["version"], "Revalidate original result"
        )
        result = self.runner.step(run)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(self.http.created, count)

    def test_unconfirmed_stop_quarantines_even_if_turn_record_was_closed(self):
        run = self.runner.prepare_readiness("fixture")
        self.runner.step(run)
        original = self.http.request

        def request(method, path, payload=None, **kwargs):
            if path.endswith("/abort"):
                return {"aborted": False, "status": "aborted"}, {}
            return original(method, path, payload, **kwargs)

        self.http.request = request
        self.runner.stop(run)
        self.assertEqual(self.journal.get(run)["state"], "reconciling")
