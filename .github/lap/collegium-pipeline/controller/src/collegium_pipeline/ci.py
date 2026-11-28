"""Classify exact-head CI without turning pending/approval states into code fixes."""

import re

from .domain import digest
from .quality import verify_checks


def inspect_ci(checks, statuses, *, head, required):
    try:
        verify_checks(checks, statuses, head=head, required=required)
        return {"state": "green", "failures": [], "fingerprint": None}
    except ValueError:
        pass
    latest = {}
    for row in checks:
        key = (row["name"], (row.get("app") or {}).get("id"))
        if row.get("id", 0) > latest.get(key, {}).get("id", -1):
            latest[key] = row
    legacy = {}
    for row in statuses:
        if row.get("id", 0) > legacy.get(row["context"], {}).get("id", -1):
            legacy[row["context"]] = row
    failures, waiting, blocked = [], False, False
    for name in required:
        matching = [r for (n, _), r in latest.items() if n == name]
        if name in legacy:
            matching.append(legacy[name])
        if not matching:
            waiting = True
        for row in matching:
            if row.get("head_sha", row.get("sha")) != head:
                blocked = True
                continue
            state = row.get("state") if "context" in row else row.get("conclusion")
            if "context" not in row and row.get("status") != "completed":
                waiting = True
            elif state in {"failure", "error", "timed_out"}:
                failures.append(
                    {
                        "name": name,
                        "app_id": (row.get("app") or {}).get("id"),
                        "id": row["id"],
                        "conclusion": state,
                        "output": row.get("output", {}),
                        "description": row.get("description", ""),
                    }
                )
            elif state == "pending":
                waiting = True
            elif state not in {"success"}:
                blocked = True
    if blocked:
        state = "blocked"
    elif waiting:
        state = "waiting"
    else:
        state = "red"

    def cause(failure):
        output = failure.get("output") or {}
        text = str(output.get("title", "")) + "\n" + str(output.get("summary", ""))
        text = re.sub(r"\b[0-9a-f]{40,64}\b", "<revision>", text)[:8000]
        return {
            "name": failure["name"],
            "app_id": failure["app_id"],
            "conclusion": failure["conclusion"],
            "diagnostic": text,
        }

    signature = [cause(f) for f in sorted(failures, key=lambda f: (f["name"], str(f["app_id"])))]
    return {
        "state": state,
        "failures": failures,
        "fingerprint": digest(signature) if failures else None,
    }
