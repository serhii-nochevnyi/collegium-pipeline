#!/usr/bin/env python3
"""Codex HTTP header helper. Its stdout is a credential; never run it for display."""

import json
import os
import stat
import sys
from pathlib import Path

SERVER = "https://agentic-platform.infrateam.xyz"


def main():
    path = Path.home() / ".config/lap/config.json"
    try:
        metadata = path.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("lap credential file must belong to the current user and be private")
        config = json.loads(path.read_text())
        key = config["envs"][SERVER]["key"]
        if not isinstance(key, str) or not key or "\n" in key or "\r" in key:
            raise ValueError("invalid lap credential")
    except (OSError, ValueError, KeyError):
        print(
            "Collegium credential unavailable; complete lap login and check file permissions.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"X-Api-Key": key}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
