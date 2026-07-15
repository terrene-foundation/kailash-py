# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 - MCP spec-compliance parity (revision 2025-11-25).

Behavioral pins (call the function, assert raise/return - never source-grep,
per ``rules/testing.md``) for the three in-shard fixes:

1. **Local-server spawn safety** - ``kailash_mcp.security.validate_spawn_command``
   fails CLOSED by default: an unlisted command is REJECTED, never
   warn-and-allowed. Wired into all three ``MCPClient`` stdio spawn sites via
   ``MCPClient._guard_spawn_command``.
2. **Request-id rules** - ``JsonRpcRequest.from_dict`` rejects an EXPLICIT
   ``null`` id (distinct from an ABSENT id = notification).
3. **protocolVersion negotiation** - ``negotiate_protocol_version`` echoes a
   supported requested version, else returns the newest supported version
   (never a hardcoded fixed string).
"""

import pytest

from kailash_mcp.client import MCPClient
from kailash_mcp.errors import MCPErrorCode
from kailash_mcp.protocol.messages import JsonRpcRequest, JsonRpcValidationError
from kailash_mcp.security import (
    DEFAULT_ALLOWED_MCP_COMMANDS,
    SpawnSecurityError,
    validate_spawn_command,
)
from kailash_mcp.server import (
    LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    negotiate_protocol_version,
)


# ---------------------------------------------------------------------------
# 1. Local-server spawn safety - fail closed by default
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize("launcher", sorted(DEFAULT_ALLOWED_MCP_COMMANDS))
def test_default_allowlist_permits_standard_launchers(launcher):
    """Every curated launcher is permitted under the default (no raise)."""
    validate_spawn_command(launcher)  # must not raise


@pytest.mark.regression
@pytest.mark.parametrize(
    "command",
    ["sh", "bash", "zsh", "cmd", "powershell", "curl", "wget", "rm", "make"],
)
def test_default_allowlist_rejects_unlisted_command(command):
    """An unlisted command is REJECTED fail-closed - not warn-and-allowed."""
    with pytest.raises(SpawnSecurityError):
        validate_spawn_command(command)


@pytest.mark.regression
def test_absolute_path_to_unlisted_binary_rejected():
    """A full absolute path whose basename is unlisted is rejected."""
    with pytest.raises(SpawnSecurityError):
        validate_spawn_command("/usr/bin/curl")


@pytest.mark.regression
def test_absolute_path_to_listed_basename_permitted():
    """A full path whose basename IS a listed launcher is permitted."""
    validate_spawn_command("/usr/local/bin/python3")  # basename python3 -> ok


@pytest.mark.regression
@pytest.mark.parametrize("bad", ["../evil", "/opt/../bin/sh", "a/../../sh"])
def test_path_traversal_rejected_even_with_opt_out(bad):
    """Path traversal is rejected regardless of the arbitrary opt-out."""
    with pytest.raises(SpawnSecurityError):
        validate_spawn_command(bad, allow_arbitrary=True)


@pytest.mark.regression
@pytest.mark.parametrize("empty", ["", None, 123, ["python"]])
def test_empty_or_non_string_command_rejected(empty):
    with pytest.raises(SpawnSecurityError):
        validate_spawn_command(empty)


@pytest.mark.regression
def test_allow_arbitrary_opt_out_permits_unlisted():
    """The explicit opt-out permits an otherwise-unlisted command."""
    validate_spawn_command("my-custom-mcp-server", allow_arbitrary=True)


@pytest.mark.regression
def test_explicit_allowlist_narrows_and_rejects_default_launchers():
    """An explicit allowlist REPLACES the default (fail-closed narrowing)."""
    validate_spawn_command("python", allowed_commands=["python"])  # ok
    with pytest.raises(SpawnSecurityError):
        # uvx is in the DEFAULT set but NOT in this explicit allowlist.
        validate_spawn_command("uvx", allowed_commands=["python"])


@pytest.mark.regression
def test_empty_allowlist_rejects_everything():
    """An explicit empty allowlist is the maximally-closed posture."""
    with pytest.raises(SpawnSecurityError):
        validate_spawn_command("python", allowed_commands=[])


@pytest.mark.regression
def test_spawn_error_carries_authorization_error_code():
    """The typed error carries the AUTHORIZATION_FAILED JSON-RPC code."""
    with pytest.raises(SpawnSecurityError) as exc_info:
        validate_spawn_command("sh")
    assert exc_info.value.error_code == MCPErrorCode.AUTHORIZATION_FAILED


@pytest.mark.regression
def test_mcpclient_guard_reads_config_allowlist():
    """MCPClient._guard_spawn_command enforces the fail-closed default."""
    client = MCPClient()
    client._guard_spawn_command("python")  # default set -> ok
    with pytest.raises(SpawnSecurityError):
        client._guard_spawn_command("sh")


@pytest.mark.regression
def test_mcpclient_guard_honors_allow_arbitrary_config():
    """MCPClient reads allow_arbitrary_commands from its config."""
    client = MCPClient(config={"allow_arbitrary_commands": True})
    client._guard_spawn_command("my-custom-server")  # opt-out -> ok


@pytest.mark.regression
def test_mcpclient_guard_honors_explicit_allowlist_config():
    client = MCPClient(config={"allowed_commands": ["python"]})
    client._guard_spawn_command("python")
    with pytest.raises(SpawnSecurityError):
        client._guard_spawn_command("uvx")


# ---------------------------------------------------------------------------
# 2. Request-id rules - explicit null id is invalid (distinct from absent)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_explicit_null_id_rejected():
    """An explicit ``{"id": null}`` is invalid - not a notification."""
    with pytest.raises(JsonRpcValidationError):
        JsonRpcRequest.from_dict({"jsonrpc": "2.0", "method": "x", "id": None})


@pytest.mark.regression
def test_absent_id_is_notification():
    """An ABSENT id denotes a notification (id=None, is_notification True)."""
    req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "method": "notify"})
    assert req.id is None
    assert req.is_notification is True


@pytest.mark.regression
def test_present_id_is_request():
    req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "method": "x", "id": 7})
    assert req.id == 7
    assert req.is_notification is False


# ---------------------------------------------------------------------------
# 3. protocolVersion negotiation - genuine, not a hardcoded echo
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize("version", SUPPORTED_PROTOCOL_VERSIONS)
def test_negotiate_echoes_supported_requested_version(version):
    """A supported requested version is echoed back verbatim."""
    assert negotiate_protocol_version(version) == version


@pytest.mark.regression
@pytest.mark.parametrize("requested", ["1999-01-01", "", None, 123, "2099-12-31"])
def test_negotiate_returns_latest_for_unsupported_or_absent(requested):
    """An unsupported / absent requested version yields the newest supported."""
    assert negotiate_protocol_version(requested) == LATEST_PROTOCOL_VERSION


@pytest.mark.regression
def test_latest_is_newest_of_supported_set():
    assert LATEST_PROTOCOL_VERSION == SUPPORTED_PROTOCOL_VERSIONS[0]


# ---------------------------------------------------------------------------
# 4. Sibling spawn-site parity — the fail-closed guard is wired at EVERY
#    process-spawn surface, not only the MCPClient sites. Surfaced by an
#    adversarial security review of the first shard (enforcement-surface
#    parity, ``rules/security.md`` § Multi-Site Kwarg Plumbing).
# ---------------------------------------------------------------------------
import asyncio

from kailash_mcp.discovery.discovery import HealthChecker, ServerInfo
from kailash_mcp.transports.transports import EnhancedStdioTransport


@pytest.mark.asyncio
async def test_enhanced_stdio_transport_connect_fails_closed(monkeypatch):
    """EnhancedStdioTransport.connect rejects an unlisted command BEFORE spawn.

    The typed SpawnSecurityError must propagate (not be wrapped into a generic
    TransportError), and the subprocess must never be spawned.
    """
    spawned = {"called": False}

    async def _no_spawn(*args, **kwargs):
        spawned["called"] = True
        raise AssertionError("spawn must not be reached for an unlisted command")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _no_spawn)
    transport = EnhancedStdioTransport(command="sh")  # shell — not in the allowlist
    with pytest.raises(SpawnSecurityError) as exc_info:
        await transport.connect()
    assert exc_info.value.error_code == MCPErrorCode.AUTHORIZATION_FAILED
    assert spawned["called"] is False


@pytest.mark.asyncio
async def test_enhanced_stdio_transport_default_launcher_reaches_spawn(monkeypatch):
    """A listed launcher (python) passes the guard and reaches the spawn call."""
    reached = {"cmd": None}

    async def _fake_spawn(cmd, *args, **kwargs):
        reached["cmd"] = cmd
        raise RuntimeError("stub-spawn-stop")  # halt before real I/O tasks

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)
    transport = EnhancedStdioTransport(command="python")
    with pytest.raises(Exception):  # TransportError from the stubbed spawn
        await transport.connect()
    assert reached["cmd"] == "python"  # guard passed, spawn reached


@pytest.mark.asyncio
async def test_enhanced_stdio_transport_allow_arbitrary_bypasses_guard(monkeypatch):
    """allow_arbitrary_commands=True bypasses the allowlist and reaches spawn."""
    reached = {"cmd": None}

    async def _fake_spawn(cmd, *args, **kwargs):
        reached["cmd"] = cmd
        raise RuntimeError("stub-spawn-stop")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)
    transport = EnhancedStdioTransport(
        command="my-unlisted-server", allow_arbitrary_commands=True
    )
    with pytest.raises(Exception):
        await transport.connect()
    assert reached["cmd"] == "my-unlisted-server"  # opt-out honored, spawn reached


@pytest.mark.asyncio
async def test_discovery_health_check_blocks_unlisted_command():
    """HealthChecker.check_server_health reports 'blocked' for an unlisted stdio
    command instead of spawning it to probe liveness."""
    checker = HealthChecker(None)
    server = ServerInfo(
        name="evil", transport="stdio", command="sh", args=["-c", "echo pwned"]
    )
    result = await checker.check_server_health(server)
    assert result["status"] == "blocked"


@pytest.mark.asyncio
async def test_discovery_health_check_allows_listed_launcher(monkeypatch):
    """A listed launcher passes the discovery guard and reaches the probe spawn."""
    reached = {"cmd": None}

    async def _fake_spawn(cmd, *args, **kwargs):
        reached["cmd"] = cmd
        raise RuntimeError("stub-spawn-stop")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)
    checker = HealthChecker(None)
    server = ServerInfo(name="ok", transport="stdio", command="python", args=["-V"])
    result = await checker.check_server_health(server)
    # spawn was reached (guard passed); the stub failure surfaces as unhealthy,
    # NOT blocked — the key assertion is status != "blocked".
    assert result["status"] != "blocked"
    assert reached["cmd"] == "python"
