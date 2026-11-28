"""Deterministic investigation routing and conservative, evidence-bound complexity."""

import json

from .capacity import checked_paths
from .domain import PolicyError, Selection, digest

PERSPECTIVES = ("current_system", "alternatives", "constraints", "risks")
DIMENSIONS = ("scope", "uncertainty", "contracts", "security", "persistence", "concurrency")
LEVELS = ("simple", "standard", "complex", "critical")
REVIEW_CHECKS = ("coverage", "sources", "uncertainty", "alternatives", "risks", "decomposition")


def variants():
    return [
        Selection(role, model, effort, "investigation_policy/v1")
        for role, routes in (
            ("assessor", [("sonnet", "low")]),
            (
                "researcher",
                [("sonnet", "low"), ("sonnet", "high"), ("opus", "high"), ("opus", "max")],
            ),
            ("synthesizer", [("sonnet", "high"), ("opus", "high"), ("opus", "max")]),
            ("investigation_reviewer", [("opus", "high"), ("opus", "max")]),
        )
        for model, effort in routes
    ]


def binding_key(selection):
    return ":".join((selection.role, selection.model, selection.effort))


def route(stage, level="standard"):
    if level not in LEVELS:
        raise PolicyError("Unknown investigation complexity")
    if stage == "assessing":
        role, model, effort = "assessor", "sonnet", "low"
    elif stage == "researching":
        role = "researcher"
        model, effort = {
            "simple": ("sonnet", "low"),
            "standard": ("sonnet", "high"),
            "complex": ("opus", "high"),
            "critical": ("opus", "max"),
        }[level]
    elif stage == "synthesizing":
        role, model, effort = (
            "synthesizer",
            "sonnet" if level == "simple" else "opus",
            "max" if level == "critical" else "high",
        )
    elif stage == "investigation_review":
        role, model, effort = (
            "investigation_reviewer",
            "opus",
            "max" if level == "critical" else "high",
        )
    else:
        raise PolicyError("Unknown investigation stage")
    return Selection(role, model, effort, "investigation_policy/v1")


def validate_policy(policy):
    if (
        not isinstance(policy, dict)
        or set(policy)
        != {"schema_version", "source_paths", "parallelism", "max_jobs", "minimum_complexity"}
        or policy["schema_version"] != "investigation-policy/v1"
    ):
        raise PolicyError("Invalid investigation policy fields")
    checked_paths(policy["source_paths"], policy["source_paths"])
    if type(policy["parallelism"]) is not int or not 1 <= policy["parallelism"] <= 4:
        raise PolicyError("Investigation parallelism must be1..4")
    if type(policy["max_jobs"]) is not int or not 7 <= policy["max_jobs"] <= 32:
        raise PolicyError("Investigation worker budget must be7..32")
    if policy["minimum_complexity"] not in LEVELS:
        raise PolicyError("Invalid minimum complexity")


def cited(claim, sources):
    if not isinstance(claim, dict) or set(claim) not in (
        {"text", "citations"},
        {"text", "citations", "environments"},
    ):
        raise PolicyError("Findings need text and independently checked citations")
    if not isinstance(claim["text"], str) or not claim["text"].strip() or len(claim["text"]) > 8000:
        raise PolicyError("Invalid finding text")
    refs = claim["citations"]
    if not isinstance(refs, list) or not refs or len(refs) > 16:
        raise PolicyError("A factual finding needs registered source citations")
    catalog = {s["id"]: s for s in sources}
    environments = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) not in (
            {"source_id", "start", "end", "quote"},
            {"source_id", "start", "end", "quote", "environment"},
        ):
            raise PolicyError("Invalid citation fields")
        source = catalog.get(ref["source_id"])
        if not source or type(ref["start"]) is not int or type(ref["end"]) is not int:
            raise PolicyError("Citation source or line bounds are absent")
        if source.get("kind") == "mcp":
            if ref.get("environment") != source["environment"]:
                raise PolicyError(
                    "MCP citation environment differs from pinned DEV/PROD/SHARED source"
                )
            environments.add(source["environment"])
        elif "environment" in ref:
            raise PolicyError("Git evidence has no asserted service environment")
        if not source["start"] <= ref["start"] <= ref["end"] <= source["end"]:
            raise PolicyError("Citation leaves captured source bounds")
        lines = source["text"].splitlines()
        quote = "\n".join(lines[ref["start"] - source["start"] : ref["end"] - source["start"] + 1])
        if not quote.strip() or ref["quote"] != quote:
            raise PolicyError(
                "Citation quote differs from the pinned source: "
                + json.dumps(
                    {
                        "source_id": ref["source_id"],
                        "start": ref["start"],
                        "end": ref["end"],
                        "expected_quote": quote,
                    }
                )
            )
    if environments and claim.get("environments") != sorted(environments):
        raise PolicyError("MCP facts must explicitly label the exact cited environment set")
    if not environments and "environments" in claim:
        raise PolicyError("Cannot assert a service environment from Git-only evidence")
    return claim


def assessment(payload, sources, flags, minimum):
    if not isinstance(payload, dict) or set(payload) != {"dimensions", "confidence", "rationale"}:
        raise PolicyError("Invalid complexity assessment")
    values = payload["dimensions"]
    if not isinstance(values, dict) or set(values) != set(DIMENSIONS):
        raise PolicyError("Complexity must cover every dimension")
    for item in values.values():
        if (
            not isinstance(item, dict)
            or set(item) != {"score", "evidence"}
            or type(item["score"]) is not int
            or not 0 <= item["score"] <= 3
        ):
            raise PolicyError("Complexity dimension score must be0..3")
        cited(item["evidence"], sources)
    if (
        type(payload["confidence"]) not in (int, float)
        or not 0 <= payload["confidence"] <= 1
        or not isinstance(payload["rationale"], str)
        or not payload["rationale"].strip()
    ):
        raise PolicyError("Assessment needs bounded confidence and rationale")
    score = sum(d["score"] for d in values.values())
    rank = 0 if score <= 3 else 1 if score <= 8 else 2 if score <= 14 else 3
    floors = {"security": 3, "data_migration": 3, "public_api": 2, "concurrency": 2, "unknowns": 2}
    rank = max(rank, LEVELS.index(minimum), *[floors[f] for f in flags])
    dimension_floors = {
        name: floor
        for name, floor in {
            "security": 3,
            "persistence": 3,
            "contracts": 2,
            "concurrency": 2,
            "uncertainty": 2,
        }.items()
        if values[name]["score"] >= 2
    }
    rank = max(rank, *dimension_floors.values()) if dimension_floors else rank
    if payload["confidence"] < 0.6:
        rank = max(rank, 2)
    return {
        **payload,
        "score": score,
        "complexity": LEVELS[rank],
        "routing_reason": {
            "policy": "investigation-policy/v1",
            "risk_floors": flags,
            "dimension_floors": dimension_floors,
            "minimum": minimum,
        },
        "evidence_digest": digest(sources),
    }
