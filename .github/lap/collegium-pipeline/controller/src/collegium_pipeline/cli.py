"""Explicit local commands; admission never launches an agent implicitly."""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .adapters import Github
from .config import config_digest, load_config
from .doctor import doctor
from .domain import Task, digest, select_model
from .quality import verify_checks, verify_pr
from .store import Journal


def main(argv=None, *, recovery=None):
    parser = argparse.ArgumentParser(prog="collegium-pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "prepare-text", "verify-pr", "status", "recheck-result"):
        command = commands.add_parser(name)
        command.add_argument("--config", default="config/pilot.json")
        if name in {"prepare-text", "status", "recheck-result"}:
            command.add_argument("--journal", required=True)
        if name == "prepare-text":
            command.add_argument("--title", required=True)
            command.add_argument("--requirements-file", type=Path, required=True)
            command.add_argument("--task-id")
        elif name == "verify-pr":
            command.add_argument("--number", type=int, required=True)
        elif name in {"status", "recheck-result"}:
            command.add_argument("--run-id", required=True)
            if name == "recheck-result":
                command.add_argument("--reason", required=True)
    route = commands.add_parser("explain-route")
    route.add_argument("role")
    route.add_argument("--critical", action="store_true")
    route.add_argument("--same-cause-failures", type=int, default=0)
    selftest = commands.add_parser("self-test")
    selftest.add_argument("--config", default="config/readiness.json")
    selftest.add_argument("--journal", default=".local/controller.sqlite3")
    selftest.add_argument("--artifacts", default=".local/artifacts")
    selftest.add_argument("--task-id", default="controller-readiness-v1")
    selftest.add_argument("--run-id")
    selftest.add_argument("--once", action="store_true")
    selftest.add_argument("--timeout", type=int, default=900)
    delivery = commands.add_parser("deliver")
    delivery.add_argument("--config", default="config/delivery.example.json")
    delivery.add_argument("--journal", required=True)
    delivery.add_argument("--artifacts", default=".local/delivery-artifacts")
    delivery.add_argument("--run-id", required=True)
    delivery.add_argument("--once", action="store_true")
    delivery.add_argument("--timeout", type=int, default=3600)
    delivery.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "explain-route":
            result = asdict(
                select_model(
                    args.role, critical=args.critical, same_cause_failures=args.same_cause_failures
                )
            )
        else:
            config = load_config(args.config)
            if args.command == "deliver":
                from .credentials import local_platform
                from .delivery import Delivery, serial_lock
                from .native_broker import github_broker

                if (
                    not args.live
                    or args.timeout <= 0
                    or not Path(args.journal).is_file()
                    or not config.get("execution_enabled")
                    or not config.get("broker_enabled")
                    or config.get("execution_profile", "delivery") != "delivery"
                ):
                    raise ValueError(
                        "Delivery needs --live, a positive timeout and an existing admitted journal"
                    )
                with serial_lock(args.journal):
                    journal = Journal(args.journal)
                    try:
                        if recovery is not None:
                            from .recovery import Checkpoints, WriteAhead

                            http, key, identity = recovery
                            if identity["automation_id"] != config.get("recovery_store", {}).get(
                                "owner"
                            ):
                                raise ValueError("Recovery owner differs from the cloud controller")
                            journal.before_effect = WriteAhead(
                                config,
                                journal,
                                args.artifacts,
                                Checkpoints(config, http, key),
                                identity,
                            ).save
                            journal.before_effect({"kind": "tick", "run_id": args.run_id})
                        coordinator = Delivery(
                            config,
                            journal,
                            github_broker(config, local_platform(), journal, args.run_id),
                            local_platform(),
                            args.artifacts,
                        )
                        deadline = time.monotonic() + args.timeout
                        while time.monotonic() < deadline:
                            result = coordinator.step(args.run_id)
                            print(
                                json.dumps(
                                    {k: result[k] for k in ("run_id", "state", "head", "cycle")}
                                ),
                                flush=True,
                            )
                            if result["state"] == "ready_for_acceptance":
                                return 0
                            if result["state"] in {"failed", "blocked"}:
                                return 2
                            if args.once:
                                return 0
                            time.sleep(2)
                        coordinator.stop(args.run_id, "CLI timeout")
                        return 2
                    except KeyboardInterrupt:
                        coordinator.stop(args.run_id, "Operator interrupt")
                        return 130
                    finally:
                        journal.close()
            if args.command == "self-test":
                from .credentials import local_platform
                from .runner import Runner

                if args.timeout <= 0:
                    raise ValueError("Timeout must be positive")
                Path(args.journal).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                journal = Journal(args.journal)
                runner = Runner(config, journal, local_platform(), args.artifacts)
                try:
                    run_id = args.run_id or runner.prepare_readiness(args.task_id)
                    deadline = time.monotonic() + args.timeout
                    while time.monotonic() < deadline:
                        result = runner.step(run_id)
                        if result.get("action") not in {"waiting", "settling"}:
                            print(json.dumps(result), flush=True)
                        if result["state"] == "self_test_passed":
                            return 0
                        if result["state"] in {"failed", "cancelled", "reconciling"}:
                            return 2
                        if args.once:
                            return 0
                        time.sleep(2)
                    runner.stop(run_id, "coordinator_timeout")
                    return 2
                except KeyboardInterrupt:
                    if "run_id" in locals():
                        runner.stop(run_id, "operator_interrupt")
                    return 130
                finally:
                    journal.close()
            if args.command == "doctor":
                result = doctor(config)
                print(json.dumps(result, indent=2))
                return 0 if result["execution_ready"] else 2
            if args.command == "prepare-text":
                requirements = args.requirements_file.read_text()
                source_id = args.task_id or digest(
                    {"title": args.title, "requirements": requirements}
                )
                task = Task("text", source_id, config["repository"], args.title, requirements)
                journal = Journal(args.journal)
                try:
                    run_id = journal.admit(task, config_digest(config))
                    state = journal.get(run_id)["state"]
                finally:
                    journal.close()
                result = {
                    "run_id": run_id,
                    "state": state,
                    "agent_started": False,
                    "mode": config["mode"],
                    "acceptance_digest": task.acceptance_digest,
                }
            elif args.command in {"status", "recheck-result"}:
                if not Path(args.journal).is_file():
                    raise ValueError("Journal does not exist")
                journal = Journal(args.journal)
                try:
                    if args.command == "recheck-result":
                        journal.recheck_result(
                            args.run_id, journal.get(args.run_id)["version"], args.reason
                        )
                    result = journal.get(args.run_id)
                    result["events"] = journal.events(args.run_id)
                    if journal.connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='deliveries'"
                    ).fetchone():
                        row = journal.connection.execute(
                            "SELECT document FROM deliveries WHERE run_id=?", (args.run_id,)
                        ).fetchone()
                        if row:
                            result["delivery"] = json.loads(row[0])
                finally:
                    journal.close()
            else:
                pr, checks, statuses = Github(config["repository"]).pr_evidence(args.number)
                verify_pr(
                    pr,
                    repository_id=config["repository_id"],
                    head=pr["head"]["sha"],
                    base=pr["base"]["sha"],
                )
                verify_checks(
                    checks, statuses, head=pr["head"]["sha"], required=config["required_checks"]
                )
                result = {
                    "pr": pr["html_url"],
                    "head": pr["head"]["sha"],
                    "base": pr["base"]["sha"],
                    "ci_passed": True,
                    "independent_code_review": "not_evaluated",
                    "run_advanced": False,
                }
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
