"""Independent, signed checkpoint storage. No network, repositories or agent calls."""

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
from pathlib import Path

CHUNK = 120_000
MAX_BYTES = 8_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def signature(value, key):
    return hmac.new(key.encode(), canonical(value), hashlib.sha256).hexdigest()


def write_atomic(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def handle(event, root, owner, key):
    event = dict(event)
    mac = event.pop("mac", "")
    if not key or not hmac.compare_digest(signature(event, key), str(mac)):
        raise ValueError("Checkpoint authentication refused")
    if event.get("owner") != owner or not re.fullmatch(
        r"[a-f0-9]{32}", event.get("request_id", "")
    ):
        raise ValueError("Checkpoint owner or request identity differs")
    namespace = event.get("namespace")
    if namespace not in {"delivery", "diagnostic", "service"}:
        raise ValueError("Invalid checkpoint namespace")
    root = Path(root) / namespace
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    head_path, pending_path = root / "head.json", root / "pending.json"
    head = json.loads(head_path.read_text()) if head_path.exists() else None
    action = event.get("action")
    result = {
        "owner": owner,
        "namespace": namespace,
        "request_id": event["request_id"],
        "head": head,
    }
    if action == "head":
        pass
    elif action == "begin":
        checkpoint, parent, size = event["checkpoint"], event["parent"], event["size"]
        if (
            not re.fullmatch(r"[a-f0-9]{64}", checkpoint)
            or type(size) is not int
            or not 0 < size <= MAX_BYTES
        ):
            raise ValueError("Invalid checkpoint size or digest")
        if head and head["checkpoint"] == checkpoint:
            return {**result, "committed": True}
        if (head["checkpoint"] if head else None) != parent:
            raise ValueError("Checkpoint CAS parent changed")
        pending = {"checkpoint": checkpoint, "parent": parent, "size": size}
        if pending_path.exists() and json.loads(pending_path.read_text()) != pending:
            old = json.loads(pending_path.read_text())
            if not head or old["checkpoint"] != head["checkpoint"]:
                shutil.rmtree(root / old["checkpoint"], ignore_errors=True)
        (root / checkpoint).mkdir(mode=0o700, exist_ok=True)
        write_atomic(pending_path, canonical(pending))
    elif action in {"chunk", "finish"}:
        checkpoint = event["checkpoint"]
        if head and head["checkpoint"] == checkpoint:
            return {**result, "committed": True}
        if not pending_path.exists():
            raise ValueError("No pending checkpoint")
        pending = json.loads(pending_path.read_text())
        if (
            checkpoint != pending["checkpoint"]
            or (head["checkpoint"] if head else None) != pending["parent"]
        ):
            raise ValueError("Checkpoint CAS differs")
        folder = root / checkpoint
        count = (pending["size"] + CHUNK - 1) // CHUNK
        if action == "chunk":
            index = event["index"]
            if type(index) is not int or not 0 <= index < count:
                raise ValueError("Invalid chunk number")
            data = base64.b64decode(event["data"], validate=True)
            expected = min(CHUNK, pending["size"] - index * CHUNK)
            if len(data) != expected:
                raise ValueError("Checkpoint chunk length differs")
            path = folder / str(index)
            if path.exists() and path.read_bytes() != data:
                raise ValueError("Immutable chunk changed")
            write_atomic(path, data)
        else:
            data = b"".join((folder / str(n)).read_bytes() for n in range(count))
            if len(data) != pending["size"] or hashlib.sha256(data).hexdigest() != checkpoint:
                raise ValueError("Checkpoint content digest differs")
            new_head = {"checkpoint": checkpoint, "size": len(data), "parent": pending["parent"]}
            temporary = root / "head.tmp"
            temporary.write_bytes(canonical(new_head))
            temporary.replace(head_path)
            pending_path.unlink()
            # Two committed generations plus one pending upload stay below state_bytes.
            for path in root.iterdir():
                if path.is_dir() and path.name not in {checkpoint, pending["parent"]}:
                    shutil.rmtree(path)
            result["head"] = new_head
            result["committed"] = True
    elif action == "read":
        if not head or event["checkpoint"] != head["checkpoint"]:
            raise ValueError("Checkpoint read head changed")
        index = event["index"]
        if type(index) is not int or not 0 <= index < (head["size"] + CHUNK - 1) // CHUNK:
            raise ValueError("Invalid read chunk")
        result["data"] = base64.b64encode(
            (root / head["checkpoint"] / str(index)).read_bytes()
        ).decode()
    else:
        raise ValueError("Unknown checkpoint action")
    return result


def main():
    settings = json.loads(Path("recovery_scope.json").read_text())
    event = json.loads(Path("/job/event.json").read_text())["data"]
    key = os.environ.get("PIPELINE_CONTROL_KEY", "")
    result = handle(
        event, Path(os.environ["ARANARIUM_STATE_DIR"]) / "checkpoints", settings["owner"], key
    )
    print(json.dumps({**result, "mac": signature(result, key)}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"error": "checkpoint_refused"}))
        raise SystemExit(2) from None
