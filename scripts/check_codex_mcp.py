"""Discover one MCP through the installed Codex client, without a model call."""

import argparse
import json
import os
import select
import signal
import subprocess
import time


def inspect(server):
    process = subprocess.Popen(
        ["codex", "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive(request_id):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if not select.select([process.stdout], [], [], 1)[0]:
                continue
            line = process.stdout.readline()
            if not line:
                break
            message = json.loads(line)
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError("Codex MCP discovery failed")
                return message["result"]
        raise TimeoutError("Codex MCP discovery timed out")

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "collegium_readiness", "version": "0.1.0"}},
            }
        )
        receive(1)
        send({"method": "initialized"})
        send(
            {
                "id": 2,
                "method": "mcpServerStatus/list",
                "params": {"serverName": server, "detail": "full"},
            }
        )
        result = receive(2)
        rows = result["data"]
        return [
            {
                "name": row["name"],
                "auth_status": row["authStatus"],
                "runtime_status": row.get("runtimeStatus"),
                "tools": sorted(row.get("tools", {})),
                "discovery_ok": bool(row.get("tools")) and not row.get("toolsError"),
            }
            for row in rows
        ]
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("server", choices=["collegium", "collegium-help"])
    args = parser.parse_args()
    result = inspect(args.server)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result and all(row["discovery_ok"] for row in result) else 1)
