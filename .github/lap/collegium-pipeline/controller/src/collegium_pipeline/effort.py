"""Observe the real harness process through a pinned first tool call.

This proves client launch configuration, not a provider's internal computation.
The worker's final message is never accepted as configuration evidence.
"""

import ast
import json
import shlex
import textwrap

from .domain import PolicyError, digest, verify_selection

MARKER = "COLLEGIUM_RUNTIME_PROBE="
PROBE_COMMAND = (
    "python3 - <<'PIPELINE_RUNTIME_PROBE'\n"
    + textwrap.dedent("""\
    import glob,json,os
    rows=[]
    for path in sorted(glob.glob('/proc/[0-9]*/cmdline')):
        try:
            args=open(path,'rb').read().decode().split('\\0')
            if 'app-server' not in args or not any('codex' in a for a in args[:2]):
                continue
            settings={}
            for i,a in enumerate(args):
                if a in ('-c','--config') and i+1<len(args):
                    key,sep,value=args[i+1].partition('=')
                    if sep and key in ('model','model_reasoning_effort'):
                        settings[key]=value.strip('"')
            rows.append({'pid':int(path.split('/')[2]),'harness':'codex',
                         'model':settings.get('model'),
                         'effort':settings.get('model_reasoning_effort')})
        except (OSError,ValueError,UnicodeError):
            continue
    print('COLLEGIUM_RUNTIME_PROBE='+json.dumps(rows,sort_keys=True))
""")
    + "PIPELINE_RUNTIME_PROBE"
)

CLAUDE_PROBE_COMMAND = (
    "python3 - <<'PIPELINE_RUNTIME_PROBE'\n"
    + textwrap.dedent("""\
    import glob,json,os
    rows=[]
    for path in sorted(glob.glob('/proc/[0-9]*/cmdline')):
        try:
            args=open(path,'rb').read().decode().split('\\0')
            if os.path.basename(args[0])!='claude' or '--output-format' not in args:
                continue
            settings={}
            for i,a in enumerate(args):
                if a in ('--model','--effort') and i+1<len(args):
                    settings[a[2:]]=args[i+1]
            rows.append({'pid':int(path.split('/')[2]),'harness':'claude-code',
                         'model':settings.get('model'),'effort':settings.get('effort')})
        except (OSError,ValueError,UnicodeError):
            continue
    print('COLLEGIUM_RUNTIME_PROBE='+json.dumps(rows,sort_keys=True))
""")
    + "PIPELINE_RUNTIME_PROBE"
)

# Subscription aliases are resolved by Claude Code. Reject an unknown resolution
# until its effort support is checked; the CLI can silently lower unsupported levels.
CLAUDE_EFFORT_LEVELS = {
    "claude-opus-5-5": {"low", "medium", "high", "xhigh", "max"},
    "claude-sonnet-5-5": {"low", "medium", "high", "xhigh", "max"},
}


def probe_command(harness="codex"):
    if harness not in {"codex", "claude-code"}:
        raise PolicyError("Unknown runtime diagnostic harness")
    return CLAUDE_PROBE_COMMAND if harness == "claude-code" else PROBE_COMMAND


def parse_probe(output: str, *, harness="codex") -> dict:
    if not isinstance(output, str):
        raise PolicyError("Runtime probe output is not text")
    lines = [line for line in output.splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise PolicyError("Runtime probe output missing or ambiguous")
    rows = json.loads(lines[0][len(MARKER) :])
    if not isinstance(rows, list) or len(rows) != 1:
        raise PolicyError("Runtime probe must identify exactly one harness process")
    row = rows[0]
    if not isinstance(row, dict):
        raise PolicyError("Runtime process identity is not an object")
    if type(row.get("pid")) is not int or row["pid"] <= 0 or row.get("harness") != harness:
        raise PolicyError("Invalid runtime process identity")
    levels = {"low", "medium", "high", "xhigh"}
    if harness == "claude-code":
        levels.add("max")
    if not row.get("model") or row.get("effort") not in levels:
        raise PolicyError("Runtime did not expose an explicit supported model/effort")
    return row


def command_text(event: dict, *, harness="codex") -> str:
    arguments = event.get("input")
    if not isinstance(arguments, dict):
        raise PolicyError("Shell event arguments are not an object")
    value = arguments.get("command")
    if not isinstance(value, str):
        raise PolicyError("Shell event has no command")
    if harness == "claude-code":
        if event.get("name") != "Bash":
            raise PolicyError("Claude runtime diagnostic must use Bash")
        return value
    args = shlex.split(value)
    if len(args) != 3 or args[:2] not in (["/bin/bash", "-c"], ["bash", "-c"]):
        raise PolicyError("Unexpected command wrapper")
    return args[2]


def commands_equal(expected: str, actual: str) -> bool:
    """Permit Python formatting only when the quoted shell frame is unchanged."""
    if expected == actual:
        return True
    left = expected.rstrip("\n").splitlines()
    right = actual.rstrip("\n").splitlines()
    if len(left) < 3 or len(right) < 3 or left[0] != right[0] or left[-1] != right[-1]:
        return False
    if not left[0].startswith("python3 - <<'"):
        return False
    try:
        return ast.dump(ast.parse("\n".join(left[1:-1]))) == ast.dump(
            ast.parse("\n".join(right[1:-1]))
        )
    except SyntaxError:
        return False


def tool_result(observation: dict, command: str, *, index: int, harness="codex"):
    uses = [e for e in observation["events"] if e.get("type") == "agent.tool_use"]
    if len(uses) <= index or not commands_equal(
        command, command_text(uses[index], harness=harness)
    ):
        raise PolicyError("Required tool command is missing, modified or out of order")
    use = uses[index]
    results = [
        e
        for e in observation["events"]
        if e.get("type") == "agent.tool_result" and e.get("tool_use_id") == use.get("tool_use_id")
    ]
    if len(results) != 1 or not use.get("tool_use_id"):
        raise PolicyError("Tool result identity is missing or ambiguous")
    result = results[0]
    if harness == "claude-code":
        # Claude emits Bash's content/is_error rather than Codex's exit_code/output.
        # Do not manufacture an exit code. Pinned scripts also emit their own
        # success marker; validation subprocess statuses are printed by checkout.
        if result.get("is_error") is not False or (
            "exit_code" in result and result["exit_code"] != 0
        ):
            raise PolicyError("Claude Bash command failed or omitted completion status")
        content = result.get("content")
        if isinstance(content, str):
            output = content
        elif isinstance(content, list) and all(
            isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str)
            for p in content
        ):
            output = "\n".join(p["text"] for p in content)
        else:
            raise PolicyError("Claude Bash result omitted text content")
        return use, {**result, "output": output}
    if result.get("is_error") is not False or type(result.get("exit_code")) is not int:
        raise PolicyError("Tool did not provide a verified exit status")
    if result["exit_code"] != 0:
        raise PolicyError("Required tool command failed")
    return use, result


def runtime_evidence(observation: dict, binding, *, session_id, turn_id):
    """Consume authenticated platform observations, never a worker's result JSON."""
    session, turn = observation["session"], observation["turn"]
    if (
        session.get("id") != session_id
        or turn.get("session_id") != session_id
        or turn.get("id") != turn_id
        or session.get("agent_id") != binding.agent_id
        or session.get("project_id") != binding.project_id
    ):
        raise PolicyError("Runtime observation belongs to another session, turn or worker")
    if (
        turn.get("status") != "completed"
        or turn.get("cut_off") is not False
        or turn.get("error") is not None
    ):
        raise PolicyError("Turn did not finish cleanly")
    if (
        session.get("harness") != binding.harness
        or session.get("runtime") != binding.runtime
        or not session.get("harness_release", "").startswith(binding.harness + "-")
    ):
        raise PolicyError("Runtime did not acknowledge the bound harness")
    users = [e for e in observation["events"] if e.get("type") == "user.message"]
    if len(users) != 1:
        raise PolicyError("Runtime evidence requires a fresh single-turn session")
    trace = turn.get("trace_id")
    if not trace or not users[0].get("traceparent", "").startswith("00-" + trace + "-"):
        raise PolicyError("Observation is not correlated with the admitted turn trace")
    command = probe_command(binding.harness)
    use, result = tool_result(observation, command, index=0, harness=binding.harness)
    process = parse_probe(result.get("output", ""), harness=binding.harness)
    if process["model"] != binding.api_model:
        raise PolicyError("Actual process model differs from the bound API model")
    evidence = {
        "verified_by_platform": True,
        "harness": binding.harness,
        "model": binding.selection.model,
        "effort": process["effort"],
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": binding.agent_id,
        "harness_release": session["harness_release"],
        "runtime": binding.runtime,
        "proof_kind": "first_tool_" + binding.harness.replace("-", "_") + "_process_arguments",
        "process_id": process["pid"],
        "tool_use_id": use["tool_use_id"],
        "tool_result_event_id": result["id"],
        "command_digest": digest(command),
        "command_normalization": "same_python_ast_and_pinned_shell_frame",
    }
    if binding.model_connection_id:
        evidence["model_connection_id"] = binding.model_connection_id
    if binding.harness == "claude-code":
        if any(
            e.get("parent_tool_use_id")
            or (
                e.get("type") == "agent.tool_use" and e.get("name") in {"Agent", "Task", "Workflow"}
            )
            for e in observation["events"]
        ):
            raise PolicyError("Stage workers may not delegate outside the controller's budget")
        idle = [e for e in observation["events"] if e.get("type") == "session.status_idle"]
        models = idle[-1].get("usage", {}).get("models", {}) if idle else {}
        if not isinstance(models, dict) or len(models) != 1:
            raise PolicyError("Claude served-model telemetry is absent or ambiguous")
        served = next(iter(models))
        if not served.startswith("claude-" + binding.api_model + "-") or process[
            "effort"
        ] not in CLAUDE_EFFORT_LEVELS.get(served, set()):
            raise PolicyError("Claude served model or its effort support is not approved")
        evidence.update(
            served_model=served,
            effort_verification="explicit_launch_argument_and_supported_served_model",
            provider_internal_reasoning_verified=False,
        )
    verify_selection(binding.selection, evidence)
    return evidence
