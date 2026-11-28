"""Real ticket engine/native adapter fixtures; no model or external repository calls."""

import copy
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from collegium_pipeline.config import config_digest
from collegium_pipeline.domain import PolicyError, Task, digest
from collegium_pipeline.epics import Epics
from collegium_pipeline.store import Journal


class EpicTests(unittest.TestCase):
    def setUp(self):
        from test_delivery import BASE, DeliveryTests, Repository

        self.base = BASE
        self.fixture = DeliveryTests()
        self.fixture.setUp()
        self.config = copy.deepcopy(self.fixture.config)
        self.config.update(
            scheduling={"project": 2, "repository": 2, "epic": 2},
            repair_pr_mode="keep_ready",
            epic={
                "max_tickets": 100,
                "max_total_tokens": 500000,
                "integration_token_reserve": 100000,
                "jira": None,
                "scopes": {},
            },
        )
        self.journal, self.http = self.fixture.journal, self.fixture.http
        self.directory = self.fixture.path / "epic-artifacts"
        self.repos = {}
        self.shared = Repository()
        self.shared.red_commits = 0
        shared = self.shared

        class Repo(Repository):
            def __init__(self):
                super().__init__()
                self.refs, self.commits, self.trees = shared.refs, shared.commits, shared.trees
                self.writes = shared.writes
                self.ci = "success"
                self.legacy = False

            def pages(self, path, key=None):
                if key == "check_runs":
                    return self.read(path)["check_runs"]
                if "/statuses" in path:
                    return [{"id": 2, "context": "test", "state": "success"}] if self.legacy else []
                return super().pages(path)

            def read(self, path=""):
                if path.startswith("/commits/") and "/check-runs" in path:
                    if self.legacy:
                        return {"total_count": 0, "check_runs": []}
                    sha = path.split("/")[2]
                    return {
                        "total_count": 1,
                        "check_runs": [
                            {
                                "id": 1,
                                "name": "test",
                                "head_sha": sha,
                                "status": "in_progress" if self.ci == "pending" else "completed",
                                "conclusion": None if self.ci == "pending" else self.ci,
                                "app": {"id": 7},
                            }
                        ],
                    }
                return super().read(path)

        self.Repo = Repo
        self.engine = self.new_engine()

        def scoped(packet, observed):
            if packet["stage"] in {"implementing", "fixing"}:
                result = json.loads(observed["turn"]["answer"])
                path = packet["context"]["ticket_scope"]["paths"][0]
                result["payload"]["changes"] = {path: "value = 1\n"}
                observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = scoped
        self.scoped = scoped

        def task(key):
            return asdict(
                Task(
                    "jira",
                    {"EPIC": "100", "A": "101", "B": "102", "C": "103"}[key],
                    "owner/repo",
                    key,
                    "Implement " + key,
                )
            )

        self.graph = {
            "schema_version": "epic/v1",
            "version": 1,
            "strategy": "direct_to_base",
            "epic": task("EPIC"),
            "tickets": [
                {
                    "key": key,
                    "task": task(key),
                    "depends_on": [] if key != "C" else ["A", "B"],
                    "paths": ["src/" + key.lower() + ".py"],
                    "resources": [],
                }
                for key in "ABC"
            ],
        }

    def new_engine(self):
        return Epics(
            self.config, self.journal, self.repo, self.http, self.directory, clock=lambda: 100
        )

    def repo(self, root):
        if root not in self.repos:
            self.repos[root] = self.Repo()
        return self.repos[root]

    def admit(self):
        self.root = self.engine.admit(self.graph)["run_id"]
        return self.root

    def tearDown(self):
        self.fixture.journal = self.journal
        self.fixture.tearDown()

    def until(self, condition, limit=100):
        for _ in range(limit):
            result = self.engine.step(self.root)
            if condition(result):
                return result
        self.fail("Epic never reached condition: " + json.dumps(result))

    def ready_ab(self):
        return self.until(lambda r: all(r["nodes"][k]["state"] == "awaiting_merge" for k in "AB"))

    def merge(self, key):
        doc = self.engine.load(self.root)
        child = doc["nodes"][key]["run_id"]
        driver = self.engine.driver(child)
        delivery = driver._load(child)
        self.assertEqual(delivery["state"], "ready_for_acceptance")
        repo = self.repo(child)
        head = digest({"merge": child, "base": repo.refs["main"]})[:40]
        repo.commits[head] = {
            "parents": [{"sha": repo.refs["main"]}, {"sha": delivery["head"]}],
            "tree": repo.commits[delivery["head"]]["tree"],
        }
        repo.refs["main"] = head
        repo.pr.update(
            state="closed", merged=True, merged_at="2026-11-28T12:00:00Z", merge_commit_sha=head
        )
        # A merged PR retains its original head even while other ticket branches exist.
        return head

    def merged_all(self):
        self.admit()
        self.ready_ab()
        self.merge("A")
        self.merge("B")
        self.until(lambda r: r["nodes"]["C"]["state"] == "awaiting_merge")
        self.merge("C")

    def test_independent_native_turns_overlap_and_dependent_cannot_bypass_dormant_claim(self):
        def running(packet, observed):
            self.scoped(packet, observed)
            if packet["stage"] == "planning":
                observed["turn"]["status"] = "running"

        self.http.mutate = running
        self.admit()
        result = self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        self.assertEqual(
            sum(
                r["observation"]["turn"]["status"] == "running" for r in self.http.sessions.values()
            ),
            2,
        )
        child = result["nodes"]["C"]["run_id"]
        self.assertIsNone(self.engine.driver(child)._load(child))
        denied = self.engine.driver(child).step(child)
        self.assertEqual(denied["action"], "managed_by_epic")
        self.assertEqual(self.http.created, 2)

    def test_full_epic_reuses_ticket_quality_then_validates_combined_base_and_replays(self):
        self.merged_all()
        result = self.until(lambda r: r["state"] == "ready_for_acceptance")
        self.assertFalse(result["delivered"])
        self.assertEqual(result["integration_head"], self.shared.refs["main"])
        self.assertEqual(self.http.created, 17)  # five stages per ticket, two integrated gates
        self.assertNotEqual(result["validation"]["session_id"], result["review"]["session_id"])
        self.assertEqual(result["validation"]["revision"]["head"], result["integration_head"])
        self.assertEqual(result["review"]["revision"]["head"], result["integration_head"])
        writes = copy.deepcopy(self.shared.writes)
        for _ in range(3):
            self.assertEqual(self.engine.step(self.root)["state"], "ready_for_acceptance")
        self.assertEqual(self.http.created, 17)
        self.assertEqual(self.shared.writes, writes)
        self.assertEqual(sum(k == "pr" for k, _ in writes), 3)
        self.assertEqual(sum(k == "commit" for k, _ in writes), 3)

    def test_open_green_pr_is_not_a_satisfied_dependency(self):
        self.admit()
        self.ready_ab()
        before = self.http.created
        for _ in range(3):
            result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["C"]["state"], "queued")
        self.assertEqual(self.http.created, before)
        self.assertNotEqual(result["state"], "ready_for_acceptance")

    def test_overlapping_paths_resources_and_unknown_overlap_serialize(self):
        for mode in ("paths", "resources", "unknown"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                journal = Journal(Path(folder) / "db")
                engine = Epics(
                    self.config,
                    journal,
                    self.repo,
                    self.http,
                    Path(folder) / "artifacts",
                    clock=lambda: 100,
                )
                graph = copy.deepcopy(self.graph)
                if mode == "paths":
                    graph["tickets"][1]["paths"] = graph["tickets"][0]["paths"]
                elif mode == "resources":
                    for n in graph["tickets"][:2]:
                        n["resources"] = ["shared-schema"]
                else:
                    graph["tickets"][0]["resources"] = None
                before = self.http.created
                root = engine.admit(graph)["run_id"]
                result = engine.step(root)
                self.assertEqual(self.http.created - before, 1)
                self.assertIn("capacity", result["nodes"]["B"]["reason"])
                journal.close()

    def test_standalone_ticket_and_epic_share_capacity_and_canonical_identity(self):
        self.admit()
        nodes = self.engine.load(self.root)["nodes"]
        task = Task(**self.graph["tickets"][0]["task"])
        same = self.journal.admit(task, config_digest(self.config))
        self.assertEqual(same, nodes["A"]["run_id"])
        self.assertEqual(self.engine.driver(same).step(same)["action"], "managed_by_epic")
        standalone = self.journal.admit(
            Task("text", "standalone", "owner/repo", "Single", "Work"), config_digest(self.config)
        )
        self.engine.capacity.register(standalone, paths=["src/d.py"], resources=[])
        self.engine.driver(standalone).step(standalone)
        self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        active = self.journal.connection.execute(
            "SELECT count(*) FROM ticket_claims WHERE state='active'"
        ).fetchone()[0]
        self.assertEqual(active, 2)

    def test_repeated_admission_is_stable_and_ownership_conflict_rolls_back_everything(self):
        self.admit()
        self.assertEqual(self.engine.admit(self.graph)["run_id"], self.root)
        count = self.journal.connection.execute("SELECT count(*) FROM runs").fetchone()[0]
        graph = copy.deepcopy(self.graph)
        graph["epic"]["source_id"] = "200"
        with self.assertRaisesRegex(PolicyError, "already claimed"):
            self.engine.admit(graph)
        self.assertEqual(
            self.journal.connection.execute("SELECT count(*) FROM runs").fetchone()[0], count
        )
        self.assertEqual(self.http.created, 0)

    def test_restart_observes_original_running_turns_without_replacement(self):
        def running(packet, observed):
            self.scoped(packet, observed)
            observed["turn"]["status"] = "running"

        self.http.mutate = running
        self.admit()
        self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        self.journal.close()
        self.journal = Journal(self.fixture.path / "journal.sqlite3")
        self.engine = self.new_engine()
        self.assertEqual(self.engine.admit(self.graph)["run_id"], self.root)
        self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        self.assertEqual(
            sum(
                self.engine.capacity.get(n["run_id"])["state"] == "active"
                for n in self.engine.load(self.root)["nodes"].values()
            ),
            2,
        )

    def test_signed_independent_checkpoint_restores_graph_and_dormant_claims(self):
        from test_recovery import RecoveryTests

        from collegium_pipeline.recovery import WriteAhead

        recovery = RecoveryTests()
        recovery.setUp()
        try:
            config = {**self.config, "recovery_store": recovery.config["recovery_store"]}
            engine = Epics(
                config, recovery.journal, self.repo, self.http, recovery.state / "artifacts"
            )
            original = engine.admit(self.graph)
            WriteAhead(
                config,
                recovery.journal,
                recovery.state / "artifacts",
                recovery.store,
                recovery.identity,
            ).save({"kind": "tick", "run_id": original["run_id"]})
            recovery.config = config
            recovery.http.prior["item"]["event"]["data"] = {
                "action": "epic",
                "operation": "prepare",
            }
            recovery.lose_snapshot()
            recovery.restore()
            restored = Epics(
                config, recovery.journal, self.repo, self.http, recovery.state / "artifacts"
            )
            replay = restored.admit(self.graph)
            self.assertEqual(original, replay)
            self.assertEqual(
                recovery.journal.connection.execute(
                    "SELECT count(*) FROM ticket_claims WHERE state='dormant'"
                ).fetchone()[0],
                4,
            )
            self.assertEqual(self.http.created, 0)
        finally:
            recovery.tearDown()

    def test_competing_connections_cannot_exceed_capacity(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from collegium_pipeline.capacity import Capacity

        self.config["scheduling"] = {"project": 1, "repository": 1, "epic": 1}
        roots = []
        for key in ("one", "two"):
            root = self.journal.admit(
                Task("text", key, "owner/repo", key, "Acceptance"), config_digest(self.config)
            )
            self.engine.capacity.register(root, paths=["src/" + key + ".py"], resources=[])
            roots.append(root)
        barrier = Barrier(2)

        def acquire(root):
            journal = Journal(self.fixture.path / "journal.sqlite3")
            try:
                capacity = Capacity(journal, self.config)
                barrier.wait(timeout=5)
                return capacity.acquire(root)
            finally:
                journal.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(acquire, roots))
        self.assertEqual(sum(results), 1)

    def test_fifo_waiter_is_not_starved_by_newer_independent_standalone(self):
        self.config["scheduling"] = {"project": 1, "repository": 1, "epic": 1}
        roots = []
        for key in ("older", "newer"):
            root = self.journal.admit(
                Task("text", key, "owner/repo", key, "Acceptance"), config_digest(self.config)
            )
            self.engine.capacity.register(root, paths=["src/" + key + ".py"], resources=[])
            roots.append(root)
        self.assertFalse(self.engine.capacity.acquire(roots[1]))
        self.assertTrue(self.engine.capacity.acquire(roots[0]))

    def test_uncertain_child_keeps_resource_claim(self):
        self.admit()
        result = self.engine.step(self.root)
        child = result["nodes"]["A"]["run_id"]
        row = self.journal.connection.execute(
            "SELECT id,pending_intent FROM runs WHERE source_id LIKE ? "
            "AND pending_intent IS NOT NULL",
            (child + ":%",),
        ).fetchone()
        self.journal.unknown_launch(row["id"], row["pending_intent"])
        self.assertFalse(self.engine.capacity.release(child))
        self.assertEqual(self.engine.capacity.get(child)["state"], "active")

    def test_failed_child_blocks_descendant_but_sibling_finishes(self):
        def failed(packet, observed):
            self.scoped(packet, observed)
            if packet["task"]["source_id"] == "101" and packet["stage"] == "implementing":
                value = json.loads(observed["turn"]["answer"])
                value.update(verdict="fail", blocking_findings=["Cannot implement"])
                observed["turn"]["answer"] = json.dumps(value)

        self.http.mutate = failed
        self.admit()
        result = self.until(
            lambda r: (
                r["nodes"]["A"]["state"] == "failed"
                and r["nodes"]["B"]["state"] == "awaiting_merge"
            )
        )
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["C"]["state"], "blocked_dependency")
        self.assertEqual(result["state"], "blocked_children")

    def test_pause_prevents_new_ticket_admission_and_resume_retains_identity(self):
        self.admit()
        before = copy.deepcopy(self.engine.load(self.root)["nodes"])
        self.engine.pause(self.root, True)
        self.assertEqual(self.engine.step(self.root)["state"], "paused")
        self.assertEqual(self.http.created, 0)
        self.engine.pause(self.root, False)
        self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        self.assertEqual(
            {k: v["run_id"] for k, v in before.items()},
            {k: v["run_id"] for k, v in self.engine.load(self.root)["nodes"].items()},
        )

    def test_epic_budget_reserves_integration_and_active_ticket_capacity(self):
        self.config["epic"]["max_total_tokens"] = 200000
        self.admit()
        result = self.engine.step(self.root)
        self.assertEqual(self.http.created, 1)
        self.assertIn("reservation", result["nodes"]["B"]["reason"])

    def test_worker_cannot_write_outside_its_resource_claim(self):
        def outside(packet, observed):
            self.scoped(packet, observed)
            if packet["stage"] == "implementing":
                value = json.loads(observed["turn"]["answer"])
                value["payload"]["changes"] = {"src/other.py": "unexpected\n"}
                observed["turn"]["answer"] = json.dumps(value)

        self.http.mutate = outside
        self.admit()
        result = self.until(lambda r: r["nodes"]["A"]["state"] == "blocked")
        self.assertNotEqual(result["state"], "ready_for_acceptance")
        self.assertFalse(self.shared.writes)

    def test_combined_red_ci_and_changed_base_cannot_finish_epic(self):
        self.merged_all()
        self.repo(self.root).ci = "failure"
        result = self.until(lambda r: r["state"] == "blocked")
        self.assertEqual(result["integration_ci"]["state"], "red")
        self.assertFalse(result["delivered"])

    def test_graph_and_configuration_drift_are_rejected(self):
        self.admit()
        graph = copy.deepcopy(self.graph)
        graph["tickets"][0]["task"]["requirements"] = "Changed acceptance"
        with self.assertRaises(PolicyError):
            self.engine.admit(graph)
        self.config["scheduling"]["project"] = 3
        with self.assertRaises(PolicyError):
            self.engine.step(self.root)

    def test_invalid_dags_rejected_before_any_admission(self):
        mutations = [
            lambda g: g.update(tickets=[]),
            lambda g: g["tickets"][0].update(depends_on=["missing"]),
            lambda g: g["tickets"][0].update(depends_on=["C"]),
            lambda g: g["tickets"].append(copy.deepcopy(g["tickets"][0])),
            lambda g: g["tickets"][0]["task"].update(repository="other/repo"),
            lambda g: g["tickets"][0].update(paths=["../secrets"]),
            lambda g: g.update(strategy="integration_branch"),
        ]
        before = self.journal.connection.execute("SELECT count(*) FROM runs").fetchone()[0]
        for mutate in mutations:
            graph = copy.deepcopy(self.graph)
            mutate(graph)
            with self.assertRaises(PolicyError):
                self.engine.admit(graph)
        self.assertEqual(
            self.journal.connection.execute("SELECT count(*) FROM runs").fetchone()[0], before
        )

    def standalone_claim(self, key="other", paths=None):
        root = self.journal.admit(
            Task("text", key, "owner/repo", key, "Acceptance"), config_digest(self.config)
        )
        self.engine.capacity.register(root, paths=paths or ["src/"], resources=[])
        self.assertTrue(self.engine.capacity.acquire(root))
        return root

    def test_cached_prerequisites_cannot_launch_c_after_base_reset_or_via_singleton(self):
        self.admit()
        self.ready_ab()
        blocker = self.standalone_claim(paths=["src/c.py"])
        self.merge("A")
        self.merge("B")
        self.engine.step(self.root)
        for _ in range(3):
            if self.engine.load(self.root)["cursor"] == 2:
                break
            self.engine.step(self.root)
        doc = self.engine.load(self.root)
        child = doc["nodes"]["C"]["run_id"]
        self.assertEqual(self.engine.capacity.get(child)["state"], "waiting")
        before = self.http.created
        self.shared.refs["main"] = self.base
        self.engine.capacity.release(blocker)
        self.assertEqual(self.engine.driver(child).step(child)["action"], "managed_by_epic")
        self.assertFalse(self.engine.capacity.acquire(child))
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["C"]["state"], "blocked_dependency")
        self.assertIsNone(self.engine.driver(child)._load(child))
        self.assertEqual(self.http.created, before)

    def test_child_initial_base_must_equal_the_verified_prerequisite_snapshot(self):
        self.admit()
        self.ready_ab()
        self.merge("A")
        self.merge("B")
        child = self.engine.load(self.root)["nodes"]["C"]["run_id"]
        repo = self.repo(child)
        original_ref = repo.ref
        repo.ref = lambda branch: self.base if branch == "main" else original_ref(branch)
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["C"]["state"], "blocked")
        self.assertIn("prerequisite", result["nodes"]["C"]["reason"])
        self.assertEqual(self.http.created, before)

    def test_waiting_integrated_ci_is_rechecked_until_green_at_the_same_head(self):
        self.merged_all()
        self.repo(self.root).ci = "pending"
        result = self.until(lambda r: r["state"] == "waiting_integration_ci")
        before = self.http.created
        self.repo(self.root).ci = "success"
        self.assertEqual(self.engine.step(self.root)["state"], "ready_for_acceptance")
        self.assertEqual(self.http.created, before)
        self.assertEqual(result["integration_head"], self.shared.refs["main"])

    def test_legacy_commit_status_without_sha_uses_exact_head_normalization(self):
        self.merged_all()
        self.repo(self.root).legacy = True
        self.assertEqual(
            self.until(lambda r: r["state"] == "ready_for_acceptance")["integration_ci"]["state"],
            "green",
        )

    def test_pause_dormants_waiting_integrator_and_does_not_block_newer_work(self):
        self.merged_all()
        blocker = self.standalone_claim(paths=["src/d.py"])
        self.assertEqual(self.engine.step(self.root)["state"], "waiting_integration_capacity")
        self.engine.pause(self.root, True)
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "dormant")
        self.engine.capacity.release(blocker)
        newer = self.standalone_claim("newer", paths=["src/d.py"])
        self.assertEqual(self.engine.step(self.root)["state"], "paused")
        self.assertEqual(self.engine.capacity.get(newer)["state"], "active")

    def test_unstarted_integrator_refreshes_head_after_waiting_for_capacity(self):
        self.merged_all()
        blocker = self.standalone_claim(paths=["src/d.py"])
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "waiting_integration_capacity")
        self.assertIsNone(result["integration_head"])
        original, changed = self.shared.refs["main"], "9" * 40
        self.shared.commits[changed] = {
            "parents": [{"sha": original}],
            "tree": self.shared.commits[original]["tree"],
        }
        self.shared.refs["main"] = changed
        self.engine.capacity.release(blocker)
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "integrating_validating")
        self.assertEqual(result["integration_head"], changed)
        self.assertEqual(self.http.created, before + 1)

    def test_durable_ready_child_recovers_stale_active_claim_after_human_merge(self):
        self.admit()
        self.ready_ab()
        child = self.engine.load(self.root)["nodes"]["A"]["run_id"]
        # An old dispatcher could stop after the ready document, before hold_ready.
        self.journal.connection.execute(
            "UPDATE ticket_claims SET state='active' WHERE run_id=?", (child,)
        )
        self.merge("A")
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["A"]["state"], "merged")
        self.assertEqual(self.engine.driver(child)._load(child)["state"], "ready_for_acceptance")
        self.assertEqual(self.engine.capacity.get(child)["state"], "released")
        self.assertEqual(self.http.created, before)

    def test_ready_document_and_claim_hold_are_one_transaction(self):
        from unittest.mock import patch

        from collegium_pipeline.capacity import Capacity

        self.admit()
        result = self.until(lambda r: r["nodes"]["A"]["state"] == "waiting_ci")
        child = result["nodes"]["A"]["run_id"]
        before = self.engine.driver(child)._load(child)
        with patch.object(Capacity, "hold_ready", side_effect=OSError("cut")):
            with self.assertRaises(OSError):
                self.engine.step(self.root)
        self.assertEqual(self.engine.driver(child)._load(child), before)
        self.assertEqual(self.engine.capacity.get(child)["state"], "active")
        self.ready_ab()

    def test_stale_integration_drains_confirmed_finished_turn_without_accepting_it(self):
        self.merged_all()

        def running(packet, observed):
            self.scoped(packet, observed)
            if packet["job_key"].startswith("epic:"):
                observed["turn"]["status"] = "running"

        self.http.mutate = running
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "integrating_validating")
        original = self.shared.refs["main"]
        changed = "9" * 40
        self.shared.commits[changed] = {
            "parents": [{"sha": original}],
            "tree": self.shared.commits[original]["tree"],
        }
        self.shared.refs["main"] = changed
        self.assertEqual(self.engine.step(self.root)["state"], "blocked")
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "active")
        before = self.http.created
        for row in self.http.sessions.values():
            if row["packet"]["job_key"].startswith("epic:"):
                row["observation"]["turn"].update(
                    status="completed", finished_at="2026-11-28T12:00:00Z"
                )
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertIsNone(result["validation"])
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")
        self.assertEqual(self.http.created, before)
        self.assertTrue(result["settlement"]["settled"])
        self.standalone_claim("after-drain")

    def test_ready_replay_does_not_reenter_capacity_queue(self):
        self.merged_all()
        self.until(lambda r: r["state"] == "ready_for_acceptance")
        blocker = self.standalone_claim()
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "ready_for_acceptance")
        self.assertEqual(self.engine.capacity.get(blocker)["state"], "active")
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")
        self.assertEqual(self.http.created, before)

    def test_known_child_usage_overrun_refuses_new_integrator_dispatch(self):
        self.merged_all()
        child = self.engine.load(self.root)["nodes"]["C"]["run_id"]
        driver = self.engine.driver(child)
        doc = driver._load(child)
        doc["tokens"] = self.config["epic"]["max_total_tokens"] + 1
        driver._save(child, doc)
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertIn("budget", result["reason"])
        self.assertEqual(self.http.created, before)

    def test_known_integrator_usage_overrun_refuses_next_review(self):
        self.merged_all()
        result = self.until(lambda r: r["validation"] is not None)
        result["tokens"] = self.config["epic"]["integration_token_reserve"] + 1
        self.engine.save(self.root, result)
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.http.created, before)

    def test_closed_unmerged_or_replaced_pr_reports_blocked_instead_of_awaiting_merge(self):
        self.admit()
        self.ready_ab()
        child = self.engine.load(self.root)["nodes"]["A"]["run_id"]
        self.repo(child).pr["state"] = "closed"
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["A"]["state"], "blocked")
        self.assertIn("closed without merge", result["nodes"]["A"]["reason"])
        self.assertEqual(result["nodes"]["C"]["state"], "blocked_dependency")

    def test_removed_rest_merge_sha_requires_actual_merged_lifecycle_and_head_ancestry(self):
        self.admit()
        self.ready_ab()
        for key in "AB":
            self.merge(key)
            child = self.engine.load(self.root)["nodes"][key]["run_id"]
            self.repo(child).pr.pop("merge_commit_sha")
        result = self.engine.step(self.root)
        for key in "AB":
            evidence = result["nodes"][key]["merged"]
            self.assertIsNone(evidence["merge_commit"])
            self.assertEqual(evidence["ancestry_proof"], "accepted_head")
            self.assertEqual(evidence["contained_commit"], evidence["head"])
        self.assertEqual(result["nodes"]["C"]["state"], "planning")

    def test_removed_rest_merge_sha_never_accepts_uncontained_head(self):
        self.admit()
        self.ready_ab()
        child = self.engine.load(self.root)["nodes"]["A"]["run_id"]
        repo = self.repo(child)
        repo.pr.update(state="closed", merged=True, merged_at="2026-11-28T12:00:00Z")
        repo.pr.pop("merge_commit_sha", None)
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["A"]["state"], "blocked")
        self.assertEqual(result["nodes"]["C"]["state"], "blocked_dependency")

    def test_shared_resource_stays_owned_until_merge_without_consuming_active_slot(self):
        self.graph["tickets"][1]["paths"] = self.graph["tickets"][0]["paths"]
        self.admit()
        result = self.until(lambda r: r["nodes"]["A"]["state"] == "awaiting_merge")
        a = result["nodes"]["A"]["run_id"]
        b = result["nodes"]["B"]["run_id"]
        self.assertEqual(self.engine.capacity.get(a)["state"], "awaiting_merge")
        self.assertIsNone(self.engine.driver(b)._load(b))
        before = self.http.created
        self.engine.step(self.root)
        self.assertEqual(self.http.created, before)
        self.merge("A")
        self.engine.step(self.root)
        self.assertEqual(self.http.created, before + 1)

    def test_missing_integrated_ci_expires_without_holding_repository_capacity(self):
        self.merged_all()
        now = [100]
        self.engine.clock = lambda: now[0]
        self.repo(self.root).ci = "pending"
        self.until(lambda r: r["state"] == "waiting_integration_ci")
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")
        now[0] += 1000
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertIn("deadline", result["reason"])
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")

    def test_observed_ticket_overrun_allows_polling_but_no_new_sibling_stage(self):
        def overrun(packet, observed):
            self.scoped(packet, observed)
            if packet["task"]["source_id"] == "101" and packet["stage"] == "planning":
                for event in observed["events"]:
                    if event["type"] == "session.status_idle":
                        event["usage"] = {
                            "input_tokens": self.config["epic"]["max_total_tokens"] + 1
                        }

        self.http.mutate = overrun
        self.admit()
        self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        for _ in range(4):
            result = self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        self.assertEqual(result["nodes"]["B"]["state"], "blocked")
        self.assertIn("budget", result["nodes"]["B"]["reason"])

    def test_rejected_paid_checkout_is_charged_before_any_sibling_retry(self):
        def reject(packet, observed):
            self.scoped(packet, observed)
            if packet["task"]["source_id"] == "101" and packet["stage"] == "planning":
                observed["events"][3]["input"]["command"] += " && echo changed"
                observed["events"][-1]["usage"] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_input_tokens": self.config["epic"]["max_total_tokens"] + 1,
                }

        self.http.mutate = reject
        self.admit()
        self.engine.step(self.root)
        for _ in range(4):
            result = self.engine.step(self.root)
        self.assertEqual(self.http.created, 2)
        child = result["nodes"]["A"]["run_id"]
        self.assertGreater(
            self.engine.driver(child)._load(child)["tokens"],
            self.config["epic"]["max_total_tokens"],
        )
        self.assertEqual(result["nodes"]["B"]["state"], "blocked")

    def test_dependency_waiter_is_dormant_after_proof_loss_and_cannot_starve_new_work(self):
        self.admit()
        self.ready_ab()
        blocker = self.standalone_claim(paths=["src/c.py"])
        self.merge("A")
        self.merge("B")
        self.engine.step(self.root)
        child = self.engine.load(self.root)["nodes"]["C"]["run_id"]
        self.assertEqual(self.engine.capacity.get(child)["state"], "waiting")
        self.shared.refs["main"] = self.base
        self.engine.capacity.release(blocker)
        self.engine.step(self.root)
        self.assertEqual(self.engine.capacity.get(child)["state"], "dormant")
        self.standalone_claim("after-reset", paths=["src/d.py"])

    def test_budget_waiter_dormants_when_its_old_reservation_is_no_longer_affordable(self):
        self.admit()
        self.ready_ab()
        blocker = self.standalone_claim(paths=["src/c.py"])
        self.merge("A")
        self.merge("B")
        self.engine.step(self.root)
        doc = self.engine.load(self.root)
        child = doc["nodes"]["C"]["run_id"]
        a = doc["nodes"]["A"]["run_id"]
        delivery = self.engine.driver(a)._load(a)
        delivery["tokens"] = self.config["epic"]["max_total_tokens"] + 1
        self.engine.driver(a)._save(a, delivery)
        self.engine.step(self.root)
        self.assertEqual(self.engine.capacity.get(child)["state"], "dormant")
        self.engine.capacity.release(blocker)
        self.standalone_claim("after-budget", paths=["src/d.py"])

    def test_reset_during_integrated_validation_drains_and_releases_root(self):
        self.merged_all()
        self.engine.step(self.root)  # Validator is already completed remotely, not collected.
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "active")
        before = self.http.created
        self.shared.refs["main"] = self.base
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")
        self.assertIsNone(result["validation"])
        self.assertEqual(self.http.created, before)
        self.standalone_claim("after-integration-reset", paths=["src/d.py"])

    def test_rejected_integrated_checkout_and_bad_reviewer_json_settle_without_repeat(self):
        def reject(packet, observed):
            self.scoped(packet, observed)
            if packet["job_key"].startswith("epic:") and packet["stage"] == self.reject_stage:
                if self.reject_stage == "validating":
                    observed["events"][3]["input"]["command"] += " && echo changed"
                else:
                    observed["turn"]["answer"] = "{not-json"

        self.reject_stage = "validating"
        self.http.mutate = reject
        self.merged_all()
        result = self.until(lambda r: r["state"] == "blocked")
        before = self.http.created
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")
        self.assertGreater(result["tokens"], 0)
        self.assertIsNone(result["validation"])
        for _ in range(3):
            self.engine.step(self.root)
        self.assertEqual(self.http.created, before)

    def test_invalid_integrated_reviewer_json_is_drained_without_acceptance(self):
        self.merged_all()

        def malformed(packet, observed):
            self.scoped(packet, observed)
            if packet["job_key"].startswith("epic:") and packet["stage"] == "reviewing":
                observed["turn"]["answer"] = "{not-json"

        self.http.mutate = malformed
        result = self.until(lambda r: r["state"] == "blocked")
        self.assertIsNone(result["review"])
        self.assertEqual(self.engine.capacity.get(self.root)["state"], "released")

    def test_long_reachable_ancestry_continues_without_permanent_missing_proof(self):
        self.admit()
        self.ready_ab()
        blocker = self.standalone_claim(paths=["src/c.py"])
        self.merge("A")
        self.merge("B")
        self.engine.step(self.root)
        for i in range(300):
            parent = self.shared.refs["main"]
            head = digest({"forward": i})[:40]
            self.shared.commits[head] = {
                "parents": [{"sha": parent}],
                "tree": self.shared.commits[parent]["tree"],
            }
            self.shared.refs["main"] = head
        before = self.http.created
        result = self.engine.step(self.root)
        self.assertEqual(result["nodes"]["A"]["state"], "waiting_prerequisite_evidence")
        child = result["nodes"]["C"]["run_id"]
        self.assertEqual(self.engine.capacity.get(child)["state"], "dormant")
        result = self.until(lambda r: all(r["nodes"][k]["merged"] for k in "AB"), limit=20)
        self.assertEqual(self.http.created, before)
        self.engine.capacity.release(blocker)
        self.engine.step(self.root)
        self.assertEqual(self.http.created, before + 1)
        self.assertEqual(self.engine.driver(child)._load(child)["base"], self.shared.refs["main"])

    def test_broker_checkpoint_refusal_aborts_tick_and_known_noop_does_not_hold_claim(self):
        from collegium_pipeline.store import CheckpointError

        self.admit()
        self.until(lambda r: r["nodes"]["A"]["state"] == "publishing")
        child = self.engine.load(self.root)["nodes"]["A"]["run_id"]

        def refuse(operation):
            if operation["kind"] == "broker":
                raise PolicyError("checkpoint refused")

        self.journal.before_effect = refuse
        with self.assertRaises(CheckpointError):
            self.engine.step(self.root)
        self.assertFalse(self.engine.capacity.unresolved(child))
        self.assertTrue(self.engine.capacity.release(child))
        self.journal.before_effect = lambda _: None
        self.until(lambda r: r["nodes"]["A"]["state"] == "awaiting_merge")
        self.assertEqual(
            sum(k == "pr" and p["head"] == "collegium/" + child for k, p in self.shared.writes), 1
        )

    def test_scope_noop_disposition_never_hides_a_later_lost_mutation(self):
        from collegium_pipeline.broker import PRBroker
        from collegium_pipeline.transport import RemoteError

        root = self.journal.admit(
            Task("text", "broker-noop", "owner/repo", "Broker", "Acceptance"),
            config_digest(self.config),
        )
        repo = self.repo(root)
        broker = PRBroker(self.config, self.journal, repo)

        def refused():
            raise PolicyError("scope refused")

        repo.scope = refused
        with self.assertRaises(PolicyError):
            broker.branch(root, self.base)
        self.assertFalse(self.engine.capacity.unresolved(root))
        repo.scope = lambda: None
        repo.lose = "branch"
        with self.assertRaises(RemoteError):
            broker.branch(root, self.base)
        self.assertTrue(self.engine.capacity.unresolved(root))
        broker.branch(root, self.base)
        self.assertFalse(self.engine.capacity.unresolved(root))
        self.assertEqual(sum(k == "branch" for k, _ in self.shared.writes), 1)
