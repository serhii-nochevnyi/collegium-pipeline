"""Fixed service authority; merges push only to the pinned isolated ref, never a PR base."""

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import native_github_broker as native

ordinary_execute = native.execute


def verify(proof, purpose, policy):
    body = proof.get("body", {}) if isinstance(proof, dict) else {}
    key = os.environ.get("PIPELINE_CONTROL_KEY")
    expected = (
        hmac.new(
            key.encode(),
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        if key
        else ""
    )
    if (
        not key
        or time.time() > policy["expires_at"]
        or not hmac.compare_digest(proof.get("mac", ""), expected)
        or body.get("purpose") != purpose
        or body.get("suite_id") != policy["suite_id"]
        or body.get("graph_digest") != policy["graph_digest"]
        or body.get("task_key") not in {"A", "B", "C"}
        or not re.fullmatch(r"[a-f0-9-]{36}", body.get("child_id", ""))
    ):
        raise ValueError("Service action lacks a current signed admitted-child receipt")
    return body


def fixed_scope(scope, policy):
    if (
        scope["repository"] != "serhii-nochevnyi/collegium-pipeline"
        or scope["base_branch"] != policy["base_branch"]
        or scope["base_branch"] != "collegium/" + policy["suite_id"]
        or scope["allowed_paths"] != list(policy["fixtures"])
    ):
        raise ValueError("Service scope differs from the fixed suite")


def baseline(scope, policy, read):
    prefix = "/repos/" + scope["repository"]
    if read(prefix + "/git/ref/heads/main")["object"]["sha"] != policy["main_sha"]:
        raise ValueError("Main changed; stop isolated diagnostic")
    tip = read(prefix + "/git/ref/heads/" + scope["base_branch"])["object"]["sha"]
    current = tip
    merges = []
    seen = set()
    while current != policy["baseline"]:
        if len(seen) >= 3:
            raise ValueError("Service base left the authorized seed history")
        commit = read(prefix + "/git/commits/" + current)
        lines = [
            s
            for s in commit.get("message", "").splitlines()
            if s.startswith("Collegium-Service-Merge: ")
        ]
        if len(lines) != 1 or len(commit.get("parents", [])) != 2:
            raise ValueError("Unapproved service base commit")
        proof = json.loads(lines[0].split(": ", 1)[1])
        body = verify(proof, "ready", policy)
        if body["task_key"] in seen or commit["parents"][1]["sha"] != body["head"]:
            raise ValueError("Service merge history contradicts signed receipt")
        seen.add(body["task_key"])
        merges.append((body["task_key"], commit))
        current = commit["parents"][0]["sha"]
    if merges:

        def tree(sha):
            data = read(prefix + "/git/trees/" + sha + "?recursive=1")
            if data.get("truncated"):
                raise ValueError("Service tree evidence is incomplete")
            return {
                r["path"]: (r["mode"], r["type"], r["sha"])
                for r in data["tree"]
                if r["type"] != "tree"
            }

        expected = tree(read(prefix + "/git/commits/" + policy["baseline"])["tree"]["sha"])
        applied = set()
        for name, commit in reversed(merges):
            if name == "C" and not {"A", "B"} <= applied:
                raise ValueError("Service integration history violated A/B before C")
            applied.add(name)
            path = "tests/test_epic_service_" + name.lower() + ".py"
            content = policy["fixtures"][path].encode()
            sha = hashlib.sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content, usedforsecurity=False
            ).hexdigest()
            expected[path] = ("100644", "blob", sha)
            if tree(commit["tree"]["sha"]) != expected:
                raise ValueError("Signed merge changed unrelated service tree")
    return tip


def checked(scope, request, read):
    policy = json.loads(Path("epic_service_scope.json").read_text())
    fixed_scope(scope, policy)
    prefix = "/repos/" + scope["repository"]
    expected_tip = baseline(scope, policy, read)
    match = re.fullmatch(re.escape(prefix) + r"/pulls/(\d+)(/merge)?", request["path"])
    if not match:
        raise ValueError("Service action must address a fixed-repository PR")
    number = int(match[1])
    pr = {**read(prefix + "/pulls/" + str(number)), "_service_base_tip": expected_tip}
    if request["method"] == "SERVICE_CLOSE":
        if (
            match[2]
            or number != policy["ci_probe"]["number"]
            or pr["node_id"] != policy["ci_probe"]["node_id"]
            or pr["head"]["ref"] != policy["base_branch"]
            or pr["base"]["ref"] != "main"
            or request.get("payload") != {"state": "closed"}
            or pr.get("merged")
        ):
            raise ValueError("Only the fixed unmerged CI probe can be closed")
        return prefix + "/pulls/" + str(number), pr, False
    if pr.get("merged"):
        if pr.get("state") != "closed":
            raise ValueError("Merged service PR has inconsistent lifecycle")
    elif pr.get("state") != "open" or pr.get("draft") is not False:
        raise ValueError("Closed unmerged or draft service PR cannot be integrated")
    payload = request.get("payload", {})
    body = verify(payload.get("acceptance", {}), "ready", policy)
    expected_path = "tests/test_epic_service_" + body["task_key"].lower() + ".py"
    if (
        request["method"] != "SERVICE_MERGE"
        or not match[2]
        or set(payload) != {"sha", "acceptance"}
        or pr["base"]["ref"] != policy["base_branch"]
        or body.get("base_branch") != policy["base_branch"]
        or pr["base"]["repo"]["id"] != 1474663859
        or pr["head"]["repo"]["id"] != 1474663859
        or pr["head"]["sha"] != payload["sha"]
        or body.get("head") != payload["sha"]
        or body.get("pr", {}).get("number") != number
        or body["pr"].get("node_id") != pr["node_id"]
        or pr["head"]["ref"] != "collegium/" + body["child_id"]
        or body.get("branch") != pr["head"]["ref"]
        or "<!-- collegium-run:" + body["child_id"] + " -->" not in pr.get("body", "")
        or not body.get("validation_session")
        or not body.get("review_session")
        or body["validation_session"] == body["review_session"]
    ):
        raise ValueError("Service merge differs from accepted independent revision")
    files = read(prefix + "/pulls/" + str(number) + "/files?per_page=100")
    if len(files) != 1 or files[0]["filename"] != expected_path or files[0]["status"] != "added":
        raise ValueError("Service PR must add its one exact admitted fixture")
    blob = read(prefix + "/contents/" + expected_path + "?ref=" + pr["head"]["sha"])
    if base64.b64decode(blob["content"]).decode() != policy["fixtures"][expected_path]:
        raise ValueError("Service fixture contents differ")
    checks = read(prefix + "/commits/" + pr["head"]["sha"] + "/check-runs?per_page=100&filter=all")
    if checks.get("total_count", 101) > 100:
        raise ValueError("Service CI evidence is truncated")
    quality = [
        c
        for c in checks["check_runs"]
        if c["name"] == "quality" and c["head_sha"] == pr["head"]["sha"]
    ]
    latest = max(quality, key=lambda c: c["id"]) if quality else {}
    if (
        latest.get("status") != "completed"
        or latest.get("conclusion") != "success"
        or latest.get("app", {}).get("slug") != "github-actions"
    ):
        raise ValueError("Exact-head GitHub Actions quality must pass")
    return prefix + "/pulls/" + str(number) + "/merge", pr, True


def merge_isolated(scope, policy, pr, acceptance):
    # The actual write names a literal ref plus expected old SHA. PR retargeting
    # cannot redirect this push. GitHub observes the ordinary merge from ancestry.
    with tempfile.TemporaryDirectory(prefix="collegium-service-merge-") as directory:

        def git(*args, check=True):
            return subprocess.run(
                ["git", *args],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=120,
                check=check,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )

        git("clone", "--no-checkout", "https://github.com/" + scope["repository"] + ".git", ".")
        branch = scope["base_branch"]
        tip = git("ls-remote", "--heads", "origin", "refs/heads/" + branch).stdout.split()[0]
        if tip != pr["_service_base_tip"]:
            raise ValueError("Service base moved after proof; observe again before merge")
        git("checkout", "--detach", tip)
        if git("merge-base", "--is-ancestor", pr["head"]["sha"], tip, check=False).returncode == 0:
            return 200, {"sha": tip, "head_contained": True, "already_observed": True}
        if pr.get("merged"):
            raise ValueError("Merged PR head disappeared; never create another merge")
        marker = (
            "Merge fixed epic service "
            + acceptance["body"]["task_key"]
            + "\n\nCollegium-Service-Merge: "
            + json.dumps(acceptance, sort_keys=True, separators=(",", ":"))
        )
        git(
            "-c",
            "user.name=Collegium service",
            "-c",
            "user.email=collegium-service@users.noreply.github.com",
            "merge",
            "--no-ff",
            "-m",
            marker,
            pr["head"]["sha"],
        )
        head = git("rev-parse", "HEAD").stdout.strip()
        parents = git("rev-list", "--parents", "-n", "1", "HEAD").stdout.split()[1:]
        if parents != [tip, pr["head"]["sha"]]:
            raise ValueError("Service integration must preserve exact parents")
        git(
            "push",
            "--force-with-lease=refs/heads/" + branch + ":" + tip,
            "origin",
            "HEAD:refs/heads/" + branch,
        )
        return 200, {"sha": head, "head_contained": True, "ref": branch}


def execute(scope, request):
    policy = json.loads(Path("epic_service_scope.json").read_text())
    fixed_scope(scope, policy)

    def read(path):
        status, body = native.http_request("GET", path)
        if status != 200:
            raise ValueError("Service proof read failed")
        return body

    if request["method"] in {"SERVICE_MERGE", "SERVICE_CLOSE"}:
        path, pr, merge = checked(scope, request, read)
        if merge:
            return merge_isolated(scope, policy, pr, request["payload"]["acceptance"])
        if pr.get("state") == "closed":
            return 200, {"state": "closed", "already_observed": True}
        return native.http_request("PATCH", path, {"state": "closed"})
    if request["method"] != "GET":
        raw = {k: request[k] for k in ("method", "path", "payload")}
        body = verify(request.get("authorization", {}), "rpc", policy)
        if body.get("request_digest") != native.identity(raw):
            raise ValueError("Signed action request differs")
        payload = request["payload"]
        branch = "collegium/" + body["child_id"]
        if branch == scope["base_branch"]:
            raise ValueError("Ordinary writes cannot target integration base")
        if request["method"] == "GIT_COMMIT":
            target = payload.get("branch", {}).get("branchName")
            changes = native.decode_changes(scope, payload)
            path = "tests/test_epic_service_" + body["task_key"].lower() + ".py"
            if changes != {path: policy["fixtures"][path]}:
                raise ValueError("Only the child exact fixture is allowed")
        elif request["method"] == "POST" and request["path"].endswith("/git/refs"):
            target = payload.get("ref", "").removeprefix("refs/heads/")
            if payload.get("sha") != baseline(scope, policy, read):
                raise ValueError("Child must fork authorized current base")
        elif request["method"] == "POST" and request["path"].endswith("/pulls"):
            target = payload.get("head")
        else:
            raise ValueError("Unsupported signed service mutation")
        if target != branch:
            raise ValueError("Service write targets another child or integration ref")
    return ordinary_execute(scope, request)


if __name__ == "__main__":
    native.execute = execute
    native.main()
