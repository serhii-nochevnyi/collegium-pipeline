"""Durable local prototype journal. This is not the PostgreSQL production store."""

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from .domain import PolicyError, Task

STAGES = ("planning", "plan_review", "implementing", "validating", "reviewing", "waiting_ci")
TERMINAL = {"ready_for_acceptance", "failed", "cancelled"}


class Journal:
    def __init__(self, path: str | Path):
        self.before_effect = None
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        # Concurrent first-open journal-mode changes may return SQLITE_BUSY without
        # using SQLite's busy timeout. Retry only that initialization, never a task/effect.
        deadline = time.monotonic() + 10
        while True:
            try:
                self.connection.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as exc:
                code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
                if (
                    code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                    or time.monotonic() >= deadline
                ):
                    self.connection.close()
                    raise
                time.sleep(0.01)
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, repository TEXT NOT NULL, source TEXT NOT NULL,
                source_id TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL,
                task TEXT NOT NULL, config_digest TEXT NOT NULL, pending_intent TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS canonical_task ON runs
                (repository,source,source_id);
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                kind TEXT NOT NULL, data TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );
        """)

    def checkpoint(self, operation):
        if self.before_effect is not None:
            self.record(operation["run_id"], "effect_attempt", {"operation": operation})
            try:
                self.before_effect(operation)
            except Exception:
                # The actual external call follows this hook and was never reached.
                self.record(operation["run_id"], "effect_not_started", {"operation": operation})
                raise

    def effect_not_started(self, operation):
        events = [
            e
            for e in self.events(operation["run_id"])
            if e["kind"] in {"effect_attempt", "effect_not_started"}
            and e["data"]["operation"] == operation
        ]
        return bool(events and events[-1]["kind"] == "effect_not_started")

    def close(self):
        self.connection.close()

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def _event(self, run_id, kind, data):
        self.connection.execute(
            "INSERT INTO events(run_id,kind,data) VALUES(?,?,?)",
            (run_id, kind, json.dumps(data, sort_keys=True)),
        )

    def admit(self, task: Task, config_digest: str, *, purpose="delivery") -> str:
        if purpose not in {"delivery", "readiness", "calibration", "delivery_worker"}:
            raise PolicyError("Unknown run purpose")
        with self.transaction():
            existing = self.connection.execute(
                "SELECT * FROM runs WHERE repository=? AND source=? AND source_id=?",
                (task.repository, task.source, task.source_id),
            ).fetchone()
            encoded = json.dumps(asdict(task), sort_keys=True)
            if existing:
                if existing["task"] != encoded or existing["config_digest"] != config_digest:
                    raise PolicyError("Active task changed; explicit replan required")
                admitted = self.events(existing["id"])[0]["data"]
                if admitted.get("purpose", "delivery") != purpose:
                    raise PolicyError("Run purpose cannot change")
                return existing["id"]
            run_id = str(uuid4())
            self.connection.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,0,?,?,NULL)",
                (
                    run_id,
                    task.repository,
                    task.source,
                    task.source_id,
                    "planning",
                    encoded,
                    config_digest,
                ),
            )
            self._event(
                run_id,
                "admitted",
                {"acceptance_digest": task.acceptance_digest, "purpose": purpose},
            )
            return run_id

    def record(self, run_id: str, kind: str, data: dict):
        """Coordinator-owned observation; never used to bypass stage transitions."""
        with self.transaction():
            self.get(run_id)
            self._event(run_id, kind, data)

    def fail(self, run_id: str, version: int, reason: str):
        with self.transaction():
            run = self.get(run_id)
            if run["version"] != version or run["state"] not in STAGES:
                raise PolicyError("Cannot fail a stale or reconciling run")
            self.connection.execute(
                "UPDATE runs SET state='failed',version=version+1,pending_intent=NULL WHERE id=?",
                (run_id,),
            )
            self._event(run_id, "stage_failed", {"stage": run["state"], "reason": reason})

    def complete_readiness(self, run_id: str, version: int, evidence: dict):
        with self.transaction():
            run = self.get(run_id)
            if run["version"] != version or run["state"] != "waiting_ci" or run["pending_intent"]:
                raise PolicyError("Readiness stages have not finished")
            if self.events(run_id)[0]["data"].get("purpose") != "readiness":
                raise PolicyError("A delivery run cannot skip PR/CI acceptance")
            self.connection.execute(
                "UPDATE runs SET state='self_test_passed',version=version+1 WHERE id=?", (run_id,)
            )
            self._event(run_id, "readiness_passed", evidence)

    def complete_calibration(self, run_id: str, version: int, evidence: dict):
        with self.transaction():
            run = self.get(run_id)
            if run["version"] != version or run["state"] != "planning" or not run["pending_intent"]:
                raise PolicyError("Calibration has no active launch")
            if self.events(run_id)[0]["data"].get("purpose") != "calibration":
                raise PolicyError("A product run cannot be completed as a calibration")
            self.connection.execute(
                "UPDATE runs SET state='calibration_passed',version=version+1,"
                "pending_intent=NULL WHERE id=?",
                (run_id,),
            )
            self._event(run_id, "calibration_verified", evidence)

    def recheck_result(self, run_id: str, version: int, reason: str):
        """Re-observe a finished rejected result; never start a replacement agent."""
        with self.transaction():
            run = self.get(run_id)
            if run["state"] != "failed" or run["version"] != version or not reason.strip():
                raise PolicyError("Only a known failed result can be explicitly rechecked")
            events = self.events(run_id)
            rejected = [e for e in events if e["kind"] == "rejected_observation"]
            failed = [e for e in events if e["kind"] == "stage_failed"]
            launched = [e for e in events if e["kind"] == "launched"]
            if not rejected or not failed or not launched:
                raise PolicyError("No recorded observation is available for recheck")
            if not (launched[-1]["sequence"] < rejected[-1]["sequence"] < failed[-1]["sequence"]):
                raise PolicyError("The last launch does not have a rejected finished result")
            if rejected[-1]["data"]["reason"] != failed[-1]["data"]["reason"]:
                raise PolicyError("The failure is not the recorded result rejection")
            stage = failed[-1]["data"]["stage"]
            self.connection.execute(
                "UPDATE runs SET state=?,pending_intent=?,version=version+1 WHERE id=?",
                (stage, launched[-1]["data"]["intent"], run_id),
            )
            self._event(
                run_id,
                "observation_recheck",
                {"reason": reason, "observation": rejected[-1]["data"]["artifact_digest"]},
            )

    def get(self, run_id: str) -> dict:
        row = self.connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise PolicyError("Unknown run")
        return dict(row)

    def begin_dispatch(
        self, run_id: str, version: int, selection: dict, request_digest=None
    ) -> str:
        with self.transaction():
            run = self.get(run_id)
            if run["version"] != version or run["state"] not in STAGES or run["pending_intent"]:
                raise PolicyError("Stale dispatch or an unresolved launch already exists")
            intent = str(uuid4())
            self.connection.execute(
                "UPDATE runs SET pending_intent=?,version=version+1 WHERE id=?",
                (intent, run_id),
            )
            self._event(
                run_id,
                "dispatch_intent",
                {
                    "intent": intent,
                    "selection": selection,
                    "request_digest": request_digest,
                },
            )
            return intent

    def record_session(self, run_id: str, intent: str, session_id: str):
        if not session_id:
            raise PolicyError("Session identity is missing")
        with self.transaction():
            run = self.get(run_id)
            if run["pending_intent"] != intent or run["state"] not in STAGES:
                raise PolicyError("Session belongs to an inactive launch intent")
            if any(
                e["kind"] == "session_created" and e["data"]["intent"] == intent
                for e in self.events(run_id)
            ):
                raise PolicyError("Session already recorded")
            self._event(run_id, "session_created", {"intent": intent, "session_id": session_id})

    def record_launch(self, run_id: str, intent: str, session_id: str, turn_id: str):
        if not session_id or not turn_id:
            raise PolicyError("Launch identity is incomplete")
        with self.transaction():
            run = self.get(run_id)
            if run["pending_intent"] != intent or run["state"] not in STAGES:
                raise PolicyError("Launch belongs to an inactive intent")
            prior = self.events(run_id)
            if any(e["kind"] == "launched" and e["data"]["intent"] == intent for e in prior):
                raise PolicyError("Launch already recorded; reconcile existing identity")
            self._event(
                run_id,
                "launched",
                {"intent": intent, "session_id": session_id, "turn_id": turn_id, "at": time.time()},
            )

    def unknown_launch(self, run_id: str, intent: str):
        with self.transaction():
            if self.get(run_id)["pending_intent"] != intent:
                raise PolicyError("Launch intent changed")
            self.connection.execute(
                "UPDATE runs SET state='reconciling',version=version+1 WHERE id=?", (run_id,)
            )
            self._event(run_id, "unknown_launch", {"intent": intent})

    def advance(self, run_id: str, version: int, evidence: dict):
        """Only a coordinator that has validated evidence calls this internal method."""
        with self.transaction():
            run = self.get(run_id)
            if run["version"] != version or run["state"] not in STAGES:
                raise PolicyError("Stale or non-runnable run")
            if not run["pending_intent"] or not any(
                e["kind"] == "launched" and e["data"]["intent"] == run["pending_intent"]
                for e in self.events(run_id)
            ):
                raise PolicyError("Stage has no confirmed launch")
            index = STAGES.index(run["state"])
            target = STAGES[index + 1] if index + 1 < len(STAGES) else "ready_for_acceptance"
            self.connection.execute(
                "UPDATE runs SET state=?,version=version+1,pending_intent=NULL WHERE id=?",
                (target, run_id),
            )
            self._event(run_id, "stage_accepted", {"stage": run["state"], "evidence": evidence})

    def events(self, run_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT sequence,kind,data FROM events WHERE run_id=? ORDER BY sequence", (run_id,)
        )
        return [
            {"sequence": r["sequence"], "kind": r["kind"], "data": json.loads(r["data"])}
            for r in rows
        ]

    def complete_worker(self, run_id, version, evidence):
        with self.transaction():
            run = self.get(run_id)
            if (
                run["version"] != version
                or run["state"] != "planning"
                or self.events(run_id)[0]["data"].get("purpose") != "delivery_worker"
                or not any(e["kind"] == "launched" for e in self.events(run_id))
            ):
                raise PolicyError("Not a confirmed delivery-worker operation")
            self.connection.execute(
                "UPDATE runs SET state='worker_completed',version=version+1,"
                "pending_intent=NULL WHERE id=?",
                (run_id,),
            )
            self._event(run_id, "worker_completed", evidence)
