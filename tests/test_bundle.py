"""The bundle carries the controller, preserves claims and starts with dispatch disabled."""

import contextlib
import copy
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collegium_pipeline.domain import PolicyError
from collegium_pipeline.platform import agent_digest

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts/build_bundle.py"))["build"]
VALIDATE = runpy.run_path(str(ROOT / "scripts/build_bundle.py"))["validate_integrations"]
ENTRY_MODULE = runpy.run_path(str(ROOT / "scripts/bundle_controller.py"))
ENTRY = ENTRY_MODULE["main"]
FENCE = ENTRY_MODULE["cloud_fence"]
SAVE = ENTRY_MODULE["save_receipt"]


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)
        self.result = BUILD(
            ROOT / "config/claude-service.json", ROOT / "config/integrations.json", self.path
        )
        self.manifest = json.loads((self.path / "lap.yaml").read_text())

    def tearDown(self):
        self.folder.cleanup()

    def test_installation_contains_controller_and_existing_agent_claims(self):
        self.assertEqual(len(self.manifest["agents"]), 8)
        self.assertEqual(len(self.manifest["automations"]), 2)
        claims = json.loads((self.path / "claims.json").read_text())
        self.assertEqual(len(claims), 9)
        for automation in self.manifest["automations"]:
            self.assertEqual(automation["start"], "paused")
            self.assertLessEqual(len(automation["script"]["files"]), 64)
            for name in automation["script"]["files"]:
                self.assertTrue((self.path / name).is_file(), name)
        controller = self.manifest["automations"][0]
        self.assertIn(
            "controller/src/collegium_pipeline/delivery.py", controller["script"]["files"]
        )
        self.assertEqual(controller["script"]["secrets"], ["PIPELINE_CONTROL_KEY"])
        for agent in self.manifest["agents"]:
            self.assertEqual(agent["harness"], "claude-code")
            self.assertEqual(agent["model_connection"], "claude-code-subscription")
            self.assertEqual(agent["repositories"][0]["access"], "read")
            self.assertNotIn("vault_keys", agent)
            self.assertIn("agent/" + agent["name"], claims)

    def test_packaged_preflight_does_not_dispatch_or_need_a_host_credential(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = ENTRY({"action": "preflight"}, root=self.path / "controller", environ={})
        value = json.loads(out.getvalue())
        self.assertEqual(rc, 0)
        self.assertFalse(value["execution_enabled"])
        self.assertFalse(value["broker_enabled"])
        self.assertFalse(value["agent_started"])
        self.assertFalse(value["control_key_present"])

    def test_delivery_cannot_use_a_task_event_to_inject_a_key_or_enable_execution(self):
        for event in (
            {"action": "shell", "command": "anything"},
            {
                "action": "deliver",
                "run_id": "run",
                "live": True,
                "PIPELINE_CONTROL_KEY": "untrusted-event-data",
            },
        ):
            with self.assertRaises(PolicyError):
                ENTRY(
                    event,
                    root=self.path / "controller",
                    environ={"ARANARIUM_STATE_DIR": str(self.path / "state")},
                )

    def test_dev_prod_are_separate_and_no_mcp_is_falsely_claimed_healthy(self):
        integrations = json.loads((self.path / "controller/integrations.json").read_text())
        urls = {c["name"]: c["url"] for c in integrations["connections"]}
        self.assertNotEqual(urls["grafana-prod"], urls["grafana-dev"])
        self.assertNotEqual(urls["langfuse-prod"], urls["langfuse-dev"])
        self.assertFalse(integrations["environment_substitution_allowed"])
        needs = {c["name"]: c for c in self.manifest["connections"]}
        for status in integrations["status"]:
            if status["state"] != "connected":
                self.assertEqual(status["allowed_tools"], [])
                self.assertFalse(status["attached_to_live_agents"])
                self.assertNotIn(status["need"], needs)
                for agent in self.manifest["agents"]:
                    self.assertNotIn(status["need"], agent["mcp_servers"])
            else:
                self.assertTrue(status["authenticated_discovery"])
                self.assertEqual(needs[status["need"]]["tools"], status["allowed_tools"])
                self.assertTrue(needs[status["need"]]["tools"])
            # Tool discovery is not proof of a successful backend data call.
            self.assertFalse(status["backend_read_verified"])

    def control_fixture(self):
        root = self.path / "controller"
        config = json.loads((root / "settings.json").read_text())
        integrations = json.loads((root / "integrations.json").read_text())
        needs = [s for s in integrations["status"] if s["allowed_tools"]]
        agents = {}
        for binding in config["workers"].values():
            agent = {
                "id": binding["agent_id"],
                "references": {
                    "mcp": [
                        {"name": s["need"], "level": "project", "id": s["connection_id"]}
                        for s in needs
                    ]
                },
                "config": {
                    "tools": [
                        {
                            "type": "mcp_toolset",
                            "mcp_server_name": s["need"],
                            "default_config": {"enabled": False},
                            "configs": {n: {"enabled": True} for n in s["allowed_tools"]},
                        }
                        for s in needs
                    ]
                },
            }
            agents["/api/agents/" + binding["agent_id"]] = agent
            binding["approved_agent_digest"] = agent_digest(agent)
        (root / "settings.json").write_text(json.dumps(config))

        class ReadOnlyHttp:
            def request(self, method, path):
                if method != "GET" or path not in agents:
                    raise AssertionError("Unexpected control-plane operation")
                return agents[path], {}

        return root, config, agents, ReadOnlyHttp()

    def test_control_verification_uses_vault_key_and_only_reads_fixed_bindings(self):
        root, _, _, http = self.control_fixture()
        with (
            patch("collegium_pipeline.transport.JsonHttp", return_value=http) as transport,
            patch("collegium_pipeline.native_broker.ScriptTransport.scope") as scope,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            rc = ENTRY(
                {"action": "verify-control"},
                root=root,
                environ={"PIPELINE_CONTROL_KEY": "fixture-vault-key"},
            )
        transport.assert_called_once_with(
            "https://agentic-platform.infrateam.xyz", {"X-Api-Key": "fixture-vault-key"}
        )
        scope.assert_called_once()
        self.assertEqual(rc, 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result["control_key_valid"])
        self.assertEqual(result["worker_bindings_verified"], 8)
        self.assertFalse(result["agent_started"])
        self.assertNotIn("fixture-vault-key", out.getvalue())

    def test_control_verification_rejects_event_credentials_missing_key_and_drift(self):
        root, _, agents, http = self.control_fixture()
        for event, environ in (
            ({"action": "verify-control"}, {"LAP_API_KEY": "host-key"}),
            (
                {"action": "verify-control", "PIPELINE_CONTROL_KEY": "event-key"},
                {"PIPELINE_CONTROL_KEY": "fixture-vault-key"},
            ),
        ):
            with self.assertRaises(PolicyError):
                ENTRY(event, root=root, environ=environ, http=http)
        next(iter(agents.values()))["references"]["mcp"][0]["id"] = "broader-connection"
        with self.assertRaises(PolicyError):
            ENTRY(
                {"action": "verify-control"},
                root=root,
                environ={"PIPELINE_CONTROL_KEY": "fixture-vault-key"},
                http=http,
            )
        for drift in ("reference", "tool-ceiling"):
            with self.subTest(drift=drift):
                root, config, agents, http = self.control_fixture()
                agent = next(iter(agents.values()))
                if drift == "reference":
                    agent["references"]["mcp"][0]["id"] = "broader-connection"
                else:
                    agent["config"]["tools"][0]["default_config"]["enabled"] = True
                next(iter(config["workers"].values()))["approved_agent_digest"] = agent_digest(
                    agent
                )
                (root / "settings.json").write_text(json.dumps(config))
                with self.assertRaisesRegex(PolicyError, "Installed MCP"):
                    ENTRY(
                        {"action": "verify-control"},
                        root=root,
                        environ={"PIPELINE_CONTROL_KEY": "fixture-vault-key"},
                        http=http,
                    )

    def invoke(self, event):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = ENTRY(
                event,
                root=self.path / "controller",
                environ={"ARANARIUM_STATE_DIR": str(self.path / "state")},
            )
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_prepare_reopen_is_idempotent_and_changed_input_is_rejected(self):
        event = {
            "action": "prepare",
            "task_id": "same",
            "title": "Title",
            "requirements": "First acceptance",
        }
        first = self.invoke(event)
        self.assertEqual(first, self.invoke(event))
        status = self.invoke({"action": "status", "run_id": first["run_id"]})
        self.assertEqual(len(status["events"]), 1)
        with self.assertRaises(PolicyError):
            self.invoke({**event, "requirements": "Changed acceptance"})
        self.assertEqual(self.invoke(event), first)
        self.assertFalse((self.path / "state/collegium-pipeline/intake-requirements.txt").exists())

    def test_concurrent_processes_admit_one_immutable_task(self):
        program = (
            "import runpy; m=runpy.run_path("
            + repr(str(ROOT / "scripts/bundle_controller.py"))
            + "); m['main']({'action':'prepare','task_id':'race','title':'Race',"
            "'requirements':'Same acceptance'},root="
            + repr(str(self.path / "controller"))
            + ",environ={'ARANARIUM_STATE_DIR':"
            + repr(str(self.path / "state"))
            + "})"
        )
        children = [
            subprocess.Popen(
                [sys.executable, "-c", program],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            )
            for _ in range(4)
        ]
        results = []
        for child in children:
            output, error = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, error)
            results.append(json.loads(output))
        self.assertEqual(len({r["run_id"] for r in results}), 1)
        status = self.invoke({"action": "status", "run_id": results[0]["run_id"]})
        self.assertEqual(len(status["events"]), 1)

    def test_real_process_crash_rolls_back_only_uncommitted_transaction(self):
        event = {"action": "state-probe", "mode": "commit"}
        first = self.invoke(event)
        program = (
            "import runpy; m=runpy.run_path("
            + repr(str(ROOT / "scripts/bundle_controller.py"))
            + "); m['main']({'action':'state-probe','mode':'crash'},root="
            + repr(str(self.path / "controller"))
            + ",environ={'ARANARIUM_STATE_DIR':"
            + repr(str(self.path / "state"))
            + "})"
        )
        result = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            timeout=20,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(result.returncode, 75, result.stderr)
        after = self.invoke({"action": "state-probe", "mode": "inspect"})
        self.assertEqual(after, first)
        self.assertEqual(after["integrity"], "ok")
        self.assertEqual(after["effects"], ["committed"])
        self.assertEqual(after["admissions"], 1)
        self.assertEqual(self.invoke(event), first)

    def fence_fixture(self, previous=(), *, retry=False, diagnostic=False):
        event = (
            {"action": "state-probe", "mode": "fenced-check"}
            if diagnostic
            else {"action": "deliver", "live": True, "run_id": "product"}
        )
        env = {
            "LAP_AUTOMATION_ID": "aut_test",
            "LAP_RUN_ID": "run_now",
            "LAP_ATTEMPT_ID": "att_now",
        }
        now = {
            "id": "run_now",
            "automation_id": "aut_test",
            "status": "running",
            "item": {"event": {"data": event}},
            "attempts": [{"id": "att_now", "n": 1, "status": "running"}],
        }
        if retry:
            now["attempts"].insert(0, {"id": "att_lost", "n": 1, "status": "failed"})
            now["attempts"][-1]["n"] = 2
        details = {row["id"]: row for row in [now, *previous]}

        class ReadHttp:
            def request(self, method, path):
                if method != "GET":
                    raise AssertionError("Fence cannot mutate the platform")
                if path.endswith("?limit=100"):
                    return {"runs": [{"id": r} for r in details]}, {}
                return details[path.rsplit("/", 1)[-1]], {}

        return event, env, ReadHttp()

    def previous(self, *, action="deliver", status="succeeded"):
        return {
            "id": "run_prior",
            "automation_id": "aut_test",
            "status": status,
            "item": {"event": {"data": {"action": action, "mode": "fenced-hold"}}},
            "attempts": [
                {
                    "id": "att_prior",
                    "n": 1,
                    "status": "cancelled" if status == "cancelled" else "succeeded",
                }
            ],
        }

    def test_fence_survives_snapshot_loss_and_refuses_effect_replay(self):
        # External effects may exist although a cancelled sandbox loses every journal write.
        for status in ("cancelled", "failed", "succeeded"):
            event, env, http = self.fence_fixture([self.previous(status=status)])
            with self.subTest(status=status), self.assertRaisesRegex(PolicyError, "Uncheckpointed"):
                FENCE(event, self.path, env, http)
        event, env, http = self.fence_fixture(retry=True)
        with self.assertRaisesRegex(PolicyError, "Uncertain cloud attempt"):
            FENCE(event, self.path, env, http)

    def test_adopted_checkpoint_allows_next_delivery_but_bad_receipt_does_not(self):
        prior = self.previous()
        event, env, http = self.fence_fixture([prior])
        receipt = {"automation_id": "aut_test", "run_id": "run_prior", "attempt_id": "att_prior"}
        SAVE(self.path / "cloud-fence.json", receipt)
        path, value = FENCE(event, self.path, env, http)
        self.assertEqual(path, self.path / "cloud-fence.json")
        self.assertEqual(value["run_id"], "run_now")
        for key, bad in (
            ("automation_id", "aut_other"),
            ("attempt_id", "att_other"),
            ("run_id", "run_missing"),
        ):
            SAVE(path, {**receipt, key: bad})
            with self.subTest(key=key), self.assertRaises(PolicyError):
                FENCE(event, self.path, env, http)

    def test_fence_refuses_truncated_history_and_separates_diagnostic_namespace(self):
        previous = [{**self.previous(action="status"), "id": f"run_{n}"} for n in range(99)]
        event, env, http = self.fence_fixture(previous)
        with self.assertRaisesRegex(PolicyError, "history window exhausted"):
            FENCE(event, self.path, env, http)
        previous = [self.previous(action="state-probe", status="cancelled")]
        event, env, http = self.fence_fixture(previous)
        FENCE(event, self.path, env, http)  # Diagnostic cancellation cannot poison product state.
        event, env, http = self.fence_fixture(previous, diagnostic=True)
        with self.assertRaisesRegex(PolicyError, "Uncheckpointed"):
            FENCE(event, self.path, env, http, diagnostic=True)

    def test_diagnostics_cannot_enable_execution_or_accept_arbitrary_commands(self):
        with self.assertRaises(PolicyError):
            self.invoke({"action": "state-probe", "mode": "commit", "command": "anything"})
        config = json.loads((self.path / "controller/settings.json").read_text())
        config["execution_enabled"] = True
        (self.path / "controller/settings.json").write_text(json.dumps(config))
        with self.assertRaises(PolicyError):
            self.invoke({"action": "state-probe", "mode": "commit"})

    def test_bundle_refuses_unrestricted_unverified_or_mismatched_mcp(self):
        baseline = json.loads((ROOT / "config/integrations.json").read_text())
        for failure in ("implicit_all", "wildcard", "undiscovered", "binding", "role"):
            with self.subTest(failure=failure):
                value = copy.deepcopy(baseline)
                connection = value["connections"][0]
                status = value["status"][0]
                if failure == "implicit_all":
                    connection.pop("tools")
                elif failure == "wildcard":
                    connection["tools"] = status["allowed_tools"] = ["*"]
                elif failure == "undiscovered":
                    connection["tools"] = status["allowed_tools"] = ["some_read"]
                elif failure == "binding":
                    value["bindings"][connection["name"]]["connection_id"] = "other"
                else:
                    value["role_connections"]["planner"].append("undeclared")
                with self.assertRaises(PolicyError):
                    VALIDATE(value)


if __name__ == "__main__":
    unittest.main()
