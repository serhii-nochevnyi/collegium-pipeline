"""The service diagnostic cannot turn an unrelated CI failure into permission to repair."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from collegium_pipeline.domain import PolicyError
from collegium_pipeline.service_test import failure_evidence


class ServiceFailureTests(unittest.TestCase):
    def setUp(self):
        self.head = "a" * 40
        self.config = {
            "repository": "owner/repo",
            "repository_id": 123,
            "service_test": {
                "check_name": "quality",
                "failure_signature": "AssertionError: red",
                "test_name": "test_service_phase",
            },
        }
        self.doc = {"head": self.head, "pr": {"number": 4}}
        self.check = {
            "id": 9,
            "name": "quality",
            "app": {"id": 15368},
            "head_sha": self.head,
            "conclusion": "failure",
            "details_url": "https://github.com/owner/repo/actions/runs/7/job/8",
        }
        self.ci = {"failures": [{"id": 9}]}
        self.job = {
            "id": 8,
            "run_id": 7,
            "head_sha": self.head,
            "conclusion": "failure",
            "name": "quality",
            "check_run_url": "https://api.github.com/repos/owner/repo/check-runs/9",
        }
        self.run = {"head_sha": self.head, "repository": {"id": 123}, "event": "pull_request"}

    def invoke(self, log="test_service_phase: AssertionError: red"):
        with (
            patch("collegium_pipeline.service_test.Github.read", side_effect=[self.job, self.run]),
            patch(
                "collegium_pipeline.service_test.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=log),
            ) as cli,
        ):
            result = failure_evidence(self.config, self.doc, [self.check], self.ci)
            self.assertEqual(
                cli.call_args.args[0], ["gh", "api", "repos/owner/repo/actions/jobs/8/logs"]
            )
            return result

    def test_matches_actual_actions_job_head_and_assertion(self):
        result = self.invoke()
        self.assertEqual((result["pr_number"], result["head"]), (4, self.head))
        self.assertEqual((result["run_id"], result["job_id"]), (7, 8))
        self.assertEqual(len(result["logs_digest"]), 64)

    def test_cloud_uses_only_native_app_reads_and_logs(self):
        app = Mock()
        app.read.side_effect = [self.job, self.run]
        app.logs.return_value = "test_service_phase: AssertionError: red"
        self.config["broker_reads"] = "native_script"
        with patch("collegium_pipeline.service_test.subprocess.run") as local:
            result = failure_evidence(self.config, self.doc, [self.check], self.ci, github=app)
        local.assert_not_called()
        app.logs.assert_called_once_with(8)
        self.assertEqual(result["head"], self.head)

    def test_other_assertion_or_wrong_job_revision_cannot_authorize_repair(self):
        with self.assertRaises(PolicyError):
            self.invoke("Some unrelated failure")
        self.job["head_sha"] = "b" * 40
        with self.assertRaises(PolicyError):
            self.invoke()

    def test_foreign_or_spoofed_check_url_rejected_without_reading_logs(self):
        for url in (
            "https://github.com/other/repo/actions/runs/7/job/8",
            "https://evil.example/actions/runs/7/job/8",
        ):
            self.check["details_url"] = url
            with patch("collegium_pipeline.service_test.Github.read") as read:
                with self.assertRaises(PolicyError):
                    failure_evidence(self.config, self.doc, [self.check], self.ci)
                read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
