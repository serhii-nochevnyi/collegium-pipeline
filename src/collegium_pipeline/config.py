"""Validated operational configuration for the first local prototype."""

import json
import math
import re
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
    "broker_transport",
    "native_broker",
    "repair_pr_mode",
    "model_policy",
    "model_connection",
    "model_connection_id",
    "service_test",
    "repair_validation_commands",
    "broker_reads",
    "broker_allow_paused_triggers",
    "broker_compress_requests",
}


def load_config(path: str | Path) -> dict:
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict) or set(config) - FIELDS:
        raise PolicyError("Unknown pilot configuration fields")
    if config.get("schema_version") != "pilot/v1" or config.get("mode") != "local_serial_prototype":
        raise PolicyError("Only the explicit local serial prototype is supported")
    if config.get("execution_profile", "delivery") not in {"delivery", "readiness"}:
        raise PolicyError("Unknown execution profile")
    if config.get("model_policy", "codex") not in {"codex", "claude"}:
        raise PolicyError("Unknown model policy")
    if config.get("model_policy") == "claude" and (
        not isinstance(config.get("model_connection"), str)
        or not config["model_connection"].startswith("project/")
        or not isinstance(config.get("model_connection_id"), str)
        or not config["model_connection_id"].startswith("mcn_")
    ):
        raise PolicyError("Claude requires an explicit project model connection and identity")
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
        if "repair_validation_commands" in config:
            commands = config["repair_validation_commands"]
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
                raise PolicyError("Explicit repair validation argv commands are required")
        if config["broker_enabled"] and (
            not config["execution_enabled"]
            or config.get("execution_profile", "delivery") != "delivery"
        ):
            raise PolicyError("Write broker requires enabled delivery profile")
    transport = config.get("broker_transport", "environment")
    if transport not in {"environment", "collegium_script"}:
        raise PolicyError("Unknown broker transport")
    if config.get("broker_reads", "native_script") not in {"native_script", "local_gh"}:
        raise PolicyError("Unknown broker read transport")
    if type(config.get("broker_allow_paused_triggers", False)) is not bool:
        raise PolicyError("broker_allow_paused_triggers must be boolean")
    if type(config.get("broker_compress_requests", False)) is not bool:
        raise PolicyError("broker_compress_requests must be boolean")
    if config.get("repair_pr_mode", "draft") not in {"draft", "keep_ready"}:
        raise PolicyError("Unknown repair PR mode")
    if transport == "collegium_script":
        binding = config.get("native_broker")
        if (
            not isinstance(binding, dict)
            or set(binding) != {"automation_id", "approved_digest"}
            or not isinstance(binding["automation_id"], str)
            or not binding["automation_id"].startswith("aut_")
            or not isinstance(binding["approved_digest"], str)
            or len(binding["approved_digest"]) != 64
        ):
            raise PolicyError("A pinned native broker binding is required")
        if config.get("repair_pr_mode") != "keep_ready":
            raise PolicyError(
                "Native egress requires keep_ready; GraphQL draft transitions are unavailable"
            )
    if "service_test" in config:
        gate = config["service_test"]
        if (
            not isinstance(gate, dict)
            or set(gate)
            != {
                "initial_changes_digest",
                "repaired_changes_digest",
                "check_name",
                "failure_signature",
                "test_name",
            }
            or any(not isinstance(v, str) or not v for v in gate.values())
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", gate[k])
                for k in ("initial_changes_digest", "repaired_changes_digest")
            )
            or gate["initial_changes_digest"] == gate["repaired_changes_digest"]
            or gate["check_name"] not in config["required_checks"]
            or not config.get("repair_validation_commands")
        ):
            raise PolicyError(
                "Service test requires exact distinct fixture digests and CI diagnostic"
            )
    return config


def config_digest(config: dict) -> str:
    return digest(config)
