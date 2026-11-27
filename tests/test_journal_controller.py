import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from collegium_pipeline.controller import accept_stage
from collegium_pipeline.domain import PolicyError, Revision, Task, digest, select_model
from collegium_pipeline.quality import Review
from collegium_pipeline.store import STAGES, Journal


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "runs.sqlite3"
        self.journal = Journal(self.path)
        self.task = Task("text", "task-1", "owner/repo", "Title", "Acceptance")
        self.config = digest("config")
        self.run = self.journal.admit(self.task, self.config)

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def test_duplicate_admission_and_changed_scope(self):
        other = Journal(self.path)
        try:
            self.assertEqual(other.admit(self.task, self.config), self.run)
            with self.assertRaises(PolicyError):
                other.admit(replace(self.task, requirements="Changed"), self.config)
        finally:
            other.close()

    def test_claimed_dispatch_cannot_be_started_twice(self):
        intent = self.journal.begin_dispatch(self.run, 0, asdict(select_model("planner")))
        with self.assertRaises(PolicyError):
            self.journal.begin_dispatch(self.run, 0, asdict(select_model("planner")))
        self.journal.record_launch(self.run, intent, "session", "turn")
        with self.assertRaises(PolicyError):
            self.journal.record_launch(self.run, intent, "other", "other")

    def test_unknown_launch_survives_restart_and_cannot_relaunch(self):
        intent = self.journal.begin_dispatch(self.run, 0, asdict(select_model("planner")))
        self.journal.unknown_launch(self.run, intent)
        self.journal.close()
        self.journal = Journal(self.path)
        self.assertEqual(self.journal.get(self.run)["state"], "reconciling")
        with self.assertRaises(PolicyError):
            self.journal.begin_dispatch(self.run, 2, asdict(select_model("planner")))
        self.assertEqual(self.journal.admit(self.task, self.config), self.run)

    def test_no_launch_or_stale_version_cannot_advance(self):
        with self.assertRaises(PolicyError):
            self.journal.advance(self.run, 0, {})
        with self.assertRaises(PolicyError):
            self.journal.advance(self.run, 99, {})

    def test_text_task_through_all_gates_with_adapter_fixtures(self):
        """Domain integration proof only: these fixtures do not represent live agents."""
        revision = Revision(123, "a" * 40, "b" * 40, self.task.acceptance_digest, self.config)
        sessions = {}
        roles = ("planner", "plan_reviewer", "executor", "executor", "code_reviewer", "sentinel")
        for stage, role in zip(STAGES, roles, strict=True):
            run = self.journal.get(self.run)
            selection = select_model(role)
            intent = self.journal.begin_dispatch(self.run, run["version"], asdict(selection))
            session = "session-" + stage
            sessions[stage] = session
            self.journal.record_launch(self.run, intent, session, "turn-" + stage)
            result = {
                "verdict": "pass",
                "revision": asdict(revision),
                "artifact_digest": digest(stage),
            }
            evidence = {
                "model": selection.model,
                "effort": selection.effort,
                "harness": "codex",
                "verified_by_platform": True,
                "session_id": session,
            }
            kwargs = {}
            if stage in {"plan_review", "reviewing"}:
                subject = sessions["planning" if stage == "plan_review" else "implementing"]
                kwargs["review"] = Review(revision, session, subject, "pass", 0)
            if stage == "validating":
                result["commands"] = [{"command": "project-check", "exit_code": 0}]
            if stage == "waiting_ci":
                kwargs.update(
                    pr={
                        "state": "open",
                        "draft": False,
                        "mergeable": True,
                        "head": {"sha": revision.head},
                        "base": {"sha": revision.base, "repo": {"id": 123}},
                    },
                    checks=[
                        {
                            "id": 1,
                            "name": "test",
                            "head_sha": revision.head,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ],
                    required_checks=["test"],
                )
            accept_stage(
                self.journal,
                self.run,
                version=self.journal.get(self.run)["version"],
                current=revision,
                selection=selection,
                actual_selection=evidence,
                result=result,
                **kwargs,
            )
        self.assertEqual(self.journal.get(self.run)["state"], "ready_for_acceptance")
        self.assertEqual(self.journal.admit(self.task, self.config), self.run)
        self.assertEqual(
            len([e for e in self.journal.events(self.run) if e["kind"] == "stage_accepted"]), 6
        )

    def test_worker_result_cannot_be_replayed_for_unrecorded_session(self):
        selection = select_model("planner")
        intent = self.journal.begin_dispatch(self.run, 0, asdict(selection))
        self.journal.record_launch(self.run, intent, "real", "turn")
        revision = Revision(123, "a" * 40, "b" * 40, self.task.acceptance_digest, self.config)
        with self.assertRaises(PolicyError):
            accept_stage(
                self.journal,
                self.run,
                version=1,
                current=revision,
                selection=selection,
                actual_selection={
                    "model": selection.model,
                    "effort": selection.effort,
                    "harness": "codex",
                    "verified_by_platform": True,
                    "session_id": "forged",
                },
                result={
                    "verdict": "pass",
                    "revision": asdict(revision),
                    "artifact_digest": digest("artifact"),
                },
            )
        self.assertEqual(self.journal.get(self.run)["state"], "planning")
