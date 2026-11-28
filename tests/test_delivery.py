import base64
import copy
import json
import tempfile
import unittest
from dataclasses import asdict
from hashlib import sha1
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

from test_runner import FakeHttp

from collegium_pipeline.broker import GithubApp, changes_checked
from collegium_pipeline.ci import inspect_ci
from collegium_pipeline.config import config_digest
from collegium_pipeline.delivery import Delivery, serial_lock
from collegium_pipeline.domain import PolicyError, Task, digest, select_model
from collegium_pipeline.effort import MARKER, PROBE_COMMAND
from collegium_pipeline.platform import agent_digest
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError

BASE = "b" * 40


class Repository:
    """Stateful API contract fixture. No GitHub network or repository writes."""

    def __init__(self):
        self.refs = {"main": BASE}
        self.commits = {BASE: {"tree": {"sha": "d" * 40}, "parents": [], "message": "Base"}}
        self.trees = {
            "d" * 40: {
                "src/app.py": {
                    "path": "src/app.py",
                    "mode": "100644",
                    "type": "blob",
                    "sha": "0" * 40,
                }
            }
        }
        self.pr = None
        self.writes = []
        self.lose = None
        self.red_commits = 1
        self.ci = None

    def scope(self):
        pass

    def ref(self, branch):
        return self.refs.get(branch)

    def read(self, path=""):
        if path.startswith("/git/commits/"):
            return copy.deepcopy(self.commits[path.rsplit("/", 1)[1]])
        if path.startswith("/git/trees/"):
            oid = path.split("/git/trees/", 1)[1].split("?", 1)[0]
            return {"tree": list(self.trees[oid].values()), "truncated": False}
        if path.startswith("/pulls/"):
            p = copy.deepcopy(self.pr)
            p["head"]["sha"] = self.refs[p["head"]["ref"]]
            p["base"]["sha"] = self.refs["main"]
            return p
        return {"id": 123}

    def pages(self, path):
        return [self.read("/pulls/1")] if self.pr else []

    def mutate(self, operation, payload):
        self.writes.append((operation, copy.deepcopy(payload)))
        if operation == "branch":
            self.refs[payload["ref"].removeprefix("refs/heads/")] = payload["sha"]
        elif operation == "commit":
            branch = payload["branch"]["branchName"]
            if self.refs[branch] != payload["expectedHeadOid"]:
                raise RemoteError("Expected head changed", unknown_outcome=True)
            head = digest(payload)[:40]
            self.commits[head] = {
                "parents": [{"sha": payload["expectedHeadOid"]}],
                "tree": {"sha": "d" * 40},
                "message": payload["message"]["headline"] + "\n\n" + payload["message"]["body"],
            }
            parent = payload["expectedHeadOid"]
            tree = copy.deepcopy(self.trees[self.commits[parent]["tree"]["sha"]])
            for e in payload["fileChanges"]["additions"]:
                raw = base64.b64decode(e["contents"])
                tree[e["path"]] = {
                    "path": e["path"],
                    "mode": "100644",
                    "type": "blob",
                    "sha": sha1(
                        b"blob " + str(len(raw)).encode() + b"\x00" + raw, usedforsecurity=False
                    ).hexdigest(),
                }
            for e in payload["fileChanges"]["deletions"]:
                tree.pop(e["path"], None)
            oid = digest(tree)[:40]
            self.trees[oid] = tree
            self.commits[head]["tree"] = {"sha": oid}
            self.refs[branch] = head
        elif operation == "pr":
            self.pr = {
                **payload,
                "number": 1,
                "node_id": "PR_node",
                "html_url": "https://github.com/owner/repo/pull/1",
                "state": "open",
                "mergeable": True,
                "head": {
                    "sha": self.refs[payload["head"]],
                    "ref": payload["head"],
                    "repo": {"id": 123},
                },
                "base": {"sha": self.refs["main"], "ref": "main", "repo": {"id": 123}},
            }
        elif operation in {"draft", "ready"}:
            self.pr["draft"] = operation == "draft"
        if self.lose == operation:
            self.lose = None
            raise RemoteError("Response lost", unknown_outcome=True)
        return {}

    def pr_evidence(self, number):
        pr = self.read("/pulls/1")
        commits = len(self.commits) - 1
        state = self.ci or ("failure" if commits <= self.red_commits else "success")
        rows = (
            []
            if state == "missing"
            else [
                {
                    "id": commits,
                    "name": "test",
                    "head_sha": pr["head"]["sha"],
                    "status": "in_progress" if state == "pending" else "completed",
                    "conclusion": state,
                    "app": {"id": 7},
                    "output": {"summary": "A test assertion failed" if state == "failure" else ""},
                }
            ]
        )
        return pr, rows, []


class WorkersHttp(FakeHttp):
    def request(self, method, path, payload=None, **kwargs):
        return super().request(method, unquote(path), payload, **kwargs)

    def observation(self, session_id, row):
        p = row["packet"]
        agent = self.agents[row["agent_id"]]
        result = copy.deepcopy(p["result_schema"])
        result["verdict"] = "pass"
        if p["stage"] == "planning":
            result["payload"] = {"plan": ["Implement requirement"], "acceptance": ["Run test"]}
        if p["stage"] in {"implementing", "fixing"}:
            result["payload"] = {
                "changes": {
                    "src/app.py": "value = 1\n"
                    if p["stage"] == "implementing"
                    else f"value = {int(p['job_key'].split(':')[0]) + 1}\n"
                }
            }
        events = [
            {
                "type": "user.message",
                "traceparent": "00-trace-id-parent-01",
                "content": [{"type": "text", "text": json.dumps(p)}],
            }
        ]
        events += self.tool(
            PROBE_COMMAND,
            MARKER
            + json.dumps(
                [
                    {
                        "pid": 8,
                        "harness": "codex",
                        "model": agent["model"],
                        "effort": agent["config"]["effort"],
                    }
                ]
            ),
            "probe",
        )
        results = (
            [{"argv": ["python3", "-m", "unittest"], "exit_code": 0}]
            if p["stage"] == "validating"
            else []
        )
        events += self.tool(
            p["checkout_command"],
            "COLLEGIUM_CHECKOUT="
            + json.dumps(
                {
                    "head": p["revision"]["head"],
                    "directory": "/tmp/source",
                    "passed": True,
                    "results": results,
                }
            ),
            "checkout",
        )
        events.append(
            {"type": "session.status_idle", "usage": {"input_tokens": 10, "output_tokens": 10}}
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


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.journal = Journal(self.path / "journal.sqlite3")
        self.github = Repository()
        self.http = WorkersHttp()
        self.now = 100
        self.config = {
            "repository": "owner/repo",
            "repository_id": 123,
            "project_id": "project",
            "base_branch": "main",
            "execution_profile": "delivery",
            "execution_enabled": True,
            "broker_enabled": True,
            "allowed_paths": ["src/"],
            "validation_commands": [["python3", "-m", "unittest"]],
            "required_checks": ["test"],
            "max_repair_attempts": 3,
            "max_total_tokens": 100000,
            "workers": {},
        }
        for role, repeat in [
            ("planner", 0),
            ("plan_reviewer", 0),
            ("executor", 0),
            ("code_reviewer", 0),
            ("fixer", 0),
            ("fixer", 1),
            ("fixer", 2),
        ]:
            sel = select_model(role, same_cause_failures=repeat)
            key = role if not repeat else role + ":" + sel.effort
            agent = {
                "id": key,
                "model": "openai/" + sel.model,
                "project_id": "project",
                "runtime": "aranarium-aws",
                "config": {
                    "effort": sel.effort,
                    "repositories": [{"url": "https://github.com/owner/repo", "access": "read"}],
                },
            }
            self.http.agents[key] = agent
            self.config["workers"][key] = {
                "agent_id": key,
                "api_model": agent["model"],
                "project_id": "project",
                "runtime": "aranarium-aws",
                "environment_id": "base",
                "selection": asdict(sel),
                "approved_agent_digest": agent_digest(agent),
            }
        self.run = self.journal.admit(
            Task("text", "fixture", "owner/repo", "Fixture task", "Implement a value"),
            config_digest(self.config),
        )
        self.driver = Delivery(
            self.config,
            self.journal,
            self.github,
            self.http,
            self.path / "artifacts",
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def until(self, target, limit=100):
        for _ in range(limit):
            r = self.driver.step(self.run)
            if r["state"] == target:
                return r
        self.fail("Never reached " + target + ": " + r["state"])

    def service_profile(self):
        self.config["service_test"] = {
            "initial_changes_digest": digest({"src/app.py": "value = 1\n"}),
            "repaired_changes_digest": digest({"src/app.py": "value = 2\n"}),
            "check_name": "test",
            "failure_signature": "AssertionError",
            "test_name": "test_service",
        }
        self.config["repair_validation_commands"] = [["python3", "-m", "unittest"]]
        self.run = self.journal.admit(
            Task("text", "service", "owner/repo", "Service diagnostic", "Red then green"),
            config_digest(self.config),
        )

    @staticmethod
    def service_failure(config, doc, checks, ci, **kwargs):
        return {
            "pr_number": doc["pr"]["number"],
            "head": doc["head"],
            "run_id": 1,
            "job_id": 2,
            "check_id": 3,
            "logs_digest": digest("observed fixture log"),
        }

    def test_service_requires_real_red_receipt_before_repair_and_same_pr_green(self):
        self.service_profile()
        with patch("collegium_pipeline.delivery.failure_evidence", self.service_failure):
            result = self.until("ready_for_acceptance")
        self.assertEqual(result["repairs"], 1)
        self.assertEqual(result["service_red"]["head"], result["service_initial_head"])
        self.assertNotEqual(result["head"], result["service_initial_head"])
        self.assertEqual(result["service_red"]["pr_number"], result["pr"]["number"])

    def test_service_initial_green_blocks_instead_of_claiming_test_success(self):
        self.service_profile()
        self.github.ci = "success"
        result = self.until("blocked")
        self.assertEqual(result["repairs"], 0)
        self.assertNotIn("ci_green", result)
        self.assertEqual([op for op, _ in self.github.writes].count("commit"), 1)

    def final_review(self, *, launch):
        self.config["repair_pr_mode"] = "keep_ready"
        self.service_profile()
        with patch("collegium_pipeline.delivery.failure_evidence", self.service_failure):
            for _ in range(80):
                r = self.driver.step(self.run)
                if r["state"] == "reviewing" and r["cycle"] == 1:
                    if launch:
                        self.driver.step(self.run)
                    return
        self.fail("No repaired final review")

    def test_expired_run_can_finalize_confirmed_review_without_dispatch_or_writes(self):
        self.final_review(launch=True)
        self.now += 10000
        writes, sessions = copy.deepcopy(self.github.writes), copy.deepcopy(self.http.sessions)
        before_config = config_digest(self.config)
        original_http = self.http.request

        def read_only(method, *args, **kwargs):
            self.assertEqual(method, "GET")
            return original_http(method, *args, **kwargs)

        with patch.object(self.http, "request", side_effect=read_only):
            for _ in range(3):
                result = self.driver.finalize(self.run)
        self.assertEqual(result["state"], "ready_for_acceptance")
        self.assertTrue(result["ci_green"])
        self.assertEqual(self.github.writes, writes)
        self.assertEqual(self.http.sessions, sessions)
        self.assertEqual(config_digest(self.config), before_config)
        self.assertEqual(result["started_at"], 100)
        self.assertFalse(self.driver._evidence_only)

    def test_finalization_refuses_an_unlaunched_review_and_normal_deadline_stays_enforced(self):
        self.final_review(launch=False)
        self.now += 10000
        sessions = copy.deepcopy(self.http.sessions)
        with self.assertRaisesRegex(PolicyError, "cannot create a review"):
            self.driver.finalize(self.run)
        self.assertEqual(self.http.sessions, sessions)
        self.assertEqual(self.driver.step(self.run)["state"], "blocked")

    def test_evidence_only_guard_refuses_dispatch_and_repository_writes(self):
        from collegium_pipeline.delivery import EvidenceOnly

        with self.assertRaises(PolicyError):
            EvidenceOnly(self.http).request("POST", "/session")
        with self.assertRaises(PolicyError):
            EvidenceOnly(self.github).mutate("ready", {})

    def test_finalization_cannot_admit_another_repair_when_ci_turns_red(self):
        self.final_review(launch=True)
        self.now += 10000
        self.driver.finalize(self.run)
        self.driver.finalize(self.run)
        self.github.ci = "failure"
        sessions = copy.deepcopy(self.http.sessions)
        result = self.driver.finalize(self.run)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["repairs"], 1)
        self.assertEqual(self.http.sessions, sessions)
        self.assertIs(self.driver.github, self.github)

    def test_service_premature_green_candidate_is_rejected_before_any_write(self):
        self.service_profile()

        def mutate(packet, observed):
            if packet["stage"] == "implementing":
                result = json.loads(observed["turn"]["answer"])
                result["payload"]["changes"]["src/app.py"] = "value = 2\n"
                observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = mutate
        with self.assertRaises(PolicyError):
            self.until("ready_for_acceptance")
        self.assertFalse(self.github.writes)

    def test_service_local_failure_does_not_authorize_a_fixer(self):
        self.service_profile()
        doc = {"repairs": 0}
        self.driver._repair(self.run, doc, {"kind": "local_failure"}, "signature")
        self.assertEqual(doc["state"], "blocked")
        self.assertEqual(doc["repairs"], 0)

    def test_service_unrelated_red_ci_cannot_launch_a_fixer(self):
        self.service_profile()
        self.until("waiting_ci")
        with patch(
            "collegium_pipeline.delivery.failure_evidence",
            side_effect=PolicyError("Wrong assertion"),
        ):
            with self.assertRaises(PolicyError):
                self.driver.step(self.run)
        self.assertEqual(self.driver._load(self.run)["repairs"], 0)

    def test_red_fix_validate_review_green_and_replay(self):
        r = self.until("ready_for_acceptance")
        self.assertTrue(r["ci_green"])
        self.assertEqual(r["repairs"], 1)
        self.assertFalse(r["delivered"])
        self.assertEqual(
            [op for op, _ in self.github.writes],
            ["branch", "commit", "pr", "draft", "commit", "ready"],
        )
        self.assertNotEqual(r["candidate"]["session_id"], r["review"]["session_id"])
        self.assertEqual(r["validation"]["revision"]["head"], r["head"])
        self.assertEqual(r["review"]["revision"]["head"], r["head"])
        count = self.http.created
        writes = len(self.github.writes)
        self.driver.step(self.run)
        self.assertEqual((self.http.created, len(self.github.writes)), (count, writes))

    def test_keep_ready_mode_repairs_without_graphql_transitions(self):
        self.config["repair_pr_mode"] = "keep_ready"
        self.journal.connection.execute(
            "UPDATE runs SET config_digest=? WHERE id=?", (config_digest(self.config), self.run)
        )
        result = self.until("ready_for_acceptance")
        self.assertEqual(result["repairs"], 1)
        self.assertFalse(any(op in {"draft", "ready"} for op, _ in self.github.writes))

    def test_completed_checkout_protocol_failure_retries_without_weakening_proof(self):
        def mutate(packet, obs):
            if packet["stage"] == "planning" and packet["job_key"].endswith(":0"):
                obs["events"][3]["input"]["command"] += " && echo changed"

        self.http.mutate = mutate
        result = self.until("plan_review")
        self.assertEqual(result["protocol_failures"], 1)
        self.assertEqual(self.http.created, 2)
        self.assertEqual(self.github.writes, [])
        self.assertTrue(
            any(e["kind"] == "worker_protocol_rejected" for e in self.journal.events(self.run))
        )

    def test_checkout_protocol_retry_is_bounded(self):
        def mutate(packet, obs):
            obs["events"][3]["input"]["command"] += " && echo changed"

        self.http.mutate = mutate
        result = self.until("failed")
        self.assertEqual(result["protocol_failures"], 4)
        self.assertEqual(self.http.created, 4)
        self.assertEqual(self.github.writes, [])

    def test_worker_runtime_budget_uses_actual_turn_start_after_long_admission_wait(self):
        def mutate(packet, observed):
            observed["turn"].update(status="running", started_at="1970-01-01T00:16:40+00:00")

        self.http.mutate = mutate
        self.driver.step(self.run)
        self.now = 1001
        result = self.driver.step(self.run)
        self.assertEqual(result["state"], "planning")
        self.assertEqual(self.http.created, 1)
        child = self.journal.connection.execute(
            "SELECT id FROM runs WHERE id!=?", (self.run,)
        ).fetchone()[0]
        self.assertFalse(any(e["kind"] == "job_timeout" for e in self.journal.events(child)))

    def test_timed_out_turn_must_be_definitively_terminal_before_bounded_retry(self):
        def mutate(packet, observed):
            observed["turn"].update(status="running", started_at="1970-01-01T00:01:40+00:00")

        self.http.mutate = mutate
        self.driver.step(self.run)
        self.now = 400
        with self.assertRaisesRegex(PolicyError, "timed out"):
            self.driver.step(self.run)
        with self.assertRaisesRegex(PolicyError, "still uncertain"):
            self.driver.step(self.run)
        self.assertEqual(self.http.created, 1)
        observed = self.http.sessions["session-1"]["observation"]
        observed["turn"].update(
            status="failed", error="aborted", finished_at="1970-01-01T00:06:41+00:00"
        )
        result = self.driver.step(self.run)
        self.assertEqual(result["protocol_failures"], 1)
        self.assertEqual(result["plan_attempt"], 1)
        self.assertEqual(self.http.created, 1)
        self.http.mutate = lambda packet, observed: None
        self.until("plan_review")
        self.assertEqual(self.http.created, 2)

    def rejected_validation(self):
        self.until("validating")

        def mutate(packet, obs):
            if packet["stage"] == "validating":
                checkout = json.loads(obs["events"][4]["output"].split("=", 1)[1])
                checkout["results"][0]["exit_code"] = 1
                obs["events"][4]["output"] = "COLLEGIUM_CHECKOUT=" + json.dumps(checkout)

        self.http.mutate = mutate
        self.driver.step(self.run)
        with self.assertRaisesRegex(PolicyError, "contradicts actual"):
            self.driver.step(self.run)

    def test_explicit_validation_correction_preserves_candidate_and_failed_evidence(self):
        self.rejected_validation()
        before = self.driver._load(self.run)
        old = copy.deepcopy(self.config)
        self.config["validation_commands"] = [["python3", "-m", "unittest", "-v"]]
        result = self.driver.reconfigure_validation(self.run, old, "Correct test environment")
        self.assertEqual(result["head"], before["head"])
        self.assertEqual(result["branch"], before["branch"])
        self.assertEqual(result["plan_attempt"], 1)
        self.assertEqual(result["tokens"], before["tokens"] + 20)
        self.assertEqual(self.journal.get(self.run)["config_digest"], config_digest(self.config))
        events = self.journal.events(self.run)
        correction = next(e for e in events if e["kind"] == "delivery_validation_reconfigured")
        child = self.journal.get(correction["data"]["job"])
        self.assertEqual(child["state"], "failed")
        self.assertIsNone(child["pending_intent"])
        self.assertEqual(self.driver.artifacts.get(correction["data"]["previous_config"]), old)

        def mutate(packet, obs):
            if packet["stage"] == "validating":
                checkout = json.loads(obs["events"][4]["output"].split("=", 1)[1])
                checkout["results"][0]["argv"] = self.config["validation_commands"][0]
                obs["events"][4]["output"] = "COLLEGIUM_CHECKOUT=" + json.dumps(checkout)

        self.http.mutate = mutate
        created = self.http.created
        self.restart_controller()
        self.driver.step(self.run)
        self.assertEqual(self.http.created, created + 1)
        self.assertEqual(self.driver.step(self.run)["state"], "reviewing")
        with self.assertRaises(PolicyError):
            self.driver.reconfigure_validation(self.run, old, "Repeat must not duplicate")

    def test_validation_correction_refuses_scope_change_or_uncertain_launch(self):
        self.until("validating")
        self.driver.step(self.run)
        old = copy.deepcopy(self.config)
        self.config["validation_commands"] = [["python3", "-m", "unittest", "-v"]]
        with self.assertRaises(PolicyError):
            self.driver.reconfigure_validation(self.run, old, "Still running, no observation")
        self.config["allowed_paths"] = ["/"]
        with self.assertRaises(PolicyError):
            self.driver.reconfigure_validation(self.run, old, "Scope must stay frozen")
        self.assertEqual(self.journal.get(self.run)["config_digest"], config_digest(old))

    def test_validation_correction_cli_does_not_fall_through_to_github(self):
        from collegium_pipeline.cli import main

        self.rejected_validation()
        old = copy.deepcopy(self.config)
        self.config["validation_commands"] = [["python3", "-m", "unittest", "-v"]]
        with (
            patch("collegium_pipeline.cli.load_config", side_effect=[self.config, old]),
            patch("builtins.print"),
            patch("collegium_pipeline.cli.Github") as github,
        ):
            code = main(
                [
                    "reconfigure-validation",
                    "--config",
                    "new.json",
                    "--previous-config",
                    "old.json",
                    "--journal",
                    str(self.path / "journal.sqlite3"),
                    "--artifacts",
                    str(self.path / "artifacts"),
                    "--run-id",
                    self.run,
                    "--reason",
                    "Correct environment",
                    "--apply",
                ]
            )
        self.assertEqual(code, 0)
        github.assert_not_called()

    def restart_controller(self):
        self.journal.close()
        self.journal = Journal(self.path / "journal.sqlite3")
        self.driver = Delivery(
            self.config,
            self.journal,
            self.github,
            self.http,
            self.path / "artifacts",
            clock=lambda: self.now,
        )

    def test_github_ref_preserves_branch_path_separators(self):
        calls = []

        class Http:
            def request(self, method, path):
                calls.append((method, path))
                return {"object": {"sha": BASE}}, {}

        app = GithubApp("owner/repo", 123, Http())
        branch = "collegium/" + self.run
        self.assertEqual(app.ref(branch), BASE)
        self.assertEqual(calls, [("GET", "/repos/owner/repo/git/ref/heads/" + branch)])

    def test_lost_pr_response_reconciles_without_second_pr(self):
        self.until("opening_pr")
        self.github.lose = "pr"
        with self.assertRaises(RemoteError):
            self.driver.step(self.run)
        self.restart_controller()
        self.driver.step(self.run)
        self.assertEqual(sum(op == "pr" for op, _ in self.github.writes), 1)

    def test_lost_commit_response_reconciles_without_second_commit(self):
        self.until("publishing")
        self.github.lose = "commit"
        with self.assertRaises(RemoteError):
            self.driver.step(self.run)
        self.restart_controller()
        r = self.driver.step(self.run)
        self.assertEqual(r["state"], "validating")
        self.assertEqual(sum(op == "commit" for op, _ in self.github.writes), 1)

    def test_ambiguous_action_without_observable_effect_never_retries(self):
        broker = self.driver.broker

        def fail(op, payload):
            raise RemoteError("lost before effect", unknown_outcome=True)

        self.github.mutate = fail
        with self.assertRaises(RemoteError):
            broker.branch(self.run, BASE)
        self.restart_controller()
        broker = self.driver.broker
        with self.assertRaises(PolicyError):
            broker.branch(self.run, BASE)

    def test_pending_missing_wait_then_timeout_without_fixer(self):
        self.github.ci = "missing"
        self.until("waiting_ci")
        r = self.driver.step(self.run)
        self.assertEqual(r["repairs"], 0)
        self.now += 901
        r = self.driver.step(self.run)
        self.assertEqual(r["state"], "blocked")
        self.assertEqual(r["repairs"], 0)

    def test_skipped_ci_is_blocked_not_green(self):
        self.github.ci = "skipped"
        self.until("waiting_ci")
        self.assertEqual(self.driver.step(self.run)["state"], "blocked")

    def test_base_movement_invalidates_quality(self):
        self.until("waiting_ci")
        self.github.refs["main"] = "c" * 40
        self.assertEqual(self.driver.step(self.run)["state"], "blocked")

    def test_external_push_is_never_overwritten(self):
        r = self.until("waiting_ci")
        self.github.refs[r["branch"]] = "e" * 40
        count = len(self.github.writes)
        self.assertEqual(self.driver.step(self.run)["state"], "blocked")
        self.assertEqual(len(self.github.writes), count)

    def test_repair_limit_and_policy_effort_ladder(self):
        self.github.red_commits = 100
        r = self.until("failed")
        self.assertEqual(r["repairs"], 3)
        selected = [
            self.http.agents[s["agent_id"]]["config"]["effort"]
            for s in self.http.sessions.values()
            if s["packet"]["stage"] == "fixing"
        ]
        self.assertEqual(selected, ["low", "high", "xhigh"])
        self.assertEqual(sum(op == "pr" for op, _ in self.github.writes), 1)

    def test_unknown_effort_variant_cannot_fall_back(self):
        self.github.red_commits = 100
        # Change binding before admission, not during a run.
        self.config["workers"].pop("fixer:high")
        self.journal.connection.execute(
            "UPDATE runs SET config_digest=? WHERE id=?", (config_digest(self.config), self.run)
        )
        self.until("fixing")
        self.until("waiting_ci")
        self.until("fixing")
        with self.assertRaisesRegex(PolicyError, "not bound"):
            self.driver.step(self.run)

    def test_preexisting_branch_is_not_adopted_even_at_same_base(self):
        self.github.refs["collegium/" + self.run] = BASE
        with self.assertRaisesRegex(PolicyError, "occupied"):
            self.driver.broker.branch(self.run, BASE)
        self.assertEqual(self.github.writes, [])

    def test_direct_broker_cannot_bypass_disabled_writes(self):
        self.config["broker_enabled"] = False
        with self.assertRaisesRegex(PolicyError, "disabled"):
            self.driver.broker.branch(self.run, BASE)
        self.assertEqual(self.github.writes, [])

    def test_out_of_scope_change_refused_before_publication(self):
        with self.assertRaises(PolicyError):
            changes_checked({"../escape": "x"}, ["src/"])
        with self.assertRaises(PolicyError):
            changes_checked({".github/workflows/test.yml": "x"}, ["src/"])
        with self.assertRaises(PolicyError):
            changes_checked({"src/.git/config": "x"}, ["src/"])
        self.assertEqual(self.github.writes, [])

    def test_wrong_runtime_effort_rejected_before_candidate(self):
        def mutate(packet, obs):
            obs["events"][2]["output"] = MARKER + json.dumps(
                [{"pid": 8, "harness": "codex", "model": "openai/gpt-6.2-sol", "effort": "low"}]
            )

        self.http.mutate = mutate
        self.driver.step(self.run)
        with self.assertRaises(PolicyError):
            self.driver.step(self.run)
        self.assertEqual(self.github.writes, [])

    def test_local_coordinators_are_serialized(self):
        with serial_lock(self.path / "journal.sqlite3"):
            with self.assertRaises(PolicyError):
                with serial_lock(self.path / "journal.sqlite3"):
                    pass

    def test_disabled_profile_does_not_dispatch(self):
        self.config["broker_enabled"] = False
        with self.assertRaises(PolicyError):
            self.driver.step(self.run)
        self.assertEqual(self.http.created, 0)
        self.assertEqual(self.github.writes, [])

    def test_validation_cannot_report_pass_for_failed_command(self):
        def mutate(packet, obs):
            if packet["stage"] == "validating":
                data = {
                    "head": packet["revision"]["head"],
                    "results": [{"argv": ["python3", "-m", "unittest"], "exit_code": 1}],
                }
                obs["events"][4]["output"] = "COLLEGIUM_CHECKOUT=" + json.dumps(data)

        self.http.mutate = mutate
        self.until("validating")
        self.driver.step(self.run)
        with self.assertRaises(PolicyError):
            self.driver.step(self.run)
        self.assertIsNone(self.github.pr)

    def test_review_failure_repairs_and_revalidates_before_opening_pr(self):
        def mutate(packet, obs):
            if packet["stage"] == "reviewing" and packet["job_key"].startswith("0:"):
                result = json.loads(obs["turn"]["answer"])
                result.update(verdict="fail", blocking_findings=["Missing requirement"])
                obs["turn"]["answer"] = json.dumps(result)

        self.http.mutate = mutate
        self.github.red_commits = 0
        r = self.until("ready_for_acceptance")
        self.assertEqual(r["repairs"], 1)
        self.assertEqual(
            sum(s["packet"]["stage"] == "validating" for s in self.http.sessions.values()), 2
        )
        operations = [op for op, _ in self.github.writes]
        self.assertGreater(
            operations.index("pr"), max(i for i, op in enumerate(operations) if op == "commit")
        )

    def test_ready_replay_does_not_reuse_stale_green(self):
        r = self.until("ready_for_acceptance")
        self.github.refs[r["branch"]] = "f" * 40
        r = self.driver.step(self.run)
        self.assertEqual(r["state"], "blocked")

    def test_commit_reconciliation_verifies_contents_not_just_marker(self):
        self.until("publishing")
        self.github.lose = "commit"
        with self.assertRaises(RemoteError):
            self.driver.step(self.run)
        head = next(v for k, v in self.github.refs.items() if k != "main")
        tree = self.github.commits[head]["tree"]["sha"]
        self.github.trees[tree]["src/app.py"]["sha"] = "f" * 40
        with self.assertRaisesRegex(PolicyError, "contents differ"):
            self.driver.step(self.run)

    def test_plan_rejection_replans_with_findings(self):
        def mutate(packet, obs):
            if packet["stage"] == "plan_review" and packet["job_key"].endswith(":0"):
                result = json.loads(obs["turn"]["answer"])
                result.update(verdict="fail", blocking_findings=["Acceptance missing"])
                obs["turn"]["answer"] = json.dumps(result)

        self.http.mutate = mutate
        self.github.red_commits = 0
        r = self.until("ready_for_acceptance")
        self.assertEqual(r["plan_attempt"], 1)
        plans = [
            s["packet"] for s in self.http.sessions.values() if s["packet"]["stage"] == "planning"
        ]
        self.assertEqual(len(plans), 2)
        self.assertEqual(
            plans[1]["context"]["feedback"]["blocking_findings"], ["Acceptance missing"]
        )

    def test_different_ci_cause_resets_effort(self):
        self.github.red_commits = 100
        self.until("fixing")
        self.until("waiting_ci")
        original = self.github.pr_evidence

        def evidence(number):
            pr, checks, statuses = original(number)
            checks[0]["output"]["summary"] = "Another test failure"
            return pr, checks, statuses

        self.github.pr_evidence = evidence
        r = self.until("fixing")
        self.assertEqual(r["same_cause"], 0)

    def test_total_job_budget_prevents_another_worker(self):
        self.config["max_worker_jobs"] = 1
        self.journal.connection.execute(
            "UPDATE runs SET config_digest=? WHERE id=?", (config_digest(self.config), self.run)
        )
        self.until("plan_review")
        with self.assertRaisesRegex(PolicyError, "job budget"):
            self.driver.step(self.run)
        self.assertEqual(self.http.created, 1)

    def test_non_regular_paths_are_refused_before_commit(self):
        self.until("publishing")
        self.github.trees["d" * 40]["src/app.py"]["mode"] = "120000"
        with self.assertRaisesRegex(PolicyError, "regular"):
            self.driver.step(self.run)
        self.assertFalse(any(op == "commit" for op, _ in self.github.writes))

    def test_stop_quarantines_active_turn(self):
        self.driver.step(self.run)
        original = self.http.request

        def request(method, path, payload=None, **kwargs):
            if path.endswith("/abort"):
                return {"aborted": False}, {}
            return original(method, path, payload, **kwargs)

        self.http.request = request
        self.driver.stop(self.run, "test cancellation")
        self.assertEqual(self.driver._load(self.run)["state"], "blocked")
        child = self.journal.connection.execute(
            "SELECT id FROM runs WHERE source_id LIKE ?", (self.run + ":%",)
        ).fetchone()[0]
        self.assertEqual(self.journal.get(child)["state"], "reconciling")


class BrokerTransportTests(unittest.TestCase):
    def test_app_scope_refuses_pat_and_wide_scope(self):
        for data in (
            {},
            {"total_count": 2, "repositories": []},
            {"total_count": 1, "repositories": [{"id": 999, "full_name": "owner/repo"}]},
        ):

            class Http:
                def request(self, *args, response=data):
                    return response, {}

            with self.assertRaises(PolicyError):
                GithubApp("owner/repo", 123, Http()).scope()

    def test_commit_uses_expected_head_not_force_push(self):
        calls = []

        class Http:
            def request(self, method, path, payload=None):
                calls.append((method, path, payload))
                return {"data": {"createCommitOnBranch": {"commit": {"oid": "a" * 40}}}}, {}

        g = GithubApp("owner/repo", 123, Http())
        g.mutate(
            "commit", {"expectedHeadOid": BASE, "fileChanges": {"additions": [], "deletions": []}}
        )
        self.assertEqual(calls[0][1], "/graphql")
        self.assertEqual(calls[0][2]["variables"]["input"]["expectedHeadOid"], BASE)

    def test_partial_graphql_errors_are_ambiguous(self):
        class Http:
            def request(self, *args):
                return {"data": {"createCommitOnBranch": {}}, "errors": [{"message": "failed"}]}, {}

        with self.assertRaises(RemoteError) as caught:
            GithubApp("owner/repo", 123, Http()).mutate("commit", {})
        self.assertTrue(caught.exception.unknown_outcome)

    def test_ci_latest_and_duplicate_apps(self):
        row = {
            "name": "test",
            "id": 2,
            "head_sha": BASE,
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 1},
        }
        self.assertEqual(inspect_ci([row], [], head=BASE, required=["test"])["state"], "green")
        bad = {**row, "app": {"id": 2}, "conclusion": "failure"}
        self.assertEqual(inspect_ci([row, bad], [], head=BASE, required=["test"])["state"], "red")
        self.assertEqual(
            inspect_ci([{**row, "conclusion": "cancelled"}], [], head=BASE, required=["test"])[
                "state"
            ],
            "blocked",
        )
