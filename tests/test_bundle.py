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
        self.assertEqual(len(self.manifest["automations"]), 3)
        claims = json.loads((self.path / "claims.json").read_text())
        self.assertEqual(len(claims), 10)
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

    def test_cloud_package_size_and_isolated_import(self):
        files = self.manifest["automations"][0]["script"]["files"]
        self.assertLessEqual(sum((self.path / name).stat().st_size for name in files), 256_000)
        self.assertFalse((self.path / "controller/src/collegium_pipeline/runner.py").exists())
        program = (
            "import runpy; m=runpy.run_path("
            + repr(str(self.path / "controller/entry.py"))
            + "); m['main']({'action':'preflight'},root="
            + repr(str(self.path / "controller"))
            + ",environ={})"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", program],
            cwd=self.path,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["agent_started"])

    def test_cloud_service_rejects_scope_payload_before_any_network(self):
        config = json.loads((self.path / "controller/settings.json").read_text())
        for event in (
            {"action": "service-test", "mode": "run", "changes": {}},
            {"action": "service-test", "mode": "unknown"},
        ):
            http = unittest.mock.Mock()
            with self.assertRaises(PolicyError):
                ENTRY_MODULE["cloud_service"](event, self.path / "state", config, {}, http)
            http.request.assert_not_called()

    def test_manual_cloud_service_uses_delivery_engine_and_inspects_without_duplicates(self):
        from test_delivery import DeliveryTests as Harness

        from collegium_pipeline.domain import digest

        fixture = Harness()
        fixture.setUp()
        try:
            config = copy.deepcopy(fixture.config)
            config.update(
                execution_enabled=False,
                broker_enabled=False,
                allowed_paths=["tests/test_live_service.py"],
                recovery_store={"owner": "aut_owner"},
            )
            # This diagnostic uses the approved immutable red/green fixture.
            text = (
                '"""Temporary PR-only fault injection for the Collegium delivery conveyor."""\n\n'
                'import unittest\n\nEXPECTED = "green"\nACTUAL = "red"\n\n\n'
                "class LiveServiceTests(unittest.TestCase):\n"
                "    def test_service_phase(self):\n        self.assertEqual(ACTUAL, EXPECTED)\n"
            )
            config["service_test"] = {
                "initial_changes_digest": digest({"tests/test_live_service.py": text}),
                "repaired_changes_digest": digest(
                    {
                        "tests/test_live_service.py": text.replace(
                            'ACTUAL = "red"', 'ACTUAL = "green"'
                        )
                    }
                ),
                "failure_signature": "AssertionError",
                "test_name": "test_service_phase",
                "check_name": "test",
            }

            def mutate(packet, observed):
                if packet["stage"] in {"implementing", "fixing"}:
                    r = json.loads(observed["turn"]["answer"])
                    content = (
                        text
                        if packet["stage"] == "implementing"
                        else text.replace('ACTUAL = "red"', 'ACTUAL = "green"')
                    )
                    r["payload"]["changes"] = {"tests/test_live_service.py": content}
                    observed["turn"]["answer"] = json.dumps(r)

            fixture.http.mutate = mutate
            event = {"action": "service-test", "mode": "run"}
            environ = {
                "LAP_AUTOMATION_ID": "aut_owner",
                "LAP_RUN_ID": "run_cloud",
                "LAP_ATTEMPT_ID": "att_cloud",
                "PIPELINE_CONTROL_KEY": "fixture-only",
            }

            class Cloud:
                history = []
                paused = True

                def request(self, method, path, payload=None, **kwargs):
                    if path == "/api/automations/aut_owner":
                        return {"status": "paused" if self.paused else "active"}, {}
                    row = {
                        "id": environ["LAP_RUN_ID"],
                        "automation_id": "aut_owner",
                        "status": "running",
                        "attempts": [
                            {"id": environ["LAP_ATTEMPT_ID"], "n": 1, "status": "running"}
                        ],
                        "item": {"event": {"data": event.copy()}},
                    }
                    if path == "/api/automations/aut_owner/runs?limit=100":
                        return {"runs": [row, *self.history]}, {}
                    if path == "/api/automations/aut_owner/runs/" + row["id"]:
                        return row, {}
                    for old in self.history:
                        if path.endswith("/runs/" + old["id"]):
                            return old, {}
                    return fixture.http.request(method, path, payload, **kwargs)

            http, snapshots = Cloud(), []
            with (
                patch(
                    "collegium_pipeline.native_broker.NativeGithubApp", return_value=fixture.github
                ),
                patch("collegium_pipeline.recovery.Checkpoints"),
                patch(
                    "collegium_pipeline.recovery.WriteAhead",
                    return_value=unittest.mock.Mock(save=snapshots.append),
                ),
                patch("collegium_pipeline.delivery.failure_evidence", fixture.service_failure),
                patch("time.sleep"),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                from collegium_pipeline.transport import RemoteError

                def prior(status):
                    return {
                        "id": environ["LAP_RUN_ID"],
                        "automation_id": "aut_owner",
                        "status": status,
                        "attempts": [{"id": environ["LAP_ATTEMPT_ID"], "n": 1, "status": status}],
                        "item": {"event": {"data": event.copy()}},
                    }

                # A rejected run before the fence is harmless and must not wedge history.
                http.paused = False
                with self.assertRaisesRegex(PolicyError, "paused installed"):
                    ENTRY_MODULE["cloud_service"](event, self.path / "state", config, environ, http)
                marker = self.path / "state/no-dispatch/run_cloud-att_cloud.json"
                self.assertTrue(marker.exists())
                http.history = [prior("failed")]
                http.paused = True
                environ.update(LAP_RUN_ID="run_afterreject", LAP_ATTEMPT_ID="att_afterreject")

                # Real fixture mutation succeeds, then loses its response in this cloud slice.
                fixture.github.lose = "commit"
                with self.assertRaises(RemoteError):
                    ENTRY_MODULE["cloud_service"](event, self.path / "state", config, environ, http)
                self.assertEqual([op for op, _ in fixture.github.writes].count("commit"), 1)
                self.assertFalse(
                    (self.path / "state/no-dispatch/run_afterreject-att_afterreject.json").exists()
                )
                http.history.insert(0, prior("failed"))
                environ.update(LAP_RUN_ID="run_resume", LAP_ATTEMPT_ID="att_resume")
                result = ENTRY_MODULE["cloud_service"](
                    event, self.path / "state", config, environ, http
                )
                self.assertEqual(result, 0)
                summary = json.loads(output.getvalue().split("COLLEGIUM_SERVICE_RESULT=")[-1])
                self.assertEqual(summary["state"], "ready_for_acceptance")
                self.assertEqual(summary["repairs"], 1)
                self.assertEqual(len(summary["workers"]), 8)
                self.assertEqual(fixture.http.created, 8)
                self.assertEqual([op for op, _ in fixture.github.writes].count("commit"), 2)
                self.assertGreater(len(snapshots), 8)
                created, writes = fixture.http.created, len(fixture.github.writes)
                http.history = [
                    {
                        "id": "run_resume",
                        "automation_id": "aut_owner",
                        "status": "succeeded",
                        "attempts": [{"id": "att_resume", "n": 1, "status": "succeeded"}],
                        "item": {"event": {"data": event.copy()}},
                    }
                ]
                event["mode"] = "inspect"
                environ.update(LAP_RUN_ID="run_inspect", LAP_ATTEMPT_ID="att_inspect")
                self.assertEqual(
                    ENTRY_MODULE["cloud_service"](
                        event, self.path / "state", config, environ, http
                    ),
                    0,
                )
                self.assertEqual(
                    (fixture.http.created, len(fixture.github.writes)), (created, writes)
                )
            self.assertFalse(config["execution_enabled"])
            self.assertFalse(config["broker_enabled"])
        finally:
            fixture.tearDown()

    def test_github_probe_rejects_caller_selected_payloads_before_network(self):
        for event in (
            {"action": "recovery-probe", "mode": "github-commit", "changes": {"bad": "data"}},
            {"action": "recovery-probe", "mode": "github-unknown"},
        ):
            with self.assertRaises(PolicyError):
                ENTRY(
                    event,
                    root=self.path / "controller",
                    environ={
                        "ARANARIUM_STATE_DIR": str(self.path / "state"),
                        "PIPELINE_CONTROL_KEY": "fixture-key",
                    },
                    http=object(),
                )

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
        outputs = []
        try:
            for child in children:
                outputs.append(child.communicate(timeout=20))
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        results = []
        for child, (output, error) in zip(children, outputs, strict=True):
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

    def fence_fixture(
        self, previous=(), *, retry=False, diagnostic=False, current="run_now", attempt="att_now"
    ):
        event = (
            {"action": "state-probe", "mode": "fenced-check"}
            if diagnostic
            else {"action": "deliver", "live": True, "run_id": "product"}
        )
        env = {
            "LAP_AUTOMATION_ID": "aut_test",
            "LAP_RUN_ID": current,
            "LAP_ATTEMPT_ID": attempt,
        }
        now = {
            "id": current,
            "automation_id": "aut_test",
            "status": "running",
            "item": {"event": {"data": event}},
            "attempts": [{"id": attempt, "n": 1, "status": "running"}],
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

    def test_paginated_history_never_clears_the_fence(self):
        event, env, delegate = self.fence_fixture()

        class PagedHttp:
            def request(self, method, path):
                body, headers = delegate.request(method, path)
                if path.endswith("?limit=100"):
                    body["has_more"] = True
                return body, headers

        for saved in (False, True):
            if saved:
                SAVE(
                    self.path / "cloud-fence.json",
                    {
                        "automation_id": "aut_test",
                        "run_id": "run_prior",
                        "attempt_id": "att_prior",
                    },
                )
            with self.subTest(receipt=saved), self.assertRaisesRegex(PolicyError, "Paginated"):
                FENCE(event, self.path, env, PagedHttp())

    def test_normal_failure_saves_receipt_with_journal_including_disabled_delivery(self):
        from collegium_pipeline.transport import RemoteError

        event, env, http = self.fence_fixture()
        root = self.path / "controller"
        env.update(ARANARIUM_STATE_DIR=str(self.path / "state"), PIPELINE_CONTROL_KEY="fixture-key")
        checkpoint = self.path / "state/collegium-pipeline/cloud-fence.json"
        # Disabled delivery is rejected AFTER the fence; its harmless failure is accounted for.
        with patch("collegium_pipeline.cli.main") as dispatch:
            with self.assertRaisesRegex(PolicyError, "disabled"):
                ENTRY(event, root=root, environ=env, http=http)
        dispatch.assert_not_called()
        self.assertEqual(json.loads(checkpoint.read_text())["run_id"], "run_now")
        checkpoint.unlink()
        config = json.loads((root / "settings.json").read_text())
        config["execution_enabled"] = True
        (root / "settings.json").write_text(json.dumps(config))
        with patch("collegium_pipeline.cli.main", side_effect=RemoteError("Response lost")):
            with patch.dict(os.environ, {}, clear=False), self.assertRaises(RemoteError):
                ENTRY(event, root=root, environ=env, http=http)
        self.assertEqual(json.loads(checkpoint.read_text())["attempt_id"], "att_now")
        # Represent that adopted receipt as the previous failed run in the next sandbox.
        SAVE(
            checkpoint,
            {"automation_id": "aut_test", "run_id": "run_prior", "attempt_id": "att_prior"},
        )
        previous = self.previous(status="failed")
        previous["attempts"][0]["status"] = "failed"
        next_event, next_env, next_http = self.fence_fixture([previous])
        FENCE(next_event, checkpoint.parent, next_env, next_http)

    def test_pre_dispatch_failures_are_accounted_without_hiding_older_ambiguity(self):
        from collegium_pipeline.transport import RemoteError

        for failure in ("missing-run", "missing-key", "transient-api"):
            with self.subTest(failure=failure):
                event, env, _ = self.fence_fixture(current="run_" + failure.replace("-", ""))
                if failure == "missing-run":
                    event.pop("run_id")
                env.update(
                    ARANARIUM_STATE_DIR=str(self.path / failure), PIPELINE_CONTROL_KEY="fixture-key"
                )
                if failure == "missing-key":
                    env.pop("PIPELINE_CONTROL_KEY")

                class BrokenHttp:
                    def request(self, method, path):
                        raise RemoteError("Temporary API read failure")

                with patch("collegium_pipeline.cli.main") as dispatch:
                    with self.assertRaises((PolicyError, RemoteError)):
                        ENTRY(event, root=self.path / "controller", environ=env, http=BrokenHttp())
                dispatch.assert_not_called()
                prior = {
                    "id": env["LAP_RUN_ID"],
                    "automation_id": "aut_test",
                    "status": "failed",
                    "item": {"event": {"data": event}},
                    "attempts": [{"id": "att_now", "n": 1, "status": "failed"}],
                }
                next_event, next_env, next_http = self.fence_fixture([prior], current="run_next")
                state = self.path / failure / "collegium-pipeline"
                FENCE(next_event, state, next_env, next_http)
                # A no-dispatch record is NOT an anchor past an older uncertain effect.
                next_event, next_env, next_http = self.fence_fixture(
                    [prior, self.previous(status="cancelled")], current="run_next"
                )
                with self.assertRaisesRegex(PolicyError, "Uncheckpointed"):
                    FENCE(next_event, state, next_env, next_http)
                # A retry record alone cannot account for an earlier lost attempt.
                prior["attempts"].append({"id": "att_lost", "n": 2, "status": "failed"})
                next_event, next_env, next_http = self.fence_fixture([prior], current="run_next")
                with self.assertRaisesRegex(PolicyError, "Uncheckpointed"):
                    FENCE(next_event, state, next_env, next_http)

    def test_delivery_entry_cannot_dispatch_after_lost_snapshot(self):
        event, env, http = self.fence_fixture([self.previous(status="cancelled")])
        root = self.path / "controller"
        config = json.loads((root / "settings.json").read_text())
        config["execution_enabled"] = True
        config.pop("recovery_store", None)  # Legacy uncheckpointed attempts still cannot resume.
        (root / "settings.json").write_text(json.dumps(config))
        env.update(ARANARIUM_STATE_DIR=str(self.path / "state"), PIPELINE_CONTROL_KEY="fixture-key")
        with patch("collegium_pipeline.cli.main") as dispatch:
            with self.assertRaisesRegex(PolicyError, "Uncheckpointed"):
                ENTRY(event, root=root, environ=env, http=http)
        dispatch.assert_not_called()

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
