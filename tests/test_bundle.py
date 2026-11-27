"""The bundle carries the controller, preserves claims and starts with dispatch disabled."""

import contextlib
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path

from collegium_pipeline.domain import PolicyError

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts/build_bundle.py"))["build"]
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
        self.assertTrue(all(not s["attached_to_live_agents"] for s in integrations["status"]))
        self.assertTrue(all(s["allowed_tools"] == [] for s in integrations["status"]))


if __name__ == "__main__":
    unittest.main()
