"""Durable shared ticket capacity under the existing single fenced dispatcher."""

import json

from .domain import PolicyError

DEFAULT_LIMITS = {"project": 1, "repository": 1, "epic": 1}


def covers(prefix, path):
    return prefix == path or prefix.endswith("/") and path.startswith(prefix)


def checked_paths(paths, allowed):
    if not isinstance(paths, list) or not paths or len(paths) > 100:
        raise PolicyError("Explicit nonempty ticket path claims are required")
    for path in paths:
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or any(ord(c) < 32 for c in path)
            or any(p in {"", ".", "..", ".git"} for p in path.rstrip("/").split("/"))
            or not any(covers(a, path) for a in allowed)
        ):
            raise PolicyError("Ticket claim leaves the repository path ceiling")
    return sorted(set(paths))


def limits(config):
    value = config.get("scheduling", DEFAULT_LIMITS)
    if (
        not isinstance(value, dict)
        or set(value) != set(DEFAULT_LIMITS)
        or any(type(n) is not int or not 1 <= n <= 32 for n in value.values())
        or value["epic"] > value["project"]
        or value["repository"] > value["project"]
    ):
        raise PolicyError("Scheduling needs project/repository/epic limits in1..32")
    return value


def conflict(a, b):
    if a["repository"] != b["repository"]:
        return False
    return (
        bool(set(a["resources"]) & set(b["resources"]))
        or any(covers(x, y) or covers(y, x) for x in a["paths"] for y in b["paths"])
        or "repository:*" in a["resources"]
        or "repository:*" in b["resources"]
    )


class Capacity:
    def __init__(self, journal, config):
        self.journal, self.config = journal, config
        self.db = journal.connection
        self.db.execute("""CREATE TABLE IF NOT EXISTS ticket_claims (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT UNIQUE NOT NULL REFERENCES runs(id),
            document TEXT NOT NULL, state TEXT NOT NULL)""")

    def get(self, root):
        row = self.db.execute("SELECT * FROM ticket_claims WHERE run_id=?", (root,)).fetchone()
        return {**dict(row), **json.loads(row["document"])} if row else None

    def register(self, root, *, paths=None, resources=None, epic=None, dormant=False):
        scope = {
            "project": self.config.get("project_id", "local"),
            "repository": self.config["repository"],
            "epic": epic,
            "paths": checked_paths(
                paths or self.config["allowed_paths"], self.config["allowed_paths"]
            ),
            "resources": ["repository:*"] if resources is None else resources,
            "limits": limits(self.config),
        }
        if not isinstance(scope["resources"], list) or any(
            not isinstance(r, str) or not r or len(r) > 200 for r in scope["resources"]
        ):
            raise PolicyError("Invalid shared resource claims")
        scope["resources"] = sorted(set(scope["resources"]))
        with self.journal.transaction():
            old = self.get(root)
            if old:
                if json.loads(old["document"]) != scope:
                    raise PolicyError(
                        "Ticket ownership/scope changed; canonical run is already claimed"
                    )
                return
            self.db.execute(
                "INSERT INTO ticket_claims(run_id,document,state) VALUES(?,?,?)",
                (root, json.dumps(scope, sort_keys=True), "dormant" if dormant else "waiting"),
            )

    def activate(self, root, epic):
        with self.journal.transaction():
            row = self.get(root)
            if not row or row["epic"] != epic:
                raise PolicyError("Epic cannot activate another ticket's claim")
            self.db.execute(
                "UPDATE ticket_claims SET state='waiting' WHERE run_id=? AND state='dormant'",
                (root,),
            )

    def acquire(self, root, *, epic_owner=None):
        if not self.get(root):
            self.register(root)
        with self.journal.transaction():
            row = self.get(root)
            if row["epic"] and row["epic"] != epic_owner:
                return False
            if row["state"] == "active":
                return True
            if row["state"] in {"dormant", "awaiting_merge"}:
                return False
            others = [
                self.get(r[0])
                for r in self.db.execute(
                    "SELECT run_id FROM ticket_claims WHERE run_id<>? "
                    "AND state IN ('active','waiting','awaiting_merge') ORDER BY queue_id",
                    (root,),
                ).fetchall()
            ]
            active = [r for r in others if r["state"] == "active"]
            held = [r for r in others if r["state"] in {"active", "awaiting_merge"}]

            def eligible(request):
                if any(conflict(request, r) for r in held):
                    return False
                for name in ("project", "repository", "epic"):
                    if name == "epic" and not request["epic"]:
                        continue
                    peers = [r for r in active if r[name] == request[name]]
                    ceiling = min([request["limits"][name], *[r["limits"][name] for r in peers]])
                    if len(peers) >= ceiling:
                        return False
                return True

            if not eligible(row) or any(
                r["state"] == "waiting" and r["queue_id"] < row["queue_id"] and eligible(r)
                for r in others
            ):
                return False
            self.db.execute("UPDATE ticket_claims SET state='active' WHERE run_id=?", (root,))
            return True

    def defer(self, root, epic):
        with self.journal.transaction():
            row = self.get(root)
            if not row or row["epic"] != epic:
                raise PolicyError("Epic cannot defer another ticket's claim")
            self.db.execute(
                "UPDATE ticket_claims SET state='dormant' WHERE run_id=? AND state='waiting'",
                (root,),
            )

    def unresolved(self, root):
        if self.db.execute(
            "SELECT 1 FROM runs WHERE source_id LIKE ? "
            "AND (pending_intent IS NOT NULL OR state='reconciling')",
            (root + ":%",),
        ).fetchone():
            return True
        events = self.journal.events(root)
        done = {e["data"]["key"] for e in events if e["kind"] == "broker_done"}
        from .broker import broker_unstarted

        return any(
            e["kind"] == "broker_intent"
            and e["data"]["key"] not in done
            and not broker_unstarted(self.journal, root, e["data"]["key"], e["data"]["identity"])
            for e in events
        )

    def release(self, root):
        with self.journal.transaction():
            if self.unresolved(root):
                return False
            self.db.execute("UPDATE ticket_claims SET state='released' WHERE run_id=?", (root,))
            return True

    def hold_ready(self, root):
        with self.journal.transaction():
            if self.unresolved(root):
                return False
            self.db.execute(
                "UPDATE ticket_claims SET state='awaiting_merge' WHERE run_id=?", (root,)
            )
            return True
