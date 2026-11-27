"""Versioned task identities and policy decisions; no external side effects."""

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256


class PolicyError(ValueError):
    pass


def digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Task:
    source: str
    source_id: str
    repository: str
    title: str
    requirements: str

    def __post_init__(self):
        if self.source not in {"text", "jira"}:
            raise PolicyError("Task source must be text or jira")
        if not all(isinstance(v, str) and v.strip() for v in asdict(self).values()):
            raise PolicyError("Task fields cannot be empty")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise PolicyError("Repository must be an explicit owner/name")

    @property
    def acceptance_digest(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class Revision:
    repository_id: int
    head: str
    base: str
    acceptance_digest: str
    config_digest: str

    def __post_init__(self):
        if type(self.repository_id) is not int or self.repository_id <= 0:
            raise PolicyError("A positive immutable repository ID is required")
        for name in ("head", "base"):
            if not re.fullmatch(r"[0-9a-f]{40}", getattr(self, name)):
                raise PolicyError(f"{name} must be an exact Git commit SHA")
        for name in ("acceptance_digest", "config_digest"):
            if not re.fullmatch(r"[0-9a-f]{64}", getattr(self, name)):
                raise PolicyError(f"{name} must be SHA256")


@dataclass(frozen=True)
class Selection:
    role: str
    model: str
    effort: str
    reason: str


BASE_ROUTES = {
    "researcher": ("gpt-6.2-sol", "high"),
    "planner": ("gpt-6.2-sol", "high"),
    "plan_reviewer": ("gpt-6.2-sol", "high"),
    "executor": ("gpt-6.2-sol", "low"),
    "code_reviewer": ("gpt-6.2-sol", "high"),
    "fixer": ("gpt-6.2-sol", "low"),
    "integrator": ("gpt-6.2-sol", "high"),
    "drift_checker": ("gpt-6.2-sol", "low"),
    "sentinel": ("gpt-6-luna", "medium"),
}

STAGE_ROLES = {
    "planning": "planner",
    "plan_review": "plan_reviewer",
    "implementing": "executor",
    "validating": "executor",
    "reviewing": "code_reviewer",
    "waiting_ci": "sentinel",
}


def select_model(
    role: str, *, critical=False, checkpoint=False, same_cause_failures=0, very_complex=False
) -> Selection:
    if role not in BASE_ROUTES:
        raise PolicyError(f"Unknown role: {role}")
    if type(same_cause_failures) is not int or same_cause_failures < 0:
        raise PolicyError("Failure count must be a nonnegative integer")
    model, effort = BASE_ROUTES[role]
    reason = "base"
    if role == "fixer" and same_cause_failures:
        effort = "high" if same_cause_failures == 1 else "xhigh"
        reason = "same_cause_repeat" if same_cause_failures == 1 else "repeat_tier_exhausted"
    elif role == "executor" and (critical or checkpoint):
        effort, reason = "high", "critical_or_checkpoint"
    elif role in {"planner", "plan_reviewer", "code_reviewer", "integrator"}:
        if critical or checkpoint:
            effort, reason = "xhigh", "critical_or_checkpoint"
    elif role == "researcher" and very_complex:
        effort, reason = "xhigh", "very_complex"
    return Selection(role, model, effort, reason)


def verify_selection(requested: Selection, actual: dict) -> None:
    """Caller must supply runtime evidence, not a worker's self-report."""
    expected = {"model": requested.model, "effort": requested.effort, "harness": "codex"}
    if actual.get("verified_by_platform") is not True or not actual.get("session_id"):
        raise PolicyError("Actual runtime selection has not been verified")
    for key, value in expected.items():
        if actual.get(key) != value:
            raise PolicyError(f"Runtime {key} differs from the admitted policy")
