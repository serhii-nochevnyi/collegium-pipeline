"""Restrict the investigation automation to its read-only entry point."""

import json
import runpy
from pathlib import Path


def main():
    event = json.loads(Path("/job/event.json").read_text()).get("data", {})
    if not isinstance(event, dict) or event.get("action") != "investigate":
        raise ValueError("This automation accepts only investigate events")
    root = Path(__file__).resolve().parent
    return runpy.run_path(str(root / "entry.py"))["main"](event, root=root)


if __name__ == "__main__":
    raise SystemExit(main())
