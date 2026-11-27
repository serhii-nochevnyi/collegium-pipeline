"""Content-addressed immutable JSON artifacts for the serial coordinator."""

import json
import os
import re
import tempfile
from pathlib import Path

from .domain import PolicyError, digest


class Artifacts:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def put(self, value: dict) -> str:
        identity = digest(value)
        target = self.directory / (identity + ".json")
        if target.exists():
            self.get(identity)
            return identity
        fd, name = tempfile.mkstemp(prefix="artifact-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            # link does not replace a concurrently created immutable artifact.
            try:
                os.link(name, target)
            except FileExistsError:
                self.get(identity)
        finally:
            Path(name).unlink(missing_ok=True)
        return identity

    def get(self, identity: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise PolicyError("Invalid artifact identity")
        value = json.loads((self.directory / (identity + ".json")).read_text())
        if digest(value) != identity:
            raise PolicyError("Artifact was modified")
        return value
