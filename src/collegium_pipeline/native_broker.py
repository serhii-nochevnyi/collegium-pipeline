"""GitHub App brokerage through a pinned, manual-only Collegium script executor."""

import base64
import hashlib
import json
import time
import zlib
from urllib.parse import quote

from .adapters import Github
from .broker import GithubApp
from .domain import PolicyError, digest
from .transport import RemoteError

MARKER = "COLLEGIUM_BROKER_RESPONSE="


def encode_request(request, *, compress=False):
    raw = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) <= 60_000:
        return request
    if not compress:
        raise PolicyError("Large broker RPC requires reviewed compression support")
    transfer = json.loads(raw)
    encoding = "zlib-base64"
    changes = (transfer.get("payload") or {}).get("fileChanges", {})
    if request["method"] == "GIT_COMMIT" and "additions" in changes:
        # Compress UTF-8 source before base64; compressing already-base64 source
        # loses enough redundancy to exceed the platform's 256 KB event limit.
        for row in changes["additions"]:
            content = base64.b64decode(row.pop("contents"), validate=True)
            row["text"] = content.decode("utf-8")
        encoding = "git-text-zlib-base64"
    raw = json.dumps(transfer, sort_keys=True, separators=(",", ":")).encode()
    wire = {
        "encoding": encoding,
        "request_digest": digest(request),
        "data": base64.b64encode(zlib.compress(raw, 9)).decode(),
    }
    if len(raw) > 2_000_000 or len(json.dumps({"data": wire}).encode()) > 250_000:
        raise PolicyError("Broker RPC exceeds the bounded managed-event size")
    return wire


def binding_digest(row, code):
    return digest(
        {
            "project_id": row["project_id"],
            "target": row["target"],
            "status": row["status"],
            "triggers": row["triggers"],
            "files": code["current"]["files"],
        }
    )


class ScriptTransport:
    def __init__(self, config, http, journal, run_id, *, clock=time.monotonic, pause=time.sleep):
        self.config, self.http, self.journal, self.run_id = config, http, journal, run_id
        self.clock, self.pause = clock, pause
        self.binding = config["native_broker"]
        self.path = "/api/automations/" + self.binding["automation_id"]

    def scope(self):
        row, _ = self.http.request("GET", self.path)
        code, _ = self.http.request("GET", self.path + "/code")
        if binding_digest(row, code) != self.binding["approved_digest"]:
            raise PolicyError("Native broker configuration/code changed")
        expected = [
            {
                "type": "github_repository",
                "url": "https://github.com/" + self.config["repository"],
                "connection": self.config["github_connection_id"],
                "access": "contributor",
            }
        ]
        target = row["target"]
        if (
            row["project_id"] != self.config["project_id"]
            or row["status"] != "paused"
            or (row["triggers"] and not self.config.get("broker_allow_paused_triggers", False))
            or target.get("kind") != "script"
            or target.get("repositories") != expected
            or any(target.get(k) for k in ("secrets", "variables", "mcp_servers"))
        ):
            raise PolicyError("Native broker scope differs from its admitted project/repository")
        scope = json.loads(code["current"]["files"]["broker_scope.json"])
        if scope != {k: self.config[k] for k in ("repository", "base_branch", "allowed_paths")}:
            raise PolicyError("Native broker path/branch policy differs")
        # Connection kind is checked through the authoritative project connection list.
        connections, _ = self.http.request(
            "GET", "/api/projects/" + self.config["project_id"] + "/github-connections"
        )
        own = [
            c for c in connections["connections"] if c["id"] == self.config["github_connection_id"]
        ]
        if len(own) != 1 or own[0].get("kind") != "github_app":
            raise PolicyError("Native broker requires the project's GitHub App connection")
        return {"kind": "github_app", "credential_location": "native_egress_proxy"}

    def request(self, method, path, payload=None):
        if method != "GET" and (
            self.config.get("execution_enabled") is not True
            or self.config.get("broker_enabled") is not True
        ):
            raise PolicyError("Native broker write authority is disabled")
        self.scope()
        request = {"method": method, "path": path, "payload": payload}
        wire = encode_request(request, compress=self.config.get("broker_compress_requests", False))
        key = digest(request)
        mutation = method != "GET"
        events = self.journal.events(self.run_id)
        prior = (
            [
                e["data"]
                for e in events
                if e["kind"] == "broker_rpc_started" and e["data"]["key"] == key
            ]
            if mutation
            else []
        )
        intents = (
            [e for e in events if e["kind"] == "broker_rpc_intent" and e["data"]["key"] == key]
            if mutation
            else []
        )
        queued = (
            [
                e["data"]
                for e in events
                if e["kind"] == "broker_rpc_queued" and e["data"]["key"] == key
            ]
            if mutation
            else []
        )
        if prior:
            remote_run = prior[-1]["remote_run"]
        elif queued:
            remote_run = self.assigned_run(queued[-1]["item_id"], mutation)
            self.journal.record(
                self.run_id,
                "broker_rpc_started",
                {"key": key, "remote_run": remote_run, "mutation": mutation},
            )
        else:
            if intents:
                raise PolicyError("Unresolved broker submission; never launch a replacement")
            if mutation:
                self.journal.record(self.run_id, "broker_rpc_intent", {"key": key})
            try:
                started, _ = self.http.request("POST", self.path + "/run", {"data": wire})
            except RemoteError as exc:
                if mutation and exc.status == 413 and not exc.unknown_outcome:
                    self.journal.record(
                        self.run_id,
                        "broker_rpc_refused",
                        {"key": key, "status": 413, "remote_run_created": False},
                    )
                raise
            remote_run = (started.get("run") or {}).get("id")
            if not remote_run:
                item_id = (started.get("item") or {}).get("id")
                if not item_id:
                    raise RemoteError(
                        "Broker submission omitted its run ID", unknown_outcome=mutation
                    )
                self.journal.record(
                    self.run_id, "broker_rpc_queued", {"key": key, "item_id": item_id}
                )
                remote_run = self.assigned_run(item_id, mutation)
            self.journal.record(
                self.run_id,
                "broker_rpc_started",
                {"key": key, "remote_run": remote_run, "mutation": mutation},
            )
        deadline = self.clock() + 180
        while self.clock() < deadline:
            row, _ = self.http.request("GET", self.path + "/runs/" + remote_run)
            if row["status"] in {"running", "queued", "waiting"}:
                self.pause(1)
                continue
            if row["status"] != "succeeded" or row.get("output_cut") is not False:
                raise RemoteError(
                    "Broker job failed or output is incomplete", unknown_outcome=mutation
                )
            lines = [
                line[len(MARKER) :]
                for line in row.get("output_tail", "").splitlines()
                if line.startswith(MARKER)
            ]
            if len(lines) != 1:
                raise RemoteError("Broker response absent or ambiguous", unknown_outcome=mutation)
            result = json.loads(lines[0])
            if result.get("request_digest") != key or type(result.get("status")) is not int:
                raise RemoteError("Broker response identity differs", unknown_outcome=mutation)
            status = result["status"]
            if not 200 <= status < 300:
                raise RemoteError(
                    f"Native GitHub HTTP {status}",
                    status=status,
                    unknown_outcome=mutation and status >= 500,
                    detail=result.get("body"),
                )
            return result["body"], {}
        raise RemoteError(
            "Broker job deadline exceeded; retain its run ID", unknown_outcome=mutation
        )

    def assigned_run(self, item_id, mutation):
        until = self.clock() + 180
        while self.clock() < until:
            try:
                rows, _ = self.http.request("GET", self.path + "/runs?limit=100")
            except RemoteError as exc:
                raise RemoteError(
                    "Broker queue observation unavailable; retain receipt", unknown_outcome=mutation
                ) from exc
            matches = [r for r in rows["runs"] if r.get("item_id") == item_id]
            if len(matches) > 1:
                raise PolicyError("Native broker queued item has ambiguous runs")
            if matches:
                return matches[0]["id"]
            self.pause(1)
        raise RemoteError(
            "Broker item is still queued; retain its receipt", unknown_outcome=mutation
        )


class NativeGithubApp(GithubApp):
    def __init__(self, config, http, journal, run_id):
        # Read authority is explicit in the admitted config. Mutations never use
        # this client or fall back to a person's credential.
        self.reader = (
            Github(config["repository"]) if config.get("broker_reads") == "local_gh" else None
        )
        super().__init__(
            config["repository"],
            config["repository_id"],
            ScriptTransport(config, http, journal, run_id),
        )

    def read(self, path=""):
        return self.reader.read(path) if self.reader else super().read(path)

    def logs(self, job_id):
        if type(job_id) is not int or job_id <= 0 or self.reader:
            raise PolicyError("Cloud Actions logs require the native App reader")
        value = self.read(f"/actions/jobs/{job_id}/logs")
        if value.get("encoding") != "zlib-base64" or len(value.get("data", "")) > 50_000:
            raise PolicyError("Invalid native log response")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(value["data"], validate=True), 2_000_001)
        if (
            len(raw) > 2_000_000
            or not decoder.eof
            or decoder.unused_data
            or decoder.unconsumed_tail
            or hashlib.sha256(raw).hexdigest() != value["sha256"]
        ):
            raise PolicyError("Native Actions logs are incomplete or changed")
        return raw.decode("utf-8")

    def ref(self, branch):
        if not self.reader:
            return super().ref(branch)
        # Matching refs returns [] for absence; gh's generic JSON reader deliberately
        # hides error bodies, so an auth/transport error must never mean "missing".
        rows = self.reader.read("/git/matching-refs/heads/" + quote(branch, safe="/"))
        exact = [r for r in rows if r.get("ref") == "refs/heads/" + branch]
        if not exact:
            return None
        if len(exact) != 1 or exact[0].get("object", {}).get("type") != "commit":
            raise PolicyError("GitHub ref identity is ambiguous or not a commit")
        return exact[0]["object"]["sha"]

    def scope(self):
        evidence = self.http.scope()
        if self.read().get("id") != self.repository_id:
            raise PolicyError("Native App repository identity differs")
        return evidence

    def mutate(self, operation, payload):
        prefix = "/repos/" + self.repository
        if operation == "commit":
            return self.http.request("GIT_COMMIT", prefix + "/git/commit-on-branch", payload)[0]
        if operation == "branch":
            return self.http.request("POST", prefix + "/git/refs", payload)[0]
        if operation == "pr":
            return self.http.request("POST", prefix + "/pulls", payload)[0]
        raise PolicyError("Native egress cannot use GraphQL draft/ready mutations")


def github_broker(config, http, journal, run_id):
    if config.get("broker_transport", "environment") == "collegium_script":
        return NativeGithubApp(config, http, journal, run_id)
    return GithubApp.from_environment(config)
