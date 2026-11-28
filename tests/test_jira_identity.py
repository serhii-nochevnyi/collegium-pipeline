import unittest

from collegium_pipeline.adapters import jira_snapshot
from collegium_pipeline.domain import PolicyError, Task
from collegium_pipeline.epics import task_checked


class JiraIdentityTests(unittest.TestCase):
    def manifest_task(self, identity, source="jira"):
        return {
            "source": source,
            "source_id": identity,
            "repository": "owner/repo",
            "title": "Fix",
            "requirements": "Acceptance",
        }

    def exported_task(self, identity):
        return jira_snapshot(
            {
                "id": identity,
                "key": "P-12",
                "fields": {"summary": "Fix", "description": "Acceptance"},
            },
            "owner/repo",
        )

    def test_manifest_and_jira_export_share_canonical_issue_identity(self):
        task = task_checked(self.manifest_task("12"))
        self.assertEqual(task.source_id, "12")
        self.assertEqual(task, self.exported_task("12"))

    def test_jira_issue_keys_and_numeric_aliases_are_rejected(self):
        for identity in ("P-12", " 12", "12 ", "12\n", "012", "+12", "0", "-12", "１２"):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(PolicyError, "canonical positive decimal"):
                    task_checked(self.manifest_task(identity))
                with self.assertRaisesRegex(PolicyError, "canonical positive decimal"):
                    self.exported_task(identity)

    def test_non_string_jira_ids_and_source_types_are_rejected(self):
        for identity in (12, True, 12.0, ["12"]):
            with self.subTest(identity=identity):
                with self.assertRaises(PolicyError):
                    Task(**self.manifest_task(identity))
                with self.assertRaises(PolicyError):
                    self.exported_task(identity)
        with self.assertRaises(PolicyError):
            Task(**self.manifest_task("12", source=["jira"]))

    def test_text_task_identity_remains_opaque(self):
        for identity in ("P-12", "012", "12 "):
            with self.subTest(identity=identity):
                task = task_checked(self.manifest_task(identity, "text"))
                self.assertEqual(task.source_id, identity)
