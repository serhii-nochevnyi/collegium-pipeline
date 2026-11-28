"""Pinned native MCP snapshots, bounded evidence and explicit DEV/PROD citations."""

import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_investigations
from test_recovery import AgentsHttp, DiskStore

from collegium_pipeline.artifacts import Artifacts
from collegium_pipeline.domain import PolicyError, digest
from collegium_pipeline.investigation_cloud import dispatch
from collegium_pipeline.investigation_mcp import ENVIRONMENTS, McpSources, verify_snapshot
from collegium_pipeline.investigation_policy import cited
from collegium_pipeline.investigations import Investigations
from collegium_pipeline.platform import agent_digest
from collegium_pipeline.recovery import WriteAhead, restore_checkpoint
from collegium_pipeline.store import Journal
from collegium_pipeline.transport import RemoteError


class McpEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.artifacts = Artifacts(Path(self.temp.name) / "artifacts")
        self.schema = {"type": "object", "properties": {"query": {"type": "string"}}}
        self.catalog = {"schema_version": "investigation-mcp/v1", "sources": {}, "unavailable": []}
        self.clients = {}
        for i, (name, env) in enumerate(ENVIRONMENTS.items()):
            self.catalog["sources"][name] = {
                "connection_id": "mcpc_" + str(i),
                "server_id": "mcp_" + str(i),
                "environment": env,
                "url": "https://" + name + ".example.test/mcp",
                "tools": {"observe": digest(self.schema)},
            }
            client = Mock()
            client.tools.return_value = [{"name": "observe", "inputSchema": self.schema}]
            client.call.return_value = {"name": name, "values": [1, 2, 3]}
            self.clients[name] = client
        self.config = {"project_id": "project", "repository_id": 123}
        self.identity = {
            "automation_id": "aut_owner",
            "run_id": "run_capture",
            "attempt_id": "att_capture",
        }
        self.env = {
            "LAP_ATTEMPT_ID": "att_capture",
            "LAP_ATTEMPT_KEY": "fake-attempt",
            "LAP_API_URL": "https://platform.example.test",
        }
        self.http = Mock()
        self.http.request.side_effect = self.request
        self.scope = {
            "status": "paused",
            "project_id": "project",
            "target": {
                "mcp_servers": [
                    {
                        "name": name,
                        "level": "project",
                        "connection": row["connection_id"],
                        "tools": list(row["tools"]),
                    }
                    for name, row in self.catalog["sources"].items()
                ]
            },
        }
        self.hub = {
            "data": [
                {"server_id": row["server_id"], "server_name": name, "url": row["url"]}
                for name, row in self.catalog["sources"].items()
            ]
        }
        self.provider = McpSources(
            self.config,
            self.catalog,
            self.http,
            self.env,
            self.identity,
            self.artifacts,
            connect=lambda name: self.clients[name],
        )
        self.head = "a" * 40

    def tearDown(self):
        self.temp.cleanup()

    def request(self, method, path, *args, **kwargs):
        self.assertEqual(method, "GET")
        if path.startswith("/api/automations/"):
            return self.scope, {}
        if path == "/public/mcp_hub":
            return self.hub, {}
        if path.startswith("/api/mcp-stubs/"):
            name = path.split("/")[3]
            row = self.catalog["sources"][name]
            return {
                "connection": {"id": row["connection_id"], "level": "project"},
                "server": {"id": row["server_id"], "name": name},
            }, {}
        self.fail(path)

    def observation(self, name="ak-dev", **changes):
        return {
            "connection": name,
            "environment": ENVIRONMENTS[name],
            "tool": "observe",
            "arguments": {},
            "selector": "",
            "line_limit": 100,
            "max_age_seconds": 3600,
            **changes,
        }

    def capture(self, request=None):
        return self.provider.capture(self.head, [request or self.observation()])[0]

    def claim(self, source):
        return {
            "text": "Observation at its recorded time.",
            "environments": [source["environment"]],
            "citations": [
                {
                    "source_id": source["id"],
                    "start": 1,
                    "end": 1,
                    "quote": source["text"].splitlines()[0],
                    "environment": source["environment"],
                }
            ],
        }

    def test_native_snapshot_hash_and_canonical_quote(self):
        source = self.capture()
        self.assertEqual(source["native_identity"], self.identity)
        self.assertEqual(
            source["response_digest"], digest(self.clients["ak-dev"].call.return_value)
        )
        self.assertEqual(source["environment"], "DEV")
        self.assertEqual(verify_snapshot(source, self.artifacts), source)
        self.assertEqual(cited(self.claim(source), [source])["environments"], ["DEV"])
        self.assertEqual(self.clients["ak-dev"].call.call_count, 1)

    def test_entire_request_set_validates_before_network(self):
        for request in [
            self.observation(environment="PROD"),
            self.observation(connection="grafana-dev"),
            self.observation(tool="delete_dashboard"),
            self.observation(selector="/invalid~"),
            self.observation(line_limit=True),
            {**self.observation(), "snapshot": {}},
            self.observation(connection=[]),
        ]:
            with self.subTest(request=request), self.assertRaises(PolicyError):
                self.provider.capture(self.head, [self.observation(), request])
        with self.assertRaises(PolicyError):
            self.provider.capture(self.head, [self.observation(), self.observation()])
        self.http.request.assert_not_called()

    def test_no_personal_key_fallback(self):
        self.env.pop("LAP_ATTEMPT_KEY")
        self.env["LAP_API_KEY"] = "fake-personal"
        with self.assertRaisesRegex(PolicyError, "no personal-key fallback"):
            self.capture()
        self.clients["ak-dev"].call.assert_not_called()

    def test_connection_url_schema_and_grant_drift(self):
        self.scope["target"]["mcp_servers"][0]["connection"] = "mcpc_wrong"
        with self.assertRaises(PolicyError):
            self.capture()
        self.scope["target"]["mcp_servers"][0]["connection"] = "mcpc_0"
        original = self.hub["data"][1]["url"]
        self.hub["data"][1]["url"] = "https://prod.example.test"
        with self.assertRaises(PolicyError):
            self.capture()
        self.hub["data"][1]["url"] = original
        self.clients["ak-dev"].tools.return_value[0]["inputSchema"] = {"type": "string"}
        with self.assertRaises(PolicyError):
            self.capture()
        self.clients["ak-dev"].call.assert_not_called()

    def test_metadata_drift_during_read_is_refused(self):
        def changed(*args, **kwargs):
            self.hub["data"][1]["url"] = "https://changed.example.test"
            return {"data": "observed"}

        self.clients["ak-dev"].call.side_effect = changed
        with self.assertRaisesRegex(PolicyError, "URL/identity"):
            self.capture()

    def test_error_oversize_and_nonfinite_responses_are_not_facts(self):
        for value in [
            {"isError": True},
            {"status": "error"},
            {"text": "x" * 256001},
            {"value": float("nan")},
        ]:
            self.clients["ak-dev"].call.return_value = value
            with self.assertRaises(PolicyError):
                self.capture()
        self.clients["ak-dev"].call.side_effect = RuntimeError("sensitive upstream failure")
        with self.assertRaises(PolicyError) as exc:
            self.capture()
        self.assertNotIn("sensitive", str(exc.exception))

    def test_pointer_text_and_explicit_partial_coverage(self):
        self.clients["ak-dev"].call.return_value = [
            {"type": "text", "text": json.dumps({"a/b": {"~": "line1\nline2\nline3"}})}
        ]
        source = self.capture(self.observation(selector="/a~1b/~0", line_limit=2))
        self.assertEqual(source["text"], "line1\nline2")
        self.assertFalse(source["coverage"]["excerpt_complete"])
        self.assertEqual(source["coverage"]["selected_lines"], 3)
        self.assertEqual(source["coverage"]["upstream_completeness"], "not_asserted")
        with self.assertRaises(PolicyError):
            self.capture(self.observation(selector="/missing"))

    def test_tampered_response_and_forged_quote_environment(self):
        source = self.capture()
        claim = self.claim(source)
        with self.assertRaises(PolicyError):
            verify_snapshot({**source, "text": "invented"}, self.artifacts)
        for changes in [{"environment": "PROD"}, {"quote": "invented"}, {"end": 999}]:
            bad = copy.deepcopy(claim)
            bad["citations"][0].update(changes)
            with self.assertRaises(PolicyError):
                cited(bad, [source])
        for envs in [None, ["PROD"], ["DEV", "PROD"], ["DEV", "DEV"]]:
            with self.assertRaises(PolicyError):
                cited({**claim, "environments": envs}, [source])
        (self.artifacts.directory / (source["snapshot_digest"] + ".json")).write_text("{}")
        with self.assertRaises(PolicyError):
            verify_snapshot(source, self.artifacts)

    def test_explicit_dev_prod_comparison(self):
        dev = self.capture()
        prod = self.capture(self.observation("ak-prod"))
        claim = self.claim(dev)
        claim["citations"] += self.claim(prod)["citations"]
        claim["environments"] = ["DEV", "PROD"]
        self.assertEqual(cited(claim, [dev, prod]), claim)
        claim["environments"] = ["PROD"]
        with self.assertRaises(PolicyError):
            cited(claim, [dev, prod])

    def test_hidden_argument_fields_are_not_sent(self):
        with self.assertRaisesRegex(PolicyError, "schema fields"):
            self.capture(self.observation(arguments={"secret_header": "value"}))
        self.clients["ak-dev"].call.assert_not_called()

    def test_expiry_blocks_new_workers(self):
        f = test_investigations.InvestigationTests()
        f.setUp()
        try:
            source = self.capture()
            f.engine.artifacts.put(self.artifacts.get(source["snapshot_digest"]))
            intake = {**f.intake, "sources": [], "mcp_sources": [self.observation()]}
            intake["task"] = {**intake["task"], "source_id": "mcp-expiry"}
            root = f.engine.admit(intake, [source])["run_id"]
            with patch(
                "collegium_pipeline.investigations.time.time", return_value=source["expires_at"] + 1
            ):
                result = f.engine.step(root)
            self.assertEqual(result["state"], "blocked")
            self.assertIn("expired", result["reason"])
            self.assertEqual(f.http.created, 0)
        finally:
            f.tearDown()

    def test_cloud_readmission_reuses_snapshot_without_new_mcp_calls(self):
        f = test_investigations.InvestigationTests()
        f.setUp()
        try:
            state = f.path / "cloud-mcp"
            hooks = {
                "cloud_identity": lambda _: self.identity,
                "cloud_fence": Mock(return_value=(state / "receipt", self.identity)),
                "save_receipt": Mock(),
                "reconcile_controller": Mock(),
            }
            config = {
                **f.config,
                "execution_enabled": False,
                "recovery_store": {"owner": "aut_owner"},
            }
            intake = {**f.intake, "sources": [], "mcp_sources": [self.observation()]}
            output = io.StringIO()
            with (
                patch("collegium_pipeline.investigation_cloud.Checkpoints"),
                patch(
                    "collegium_pipeline.investigation_cloud.WriteAhead",
                    return_value=Mock(save=Mock()),
                ),
                contextlib.redirect_stdout(output),
            ):
                for _ in range(2):
                    dispatch(
                        {"action": "investigate", "operation": "prepare", "intake": intake},
                        state,
                        config,
                        {**self.env, "PIPELINE_CONTROL_KEY": "fake-control"},
                        self.http,
                        hooks,
                        mcp_catalog=self.catalog,
                        mcp_connect=lambda name: self.clients[name],
                    )
            results = [json.loads(line.split("=", 1)[1]) for line in output.getvalue().splitlines()]
            self.assertEqual(results[0]["run_id"], results[1]["run_id"])
            self.assertEqual(results[0]["sources"], results[1]["sources"])
            self.assertEqual(self.clients["ak-dev"].call.call_count, 1)
            self.assertEqual(f.http.created, 0)
        finally:
            f.tearDown()

    def test_complete_worker_flow_preserves_environment_citations(self):
        f = test_investigations.InvestigationTests()
        f.setUp()
        try:
            source = self.capture()
            f.engine.artifacts.put(self.artifacts.get(source["snapshot_digest"]))
            f.claim = self.claim(source)
            intake = {
                **f.intake,
                "task": {**f.intake["task"], "source_id": "mcp-worker-flow"},
                "sources": [],
                "mcp_sources": [self.observation()],
            }
            f.root = f.engine.admit(intake, [source])["run_id"]
            result = f.until("ready_for_decision")
            self.assertEqual(len(result["research"]), 4)
            self.assertEqual(f.http.created, 7)
            status = f.engine.status(f.root)
            self.assertTrue(status["evidence_fresh"])
            self.assertEqual(status["evidence_catalog"][0]["environment"], "DEV")
        finally:
            f.tearDown()

    def test_signed_recovery_restores_raw_mcp_snapshot_and_original_native_turn(self):
        f = test_investigations.InvestigationTests()
        f.setUp()
        try:
            cfg = copy.deepcopy(f.config)
            cfg["recovery_store"] = {
                "owner": "aut_owner",
                "automation_id": "aut_store",
                "approved_digest": "a" * 64,
            }
            binding = cfg["workers"]["assessor:sonnet:low"]
            agent = copy.deepcopy(f.http.agents[binding["agent_id"]])
            agent["id"] = "agent_test"
            binding.update(agent_id="agent_test", approved_agent_digest=agent_digest(agent))
            http = AgentsHttp(agent, lose="prompt")
            http.prior["item"]["event"]["data"] = {"action": "investigate", "operation": "tick"}
            state = f.path / "signed-mcp"
            state.mkdir()
            journal = Journal(state / "journal.sqlite3")
            engine = Investigations(cfg, journal, http, state / "artifacts")
            source = self.capture()
            engine.artifacts.put(self.artifacts.get(source["snapshot_digest"]))
            intake = {**f.intake, "sources": [], "mcp_sources": [self.observation()]}
            root = engine.admit(intake, [source])["run_id"]
            store = DiskStore(f.path / "independent")
            identity = {
                "automation_id": "aut_owner",
                "run_id": "run_lost",
                "attempt_id": "att_lost",
            }
            journal.before_effect = WriteAhead(
                cfg, journal, state / "artifacts", store, identity
            ).save
            with self.assertRaises(RemoteError):
                engine.step(root)
            journal.close()
            shutil.rmtree(state)
            self.assertTrue(restore_checkpoint(cfg, state, store, http, None))
            journal = Journal(state / "journal.sqlite3")
            try:
                loaded = Investigations(cfg, journal, http, state / "artifacts")
                catalog = loaded.artifacts.get(loaded.load(root)["sources"])["sources"]
                self.assertEqual(verify_snapshot(catalog[0], loaded.artifacts), source)
                workers = loaded.status(root)["workers"]
                self.assertEqual(
                    (len(workers), workers[0]["session_id"], workers[0]["turn_id"]),
                    (1, "ses_known", "run_turn"),
                )
                self.assertEqual((len(http.sessions), len(http.turns)), (1, 1))
                self.assertEqual(self.clients["ak-dev"].call.call_count, 1)
            finally:
                journal.close()
        finally:
            f.tearDown()
