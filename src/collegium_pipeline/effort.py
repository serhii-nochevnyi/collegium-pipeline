"""Observe the real Codex process through a pinned first tool call.

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


def parse_probe(output: str) -> dict:
    if not isinstance(output, str):
        raise PolicyError("Runtime probe output is not text")
    lines = [line for line in output.splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise PolicyError("Runtime probe output missing or ambiguous")
    rows = json.loads(lines[0][len(MARKER) :])
    if not isinstance(rows, list) or len(rows) != 1:
        raise PolicyError("Runtime probe must identify exactly one Codex app-server")
    row = rows[0]
    if not isinstance(row, dict):
        raise PolicyError("Runtime process identity is not an object")
    if type(row.get("pid")) is not int or row["pid"] <= 0 or row.get("harness") != "codex":
        raise PolicyError("Invalid runtime process identity")
    if not row.get("model") or row.get("effort") not in {"low", "medium", "high", "xhigh"}:
        raise PolicyError("Runtime did not expose an explicit supported model/effort")
    return row


def command_text(event: dict) -> str:
    arguments = event.get("input")
    if not isinstance(arguments, dict):
        raise PolicyError("Shell event arguments are not an object")
    value = arguments.get("command")
    if not isinstance(value, str):
        raise PolicyError("Shell event has no command")
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


def tool_result(observation: dict, command: str, *, index: int):
    uses = [e for e in observation["events"] if e.get("type") == "agent.tool_use"]
    if len(uses) <= index or not commands_equal(command, command_text(uses[index])):
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
        session.get("harness") != "codex"
        or session.get("runtime") != binding.runtime
        or not session.get("harness_release", "").startswith("codex-")
    ):
        raise PolicyError("Runtime did not acknowledge Codex")
    users = [e for e in observation["events"] if e.get("type") == "user.message"]
    if len(users) != 1:
        raise PolicyError("Runtime evidence requires a fresh single-turn session")
    trace = turn.get("trace_id")
    if not trace or not users[0].get("traceparent", "").startswith("00-" + trace + "-"):
        raise PolicyError("Observation is not correlated with the admitted turn trace")
    use, result = tool_result(observation, PROBE_COMMAND, index=0)
    process = parse_probe(result.get("output", ""))
    if process["model"] != binding.api_model:
        raise PolicyError("Actual Codex process model differs from the bound API model")
    evidence = {
        "verified_by_platform": True,
        "harness": "codex",
        "model": binding.selection.model,
        "effort": process["effort"],
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": binding.agent_id,
        "harness_release": session["harness_release"],
        "runtime": binding.runtime,
        "proof_kind": "first_tool_codex_process_arguments",
        "process_id": process["pid"],
        "tool_use_id": use["tool_use_id"],
        "tool_result_event_id": result["id"],
        "command_digest": digest(PROBE_COMMAND),
        "command_normalization": "same_python_ast_and_pinned_shell_frame",
    }
    verify_selection(binding.selection, evidence)
    return evidence
