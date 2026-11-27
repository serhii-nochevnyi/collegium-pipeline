"""The bundle carries the controller, preserves claims and starts with dispatch disabled."""

import contextlib
import copy
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collegium_pipeline.domain import PolicyError
from collegium_pipeline.platform import agent_digest

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts/build_bundle.py"))["build"]
VALIDATE = runpy.run_path(str(ROOT / "scripts/build_bundle.py"))["validate_integrations"]
ENTRY = runpy.run_path(str(ROOT / "scripts/bundle_controller.py"))["main"]


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
