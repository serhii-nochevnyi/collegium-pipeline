"""Coordinator acceptance boundary for the serial prototype."""

import json
import re
from dataclasses import asdict

from .domain import STAGE_ROLES, PolicyError, Revision, Selection, Task, verify_selection
from .quality import Review, verify_checks, verify_pr, verify_review


def accept_stage(
    journal,
    run_id: str,
    *,
    version: int,
    current: Revision,
    selection: Selection,
    actual_selection: dict,
    result: dict,
    review: Review | None = None,
    pr=None,
    checks=None,
    statuses=None,
    required_checks=None,
):
    """Inputs come from coordinator adapters; worker JSON alone is insufficient."""
    run = journal.get(run_id)
    if run["version"] != version:
        raise PolicyError("Run changed while observing evidence")
    task = Task(**json.loads(run["task"]))
    if (
        current.acceptance_digest != task.acceptance_digest
        or current.config_digest != run["config_digest"]
    ):
        raise PolicyError("Acceptance or configuration evidence does not match this run")
    verify_selection(selection, actual_selection)
    launch = next(
        (
            e["data"]
            for e in reversed(journal.events(run_id))
            if e["kind"] == "launched" and e["data"]["intent"] == run["pending_intent"]
        ),
        None,
    )
    if launch is None or launch["session_id"] != actual_selection["session_id"]:
        raise PolicyError("Runtime evidence does not match the admitted launch")
    intent = next(
        e["data"]
        for e in journal.events(run_id)
        if e["kind"] == "dispatch_intent" and e["data"]["intent"] == run["pending_intent"]
    )
    if intent["selection"] != asdict(selection):
        raise PolicyError("Selection differs from the admitted dispatch")
    stage = run["state"]
    if STAGE_ROLES.get(stage) != selection.role:
        raise PolicyError("Role does not match the current stage")
    if result.get("verdict") != "pass" or result.get("revision") != asdict(current):
        raise PolicyError("Stage result is failing or belongs to a different revision")
    if not re.fullmatch(r"[0-9a-f]{64}", result.get("artifact_digest", "")):
        raise PolicyError("Stage result has no artifact identity")
    if stage in {"plan_review", "reviewing"}:
        if review is None:
            raise PolicyError("Independent review evidence is required")
        verify_review(review, current)
        prior_stage = "planning" if stage == "plan_review" else "implementing"
        subject = next(
            (
                e["data"]["evidence"]["session_id"]
                for e in reversed(journal.events(run_id))
                if e["kind"] == "stage_accepted" and e["data"]["stage"] == prior_stage
            ),
            None,
        )
        if (
            review.reviewer_session != actual_selection["session_id"]
            or review.executor_session != subject
        ):
            raise PolicyError("Review identities do not match the recorded producer and reviewer")
    if stage == "validating":
        commands = result.get("commands")
        if not commands or any(
            type(c.get("exit_code")) is not int or c["exit_code"] != 0 or not c.get("command")
            for c in commands
        ):
            raise PolicyError("Applicable validation commands have not passed")
    if stage == "waiting_ci":
        if pr is None:
            raise PolicyError("Independently observed PR evidence is missing")
        verify_pr(pr, repository_id=current.repository_id, head=current.head, base=current.base)
        verify_checks(
            checks or [], statuses or [], head=current.head, required=required_checks or []
        )
    journal.advance(
        run_id,
        version,
        {
            "revision": asdict(current),
            "artifact_digest": result["artifact_digest"],
            "selection": asdict(selection),
            "session_id": actual_selection["session_id"],
        },
    )
