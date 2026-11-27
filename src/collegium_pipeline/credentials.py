"""Resolve the existing local credential only for the verified platform origin."""

import json
import os
import stat
from pathlib import Path

from .domain import PolicyError
from .transport import JsonHttp

SERVER = "https://agentic-platform.infrateam.xyz"


def local_platform(timeout=150):
    key = os.environ.get("LAP_API_KEY")
    if key:
        if os.environ.get("LAP_SERVER") != SERVER:
            raise PolicyError("LAP_API_KEY requires the exact verified LAP_SERVER")
    else:
        path = Path.home() / ".config/lap/config.json"
        metadata = path.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise PolicyError("lap credential file must be private and owned by the current user")
        key = json.loads(path.read_text())["envs"][SERVER]["key"]
    if not isinstance(key, str) or not key or "\r" in key or "\n" in key:
        raise PolicyError("Invalid platform credential")
    return JsonHttp(SERVER, {"X-Api-Key": key}, timeout=timeout)
