"""Collegium's verified session API; observation does not imply quality acceptance.

Contract source: services/acp-mcp/src/lap/sessions.py, read 2026-11-27.
No automatic retry creates another session after an ambiguous response.
"""

from dataclasses import asdict, dataclass
from urllib.parse import quote

from .domain import PolicyError, Selection, digest, selection_harness
from .transport import RemoteError


@dataclass(frozen=True)
class WorkerBinding:
    agent_id: str
    project_id: str
    runtime: str
    environment_id: str
    api_model: str
    selection: Selection
    approved_agent_digest: str
    harness: str = "codex"
    model_connection_id: str | None = None


def agent_digest(agent: dict) -> str:
    """Pin configuration and ownership, excluding usage and source revision labels."""
    volatile = {"created_at_ms", "updated_at_ms", "last_run_at", "last_error", "status", "spend"}
    snapshot = {key: value for key, value in agent.items() if key not in volatile}
    if isinstance(snapshot.get("provenance"), dict):
        # Source revision labels may change independently of runtime configuration.
        # Keep installation/source/instance identity and source_gone pinned.
        snapshot["provenance"] = {
            key: value
            for key, value in snapshot["provenance"].items()
            if key not in {"commit", "version"}
        }
    return digest(snapshot)


class Collegium:
    def __init__(self, http):
        self.http = http

    def dispatch(
        self,
        journal,
        run_id: str,
        version: int,
        *,
        binding: WorkerBinding,
        selection: Selection,
        prompt: str,
        execution_enabled=False,
    ):
        if execution_enabled is not True:
            raise PolicyError("Live dispatch is disabled")
        if binding.selection != selection:
            raise PolicyError("Worker variant differs from the requested role/model/effort")
        # API alias mapping is explicit and bounded; no provider fallback.
        if binding.harness != selection_harness(selection):
            raise PolicyError("Worker harness differs from the admitted policy")
        aliases = {selection.model}
        if binding.harness == "codex":
            aliases.add("openai/" + selection.model)
        if binding.api_model not in aliases:
            raise PolicyError("Worker model alias is not approved")
        if binding.harness == "claude-code" and not binding.model_connection_id:
            raise PolicyError("Claude workers require an explicit private model connection")
        if not prompt.strip() or not binding.runtime or not binding.environment_id:
            raise PolicyError("Prompt, runtime and environment are required")
        safe_agent = quote(binding.agent_id, safe="")
        agent, _ = self.http.request("GET", f"/api/agents/{safe_agent}")
        if agent_digest(agent) != binding.approved_agent_digest:
            raise PolicyError("Worker configuration changed; review and bind a new variant")
        if agent.get("model") != binding.api_model:
            raise PolicyError("Worker model differs from its binding")
        if agent.get("project_id") != binding.project_id:
            raise PolicyError("Worker belongs to a different Collegium project")
        configured_runtime = agent.get("runtime") or agent.get("config", {}).get("runtime")
        if configured_runtime != binding.runtime:
            raise PolicyError("Worker runtime differs from its binding")
        if agent.get("config", {}).get("effort") != selection.effort:
            raise PolicyError("Worker effort must be explicit and match its selected variant")
        if binding.model_connection_id and (
            agent.get("model_connection_id") != binding.model_connection_id
            or agent.get("harness") != binding.harness
        ):
            raise PolicyError("Worker private model connection or harness differs")
        run = journal.get(run_id)
        request = {
            "binding": asdict(binding),
            "prompt": prompt,
            "acceptance": run["task"],
            "config": run["config_digest"],
        }
        intent = journal.begin_dispatch(run_id, version, asdict(selection), digest(request))
        journal.record(
            run_id,
            "dispatch_request",
            {
                "intent": intent,
                "stage": run["state"],
                "request": request,
            },
        )
        from .recovery import session_name

        try:
            journal.checkpoint({"kind": "session_create", "run_id": run_id, "intent": intent})
            created, _ = self.http.request(
                "POST",
                "/session",
                {
                    "runtime": binding.runtime,
                    "agent_id": binding.agent_id,
                    "environment_id": binding.environment_id,
                    "harness": binding.harness,
                    "name": session_name(intent),
                },
            )
            session_id = created.get("id")
            if not isinstance(session_id, str) or not session_id:
                raise RemoteError("Session response omitted its ID", unknown_outcome=True)
            # Durable session identity precedes prompt submission. A caller can
            # inspect this session even if the prompt response is lost.
            journal.record_session(run_id, intent, session_id)
            journal.checkpoint({"kind": "prompt", "run_id": run_id, "intent": intent})
            started, _ = self.http.request(
                "POST",
                f"/session/{quote(session_id, safe='')}/prompt_async",
                {
                    "parts": [{"type": "text", "text": prompt}],
                    "model": {"modelID": binding.api_model},
                },
                headers={"Idempotency-Key": intent},
            )
            turn_id = started.get("turn_id")
            if not isinstance(turn_id, str) or not turn_id:
                raise RemoteError("Turn response omitted its ID", unknown_outcome=True)
            journal.record_launch(run_id, intent, session_id, turn_id)
            return {"intent": intent, "session_id": session_id, "turn_id": turn_id}
        except (RemoteError, OSError, ValueError, KeyError):
            # Conservative even for an explicit refusal: retain the launch
            # identity rather than silently creating a second session.
            journal.unknown_launch(run_id, intent)
            raise

    def resume_dispatch(self, journal, run_id, *, binding, selection, prompt, execution_enabled):
        """Only the recorded session and idempotency key may be continued."""
        if not execution_enabled or binding.selection != selection:
            raise PolicyError("Resumed dispatch is disabled or its selection differs")
        run = journal.get(run_id)
        events = journal.events(run_id)
        intent = run["pending_intent"]
        requests = [
            e["data"]
            for e in events
            if e["kind"] == "dispatch_request" and e["data"]["intent"] == intent
        ]
        expected = {
            "binding": asdict(binding),
            "prompt": prompt,
            "acceptance": run["task"],
            "config": run["config_digest"],
        }
        if len(requests) != 1 or requests[0]["request"] != expected:
            raise PolicyError("Resumed dispatch request differs from its immutable intent")
        agent, _ = self.http.request("GET", "/api/agents/" + binding.agent_id)
        if agent_digest(agent) != binding.approved_agent_digest:
            raise PolicyError("Resumed worker configuration changed")
        known = [
            e["data"]["session_id"]
            for e in events
            if e["kind"] == "session_created" and e["data"]["intent"] == intent
        ]
        if run["state"] not in {
            "planning",
            "plan_review",
            "implementing",
            "validating",
            "reviewing",
            "waiting_ci",
        }:
            raise PolicyError("Reconcile the launch before resuming its prompt")
        if not known:
            operation = {"kind": "session_create", "run_id": run_id, "intent": intent}
            if not journal.effect_not_started(operation):
                raise PolicyError("Reconcile the existing session before creating any replacement")
            from .recovery import session_name

            journal.checkpoint(operation)
            created, _ = self.http.request(
                "POST",
                "/session",
                {
                    "runtime": binding.runtime,
                    "agent_id": binding.agent_id,
                    "environment_id": binding.environment_id,
                    "harness": binding.harness,
                    "name": session_name(intent),
                },
            )
            if not isinstance(created.get("id"), str) or not created["id"]:
                raise PolicyError("Resumed creation has no known session identity")
            journal.record_session(run_id, intent, created["id"])
            known = [created["id"]]
        if len(known) != 1:
            raise PolicyError("Resumed session identity is ambiguous")
        from .recovery import session_name

        session, _ = self.http.request("GET", "/session/" + known[0])
        if any(
            session.get(k) != v
            for k, v in {
                "name": session_name(intent),
                "agent_id": binding.agent_id,
                "project_id": binding.project_id,
                "runtime": binding.runtime,
                "harness": binding.harness,
                "environment_id": binding.environment_id,
            }.items()
        ):
            raise PolicyError("Resumed session identity differs")
        launched = [
            e["data"] for e in events if e["kind"] == "launched" and e["data"]["intent"] == intent
        ]
        if launched:
            if len(launched) != 1 or launched[0]["session_id"] != known[0]:
                raise PolicyError("Resumed launch identities differ")
            return launched[0]
        journal.checkpoint({"kind": "prompt", "run_id": run_id, "intent": intent})
        started, _ = self.http.request(
            "POST",
            "/session/" + known[0] + "/prompt_async",
            {
                "parts": [{"type": "text", "text": prompt}],
                "model": {"modelID": binding.api_model},
            },
            headers={"Idempotency-Key": intent},
        )
        turn = started.get("turn_id")
        if not isinstance(turn, str) or not turn:
            raise PolicyError("Resumed prompt has no known turn identity")
        journal.record_launch(run_id, intent, known[0], turn)
        return {"session_id": known[0], "turn_id": turn, "intent": intent}

    def observe(self, session_id: str, turn_id: str):
        path = f"/session/{quote(session_id, safe='')}/turns/{quote(turn_id, safe='')}"
        row, _ = self.http.request("GET", path)
        return row

    def observations(self, session_id: str, turn_id: str):
        turn = self.observe(session_id, turn_id)
        session, _ = self.http.request("GET", "/session/" + quote(session_id, safe=""))
        events, _ = self.http.request(
            "GET", "/session/" + quote(session_id, safe="") + "/runtime_events/list"
        )
        if events.get("has_more"):
            raise PolicyError("Incomplete event history; refusing partial runtime evidence")
        return {"turn": turn, "session": session, "events": events["data"]}
