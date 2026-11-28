"""Real temporary Git objects prove captured excerpts and path/mode boundaries."""

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from collegium_pipeline.domain import PolicyError
from collegium_pipeline.investigation_policy import cited
from collegium_pipeline.investigation_sources import GitSources


class InvestigationSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "source"
        self.repo.mkdir()

        def git(*args):
            return subprocess.check_output(
                ["git", *args], cwd=self.repo, stderr=subprocess.DEVNULL, text=True
            ).strip()

        git("init")
        (self.repo / "docs").mkdir()
        (self.repo / "docs/readme.md").write_text("first\nsecond\nthird\n")
        (self.repo / "docs/link").symlink_to("readme.md")
        (self.repo / "docs/exec.py").write_text("print(1)\n")
        (self.repo / "docs/exec.py").chmod(0o755)
        git("add", ".")
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "-m",
            "Source fixture",
        )
        self.head = git("rev-parse", "HEAD")
        self.provider = GitSources(
            {
                "repository": "owner/repo",
                "repository_id": 123,
                "investigation": {"source_paths": ["docs/"]},
            }
        )
        self.provider.metadata = Mock(return_value={"repository_id": 123})
        real_run = subprocess.run

        def local(argv, **kwargs):
            argv = list(argv)
            if argv[:2] == ["git", "clone"]:
                argv[-2] = str(self.repo)
            return real_run(argv, **kwargs)

        self.patch = patch(
            "collegium_pipeline.investigation_sources.subprocess.run", side_effect=local
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_capture_checks_actual_commit_blob_hash_lines_and_citation(self):
        source = self.provider.capture(
            self.head, [{"path": "docs/readme.md", "start": 2, "end": 3}]
        )[0]
        self.assertEqual(source["text"], "second\nthird")
        self.assertEqual(source["sha256"], hashlib.sha256(b"first\nsecond\nthird\n").hexdigest())
        self.assertEqual(source["head"], self.head)
        claim = {
            "text": "Two captured lines",
            "citations": [
                {"source_id": source["id"], "start": 2, "end": 3, "quote": "second\nthird"}
            ],
        }
        self.assertEqual(cited(claim, [source]), claim)
        claim["citations"][0]["quote"] = "fabricated"
        with self.assertRaises(PolicyError):
            cited(claim, [source])

    def test_symlink_executable_and_out_of_range_sources_are_refused(self):
        for row in (
            {"path": "docs/link", "start": 1, "end": 1},
            {"path": "docs/exec.py", "start": 1, "end": 1},
            {"path": "docs/readme.md", "start": 1, "end": 4},
        ):
            with self.subTest(row=row), self.assertRaises(PolicyError):
                self.provider.capture(self.head, [row])

    def test_invalid_scope_or_revision_is_refused_before_network(self):
        for head, row in (
            ("main", {"path": "docs/readme.md", "start": 1, "end": 1}),
            (self.head, {"path": "docs/../secrets", "start": 1, "end": 1}),
            (self.head, {"path": "other.txt", "start": 1, "end": 1}),
            (self.head, {"path": "docs/readme.md", "start": True, "end": 2}),
        ):
            with self.assertRaises(PolicyError):
                self.provider.capture(head, [row])
        self.provider.metadata.assert_not_called()
