import unittest
from unittest.mock import patch

import test_epics

from collegium_pipeline.domain import PolicyError
from collegium_pipeline.platform import confirmed_pending_launch
from collegium_pipeline.recovery import reconcile_existing, session_name
from collegium_pipeline.store import CheckpointError


class EpicDispatchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_epics.EpicTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def refuse_launch_effect(self, owner, kind):
        fixture = self.fixture
        jobs = []

        def refuse(operation):
            if operation["kind"] != kind:
                return
            run = fixture.journal.get(operation["run_id"])
            if run["source_id"].startswith(owner + ":"):
                jobs.append(run["id"])
                raise PolicyError("Fixture refused launch checkpoint")

        fixture.journal.before_effect = refuse
        with self.assertRaises(CheckpointError):
            fixture.engine.step(fixture.root)
        fixture.journal.before_effect = lambda _: None
        self.assertEqual(len(jobs), 1)
        return jobs[0]

    def exhaust(self, child):
        fixture = self.fixture
        driver = fixture.engine.driver(child)
        delivery = driver._load(child)
        delivery["tokens"] = fixture.config["epic"]["max_total_tokens"] + 1
        driver._save(child, delivery)

    def test_proven_unstarted_ticket_cannot_create_session_after_budget_is_exhausted(self):
        fixture = self.fixture
        fixture.admit()
        doc = fixture.engine.load(fixture.root)
        a, b = (doc["nodes"][key]["run_id"] for key in "AB")
        job = self.refuse_launch_effect(b, "session_create")
        run = fixture.journal.get(job)
        intent = run["pending_intent"]
        self.assertTrue(
            fixture.journal.effect_not_started(
                {"kind": "session_create", "run_id": job, "intent": intent}
            )
        )
        original_request = fixture.http.request

        def observe(method, path, *args, **kwargs):
            if method == "GET" and path.startswith("/session?project_id="):
                return [], {}
            return original_request(method, path, *args, **kwargs)

        with patch.object(fixture.http, "request", side_effect=observe):
            outcome = reconcile_existing(
                fixture.config, fixture.journal, fixture.http, fixture.repo(fixture.root)
            )
        self.assertTrue(outcome["workers"][0]["not_started"])
        self.assertIsNone(confirmed_pending_launch(fixture.journal, job))
        self.exhaust(a)

        before = fixture.http.created
        result = fixture.engine.step(fixture.root)
        self.assertEqual(fixture.http.created, before)
        self.assertIn("budget", result["nodes"]["B"]["reason"])
        self.assertEqual(fixture.journal.get(job)["pending_intent"], intent)

    def test_existing_integration_session_cannot_send_first_prompt_over_budget(self):
        fixture = self.fixture
        fixture.merged_all()
        job = self.refuse_launch_effect(fixture.root, "prompt")
        run = fixture.journal.get(job)
        intent = run["pending_intent"]
        events = fixture.journal.events(job)
        session = next(e["data"]["session_id"] for e in events if e["kind"] == "session_created")
        binding = next(
            e["data"]["request"]["binding"] for e in events if e["kind"] == "dispatch_request"
        )
        named = {
            "id": session,
            "name": session_name(intent),
            **{
                key: binding[key]
                for key in ("agent_id", "project_id", "runtime", "harness", "environment_id")
            },
        }
        original_request = fixture.http.request

        def observe(method, path, *args, **kwargs):
            if method == "GET":
                if path.startswith("/session?project_id="):
                    return [named], {}
                if path == "/session/" + session + "/runtime_events/list":
                    return {"data": [], "has_more": False}, {}
                if path == "/session/" + session:
                    return named, {}
            return original_request(method, path, *args, **kwargs)

        child = fixture.engine.load(fixture.root)["nodes"]["A"]["run_id"]
        self.exhaust(child)
        before = fixture.http.created
        with patch.object(fixture.http, "request", side_effect=observe) as http:
            outcome = reconcile_existing(
                fixture.config, fixture.journal, fixture.http, fixture.repo(fixture.root)
            )
            self.assertEqual(outcome["workers"], [{"session_id": session, "turn_id": None}])
            self.assertIsNone(confirmed_pending_launch(fixture.journal, job))
            result = fixture.engine.step(fixture.root)
            self.assertFalse(any(c.args[0] == "POST" for c in http.call_args_list))
        self.assertEqual(fixture.http.created, before)
        self.assertEqual(result["state"], "blocked")
        self.assertIn("budget", result["reason"])
        self.assertEqual(fixture.journal.get(job)["pending_intent"], intent)
