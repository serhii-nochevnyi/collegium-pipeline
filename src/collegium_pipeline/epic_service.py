"""Fixed installed-bundle diagnostic; production epic authority remains disabled."""

import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict

from .config import config_digest
from .delivery import serial_lock
from .domain import PolicyError, Task, digest
from .epic_cloud import summary
from .epics import Epics
from .native_broker import NativeGithubApp, ScriptTransport
from .recovery import (
    Checkpoints,
    ExternalRecoveryRequired,
    WriteAhead,
    mac,
    reconcile_existing,
    recovery_profiles,
)
from .store import Journal


def fixtures(revision=2):
    values = {
        "A": (
            "import unittest\n\nVALUE_A = 19\n\nclass ServiceATests(unittest.TestCase):\n"
            "    def test_a(self):\n        self.assertEqual(VALUE_A, 19)\n"
        ),
        "B": (
            "import unittest\n\nVALUE_B = 37\n\nclass ServiceBTests(unittest.TestCase):\n"
            "    def test_b(self):\n        self.assertEqual(VALUE_B, 37)\n"
        ),
        "C": (
            "import unittest\nfrom test_epic_service_a import VALUE_A\n"
            "from test_epic_service_b import VALUE_B\n\nclass ServiceCTests(unittest.TestCase):\n"
            "    def test_combined(self):\n        self.assertEqual(VALUE_A + VALUE_B, 56)\n"
        ),
    }

    if revision == 1:
        return values
    return {
        k: v.replace("import unittest\nfrom", "import unittest\n\nfrom").replace(
            "\n\nclass ", "\n\n\nclass "
        )
        for k, v in values.items()
    }


def paths():
    return [f"tests/test_epic_service_{key.lower()}.py" for key in "ABC"]


def authorize_rpc(config, journal, child, request):
    spec = config["epic_service_test"]
    key = os.environ.get("PIPELINE_CONTROL_KEY")
    if not key or time.time() > spec["expires_at"]:
        raise PolicyError("Service mutation authorization is absent or expired")
    row = journal.connection.execute(
        "SELECT n.ticket_key,e.document FROM epic_nodes n JOIN epics e ON e.run_id=n.epic_id "
        "WHERE n.run_id=?",
        (child,),
    ).fetchone()
    if (
        not row
        or row[0] not in {"A", "B", "C"}
        or journal.get(child)["config_digest"] != config_digest(config)
    ):
        raise PolicyError("Service mutation is not an admitted fixed epic child")
    doc = json.loads(row[1])
    if doc["graph_digest"] != digest(graph(config)):
        raise PolicyError("Service graph authority differs")
    body = {
        "purpose": "rpc",
        "suite_id": spec["suite_id"],
        "task_key": row[0],
        "child_id": child,
        "graph_digest": doc["graph_digest"],
        "request_digest": digest(request),
    }
    return {"body": body, "mac": mac(body, key)}


def ready_receipts(engine, root, key):
    doc = engine.load(root)
    receipts = {}
    for name, node in doc["nodes"].items():
        delivery = engine.driver(node["run_id"])._load(node["run_id"])
        if (
            not delivery
            or delivery["state"] != "ready_for_acceptance"
            or not delivery.get("ci_green")
        ):
            continue
        validation, review = delivery["validation"], delivery["review"]
        if (
            any(
                r["revision"]["head"] != delivery["head"] or r["verdict"] != "pass"
                for r in (validation, review)
            )
            or validation["session_id"] == review["session_id"]
        ):
            raise PolicyError("Service ready evidence differs from accepted independent revisions")
        body = {
            "purpose": "ready",
            "suite_id": engine.config["epic_service_test"]["suite_id"],
            "task_key": name,
            "child_id": node["run_id"],
            "graph_digest": doc["graph_digest"],
            "pr": delivery["pr"],
            "head": delivery["head"],
            "branch": delivery["branch"],
            "base_branch": engine.config["base_branch"],
            "validation_session": validation["session_id"],
            "review_session": review["session_id"],
        }
        receipts[name] = {"body": body, "mac": mac(body, key)}
    return receipts


def baseline(engine, root, key):
    config, doc = engine.config, engine.load(root)
    spec = config["epic_service_test"]
    github = engine.github_factory(root)
    if time.time() > spec["expires_at"] or github.ref("main") != spec["main_sha"]:
        raise PolicyError("Service authority expired or main changed")
    tip = github.ref(config["base_branch"])
    verified = tip
    if doc["base"] is None and tip != spec["baseline"]:
        raise PolicyError("Initial service base differs from the pinned seed")
    seen, merges = set(), []
    while tip != spec["baseline"]:
        if len(seen) >= 3:
            raise PolicyError("Service base is not the seed or authorized fixture integration")
        commit = github.read("/git/commits/" + tip)
        lines = [
            s
            for s in commit.get("message", "").splitlines()
            if s.startswith("Collegium-Service-Merge: ")
        ]
        if len(lines) != 1 or len(commit.get("parents", [])) != 2:
            raise PolicyError("Service base contains an unapproved commit")
        proof = json.loads(lines[0].split(": ", 1)[1])
        body = proof["body"]
        name = body.get("task_key")
        if (
            not hmac.compare_digest(proof.get("mac", ""), mac(body, key))
            or body.get("purpose") != "ready"
            or body.get("suite_id") != spec["suite_id"]
            or body.get("graph_digest") != doc["graph_digest"]
            or name not in doc["nodes"]
            or name in seen
            or body.get("child_id") != doc["nodes"][name]["run_id"]
            or commit["parents"][1]["sha"] != body.get("head")
        ):
            raise PolicyError("Service base merge proof differs from the admitted graph")
        seen.add(name)
        merges.append((name, commit))
        tip = commit["parents"][0]["sha"]
    if merges:

        def tree(sha):
            data = github.read("/git/trees/" + sha + "?recursive=1")
            if data.get("truncated"):
                raise PolicyError("Service tree evidence is incomplete")
            return {
                r["path"]: (r["mode"], r["type"], r["sha"])
                for r in data["tree"]
                if r["type"] != "tree"
            }

        original = github.read("/git/commits/" + spec["baseline"])
        expected = tree(original["tree"]["sha"])
        applied = set()
        for name, commit in reversed(merges):
            if name == "C" and not {"A", "B"} <= applied:
                raise PolicyError("Service integration history violated A/B before C")
            applied.add(name)
            content = fixtures(spec.get("revision", 1))[name].encode()
            sha = hashlib.sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content, usedforsecurity=False
            ).hexdigest()
            expected["tests/test_epic_service_" + name.lower() + ".py"] = ("100644", "blob", sha)
            if tree(commit["tree"]["sha"]) != expected:
                raise PolicyError("Signed service merge changed unrelated tree contents")
    return verified


def observe_overlap(http, workers):
    if len(workers) != 2 or len({w["session_id"] for w in workers}) != 2:
        raise PolicyError("Overlap requires exactly distinct A/B session identities")

    def get(worker):
        row, _ = http.request(
            "GET", "/session/" + worker["session_id"] + "/turns/" + worker["turn_id"]
        )
        if row.get("id") != worker["turn_id"] or row.get("session_id") != worker["session_id"]:
            raise PolicyError("Overlap observation has a different turn identity")
        return {k: row.get(k) for k in ("id", "session_id", "status", "started_at", "finished_at")}

    for _ in range(20):
        a, b, again = get(workers[0]), get(workers[1]), get(workers[0])
        if all(
            r["status"] == "running" and r["started_at"] and not r["finished_at"]
            for r in (a, b, again)
        ):
            return {"observed_at": time.time(), "a_before": a, "b": b, "a_after": again}
        if any(r["status"] in {"completed", "failed", "cancelled"} for r in (a, b, again)):
            raise PolicyError("A/B did not establish a real running overlap")
        time.sleep(1)
    raise PolicyError("A/B running overlap was not observed within the bounded probe")


def graph(config):
    suite = config["epic_service_test"]["suite_id"]
    revision = config["epic_service_test"].get("revision", 1)
    prefix = f"epic-service:{suite}" + (f":v{revision}" if revision > 1 else "")

    def task(key, requirements):
        return asdict(
            Task(
                "text",
                f"{prefix}:{key}",
                config["repository"],
                f"SERVICE ONLY epic {key}",
                requirements,
            )
        )

    return {
        "schema_version": "epic/v1",
        "version": 1,
        "strategy": "direct_to_base",
        "epic": task("ROOT", "Fixed live diagnostic A/B -> C; no Jira or product pilot."),
        "tickets": [
            {
                "key": key,
                "task": task(
                    key,
                    "Create exactly this one fixture, byte-for-byte. No other file changes. "
                    "Preserve the literal text in payload.changes. "
                    "All existing quality gates apply.\n" + paths()[i] + "\n" + content,
                ),
                "depends_on": [] if key in "AB" else ["A", "B"],
                "paths": [paths()[i]],
                "resources": [],
            }
            for i, (key, content) in enumerate(fixtures(revision).items())
        ],
    }


def inspect(engine, root):
    doc = engine.load(root)
    deliveries, workers, commits, prs = {}, [], [], []
    roots = [root, *[n["run_id"] for n in doc["nodes"].values()]]
    for owner in roots:
        delivery = engine.driver(owner)._load(owner) if owner != root else None
        if delivery:
            deliveries[owner] = {
                k: delivery.get(k)
                for k in ("state", "head", "base", "branch", "pr", "tokens", "used_jobs")
            }
        for e in engine.journal.events(owner):
            if e["kind"] == "broker_done":
                if e["data"]["key"].startswith("commit:"):
                    commits.append({"owner": owner, **e["data"]})
                elif e["data"]["key"] == "pr":
                    prs.append({"owner": owner, **e["data"]})
        jobs = engine.journal.connection.execute(
            "SELECT id, source_id, state, pending_intent FROM runs WHERE source_id LIKE ?",
            (owner + ":%",),
        ).fetchall()
        for job in jobs:
            done = [
                e["data"]
                for e in engine.journal.events(job["id"])
                if e["kind"] == "worker_completed"
            ]
            accepted = engine.artifacts.get(done[-1]["artifact_digest"]) if done else {}
            for e in engine.journal.events(job["id"]):
                if e["kind"] == "launched":
                    workers.append(
                        {
                            "owner": owner,
                            "job": job["id"],
                            "job_key": job["source_id"],
                            "state": job["state"],
                            "accepted": bool(done),
                            "runtime_evidence": accepted.get("runtime_evidence"),
                            "observed_tokens": accepted.get("observed_tokens"),
                            "revision": accepted.get("revision"),
                            **e["data"],
                        }
                    )
    return {
        **summary({"run_id": root, **doc}),
        "deliveries": deliveries,
        "workers": workers,
        "commit_receipts": commits,
        "pr_receipts": prs,
        "config_digest": config_digest(engine.config),
        "pilot_selected": False,
        "controller_host": "Collegium installed bundle",
        "checkpoint_receipts": [
            json.loads(row[0])
            for row in engine.journal.connection.execute(
                "SELECT data FROM events WHERE kind='checkpoint_recovered' ORDER BY sequence"
            )
        ],
    }


def legacy_roots(journal, legacy):
    if legacy is None:
        return []
    if not journal.connection.execute("SELECT 1 FROM sqlite_master WHERE name='epics'").fetchone():
        return []
    return [
        row[0]
        for row in journal.connection.execute(
            "SELECT e.run_id FROM epics e JOIN runs r ON r.id=e.run_id WHERE r.config_digest=?",
            (config_digest(legacy),),
        )
    ]


def retire_legacy(journal, legacy, http, state):
    if legacy is None:
        raise PolicyError("No archived fixed service profile to retire")
    engine = Epics(
        legacy,
        journal,
        lambda root: NativeGithubApp(legacy, http, journal, root),
        http,
        state / "artifacts",
    )
    pending = []
    roots = legacy_roots(journal, legacy)
    for root in roots:
        doc = engine.load(root)
        if doc["graph_digest"] != digest(graph(legacy)):
            raise PolicyError("Archive does not match the fixed rejected fixture graph")
        for node in doc["nodes"].values():
            child = node["run_id"]
            driver = engine.driver(child)
            pending.extend(driver.workers.drain(child)["pending"])
            delivery = driver._load(child)
            if delivery:
                driver.account_usage(child, delivery)
                delivery.update(
                    state="blocked", reason="Rejected fixture formatting; explicit new revision"
                )
                driver._save(child, delivery)
            if not engine.capacity.release(child):
                pending.append(child)
            node.update(state="blocked", reason="Explicit rejected-fixture retirement")
        doc.update(
            state="blocked",
            paused=True,
            reason="Retired fixture revision1 after terminal drain",
            fixture_retired=not pending,
        )
        engine.save(root, doc)
        if not engine.capacity.release(root):
            pending.append(root)
        doc["fixture_retired"] = not pending
        engine.save(root, doc)
        journal.checkpoint({"kind": "tick", "run_id": root})
    return {
        "state": "retiring" if pending else "retired",
        "retired_roots": roots,
        "pending": pending,
        "pilot_selected": False,
        "workers": [],
        "nodes": {},
    }


def run(event, state, config, environ, http, hooks, *, legacy=None):
    guard = {}
    try:
        return _run(event, state, config, environ, http, hooks, guard, legacy)
    finally:
        if not guard.get("fenced") and event.get("mode") not in {"preflight", "inspect"}:
            try:
                identity = hooks["cloud_identity"](environ)
            except PolicyError:
                identity = None
            if identity:
                target = (
                    state
                    / "no-dispatch"
                    / (identity["run_id"] + "-" + identity["attempt_id"] + ".json")
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                hooks["save_receipt"](target, identity)


def _run(event, state, config, environ, http, hooks, guard, legacy):
    if set(event) != {"action", "mode"} or event.get("mode") not in {
        "preflight",
        "run",
        "inspect",
        "crash",
        "retire",
    }:
        raise PolicyError("Fixed epic service mode accepts no arbitrary event fields")
    if config["execution_enabled"] or config["broker_enabled"]:
        raise PolicyError("Service diagnostic requires disabled installed production authority")
    spec = config["epic_service_test"]
    if (
        config["base_branch"] != "collegium/" + spec["suite_id"]
        or config["allowed_paths"] != paths()
    ):
        raise PolicyError("Service diagnostic leaves its isolated branch or fixed fixture ceiling")
    identity = hooks["cloud_identity"](environ)
    if identity["automation_id"] != config["recovery_store"]["owner"]:
        raise PolicyError("Service diagnostic belongs to another controller")
    key = environ.get("PIPELINE_CONTROL_KEY")
    if not key or http is None:
        raise PolicyError("Service diagnostic requires its Vault control key")
    if event["mode"] == "preflight":
        ScriptTransport(config, http, None, None).scope()
        print(
            "COLLEGIUM_EPIC_SERVICE_PREFLIGHT="
            + json.dumps(
                {
                    "base_branch": config["base_branch"],
                    "allowed_paths": paths(),
                    "production_enabled": False,
                    "pilot_selected": False,
                    "agent_started": False,
                }
            ),
            flush=True,
        )
        return 0
    scoped = {**config, "execution_enabled": True, "broker_enabled": True}
    archived = {**legacy, "execution_enabled": True, "broker_enabled": True} if legacy else None
    profiles = recovery_profiles(scoped, archived) if archived else None
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    fence = None
    try:
        try:
            fence, receipt = hooks["cloud_fence"](event, state, environ, http, epic_service=True)
        except ExternalRecoveryRequired:
            hooks["reconcile_controller"](scoped, state, http, key, profiles=profiles)
            fence, receipt = hooks["cloud_fence"](event, state, environ, http, epic_service=True)
        guard["fenced"] = True
        with serial_lock(state / "journal.sqlite3"):
            journal = Journal(state / "journal.sqlite3")
            try:
                writer = archived if event["mode"] == "retire" and archived else scoped
                journal.before_effect = WriteAhead(
                    writer,
                    journal,
                    state / "artifacts",
                    Checkpoints(writer, http, key),
                    identity,
                    profiles=profiles,
                ).save
                if event["mode"] == "retire":
                    reconcile_existing(
                        scoped,
                        journal,
                        http,
                        NativeGithubApp(scoped, http, journal, None),
                        profiles=profiles,
                    )
                    result = retire_legacy(journal, archived, http, state)
                    print("COLLEGIUM_EPIC_SERVICE_RESULT=" + json.dumps(result), flush=True)
                    return 0
                for previous in legacy_roots(journal, archived):
                    prior = journal.connection.execute(
                        "SELECT document FROM epics WHERE run_id=?", (previous,)
                    ).fetchone()
                    if not json.loads(prior[0]).get("fixture_retired"):
                        raise PolicyError(
                            "Retire the rejected fixed service revision before new work"
                        )
                engine = Epics(
                    scoped,
                    journal,
                    lambda root: NativeGithubApp(scoped, http, journal, root),
                    http,
                    state / "artifacts",
                )
                root = engine.admit(graph(scoped))["run_id"]
                verified_base = baseline(engine, root, key)
                if event["mode"] == "inspect":
                    print(
                        "COLLEGIUM_EPIC_SERVICE_RESULT="
                        + json.dumps(
                            {
                                **inspect(engine, root),
                                "ready_receipts": ready_receipts(engine, root, key),
                            }
                        ),
                        flush=True,
                    )
                    return 0
                reconcile_existing(
                    scoped,
                    journal,
                    http,
                    NativeGithubApp(scoped, http, journal, root),
                    profiles=profiles,
                )
                if event["mode"] == "crash" and inspect(engine, root)["workers"]:
                    raise PolicyError("Crash probe already started; resume original run")
                journal.checkpoint({"kind": "tick", "run_id": root})
                engine.step(root, expected_base=verified_base)
                result = inspect(engine, root)
                result["ready_receipts"] = ready_receipts(engine, root, key)
                if event["mode"] == "crash":
                    if len(result["workers"]) != 2:
                        raise PolicyError("Crash probe requires exactly the original A/B launches")
                    result["overlap"] = observe_overlap(http, result["workers"])
                    # Deliberately withhold post-launch checkpoint/receipt. Operator cancels
                    # this attempt; external checkpoint contains the last pre-prompt intent.
                    print("COLLEGIUM_EPIC_SERVICE_CRASH_READY=" + json.dumps(result), flush=True)
                    time.sleep(180)
                    raise PolicyError("Crash hold expired; expected explicit operator cancellation")
                journal.checkpoint({"kind": "tick", "run_id": root})
                print("COLLEGIUM_EPIC_SERVICE_RESULT=" + json.dumps(result), flush=True)
            finally:
                journal.close()
    finally:
        if fence is not None:
            hooks["save_receipt"](fence, receipt)
    return 0
