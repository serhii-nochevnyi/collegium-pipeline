"""Validated operational configuration for the first local prototype."""

import json
import math
from pathlib import Path

from .domain import PolicyError, digest

FIELDS = {
    "schema_version",
    "mode",
    "server",
    "mcp_endpoint",
    "space_id",
    "project_id",
    "github_connection_id",
    "repository",
    "repository_id",
    "base_branch",
    "required_checks",
    "workers",
    "execution_enabled",
    "max_cost_usd",
    "max_repair_attempts",
    "execution_profile",
    "max_stage_seconds",
    "max_stage_attempts",
    "max_total_tokens",
    "broker_enabled",
    "allowed_paths",
    "validation_commands",
    "ci_timeout_seconds",
    "max_delivery_seconds",
    "max_worker_jobs",
}


def load_config(path: str | Path) -> dict:
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict) or set(config) - FIELDS:
        raise PolicyError("Unknown pilot configuration fields")
    if config.get("schema_version") != "pilot/v1" or config.get("mode") != "local_serial_prototype":
        raise PolicyError("Only the explicit local serial prototype is supported")
    if config.get("execution_profile", "delivery") not in {"delivery", "readiness"}:
        raise PolicyError("Unknown execution profile")
    if config.get("server") != "https://agentic-platform.infrateam.xyz":
        raise PolicyError("No credentials are forwarded to an unverified server")
    if config.get("mcp_endpoint") != "https://agentic-platform-mcp.infrateam.xyz/mcp":
        raise PolicyError("Unverified Collegium MCP endpoint")
    for field in ("space_id", "project_id", "github_connection_id", "repository", "base_branch"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise PolicyError(f"Missing configuration: {field}")
    if type(config.get("repository_id")) is not int or config["repository_id"] <= 0:
        raise PolicyError("Immutable repository ID is required")
    if type(config.get("execution_enabled")) is not bool:
        raise PolicyError("execution_enabled must be a boolean")
    if not isinstance(config.get("workers"), dict):
        raise PolicyError("workers must be an explicit role mapping")
    checks = config.get("required_checks")
    if (
        not isinstance(checks, list)
        or not checks
        or any(not isinstance(c, str) or not c for c in checks)
    ):
        raise PolicyError("An explicit nonempty CI check list is required")
    if type(config.get("max_repair_attempts")) is not int or config["max_repair_attempts"] < 0:
        raise PolicyError("Invalid repair limit")
    limit = config.get("max_cost_usd")
    if limit is not None and (
        type(limit) not in (int, float) or not math.isfinite(limit) or limit <= 0
    ):
        raise PolicyError("Cost ceiling must be positive")
    if config["execution_enabled"] and (limit is None or not config["workers"]):
        raise PolicyError("Execution requires workers and an explicit cost ceiling")
    for field in (
        "max_stage_seconds",
        "max_stage_attempts",
        "max_total_tokens",
        "ci_timeout_seconds",
        "max_delivery_seconds",
        "max_worker_jobs",
    ):
        if field in config and (type(config[field]) is not int or config[field] <= 0):
            raise PolicyError(f"{field} must be a positive integer")
    if "broker_enabled" in config:
        if type(config["broker_enabled"]) is not bool:
            raise PolicyError("broker_enabled must be boolean")
        paths = config.get("allowed_paths")
        commands = config.get("validation_commands")
        if (
            not isinstance(paths, list)
            or not paths
            or any(
                not isinstance(p, str)
                or not p
                or p.startswith("/")
                or ".." in p.split("/")
                or ".git" in p.split("/")
                for p in paths
            )
        ):
            raise PolicyError("Explicit allowed file paths/prefixes are required")
        if (
            not isinstance(commands, list)
            or not commands
            or any(
                not isinstance(c, list)
                or not c
                or any(not isinstance(v, str) or not v or "\x00" in v for v in c)
                for c in commands
            )
        ):
            raise PolicyError("Explicit validation argv commands are required")
        if config["broker_enabled"] and (
            not config["execution_enabled"]
            or config.get("execution_profile", "delivery") != "delivery"
        ):
            raise PolicyError("Write broker requires enabled delivery profile")
    return config


def config_digest(config: dict) -> str:
    return digest(config)
