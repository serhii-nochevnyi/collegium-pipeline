import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collegium_pipeline.cli import main
from collegium_pipeline.config import load_config
from collegium_pipeline.domain import PolicyError
from collegium_pipeline.transport import JsonHttp, McpClient, RemoteError

ROOT = Path(__file__).resolve().parents[1]


class ConfigCliTests(unittest.TestCase):
    def test_unsafe_or_ambiguous_config_is_rejected(self):
        config = json.loads((ROOT / "config/pilot.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for changes in (
                {"unknown": True},
                {"execution_enabled": "false"},
                {"max_cost_usd": float("nan")},
                {"max_cost_usd": -1},
                {"required_checks": []},
                {"execution_enabled": True},
                {"server": "https://untrusted.example"},
            ):
                path.write_text(json.dumps({**config, **changes}))
                with self.subTest(changes=changes), self.assertRaises(PolicyError):
                    load_config(path)

    def test_ticketless_admission_has_no_subprocess_or_external_side_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            requirements = Path(folder) / "task.md"
            requirements.write_text("A synthetic local task for admission verification.")
            journal = Path(folder) / "journal.sqlite3"
            arguments = [
                "prepare-text",
                "--config",
                str(ROOT / "config/pilot.json"),
                "--journal",
                str(journal),
                "--title",
                "Synthetic task",
                "--requirements-file",
                str(requirements),
            ]
            ids = []
            with patch("subprocess.run", side_effect=AssertionError("External call forbidden")):
                for _ in range(2):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(main(arguments), 0)
                    row = json.loads(output.getvalue())
                    self.assertFalse(row["agent_started"])
                    ids.append(row["run_id"])
            self.assertEqual(ids[0], ids[1])

    def test_status_does_not_create_a_missing_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Path(folder) / "missing.sqlite3"
            with contextlib.redirect_stderr(io.StringIO()):
                result = main(
                    [
                        "status",
                        "--config",
                        str(ROOT / "config/pilot.json"),
                        "--journal",
                        str(journal),
                        "--run-id",
                        "unknown",
                    ]
                )
            self.assertEqual(result, 1)
            self.assertFalse(journal.exists())


class TransportTests(unittest.TestCase):
    def test_large_json_body_uses_private_file_instead_of_a_long_curl_config_line(self):
        payload = {"data": "x" * 200000, "multiline": "first\nsecond", "unicode": "Україна"}
        files = []

        def curl(arguments, **kwargs):
            lines = kwargs["input"].splitlines()
            self.assertLess(max(map(len, lines)), 1000)
            value = next(
                line.split(" = ", 1)[1] for line in lines if line.startswith("data-binary")
            )
            name = json.loads(value)
            self.assertTrue(name.startswith("@"))
            body = Path(name[1:])
            files.append(body)
            self.assertEqual(body.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(body.read_text()), payload)
            header = Path(arguments[arguments.index("--dump-header") + 1])
            header.write_text("HTTP/2 200\nContent-Type: application/json\n")
            return subprocess.CompletedProcess(arguments, 0, '{"ok":true}\n200', "")

        with patch("subprocess.run", side_effect=curl):
            value, _ = JsonHttp("https://approved.example").request("POST", "/large", payload)
        self.assertTrue(value["ok"])
        self.assertTrue(files and all(not path.exists() for path in files))

    def test_credentials_stay_on_stdin_and_sse_crlf_is_parsed(self):
        secret = "synthetic-test-key"
        http = JsonHttp("https://approved.example", {"X-Api-Key": secret})

        def curl(arguments, **kwargs):
            self.assertNotIn(secret, repr(arguments))
            self.assertNotIn("--location", arguments)
            self.assertIn(secret, kwargs["input"])
            header_path = Path(arguments[arguments.index("--dump-header") + 1])
            header_path.write_text("HTTP/2 200\nContent-Type: text/event-stream\n")
            return subprocess.CompletedProcess(
                arguments,
                0,
                "event: message\r\n"
                'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\r\n\r\n\n200',
                "",
            )

        with patch("subprocess.run", side_effect=curl):
            result, _ = http.request("POST", "/mcp", {"method": "test"})
        self.assertTrue(result["result"]["ok"])

    def test_timeout_and_server_failure_make_write_outcome_unknown(self):
        http = JsonHttp("https://approved.example")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("curl", 30)):
            with self.assertRaises(RemoteError) as context:
                http.request("POST", "/session", {})
            self.assertTrue(context.exception.unknown_outcome)
            with self.assertRaises(RemoteError) as context:
                http.request("GET", "/session/id")
            self.assertFalse(context.exception.unknown_outcome)

    def test_header_injection_and_cross_origin_paths_are_refused(self):
        with self.assertRaises(ValueError):
            JsonHttp("https://user:password@approved.example")
        http = JsonHttp("https://approved.example", {"X-Api-Key": "bad\nheader"})
        with self.assertRaises(ValueError):
            http.request("GET", "/read")
        with self.assertRaises(ValueError):
            http.request("GET", "//untrusted.example/read")

    def test_mcp_initialization_session_headers_and_identity_checks(self):
        class FakeHttp:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload, **kwargs):
                self.calls.append((payload, kwargs))
                if payload["method"] == "initialize":
                    return {"id": 1, "result": {"protocolVersion": "2025-03-26"}}, {
                        "mcp-session-id": "s"
                    }
                if payload["method"] == "notifications/initialized":
                    return {}, {}
                return {"id": payload["id"], "result": {"content": []}}, {}

        http = FakeHttp()
        client = McpClient(http)
        client.call("list_spaces")
        self.assertEqual(len(http.calls), 3)
        self.assertEqual(http.calls[2][1]["headers"]["Mcp-Session-Id"], "s")
        self.assertEqual(http.calls[2][1]["headers"]["MCP-Protocol-Version"], "2025-03-26")
