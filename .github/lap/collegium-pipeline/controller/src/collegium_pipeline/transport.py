"""Small JSON HTTP transport using the host's verified TLS implementation."""

import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class RemoteError(RuntimeError):
    def __init__(self, message: str, *, status=0, unknown_outcome=False, detail=None):
        super().__init__(message)
        self.status = status
        self.unknown_outcome = unknown_outcome
        self.detail = detail


class JsonHttp:
    def __init__(self, origin: str, headers=None, timeout=30):
        parsed = urlparse(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("A credential-free HTTPS origin is required")
        self.origin = origin.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def request(self, method: str, path: str, payload=None, *, headers=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Request path must stay on its configured origin")
        values = ["url = " + json.dumps(self.origin + path)]
        all_headers = {
            "Accept": "application/json, text/event-stream",
            **self.headers,
            **(headers or {}),
        }
        if payload is not None:
            all_headers["Content-Type"] = "application/json"
        for key, value in all_headers.items():
            if "\n" in key + value or "\r" in key + value:
                raise ValueError("Invalid HTTP header")
            values.append("header = " + json.dumps(key + ": " + value))
        with tempfile.TemporaryDirectory(prefix="collegium-http-") as folder:
            header_file = Path(folder) / "headers"
            if payload is not None:
                body_file = Path(folder) / "body.json"
                body_file.write_text(json.dumps(payload))
                body_file.chmod(0o600)
                values.append("data-binary = " + json.dumps("@" + str(body_file)))
            try:
                response = subprocess.run(
                    [
                        "curl",
                        "--silent",
                        "--show-error",
                        "--max-time",
                        str(self.timeout),
                        "--request",
                        method,
                        "--dump-header",
                        str(header_file),
                        "--write-out",
                        "\n%{http_code}",
                        "--config",
                        "-",
                    ],
                    input="\n".join(values) + "\n",
                    capture_output=True,
                    text=True,
                    timeout=self.timeout + 5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RemoteError(
                    "HTTP transport interrupted", unknown_outcome=method != "GET"
                ) from exc
            if response.returncode:
                raise RemoteError("HTTP request did not finish", unknown_outcome=method != "GET")
            body, code = response.stdout.rsplit("\n", 1)
            status = int(code)
            response_headers = {}
            for line in header_file.read_text().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    response_headers[key.lower()] = value.strip()
            if status < 200 or status >= 300:
                try:
                    detail = json.loads(body)
                    encoded = json.dumps(detail)
                    for value in self.headers.values():
                        if value:
                            encoded = encoded.replace(value, "[REDACTED]")
                    detail = json.loads(encoded)
                except ValueError:
                    detail = None
                raise RemoteError(
                    f"Remote HTTP {status}",
                    status=status,
                    unknown_outcome=method != "GET" and status >= 500,
                    detail=detail,
                )
            if not body:
                return {}, response_headers
            try:
                if response_headers.get("content-type", "").startswith("text/event-stream"):
                    for event in body.replace("\r\n", "\n").split("\n\n"):
                        data = "\n".join(
                            line[5:].lstrip()
                            for line in event.splitlines()
                            if line.startswith("data:")
                        )
                        if data:
                            value = json.loads(data)
                            if "result" in value or "error" in value:
                                return value, response_headers
                    raise ValueError("SSE response contains no JSON-RPC result")
                return json.loads(body), response_headers
            except ValueError as exc:
                raise RemoteError("Invalid JSON response", unknown_outcome=method != "GET") from exc


class McpClient:
    def __init__(self, http: JsonHttp, path="/mcp"):
        self.http, self.path = http, path
        self.headers = {}
        self.sequence = 0
        self.initialized = False

    def initialize(self):
        self.sequence += 1
        result, headers = self.http.request(
            "POST",
            self.path,
            {
                "jsonrpc": "2.0",
                "id": self.sequence,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "collegium-pipeline", "version": "0.1.0"},
                },
            },
        )
        if result.get("id") != self.sequence or "error" in result:
            raise RemoteError("MCP initialization refused")
        protocol = result["result"]["protocolVersion"]
        self.headers["MCP-Protocol-Version"] = protocol
        if "mcp-session-id" in headers:
            self.headers["Mcp-Session-Id"] = headers["mcp-session-id"]
        self.http.request(
            "POST",
            self.path,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self.headers,
        )
        self.initialized = True

    def rpc(self, method, params):
        if not self.initialized:
            self.initialize()
        self.sequence += 1
        result, _ = self.http.request(
            "POST",
            self.path,
            {
                "jsonrpc": "2.0",
                "id": self.sequence,
                "method": method,
                "params": params,
            },
            headers=self.headers,
        )
        if result.get("id") != self.sequence or "error" in result:
            raise RemoteError("MCP request refused or response identity mismatched")
        return result["result"]

    def call(self, name, arguments=None):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise RemoteError(f"MCP tool {name} refused the operation")
        return result
