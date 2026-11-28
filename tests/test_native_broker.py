import base64
import copy
import hashlib
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from test_native_broker_remote import broker as remote_broker

from collegium_pipeline.domain import PolicyError, Task, digest
from collegium_pipeline.native_broker import (
    MARKER,
    NativeGithubApp,
    ScriptTransport,
    binding_digest,
)
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError


class PlatformFixture:
    def __init__(self, config):
        self.submissions = 0
        self.reply = {"id": 123}
        self.cut = False
        self.forge = False
        self.lost = False
        self.kind = "github_app"
        self.row = {
            "project_id": "project",
            "status": "paused",
            "triggers": [],
            "target": {
                "kind": "script",
                "repositories": [
                    {
                        "type": "github_repository",
                        "url": "https://github.com/owner/repo",
                        "connection": "app",
                        "access": "contributor",
                    }
                ],
            },
        }
        self.code = {
            "current": {
                "files": {
                    "broker_scope.json": json.dumps(
                        {k: config[k] for k in ("repository", "base_branch", "allowed_paths")}
                    ),
                    "native_github_broker.py": "reviewed fixture source",
                }
            }
        }
        self.requests = {}

    def request(self, method, path, payload=None):
        if path.endswith("/code"):
            return copy.deepcopy(self.code), {}
        if path.endswith("/github-connections"):
            return {"connections": [{"id": "app", "kind": self.kind}]}, {}
        if path.endswith("/run"):
            self.submissions += 1
            self.requests[str(self.submissions)] = remote_broker.decode_request(payload["data"])
            if self.lost:
                raise RemoteError("Submission response lost", unknown_outcome=True)
            return {"run": {"id": str(self.submissions)}}, {}
        if "/runs/" in path:
            key = digest(self.requests[path.rsplit("/", 1)[1]])
            data = {
                "request_digest": "forged" if self.forge else key,
                "status": 200,
                "body": self.reply,
            }
            return {
                "status": "succeeded",
                "output_cut": self.cut,
                "output_tail": MARKER + json.dumps(data),
            }, {}
        return copy.deepcopy(self.row), {}


class NativeTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = Journal(Path(self.temp.name) / "runs.sqlite3")
        self.config = {
            "repository": "owner/repo",
            "repository_id": 123,
            "base_branch": "main",
            "allowed_paths": ["tests/"],
            "project_id": "project",
            "github_connection_id": "app",
            "execution_enabled": True,
            "broker_enabled": True,
        }
        self.platform = PlatformFixture(self.config)
        self.config["native_broker"] = {
            "automation_id": "aut_fixture",
            "approved_digest": binding_digest(self.platform.row, self.platform.code),
        }
        self.run = self.journal.admit(
            Task("text", "fixture", "owner/repo", "Service", "Scope"), digest(self.config)
        )
        self.transport = ScriptTransport(
            self.config, self.platform, self.journal, self.run, pause=lambda _: None
        )

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def test_read_uses_managed_scope_without_exporting_token(self):
        row, _ = self.transport.request("GET", "/repos/owner/repo")
        self.assertEqual(row["id"], 123)
        self.assertEqual(self.transport.scope()["credential_location"], "native_egress_proxy")
        self.assertEqual(self.platform.submissions, 1)

    def test_native_logs_verify_digest_expansion_and_no_gh_fallback(self):
        app = NativeGithubApp(self.config, self.platform, self.journal, self.run)
        raw = b"test_service_phase: AssertionError: red"
        self.platform.reply = {
            "encoding": "zlib-base64",
            "data": base64.b64encode(zlib.compress(raw)).decode(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        with patch("subprocess.run") as local:
            self.assertEqual(app.logs(12), raw.decode())
            local.assert_not_called()
        self.platform.reply["sha256"] = "0" * 64
        with self.assertRaises(PolicyError):
            app.logs(12)
        self.platform.reply["data"] = base64.b64encode(zlib.compress(b"x" * 2_000_001)).decode()
        with self.assertRaises(PolicyError):
            app.logs(12)

    def test_code_or_connection_drift_blocks_before_dispatch(self):
        self.platform.code["current"]["files"]["native_github_broker.py"] = "changed"
        with self.assertRaisesRegex(PolicyError, "changed"):
            self.transport.request("GET", "/repos/owner/repo")
        self.assertEqual(self.platform.submissions, 0)

    def test_personal_token_connection_cannot_substitute_for_app(self):
        self.platform.kind = "github_token"
        with self.assertRaisesRegex(PolicyError, "GitHub App"):
            self.transport.request("GET", "/repos/owner/repo")
        self.assertEqual(self.platform.submissions, 0)

    def test_lost_mutation_submission_never_launches_replacement(self):
        self.platform.lost = True
        with self.assertRaises(RemoteError):
            self.transport.request("POST", "/repos/owner/repo/pulls", {"head": "branch"})
        with self.assertRaisesRegex(PolicyError, "replacement"):
            self.transport.request("POST", "/repos/owner/repo/pulls", {"head": "branch"})
        self.assertEqual(self.platform.submissions, 1)

    def test_mutation_replay_observes_original_job(self):
        self.transport.request("POST", "/repos/owner/repo/pulls", {"head": "branch"})
        self.transport.request("POST", "/repos/owner/repo/pulls", {"head": "branch"})
        self.assertEqual(self.platform.submissions, 1)

    def test_forged_or_truncated_reply_is_rejected(self):
        self.platform.forge = True
        with self.assertRaises(RemoteError):
            self.transport.request("GET", "/repos/owner/repo")
        self.platform.forge = False
        self.platform.cut = True
        with self.assertRaises(RemoteError):
            self.transport.request("GET", "/repos/owner/repo")

    def test_disabled_writes_do_not_dispatch(self):
        self.config["broker_enabled"] = False
        with self.assertRaisesRegex(PolicyError, "disabled"):
            self.transport.request("POST", "/repos/owner/repo/pulls", {})
        self.assertEqual(self.platform.submissions, 0)

    def test_explicit_local_reads_never_route_mutations_to_personal_credentials(self):
        self.config["broker_reads"] = "local_gh"
        github = NativeGithubApp(self.config, self.platform, self.journal, self.run)
        with patch(
            "collegium_pipeline.native_broker.Github.read", return_value={"id": 123}
        ) as read:
            self.assertEqual(github.read()["id"], 123)
            github.mutate("branch", {"ref": "fixture", "sha": "a" * 40})
            self.assertEqual(read.call_count, 1)
        self.assertEqual(self.platform.submissions, 1)

    def test_bundle_triggers_require_explicit_opt_in_and_always_a_paused_broker(self):
        self.platform.row["triggers"] = [{"kind": "schedule", "cron": "0 0 1 1 *"}]
        self.config["native_broker"]["approved_digest"] = binding_digest(
            self.platform.row, self.platform.code
        )
        with self.assertRaises(PolicyError):
            self.transport.scope()
        self.config["broker_allow_paused_triggers"] = True
        self.transport.scope()
        self.platform.row["status"] = "active"
        self.config["native_broker"]["approved_digest"] = binding_digest(
            self.platform.row, self.platform.code
        )
        with self.assertRaises(PolicyError):
            self.transport.scope()

    def test_local_ref_absence_is_distinct_from_auth_failure_and_prefix_matches(self):
        self.config["broker_reads"] = "local_gh"
        github = NativeGithubApp(self.config, self.platform, self.journal, self.run)
        with patch("collegium_pipeline.native_broker.Github.read", return_value=[]):
            self.assertIsNone(github.ref("collegium/task"))
        with patch(
            "collegium_pipeline.native_broker.Github.read", side_effect=RuntimeError("auth")
        ):
            with self.assertRaises(RuntimeError):
                github.ref("collegium/task")
        rows = [
            {
                "ref": "refs/heads/collegium/task-other",
                "object": {"type": "commit", "sha": "a" * 40},
            }
        ]
        with patch("collegium_pipeline.native_broker.Github.read", return_value=rows):
            self.assertIsNone(github.ref("collegium/task"))

    def test_large_rpc_requires_pinned_compression_and_preserves_request_identity(self):
        payload = {"contents": "reviewed source\n" * 20000}
        with self.assertRaises(PolicyError):
            self.transport.request("GIT_COMMIT", "/repos/owner/repo/git/commit-on-branch", payload)
        self.assertEqual(self.platform.submissions, 0)
        self.config["broker_compress_requests"] = True
        result, _ = self.transport.request(
            "GIT_COMMIT", "/repos/owner/repo/git/commit-on-branch", payload
        )
        self.assertEqual(result["id"], 123)
        self.assertEqual(self.platform.requests["1"]["payload"], payload)
