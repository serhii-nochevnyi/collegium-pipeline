"""The native broker must refuse any scope expansion before a network or Git write."""

import base64
import importlib.util
import json
import unittest
import zlib
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "native_broker", Path(__file__).resolve().parents[1] / "scripts/native_github_broker.py"
)
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)
BRANCH = "collegium/12345678-1234-1234-1234-123456789abc"
SCOPE = {"repository": "owner/repo", "base_branch": "main", "allowed_paths": ["tests/"]}


class NativeBrokerScopeTests(unittest.TestCase):
    def test_compressed_utf8_git_changes_restore_exact_original_payload(self):
        from collegium_pipeline.native_broker import encode_request

        contents = base64.b64encode(("Source with unicode: Україна\n" * 5000).encode()).decode()
        request = {
            "method": "GIT_COMMIT",
            "path": "/repos/owner/repo/git/commit-on-branch",
            "payload": {
                "fileChanges": {"additions": [{"path": "tests/test.py", "contents": contents}]}
            },
        }
        wire = encode_request(request, compress=True)
        self.assertEqual(wire["encoding"], "git-text-zlib-base64")
        self.assertEqual(broker.decode_request(wire), request)
        self.assertLess(len(json.dumps({"data": wire}).encode()), 250000)

    def test_compressed_rpc_rejects_forged_digest_trailing_data_and_expansion_bombs(self):
        request = {"method": "GET", "path": "/repos/owner/repo", "payload": None}
        raw = json.dumps(request).encode()
        wire = {
            "encoding": "zlib-base64",
            "data": base64.b64encode(zlib.compress(raw)).decode(),
            "request_digest": broker.identity(request),
        }
        self.assertEqual(broker.decode_request(wire), request)
        for changed in (
            {"request_digest": "wrong"},
            {"data": base64.b64encode(zlib.compress(raw) + b"trailing").decode()},
            {"data": base64.b64encode(zlib.compress(b"x" * 2_000_001)).decode()},
        ):
            with self.assertRaises(ValueError):
                broker.decode_request({**wire, **changed})

    def test_reads_are_repository_bound_and_never_include_credentials(self):
        broker.check_scope(SCOPE, {"method": "GET", "path": "/repos/owner/repo/pulls?state=all"})
        for path in (
            "/repos/other/repo/pulls",
            "/installation/repositories",
            "/graphql",
            "/repos/owner/repo/../../user",
            "/repos/owner/repo/%2e%2e/user",
            "/repos/owner/repo/actions/secrets",
            "/repos/owner/repoevil/pulls",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                broker.check_scope(SCOPE, {"method": "GET", "path": path})

    def test_actions_read_scope_does_not_allow_mutations_or_secrets(self):
        for path in ("/actions/jobs/12", "/actions/jobs/12/logs", "/actions/runs/13"):
            broker.check_scope(SCOPE, {"method": "GET", "path": "/repos/owner/repo" + path})
            with self.assertRaises(ValueError):
                broker.check_scope(SCOPE, {"method": "POST", "path": "/repos/owner/repo" + path})
        for path in ("/actions/secrets", "/actions/runs/13/rerun", "/actions/jobs/../logs"):
            with self.assertRaises(ValueError):
                broker.check_scope(SCOPE, {"method": "GET", "path": "/repos/owner/repo" + path})

    def test_default_branch_and_arbitrary_mutations_are_refused(self):
        for request in (
            {
                "method": "POST",
                "path": "/repos/owner/repo/git/refs",
                "payload": {"ref": "refs/heads/main", "sha": "a" * 40},
            },
            {
                "method": "PATCH",
                "path": "/repos/owner/repo/git/refs/heads/main",
                "payload": {"sha": "a" * 40},
            },
            {"method": "DELETE", "path": "/repos/owner/repo/git/refs/heads/" + BRANCH},
            {
                "method": "POST",
                "path": "/repos/owner/repo/issues",
                "payload": {"title": "unexpected"},
            },
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                broker.check_scope(SCOPE, request)

    def test_pr_requires_matching_run_marker_and_base(self):
        payload = {
            "head": BRANCH,
            "base": "main",
            "draft": False,
            "body": "<!-- collegium-run:" + BRANCH.split("/")[1] + " -->",
        }
        broker.check_scope(
            SCOPE, {"method": "POST", "path": "/repos/owner/repo/pulls", "payload": payload}
        )
        for changed in ({"base": "other"}, {"head": "main"}, {"body": "unowned"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                broker.check_scope(
                    SCOPE,
                    {
                        "method": "POST",
                        "path": "/repos/owner/repo/pulls",
                        "payload": {**payload, **changed},
                    },
                )

    def test_commit_requires_exact_parent_and_repository(self):
        payload = {
            "branch": {"repositoryNameWithOwner": "owner/repo", "branchName": BRANCH},
            "expectedHeadOid": "a" * 40,
        }
        broker.check_scope(
            SCOPE,
            {
                "method": "GIT_COMMIT",
                "path": "/repos/owner/repo/git/commit-on-branch",
                "payload": payload,
            },
        )
        for changed in (
            {"expectedHeadOid": "main"},
            {"branch": {"repositoryNameWithOwner": "other/repo", "branchName": BRANCH}},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                broker.check_scope(
                    SCOPE,
                    {
                        "method": "GIT_COMMIT",
                        "path": "/repos/owner/repo/git/commit-on-branch",
                        "payload": {**payload, **changed},
                    },
                )

    def test_changed_files_cannot_escape_scope_or_carry_binary_data(self):
        def payload(path, raw):
            return {
                "fileChanges": {
                    "additions": [{"path": path, "contents": base64.b64encode(raw).decode()}]
                }
            }

        self.assertEqual(
            broker.decode_changes(SCOPE, payload("tests/test_service.py", b"value = 1\n")),
            {"tests/test_service.py": "value = 1\n"},
        )
        for path, raw in (
            ("tests/../outside", b"a"),
            ("tests/.git/config", b"a"),
            (".github/workflows/ci.yml", b"a"),
            ("tests/binary", b"\x00"),
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                broker.decode_changes(SCOPE, payload(path, raw))
