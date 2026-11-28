"""Capture bounded regular-file excerpts from an independently pinned Git revision."""

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import PurePosixPath

from .capacity import checked_paths
from .domain import PolicyError, digest


class GitSources:
    def __init__(self, config):
        self.config = config

    def metadata(self):
        row = subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--fail",
                "--max-time",
                "30",
                "--header",
                "Accept: application/vnd.github+json",
                "--header",
                "X-GitHub-Api-Version: 2026-03-10",
                "https://api.github.com/repos/" + self.config["repository"],
            ],
            capture_output=True,
            text=True,
            timeout=35,
            check=True,
        )
        data = json.loads(row.stdout)
        if (
            data.get("id") != self.config["repository_id"]
            or data.get("full_name") != self.config["repository"]
        ):
            raise PolicyError("Investigation repository identity differs")
        return {"repository_id": data["id"], "repository": data["full_name"]}

    def capture(self, head, requests):
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
            raise PolicyError("An exact investigation commit is required")
        if not isinstance(requests, list) or not 1 <= len(requests) <= 16:
            raise PolicyError("Capture1..16bounded source excerpts")
        seen = set()
        for row in requests:
            if not isinstance(row, dict) or set(row) != {"path", "start", "end"}:
                raise PolicyError("Source requests need path/start/end")
            checked_paths([row["path"]], self.config["investigation"]["source_paths"])
            if (
                str(PurePosixPath(row["path"])) != row["path"]
                or row["path"].endswith("/")
                or row["path"] in seen
            ):
                raise PolicyError("Source files must be unique canonical regular paths")
            if (
                type(row["start"]) is not int
                or type(row["end"]) is not int
                or not 1 <= row["start"] <= row["end"] <= row["start"] + 199
            ):
                raise PolicyError("Source excerpts need at most200lines")
            seen.add(row["path"])
        self.metadata()
        with tempfile.TemporaryDirectory(prefix="collegium-investigation-") as directory:

            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=directory, capture_output=True, timeout=120, check=True
                ).stdout

            git(
                "clone",
                "--no-checkout",
                "--filter=blob:none",
                "https://github.com/" + self.config["repository"] + ".git",
                ".",
            )
            if git("cat-file", "-t", head).strip() != b"commit":
                raise PolicyError("Investigation head is not a commit")
            sources = []
            for row in requests:
                entry = git("ls-tree", head, "--", row["path"]).decode().split()
                if len(entry) != 4 or entry[0:2] != ["100644", "blob"]:
                    raise PolicyError("Investigation source is not a regular non-executable file")
                size = int(git("cat-file", "-s", entry[2]))
                if size > 2_000_000:
                    raise PolicyError("Source blob exceeds the capture bound")
                raw = git("cat-file", "blob", entry[2])
                if b"\x00" in raw:
                    raise PolicyError("Source must be UTF-8 text")
                lines = raw.decode().splitlines()
                if row["end"] > len(lines):
                    raise PolicyError("Source excerpt extends beyond the file")
                text = "\n".join(lines[row["start"] - 1 : row["end"]])
                if len(text.encode()) > 16000:
                    raise PolicyError("Source excerpt exceeds16KB")
                source = {
                    **row,
                    "head": head,
                    "repository_id": self.config["repository_id"],
                    "blob": entry[2],
                    "text": text,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                sources.append({"id": digest(source), **source})
            if sum(len(s["text"].encode()) for s in sources) > 48000:
                raise PolicyError("Source catalog exceeds48KB")
            return sources
