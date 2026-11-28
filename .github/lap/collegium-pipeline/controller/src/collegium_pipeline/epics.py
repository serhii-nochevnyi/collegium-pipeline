"""Immutable epic DAGs over the existing ticket engine; no merge authority."""

import json
import re
import time
from dataclasses import asdict

from .artifacts import Artifacts
from .broker import commit_evidence
from .capacity import Capacity, checked_paths
from .ci import inspect_ci
from .config import config_digest
from .delivery import Delivery
from .delivery_workers import NativeJobs
from .domain import PolicyError, Task, digest
from .platform import confirmed_pending_launch
from .store import CheckpointError


class AncestryPending(PolicyError):
    """A bounded read has not exhausted the immutable commit graph yet."""


def task_checked(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"source", "source_id", "repository", "title", "requirements"}
        or any(not isinstance(v, str) for v in value.values())
    ):
        raise PolicyError("Malformed task snapshot")
    return Task(**value)


def graph_checked(value, config):
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "version",
        "strategy",
        "epic",
        "tickets",
    }:
        raise PolicyError("Expected an explicit epic/v1 graph")
    if (
        value["schema_version"] != "epic/v1"
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["strategy"] != "direct_to_base"
    ):
        raise PolicyError("Only immutable version1 direct_to_base graphs are supported")
    if len(json.dumps(value).encode()) > 1_000_000:
        raise PolicyError("Epic graph exceeds snapshot budget")
    epic = task_checked(value["epic"])
    if epic.repository != config["repository"]:
        raise PolicyError("Epic repository mapping differs")
    nodes = value["tickets"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= config.get("epic", {}).get(
        "max_tickets", 100
    ):
        raise PolicyError("An epic needs1..max_tickets children")
    keys, identities = set(), {(epic.source, epic.source_id)}
    normalized = []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {
            "key",
            "task",
            "depends_on",
            "paths",
            "resources",
        }:
            raise PolicyError("Invalid epic ticket fields")
        task = task_checked(node["task"])
        key, deps = node["key"], node["depends_on"]
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", key)
            or key in keys
        ):
            raise PolicyError("Duplicate or invalid ticket key")
        identity = (task.source, task.source_id)
        if identity in identities or task.repository != epic.repository:
            raise PolicyError("Duplicate ticket identity or unknown repository mapping")
        if (
            not isinstance(deps, list)
            or any(not isinstance(d, str) for d in deps)
            or len(set(deps)) != len(deps)
        ):
            raise PolicyError("Invalid dependency list")
        paths = checked_paths(node["paths"] or config["allowed_paths"], config["allowed_paths"])
        resources = node["resources"]
        if resources is not None and (
            not isinstance(resources, list)
            or any(not isinstance(r, str) or not r or len(r) > 200 for r in resources)
        ):
            raise PolicyError("Invalid ticket resource claims")
        normalized.append(
            {
                **node,
                "task": asdict(task),
                "paths": paths,
                "depends_on": sorted(deps),
                "resources": None if resources is None else sorted(set(resources)),
            }
        )
        keys.add(key)
        identities.add(identity)
    pending = {n["key"]: set(n["depends_on"]) for n in normalized}
    if any(deps - keys for deps in pending.values()):
        raise PolicyError("Unknown prerequisite in epic graph")
    visited = set()
    while pending:
        ready = {key for key, deps in pending.items() if deps <= visited}
        if not ready:
            raise PolicyError("Epic dependency cycle")
        visited |= ready
        pending = {key: deps for key, deps in pending.items() if key not in ready}
    return {**value, "epic": asdict(epic), "tickets": sorted(normalized, key=lambda n: n["key"])}


class Epics:
    def __init__(self, config, journal, github_factory, http, artifacts, *, clock=None):
        self.config, self.journal, self.github_factory, self.http = (
            config,
            journal,
            github_factory,
            http,
        )
        self.artifacts = Artifacts(artifacts)
        self.clock = clock
        self.capacity = Capacity(journal, config)
        journal.connection.execute(
            "CREATE TABLE IF NOT EXISTS epics "
            "(run_id TEXT PRIMARY KEY REFERENCES runs(id), document TEXT NOT NULL)"
        )
        journal.connection.execute(
            "CREATE TABLE IF NOT EXISTS epic_nodes "
            "(epic_id TEXT NOT NULL REFERENCES epics(run_id), "
            "ticket_key TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id), "
            "PRIMARY KEY(epic_id,ticket_key))"
        )
        journal.connection.execute(
            "CREATE TABLE IF NOT EXISTS ancestry "
            "(identity TEXT PRIMARY KEY, document TEXT NOT NULL)"
        )

    def save(self, root, doc):
        with self.journal.transaction():
            self.journal.connection.execute(
                "INSERT INTO epics VALUES(?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET document=excluded.document",
                (root, json.dumps(doc, sort_keys=True)),
            )
            self.journal._event(
                root, "epic_tick", {"state": doc["state"], "graph_digest": doc["graph_digest"]}
            )
        return {"run_id": root, **doc}

    def load(self, root):
        row = self.journal.connection.execute(
            "SELECT document FROM epics WHERE run_id=?", (root,)
        ).fetchone()
        if not row or self.journal.get(root)["config_digest"] != config_digest(self.config):
            raise PolicyError("Epic missing or its configuration changed")
        return json.loads(row[0])

    def admit(self, graph):
        graph = graph_checked(graph, self.config)
        with self.journal.transaction():
            root = self.journal.admit(
                Task(**graph["epic"]), config_digest(self.config), purpose="epic"
            )
            exists = self.journal.connection.execute(
                "SELECT document FROM epics WHERE run_id=?", (root,)
            ).fetchone()
            if exists:
                doc = json.loads(exists[0])
                if doc["graph_digest"] != digest(graph):
                    raise PolicyError("Epic graph changed; explicit paused replan is required")
                return {"run_id": root, **doc}
            doc = {
                "graph": graph,
                "graph_digest": digest(graph),
                "version": 1,
                "paused": False,
                "state": "queued",
                "cursor": 0,
                "base": None,
                "integration_head": None,
                "integration_attempt": 0,
                "validation": None,
                "review": None,
                "tokens": 0,
                "nodes": {},
                "delivered": False,
            }
            self.save(root, doc)
            self.capacity.register(root, resources=["repository:*"], epic=root, dormant=True)
            for node in graph["tickets"]:
                child = self.journal.admit(Task(**node["task"]), config_digest(self.config))
                self.capacity.register(
                    child, paths=node["paths"], resources=node["resources"], epic=root, dormant=True
                )
                self.journal.connection.execute(
                    "INSERT INTO epic_nodes VALUES(?,?,?)", (root, node["key"], child)
                )
                doc["nodes"][node["key"]] = {
                    "run_id": child,
                    "state": "queued",
                    "reason": "dependencies",
                    "merged": None,
                }
            return self.save(root, doc)

    def pause(self, root, paused):
        if type(paused) is not bool:
            raise PolicyError("Pause must be boolean")
        doc = self.load(root)
        with self.journal.transaction():
            doc["paused"] = paused
            if paused:
                for run in [root, *[n["run_id"] for n in doc["nodes"].values()]]:
                    self.journal.connection.execute(
                        "UPDATE ticket_claims SET state='dormant' "
                        "WHERE run_id=? AND state='waiting'",
                        (run,),
                    )
            return self.save(root, doc)

    def driver(self, root):
        return Delivery(
            self.config,
            self.journal,
            self.github_factory(root),
            self.http,
            self.artifacts.directory,
            **({"clock": self.clock} if self.clock else {}),
        )

    def settle(self, root, doc=None):
        jobs = NativeJobs(self.config, self.journal, self.http, self.artifacts)
        result = jobs.drain(root)
        if doc is not None:
            doc["tokens"] += result["tokens"] - doc.get("drained_tokens", 0)
            doc["drained_tokens"] = result["tokens"]
            doc["settlement"] = result
        self.capacity.release(root)
        return result

    def defer_waiters(self, root, doc):
        for run in [root, *[n["run_id"] for n in doc["nodes"].values()]]:
            self.capacity.defer(run, root)

    def budget(self, doc):
        spent, reserved = doc["tokens"], 0
        for node in doc["nodes"].values():
            driver = self.driver(node["run_id"])
            delivery = driver._load(node["run_id"]) or {}
            if delivery:
                driver.account_usage(node["run_id"], delivery)
            used = delivery.get("tokens", 0)
            spent += used
            if self.capacity.get(node["run_id"])["state"] == "active":
                reserved += max(0, self.config["max_total_tokens"] - used)
        return spent, reserved

    def contains(self, github, base, merge):
        identity = digest([self.config["repository_id"], base, merge])
        row = self.journal.connection.execute(
            "SELECT document FROM ancestry WHERE identity=?", (identity,)
        ).fetchone()
        state = json.loads(row[0]) if row else {"pending": [base], "seen": [], "result": None}
        if state["result"] is not None:
            return state["result"]
        pending, seen = state["pending"], set(state["seen"])
        for _ in range(32):
            if not pending or merge in seen:
                break
            commit = pending.pop()
            if commit in seen:
                continue
            seen.add(commit)
            if commit == merge:
                break
            parents = github.read("/git/commits/" + commit).get("parents")
            if not isinstance(parents, list) or any(
                not re.fullmatch(r"[a-f0-9]{40}", p.get("sha", "")) for p in parents
            ):
                raise PolicyError("Incomplete Git ancestry response")
            # Prefer mainline while retaining every alternate parent for completeness.
            pending.extend(p["sha"] for p in reversed(parents))
        result = True if merge in seen else None if pending else False
        self.journal.connection.execute(
            "INSERT INTO ancestry VALUES(?,?) "
            "ON CONFLICT(identity) DO UPDATE SET document=excluded.document",
            (identity, json.dumps({"pending": pending, "seen": sorted(seen), "result": result})),
        )
        return result

    def needs_worker(self, child, delivery):
        delivery = delivery or {"state": "planning", "cycle": 0, "plan_attempt": 0}
        stage = delivery["state"]
        if stage not in {
            "planning",
            "plan_review",
            "implementing",
            "validating",
            "reviewing",
            "fixing",
        }:
            return False
        key = f"{delivery['cycle']}:{stage}:{delivery['plan_attempt']}"
        row = self.journal.connection.execute(
            "SELECT id FROM runs WHERE source_id=?", (child + ":" + key,)
        ).fetchone()
        return self.job_needs_admission(row[0] if row else None)

    def job_needs_admission(self, job):
        if job is None:
            return True
        if any(e["kind"] == "worker_completed" for e in self.journal.events(job)):
            return False
        # A durable intent or named session is not proof that its paid prompt began.
        # Unknown intents retain their claims, but cannot bypass budget admission.
        return confirmed_pending_launch(self.journal, job) is None

    def merged(self, root, delivery, base):
        if (
            not delivery
            or delivery["state"] != "ready_for_acceptance"
            or not delivery.get("ci_green")
        ):
            return None
        github = self.github_factory(root)
        pr = github.read(f"/pulls/{delivery['pr']['number']}")
        if (
            pr.get("node_id") != delivery["pr"]["node_id"]
            or pr.get("head", {}).get("sha") != delivery["head"]
            or pr.get("head", {}).get("ref") != delivery["branch"]
            or pr.get("base", {}).get("repo", {}).get("id") != self.config["repository_id"]
            or pr.get("base", {}).get("ref") != self.config["base_branch"]
            or any(
                not delivery.get(s) or delivery[s]["revision"]["head"] != delivery["head"]
                for s in ("validation", "review")
            )
        ):
            raise PolicyError("Prerequisite PR identity or accepted revision changed")
        if not pr.get("merged"):
            if pr.get("state") != "open":
                raise PolicyError("Prerequisite PR was closed without merge")
            return None
        if (
            pr.get("state") != "closed"
            or not pr.get("merged_at")
            or not re.fullmatch(r"[a-f0-9]{40}", pr.get("merge_commit_sha", ""))
        ):
            raise PolicyError("Merged prerequisite identity differs")
        checks, statuses = commit_evidence(github, delivery["head"])
        if (
            inspect_ci(
                checks, statuses, head=delivery["head"], required=self.config["required_checks"]
            )["state"]
            != "green"
        ):
            raise PolicyError("Merged prerequisite exact-head CI is no longer green")
        contained = self.contains(github, base, pr["merge_commit_sha"])
        if contained is None:
            raise AncestryPending("Continuing bounded ancestry verification at the selected base")
        if not contained:
            raise PolicyError("Prerequisite merge is not contained in the selected base")
        return {
            "pr": delivery["pr"],
            "head": delivery["head"],
            "merge_commit": pr["merge_commit_sha"],
            "observed_base": base,
        }

    def step(self, root):
        if not self.config.get("execution_enabled") or not self.config.get("broker_enabled"):
            raise PolicyError("Epic execution and broker are disabled")
        doc = self.load(root)
        github = self.github_factory(root)
        if doc["state"] in {"failed", "blocked"}:
            self.settle(root, doc)
            for status in doc["nodes"].values():
                self.driver(status["run_id"]).workers.drain(status["run_id"])
                self.capacity.release(status["run_id"])
            return self.save(root, doc)
        github.scope()
        base = github.ref(self.config["base_branch"])
        if not isinstance(base, str) or not re.fullmatch(r"[a-f0-9]{40}", base):
            raise PolicyError("Epic requires an exact configured base SHA")
        if doc["base"] is None:
            doc["base"] = base
        if doc["integration_head"] not in {None, base}:
            doc.update(state="blocked", reason="Integration base changed; explicit replan required")
            self.settle(root, doc)
            self.defer_waiters(root, doc)
            return self.save(root, doc)
        documents, failures = {}, {}
        # Refresh ALL prerequisite proofs against ONE head before any admission.
        for key, status in doc["nodes"].items():
            child = status["run_id"]
            delivery = self.driver(child)._load(child)
            if (
                delivery
                and delivery["state"] != "ready_for_acceptance"
                and self.capacity.get(child)["state"] == "active"
                and delivery["base"] != base
            ):
                driver = self.driver(child)
                delivery.update(state="blocked", reason="Base changed during active ticket work")
                driver.workers.drain(child)
                driver.account_usage(child, delivery)
                driver._save(child, delivery)
                self.capacity.release(child)
                status.update(state="blocked", reason=delivery["reason"])
            documents[key] = delivery
            status["merged"] = None
            if (
                delivery
                and delivery["state"] == "ready_for_acceptance"
                and status["state"] != "blocked"
            ):
                try:
                    # Readiness is durable even if an older dispatcher stopped before
                    # updating the capacity row. Recover that boundary before drift checks.
                    self.capacity.hold_ready(child)
                    status["merged"] = self.merged(child, delivery, base)
                    status.update(
                        state="merged" if status["merged"] else "awaiting_merge", reason=None
                    )
                    if not status["merged"]:
                        self.capacity.hold_ready(child)
                except AncestryPending as exc:
                    status.update(state="waiting_prerequisite_evidence", reason=str(exc))
                except PolicyError as exc:
                    failures[key] = str(exc)
        if github.ref(self.config["base_branch"]) != base:
            doc["state"] = "waiting_base_refresh"
            self.defer_waiters(root, doc)
            return self.save(root, doc)
        for key, reason in failures.items():
            doc["nodes"][key].update(state="blocked", reason=reason, merged=None)
        for status in doc["nodes"].values():
            if status["merged"]:
                self.capacity.release(status["run_id"])
        if not all(n["merged"] for n in doc["nodes"].values()):
            self.capacity.defer(root, root)
            if self.capacity.get(root)["state"] == "active":
                doc.update(
                    state="blocked", reason="Integration prerequisites changed during active work"
                )
                self.settle(root, doc)
                return self.save(root, doc)
        nodes = doc["graph"]["tickets"]
        order = nodes[doc["cursor"] :] + nodes[: doc["cursor"]]
        doc["cursor"] = (doc["cursor"] + 1) % len(nodes)
        policy = self.config.get("epic", {})
        for node in order:
            status = doc["nodes"][node["key"]]
            child, delivery = status["run_id"], documents[node["key"]]
            if status["merged"] or status["state"] == "awaiting_merge":
                continue
            if (delivery and delivery["state"] in {"failed", "blocked"}) or status[
                "state"
            ] == "blocked":
                self.driver(child).workers.drain(child)
                if delivery:
                    self.driver(child).account_usage(child, delivery)
                    if delivery["state"] in {"failed", "blocked"}:
                        status.update(state=delivery["state"], reason=delivery.get("reason"))
                self.capacity.release(child)
                continue
            if delivery and delivery["state"] == "ready_for_acceptance":
                self.capacity.hold_ready(child)
                continue
            claim = self.capacity.get(child)
            if claim["state"] != "active":
                dependencies = [doc["nodes"][d] for d in node["depends_on"]]
                if any(
                    d["state"] in {"failed", "blocked", "blocked_dependency"} for d in dependencies
                ):
                    status.update(state="blocked_dependency", reason="failed prerequisite")
                    self.capacity.defer(child, root)
                    continue
                if not all(d["merged"] for d in dependencies):
                    status.update(
                        state="queued", reason="prerequisite must be merged, not merely PR-ready"
                    )
                    self.capacity.defer(child, root)
                    continue
                if doc["paused"]:
                    status.update(reason="epic paused")
                    self.capacity.defer(child, root)
                    continue
                spent, reserved = self.budget(doc)
                if spent + reserved + self.config["max_total_tokens"] + policy.get(
                    "integration_token_reserve", self.config["max_total_tokens"]
                ) > policy.get(
                    "max_total_tokens", self.config["max_total_tokens"] * (len(nodes) + 1)
                ):
                    status.update(reason="epic token reservation exhausted")
                    self.capacity.defer(child, root)
                    continue
                self.capacity.activate(child, root)
                if not self.capacity.acquire(child, epic_owner=root):
                    status.update(reason="capacity or resource conflict")
                    continue
            spent, _ = self.budget(doc)
            if self.needs_worker(child, delivery) and spent >= policy.get(
                "max_total_tokens", self.config["max_total_tokens"] * (len(nodes) + 1)
            ):
                status.update(
                    state="blocked", reason="Actual epic token admission budget exhausted"
                )
                self.capacity.release(child)
                continue
            self.save(root, doc)
            self.journal.checkpoint({"kind": "tick", "run_id": root, "child": child})
            try:
                result = self.driver(child).step(child, epic_owner=root, expected_base=base)
                status.update(
                    state=result["state"], reason=result.get("reason") or result.get("action")
                )
            except CheckpointError:
                raise
            except PolicyError as exc:
                status.update(state="blocked", reason=str(exc))
                self.capacity.release(child)
            self.save(root, doc)
        if all(n["merged"] for n in doc["nodes"].values()):
            if not doc["paused"] or self.capacity.get(root)["state"] == "active":
                # Re-read observed usage after this tick; prior reservations are estimates.
                spent = doc["tokens"] + sum(
                    (self.driver(n["run_id"])._load(n["run_id"]) or {}).get("tokens", 0)
                    for n in doc["nodes"].values()
                )
                return self.integrate(root, doc, github, base, spent)
        doc["state"] = (
            "paused"
            if doc["paused"]
            else "blocked_children"
            if any(
                n["state"] in {"failed", "blocked", "blocked_dependency"}
                for n in doc["nodes"].values()
            )
            else "running"
        )
        return self.save(root, doc)

    def integrate(self, root, doc, github, head, spent):
        if doc["integration_head"] not in {None, head}:
            doc.update(state="blocked", reason="Integration base changed; explicit replan required")
            self.settle(root, doc)
            return self.save(root, doc)
        if github.ref(self.config["base_branch"]) != head:
            doc["state"] = "waiting_base_refresh"
            return self.save(root, doc)
        stage = "validating" if not doc["validation"] else "reviewing"
        if not doc["review"]:
            self.capacity.activate(root, root)
            if not self.capacity.acquire(root, epic_owner=root):
                doc["state"] = "waiting_integration_capacity"
                return self.save(root, doc)
            key = "epic:" + head + ":" + stage
            existing = self.journal.connection.execute(
                "SELECT id FROM runs WHERE source_id=?", (root + ":" + key,)
            ).fetchone()
            policy = self.config.get("epic", {})
            if self.job_needs_admission(existing[0] if existing else None) and (
                doc["tokens"]
                >= policy.get("integration_token_reserve", self.config["max_total_tokens"])
                or spent
                >= policy.get(
                    "max_total_tokens", self.config["max_total_tokens"] * (len(doc["nodes"]) + 1)
                )
            ):
                doc.update(
                    state="blocked",
                    reason="Total epic or integration token admission budget exhausted",
                )
                self.settle(root, doc)
                return self.save(root, doc)
            if github.ref(self.config["base_branch"]) != head:
                self.capacity.release(root)
                doc["state"] = "waiting_base_refresh"
                return self.save(root, doc)
            # Queueing holds no revision-specific work. Pin only after admission,
            # and preserve this SHA once a native effect might have started.
            doc["integration_head"] = head
            self.save(root, doc)
            self.journal.checkpoint({"kind": "tick", "run_id": root, "head": head})
            jobs = NativeJobs(
                self.config,
                self.journal,
                self.http,
                self.artifacts,
                **({"clock": self.clock} if self.clock else {}),
            )
            context = {
                "plan": {"graph": doc["graph"], "merged": doc["nodes"]},
                "candidate": {"head": head},
                "validation": doc["validation"],
                "feedback": None,
            }
            try:
                result = jobs.step(root, key, stage, head, doc["base"], context)
            except CheckpointError:
                raise
            except PolicyError as exc:
                doc.update(state="blocked", reason=str(exc))
                self.settle(root, doc)
                return self.save(root, doc)
            doc["state"] = "integrating_" + stage
            if result:
                doc["tokens"] += result["observed_tokens"]
                if result["verdict"] != "pass":
                    doc.update(state="blocked", reason="Combined epic validation/review failed")
                    self.settle(root, doc)
                else:
                    doc["validation" if stage == "validating" else "review"] = result
            return self.save(root, doc)
        # Existing ready evidence is rechecked without entering the dispatch queue.
        if doc["review"]["session_id"] == doc["validation"]["session_id"]:
            raise PolicyError("Epic integration review is not independent")
        checks, statuses = commit_evidence(github, head)
        ci = inspect_ci(checks, statuses, head=head, required=self.config["required_checks"])
        if github.ref(self.config["base_branch"]) != head:
            doc.update(state="blocked", reason="Base moved while collecting integration evidence")
            self.settle(root, doc)
            return self.save(root, doc)
        doc["integration_ci"] = {
            "head": head,
            "state": ci["state"],
            "evidence": self.artifacts.put({"checks": checks, "statuses": statuses}),
        }
        now = self.clock() if self.clock else time.time()
        doc.setdefault("integration_ci_started_at", now)
        doc["state"] = (
            "ready_for_acceptance"
            if ci["state"] == "green"
            else "waiting_integration_ci"
            if ci["state"] == "waiting"
            else "blocked"
        )
        if ci["state"] == "waiting" and now - doc["integration_ci_started_at"] > self.config.get(
            "ci_timeout_seconds", 900
        ):
            doc.update(state="blocked", reason="Epic integration CI deadline exceeded")
        # Finished native jobs need no work/queue claim while CI is observed.
        self.capacity.release(root)
        return self.save(root, doc)
