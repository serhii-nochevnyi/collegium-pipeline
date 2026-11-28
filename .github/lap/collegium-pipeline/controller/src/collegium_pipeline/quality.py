"""Strict acceptance of independently observed revision-bound quality evidence."""

from dataclasses import dataclass

from .domain import PolicyError, Revision


@dataclass(frozen=True)
class Review:
    revision: Revision
    reviewer_session: str
    executor_session: str
    verdict: str
    blocking_findings: int


def verify_review(review: Review, current: Revision) -> None:
    if review.revision != current:
        raise PolicyError("Review is stale: code, base, acceptance or policy changed")
    if not review.reviewer_session or not review.executor_session:
        raise PolicyError("Review and executor identities are required")
    if review.reviewer_session == review.executor_session:
        raise PolicyError("Independent review requires a separate session")
    if review.verdict != "pass" or review.blocking_findings != 0:
        raise PolicyError("Review has not passed")


def verify_checks(
    checks: list[dict], statuses: list[dict], *, head: str, required: list[str]
) -> None:
    if not required or any(not isinstance(name, str) or not name for name in required):
        raise PolicyError("Explicit required CI checks must be configured")
    # Preserve separate Apps' runs even when their display names match. A passing
    # duplicate from one App must not conceal a failure from another.
    latest = {}
    for check in checks:
        key = (check["name"], (check.get("app") or {}).get("id"))
        if check.get("id", 0) > latest.get(key, {}).get("id", -1):
            latest[key] = check
    legacy = {}
    for status in statuses:
        if status.get("id", 0) > legacy.get(status["context"], {}).get("id", -1):
            legacy[status["context"]] = status
    for name in required:
        matching = [c for (n, _), c in latest.items() if n == name]
        if name in legacy:
            matching.append(legacy[name])
        if not matching:
            raise PolicyError(f"Required check is missing: {name}")
        for check in matching:
            if "context" in check:
                if check.get("sha") != head or check.get("state") != "success":
                    raise PolicyError(f"Required commit status is stale or failing: {name}")
            elif (
                check.get("head_sha") != head
                or check.get("status") != "completed"
                or check.get("conclusion") != "success"
            ):
                raise PolicyError(f"Required check is stale, pending or failing: {name}")


def verify_pr(pr: dict, *, repository_id: int, head: str, base: str) -> None:
    if pr.get("state") != "open" or pr.get("draft") is not False:
        raise PolicyError("PR must be open and ready for review")
    if pr.get("head", {}).get("sha") != head or pr.get("base", {}).get("sha") != base:
        raise PolicyError("PR revision changed")
    if pr.get("base", {}).get("repo", {}).get("id") != repository_id:
        raise PolicyError("PR belongs to a different target repository")
    if pr.get("mergeable") is not True:
        raise PolicyError("PR mergeability is unknown or conflicting")
