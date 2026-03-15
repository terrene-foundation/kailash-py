# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for MCP Proxy (M7-01, M7-02).

Tests proxy interposition, constraint enforcement at transport level,
tool namespacing, fail-closed behavior, and audit trail creation.
"""

import asyncio
import json

import pytest

from trustplane.models import ConstraintEnvelope, OperationalConstraints
from trustplane.project import TrustProject
from trustplane.proxy import ProxyConfig, ProxyResult, ProxyServerConfig, TrustProxy


@pytest.fixture
def tmp_trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def project_with_envelope(tmp_trust_dir):
    """Project with constraint envelope for enforcement testing."""
    envelope = ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=["file_operations", "read_file"],
            blocked_actions=["external_communication", "delete_all"],
        ),
        signed_by="Test Author",
    )
    return asyncio.run(
        TrustProject.create(
            trust_dir=str(tmp_trust_dir),
            project_name="Proxy Test",
            author="Test Author",
            constraint_envelope=envelope,
        )
    )


@pytest.fixture
def proxy(project_with_envelope):
    """Proxy with filesystem and github servers configured."""
    config = ProxyConfig()
    config.add_server(
        ProxyServerConfig(
            name="filesystem",
            command="mock-fs-server",
            action_category="file_operations",
        )
    )
    config.add_server(
        ProxyServerConfig(
            name="github",
            command="mock-gh-server",
            action_category="external_communication",
        )
    )

    proxy = TrustProxy(project_with_envelope, config=config)

    # Register mock tool handlers
    async def mock_read_file(path: str = "", **kwargs):
        return f"Contents of {path}"

    async def mock_write_file(path: str = "", content: str = "", **kwargs):
        return f"Wrote {len(content)} bytes to {path}"

    async def mock_create_issue(title: str = "", **kwargs):
        return f"Created issue: {title}"

    proxy.register_tool_handler("filesystem", "read_file", mock_read_file)
    proxy.register_tool_handler("filesystem", "write_file", mock_write_file)
    proxy.register_tool_handler("github", "create_issue", mock_create_issue)

    return proxy


class TestProxyConfig:
    def test_add_server(self):
        config = ProxyConfig()
        config.add_server(ProxyServerConfig(name="test", command="test-server"))
        assert "test" in config.servers
        assert config.servers["test"].command == "test-server"

    def test_remove_server(self):
        config = ProxyConfig()
        config.add_server(ProxyServerConfig(name="test", command="test-server"))
        config.remove_server("test")
        assert "test" not in config.servers

    def test_save_and_load_json(self, tmp_path):
        config = ProxyConfig()
        config.add_server(
            ProxyServerConfig(
                name="fs",
                command="fs-server",
                args=["--path", "/tmp"],
                action_category="file_operations",
            )
        )
        path = tmp_path / "proxy.json"
        config.save(path)

        with open(path) as f:
            data = json.load(f)
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "fs"


class TestProxyLifecycle:
    def test_start_stop(self, proxy):
        assert not proxy.is_running
        proxy.start()
        assert proxy.is_running
        proxy.stop()
        assert not proxy.is_running

    def test_fail_closed_when_stopped(self, proxy):
        """When proxy is stopped, ALL tool access is denied."""
        result = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/test.txt"})
        )
        assert result.verdict == "BLOCKED"
        assert result.forwarded is False
        assert "fail-closed" in result.error

    def test_status(self, proxy):
        proxy.start()
        status = proxy.status()
        assert status["running"] is True
        assert "filesystem" in status["servers"]
        assert "github" in status["servers"]
        assert len(status["registered_tools"]) == 3


class TestProxyEnforcement:
    def test_auto_approved_call_forwarded(self, proxy):
        """Allowed actions are forwarded and create audit anchor."""
        proxy.start()
        result = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/test.txt"})
        )
        assert result.forwarded is True
        assert result.result == "Contents of /test.txt"
        assert result.anchor_id is not None

    def test_blocked_action_not_forwarded(self, proxy):
        """Blocked actions return error without forwarding."""
        proxy.start()
        result = asyncio.run(
            proxy.handle_call("github__create_issue", {"title": "Test"})
        )
        assert result.verdict == "BLOCKED"
        assert result.forwarded is False
        assert "blocked by constraint envelope" in result.error

    def test_unknown_server_blocked(self, proxy):
        proxy.start()
        result = asyncio.run(proxy.handle_call("unknown__tool", {"arg": "val"}))
        assert result.verdict == "BLOCKED"
        assert "not registered" in result.error

    def test_invalid_tool_format_blocked(self, proxy):
        proxy.start()
        result = asyncio.run(proxy.handle_call("no_separator", {}))
        assert result.verdict == "BLOCKED"
        assert "Invalid tool name format" in result.error

    def test_no_handler_blocked(self, proxy):
        proxy.start()
        result = asyncio.run(proxy.handle_call("filesystem__nonexistent", {}))
        assert result.verdict == "BLOCKED"
        assert "not registered" in result.error


class TestProxyAuditTrail:
    def test_call_log_recorded(self, proxy):
        proxy.start()
        asyncio.run(proxy.handle_call("filesystem__read_file", {"path": "/a.txt"}))
        asyncio.run(proxy.handle_call("github__create_issue", {"title": "Blocked"}))
        assert len(proxy.call_log) == 2
        assert proxy.call_log[0]["forwarded"] is True
        assert proxy.call_log[1]["forwarded"] is False

    def test_blocked_calls_logged(self, proxy):
        proxy.start()
        asyncio.run(proxy.handle_call("github__create_issue", {"title": "Test"}))
        assert proxy.call_log[0]["verdict"] == "BLOCKED"

    def test_forwarded_calls_have_anchor(self, proxy):
        proxy.start()
        result = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/b.txt"})
        )
        assert result.anchor_id is not None
        # Anchor should be in the call log
        assert proxy.call_log[0]["anchor_id"] == result.anchor_id


class TestProxyFailClosed:
    def test_crash_recovery(self, proxy):
        """After stop, no calls succeed. After restart, they do."""
        proxy.start()
        result1 = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/test.txt"})
        )
        assert result1.forwarded is True

        proxy.stop()
        result2 = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/test.txt"})
        )
        assert result2.forwarded is False
        assert "fail-closed" in result2.error

        proxy.start()
        result3 = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/test.txt"})
        )
        assert result3.forwarded is True

    def test_handler_error_logged(self, proxy):
        """If handler raises, error is recorded but call was forwarded."""

        async def failing_handler(**kwargs):
            raise RuntimeError("Mock failure")

        proxy.register_tool_handler("filesystem", "failing_tool", failing_handler)
        proxy.start()
        result = asyncio.run(proxy.handle_call("filesystem__failing_tool", {}))
        assert result.forwarded is True
        assert result.error == "Tool execution failed"


class TestProxyMultipleServers:
    def test_multiple_servers_isolated(self, proxy):
        """Each server has its own constraint enforcement."""
        proxy.start()
        # filesystem (file_operations) → allowed
        r1 = asyncio.run(
            proxy.handle_call("filesystem__read_file", {"path": "/test.txt"})
        )
        assert r1.forwarded is True

        # github (external_communication) → blocked
        r2 = asyncio.run(proxy.handle_call("github__create_issue", {"title": "Test"}))
        assert r2.forwarded is False

    def test_tool_namespacing_prevents_collision(self, proxy):
        """Tools from different servers with same name don't collide."""

        async def fs_list(**kwargs):
            return "fs list"

        async def gh_list(**kwargs):
            return "gh list"

        proxy.register_tool_handler("filesystem", "list", fs_list)
        proxy.register_tool_handler("github", "list", gh_list)
        proxy.start()

        r1 = asyncio.run(proxy.handle_call("filesystem__list", {}))
        assert r1.result == "fs list"
        # github list is blocked because action_category = external_communication
