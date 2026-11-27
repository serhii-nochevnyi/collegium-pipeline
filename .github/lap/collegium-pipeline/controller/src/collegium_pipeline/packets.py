"""Deterministic readiness task and commands; never execute generated code locally."""

import base64
import json

from .domain import PolicyError
from .effort import probe_command

REQUIREMENTS = (
    "Implement normalize_names(values) in solution.py. Accept a list of strings; trim each, "
    "drop empty strings, lowercase, deduplicate, and return lexicographically sorted names. "
    "Do not mutate the input. Raise TypeError for a non-list input or any non-string element. "
    "This is a synthetic sandbox task; do not read or write the connected repository."
)


def validation_command(candidate):
    files = candidate.get("files")
    if (
        not isinstance(files, dict)
        or set(files) != {"solution.py"}
        or not isinstance(files["solution.py"], str)
        or len(files["solution.py"]) > 12000
    ):
        raise PolicyError("Readiness implementation must contain only bounded solution.py")
    source = base64.b64encode(files["solution.py"].encode()).decode()
    return "python3 - <<'PIPELINE_VALIDATION'\n" + (
        "import base64,json,runpy,tempfile\nfrom pathlib import Path\n"
        "with tempfile.TemporaryDirectory() as folder:\n"
        f"    path=Path(folder)/'solution.py';path.write_bytes(base64.b64decode('{source}'))\n"
        "    f=runpy.run_path(str(path))['normalize_names']\n"
        "    values=[' Bob ','ALICE','bob',' ','alice'];original=values.copy()\n"
        "    assert f(values)==['alice','bob'] and values==original\n"
        "    assert f([])==[] and f([' X ','x','Y'])==['x','y']\n"
        "    for bad in ('abc',None,[1],['ok',None]):\n"
        "        try:f(bad)\n"
        "        except TypeError:pass\n"
        "        else:raise AssertionError('TypeError required')\n"
        "print('COLLEGIUM_VALIDATION='+json.dumps({'passed':True,'cases':7}))\n"
        "PIPELINE_VALIDATION"
    )


def readiness_packet(run_id, stage, role, revision, *, subject=None, harness="codex"):
    instructions = {
        "planning": (
            "Produce a concise implementation and test plan. "
            "payload must contain plan and acceptance lists."
        ),
        "plan_review": (
            "Independently review the supplied plan against requirements. "
            "Return findings; do not write code."
        ),
        "implementing": (
            "Implement the function. payload must be {files:{'solution.py':source text}}. "
            "Do not clone or push anything."
        ),
        "validating": (
            "After runtime_probe_command, execute validation_command exactly as your second "
            "tool call. Do not substitute your own tests. Report its real outcome."
        ),
        "reviewing": (
            "Independently review the supplied implementation and observed validation against "
            "requirements. Return blocking findings or an empty list. "
            "Do not rewrite the implementation."
        ),
    }
    packet = {
        "schema_version": "worker-packet/v1",
        "kind": "readiness",
        "run_id": run_id,
        "stage": stage,
        "role": role,
        "revision": revision,
        "runtime_probe_command": probe_command(harness),
        "instructions": instructions[stage],
        "requirements": REQUIREMENTS,
        "result_schema": {
            "schema_version": "worker-result/v1",
            "run_id": run_id,
            "stage": stage,
            "revision": revision,
            "verdict": "pass or fail",
            "summary": "Brief factual summary",
            "payload": {},
            "blocking_findings": [],
            "subject_artifact_digest": subject["digest"] if subject else None,
        },
    }
    if subject:
        packet["subject"] = subject
    if stage == "validating":
        packet["validation_command"] = validation_command(subject["result"]["payload"])
    return json.dumps(packet, sort_keys=True)
