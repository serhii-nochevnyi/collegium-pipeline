"""Resumable single-task delivery and bounded CI repair; never merges."""

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .artifacts import Artifacts
from .broker import PRBroker, changes_checked
from .ci import inspect_ci
from .config import config_digest
from .delivery_workers import CheckoutProtocolError, NativeJobs, validation_commands
from .domain import PolicyError, Task, digest, select_model
from .effort import runtime_evidence, tool_result
from .quality import verify_pr
from .service_test import candidate_gate, failure_evidence


@contextmanager
def serial_lock(journal_path):
    path = Path(str(journal_path) + ".delivery.lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PolicyError("Another local delivery coordinator holds this journal") from exc
        yield
    finally:
        os.close(fd)


class Delivery:
    def __init__(self, config, journal, github, http, artifacts, *, workers=None, clock=time.time):
        self.config, self.journal, self.github, self.clock = config, journal, github, clock
        self.artifacts = Artifacts(artifacts)
        self.broker = PRBroker(config, journal, github)
        self.workers = workers or NativeJobs(config, journal, http, self.artifacts, clock=clock)
        journal.connection.execute(
            "CREATE TABLE IF NOT EXISTS deliveries("
            "run_id TEXT PRIMARY KEY REFERENCES runs(id), document TEXT NOT NULL)"
        )

    def _save(self, run_id, doc):
        with self.journal.transaction():
            self.journal.connection.execute(
                "INSERT INTO deliveries VALUES(?,?) ON CONFLICT(run_id) "
                "DO UPDATE SET document=excluded.document",
                (run_id, json.dumps(doc, sort_keys=True)),
            )
            self.journal._event(
                run_id,
                "delivery_tick",
                {"state": doc["state"], "cycle": doc["cycle"], "head": doc["head"]},
            )
        return {"run_id": run_id, **doc}

    def _load(self, run_id):
        row = self.journal.connection.execute(
            "SELECT document FROM deliveries WHERE run_id=?", (run_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def reconfigure_validation(self, run_id, previous_config, reason):
        """Explicit operator correction after a definitively completed invalid validation.

        Preserve the admission, PR, candidate and old packet. Only validation argv and
        its token allowance may change; uncertain launches can never enter this path.
        The caller holds serial_lock, and supplies the new, validated configuration.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError("Validation reconfiguration needs an explicit reason")
        changed = {
            k
            for k in self.config.keys() | previous_config.keys()
            if self.config.get(k) != previous_config.get(k)
        }
        allowed = {"validation_commands", "repair_validation_commands", "max_total_tokens"}
        doc, run = self._load(run_id), self.journal.get(run_id)
        if (
            not changed
            or changed - allowed
            or run["config_digest"] != config_digest(previous_config)
            or run["state"] != "planning"
            or run["pending_intent"]
            or not doc
            or doc["state"] != "validating"
            or doc.get("protocol_failures", 0) >= self.config["max_repair_attempts"]
            or validation_commands(previous_config, repaired=bool(doc.get("service_red")))
            == validation_commands(self.config, repaired=bool(doc.get("service_red")))
        ):
            raise PolicyError("Only a recorded validation failure permits this correction")
        key = f"{doc['cycle']}:validating:{doc['plan_attempt']}"
        rows = self.journal.connection.execute(
            "SELECT id FROM runs WHERE source_id=? AND repository=?",
            (run_id + ":" + key, self.config["repository"]),
        ).fetchall()
        if len(rows) != 1 or key in doc["used_jobs"]:
            raise PolicyError("Validation has no single unaccepted worker")
        job = rows[0]["id"]
        child = self.journal.get(job)
        events = self.journal.events(job)
        observations = [e for e in events if e["kind"] == "delivery_observation"]
        launches = [e for e in events if e["kind"] == "launched"]
        if child["state"] != "planning" or len(launches) != 1 or not observations:
            raise PolicyError("Validation launch is not definitively observable")
        observed = self.artifacts.get(observations[-1]["data"]["artifact_digest"])
        if observed["turn"]["status"] != "completed" or observed["turn"].get("error"):
            raise PolicyError("An unfinished or failed turn cannot be replaced")
        started = next(e for e in events if e["kind"] == "job_started")
        packet = self.artifacts.get(started["data"]["packet_digest"])
        binding = NativeJobs(previous_config, self.journal, None, self.artifacts).binding(
            select_model("executor", profile=previous_config.get("model_policy", "codex"))
        )
        runtime_evidence(
            observed, binding, **{k: launches[0]["data"][k] for k in ("session_id", "turn_id")}
        )
        _, checked = tool_result(
            observed, packet["checkout_command"], index=1, harness=binding.harness
        )
        markers = [
            s for s in checked.get("output", "").splitlines() if s.startswith("COLLEGIUM_CHECKOUT=")
        ]
        if len(markers) != 1:
            raise PolicyError("Original validation lacks pinned command evidence")
        checkout = json.loads(markers[0].split("=", 1)[1])
        commands = checkout.get("results", [])
        if (
            checkout.get("head") != doc["head"]
            or [r.get("argv") for r in commands]
            != validation_commands(previous_config, repaired=bool(doc.get("service_red")))
            or not commands
            or any(type(r.get("exit_code")) is not int for r in commands)
            or not any(r["exit_code"] != 0 for r in commands)
        ):
            raise PolicyError("Only an actual nonzero validation command can be corrected")
        idle = [e for e in observed["events"] if e.get("type") == "session.status_idle"]
        if not idle:
            raise PolicyError("Rejected validation usage is not settled")
        tokens = sum(
            v
            for k, v in idle[-1].get("usage", {}).items()
            if k.endswith("tokens") and type(v) is int and v >= 0
        )
        doc["tokens"] += tokens
        doc["used_jobs"].append(key)
        doc["protocol_failures"] = doc.get("protocol_failures", 0) + 1
        doc["plan_attempt"] += 1
        doc.update(
            validation=None,
            review=None,
            feedback={
                "kind": "validation_reconfigured",
                "reason": reason,
                "previous_commands": commands,
            },
        )
        receipt = {
            "reason": reason,
            "job": job,
            "key": key,
            "head": doc["head"],
            "observation_digest": observations[-1]["data"]["artifact_digest"],
            "rejected_tokens": tokens,
            "previous_config": self.artifacts.put(previous_config),
            "new_config": self.artifacts.put(self.config),
            "previous_config_digest": config_digest(previous_config),
            "new_config_digest": config_digest(self.config),
        }
        with self.journal.transaction():
            current = self.journal.get(run_id)
            if current["version"] != run["version"] or self.journal.get(job) != child:
                raise PolicyError("Validation correction raced another coordinator")
            self.journal.connection.execute(
                "UPDATE runs SET state='failed',pending_intent=NULL,version=version+1 WHERE id=?",
                (job,),
            )
            self.journal._event(job, "validation_rejected", receipt)
            self.journal.connection.execute(
                "UPDATE runs SET config_digest=?,version=version+1 WHERE id=?",
                (config_digest(self.config), run_id),
            )
            self.journal.connection.execute(
                "UPDATE deliveries SET document=? WHERE run_id=?", (json.dumps(doc), run_id)
            )
            self.journal._event(run_id, "delivery_validation_reconfigured", receipt)
        return {"run_id": run_id, **doc}

    def _worker(self, run_id, doc, stage, selection=None):
        key = f"{doc['cycle']}:{stage}:{doc['plan_attempt']}"
        if key not in doc["job_keys"]:
            if len(doc["job_keys"]) >= self.config.get("max_worker_jobs", 24):
                raise PolicyError("Delivery worker-job budget exhausted")
            if doc["tokens"] >= self.config.get("max_total_tokens", 100000):
                raise PolicyError("Delivery token admission budget exhausted")
            doc["job_keys"].append(key)
            self._save(run_id, doc)
        context = {k: doc[k] for k in ("plan", "candidate", "validation", "feedback")}
        if self.config.get("service_test"):
            context["service_red"] = doc.get("service_red")
        result = self.workers.step(run_id, key, stage, doc["head"], doc["base"], context, selection)
        if result is None:
            return None
        if key not in doc["used_jobs"]:
            doc["tokens"] += result["observed_tokens"]
            doc["used_jobs"].append(key)
        self.journal.record(
            run_id,
            "delivery_worker_receipt",
            {"key": key, "artifact_digest": self.artifacts.put(result)},
        )
        return result

    def _repair(self, run_id, doc, feedback, fingerprint):
        if self.config.get("service_test") and not doc.get("service_red"):
            doc.update(
                state="blocked",
                reason="Service repair requires an actual initial PR CI failure",
                feedback=feedback,
            )
            return
        if doc["repairs"] >= self.config["max_repair_attempts"]:
            doc.update(state="failed", reason="Repair attempt limit exhausted", feedback=feedback)
            return
        doc["repairs"] += 1
        doc["same_cause"] = (
            doc["same_cause"] + 1 if doc["failure_fingerprint"] == fingerprint else 0
        )
        doc.update(
            failure_fingerprint=fingerprint,
            feedback=feedback,
            state="fixing",
            cycle=doc["cycle"] + 1,
        )
        # No worker may mutate the PR; convert to draft before publishing repaired code.
        if doc.get("pr") and self.config.get("repair_pr_mode", "draft") == "draft":
            pr = doc["pr"]
            self.broker.draft(run_id, pr["number"], pr["node_id"], draft=True, cycle=doc["cycle"])

    def step(self, run_id):
        config = self.config
        run = self.journal.get(run_id)
        if (
            config.get("execution_profile", "delivery") != "delivery"
            or config.get("execution_enabled") is not True
            or config.get("broker_enabled") is not True
        ):
            raise PolicyError("Delivery and its write broker must be explicitly enabled")
        if (
            run["config_digest"] != config_digest(config)
            or self.journal.events(run_id)[0]["data"].get("purpose", "delivery") != "delivery"
        ):
            raise PolicyError("Run configuration or purpose differs")
        if run["state"] != "planning" or run["pending_intent"]:
            raise PolicyError("Run belongs to a different stage controller")
        doc = self._load(run_id)
        if doc and doc["state"] in {"failed", "blocked"}:
            return {"run_id": run_id, **doc}
        if doc and doc["state"] == "ready_for_acceptance":
            doc["state"] = "waiting_ci"
        self.github.scope()
        base = self.github.ref(config["base_branch"])
        if not base:
            raise PolicyError("Configured base branch is unavailable")
        if doc is None:
            doc = {
                "state": "planning",
                "base": base,
                "head": base,
                "cycle": 0,
                "repairs": 0,
                "same_cause": 0,
                "failure_fingerprint": None,
                "plan_attempt": 0,
                "tokens": 0,
                "job_keys": [],
                "used_jobs": [],
                "started_at": self.clock(),
                "ci_started_at": None,
                "plan": None,
                "candidate": None,
                "validation": None,
                "review": None,
                "feedback": None,
                "pr": None,
                "branch": "collegium/" + run_id,
                "delivered": False,
            }
            self._save(run_id, doc)
        if base != doc["base"]:
            doc.update(
                state="blocked",
                reason="Base changed; explicit replan and fresh validation/review required",
            )
            return self._save(run_id, doc)
        if self.clock() - doc["started_at"] > config.get("max_delivery_seconds", 3600):
            self.workers.stop_root(run_id)
            # Do not abandon an active native turn and silently launch a replacement.
            doc.update(
                state="blocked",
                reason="Delivery deadline exceeded; inspect recorded child turns before resuming",
            )
            return self._save(run_id, doc)
        if doc["head"] != doc["base"] and self.github.ref(doc["branch"]) != doc["head"]:
            # A persisted commit intent can reconcile the sole outstanding update.
            if doc["state"] != "publishing":
                doc.update(state="blocked", reason="Run branch changed outside the controller")
                return self._save(run_id, doc)
        if doc.get("pr"):
            pr = self.github.read(f"/pulls/{doc['pr']['number']}")
            if (
                pr["state"] != "open"
                or pr["node_id"] != doc["pr"]["node_id"]
                or pr["base"]["sha"] != base
                or pr["base"]["repo"]["id"] != config["repository_id"]
                or pr["head"]["repo"]["id"] != config["repository_id"]
                or pr["head"]["ref"] != doc["branch"]
                or (doc["state"] != "publishing" and pr["head"]["sha"] != doc["head"])
            ):
                doc.update(state="blocked", reason="PR identity, scope or revision changed")
                return self._save(run_id, doc)
        stage = doc["state"]
        if stage in {
            "planning",
            "plan_review",
            "implementing",
            "validating",
            "reviewing",
            "fixing",
        }:
            selection = (
                select_model(
                    "fixer",
                    same_cause_failures=doc["same_cause"],
                    profile=config.get("model_policy", "codex"),
                )
                if stage == "fixing"
                else None
            )
            try:
                result = self._worker(run_id, doc, stage, selection)
            except CheckoutProtocolError as exc:
                count = doc.get("protocol_failures", 0) + 1
                doc.update(
                    protocol_failures=count,
                    feedback={
                        "kind": "checkout_protocol_rejected",
                        "reason": str(exc),
                        "instructions": (
                            "The previous completed worker changed or failed the pinned checkout. "
                            "Copy checkout_command VERBATIM as the second tool. Do not "
                            "regenerate, re-encode or edit its base64/data, repository or head. "
                            "The packet already contains the correct repository and SHA. This is "
                            "a bounded retry of a definitive failure, not permission to change "
                            "scope. "
                        ),
                    },
                )
                self.journal.record(
                    run_id,
                    "worker_protocol_rejected",
                    {"stage": stage, "count": count, "reason": str(exc)},
                )
                if count > config["max_repair_attempts"]:
                    doc.update(state="failed", reason="Checkout protocol retry limit exhausted")
                else:
                    doc["plan_attempt"] += 1
                return self._save(run_id, doc)
            if result is None:
                return {"run_id": run_id, **doc, "action": "waiting_worker"}
            if stage in {"plan_review", "reviewing"}:
                producer = doc["plan"] if stage == "plan_review" else doc["candidate"]
                if producer is None or producer["session_id"] == result["session_id"]:
                    raise PolicyError("Review is not independent")
            if result["verdict"] != "pass":
                if (
                    stage in {"planning", "plan_review"}
                    and doc["plan_attempt"] < config["max_repair_attempts"]
                ):
                    doc.update(
                        state="planning", plan_attempt=doc["plan_attempt"] + 1, feedback=result
                    )
                elif stage in {"validating", "reviewing"}:
                    self._repair(
                        run_id,
                        doc,
                        result,
                        digest({"stage": stage, "findings": result["blocking_findings"]}),
                    )
                else:
                    doc.update(
                        state="failed",
                        reason="Worker could not produce an acceptable candidate",
                        feedback=result,
                    )
            elif stage == "planning":
                doc.update(plan=result, state="plan_review")
            elif stage == "plan_review":
                doc.update(state="implementing")
            elif stage in {"implementing", "fixing"}:
                changes_checked(result["payload"].get("changes"), config["allowed_paths"])
                candidate_gate(config, doc, result["payload"]["changes"])
                doc.update(candidate=result, validation=None, review=None, state="publishing")
            elif stage == "validating":
                doc.update(validation=result, state="reviewing")
            elif stage == "reviewing":
                doc.update(
                    review=result,
                    state="opening_pr" if doc["pr"] is None else "readying_pr",
                    ci_started_at=self.clock(),
                )
        elif stage == "publishing":
            self.broker.branch(run_id, doc["base"])
            doc["head"] = self.broker.commit(
                run_id,
                doc["branch"],
                doc["head"],
                doc["candidate"]["payload"]["changes"],
                doc["cycle"],
            )
            if config.get("service_test") and doc["cycle"] == 0:
                doc["service_initial_head"] = doc["head"]
            doc.update(state="validating")
        elif stage == "opening_pr":
            doc["pr"] = self.broker.open_pr(
                run_id, doc["branch"], doc["head"], base, Task(**json.loads(run["task"])).title
            )
            doc.update(state="waiting_ci", ci_started_at=self.clock())
        elif stage == "readying_pr":
            pr = doc["pr"]
            if config.get("repair_pr_mode", "draft") == "draft":
                self.broker.draft(
                    run_id, pr["number"], pr["node_id"], draft=False, cycle=doc["cycle"]
                )
            doc.update(state="waiting_ci", ci_started_at=self.clock())
        elif stage == "waiting_ci":
            pr, checks, statuses = self.github.pr_evidence(doc["pr"]["number"])
            if pr["head"]["sha"] != doc["head"] or pr["base"]["sha"] != doc["base"]:
                raise PolicyError("PR changed during CI observation")
            ci = inspect_ci(checks, statuses, head=doc["head"], required=config["required_checks"])
            self.journal.record(
                run_id,
                "ci_observed",
                {
                    "artifact_digest": self.artifacts.put(
                        {"pr": pr, "checks": checks, "statuses": statuses}
                    ),
                    "state": ci["state"],
                    "head": doc["head"],
                },
            )
            if ci["state"] == "green":
                if config.get("service_test") and (
                    not doc.get("service_red")
                    or doc["service_red"]["pr_number"] != doc["pr"]["number"]
                    or doc["service_red"]["head"] != doc.get("service_initial_head")
                    or doc["head"] == doc.get("service_initial_head")
                    or doc["cycle"] < 1
                ):
                    doc.update(state="blocked", reason="Service test never proved red then repair")
                    return self._save(run_id, doc)
                if (
                    not doc["validation"]
                    or not doc["review"]
                    or doc["review"]["revision"]["head"] != doc["head"]
                    or doc["validation"]["revision"]["head"] != doc["head"]
                ):
                    raise PolicyError("Current revision lacks validation and review")
                if pr["draft"]:
                    if config.get("repair_pr_mode") == "keep_ready":
                        doc.update(
                            state="blocked",
                            reason="Owner made the PR draft; manual ready transition required",
                        )
                        return self._save(run_id, doc)
                    self.broker.draft(
                        run_id, pr["number"], pr["node_id"], draft=False, cycle=doc["cycle"]
                    )
                    return self._save(run_id, doc)
                if pr.get("mergeable") is False:
                    doc.update(state="blocked", reason="PR has merge conflicts")
                elif pr.get("mergeable") is True:
                    verify_pr(
                        pr, repository_id=config["repository_id"], head=doc["head"], base=base
                    )
                    doc.update(state="ready_for_acceptance", delivered=False, ci_green=True)
            elif ci["state"] == "red":
                if config.get("service_test") and doc["cycle"] == 0:
                    if doc["head"] != doc.get("service_initial_head"):
                        raise PolicyError("Service initial PR revision changed")
                    doc["service_red"] = failure_evidence(config, doc, checks, ci)
                    self.journal.record(run_id, "service_red_verified", doc["service_red"])
                    ci["service_assertion"] = doc["service_red"]
                self._repair(run_id, doc, ci, ci["fingerprint"])
            elif ci["state"] == "blocked":
                doc.update(
                    state="blocked",
                    reason="CI skipped, cancelled, stale or awaiting external action",
                    feedback=ci,
                )
            if doc["state"] == "waiting_ci" and self.clock() - doc["ci_started_at"] > config.get(
                "ci_timeout_seconds", 900
            ):
                doc.update(
                    state="blocked",
                    reason="CI deadline exceeded; pending/missing checks do not trigger fixes",
                )
        else:
            raise PolicyError("Unknown delivery state")
        return self._save(run_id, doc)

    def stop(self, run_id, reason):
        try:
            self.workers.stop_root(run_id)
        finally:
            doc = self._load(run_id)
            if doc and doc["state"] not in {"ready_for_acceptance", "failed", "blocked"}:
                doc.update(
                    state="blocked",
                    reason=reason + "; recorded child launches require reconciliation",
                )
                self._save(run_id, doc)
