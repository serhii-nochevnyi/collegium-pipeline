import unittest
from dataclasses import replace

from collegium_pipeline.adapters import jira_snapshot
from collegium_pipeline.domain import (
    PolicyError,
    Revision,
    Task,
    digest,
    select_model,
    verify_selection,
)
from collegium_pipeline.quality import Review, verify_checks, verify_pr, verify_review

H, B = "a" * 40, "b" * 40
REV = Revision(123, H, B, digest("requirements"), digest("config"))


class PolicyTests(unittest.TestCase):
    def test_role_ladder_and_only_policy_escalations(self):
        self.assertEqual(select_model("executor").effort, "low")
        self.assertEqual(select_model("executor", critical=True).effort, "high")
        self.assertEqual(select_model("fixer", same_cause_failures=1).effort, "high")
        self.assertEqual(select_model("fixer", same_cause_failures=2).effort, "xhigh")
        self.assertEqual(select_model("sentinel", critical=True).effort, "medium")
        self.assertEqual(select_model("drift_checker", critical=True).effort, "low")
        self.assertEqual(select_model("researcher", very_complex=True).effort, "xhigh")
        with self.assertRaises(PolicyError):
            select_model("arbitrary_role")
        with self.assertRaises(PolicyError):
            select_model("fixer", same_cause_failures=-1)

    def test_actual_runtime_evidence_is_required(self):
        selection = select_model("executor")
        actual = {
            "model": selection.model,
            "effort": selection.effort,
            "harness": "codex",
            "session_id": "session",
            "verified_by_platform": True,
        }
        verify_selection(selection, actual)
        for field, bad in (
            ("effort", "high"),
            ("model", "other"),
            ("harness", "other"),
            ("verified_by_platform", "false"),
        ):
            with self.subTest(field=field), self.assertRaises(PolicyError):
                verify_selection(selection, {**actual, field: bad})

    def test_acceptance_identity_changes_with_requirements(self):
        task = Task("text", "task-1", "owner/repo", "Title", "Requirement")
        self.assertNotEqual(
            task.acceptance_digest, replace(task, requirements="Changed").acceptance_digest
        )
        with self.assertRaises(PolicyError):
            Task("text", "task-1", "https://evil.example/repo", "Title", "R")

    def test_jira_export_preserves_adf_and_rejects_missing_identity(self):
        issue = {
            "id": "12",
            "key": "P-12",
            "fields": {
                "summary": "Fix",
                "description": {"type": "doc", "content": [{"text": "Acceptance"}]},
            },
        }
        task = jira_snapshot(issue, "owner/repo")
        self.assertIn("Acceptance", task.requirements)
        self.assertEqual(task.source_id, "12")
        with self.assertRaises(PolicyError):
            jira_snapshot({"fields": issue["fields"]}, "owner/repo")


class QualityTests(unittest.TestCase):
    def check(self, **changes):
        return {
            "id": 1,
            "name": "test",
            "head_sha": H,
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 7},
            **changes,
        }

    def test_missing_pending_skipped_failed_and_stale_checks_reject(self):
        verify_checks([self.check()], [], head=H, required=["test"])
        for changes in (
            {"head_sha": B},
            {"status": "in_progress"},
            {"conclusion": "skipped"},
            {"conclusion": "cancelled"},
            {"conclusion": "failure"},
        ):
            with self.subTest(changes=changes), self.assertRaises(PolicyError):
                verify_checks([self.check(**changes)], [], head=H, required=["test"])
        with self.assertRaises(PolicyError):
            verify_checks([], [], head=H, required=["missing"])
        with self.assertRaises(PolicyError):
            verify_checks([], [], head=H, required=[])

    def test_latest_attempt_and_distinct_apps(self):
        old = self.check(conclusion="failure")
        latest = self.check(id=2)
        verify_checks([old, latest], [], head=H, required=["test"])
        with self.assertRaises(PolicyError):
            verify_checks(
                [latest, self.check(app={"id": 8}, conclusion="failure")],
                [],
                head=H,
                required=["test"],
            )

    def test_commit_status_has_exact_revision_and_latest_state(self):
        status = {"id": 1, "context": "legacy", "sha": H, "state": "success"}
        verify_checks([], [status], head=H, required=["legacy"])
        with self.assertRaises(PolicyError):
            verify_checks(
                [], [status, {**status, "id": 2, "state": "pending"}], head=H, required=["legacy"]
            )

    def test_review_independence_and_staleness(self):
        review = Review(REV, "reviewer", "executor", "pass", 0)
        verify_review(review, REV)
        for current in (
            replace(REV, head=B),
            replace(REV, base=H),
            replace(REV, acceptance_digest=digest("changed")),
            replace(REV, config_digest=digest("changed")),
        ):
            with self.assertRaises(PolicyError):
                verify_review(review, current)
        with self.assertRaises(PolicyError):
            verify_review(replace(review, reviewer_session="executor"), REV)
        with self.assertRaises(PolicyError):
            verify_review(replace(review, blocking_findings=1), REV)

    def test_pr_open_ready_current_and_mergeable(self):
        pr = {
            "state": "open",
            "draft": False,
            "mergeable": True,
            "head": {"sha": H},
            "base": {"sha": B, "repo": {"id": 123}},
        }
        verify_pr(pr, repository_id=123, head=H, base=B)
        for changes in (
            {"draft": True},
            {"mergeable": None},
            {"state": "closed"},
            {"head": {"sha": B}},
        ):
            with self.assertRaises(PolicyError):
                verify_pr({**pr, **changes}, repository_id=123, head=H, base=B)


if __name__ == "__main__":
    unittest.main()
