"""Fixed live diagnostic boundaries and lost-snapshot recovery, without paid calls."""

import base64
import copy
import importlib.util
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collegium_pipeline.config import config_digest, load_config
from collegium_pipeline.delivery_workers import checkout_command
from collegium_pipeline.domain import PolicyError, digest
from collegium_pipeline.epic_service import baseline, fixtures, graph, observe_overlap, paths, run
from collegium_pipeline.recovery import mac

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "epic_service_guard", ROOT / "scripts/epic_service_broker.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class EpicServiceTests(unittest.TestCase):
    def setUp(self):
        import os

        self.secret = "unit-test-service-key"
        self.key_patch = patch.dict(os.environ, {"PIPELINE_CONTROL_KEY": self.secret})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.service = json.loads((ROOT / "config/epic-service.json").read_text())
        self.config = load_config(
            ROOT / ".github/lap/collegium-pipeline/controller/epic-service-settings.json"
        )
        self.policy = {
            k: self.service[k]
            for k in ("suite_id", "base_branch", "baseline", "main_sha", "ci_probe", "expires_at")
        }
        self.policy["fixtures"] = dict(zip(paths(), fixtures().values(), strict=True))
        self.policy["graph_digest"] = digest(graph(self.config))
        self.scope = {k: self.config[k] for k in ("repository", "base_branch", "allowed_paths")}
        self.head = "a" * 40
        self.pr = {
            "node_id": "PR_child",
            "state": "open",
            "draft": False,
            "merged": False,
            "head": {"ref": "collegium/" + "1" * 36, "sha": self.head, "repo": {"id": 1474663859}},
            "base": {"ref": self.service["base_branch"], "repo": {"id": 1474663859}},
            "body": "<!-- collegium-run:" + "1" * 36 + " -->",
        }
        self.check = {
            "id": 1,
            "name": "quality",
            "head_sha": self.head,
            "status": "completed",
            "conclusion": "success",
            "app": {"slug": "github-actions"},
        }
        self.request = {
            "method": "SERVICE_MERGE",
            "path": "/repos/" + self.config["repository"] + "/pulls/6/merge",
            "payload": {"sha": self.head},
        }
        body = {
            "purpose": "ready",
            "suite_id": self.policy["suite_id"],
            "graph_digest": self.policy["graph_digest"],
            "task_key": "A",
            "child_id": "1" * 36,
            "base_branch": self.policy["base_branch"],
            "head": self.head,
            "branch": self.pr["head"]["ref"],
            "pr": {"number": 6, "node_id": "PR_child"},
            "validation_session": "ses_validation",
            "review_session": "ses_review",
        }
        self.request["payload"]["acceptance"] = {"body": body, "mac": mac(body, self.secret)}

    def read(self, path):
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": self.policy["main_sha"]}}
        if path.endswith("/git/ref/heads/" + self.policy["base_branch"]):
            return {"object": {"sha": self.policy["baseline"]}}
        if path.endswith("/pulls/6"):
            return self.pr
        if "/files?" in path:
            return [{"filename": paths()[0], "status": "added"}]
        if "/contents/" in path:
            return {"content": base64.b64encode(fixtures()["A"].encode()).decode()}
        if "/check-runs?" in path:
            return {"total_count": 1, "check_runs": [self.check]}
        raise AssertionError(path)

    def test_manual_service_merge_is_exact_fixture_base_and_actions_bound(self):
        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            path, pr, merge = guard.checked(self.scope, self.request, self.read)
            self.assertTrue(merge)
            self.assertEqual(pr["node_id"], self.pr["node_id"])
            self.assertTrue(path.endswith("/6/merge"))
            for bad in ["main", "another-branch"]:
                self.pr["base"]["ref"] = bad
                with self.assertRaises(ValueError):
                    guard.checked(self.scope, self.request, self.read)

    def test_foreign_head_body_or_ci_cannot_be_merged(self):
        original = copy.deepcopy(self.pr)
        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            for field in ["head", "body", "ci"]:
                self.pr = copy.deepcopy(original)
                if field == "head":
                    self.pr["head"]["sha"] = "b" * 40
                elif field == "body":
                    self.pr["body"] = "not run-owned"
                else:
                    self.check["app"]["slug"] = "untrusted-status-app"
                with self.assertRaises(ValueError):
                    guard.checked(self.scope, self.request, self.read)

    def test_only_fixed_unmerged_ci_probe_may_be_closed(self):
        self.pr.update(node_id=self.policy["ci_probe"]["node_id"])
        self.pr["head"]["ref"] = self.policy["base_branch"]
        self.pr["base"]["ref"] = "main"
        req = {
            "method": "SERVICE_CLOSE",
            "path": "/repos/"
            + self.config["repository"]
            + "/pulls/"
            + str(self.policy["ci_probe"]["number"]),
            "payload": {"state": "closed"},
        }

        def read(path):
            return self.read(path) if "/git/ref/" in path else self.pr

        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            self.assertFalse(guard.checked(self.scope, req, read)[2])
            self.pr["node_id"] = "PR_product"
            with self.assertRaises(ValueError):
                guard.checked(self.scope, req, read)

    def test_service_graph_has_exact_scopes_and_never_selects_jira(self):
        result = graph(self.config)
        self.assertEqual([n["depends_on"] for n in result["tickets"]], [[], [], ["A", "B"]])
        self.assertEqual([n["paths"] for n in result["tickets"]], [[p] for p in paths()])
        self.assertTrue(all(n["task"]["source"] == "text" for n in result["tickets"]))
        self.assertFalse(self.config["execution_enabled"])
        self.assertFalse(self.config["broker_enabled"])
        self.assertNotEqual(
            self.config["recovery_store"]["automation_id"], "aut_3a938ace3b15451585f1ed87f166625f"
        )

    def test_diagnostic_hold_does_not_change_ordinary_checkout(self):
        config = {"repository": "owner/repo", "validation_commands": []}
        old = checkout_command(config, "a" * 40)
        self.assertNotIn("time.sleep", old)
        self.assertEqual(old, checkout_command(config, "a" * 40, hold_seconds=0))
        with self.assertRaises(PolicyError):
            checkout_command(config, "a" * 40, hold_seconds=120)
        held = checkout_command(self.config, "a" * 40, hold_seconds=120)
        self.assertIn("time.sleep(120)", held)

    def test_arbitrary_events_refuse_before_any_external_action(self):
        with tempfile.TemporaryDirectory() as directory:
            http = Mock()
            hooks = {"cloud_identity": Mock(side_effect=PolicyError("no cloud"))}
            for event in [
                {"action": "epic-service", "mode": "run", "graph": {}},
                {"action": "epic-service", "mode": "merge"},
            ]:
                with self.assertRaises(PolicyError):
                    run(event, Path(directory), self.config, {}, http, hooks)
            http.request.assert_not_called()

    def test_cancelled_service_attempt_restores_only_original_fixed_profile(self):
        from test_recovery import RecoveryTests

        f = RecoveryTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.config["epic_service_test"] = {"suite_id": self.service["suite_id"], "hold_seconds": 120}
        f.journal.connection.execute(
            "UPDATE runs SET config_digest=? WHERE id=?", (config_digest(f.config), f.root)
        )
        f.http.prior["item"]["event"]["data"] = {"action": "epic-service", "mode": "crash"}
        f.write.save({"kind": "tick", "run_id": f.root})
        f.lose_snapshot()
        receipt = f.restore()
        self.assertEqual(receipt["root"], f.root)
        self.assertEqual(receipt["external_mutations"], 0)
        self.assertEqual(f.http.posts, [])

    def test_service_history_cannot_be_skipped_by_lost_attempt(self):
        fence = runpy.run_path(str(ROOT / "scripts/bundle_controller.py"))["cloud_fence"]
        from collegium_pipeline.recovery import ExternalRecoveryRequired

        current = {
            "id": "run_now",
            "automation_id": "aut_owner",
            "status": "running",
            "item": {"event": {"data": {"action": "epic-service", "mode": "run"}}},
            "attempts": [{"id": "att_now", "n": 1, "status": "running"}],
        }
        old = {
            "id": "run_old",
            "automation_id": "aut_owner",
            "status": "cancelled",
            "item": {"event": {"data": {"action": "epic-service", "mode": "crash"}}},
            "attempts": [{"id": "att_old", "n": 1, "status": "cancelled"}],
        }
        http = Mock()
        http.request.side_effect = [(current, {}), ({"runs": [current, old]}, {}), (old, {})]
        env = {
            "LAP_AUTOMATION_ID": "aut_owner",
            "LAP_RUN_ID": "run_now",
            "LAP_ATTEMPT_ID": "att_now",
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ExternalRecoveryRequired):
                fence(
                    current["item"]["event"]["data"], Path(directory), env, http, epic_service=True
                )

    def test_matching_but_unaccepted_or_forged_pr_cannot_merge(self):
        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            for proof in ({}, {**self.request["payload"]["acceptance"], "mac": "f" * 64}):
                request = copy.deepcopy(self.request)
                request["payload"]["acceptance"] = proof
                with self.assertRaises(ValueError):
                    guard.checked(self.scope, request, self.read)

    def test_signed_ordinary_write_cannot_target_integration_or_foreign_branch(self):
        for target in (self.policy["base_branch"], "collegium/" + "2" * 36):
            payload = {
                "branch": {"branchName": target},
                "fileChanges": {
                    "additions": [
                        {
                            "path": paths()[0],
                            "contents": base64.b64encode(fixtures()["A"].encode()).decode(),
                        }
                    ],
                    "deletions": [],
                },
            }
            req = {
                "method": "GIT_COMMIT",
                "path": "/repos/" + self.config["repository"] + "/git/commit-on-branch",
                "payload": payload,
            }
            body = {
                "purpose": "rpc",
                "suite_id": self.policy["suite_id"],
                "graph_digest": self.policy["graph_digest"],
                "task_key": "A",
                "child_id": "1" * 36,
                "request_digest": digest(req),
            }
            req["authorization"] = {"body": body, "mac": mac(body, self.secret)}
            with (
                patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)),
                patch.object(guard, "ordinary_execute") as execute,
            ):
                with self.assertRaises(ValueError):
                    guard.execute(self.scope, req)
                execute.assert_not_called()

    def test_merge_push_target_is_immutable_even_if_pr_is_retargeted(self):
        import subprocess

        pr = {**self.pr, "_service_base_tip": self.policy["baseline"]}
        pr["base"] = {"ref": "main"}  # Concurrent retarget after proof cannot redirect push.
        calls = []

        def command(argv, **kwargs):
            calls.append(argv)
            out = ""
            if argv[1] == "ls-remote":
                out = self.policy["baseline"] + " refs/heads/" + self.policy["base_branch"]
            elif argv[1] == "merge-base":
                return subprocess.CompletedProcess(argv, 1, "", "")
            elif argv[1] == "rev-parse":
                out = "d" * 40
            elif argv[1] == "rev-list":
                out = "d" * 40 + " " + self.policy["baseline"] + " " + self.head
            return subprocess.CompletedProcess(argv, 0, out, "")

        with patch.object(guard.subprocess, "run", side_effect=command):
            status, result = guard.merge_isolated(
                self.scope, self.policy, pr, self.request["payload"]["acceptance"]
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["ref"], self.policy["base_branch"])
        push = next(c for c in calls if c[1] == "push")
        self.assertEqual(push[-1], "HEAD:refs/heads/" + self.policy["base_branch"])
        self.assertIn(
            "--force-with-lease=refs/heads/"
            + self.policy["base_branch"]
            + ":"
            + self.policy["baseline"],
            push,
        )

    def test_wrong_seed_fails_before_any_paid_work(self):
        engine = Mock()
        engine.config = self.config
        engine.load.return_value = {"base": None}
        engine.github_factory.return_value.ref.side_effect = [self.policy["main_sha"], "b" * 40]
        with self.assertRaisesRegex(PolicyError, "pinned seed"):
            baseline(engine, "root", self.secret)
        engine.step.assert_not_called()

    def test_running_overlap_requires_real_exact_turn_observations(self):
        workers = [
            {"session_id": "ses_a", "turn_id": "turn_a"},
            {"session_id": "ses_b", "turn_id": "turn_b"},
        ]
        a = {
            "id": "turn_a",
            "session_id": "ses_a",
            "status": "running",
            "started_at": "2026-11-28T00:00:00Z",
            "finished_at": None,
        }
        b = {**a, "id": "turn_b", "session_id": "ses_b"}
        http = Mock()
        http.request.side_effect = [(a, {}), (b, {}), (a, {})]
        self.assertEqual(observe_overlap(http, workers)["b"]["id"], "turn_b")
        http.request.side_effect = [
            (a, {}),
            (b, {}),
            ({**a, "status": "completed", "finished_at": "done"}, {}),
        ]
        with self.assertRaisesRegex(PolicyError, "running overlap"):
            observe_overlap(http, workers)

    def test_rpc_signer_requires_actual_epic_membership_and_is_replay_stable(self):
        from collegium_pipeline.domain import Task
        from collegium_pipeline.epic_service import authorize_rpc
        from collegium_pipeline.epics import Epics
        from collegium_pipeline.store import Journal

        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(Path(folder) / "journal.sqlite3")
            try:
                engine = Epics(self.config, journal, Mock(), Mock(), Path(folder) / "artifacts")
                root = engine.admit(graph(self.config))["run_id"]
                child = engine.load(root)["nodes"]["A"]["run_id"]
                request = {
                    "method": "POST",
                    "path": "/repos/owner/repo/git/refs",
                    "payload": {"ref": "refs/heads/collegium/" + child, "sha": self.head},
                }
                proof = authorize_rpc(self.config, journal, child, request)
                self.assertEqual(proof, authorize_rpc(self.config, journal, child, request))
                self.assertEqual(proof["body"]["child_id"], child)
                self.assertEqual(proof["body"]["request_digest"], digest(request))
                outside = journal.admit(
                    Task(
                        "text",
                        "unrelated",
                        self.config["repository"],
                        "Outside",
                        "No service graph",
                    ),
                    config_digest(self.config),
                )
                with self.assertRaisesRegex(PolicyError, "admitted fixed epic child"):
                    authorize_rpc(self.config, journal, outside, request)
            finally:
                journal.close()

    def test_closed_unmerged_pr_cannot_use_old_ready_receipt(self):
        self.pr["state"] = "closed"
        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            with self.assertRaisesRegex(ValueError, "Closed unmerged"):
                guard.checked(self.scope, self.request, self.read)

    def test_signed_marker_and_parents_cannot_hide_unrelated_tree_change(self):
        proof = self.request["payload"]["acceptance"]
        bad = "b" * 40
        commit = {
            "message": "Merge fixed\n\nCollegium-Service-Merge: " + json.dumps(proof),
            "parents": [{"sha": self.policy["baseline"]}, {"sha": self.head}],
            "tree": {"sha": "changed"},
        }

        def read(path):
            if path.endswith("/git/ref/heads/main"):
                return {"object": {"sha": self.policy["main_sha"]}}
            if "/git/ref/heads/" in path:
                return {"object": {"sha": bad}}
            if path.endswith("/git/commits/" + bad):
                return commit
            if path.endswith("/git/commits/" + self.policy["baseline"]):
                return {"tree": {"sha": "seed"}}
            if "/git/trees/seed?" in path:
                return {"truncated": False, "tree": []}
            if "/git/trees/changed?" in path:
                return {
                    "truncated": False,
                    "tree": [
                        {"path": "unrelated.py", "mode": "100644", "type": "blob", "sha": "f" * 40}
                    ],
                }
            raise AssertionError(path)

        with self.assertRaisesRegex(ValueError, "unrelated service tree"):
            guard.baseline(self.scope, self.policy, read)
        engine = Mock()
        engine.config = self.config
        engine.load.return_value = {
            "base": self.policy["baseline"],
            "graph_digest": self.policy["graph_digest"],
            "nodes": {"A": {"run_id": "1" * 36}},
        }
        github = engine.github_factory.return_value
        github.ref.side_effect = [self.policy["main_sha"], bad]
        github.read.side_effect = lambda p: read("/repos/" + self.config["repository"] + p)
        with self.assertRaisesRegex(PolicyError, "unrelated tree"):
            baseline(engine, "root", self.secret)

    def test_verified_seed_is_bound_through_dispatch_after_checkpoint_gap(self):
        from test_epics import EpicTests

        f = EpicTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.admit()
        prior = f.shared.refs["main"]
        changed = "c" * 40
        f.shared.commits[changed] = {
            "parents": [{"sha": prior}],
            "tree": f.shared.commits[prior]["tree"],
        }
        f.shared.refs["main"] = changed
        before = f.http.created
        with self.assertRaisesRegex(PolicyError, "after service verification"):
            f.engine.step(f.root, expected_base=prior)
        self.assertEqual(f.http.created, before)

    def test_redrafted_ready_receipt_and_idempotent_closed_ci_probe(self):
        self.pr["draft"] = True
        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            with self.assertRaisesRegex(ValueError, "draft service PR"):
                guard.checked(self.scope, self.request, self.read)
        self.pr.update(node_id=self.policy["ci_probe"]["node_id"], state="closed", draft=False)
        self.pr["head"]["ref"] = self.policy["base_branch"]
        self.pr["base"]["ref"] = "main"
        request = {
            "method": "SERVICE_CLOSE",
            "path": "/repos/"
            + self.config["repository"]
            + "/pulls/"
            + str(self.policy["ci_probe"]["number"]),
            "payload": {"state": "closed"},
        }
        with patch.object(guard.Path, "read_text", return_value=json.dumps(self.policy)):
            self.assertFalse(
                guard.checked(
                    self.scope, request, lambda p: self.read(p) if "/git/ref/" in p else self.pr
                )[2]
            )

    def test_already_merged_pr_with_missing_head_never_creates_another_push(self):
        import subprocess

        pr = {
            **self.pr,
            "state": "closed",
            "merged": True,
            "_service_base_tip": self.policy["baseline"],
        }
        calls = []

        def command(argv, **kwargs):
            calls.append(argv)
            if argv[1] == "ls-remote":
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    self.policy["baseline"] + " refs/heads/" + self.policy["base_branch"],
                    "",
                )
            return subprocess.CompletedProcess(argv, 1 if argv[1] == "merge-base" else 0, "", "")

        with patch.object(guard.subprocess, "run", side_effect=command):
            with self.assertRaisesRegex(ValueError, "never create another merge"):
                guard.merge_isolated(
                    self.scope, self.policy, pr, self.request["payload"]["acceptance"]
                )
        self.assertFalse(any(c[1] == "push" or "merge" in c[1:] for c in calls))

    def test_corrected_fixture_revision_passes_actual_ruff_gates(self):
        import subprocess

        with tempfile.TemporaryDirectory() as folder:
            for path, content in zip(paths(), fixtures(2).values(), strict=True):
                (Path(folder) / Path(path).name).write_text(content)
            for args in (["check"], ["format", "--check"]):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "ruff",
                        *args,
                        "--config",
                        str(ROOT / "pyproject.toml"),
                        folder,
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_revision_changes_identity_without_rewriting_original_acceptance(self):
        original = load_config(ROOT / "config/epic-service-v1-settings.json")
        old = graph(original)
        new = graph(self.config)
        self.assertNotEqual(old["epic"]["source_id"], new["epic"]["source_id"])
        self.assertNotEqual(digest(old), digest(new))
        self.assertTrue(all(":v2:" in n["task"]["source_id"] for n in new["tickets"]))
        self.assertNotEqual(fixtures(1)["A"], fixtures(2)["A"])

    def test_retirement_retains_unknown_claims_and_only_releases_terminal_intents(self):
        from collegium_pipeline.domain import Task
        from collegium_pipeline.epic_service import retire_legacy
        from collegium_pipeline.epics import Epics
        from collegium_pipeline.store import Journal

        legacy = load_config(ROOT / "config/epic-service-v1-settings.json")
        legacy.update(execution_enabled=True, broker_enabled=True)
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            journal = Journal(state / "journal.sqlite3")
            http = Mock()
            try:
                engine = Epics(legacy, journal, Mock(), http, state / "artifacts")
                root = engine.admit(graph(legacy))["run_id"]
                child = engine.load(root)["nodes"]["A"]["run_id"]
                worker = journal.admit(
                    Task(
                        "text",
                        child + ":0:planning:0",
                        legacy["repository"],
                        "Worker",
                        "Unknown launch",
                    ),
                    config_digest(legacy),
                    purpose="delivery_worker",
                )
                journal.begin_dispatch(worker, 0, {}, "immutable")
                result = retire_legacy(journal, legacy, http, state)
                self.assertEqual(result["state"], "retiring")
                self.assertIn(worker, result["pending"])
                self.assertFalse(engine.load(root)["fixture_retired"])
                self.assertNotEqual(engine.capacity.get(child)["state"], "released")
                http.request.assert_not_called()
                journal.connection.execute(
                    "UPDATE runs SET pending_intent=NULL,state='failed' WHERE id=?", (worker,)
                )
                self.assertEqual(retire_legacy(journal, legacy, http, state)["state"], "retired")
                self.assertTrue(engine.load(root)["fixture_retired"])
                self.assertEqual(engine.capacity.get(child)["state"], "released")
            finally:
                journal.close()

    def test_retirement_cannot_hide_an_unknown_github_action(self):
        from collegium_pipeline.epic_service import retire_legacy
        from collegium_pipeline.epics import Epics
        from collegium_pipeline.store import Journal

        legacy = load_config(ROOT / "config/epic-service-v1-settings.json")
        legacy.update(execution_enabled=True, broker_enabled=True)
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            journal = Journal(state / "journal.sqlite3")
            try:
                engine = Epics(legacy, journal, Mock(), Mock(), state / "artifacts")
                root = engine.admit(graph(legacy))["run_id"]
                child = engine.load(root)["nodes"]["A"]["run_id"]
                journal.record(child, "broker_intent", {"key": "branch", "identity": "pending"})
                result = retire_legacy(journal, legacy, Mock(), state)
                self.assertEqual(result["state"], "retiring")
                self.assertIn(child, result["pending"])
                self.assertFalse(engine.load(root)["fixture_retired"])
                journal.record(
                    child, "broker_done", {"key": "branch", "identity": "pending", "result": {}}
                )
                self.assertEqual(retire_legacy(journal, legacy, Mock(), state)["state"], "retired")
            finally:
                journal.close()

    def test_actual_signed_retire_then_revision2_admission_preserves_both_roots(self):
        from dataclasses import asdict

        from test_recovery import RecoveryTests

        from collegium_pipeline.domain import Task
        from collegium_pipeline.epic_service import legacy_roots
        from collegium_pipeline.epics import Epics
        from collegium_pipeline.platform import Collegium
        from collegium_pipeline.recovery import WriteAhead
        from collegium_pipeline.store import Journal

        f = RecoveryTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        current = copy.deepcopy(self.config)
        legacy = load_config(ROOT / "config/epic-service-v1-settings.json")
        for cfg in (current, legacy):
            cfg.update(
                project_id="project",
                repository="owner/repo",
                repository_id=123,
                workers={"executor": asdict(f.binding)},
            )
            cfg["recovery_store"]["owner"] = "aut_owner"
        admitted = {**legacy, "execution_enabled": True, "broker_enabled": True}
        identity = {**f.identity, "run_id": "run_retire", "attempt_id": "att_retire"}
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            journal = Journal(state / "journal.sqlite3")
            self.assertEqual(legacy_roots(journal, admitted), [])
            engine = Epics(admitted, journal, Mock(), f.http, state / "artifacts")
            oldroot = engine.admit(graph(admitted))["run_id"]
            child = engine.load(oldroot)["nodes"]["A"]["run_id"]
            engine.driver(child)._save(
                child,
                {"state": "planning", "cycle": 0, "head": self.policy["baseline"], "tokens": 0},
            )
            worker = journal.admit(
                Task("text", child + ":0:planning:0", "owner/repo", "Worker", "Same intent"),
                config_digest(admitted),
                purpose="delivery_worker",
            )
            Collegium(f.http).dispatch(
                journal,
                worker,
                0,
                binding=f.binding,
                selection=f.selection,
                prompt="Same intent",
                execution_enabled=True,
            )
            f.http.turns[0].update(status="completed", finished_at="2026-11-28T00:00:00Z")
            WriteAhead(admitted, journal, state / "artifacts", f.store, f.identity).save(
                {"kind": "tick", "run_id": oldroot}
            )
            journal.close()
            posts = len(f.http.posts)
            hooks = {
                "cloud_identity": lambda _: identity,
                "cloud_fence": Mock(return_value=(state / "cloud-fence.json", identity)),
                "save_receipt": runpy.run_path(str(ROOT / "scripts/bundle_controller.py"))[
                    "save_receipt"
                ],
                "reconcile_controller": Mock(),
            }
            with patch("collegium_pipeline.epic_service.Checkpoints", return_value=f.store):
                run(
                    {"action": "epic-service", "mode": "retire"},
                    state,
                    current,
                    {"PIPELINE_CONTROL_KEY": self.secret},
                    f.http,
                    hooks,
                    legacy=legacy,
                )
            self.assertEqual(f.store.get()[1]["config_digest"], config_digest(admitted))
            with (
                patch("collegium_pipeline.epic_service.Checkpoints", return_value=f.store),
                patch(
                    "collegium_pipeline.epic_service.baseline", return_value=self.policy["baseline"]
                ),
                patch.object(Epics, "step", return_value={}),
            ):
                run(
                    {"action": "epic-service", "mode": "run"},
                    state,
                    current,
                    {"PIPELINE_CONTROL_KEY": self.secret},
                    f.http,
                    hooks,
                    legacy=legacy,
                )
            self.assertEqual(len(f.http.posts), posts)
            self.assertNotEqual(f.store.get()[1]["config_digest"], config_digest(admitted))
            journal = Journal(state / "journal.sqlite3")
            try:
                rows = journal.connection.execute("SELECT run_id,document FROM epics").fetchall()
                self.assertEqual(len(rows), 2)
                old = next(json.loads(row[1]) for row in rows if row[0] == oldroot)
                self.assertTrue(old["fixture_retired"])
                self.assertEqual(old["state"], "blocked")
                self.assertIsNone(journal.get(worker)["pending_intent"])
            finally:
                journal.close()
