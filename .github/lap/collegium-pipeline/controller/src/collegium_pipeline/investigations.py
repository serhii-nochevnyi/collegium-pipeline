"""Versioned read-only investigation, bounded research and independent decision review."""

import json
import re

from .artifacts import Artifacts
from .capacity import checked_paths
from .config import config_digest
from .domain import PolicyError, Task, digest
from .investigation_policy import DIMENSIONS, PERSPECTIVES, REVIEW_CHECKS, assessment, cited, route
from .investigation_workers import InvestigationJobs
from .platform import confirmed_pending_launch
from .store import CheckpointError


def strings(values, *, nonempty=False):
    if (
        not isinstance(values, list)
        or len(values) > 32
        or (nonempty and not values)
        or any(not isinstance(v, str) or not v.strip() or len(v) > 8000 for v in values)
    ):
        raise PolicyError("Expected a bounded list of nonempty text values")


def questions(values):
    if not isinstance(values, list) or len(values) > 32:
        raise PolicyError("Open questions must be bounded")
    for row in values:
        if (
            not isinstance(row, dict)
            or set(row) != {"text", "blocking"}
            or type(row["blocking"]) is not bool
        ):
            raise PolicyError("Open questions need text and explicit blocking flag")
        strings([row["text"]], nonempty=True)
    return values


def validate_research(payload, sources, perspective):
    if (
        not isinstance(payload, dict)
        or set(payload) != {"perspective", "findings", "risks", "assumptions", "open_questions"}
        or payload["perspective"] != perspective
    ):
        raise PolicyError("Research perspective or schema differs")
    for key in ("findings", "risks"):
        rows = payload[key]
        if not isinstance(rows, list) or len(rows) > 24 or (key == "findings" and not rows):
            raise PolicyError("Research needs bounded sourced findings")
        for row in rows:
            cited(row, sources)
    strings(payload["assumptions"])
    questions(payload["open_questions"])
    return payload


def validate_synthesis(payload, sources, config):
    if not isinstance(payload, dict) or set(payload) != {
        "summary",
        "options",
        "recommendation",
        "risks",
        "open_questions",
        "proposed_adr",
        "tickets",
    }:
        raise PolicyError("Synthesis schema differs")
    cited(payload["summary"], sources)
    if not isinstance(payload["options"], list) or not 2 <= len(payload["options"]) <= 5:
        raise PolicyError("Compare at least two options")
    names = []
    for option in payload["options"]:
        if not isinstance(option, dict) or set(option) != {"name", "analysis", "tradeoffs"}:
            raise PolicyError("Options need name, sourced analysis and tradeoffs")
        strings([option["name"]], nonempty=True)
        names.append(option["name"])
        cited(option["analysis"], sources)
        strings(option["tradeoffs"], nonempty=True)
    if len(set(names)) != len(names) or payload["recommendation"] not in names:
        raise PolicyError("Recommendation must identify a distinct compared option")
    if not isinstance(payload["risks"], list) or not 1 <= len(payload["risks"]) <= 24:
        raise PolicyError("Synthesis needs sourced risks")
    for risk in payload["risks"]:
        cited(risk, sources)
    questions(payload["open_questions"])
    adr = payload["proposed_adr"]
    if not isinstance(adr, dict) or set(adr) != {"title", "context", "decision", "consequences"}:
        raise PolicyError("ADR must remain a complete proposal")
    strings(list(adr.values()), nonempty=True)
    tickets = payload["tickets"]
    if not isinstance(tickets, list) or not 1 <= len(tickets) <= 16:
        raise PolicyError("Proposed decomposition must have1..16tickets")
    keys = set()
    for ticket in tickets:
        if not isinstance(ticket, dict) or set(ticket) != {
            "key",
            "title",
            "requirements",
            "acceptance",
            "depends_on",
            "paths",
            "validation_commands",
        }:
            raise PolicyError("Incomplete proposed ticket")
        if (
            not isinstance(ticket["key"], str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,31}", ticket["key"])
            or ticket["key"] in keys
        ):
            raise PolicyError("Proposed ticket keys must be unique")
        keys.add(ticket["key"])
        strings([ticket["title"], ticket["requirements"]], nonempty=True)
        strings(ticket["acceptance"], nonempty=True)
        strings(ticket["depends_on"])
        checked_paths(ticket["paths"], config["investigation"]["source_paths"])
        if ticket["validation_commands"] != config["validation_commands"]:
            raise PolicyError("Proposed validation must retain configured commands")
    edges = {t["key"]: t["depends_on"] for t in tickets}
    visited, active = set(), set()

    def visit(key):
        if key not in keys or key in active:
            raise PolicyError("Proposed dependency graph is cyclic or refers to an unknown ticket")
        if key in visited:
            return
        active.add(key)
        for dep in edges[key]:
            visit(dep)
        active.remove(key)
        visited.add(key)

    for key in keys:
        visit(key)
    return payload


class Investigations:
    def __init__(self, config, journal, http, directory):
        if config.get("broker_enabled") is not False or not config.get("investigation"):
            raise PolicyError("Investigation requires a read-only configured lane")
        self.config, self.journal = config, journal
        self.artifacts = Artifacts(directory)
        self.jobs = InvestigationJobs(config, journal, http, self.artifacts)
        journal.connection.execute(
            "CREATE TABLE IF NOT EXISTS investigations "
            "(run_id TEXT PRIMARY KEY REFERENCES runs(id), document TEXT NOT NULL)"
        )

    def save(self, root, doc):
        with self.journal.transaction():
            self.journal.connection.execute(
                "INSERT INTO investigations VALUES(?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET document=excluded.document",
                (root, json.dumps(doc, sort_keys=True)),
            )
            self.journal._event(
                root, "investigation_tick", {"state": doc["state"], "revision": doc["revision"]}
            )
        return {"run_id": root, **doc}

    def load(self, root):
        if self.journal.get(root)["config_digest"] != config_digest(self.config):
            raise PolicyError(
                "Investigation configuration changed; explicit new admission required"
            )
        row = self.journal.connection.execute(
            "SELECT document FROM investigations WHERE run_id=?", (root,)
        ).fetchone()
        if not row:
            raise PolicyError("Investigation is missing")
        return json.loads(row[0])

    def admit(self, intake, sources):
        if not isinstance(intake, dict) or set(intake) != {
            "task",
            "head",
            "sources",
            "risk_flags",
            "constraints",
        }:
            raise PolicyError("Investigation intake schema differs")
        if len(json.dumps(intake).encode()) > 24000:
            raise PolicyError("Investigation intake exceeds24KB")
        task = Task(**intake["task"])
        if task.repository != self.config["repository"] or not re.fullmatch(
            r"[0-9a-f]{40}", intake["head"]
        ):
            raise PolicyError("Investigation leaves the configured repository/revision")
        strings(intake["constraints"])
        flags = intake["risk_flags"]
        if (
            not isinstance(flags, list)
            or any(not isinstance(f, str) for f in flags)
            or len(flags) != len(set(flags))
            or set(flags) - {"security", "data_migration", "public_api", "concurrency", "unknowns"}
        ):
            raise PolicyError("Unknown risk floor")
        if (
            not sources
            or len({s["id"] for s in sources}) != len(sources)
            or any(
                s["head"] != intake["head"] or s["repository_id"] != self.config["repository_id"]
                for s in sources
            )
        ):
            raise PolicyError("Independently captured source identity differs")
        root_task = Task(
            "text",
            "investigation:" + task.source + ":" + task.source_id,
            task.repository,
            task.title,
            json.dumps({"intake": intake, "catalog": digest(sources)}, sort_keys=True),
        )
        root = self.journal.admit(root_task, config_digest(self.config), purpose="investigation")
        old = self.journal.connection.execute(
            "SELECT document FROM investigations WHERE run_id=?", (root,)
        ).fetchone()
        if old:
            return {"run_id": root, **self.load(root)}
        return self.save(
            root,
            {
                "state": "assessing",
                "revision": 1,
                "paused": False,
                "head": intake["head"],
                "intake": intake,
                "sources": self.artifacts.put({"sources": sources}),
                "assessment": None,
                "research": {},
                "synthesis": None,
                "review": None,
                "attempts": {},
                "results": {},
                "rejections": [],
                "tokens": 0,
                "decision_approved": False,
                "delivered": False,
            },
        )

    def pause(self, root, paused=True):
        doc = self.load(root)
        doc["paused"] = paused
        return self.save(root, doc)

    def contract(self, stage, perspective=None):
        claim = {
            "text": "fact",
            "citations": [
                {
                    "source_id": "registered ID",
                    "start": 1,
                    "end": 1,
                    "quote": "exact captured lines",
                }
            ],
        }
        q = [{"text": "question", "blocking": True}]
        if stage == "assessing":
            return {
                "dimensions": {d: {"score": "integer0..3", "evidence": claim} for d in DIMENSIONS},
                "confidence": "number0..1",
                "rationale": "explain scores; coordinator imposes risk floors",
            }
        if stage == "researching":
            return {
                "perspective": perspective,
                "findings": [claim],
                "risks": [claim],
                "assumptions": ["unverified inference"],
                "open_questions": q,
            }
        if stage == "synthesizing":
            return {
                "summary": claim,
                "options": [
                    {
                        "name": "unique option, at least2",
                        "analysis": claim,
                        "tradeoffs": ["tradeoff"],
                    }
                ],
                "recommendation": "one option name",
                "risks": [claim],
                "open_questions": q,
                "proposed_adr": {
                    k: "proposed text" for k in ("title", "context", "decision", "consequences")
                },
                "tickets": [
                    {
                        "key": "A",
                        "title": "title",
                        "requirements": "scope",
                        "acceptance": ["checkable outcome"],
                        "depends_on": [],
                        "paths": self.config["investigation"]["source_paths"][:1],
                        "validation_commands": self.config["validation_commands"],
                    }
                ],
            }
        return {
            "subject_digest": "context.synthesis_digest",
            "research_digests": "context.research_digests",
            "checks": {k: "boolean: pass only when verified" for k in REVIEW_CHECKS},
            "open_questions": q,
        }

    def settle(self, root, doc):
        settlement = self.jobs.drain(root)
        previous = doc.get("unaccepted_tokens", 0)
        doc["tokens"] += settlement["tokens"] - previous
        doc.update(unaccepted_tokens=settlement["tokens"], settlement=settlement)

    def step_job(self, root, doc, stage, perspective=None):
        logical = stage + (":" + perspective if perspective else "")
        if logical in doc["results"]:
            return self.artifacts.get(doc["results"][logical])
        attempt = doc["attempts"].get(logical, 0)
        key = f"investigation:{logical}:{doc['revision']}:{attempt}"
        row = self.journal.connection.execute(
            "SELECT id FROM runs WHERE source_id=?", (root + ":" + key,)
        ).fetchone()
        known = self.journal.get(row[0]) if row else None
        launched = confirmed_pending_launch(self.journal, row[0]) if row else None
        completed = bool(
            row and any(e["kind"] == "worker_completed" for e in self.journal.events(row[0]))
        )
        if doc["paused"] and not (launched or completed):
            return None
        # Unknown session/prompt intents retain their ownership, never bypass admission.
        pending_count = self.journal.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE pending_intent IS NOT NULL"
        ).fetchone()[0]
        count = self.journal.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE source_id LIKE ?", (root + ":%",)
        ).fetchone()[0]
        if not (launched or completed) and (
            doc["tokens"] >= self.config["max_total_tokens"]
            or (not known and count >= self.config["investigation"]["max_jobs"])
        ):
            doc.update(state="blocked", reason="Investigation admission budget exhausted")
            return None
        if not known and pending_count >= self.config["investigation"]["parallelism"]:
            return None
        level = (
            self.artifacts.get(doc["assessment"])["complexity"] if doc["assessment"] else "standard"
        )
        selection = route(stage, level)
        sources = self.artifacts.get(doc["sources"])["sources"]
        context = {
            "intake": doc["intake"],
            "sources": sources,
            "assessment": self.artifacts.get(doc["assessment"]) if doc["assessment"] else None,
            "research": {p: self.artifacts.get(d)["payload"] for p, d in doc["research"].items()}
            if stage in {"synthesizing", "investigation_review"}
            else {},
            "research_digests": doc["research"]
            if stage in {"synthesizing", "investigation_review"}
            else {},
            "synthesis_digest": doc["synthesis"] if stage == "investigation_review" else None,
            "synthesis": self.artifacts.get(doc["synthesis"])["payload"]
            if doc["synthesis"]
            else None,
            "payload_contract": self.contract(stage, perspective),
            "feedback": doc.get("feedback"),
        }
        try:
            result = self.jobs.step(root, key, stage, doc["head"], context, selection)
        except CheckpointError:
            raise
        except PolicyError as exc:
            # Ambiguous launches and malformed observations stay blocked with their original IDs.
            doc.update(state="blocked", reason=str(exc))
            return None
        if result is None:
            return None
        doc["tokens"] += result["observed_tokens"]
        if len(json.dumps(result).encode()) > 64000:
            self.save(root, doc)
            raise PolicyError("Investigation result exceeds64KB")
        identity = self.artifacts.put(result)
        doc["results"][logical] = identity
        self.save(root, doc)
        return result

    def step(self, root):
        if not self.config["execution_enabled"] or self.config["broker_enabled"]:
            raise PolicyError("Investigation dispatch requires explicit read-only live authority")
        doc = self.load(root)
        if doc["state"] in {"ready_for_decision", "needs_input", "blocked"}:
            if doc["state"] == "blocked":
                self.settle(root, doc)
                return self.save(root, doc)
            return {"run_id": root, **doc}
        sources = self.artifacts.get(doc["sources"])["sources"]
        try:
            if not doc["assessment"]:
                result = self.step_job(root, doc, "assessing")
                if result:
                    if result["verdict"] != "pass":
                        raise PolicyError("Assessment was inconclusive")
                    payload = assessment(
                        result["payload"],
                        sources,
                        doc["intake"]["risk_flags"],
                        self.config["investigation"]["minimum_complexity"],
                    )
                    doc.update(assessment=self.artifacts.put(payload), state="researching")
            elif len(doc["research"]) < len(PERSPECTIVES):
                for perspective in PERSPECTIVES:
                    if perspective in doc["research"] or doc["state"] == "blocked":
                        continue
                    result = self.step_job(root, doc, "researching", perspective)
                    if result:
                        if result["verdict"] != "pass":
                            raise PolicyError("Research perspective is inconclusive")
                        validate_research(result["payload"], sources, perspective)
                        doc["research"][perspective] = self.artifacts.put(result)
                if len(doc["research"]) == len(PERSPECTIVES):
                    doc["state"] = "synthesizing"
            elif not doc["synthesis"]:
                result = self.step_job(root, doc, "synthesizing")
                if result:
                    if result["verdict"] != "pass":
                        raise PolicyError("Synthesis was inconclusive")
                    validate_synthesis(result["payload"], sources, self.config)
                    doc.update(synthesis=self.artifacts.put(result), state="investigation_review")
            else:
                result = self.step_job(root, doc, "investigation_review")
                if result:
                    payload = result["payload"]
                    producers = [
                        self.artifacts.get(d)["session_id"]
                        for k, d in doc["results"].items()
                        if k != "investigation_review"
                    ]
                    if (
                        result["session_id"] in producers
                        or not isinstance(payload, dict)
                        or set(payload)
                        != {"subject_digest", "research_digests", "checks", "open_questions"}
                        or payload["subject_digest"] != doc["synthesis"]
                        or payload["research_digests"] != doc["research"]
                    ):
                        raise PolicyError(
                            "Review is not independent or is bound to stale artifacts"
                        )
                    questions(payload["open_questions"])
                    if not isinstance(payload["checks"], dict) or set(payload["checks"]) != set(
                        REVIEW_CHECKS
                    ):
                        raise PolicyError("Review must cover every required quality check")
                    if result["verdict"] != "pass" or any(
                        v is not True for v in payload["checks"].values()
                    ):
                        if doc["revision"] > self.config["max_repair_attempts"]:
                            raise PolicyError("Investigation review retry limit exhausted")
                        doc.update(
                            revision=doc["revision"] + 1,
                            synthesis=None,
                            review=None,
                            state="synthesizing",
                            feedback=result,
                        )
                        for key in ("synthesizing", "investigation_review"):
                            doc["results"].pop(key, None)
                    else:
                        qs = (
                            payload["open_questions"]
                            + self.artifacts.get(doc["synthesis"])["payload"]["open_questions"]
                        )
                        for d in doc["research"].values():
                            qs += self.artifacts.get(d)["payload"]["open_questions"]
                        doc.update(
                            review=self.artifacts.put(result),
                            state="needs_input"
                            if any(q["blocking"] for q in qs)
                            else "ready_for_decision",
                        )
        except CheckpointError:
            raise
        except PolicyError as exc:
            doc.update(state="blocked", reason=str(exc))
        if doc["state"] == "blocked":
            self.settle(root, doc)
        return self.save(root, doc)

    def status(self, root):
        doc = self.load(root)
        workers = []
        for row in self.journal.connection.execute(
            "SELECT id,source_id,state,pending_intent FROM runs WHERE source_id LIKE ?",
            (root + ":%",),
        ):
            for event in self.journal.events(row["id"]):
                if event["kind"] == "launched":
                    workers.append(
                        {
                            "job": row["id"],
                            "key": row["source_id"],
                            "state": row["state"],
                            **event["data"],
                        }
                    )
        return {
            "run_id": root,
            **doc,
            "workers": workers,
            "complexity_assessment": self.artifacts.get(doc["assessment"])
            if doc["assessment"]
            else None,
            "stage_evidence": {
                name: {
                    key: self.artifacts.get(value).get(key)
                    for key in (
                        "verdict",
                        "revision",
                        "session_id",
                        "runtime_evidence",
                        "observed_tokens",
                    )
                }
                for name, value in doc["results"].items()
            },
            "decision_approved": False,
            "delivered": False,
            "proposal": self.artifacts.get(doc["synthesis"])["payload"]
            if doc["synthesis"]
            else None,
        }
