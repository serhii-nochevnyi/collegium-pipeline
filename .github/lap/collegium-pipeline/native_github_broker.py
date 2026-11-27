"""Run only inside a pinned Collegium script executor with repository credentials at egress."""

import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

MARKER = "COLLEGIUM_BROKER_RESPONSE="


def identity(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def decode_request(value):
    if not isinstance(value, dict):
        raise ValueError("RPC data must be an object")
    if "encoding" not in value:
        return value
    if set(value) != {"encoding", "data", "request_digest"} or value["encoding"] not in {
        "zlib-base64",
        "git-text-zlib-base64",
    }:
        raise ValueError("Unknown RPC encoding")
    data = value["data"]
    if not isinstance(data, str) or len(data) > 256_000:
        raise ValueError("Compressed RPC exceeds the input limit")
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(data, validate=True), 2_000_001)
        if (
            len(raw) > 2_000_000
            or not decoder.eof
            or decoder.unused_data
            or decoder.unconsumed_tail
        ):
            raise ValueError("RPC exceeds its expansion limit or has trailing data")
        request = json.loads(raw)
    except (zlib.error, UnicodeError) as exc:
        raise ValueError("Invalid compressed RPC") from exc
    if isinstance(request, dict) and value["encoding"] == "git-text-zlib-base64":
        if request.get("method") != "GIT_COMMIT":
            raise ValueError("Text transport is only for Git commits")
        changes = (request.get("payload") or {}).get("fileChanges", {})
        for row in changes.get("additions", []):
            text = row.pop("text")
            if not isinstance(text, str) or "contents" in row:
                raise ValueError("Text transport contains an invalid file")
            row["contents"] = base64.b64encode(text.encode("utf-8")).decode()
    if not isinstance(request, dict) or identity(request) != value["request_digest"]:
        raise ValueError("RPC digest differs after decompression")
    return request


def branch_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"collegium/[a-f0-9-]{36}", value):
        raise ValueError("Only a run-owned task branch is permitted")
    return value


def commit_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("An exact commit SHA is required")
    return value


def check_scope(scope, request):
    method, path, payload = request["method"], request["path"], request.get("payload")
    prefix = "/repos/" + scope["repository"]
    split = urlsplit(path)
    decoded = unquote(split.path)
    if (
        not path.startswith(prefix)
        or split.scheme
        or split.netloc
        or split.fragment
        or "\\" in decoded
        or any(x in {".", ".."} for x in decoded.split("/"))
    ):
        raise ValueError("Request leaves the pinned repository")
    suffix = decoded[len(prefix) :]
    if method == "GET":
        if not re.fullmatch(
            r"(?:|/git/(?:ref/heads/.+|commits/[0-9a-f]{40}|trees/[0-9a-f]{40})|/pulls(?:/\d+)?|/commits/[0-9a-f]{40}/(?:check-runs|statuses)|/check-runs/\d+/annotations)",
            suffix,
        ):
            raise ValueError("Read endpoint is not permitted")
    elif method == "POST" and suffix == "/git/refs":
        branch_name(payload.get("ref", "").removeprefix("refs/heads/"))
        commit_sha(payload.get("sha"))
    elif method == "POST" and suffix == "/pulls":
        branch = branch_name(payload.get("head"))
        if payload.get("base") != scope["base_branch"] or payload.get("draft") is not False:
            raise ValueError("PR must target the pinned base as a reviewable PR")
        if f"<!-- collegium-run:{branch.split('/')[1]} -->" not in payload.get("body", ""):
            raise ValueError("PR run marker is absent")
    elif method == "GIT_COMMIT" and suffix == "/git/commit-on-branch":
        branch = payload.get("branch", {})
        if branch.get("repositoryNameWithOwner") != scope["repository"]:
            raise ValueError("Commit repository changed")
        branch_name(branch.get("branchName"))
        commit_sha(payload.get("expectedHeadOid"))
    else:
        raise ValueError("Only scoped reads, branch/PR creation and leased commits are permitted")


def http_request(method, path, payload=None):
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--max-time",
        "45",
        "--request",
        method,
        "--header",
        "Accept: application/vnd.github+json",
        "--header",
        "X-GitHub-Api-Version: 2026-03-10",
        "--write-out",
        "\n%{http_code}",
    ]
    if payload is not None:
        command += ["--header", "Content-Type: application/json", "--data-binary", "@-"]
    command += ["https://api.github.com" + path]
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        timeout=50,
        check=True,
    )
    body, status = result.stdout.rsplit("\n", 1)
    return int(status), json.loads(body) if body else {}


def decode_changes(scope, payload):
    changes = {}
    for row in payload.get("fileChanges", {}).get("additions", []):
        path = row["path"]
        if path in changes:
            raise ValueError("Duplicate changed path")
        raw = base64.b64decode(row["contents"], validate=True)
        if len(raw) > 500000 or b"\x00" in raw:
            raise ValueError("Changed file exceeds the text limit")
        changes[path] = raw.decode("utf-8")
    for row in payload.get("fileChanges", {}).get("deletions", []):
        if row["path"] in changes:
            raise ValueError("Duplicate changed path")
        changes[row["path"]] = None
    if not 1 <= len(changes) <= 100:
        raise ValueError("Expected 1–100 changed text files")
    for path in changes:
        if (
            not isinstance(path, str)
            or "\\" in path
            or path.startswith("/")
            or any(p in {"", ".", "..", ".git"} for p in path.split("/"))
            or any(ord(c) < 32 for c in path)
            or not any(
                path == a or a.endswith("/") and path.startswith(a) for a in scope["allowed_paths"]
            )
        ):
            raise ValueError("Changed path is outside the pinned scope")
    if sum(len(v.encode()) for v in changes.values() if v is not None) > 1000000:
        raise ValueError("Candidate exceeds the text limit")
    return changes


def publish_commit(scope, payload):
    changes = decode_changes(scope, payload)
    branch = branch_name(payload["branch"]["branchName"])
    parent = commit_sha(payload["expectedHeadOid"])
    message = payload.get("message", {})
    if not re.fullmatch(r"Collegium-Action: [0-9a-f]{64}", message.get("body", "")):
        raise ValueError("Commit action marker is absent")
    with tempfile.TemporaryDirectory(prefix="collegium-broker-") as folder:

        def git(*argv):
            result = subprocess.run(
                ["git", *argv],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=90,
                check=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            return result.stdout.strip()

        git("clone", "--no-checkout", "https://github.com/" + scope["repository"] + ".git", ".")
        line = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
        if line.split() != [parent, "refs/heads/" + branch]:
            raise ValueError("Task branch head changed before candidate publication")
        git("checkout", "--detach", parent)
        for path, content in changes.items():
            file = Path(folder) / path
            for ancestor in [file, *file.parents]:
                if ancestor == Path(folder):
                    break
                if ancestor.is_symlink():
                    raise ValueError("Symlink paths are unsupported")
            if file.exists() and (not file.is_file() or file.stat().st_mode & 0o111):
                raise ValueError("Only regular non-executable files are supported")
            if content is None:
                file.unlink()
            else:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
        git("add", "--all", "--", ".")
        changed = set(git("diff", "--cached", "--name-only").splitlines())
        if changed != set(changes):
            raise ValueError("Staged changes differ from the admitted candidate")
        git(
            "-c",
            "user.name=Collegium Pipeline",
            "-c",
            "user.email=collegium-pipeline@users.noreply.github.com",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            message.get("headline", "Pipeline candidate"),
            "-m",
            message["body"],
        )
        head = commit_sha(git("rev-parse", "HEAD"))
        if git("rev-list", "--parents", "-n", "1", head).split() != [head, parent]:
            raise ValueError("Candidate is not a direct child of the expected head")
        # This lease is the Git protocol's atomic expected-head precondition.
        # The candidate is proven a direct child, so no history rewrite is permitted.
        git(
            "push",
            "--force-with-lease=refs/heads/" + branch + ":" + parent,
            "origin",
            head + ":refs/heads/" + branch,
        )
        return 200, {"commit": {"oid": head}}


def execute(scope, request):
    check_scope(scope, request)
    if request["method"] == "GIT_COMMIT":
        return publish_commit(scope, request["payload"])
    return http_request(request["method"], request["path"], request.get("payload"))


def main():
    scope = json.loads(Path("broker_scope.json").read_text())
    event = json.loads(Path("/job/event.json").read_text())
    request = None
    try:
        request = decode_request(event["data"])
        status, body = execute(scope, request)
    except ValueError as exc:
        status, body = 400, {"code": "broker_scope_refused", "message": str(exc)}
    except (OSError, subprocess.SubprocessError, KeyError, TypeError):
        # Never print raw subprocess output, credentials, environment or headers.
        status, body = 500, {"code": "broker_operation_unresolved"}
    print(
        MARKER + json.dumps({"request_digest": identity(request), "status": status, "body": body})
    )


if __name__ == "__main__":
    main()
