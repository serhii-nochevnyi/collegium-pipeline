"""Live serial worker/controller loop, including a repository-read-only self-test."""

import json
import time
from dataclasses import asdict
from urllib.parse import quote

from .adapters import Github
from .artifacts import Artifacts
from .config import config_digest
from .controller import accept_stage
from .domain import STAGE_ROLES, PolicyError, Revision, Selection, Task, digest, select_model
from .effort import runtime_evidence, tool_result
from .packets import REQUIREMENTS, readiness_packet
from .platform import Collegium, WorkerBinding
from .quality import Review


def worker_binding(config, role):
    value = dict(config["workers"][role])
    value["selection"] = Selection(**value["selection"])
    binding = WorkerBinding(**value)
    if binding.project_id != config["project_id"] or binding.selection != select_model(role):
        raise PolicyError("Worker binding differs from the admitted project or policy")
    return binding


class Runner:
    def __init__(self, config, journal, http, artifact_directory, *, github=None, clock=time.time):
        self.config, self.journal = config, journal
        self.platform, self.http = Collegium(http), http
        self.artifacts = Artifacts(artifact_directory)
        self.github = github or Github(config["repository"])
        self.clock = clock

    def prepare_readiness(self, task_id):
        if self.config.get("execution_profile") != "readiness":
            raise PolicyError("Self-test requires the explicit readiness profile")
        task = Task(
            "text", task_id, self.config["repository"], "Controller readiness", REQUIREMENTS
        )
        run_id = self.journal.admit(task, config_digest(self.config), purpose="readiness")
        if not self._events(run_id, "revision_bound"):
            commit = self.github.read("/commits/" + quote(self.config["base_branch"], safe=""))
            revision = Revision(
                self.config["repository_id"],
                commit["sha"],
                commit["sha"],
                task.acceptance_digest,
                config_digest(self.config),
            )
            self.journal.record(run_id, "revision_bound", asdict(revision))
        return run_id

    def _events(self, run_id, kind):
        return [e["data"] for e in self.journal.events(run_id) if e["kind"] == kind]

    def _subject(self, run_id, stage):
        target = {
            "plan_review": "planning",
            "validating": "implementing",
            "reviewing": "implementing",
        }.get(stage)
        if not target:
            return None
        previous = next(
            e for e in reversed(self._events(run_id, "stage_accepted")) if e["stage"] == target
        )
        identity = previous["evidence"]["artifact_digest"]
        subject = {"digest": identity, "result": self.artifacts.get(identity)}
        if stage == "reviewing":
            validation = next(
                e
                for e in reversed(self._events(run_id, "stage_accepted"))
                if e["stage"] == "validating"
            )
            subject["validation"] = validation["evidence"]
        return subject

    def _budget(self, run_id):
        tokens = sum(e["observed_tokens"] for e in self._events(run_id, "stage_usage"))
        if len(self._events(run_id, "dispatch_intent")) >= self.config.get("max_stage_attempts", 8):
            raise PolicyError("Run exhausted its stage-attempt budget")
        if tokens >= self.config.get("max_total_tokens", 100000):
            raise PolicyError("Run exhausted its observed token budget")
        return tokens

    def step(self, run_id):
        run = self.journal.get(run_id)
        if run["config_digest"] != config_digest(self.config):
            raise PolicyError("Run configuration changed; explicit replan is required")
        if run["state"] in {"failed", "cancelled", "reconciling", "self_test_passed"}:
            return {"run_id": run_id, "state": run["state"]}
        if self.config.get("execution_profile") != "readiness":
            raise PolicyError(
                "This command is a read-only readiness run, not delivery authorization"
            )
        if self.journal.events(run_id)[0]["data"].get("purpose") != "readiness":
            raise PolicyError("Run was not admitted for a readiness self-test")
        if self.config.get("execution_enabled") is not True:
            raise PolicyError("Execution is disabled")
        if run["state"] == "waiting_ci" and not run["pending_intent"]:
            evidence = {
                "profile": "readiness",
                "delivered": False,
                "accepted_stages": len(self._events(run_id, "stage_accepted")),
                "cost_accounting": "not_available_from_gateway",
                "scope": "synthetic sandbox task; no repository writes",
            }
            self.journal.complete_readiness(run_id, run["version"], evidence)
            return {"run_id": run_id, "state": "self_test_passed", **evidence}
        stage = run["state"]
        binding = worker_binding(self.config, STAGE_ROLES[stage])
        if not run["pending_intent"]:
            self._budget(run_id)
            agent, _ = self.http.request("GET", "/api/agents/" + binding.agent_id)
            repositories = agent.get("config", {}).get("repositories", [])
            if any(r.get("access") != "read" for r in repositories):
                raise PolicyError("Readiness worker must not hold repository write access")
            revision = self._events(run_id, "revision_bound")[-1]
            packet = readiness_packet(
                run_id,
                stage,
                binding.selection.role,
                revision,
                subject=self._subject(run_id, stage),
            )
            packet_digest = self.artifacts.put(json.loads(packet))
            self.journal.record(
                run_id,
                "stage_packet",
                {"stage": stage, "artifact_digest": packet_digest, "submitted_at": self.clock()},
            )
            launched = self.platform.dispatch(
                self.journal,
                run_id,
                run["version"],
                binding=binding,
                selection=binding.selection,
                prompt=packet,
                execution_enabled=True,
            )
            return {"run_id": run_id, "state": stage, "action": "dispatched", **launched}
        launches = [
            e for e in self._events(run_id, "launched") if e["intent"] == run["pending_intent"]
        ]
        if not launches:
            self.journal.unknown_launch(run_id, run["pending_intent"])
            return {"run_id": run_id, "state": "reconciling"}
        launch = launches[-1]
        turn = self.platform.observe(launch["session_id"], launch["turn_id"])
        if turn["status"] in {"starting", "running"}:
            packet = self._events(run_id, "stage_packet")[-1]
            if self.clock() - packet["submitted_at"] > self.config.get("max_stage_seconds", 180):
                answer, _ = self.http.request("POST", "/session/" + launch["session_id"] + "/abort")
                self.journal.record(run_id, "stop_requested", answer)
                self.journal.unknown_launch(run_id, run["pending_intent"])
                return {"run_id": run_id, "state": "reconciling", "reason": "stage_timeout"}
            return {"run_id": run_id, "state": stage, "action": "waiting"}
        observation = self.platform.observations(launch["session_id"], launch["turn_id"])
        observed_digest = self.artifacts.put(observation)
        try:
            if turn["status"] != "completed":
                raise PolicyError("Worker turn failed or was aborted")
            # The runtime's terminal event carries usage; it may trail the API result briefly.
            idle = [e for e in observation["events"] if e.get("type") == "session.status_idle"]
            if not idle:
                packet = self._events(run_id, "stage_packet")[-1]
                if self.clock() - packet["submitted_at"] < self.config.get(
                    "max_stage_seconds", 180
                ):
                    return {"run_id": run_id, "state": stage, "action": "settling"}
                raise PolicyError("Runtime event history did not settle")
            proof = runtime_evidence(
                observation, binding, session_id=launch["session_id"], turn_id=launch["turn_id"]
            )
            packet_ref = self._events(run_id, "stage_packet")[-1]["artifact_digest"]
            user = next(e for e in observation["events"] if e.get("type") == "user.message")
            supplied = "".join(
                p.get("text", "") for p in user["content"] if p.get("type") == "text"
            )
            if digest(json.loads(supplied)) != packet_ref:
                raise PolicyError("Observed prompt differs from the admitted packet")
            result = json.loads(observation["turn"]["answer"])
            if not isinstance(result, dict):
                raise PolicyError("Worker result must be a JSON object")
            revision = self._events(run_id, "revision_bound")[-1]
            if (
                result.get("schema_version") != "worker-result/v1"
                or result.get("run_id") != run_id
                or result.get("stage") != stage
                or result.get("revision") != revision
                or not isinstance(result.get("blocking_findings"), list)
            ):
                raise PolicyError("Worker result envelope is invalid or stale")
            subject = self._subject(run_id, stage)
            if subject and result.get("subject_artifact_digest") != subject["digest"]:
                raise PolicyError("Worker reviewed or validated the wrong artifact")
            if stage == "implementing":
                from .packets import validation_command

                validation_command(result.get("payload", {}))
            if stage == "planning":
                payload = result.get("payload", {})
                if (
                    not isinstance(payload, dict)
                    or not payload.get("plan")
                    or not isinstance(payload.get("acceptance"), list)
                    or not payload["acceptance"]
                ):
                    raise PolicyError("Plan has no implementation steps or acceptance mapping")
            review = None
            if stage in {"plan_review", "reviewing"}:
                subject_stage = "planning" if stage == "plan_review" else "implementing"
                producer = next(
                    e["evidence"]["session_id"]
                    for e in reversed(self._events(run_id, "stage_accepted"))
                    if e["stage"] == subject_stage
                )
                review = Review(
                    Revision(**revision),
                    launch["session_id"],
                    producer,
                    result["verdict"],
                    len(result["blocking_findings"]),
                )
            if stage == "validating":
                packet = self.artifacts.get(packet_ref)
                use, checked = tool_result(observation, packet["validation_command"], index=1)
                if 'COLLEGIUM_VALIDATION={"passed": true, "cases": 7}' not in checked.get(
                    "output", ""
                ):
                    raise PolicyError("Required synthetic test result is absent")
                result["commands"] = [
                    {
                        "command": packet["validation_command"],
                        "exit_code": 0,
                        "tool_use_id": use["tool_use_id"],
                    }
                ]
            result["artifact_digest"] = self.artifacts.put(result)
            proof_digest = self.artifacts.put(
                {"runtime_evidence": proof, "observation_digest": observed_digest}
            )
            self.journal.record(
                run_id,
                "runtime_verified",
                {"stage": stage, "artifact_digest": proof_digest, **proof},
            )
            usage = idle[-1].get("usage", {})
            observed_tokens = sum(
                v for k, v in usage.items() if k.endswith("tokens") and type(v) is int and v >= 0
            )
            # Usage is recorded separately from acceptance and never inferred as $0.
            self.journal.record(
                run_id,
                "stage_usage",
                {"stage": stage, "observed_tokens": observed_tokens, "usage": usage},
            )
            accept_stage(
                self.journal,
                run_id,
                version=run["version"],
                current=Revision(**revision),
                selection=binding.selection,
                actual_selection=proof,
                result=result,
                review=review,
            )
            return {
                "run_id": run_id,
                "state": self.journal.get(run_id)["state"],
                "action": "accepted",
                "completed_stage": stage,
                "effort": proof["effort"],
            }
        except (PolicyError, ValueError, KeyError, TypeError) as exc:
            self.journal.record(
                run_id,
                "rejected_observation",
                {"artifact_digest": observed_digest, "reason": str(exc)},
            )
            self.journal.fail(run_id, run["version"], str(exc))
            return {"run_id": run_id, "state": "failed", "stage": stage, "reason": str(exc)}

    def stop(self, run_id, reason="operator_stop"):
        run = self.journal.get(run_id)
        if run["state"] in {"self_test_passed", "failed", "cancelled", "reconciling"}:
            return
        launches = [
            e for e in self._events(run_id, "launched") if e["intent"] == run["pending_intent"]
        ]
        if launches:
            answer, _ = self.http.request(
                "POST", "/session/" + launches[-1]["session_id"] + "/abort"
            )
            self.journal.record(run_id, "stop_requested", {"reason": reason, **answer})
            confirmed_finished = "aborted" not in answer and answer.get("status") in {
                "completed",
                "failed",
                "aborted",
            }
            if answer.get("aborted") is not True and not confirmed_finished:
                self.journal.unknown_launch(run_id, run["pending_intent"])
                return
        self.journal.fail(run_id, run["version"], reason)
