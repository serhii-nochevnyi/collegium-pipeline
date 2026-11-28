"""Configured Jira metadata and separate working scope, without selecting a real issue."""

import base64
import contextlib
import copy
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collegium_pipeline.config import load_config
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.epic_cloud import dispatch
from collegium_pipeline.jira_epics import resource_ids, result_object
from collegium_pipeline.recovery import config_digest, recovery_profiles, resolve_recovery_profile

ROOT = Path(__file__).resolve().parents[1]


class EpicMappingTests(unittest.TestCase):
    def test_installed_mapping_cloud_and_broker_checked_without_admission(self):
        from test_epic_cloud import EpicCloudTests

        f = EpicCloudTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        jira = json.loads((ROOT / "config/epic-policy.json").read_text())["epic"]["jira"]
        f.config["epic"]["jira"] = jira
        f.config["native_broker"] = {"automation_id": "aut_working", "approved_digest": "a" * 64}
        module = types.ModuleType("lap_mcp")
        module.connection = Mock()
        for cloud, succeeds in [(jira["cloud_id"], True), ("other-site", False)]:
            module.connection.return_value.call.return_value = [
                {"type": "text", "text": json.dumps({"data": {"resources": [{"cloudId": cloud}]}})}
            ]
            with (
                patch.dict(sys.modules, {"lap_mcp": module}),
                patch("collegium_pipeline.native_broker.ScriptTransport.scope") as scope,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                if succeeds:
                    dispatch(
                        {"action": "epic", "operation": "preflight"},
                        f.state,
                        f.config,
                        f.environ,
                        f.http,
                        f.hooks,
                    )
                    scope.assert_called_once()
                    result = json.loads(output.getvalue().split("COLLEGIUM_EPIC_PREFLIGHT=")[1])
                    self.assertTrue(result["working_broker_scope_verified"])
                    self.assertEqual(result["jira_mapping"], jira)
                    self.assertFalse(result["pilot_selected"])
                else:
                    with self.assertRaisesRegex(PolicyError, "not accessible"):
                        dispatch(
                            {"action": "epic", "operation": "preflight"},
                            f.state,
                            f.config,
                            f.environ,
                            f.http,
                            f.hooks,
                        )
                    scope.assert_not_called()
            f.http.request.assert_not_called()
            self.assertFalse((f.state / "journal.sqlite3").exists())

    def test_mcp_error_and_ambiguous_envelopes_are_not_valid_mapping_evidence(self):
        for value in [
            {"isError": True, "content": []},
            {"id": "1", "data": {"id": "2"}},
            {"data": "not structured"},
        ]:
            with self.assertRaises(PolicyError):
                result_object(value)
        self.assertEqual(resource_ids([{"id": "site"}]), {"site"})
        self.assertEqual(
            resource_ids({"content": [{"type": "text", "text": '[{"id":"site"}]'}]}), {"site"}
        )
        self.assertEqual(resource_ids({"data": {"resources": [{"cloudId": "site"}]}}), {"site"})

    def test_directed_link_configuration_rejects_invalid_direction(self):
        config = load_config(ROOT / "config/claude-service.json")
        policy = json.loads((ROOT / "config/epic-policy.json").read_text())
        config.update(epic=policy["epic"], scheduling=policy["scheduling"])
        config["epic"]["jira"]["dependency_links"][0]["direction"] = "both"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(PolicyError, "directions"):
                load_config(path)

    def test_frozen_trusted_profiles_keep_distinct_brokers_without_rebinding(self):
        old = load_config(ROOT / "config/claude-service.json")
        epic = copy.deepcopy(old)
        working = json.loads((ROOT / "config/epic-policy.json").read_text())["working_broker"]
        epic.update(allowed_paths=working["allowed_paths"], native_broker=working["native_broker"])
        registry = recovery_profiles(old, epic)
        self.assertEqual(resolve_recovery_profile(old, config_digest(epic), registry), epic)
        self.assertEqual(resolve_recovery_profile(epic, config_digest(old), registry), old)
        untrusted = {**epic, "allowed_paths": [".github/"]}
        with self.assertRaisesRegex(PolicyError, "different frozen"):
            resolve_recovery_profile(old, config_digest(untrusted), registry)
        foreign = {**epic, "repository": "other/repo"}
        with self.assertRaisesRegex(PolicyError, "different controller"):
            resolve_recovery_profile(old, config_digest(foreign), recovery_profiles(old, foreign))

    def test_working_remote_ceiling_allows_real_code_and_denies_protected_paths(self):
        from test_native_broker_remote import broker

        policy = json.loads((ROOT / "config/epic-policy.json").read_text())["working_broker"]
        scope = {"allowed_paths": policy["allowed_paths"]}
        for path in [
            "src/collegium_pipeline/epics.py",
            "tests/test_epics.py",
            "docs/EPICS.md",
            "README.md",
            "pyproject.toml",
            "uv.lock",
        ]:
            changes = {
                "fileChanges": {
                    "additions": [{"path": path, "contents": base64.b64encode(b"ok").decode()}],
                    "deletions": [],
                }
            }
            self.assertEqual(broker.decode_changes(scope, changes), {path: "ok"})
        for path in [
            ".github/workflows/ci.yml",
            "config/epic-policy.json",
            ".env",
            "scripts/native_github_broker.py",
            "src/../config/key",
            "/etc/passwd",
        ]:
            changes = {
                "fileChanges": {
                    "additions": [{"path": path, "contents": base64.b64encode(b"bad").decode()}],
                    "deletions": [],
                }
            }
            with self.assertRaises(ValueError):
                broker.decode_changes(scope, changes)
