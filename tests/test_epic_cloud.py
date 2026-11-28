import contextlib
import copy
import io
import json
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collegium_pipeline.config import config_digest
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.epic_cloud import dispatch
from collegium_pipeline.epics import Epics
from collegium_pipeline.store import Journal


class EpicCloudTests(unittest.TestCase):
    def setUp(self):
        from test_epics import EpicTests

        self.fixture = EpicTests()
        self.fixture.setUp()
        self.state = self.fixture.fixture.path / "cloud-state"
        self.config = {
            **copy.deepcopy(self.fixture.config),
            "execution_enabled": False,
            "broker_enabled": False,
            "recovery_store": {"owner": "aut_test"},
        }
        self.identity = {
            "automation_id": "aut_test",
            "run_id": "run_test",
            "attempt_id": "att_test",
        }
        module = runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "scripts/bundle_controller.py")
        )
        self.hooks = {
            "cloud_identity": lambda _: self.identity,
            "cloud_fence": Mock(return_value=(self.state / "cloud-fence.json", self.identity)),
            "save_receipt": module["save_receipt"],
            "reconcile_controller": Mock(),
        }
        self.http = Mock()
        self.environ = {"PIPELINE_CONTROL_KEY": "fixture-key"}

    def tearDown(self):
        self.fixture.tearDown()

    def test_disabled_prepare_pins_intended_contract_without_dispatch_and_survives_enable(self):
        operations = []
        with (
            patch("collegium_pipeline.epic_cloud.Checkpoints"),
            patch(
                "collegium_pipeline.epic_cloud.WriteAhead",
                return_value=Mock(save=operations.append),
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = dispatch(
                {"action": "epic", "operation": "prepare", "graph": self.fixture.graph},
                self.state,
                self.config,
                self.environ,
                self.http,
                self.hooks,
            )
        self.assertEqual(result, 0)
        receipt = json.loads(output.getvalue().split("COLLEGIUM_EPIC_RESULT=")[1])
        root = receipt["run_id"]
        execution = {**self.config, "execution_enabled": True, "broker_enabled": True}
        self.assertEqual(receipt["admission_config_digest"], config_digest(execution))
        self.assertFalse(receipt["agent_started"])
        self.http.request.assert_not_called()
        journal = Journal(self.state / "journal.sqlite3")
        try:
            engine = Epics(execution, journal, None, None, self.state / "artifacts")
            self.assertEqual(engine.load(root)["state"], "queued")
            self.assertEqual(journal.get(root)["config_digest"], config_digest(execution))
        finally:
            journal.close()
        self.assertEqual({op["kind"] for op in operations}, {"tick"})

    def test_disabled_tick_cannot_grant_itself_authority_and_records_no_dispatch(self):
        with self.assertRaisesRegex(PolicyError, "disabled"):
            dispatch(
                {"action": "epic", "operation": "tick", "run_id": "not-a-pilot", "live": True},
                self.state,
                self.config,
                self.environ,
                self.http,
                self.hooks,
            )
        self.hooks["cloud_fence"].assert_not_called()
        self.http.request.assert_not_called()
        self.assertTrue((self.state / "no-dispatch/run_test-att_test.json").is_file())
        self.assertFalse((self.state / "journal.sqlite3").exists())

    def test_preflight_uses_only_readonly_mcp_and_creates_no_admission(self):
        module = types.ModuleType("lap_mcp")
        module.connection = Mock()
        with (
            patch.dict(sys.modules, {"lap_mcp": module}),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(
                dispatch(
                    {"action": "epic", "operation": "preflight"},
                    self.state,
                    self.config,
                    self.environ,
                    self.http,
                    self.hooks,
                ),
                0,
            )
        module.connection.assert_called_once_with("atlassian-rovo")
        module.connection.return_value.call.assert_called_once_with(
            "getAccessibleAtlassianResources"
        )
        result = json.loads(output.getvalue().split("COLLEGIUM_EPIC_PREFLIGHT=")[1])
        self.assertTrue(result["jira_connection_read_verified"])
        self.assertFalse(result["agent_started"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse((self.state / "journal.sqlite3").exists())

    def test_event_cannot_override_policy_and_unresolved_epic_history_is_fenced(self):
        with self.assertRaises(PolicyError):
            dispatch(
                {
                    "action": "epic",
                    "operation": "prepare",
                    "graph": self.fixture.graph,
                    "execution_enabled": True,
                },
                self.state,
                self.config,
                self.environ,
                self.http,
                self.hooks,
            )
        self.hooks["cloud_fence"].assert_not_called()
        from test_bundle import BundleTests

        fixture = BundleTests()
        fixture.setUp()
        try:
            module = runpy.run_path(
                str(Path(__file__).resolve().parents[1] / "scripts/bundle_controller.py")
            )
            for operation in ("prepare", "tick", "status", "preflight"):
                prior = fixture.previous(status="cancelled")
                prior["item"]["event"]["data"] = {"action": "epic", "operation": operation}
                event, env, http = fixture.fence_fixture([prior])
                if operation in {"prepare", "tick"}:
                    with self.assertRaisesRegex(PolicyError, "Uncheckpointed"):
                        module["cloud_fence"](event, fixture.path, env, http)
                else:
                    module["cloud_fence"](event, fixture.path, env, http)
        finally:
            fixture.tearDown()
