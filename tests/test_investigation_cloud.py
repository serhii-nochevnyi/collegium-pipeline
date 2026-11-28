"""Cloud entry boundaries and complete lost-snapshot investigation recovery."""

import contextlib
import copy
import io
import json
import runpy
import shutil
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_investigations
from test_recovery import AgentsHttp, DiskStore

from collegium_pipeline.config import config_digest
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.investigation_cloud import dispatch
from collegium_pipeline.investigations import Investigations
from collegium_pipeline.platform import agent_digest
from collegium_pipeline.recovery import WriteAhead, intended_execution, restore_checkpoint
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError

ROOT = Path(__file__).resolve().parents[1]


class InvestigationCloudTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_investigations.InvestigationTests()
        self.fixture.setUp()
        self.state = self.fixture.path / "cloud"
        self.config = {
            **copy.deepcopy(self.fixture.config),
            "execution_enabled": False,
            "recovery_store": {"owner": "aut_owner"},
        }
        self.identity = {
            "automation_id": "aut_owner",
            "run_id": "run_current",
            "attempt_id": "att_current",
        }
        self.module = runpy.run_path(str(ROOT / "scripts/bundle_controller.py"))
        self.hooks = {
            "cloud_identity": lambda _: self.identity,
            "cloud_fence": Mock(return_value=(self.state / "cloud-fence.json", self.identity)),
            "reconcile_controller": Mock(),
            "save_receipt": self.module["save_receipt"],
        }
        self.sources = Mock()
        self.sources.capture.return_value = self.fixture.sources
        self.env = {"PIPELINE_CONTROL_KEY": "fake-control-key"}

    def tearDown(self):
        self.fixture.tearDown()

    def test_preparation_is_checkpointed_without_a_paid_turn_or_write_authority(self):
        with (
            patch("collegium_pipeline.investigation_cloud.Checkpoints"),
            patch(
                "collegium_pipeline.investigation_cloud.WriteAhead", return_value=Mock(save=Mock())
            ) as checkpoint,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            dispatch(
                {"action": "investigate", "operation": "prepare", "intake": self.fixture.intake},
                self.state,
                self.config,
                self.env,
                self.fixture.http,
                self.hooks,
                sources=self.sources,
            )
        result = json.loads(output.getvalue().split("=", 1)[1])
        self.assertEqual(result["state"], "assessing")
        self.assertFalse(result["pilot_selected"])
        self.assertEqual(self.fixture.http.created, 0)
        self.assertFalse(checkpoint.call_args.args[0]["broker_enabled"])
        self.assertTrue(checkpoint.return_value.save.called)
        self.assertTrue((self.state / "cloud-fence.json").exists())

    def test_event_cannot_enable_mutations_or_skip_live_authorization(self):
        for event in (
            {"action": "investigate", "operation": "tick", "run_id": "x", "live": False},
            {
                "action": "investigate",
                "operation": "prepare",
                "intake": self.fixture.intake,
                "broker_enabled": True,
            },
            {"action": "deliver", "operation": "preflight"},
        ):
            with self.assertRaises(PolicyError):
                dispatch(
                    event,
                    self.state,
                    self.config,
                    self.env,
                    self.fixture.http,
                    self.hooks,
                    sources=self.sources,
                )
        self.hooks["cloud_fence"].assert_not_called()
        self.assertEqual(self.fixture.http.created, 0)
        self.assertFalse(intended_execution(self.config)["broker_enabled"])

    def test_fence_treats_lost_investigation_dispatch_as_unsafe(self):
        from test_bundle import BundleTests

        f = BundleTests()
        f.setUp()
        try:
            prior = f.previous(status="cancelled")
            prior["item"]["event"]["data"] = {"action": "investigate", "operation": "tick"}
            event, env, http = f.fence_fixture([prior])
            from collegium_pipeline.recovery import ExternalRecoveryRequired

            with self.assertRaises(ExternalRecoveryRequired):
                self.module["cloud_fence"](event, f.path, env, http, investigation=True)
            prior["item"]["event"]["data"]["operation"] = "preflight"
            event, env, http = f.fence_fixture([prior])
            self.module["cloud_fence"](event, f.path, env, http, investigation=True)
        finally:
            f.tearDown()

    def test_signed_snapshot_restore_reconciles_original_unknown_prompt_without_duplicate(self):
        cfg = copy.deepcopy(self.fixture.config)
        cfg["recovery_store"] = {
            "owner": "aut_owner",
            "automation_id": "aut_store",
            "approved_digest": "a" * 64,
        }
        binding = cfg["workers"]["assessor:sonnet:low"]
        agent = copy.deepcopy(self.fixture.http.agents[binding["agent_id"]])
        agent["id"] = "agent_test"
        binding.update(agent_id="agent_test", approved_agent_digest=agent_digest(agent))
        http = AgentsHttp(agent, lose="prompt")
        http.prior["item"]["event"]["data"] = {"action": "investigate", "operation": "tick"}
        self.state.mkdir()
        journal = Journal(self.state / "journal.sqlite3")
        engine = Investigations(cfg, journal, http, self.state / "artifacts")
        root = engine.admit(self.fixture.intake, self.fixture.sources)["run_id"]
        store = DiskStore(self.fixture.path / "independent")
        identity = {"automation_id": "aut_owner", "run_id": "run_lost", "attempt_id": "att_lost"}
        journal.before_effect = WriteAhead(
            cfg, journal, self.state / "artifacts", store, identity
        ).save
        with self.assertRaises(RemoteError):
            engine.step(root)
        self.assertEqual(len(http.sessions), 1)
        self.assertEqual(len(http.turns), 1)
        journal.close()
        shutil.rmtree(self.state)
        restored = restore_checkpoint(cfg, self.state, store, http, None)
        self.assertTrue(restored)
        journal = Journal(self.state / "journal.sqlite3")
        try:
            loaded = Investigations(cfg, journal, http, self.state / "artifacts")
            self.assertEqual(loaded.load(root)["state"], "assessing")
            rows = loaded.status(root)["workers"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["session_id"], "ses_known")
            self.assertEqual(rows[0]["turn_id"], "run_turn")
            before = len(http.posts)
            restore_checkpoint(cfg, self.state, store, http, None)
            self.assertEqual(len(http.posts), before)
            self.assertEqual(journal.get(root)["config_digest"], config_digest(cfg))
        finally:
            journal.close()
