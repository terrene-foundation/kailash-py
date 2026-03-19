from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for kaizen.deploy module.

Self-contained tests that do NOT depend on kaizen.__init__ import chain.
Uses --noconftest or sys.path manipulation to avoid the pre-existing
import error in the broader Kaizen test suite.

Tests are organized by component:
  - LocalRegistry: file-based agent registry CRUD
  - DeployResult: dataclass serialization roundtrip
  - deploy / deploy_local: deployment routing logic
  - introspect_agent: runtime class introspection
  - HTTP deploy: real local HTTP server (no mocking)
"""

import http.server
import importlib
import json
import os
import sys
import threading
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bypass kaizen.__init__ import chain (pre-existing import error in the
# broader Kaizen test suite).  We inject the deploy sub-package modules
# directly so that ``import kaizen.deploy.registry`` never triggers
# ``kaizen/__init__.py``.
# ---------------------------------------------------------------------------
_SRC = str(Path(__file__).resolve().parents[3] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Ensure a minimal 'kaizen' package exists in sys.modules so that
# ``kaizen.deploy.*`` sub-imports resolve without executing kaizen/__init__.py.
if "kaizen" not in sys.modules:
    _kaizen_pkg = types.ModuleType("kaizen")
    _kaizen_pkg.__path__ = [os.path.join(_SRC, "kaizen")]
    _kaizen_pkg.__package__ = "kaizen"
    sys.modules["kaizen"] = _kaizen_pkg

if "kaizen.deploy" not in sys.modules:
    _deploy_pkg = types.ModuleType("kaizen.deploy")
    _deploy_pkg.__path__ = [os.path.join(_SRC, "kaizen", "deploy")]
    _deploy_pkg.__package__ = "kaizen.deploy"
    sys.modules["kaizen.deploy"] = _deploy_pkg

# Now import the actual modules — they will NOT trigger kaizen/__init__.py
from kaizen.deploy.client import (  # noqa: E402
    DeployAuthError,
    DeployError,
    DeployResult,
    deploy,
    deploy_local,
)
from kaizen.deploy.introspect import introspect_agent  # noqa: E402
from kaizen.deploy.registry import LocalRegistry  # noqa: E402


# ===================================================================
# LocalRegistry Tests
# ===================================================================


class TestLocalRegistry:
    """Tests for the file-based LocalRegistry."""

    def test_register_and_get(self, tmp_path: Path) -> None:
        """Register an agent manifest and retrieve it by name."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        manifest = {
            "name": "test-agent",
            "module": "agents.test",
            "class_name": "TestAgent",
            "description": "A test agent",
            "capabilities": ["testing"],
        }
        result = registry.register(manifest)
        assert result["agent_name"] == "test-agent"
        assert result["status"] == "registered"

        retrieved = registry.get_agent("test-agent")
        assert retrieved is not None
        assert retrieved["name"] == "test-agent"
        assert retrieved["module"] == "agents.test"
        assert retrieved["class_name"] == "TestAgent"
        assert retrieved["capabilities"] == ["testing"]

    def test_register_creates_json_file(self, tmp_path: Path) -> None:
        """Register must persist a JSON file on disk."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        manifest = {"name": "file-agent", "module": "m", "class_name": "C"}
        registry.register(manifest)

        json_path = tmp_path / "file-agent.json"
        assert json_path.exists(), "JSON file must be created on disk"
        data = json.loads(json_path.read_text())
        assert data["name"] == "file-agent"

    def test_list_agents(self, tmp_path: Path) -> None:
        """List returns all registered agents."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        registry.register({"name": "alpha", "module": "m", "class_name": "A"})
        registry.register({"name": "beta", "module": "m", "class_name": "B"})

        agents = registry.list_agents()
        names = sorted(a["name"] for a in agents)
        assert names == ["alpha", "beta"]

    def test_deregister(self, tmp_path: Path) -> None:
        """Deregister removes the agent; get returns None afterwards."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        registry.register({"name": "doomed", "module": "m", "class_name": "D"})
        assert registry.get_agent("doomed") is not None

        removed = registry.deregister("doomed")
        assert removed is True
        assert registry.get_agent("doomed") is None

    def test_deregister_nonexistent(self, tmp_path: Path) -> None:
        """Deregistering an agent that does not exist returns False."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        assert registry.deregister("ghost") is False

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        """Getting a nonexistent agent returns None."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        assert registry.get_agent("nonexistent") is None

    def test_rejects_invalid_name_with_spaces(self, tmp_path: Path) -> None:
        """Names with spaces must be rejected."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.register({"name": "bad name", "module": "m", "class_name": "C"})

    def test_rejects_invalid_name_with_slashes(self, tmp_path: Path) -> None:
        """Names with path separators must be rejected (path traversal prevention)."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.register(
                {"name": "../etc/passwd", "module": "m", "class_name": "C"}
            )

    def test_rejects_empty_name(self, tmp_path: Path) -> None:
        """Empty name must be rejected."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.register({"name": "", "module": "m", "class_name": "C"})

    def test_rejects_invalid_name_on_get(self, tmp_path: Path) -> None:
        """get_agent must also validate the name."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.get_agent("../../etc/shadow")

    def test_rejects_invalid_name_on_deregister(self, tmp_path: Path) -> None:
        """deregister must also validate the name."""
        registry = LocalRegistry(registry_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.deregister("bad/name")


# ===================================================================
# DeployResult Tests
# ===================================================================


class TestDeployResult:
    """Tests for DeployResult dataclass serialization."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict -> from_dict must be lossless."""
        original = DeployResult(
            agent_name="roundtrip-agent",
            status="registered",
            mode="local",
            governance_match=True,
            details={"path": "/tmp/test.json"},
        )
        d = original.to_dict()
        restored = DeployResult.from_dict(d)

        assert restored.agent_name == original.agent_name
        assert restored.status == original.status
        assert restored.mode == original.mode
        assert restored.governance_match == original.governance_match
        assert restored.details == original.details

    def test_to_dict_omits_governance_match_when_none(self) -> None:
        """governance_match=None should not appear in to_dict output."""
        result = DeployResult(agent_name="a", status="ok", mode="local")
        d = result.to_dict()
        assert "governance_match" not in d

    def test_to_dict_includes_governance_match_when_set(self) -> None:
        """governance_match=False should appear in to_dict output."""
        result = DeployResult(
            agent_name="a", status="ok", mode="local", governance_match=False
        )
        d = result.to_dict()
        assert d["governance_match"] is False

    def test_from_dict_with_missing_fields(self) -> None:
        """from_dict with an empty dict should produce empty-string defaults."""
        result = DeployResult.from_dict({})
        assert result.agent_name == ""
        assert result.status == ""
        assert result.mode == ""
        assert result.governance_match is None
        assert result.details == {}


# ===================================================================
# deploy / deploy_local Tests
# ===================================================================


class TestDeployLocal:
    """Tests for deploy_local and local deploy routing."""

    def test_deploy_local_creates_file(self, tmp_path: Path) -> None:
        """deploy_local must persist manifest and return DeployResult."""
        manifest = {"name": "local-agent", "module": "m", "class_name": "C"}
        result = deploy_local(manifest, registry_dir=str(tmp_path))

        assert isinstance(result, DeployResult)
        assert result.agent_name == "local-agent"
        assert result.status == "registered"
        assert result.mode == "local"

        json_path = tmp_path / "local-agent.json"
        assert json_path.exists()

    def test_deploy_local_deploy_result_fields(self, tmp_path: Path) -> None:
        """DeployResult from deploy_local has all expected fields."""
        manifest = {"name": "field-agent", "module": "mod", "class_name": "Cls"}
        result = deploy_local(manifest, registry_dir=str(tmp_path))

        assert result.agent_name == "field-agent"
        assert result.mode == "local"
        assert "path" in result.details

    def test_deploy_no_target_url_goes_local(self, tmp_path: Path) -> None:
        """deploy() with target_url=None must route to local registry."""
        manifest = {"name": "routed-local", "module": "m", "class_name": "C"}
        result = deploy(manifest, target_url=None, registry_dir=str(tmp_path))

        assert result.mode == "local"
        assert result.agent_name == "routed-local"
        assert (tmp_path / "routed-local.json").exists()


# ===================================================================
# HTTP Deploy Tests (real local server, NO mocking)
# ===================================================================


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TestCareAPIHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler that simulates a CARE Platform agent registration endpoint."""

    # Class-level control: set to an HTTP status code to force error responses
    force_status: int | None = None

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.force_status == 401:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
            return

        if self.force_status == 500:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "Internal Server Error"}).encode("utf-8")
            )
            return

        # Parse the request body
        try:
            manifest_data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
            return

        # Successful registration response
        response = {
            "status": "registered",
            "agent_id": manifest_data.get("name", "unknown"),
            "governance_match": True,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args) -> None:
        """Suppress HTTP server logs during tests."""
        pass


class TestDeployHTTP:
    """Tests for remote HTTP deployment with a real local server."""

    def test_deploy_with_target_url_attempts_http(self) -> None:
        """deploy() with a target_url must POST to the remote server."""
        port = _find_free_port()
        _TestCareAPIHandler.force_status = None

        server = http.server.HTTPServer(("127.0.0.1", port), _TestCareAPIHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        manifest = {"name": "remote-agent", "module": "m", "class_name": "C"}
        result = deploy(manifest, target_url=f"http://127.0.0.1:{port}")

        thread.join(timeout=5)
        server.server_close()

        assert result.mode == "remote"
        assert result.agent_name == "remote-agent"
        assert result.status == "registered"
        assert result.governance_match is True

    def test_deploy_auth_error_on_401(self) -> None:
        """HTTP 401 must raise DeployAuthError."""
        port = _find_free_port()
        _TestCareAPIHandler.force_status = 401

        server = http.server.HTTPServer(("127.0.0.1", port), _TestCareAPIHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        manifest = {"name": "auth-fail", "module": "m", "class_name": "C"}
        with pytest.raises(DeployAuthError, match="Authentication failed"):
            deploy(manifest, target_url=f"http://127.0.0.1:{port}")

        thread.join(timeout=5)
        server.server_close()

    def test_deploy_error_on_connection_refused(self) -> None:
        """Unreachable URL must raise DeployError."""
        # Use a port that is almost certainly not listening
        port = _find_free_port()
        manifest = {"name": "refused", "module": "m", "class_name": "C"}
        with pytest.raises(DeployError, match="Connection failed"):
            deploy(manifest, target_url=f"http://127.0.0.1:{port}", timeout=2)

    def test_deploy_error_on_500(self) -> None:
        """HTTP 500 must raise DeployError (not DeployAuthError)."""
        port = _find_free_port()
        _TestCareAPIHandler.force_status = 500

        server = http.server.HTTPServer(("127.0.0.1", port), _TestCareAPIHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        manifest = {"name": "server-error", "module": "m", "class_name": "C"}
        with pytest.raises(DeployError, match="Deploy failed"):
            deploy(manifest, target_url=f"http://127.0.0.1:{port}")

        thread.join(timeout=5)
        server.server_close()


# ===================================================================
# Introspection Tests
# ===================================================================


class TestIntrospectAgent:
    """Tests for introspect_agent runtime class extraction."""

    def test_introspect_agent_basic(self, tmp_path: Path) -> None:
        """introspect_agent extracts metadata from a class with signature and tools."""
        # Create a temporary module with a minimal agent-like class
        mod_code = '''
class AnalysisSignature:
    """Analyze market data and produce insights."""
    query: str
    result: str

class MarketAnalyzer:
    """Analyzes market trends for investment decisions."""
    signature = AnalysisSignature
    tools = ["web_search", "calculator"]
    capabilities = ["market-analysis", "trend-detection"]
    supported_models = ["gpt-4", "claude-3"]
'''
        mod_name = "_test_introspect_basic_agent"
        mod = types.ModuleType(mod_name)
        exec(mod_code, mod.__dict__)
        sys.modules[mod_name] = mod

        try:
            info = introspect_agent(mod_name, "MarketAnalyzer")
            assert info["name"] == "MarketAnalyzer"
            assert info["module"] == mod_name
            assert info["class_name"] == "MarketAnalyzer"
            assert info["tools"] == ["web_search", "calculator"]
            assert info["capabilities"] == ["market-analysis", "trend-detection"]
            assert info["supported_models"] == ["gpt-4", "claude-3"]
            # Description comes from signature docstring
            assert (
                "market data" in info["description"].lower()
                or "analyze" in info["description"].lower()
            )
        finally:
            sys.modules.pop(mod_name, None)

    def test_introspect_agent_no_signature_uses_class_doc(self) -> None:
        """When no signature attribute exists, use class docstring."""
        mod_name = "_test_introspect_no_sig"
        mod_code = '''
class SimpleAgent:
    """A simple agent for testing purposes."""
    pass
'''
        mod = types.ModuleType(mod_name)
        exec(mod_code, mod.__dict__)
        sys.modules[mod_name] = mod

        try:
            info = introspect_agent(mod_name, "SimpleAgent")
            assert info["name"] == "SimpleAgent"
            assert "simple agent" in info["description"].lower()
            assert info["tools"] == []
            assert info["capabilities"] == []
            assert info["supported_models"] == []
        finally:
            sys.modules.pop(mod_name, None)

    def test_introspect_agent_with_annotations(self) -> None:
        """Introspection extracts input/output schema from signature annotations."""
        mod_name = "_test_introspect_annotations"
        mod_code = '''
class MySignature:
    """Process text inputs."""
    query: str
    max_results: int

    # Simulate a default on 'query' to mark it as input
    query = "default"

class AnnotatedAgent:
    signature = MySignature
'''
        mod = types.ModuleType(mod_name)
        exec(mod_code, mod.__dict__)
        sys.modules[mod_name] = mod

        try:
            info = introspect_agent(mod_name, "AnnotatedAgent")
            assert "input_schema" in info
            assert "output_schema" in info
            # 'query' has a default -> input; 'max_results' does not -> output
            assert "query" in info["input_schema"]
            assert "max_results" in info["output_schema"]
        finally:
            sys.modules.pop(mod_name, None)

    def test_introspect_missing_module(self) -> None:
        """introspect_agent with a nonexistent module raises ModuleNotFoundError."""
        with pytest.raises(ModuleNotFoundError):
            introspect_agent("nonexistent_module_xyz_12345", "SomeClass")

    def test_introspect_missing_class(self) -> None:
        """introspect_agent with a nonexistent class raises AttributeError."""
        # Use a module we know exists (the introspect module itself)
        with pytest.raises(AttributeError):
            introspect_agent("kaizen.deploy.introspect", "NonexistentClass")


# ===================================================================
# DeployError hierarchy Tests
# ===================================================================


class TestDeployErrorHierarchy:
    """Tests for error classes and their details field."""

    def test_deploy_error_has_details(self) -> None:
        """DeployError must carry a details dict."""
        err = DeployError("something failed", details={"code": 500})
        assert str(err) == "something failed"
        assert err.details == {"code": 500}

    def test_deploy_error_default_details(self) -> None:
        """DeployError with no details kwarg defaults to empty dict."""
        err = DeployError("fail")
        assert err.details == {}

    def test_deploy_auth_error_is_deploy_error(self) -> None:
        """DeployAuthError must be a subclass of DeployError."""
        err = DeployAuthError("auth fail", details={"status_code": 401})
        assert isinstance(err, DeployError)
        assert err.details["status_code"] == 401
