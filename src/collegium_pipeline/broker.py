"""Coordinator-only GitHub writes with durable intent and expected-head updates."""

import base64
import os
import re
from hashlib import sha1
from urllib.parse import quote, urlencode

from .adapters import Github
from .domain import PolicyError, digest
from .transport import JsonHttp, RemoteError


def broker_unstarted(journal, run_id, key, identity):
    events = journal.events(run_id)
    intents = [e for e in events if e["kind"] == "broker_intent" and e["data"]["key"] == key]
    if not intents or intents[-1]["data"]["identity"] != identity:
        return False
    intent = intents[-1]
    if any(
        e["kind"] == "broker_not_started"
        and e["data"].get("intent_sequence") == intent["sequence"]
        and e["data"].get("identity") == identity
        for e in events
    ):
        return True
    attempts = [
        e["data"]["operation"]
        for e in events
        if e["kind"] == "effect_attempt"
        and e["sequence"] > intent["sequence"]
        and e["data"]["operation"].get("kind") == "broker"
        and e["data"]["operation"].get("key") == key
    ]
    if not attempts:
        return False
    attempt = attempts[-1]
    return digest(
        {
            "run": run_id,
            "key": key,
            "operation": attempt["operation"],
            "payload": attempt["payload"],
        }
    ) == identity and journal.effect_not_started(attempt)


def changes_checked(changes, allowed):
    if not isinstance(changes, dict) or not changes or len(changes) > 100:
        raise PolicyError("Expected 1–100 changed text files")
    for path, content in changes.items():
        if (
            not isinstance(path, str)
            or not path
            or any(p in {"", ".", "..", ".git"} for p in path.split("/"))
            or "\\" in path
            or any(ord(c) < 32 for c in path)
            or not any(path == a or (a.endswith("/") and path.startswith(a)) for a in allowed)
        ):
            raise PolicyError("Change is outside the configured file scope")
        if content is not None and (
            not isinstance(content, str) or "\x00" in content or len(content.encode()) > 500000
        ):
            raise PolicyError("Only bounded UTF-8 text changes are supported")
    if sum(len(v.encode()) for v in changes.values() if v is not None) > 1000000:
        raise PolicyError("Candidate exceeds the text artifact limit")
    return changes


class GithubApp(Github):
    """No gh/PAT fallback for writes. Token stays in a private transport header."""

    def __init__(self, repository, repository_id, http):
        super().__init__(repository)
        self.repository_id, self.http = repository_id, http

    @classmethod
    def from_environment(cls, config):
        token = os.environ.get("COLLEGIUM_GITHUB_APP_TOKEN", "")
        if not token:
            raise PolicyError("A scoped GitHub App installation token is required")
        return cls(
            config["repository"],
            config["repository_id"],
            JsonHttp(
                "https://api.github.com",
                {
                    "Authorization": "Bearer " + token,
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
            ),
        )

    def scope(self):
        data, _ = self.http.request("GET", "/installation/repositories?per_page=100")
        repos = data.get("repositories", [])
        if data.get("total_count") != 1 or len(repos) != 1:
            raise PolicyError("Broker token must be an installation token scoped to one repository")
        if repos[0].get("id") != self.repository_id or repos[0].get("full_name") != self.repository:
            raise PolicyError("Broker token repository identity differs")
        if self.read().get("id") != self.repository_id:
            raise PolicyError("Repository identity changed")

    def read(self, path=""):
        return self.http.request("GET", f"/repos/{self.repository}" + path)[0]

    def pages(self, path, key=None):
        rows = []
        for page in range(1, 101):
            data = self.read(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            part = data[key] if key else data
            rows.extend(part)
            if len(part) < 100:
                return rows
        raise PolicyError("GitHub pagination limit exceeded")

    def pr_evidence(self, number):
        pr = self.read(f"/pulls/{number}")
        head = pr["head"]["sha"]
        checks, statuses = commit_evidence(self, head)
        for check in checks:
            if check.get("conclusion") in {"failure", "timed_out"}:
                annotations = self.pages(f"/check-runs/{check['id']}/annotations")
                check["output"] = {**(check.get("output") or {}), "annotations": annotations[:100]}
        current = self.read(f"/pulls/{number}")
        if (current["head"]["sha"], current["base"]["sha"]) != (head, pr["base"]["sha"]):
            raise PolicyError("PR changed while collecting CI")
        return current, checks, statuses

    def ref(self, branch):
        try:
            return self.read("/git/ref/heads/" + quote(branch, safe="/"))["object"]["sha"]
        except RemoteError as exc:
            if exc.status == 404:
                return None
            raise

    def mutate(self, operation, payload):
        if operation == "branch":
            return self.http.request("POST", f"/repos/{self.repository}/git/refs", payload)[0]
        if operation == "pr":
            return self.http.request("POST", f"/repos/{self.repository}/pulls", payload)[0]
        fields = {
            "commit": ("createCommitOnBranch", "CreateCommitOnBranchInput", "commit { oid }"),
            "draft": (
                "convertPullRequestToDraft",
                "ConvertPullRequestToDraftInput",
                "pullRequest { id isDraft }",
            ),
            "ready": (
                "markPullRequestReadyForReview",
                "MarkPullRequestReadyForReviewInput",
                "pullRequest { id isDraft }",
            ),
        }
        name, input_type, selection = fields[operation]
        query = f"mutation($input:{input_type}!){{{name}(input:$input){{{selection}}}}}"
        data, _ = self.http.request(
            "POST", "/graphql", {"query": query, "variables": {"input": payload}}
        )
        if data.get("errors") or not data.get("data", {}).get(name):
            # A GraphQL response can contain both data and errors: reconcile, never retry blindly.
            raise RemoteError("GitHub mutation needs reconciliation", unknown_outcome=True)
        return data["data"][name]


class PRBroker:
    def __init__(self, config, journal, github, *, observation_only=False):
        self.config, self.journal, self.github = config, journal, github
        self.observation_only = observation_only

    def action(self, run_id, key, operation, payload, observe):
        if not self.observation_only and (
            self.config.get("execution_enabled") is not True
            or self.config.get("broker_enabled") is not True
            or self.config.get("execution_profile", "delivery") != "delivery"
        ):
            raise PolicyError("Broker write authority is disabled")
        identity = digest({"run": run_id, "key": key, "operation": operation, "payload": payload})
        events = self.journal.events(run_id)
        done = [e["data"] for e in events if e["kind"] == "broker_done" and e["data"]["key"] == key]
        if done:
            if done[-1]["identity"] != identity:
                raise PolicyError("Action identity changed")
            return done[-1]["result"]
        intents = [
            e["data"] for e in events if e["kind"] == "broker_intent" and e["data"]["key"] == key
        ]
        if intents and intents[-1]["identity"] != identity:
            raise PolicyError("Pending action payload changed")
        found = observe()
        descriptor = {
            "kind": "broker",
            "run_id": run_id,
            "key": key,
            "operation": operation,
            "payload": payload,
        }
        if found is None:
            if self.observation_only or (
                intents and not broker_unstarted(self.journal, run_id, key, identity)
            ):
                raise PolicyError(
                    "Unresolved external action; observation only, no automatic replay"
                )
            self.journal.record(
                run_id, "broker_intent", {"key": key, "identity": identity, "operation": operation}
            )
            sequence = self.journal.events(run_id)[-1]["sequence"]
            try:
                self.github.scope()
                self.journal.checkpoint(descriptor)
            except Exception:
                self.journal.record(
                    run_id,
                    "broker_not_started",
                    {
                        "key": key,
                        "identity": identity,
                        "intent_sequence": sequence,
                        "descriptor_digest": digest(descriptor),
                    },
                )
                raise
            self.github.mutate(operation, payload)
            found = observe()
            if found is None:
                raise RemoteError("External write not yet observable", unknown_outcome=True)
        self.journal.record(
            run_id, "broker_done", {"key": key, "identity": identity, "result": found}
        )
        return found

    def branch(self, run_id, base):
        branch = "collegium/" + run_id
        if not re.fullmatch(r"collegium/[a-f0-9-]{36}", branch):
            raise PolicyError("Invalid run branch identity")

        def observe():
            value = self.github.ref(branch)
            if value is None:
                return None
            owned = any(
                e["kind"] == "broker_intent" and e["data"]["key"] == "branch"
                for e in self.journal.events(run_id)
            )
            if value != base or not owned:
                raise PolicyError("Run branch was occupied outside this action")
            return {"branch": branch, "head": value}

        self.action(
            run_id, "branch", "branch", {"ref": "refs/heads/" + branch, "sha": base}, observe
        )
        return branch

    def commit(self, run_id, branch, parent, changes, cycle):
        changes_checked(changes, self.config["allowed_paths"])
        # Avoid silently replacing symlinks/submodules or changing executable modes.
        parent_commit = self.github.read("/git/commits/" + parent)
        tree_sha = parent_commit["tree"]["sha"]
        tree = self.github.read(f"/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise PolicyError("Incomplete tree; cannot verify changed paths")
        entries = {r["path"]: r for r in tree["tree"]}
        for path in changes:
            for prefix in [
                path,
                *["/".join(path.split("/")[:i]) for i in range(1, len(path.split("/")))],
            ]:
                entry = entries.get(prefix)
                if prefix != path and entry and entry["type"] != "tree":
                    raise PolicyError("An ancestor path is not a directory")
                if entry and entry["mode"] not in {"100644", "040000"}:
                    raise PolicyError("Only regular non-executable text paths are supported")
            if path in entries and entries[path]["type"] != "blob":
                raise PolicyError("Cannot replace a directory with text")
            if changes[path] is None and path not in entries:
                raise PolicyError("Cannot delete an absent file")
        original = {p: (e["mode"], e["sha"]) for p, e in entries.items() if e["type"] != "tree"}
        expected = dict(original)
        for path, content in changes.items():
            if content is None:
                expected.pop(path, None)
            else:
                raw = content.encode()
                oid = sha1(
                    b"blob " + str(len(raw)).encode() + b"\x00" + raw, usedforsecurity=False
                ).hexdigest()
                expected[path] = ("100644", oid)
        if expected == original:
            raise PolicyError("Candidate has no file changes")
        marker = "Collegium-Action: " + digest(
            {"run": run_id, "cycle": cycle, "parent": parent, "changes": changes}
        )
        payload = {
            "branch": {"repositoryNameWithOwner": self.config["repository"], "branchName": branch},
            "expectedHeadOid": parent,
            "message": {"headline": "Apply pipeline candidate", "body": marker},
            "fileChanges": {
                "additions": [
                    {"path": p, "contents": base64.b64encode(c.encode()).decode()}
                    for p, c in sorted(changes.items())
                    if c is not None
                ],
                "deletions": [{"path": p} for p, c in sorted(changes.items()) if c is None],
            },
        }

        def observe():
            head = self.github.ref(branch)
            if head == parent:
                return None
            if head is None:
                raise PolicyError("Run branch disappeared")
            commit = self.github.read("/git/commits/" + head)
            if commit.get("message", "").splitlines()[-1:] != [marker] or [
                p["sha"] for p in commit["parents"]
            ] != [parent]:
                raise PolicyError("Run branch changed outside the broker")
            actual_tree = self.github.read(f"/git/trees/{commit['tree']['sha']}?recursive=1")
            if actual_tree.get("truncated"):
                raise PolicyError("Incomplete committed tree")
            actual = {
                e["path"]: (e["mode"], e["sha"]) for e in actual_tree["tree"] if e["type"] != "tree"
            }
            if actual != expected:
                raise PolicyError("Observed commit contents differ from the admitted candidate")
            return {"head": head, "parent": parent, "changes_digest": digest(changes)}

        return self.action(run_id, f"commit:{cycle}", "commit", payload, observe)["head"]

    def open_pr(self, run_id, branch, head, base, title, *, description=None):
        marker = f"<!-- collegium-run:{run_id} -->"

        def observe():
            params = urlencode(
                {"state": "all", "head": self.config["repository"].split("/")[0] + ":" + branch}
            )
            rows = self.github.pages("/pulls?" + params)
            if not rows:
                return None
            if len(rows) != 1:
                raise PolicyError("Multiple PRs for the run branch")
            pr = rows[0]
            if (
                marker not in (pr.get("body") or "")
                or pr["state"] != "open"
                or pr["head"]["sha"] != head
                or pr["base"]["sha"] != base
                or pr["base"]["ref"] != self.config["base_branch"]
                or pr["base"]["repo"]["id"] != self.config["repository_id"]
                or pr["head"]["repo"]["id"] != self.config["repository_id"]
            ):
                raise PolicyError("Existing PR ownership or revision differs")
            return {"number": pr["number"], "node_id": pr["node_id"], "url": pr["html_url"]}

        return self.action(
            run_id,
            "pr",
            "pr",
            {
                "title": title,
                "body": marker
                + "\n\n"
                + (
                    description
                    if description is not None
                    else "Validation and independent review receipts "
                    "are retained by the coordinator."
                ),
                "head": branch,
                "base": self.config["base_branch"],
                "draft": False,
                "maintainer_can_modify": False,
            },
            observe,
        )

    def draft(self, run_id, number, node_id, *, draft, cycle):
        def observe():
            pr = self.github.read(f"/pulls/{number}")
            if pr["node_id"] != node_id or pr["state"] != "open":
                raise PolicyError("PR identity/state changed")
            return {"draft": draft} if pr["draft"] is draft else None

        return self.action(
            run_id,
            f"draft:{cycle}:{draft}",
            "draft" if draft else "ready",
            {"pullRequestId": node_id},
            observe,
        )


def commit_evidence(github, head):
    """Complete, exact-commit CI evidence shared by ticket and epic acceptance."""
    if not isinstance(head, str) or not re.fullmatch(r"[a-f0-9]{40}", head):
        raise PolicyError("CI evidence requires an exact commit")
    return (
        github.pages(f"/commits/{head}/check-runs?filter=all", "check_runs"),
        [{**s, "sha": head} for s in github.pages(f"/commits/{head}/statuses")],
    )
