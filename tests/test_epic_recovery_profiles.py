import contextlib
import io
import json
import runpy
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, call, patch

import test_epic_cloud
import test_recovery

from collegium_pipeline.capacity import Capacity
from collegium_pipeline.config import config_digest
from collegium_pipeline.domain import PolicyError, Selection, Task, digest
from collegium_pipeline.epic_cloud import dispatch, launch_evidence
from collegium_pipeline.platform import WorkerBinding
from collegium_pipeline.recovery import (
    WriteAhead,
    intended_execution,
    reconcile_existing,
    reconcile_workers,
    recovery_profiles,
)
from collegium_pipeline.store import Journal

CONTROLLER = Path(__file__).resolve().parents[1] / "scripts" / "bundle_controller.py"


class RecoveryProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_recovery.RecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.singleton = self.fixture.config
        self.epic = {**self.singleton, "epic": {}}
        self.profiles = recovery_profiles(self.singleton, self.epic)

    def admit(self, profile, key):
        return self.fixture.journal.admit(
            Task("text", key, profile["repository"], key, "recover"),
            config_digest(profile),
        )

    def pending(self, profile, key):
        journal = self.fixture.journal
        run = self.admit(profile, key)
        intent = journal.begin_dispatch(run, 0, {}, "request")
        journal.record_launch(run, intent, "ses_existing", "turn_existing")
        operation = {
            "kind": "broker",
            "operation": "branch",
            "run_id": run,
            "key": "branch",
            "payload": {"sha": test_recovery.BASE},
        }
        journal.record(run, "effect_attempt", {"operation": operation})
        return run

    def test_workers_and_broker_effects_use_their_own_profiles(self):
        standalone = self.pending(self.singleton, "standalone")
        epic = self.pending(self.epic, "epic")
        for invocation in (self.singleton, self.epic):
            with (
                self.subTest(invocation=config_digest(invocation)),
                patch(
                    "collegium_pipeline.recovery.reconcile_workers", wraps=reconcile_workers
                ) as workers,
                patch("collegium_pipeline.recovery.reconcile_broker", return_value={}) as broker,
            ):
                result = reconcile_existing(
                    invocation,
                    self.fixture.journal,
                    self.fixture.http,
                    self.fixture.github,
                    profiles=self.profiles,
                )
                self.assertEqual(result["external_mutations"], 0)
                self.assertEqual(
                    {config_digest(c.args[0]): c.kwargs["run_ids"] for c in workers.call_args_list},
                    {config_digest(self.singleton): {standalone}, config_digest(self.epic): {epic}},
                )
                self.assertEqual(
                    {c.args[3]["run_id"]: c.args[0] for c in broker.call_args_list},
                    {standalone: self.singleton, epic: self.epic},
                )
        with self.assertRaisesRegex(PolicyError, "different frozen configuration"):
            reconcile_existing(
                self.singleton, self.fixture.journal, self.fixture.http, self.fixture.github
            )
        self.assertEqual(self.fixture.http.posts, [])

    def test_unknown_or_foreign_pending_profile_refuses_before_observation(self):
        self.pending(self.singleton, "known")
        untrusted = {**self.epic, "epic": {"different": True}}
        foreign = {
            **self.epic,
            "recovery_store": {**self.epic["recovery_store"], "owner": "aut_other"},
        }
        for profile, registry in (
            (untrusted, self.profiles),
            (foreign, recovery_profiles(self.singleton, foreign)),
        ):
            with self.subTest(profile=profile):
                run = self.pending(profile, config_digest(profile))
                http = Mock()
                with self.assertRaisesRegex(PolicyError, "different"):
                    reconcile_existing(
                        self.singleton, self.fixture.journal, http, Mock(), profiles=registry
                    )
                http.request.assert_not_called()
                self.fixture.journal.record(run, "broker_done", {"key": "branch"})
                self.fixture.journal.connection.execute(
                    "UPDATE runs SET pending_intent=NULL WHERE id=?", (run,)
                )

    def test_signed_snapshot_restores_both_origin_profiles_and_separates_read_admissions(self):
        controller = runpy.run_path(str(CONTROLLER))["reconcile_controller"]
        fixture = self.fixture
        for idx, (origin, invocation) in enumerate(
            ((self.singleton, self.epic), (self.epic, self.singleton))
        ):
            with self.subTest(origin=config_digest(origin)):
                root = self.admit(origin, f"snapshot-{idx}")
                identity = {**fixture.identity, "run_id": f"run_lost{idx}"}
                http = Mock()
                http.request.return_value = (
                    {
                        **fixture.http.prior,
                        "id": identity["run_id"],
                        "started_at": idx,
                        "item": {
                            "event": {
                                "data": {"action": "epic", "operation": "pause"}
                                if idx
                                else {"action": "deliver"}
                            }
                        },
                    },
                    {},
                )
                write = WriteAhead(
                    origin, fixture.journal, fixture.artifacts.directory, fixture.store, identity
                )
                fixture.journal.before_effect = write.save
                fixture.journal.checkpoint({"kind": "tick", "run_id": root})
                target = fixture.state / "cross-profile"
                with (
                    patch("collegium_pipeline.recovery.Checkpoints", return_value=fixture.store),
                    patch("collegium_pipeline.native_broker.NativeGithubApp", return_value=Mock()),
                ):
                    receipt = controller(invocation, target, http, "key", profiles=self.profiles)
                self.assertEqual(receipt["config_digest"], config_digest(origin))
                self.assertEqual(receipt["root"], root)
                self.assertEqual(receipt["external_mutations"], 0)
                self.assertEqual(http.request.call_count, 1)
        with contextlib.closing(Journal(target / "recovery-reads.sqlite3")) as scratch:
            rows = scratch.connection.execute("SELECT source_id, config_digest FROM runs")
            self.assertEqual(
                set(map(tuple, rows)),
                {
                    ("recovery-reads-v1:" + config_digest(profile), config_digest(profile))
                    for profile in (self.singleton, self.epic)
                },
            )

    def test_unknown_or_foreign_checkpoint_origin_refused_before_import(self):
        controller = runpy.run_path(str(CONTROLLER))["reconcile_controller"]
        for config, identity in (
            ({**self.epic, "epic": {"changed": True}}, self.fixture.identity),
            (self.epic, {**self.fixture.identity, "automation_id": "aut_foreign"}),
        ):
            store = Mock()
            store.get.return_value = (
                "checkpoint",
                {
                    "schema_version": "checkpoint/v1",
                    "config_digest": config_digest(config),
                    "identity": identity,
                },
            )
            http = Mock()
            state = self.fixture.state / "rejected"
            with (
                patch("collegium_pipeline.recovery.Checkpoints", return_value=store),
                self.assertRaises(PolicyError),
            ):
                controller(self.singleton, state, http, "key", profiles=self.profiles)
            http.request.assert_not_called()
            self.assertFalse((state / "journal.sqlite3").exists())
            self.assertFalse((state / "recovery-reads.sqlite3").exists())


class EpicOperationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_epic_cloud.EpicCloudTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.checkpoints = Mock()

    def invoke(self, operation, config=None, **details):
        fixture = self.fixture
        with (
            patch("collegium_pipeline.epic_cloud.Checkpoints"),
            patch("collegium_pipeline.epic_cloud.WriteAhead", return_value=self.checkpoints),
            patch("collegium_pipeline.epic_cloud.NativeGithubApp"),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            dispatch(
                {"action": "epic", "operation": operation, **details},
                fixture.state,
                config if config is not None else fixture.config,
                fixture.environ,
                fixture.http,
                fixture.hooks,
            )
        return json.loads(output.getvalue().split("COLLEGIUM_EPIC_RESULT=")[1])

    def test_foreign_controller_receives_no_dispatch_receipt(self):
        fixture = self.fixture
        fixture.identity["automation_id"] = "aut_other"
        execution = intended_execution(fixture.config)
        for operation, details in (
            ("prepare", {"graph": fixture.fixture.graph}),
            ("import-jira", {"key": "EPIC-1"}),
            ("pause", {"run_id": "missing"}),
            ("resume", {"run_id": "missing"}),
            ("tick", {"run_id": "missing", "live": True}),
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(PolicyError, "owner"):
                self.invoke(operation, execution, **details)
        fixture.hooks["cloud_fence"].assert_not_called()
        fixture.hooks["reconcile_controller"].assert_not_called()
        fixture.http.request.assert_not_called()
        self.assertFalse((fixture.state / "journal.sqlite3").exists())
        receipt = fixture.state / "no-dispatch" / "run_test-att_test.json"
        self.assertEqual(json.loads(receipt.read_text()), fixture.identity)

    def test_disabled_pause_and_resume_with_pending_intended_execution_admission(self):
        fixture = self.fixture
        result = self.invoke("prepare", graph=fixture.fixture.graph)
        child = next(iter(result["nodes"].values()))["run_id"]
        with contextlib.closing(Journal(fixture.state / "journal.sqlite3")) as journal:
            intent = journal.begin_dispatch(child, 0, {}, "request")
            journal.record_launch(child, intent, "ses_before", "turn_before")
        for operation in ("pause", "resume"):
            result = self.invoke(operation, run_id=result["run_id"])
            self.assertEqual(result["paused"], operation == "pause")
            self.assertFalse(result["agent_started"])
            self.assertEqual(result["confirmed_launches"], [])
            self.assertEqual(result["uncertain_launches"], [])
        fixture.http.request.assert_not_called()

    def test_emergency_pause_does_not_reconcile_unknown_launches(self):
        fixture = self.fixture
        execution = intended_execution(fixture.config)
        result = self.invoke("prepare", graph=fixture.fixture.graph)
        root = result["run_id"]
        active, waiting = [child["run_id"] for child in result["nodes"].values()][:2]
        path = fixture.state / "journal.sqlite3"
        with contextlib.closing(Journal(path)) as journal:
            capacity = Capacity(journal, execution)
            capacity.activate(active, root)
            self.assertTrue(capacity.acquire(active, epic_owner=root))
            capacity.activate(waiting, root)
            unrelated = journal.admit(
                Task("text", "standalone", execution["repository"], "Standalone", "Recover"),
                config_digest(execution),
            )
            journal.before_effect = Mock()
            intents = {}
            worker = execution["workers"]["planner"]
            binding = WorkerBinding(**{**worker, "selection": Selection(**worker["selection"])})
            for run in (active, unrelated):
                row = journal.get(run)
                request = {
                    "binding": asdict(binding),
                    "prompt": "Unconfirmed test launch",
                    "config": row["config_digest"],
                    "acceptance": row["task"],
                }
                intent = journal.begin_dispatch(run, 0, worker["selection"], digest(request))
                journal.record(
                    run,
                    "dispatch_request",
                    {"intent": intent, "stage": row["state"], "request": request},
                )
                journal.checkpoint({"kind": "session_create", "run_id": run, "intent": intent})
                journal.unknown_launch(run, intent)
                intents[run] = intent
        self.checkpoints.reset_mock()
        result = self.invoke("pause", run_id=root)
        self.assertTrue(result["paused"])
        self.assertFalse(result["agent_started"])
        self.assertEqual(result["uncertain_launches"], [])
        self.checkpoints.save.assert_called_once_with({"kind": "tick", "run_id": root})
        with self.assertRaisesRegex(PolicyError, "disabled"):
            self.invoke("tick", run_id=root, live=True)
        fixture.http.request.assert_not_called()
        agent_id = worker["agent_id"]
        fixture.http.request.side_effect = [(fixture.fixture.http.agents[agent_id], {}), ([], {})]
        with self.assertRaisesRegex(PolicyError, "Named session absent or ambiguous"):
            self.invoke("resume", run_id=root)
        with contextlib.closing(Journal(path)) as journal:
            self.assertTrue(
                json.loads(
                    journal.connection.execute(
                        "SELECT document FROM epics WHERE run_id=?", (root,)
                    ).fetchone()[0]
                )["paused"]
            )
            self.assertEqual(journal.get(active)["pending_intent"], intents[active])
            self.assertEqual(journal.get(unrelated)["pending_intent"], intents[unrelated])
            capacity = Capacity(journal, execution)
            self.assertEqual(capacity.get(active)["state"], "active")
            self.assertEqual(capacity.get(waiting)["state"], "dormant")
        self.assertEqual(
            fixture.http.request.call_args_list,
            [
                call("GET", "/api/agents/" + agent_id),
                call("GET", "/session?project_id=project&foreign=none"),
            ],
        )

    def test_launch_receipt_uses_only_effects_after_sequence_boundary(self):
        fixture = self.fixture
        result = self.invoke("prepare", graph=fixture.fixture.graph)
        children = [child["run_id"] for child in result["nodes"].values()]
        confirmed, uncertain = children[:2]
        with contextlib.closing(Journal(fixture.state / "journal.sqlite3")) as journal:
            journal.record(confirmed, "launched", {"intent": "old"})
            after = journal.connection.execute("SELECT MAX(sequence) FROM events").fetchone()[0]
            self.assertFalse(launch_evidence(journal, after)["agent_started"])
            for run, intent in ((confirmed, "confirmed"), (uncertain, "uncertain")):
                journal.record(
                    run,
                    "effect_attempt",
                    {"operation": {"kind": "prompt", "run_id": run, "intent": intent}},
                )
            journal.record(confirmed, "launched", {"intent": "confirmed"})
            receipt = launch_evidence(journal, after)
            self.assertTrue(receipt["agent_started"])
            self.assertEqual([r["intent"] for r in receipt["confirmed_launches"]], ["confirmed"])
            self.assertEqual([r["intent"] for r in receipt["uncertain_launches"]], ["uncertain"])

    def test_status_of_unknown_epic_does_not_create_state(self):
        fixture = self.fixture
        with self.assertRaisesRegex(PolicyError, "Epic missing"):
            dispatch(
                {"action": "epic", "operation": "status", "run_id": "missing"},
                fixture.state,
                fixture.config,
                fixture.environ,
                fixture.http,
                fixture.hooks,
            )
        self.assertFalse(fixture.state.exists())
        fixture.hooks["cloud_fence"].assert_not_called()
        fixture.http.request.assert_not_called()
