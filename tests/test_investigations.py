"""Investigation routes, sourced contracts and authenticated worker lifecycle."""

import copy
import json
import shlex
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from test_delivery import WorkersHttp

from collegium_pipeline.domain import PolicyError, Task, digest
from collegium_pipeline.effort import CLAUDE_PROBE_COMMAND
from collegium_pipeline.investigation_policy import (
    DIMENSIONS,
    LEVELS,
    PERSPECTIVES,
    REVIEW_CHECKS,
    assessment,
    binding_key,
    route,
    variants,
)
from collegium_pipeline.investigations import Investigations, validate_synthesis
from collegium_pipeline.platform import agent_digest
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError

HEAD = "a" * 40


class ResearchHttp(WorkersHttp):
    def observation(self, session_id, row):
        observed = super().observation(session_id, row)
        agent = self.agents[row["agent_id"]]
        observed["session"].update(harness="claude-code", harness_release="claude-code-test")
        observed["events"][1]["input"]["command"] = CLAUDE_PROBE_COMMAND
        observed["events"][2]["output"] = "COLLEGIUM_RUNTIME_PROBE=" + json.dumps(
            [
                {
                    "pid": 7,
                    "harness": "claude-code",
                    "model": agent["model"],
                    "effort": agent["config"]["effort"],
                }
            ]
        )
        observed["events"][3]["input"]["command"] = shlex.split(
            observed["events"][3]["input"]["command"]
        )[2]
        for event in (observed["events"][1], observed["events"][3]):
            event["name"] = "Bash"
        for event in (observed["events"][2], observed["events"][4]):
            event["content"] = event["output"]
        observed["events"][-1]["usage"]["models"] = {"claude-" + agent["model"] + "-5-5": {}}
        return observed


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.journal = Journal(self.path / "journal.sqlite3")
        self.http = ResearchHttp()
        self.config = {
            "project_id": "project",
            "repository": "owner/repo",
            "repository_id": 123,
            "base_branch": "main",
            "execution_enabled": True,
            "broker_enabled": False,
            "model_policy": "claude",
            "model_connection_id": "mcn_private",
            "workers": {},
            "allowed_paths": ["src/"],
            "validation_commands": [["python3", "-m", "unittest"]],
            "max_total_tokens": 100000,
            "max_repair_attempts": 2,
            "max_stage_seconds": 300,
            "investigation": {
                "schema_version": "investigation-policy/v1",
                "parallelism": 2,
                "max_jobs": 16,
                "minimum_complexity": "simple",
                "source_paths": ["src/"],
            },
        }
        for selection in variants():
            key = binding_key(selection)
            agent = {
                "id": key,
                "project_id": "project",
                "model": selection.model,
                "runtime": "aranarium-aws",
                "harness": "claude-code",
                "model_connection_id": "mcn_private",
                "config": {
                    "effort": selection.effort,
                    "repositories": [{"url": "https://github.com/owner/repo", "access": "read"}],
                },
            }
            self.http.agents[key] = agent
            self.config["workers"][key] = {
                "agent_id": key,
                "project_id": "project",
                "runtime": "aranarium-aws",
                "environment_id": "base",
                "api_model": selection.model,
                "selection": asdict(selection),
                "approved_agent_digest": agent_digest(agent),
                "harness": "claude-code",
                "model_connection_id": "mcn_private",
            }
        source = {
            "head": HEAD,
            "repository_id": 123,
            "path": "src/app.py",
            "start": 1,
            "end": 2,
            "text": "value = 1\n# No external writes",
            "blob": "b" * 40,
            "sha256": "c" * 64,
        }
        self.sources = [{"id": digest(source), **source}]
        self.claim = {
            "text": "The source initializes value.",
            "citations": [
                {"source_id": self.sources[0]["id"], "start": 1, "end": 1, "quote": "value = 1"}
            ],
        }
        self.intake = {
            "task": asdict(
                Task(
                    "text",
                    "service-investigation",
                    "owner/repo",
                    "Read-only service diagnostic",
                    "Compare options and propose scoped work.",
                )
            ),
            "head": HEAD,
            "sources": [{"path": "src/app.py", "start": 1, "end": 2}],
            "risk_flags": [],
            "constraints": ["Read only"],
        }
        self.http.mutate = self.payload
        self.engine = Investigations(self.config, self.journal, self.http, self.path / "artifacts")
        self.root = self.engine.admit(self.intake, self.sources)["run_id"]

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def payload(self, packet, observed):
        result = json.loads(observed["turn"]["answer"])
        stage, context = packet["stage"], packet["context"]
        result["verdict"] = "pass"
        if stage == "assessing":
            result["payload"] = {
                "dimensions": {
                    d: {"score": 0, "evidence": copy.deepcopy(self.claim)} for d in DIMENSIONS
                },
                "confidence": 0.9,
                "rationale": "Small bounded source scope",
            }
        elif stage == "researching":
            result["payload"] = {
                "perspective": context["payload_contract"]["perspective"],
                "findings": [self.claim],
                "risks": [self.claim],
                "assumptions": [],
                "open_questions": [],
            }
        elif stage == "synthesizing":
            result["payload"] = self.synthesis()
        elif stage == "investigation_review":
            result["payload"] = {
                "subject_digest": context["synthesis_digest"],
                "research_digests": context["research_digests"],
                "checks": {k: True for k in REVIEW_CHECKS},
                "open_questions": [],
            }
        observed["turn"]["answer"] = json.dumps(result)

    def synthesis(self):
        return {
            "summary": self.claim,
            "options": [
                {"name": name, "analysis": self.claim, "tradeoffs": ["Bounded scope"]}
                for name in ("Keep", "Change")
            ],
            "recommendation": "Keep",
            "risks": [self.claim],
            "open_questions": [],
            "proposed_adr": {
                k: "Proposed bounded decision"
                for k in ("title", "context", "decision", "consequences")
            },
            "tickets": [
                {
                    "key": "A",
                    "title": "Proposed task",
                    "requirements": "Preserve behavior",
                    "acceptance": ["Configured tests pass"],
                    "depends_on": [],
                    "paths": ["src/app.py"],
                    "validation_commands": self.config["validation_commands"],
                }
            ],
        }

    def until(self, state):
        for _ in range(40):
            result = self.engine.step(self.root)
            if result["state"] == state:
                return result
            if result["state"] == "blocked":
                self.fail(str(result.get("reason")))
        self.fail("Investigation did not reach " + state)

    def test_full_flow_runtime_proofs_independence_and_replay(self):
        result = self.until("ready_for_decision")
        self.assertFalse(result["decision_approved"])
        self.assertEqual(self.http.created, 7)
        self.assertEqual(result["tokens"], 140)
        self.assertEqual(set(result["research"]), set(PERSPECTIVES))
        assessment_result = self.engine.artifacts.get(result["assessment"])
        self.assertEqual(assessment_result["complexity"], "simple")
        for identity in result["results"].values():
            proof = self.engine.artifacts.get(identity)["runtime_evidence"]
            self.assertTrue(proof["verified_by_platform"])
            self.assertEqual(proof["model_connection_id"], "mcn_private")
        self.assertEqual(self.engine.admit(self.intake, self.sources)["run_id"], self.root)
        for _ in range(2):
            self.engine.step(self.root)
        self.assertEqual(self.http.created, 7)
        self.assertEqual(self.engine.load(self.root)["tokens"], 140)

    def test_two_research_slots_and_pause_hold_original_work(self):
        self.engine.step(self.root)
        self.engine.step(self.root)
        self.engine.step(self.root)
        pending = self.journal.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE pending_intent IS NOT NULL"
        ).fetchone()[0]
        self.assertEqual(pending, 2)
        before = self.http.created
        self.engine.pause(self.root)
        self.engine.step(self.root)
        self.assertEqual(self.http.created, before)
        self.engine.pause(self.root, False)
        self.until("ready_for_decision")
        self.assertEqual(self.http.created, 7)

    def test_invalid_citation_and_forged_review_never_pass(self):
        original = self.payload

        def bad(packet, observed):
            original(packet, observed)
            result = json.loads(observed["turn"]["answer"])
            if packet["stage"] == "researching":
                result["payload"]["findings"][0]["citations"][0]["quote"] = "fabricated"
            observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = bad
        result = None
        for _ in range(10):
            result = self.engine.step(self.root)
            if result["state"] == "blocked":
                break
        self.assertEqual(result["state"], "blocked")
        self.assertIn("quote differs", result["reason"])
        self.assertFalse(result["decision_approved"])

    def test_review_binds_exact_artifacts_and_retries_synthesis(self):
        original = self.payload

        def rejected(packet, observed):
            original(packet, observed)
            if packet["stage"] == "investigation_review" and ":1:" in packet["job_key"]:
                result = json.loads(observed["turn"]["answer"])
                result["verdict"] = "fail"
                result["blocking_findings"] = ["Clarify option tradeoffs"]
                observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = rejected
        result = self.until("ready_for_decision")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.http.created, 9)
        self.assertEqual(result["tokens"], 180)

    def test_required_open_question_means_needs_input(self):
        original = self.payload

        def question(packet, observed):
            original(packet, observed)
            if packet["stage"] == "synthesizing":
                result = json.loads(observed["turn"]["answer"])
                result["payload"]["open_questions"] = [
                    {"text": "Choose consequential option", "blocking": True}
                ]
                observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = question
        self.until("needs_input")
        self.assertFalse(self.engine.load(self.root)["decision_approved"])

    def test_invalid_synthesis_is_repaired_without_weakening_commands_or_repeating_research(self):
        original = self.payload

        def rejected(packet, observed):
            original(packet, observed)
            if packet["stage"] == "synthesizing" and ":1:" in packet["job_key"]:
                result = json.loads(observed["turn"]["answer"])
                result["payload"]["tickets"][0]["validation_commands"] = [["true"]]
                observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = rejected
        result = self.until("ready_for_decision")
        self.assertEqual((result["revision"], self.http.created, result["tokens"]), (2, 8, 160))
        self.assertEqual(len(result["research"]), 4)
        self.assertEqual(len(result["rejections"]), 1)
        self.assertIn("configured commands", result["rejections"][0]["reason"])
        self.assertEqual(
            result["feedback"]["required_validation_commands"], self.config["validation_commands"]
        )

    def test_invalid_synthesis_retry_budget_retains_all_rejections_and_paid_usage(self):
        original = self.payload

        def rejected(packet, observed):
            original(packet, observed)
            if packet["stage"] == "synthesizing":
                result = json.loads(observed["turn"]["answer"])
                result["payload"]["tickets"][0]["validation_commands"] = [["true"]]
                observed["turn"]["answer"] = json.dumps(result)

        self.http.mutate = rejected
        result = self.until("blocked")
        self.assertEqual((self.http.created, result["tokens"]), (8, 160))
        self.assertEqual(len(result["rejections"]), 3)
        self.assertIsNone(result["review"])
        self.assertIn("retry limit", result["reason"])
        self.assertEqual(self.engine.step(self.root)["tokens"], 160)

    def test_ambiguous_launch_is_never_replaced(self):
        request = self.http.request

        def lost(method, path, *args, **kwargs):
            if method == "POST" and path == "/session":
                request(method, path, *args, **kwargs)
                raise RemoteError("lost create acknowledgment", unknown_outcome=True)
            return request(method, path, *args, **kwargs)

        self.http.request = lost
        with self.assertRaises(RemoteError):
            self.engine.step(self.root)
        created = self.http.created
        for _ in range(2):
            self.engine.step(self.root)
        self.assertEqual(self.http.created, created)
        self.assertTrue(
            self.journal.connection.execute(
                "SELECT pending_intent FROM runs WHERE pending_intent IS NOT NULL"
            ).fetchone()
        )

    def test_budget_and_configuration_changes_fail_closed(self):
        self.engine.step(self.root)
        self.engine.step(self.root)
        doc = self.engine.load(self.root)
        doc["tokens"] = self.config["max_total_tokens"]
        self.engine.save(self.root, doc)
        before = self.http.created
        self.assertEqual(self.engine.step(self.root)["state"], "blocked")
        self.assertEqual(self.http.created, before)
        with self.assertRaises(PolicyError):
            self.engine.admit({**self.intake, "constraints": ["changed"]}, self.sources)

    def test_policy_floors_and_routes(self):
        payload = {
            "dimensions": {d: {"score": 0, "evidence": self.claim} for d in DIMENSIONS},
            "confidence": 0.9,
            "rationale": "Small",
        }
        for flag in ("security", "data_migration"):
            self.assertEqual(
                assessment(payload, self.sources, [flag], "simple")["complexity"], "critical"
            )
        self.assertEqual(
            assessment({**payload, "confidence": 0.5}, self.sources, [], "simple")["complexity"],
            "complex",
        )
        expected = [("sonnet", "low"), ("sonnet", "high"), ("opus", "high"), ("opus", "max")]
        self.assertEqual(
            [
                (route("researching", level).model, route("researching", level).effort)
                for level in LEVELS
            ],
            expected,
        )
        self.assertEqual(route("investigation_review", "simple").model, "opus")
        self.assertEqual(route("investigation_review", "critical").effort, "max")
        for dimension, level in (
            ("security", "critical"),
            ("persistence", "critical"),
            ("contracts", "complex"),
            ("concurrency", "complex"),
            ("uncertainty", "complex"),
        ):
            risky = copy.deepcopy(payload)
            risky["dimensions"][dimension]["score"] = 2
            self.assertEqual(assessment(risky, self.sources, [], "simple")["complexity"], level)

    def test_decomposition_cycle_and_command_widening_refused(self):
        payload = self.synthesis()
        payload["tickets"][0]["depends_on"] = ["A"]
        with self.assertRaises(PolicyError):
            validate_synthesis(payload, self.sources, self.config)
        payload = self.synthesis()
        payload["tickets"][0]["validation_commands"] = [["sh", "-c", "curl evil"]]
        with self.assertRaises(PolicyError):
            validate_synthesis(payload, self.sources, self.config)

    def test_critical_floor_selects_private_opus_max_for_research_and_review(self):
        intake = copy.deepcopy(self.intake)
        intake["task"]["source_id"] = "critical-service-investigation"
        intake["risk_flags"] = ["security"]
        self.root = self.engine.admit(intake, self.sources)["run_id"]
        result = self.until("ready_for_decision")
        self.assertEqual(self.engine.artifacts.get(result["assessment"])["complexity"], "critical")
        for name, value in result["results"].items():
            proof = self.engine.artifacts.get(value)["runtime_evidence"]
            if name != "assessing":
                self.assertEqual((proof["model"], proof["effort"]), ("opus", "max"))

    def test_stale_review_digest_is_rejected(self):
        original = self.payload

        def stale(packet, observed):
            original(packet, observed)
            if packet["stage"] == "investigation_review":
                value = json.loads(observed["turn"]["answer"])
                value["payload"]["subject_digest"] = "0" * 64
                observed["turn"]["answer"] = json.dumps(value)

        self.http.mutate = stale
        for _ in range(20):
            result = self.engine.step(self.root)
            if result["state"] == "blocked":
                break
        self.assertEqual(result["state"], "blocked")
        self.assertIn("stale artifacts", result["reason"])

    def test_review_retry_limit_cannot_be_bypassed(self):
        original = self.payload

        def fail(packet, observed):
            original(packet, observed)
            if packet["stage"] == "investigation_review":
                value = json.loads(observed["turn"]["answer"])
                value.update(verdict="fail", blocking_findings=["Blocking missing evidence"])
                observed["turn"]["answer"] = json.dumps(value)

        self.http.mutate = fail
        for _ in range(35):
            result = self.engine.step(self.root)
            if result["state"] == "blocked":
                break
        self.assertEqual(result["state"], "blocked")
        self.assertIn("retry limit", result["reason"])
        self.assertEqual(self.http.created, 11)

    def test_existing_turn_can_be_collected_after_budget_but_no_new_worker_starts(self):
        self.engine.step(self.root)
        doc = self.engine.load(self.root)
        doc["tokens"] = self.config["max_total_tokens"]
        self.engine.save(self.root, doc)
        result = self.engine.step(self.root)
        self.assertIsNotNone(result["assessment"])
        self.assertEqual(result["tokens"], self.config["max_total_tokens"] + 20)
        self.assertEqual(self.engine.step(self.root)["state"], "blocked")
        self.assertEqual(self.http.created, 1)

    def test_rejected_terminal_json_is_drained_and_counted_once(self):
        def invalid(packet, observed):
            self.payload(packet, observed)
            observed["turn"]["answer"] += "\nnot JSON"

        self.http.mutate = invalid
        self.engine.step(self.root)
        result = self.engine.step(self.root)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["tokens"], 20)
        self.assertFalse(result["settlement"]["pending"])
        self.assertEqual(self.engine.step(self.root)["tokens"], 20)
        self.assertEqual(self.http.created, 1)
