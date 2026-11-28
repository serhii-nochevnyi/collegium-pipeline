import copy
import json
import unittest
from unittest.mock import Mock

from collegium_pipeline.domain import PolicyError
from collegium_pipeline.jira_epics import read_graph


class JiraEpicTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "repository": "owner/repo",
            "allowed_paths": ["src/"],
            "epic": {
                "max_tickets": 100,
                "scopes": {},
                "jira": {
                    "cloud_id": "site-id",
                    "epic_type_id": "epic-type",
                    "blocks_link_type_id": "blocks",
                },
            },
        }
        self.epic = {
            "id": "100",
            "key": "P-1",
            "fields": {
                "summary": "Epic",
                "description": {"type": "doc", "content": [{"text": "Preserve ADF"}]},
                "issuetype": {"id": "epic-type"},
            },
        }
        self.a = self.issue("101", "P-2")
        self.b = self.issue("102", "P-3")
        self.b["fields"]["issuelinks"] = [{"type": {"id": "blocks"}, "inwardIssue": {"key": "P-2"}}]
        self.connection = Mock()

    def issue(self, identity, key):
        return {
            "id": identity,
            "key": key,
            "fields": {
                "summary": key,
                "description": "Acceptance",
                "parent": {"id": "100", "key": "P-1"},
                "issuelinks": [],
            },
        }

    def test_paginated_read_keeps_ids_adf_and_directed_dependencies(self):
        self.connection.call.side_effect = [
            self.epic,
            {"issues": [self.a], "isLast": False, "nextPageToken": "next"},
            {"issues": [self.b], "isLast": True},
        ]
        graph = read_graph("P-1", self.config, self.connection)
        self.assertEqual(graph["epic"]["source_id"], "100")
        self.assertEqual(
            json.loads(graph["epic"]["requirements"]), self.epic["fields"]["description"]
        )
        self.assertEqual(graph["tickets"][1]["depends_on"], ["P-2"])
        self.assertIsNone(graph["tickets"][0]["resources"])
        calls = self.connection.call.call_args_list
        self.assertEqual(calls[2].kwargs["nextPageToken"], "next")
        self.assertTrue(all(c.kwargs["cloudId"] == "site-id" for c in calls))
        self.assertTrue(
            all(
                c.kwargs["view"] == "full" and c.kwargs["responseContentFormat"] == "html"
                for c in calls
            )
        )
        self.assertEqual({c.args[0] for c in calls}, {"getJiraIssue", "searchJiraIssuesUsingJql"})

    def test_stable_immutable_epic_id_can_be_used_for_revalidation(self):
        self.connection.call.side_effect = [self.epic, {"issues": [self.a], "total": 1}]
        self.assertEqual(
            read_graph("100", self.config, self.connection)["epic"]["source_id"], "100"
        )

    def test_epic_response_with_noncanonical_id_stops_before_child_search(self):
        self.connection.call.return_value = {**self.epic, "id": "0100"}
        with self.assertRaisesRegex(PolicyError, "canonical positive decimal"):
            read_graph("P-1", self.config, self.connection)
        self.connection.call.assert_called_once()

    def test_pagination_never_silently_truncates_or_accepts_repeating_token(self):
        for pages in (
            [{"issues": [self.a], "isLast": False}],
            [
                {"issues": [self.a], "nextPageToken": "same"},
                {"issues": [], "nextPageToken": "same"},
            ],
        ):
            self.connection.call.side_effect = [self.epic, *pages]
            with self.assertRaises(PolicyError):
                read_graph("P-1", self.config, self.connection)

    def test_foreign_parent_wrong_type_external_dependency_and_missing_mapping_fail(self):
        for mode in ("parent", "type", "dependency", "mapping"):
            epic, child, config = (
                copy.deepcopy(self.epic),
                copy.deepcopy(self.a),
                copy.deepcopy(self.config),
            )
            if mode == "parent":
                child["fields"]["parent"]["id"] = "foreign"
            if mode == "type":
                epic["fields"]["issuetype"]["id"] = "task"
            if mode == "dependency":
                child["fields"]["issuelinks"] = [
                    {"type": {"id": "blocks"}, "inwardIssue": {"key": "P-999"}}
                ]
            if mode == "mapping":
                config["epic"]["jira"] = None
            self.connection.call.side_effect = [epic, {"issues": [child], "isLast": True}]
            with self.assertRaises(PolicyError):
                read_graph("P-1", config, self.connection)

    def test_untrusted_key_cannot_inject_jql(self):
        with self.assertRaises(PolicyError):
            read_graph('P-1" OR project=SECRET', self.config, self.connection)
        self.connection.call.assert_not_called()
