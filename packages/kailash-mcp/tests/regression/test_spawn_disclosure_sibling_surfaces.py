# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the #2004 spawn-command disclosure at its SIBLING surfaces.

The #2004 fix converted the rejected command to a ``basename#fingerprint``
reference inside ``SpawnSecurityError``. That covers every sink that reads the
EXCEPTION. It does not cover sinks that read ``command`` / ``args`` straight off
the untrusted server config, which inherit nothing from it -- and those existed,
unswept, in the same wheel:

* ``MCPClient.health_check()`` returned ``_get_server_key()`` in its ``server``
  field on BOTH the healthy and unhealthy paths, and ``discover_tools()`` logged
  it on the ordinary success and failure paths. That key renders
  ``stdio://<command>:<arg>:<arg>...`` -- the credential verbatim.
* ``EnhancedStdioTransport.get_process_info()`` returned
  ``{"command": [self.command] + self.args}`` raw.

These are behavioural pins (call the function, assert on what comes back --
never source-grep, per ``rules/testing.md``). They FAIL against the pre-fix
source, which is what makes them evidence.

The cache key itself is deliberately NOT sanitised -- it must stay exact so two
servers differing only in arguments do not collide -- so there is a pin for that
too. A future "tidy-up" that routes the cache key through the fingerprint would
introduce a silent cache-collision bug, and this test refuses it.
"""

import asyncio

import pytest

from kailash_mcp.client import MCPClient
from kailash_mcp.transports.transports import EnhancedStdioTransport

SECRET = "SUPERSECRET_TOKEN_VALUE"

STDIO_CFG = {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@vendor/mcp-server", f"--token={SECRET}"],
}


@pytest.fixture
def client() -> MCPClient:
    """A client instance without running __init__ (these helpers are pure)."""
    return MCPClient.__new__(MCPClient)


class TestServerRefIsDisclosureSafe:
    """``_get_server_ref`` is what callers and logs see; it must not leak."""

    def test_stdio_ref_omits_the_credential_bearing_args(self, client):
        ref = client._get_server_ref(STDIO_CFG)
        assert SECRET not in ref
        assert "--token" not in ref
        # It still identifies the executable, so the log stays useful.
        assert ref.startswith("stdio://npx#")

    def test_url_transport_ref_masks_userinfo_and_query_credentials(self, client):
        cfg = {
            "transport": "sse",
            "url": f"https://user:{SECRET}@host/mcp?token={SECRET}",
        }
        ref = client._get_server_ref(cfg)
        assert SECRET not in ref

    def test_bare_string_config_is_masked_not_returned_raw(self, client):
        ref = client._get_server_ref(f"https://user:{SECRET}@host/mcp")
        assert SECRET not in ref

    def test_servers_differing_only_in_args_get_DISTINCT_refs(self, client):
        """A safe ref must not collapse distinct servers into one log line.

        Fingerprinting only the executable would render every ``npx`` server
        identically, which is why the whole command line is fingerprinted.
        """
        other = dict(STDIO_CFG, args=["-y", "@vendor/mcp-server", "--token=OTHER"])
        assert client._get_server_ref(STDIO_CFG) != client._get_server_ref(other)

    def test_unknown_transport_does_not_fall_through_to_raw_config(self, client):
        ref = client._get_server_ref(
            {
                "transport": "carrier-pigeon",
                "command": "npx",
                "args": [f"--token={SECRET}"],
            }
        )
        assert SECRET not in ref


class TestCacheKeyStaysExact:
    """The INTERNAL cache key must remain precise -- collisions would be a bug."""

    def test_cache_key_distinguishes_servers_differing_only_in_args(self, client):
        other = dict(STDIO_CFG, args=["-y", "@vendor/mcp-server", "--token=OTHER"])
        assert client._get_server_key(STDIO_CFG) != client._get_server_key(other)

    def test_cache_key_is_not_the_disclosure_safe_ref(self, client):
        """Pin the separation itself.

        If someone "fixes" the leak by sanitising the cache key instead of the
        disclosed value, this fails -- and it should, because that trades a
        disclosure bug for a correctness bug.
        """
        assert client._get_server_key(STDIO_CFG) != client._get_server_ref(STDIO_CFG)


class TestHealthCheckPayloadDoesNotDiscloseTheCommand:
    """Both health-check exit paths report the safe ref, not the raw command."""

    def _run(self, client, monkeypatch, *, fail: bool):
        async def _discover(server_config, force_refresh=False):
            if fail:
                raise RuntimeError("boom")
            return ["tool-a"]

        monkeypatch.setattr(client, "discover_tools", _discover)
        client.metrics = None
        return asyncio.run(client.health_check(STDIO_CFG))

    def test_healthy_path(self, client, monkeypatch):
        result = self._run(client, monkeypatch, fail=False)
        assert result["status"] == "healthy"
        assert SECRET not in str(result)

    def test_unhealthy_path(self, client, monkeypatch):
        result = self._run(client, monkeypatch, fail=True)
        assert result["status"] == "unhealthy"
        assert SECRET not in str(result)


class TestProcessInfoDoesNotReturnRawArgv:
    def _transport(self) -> EnhancedStdioTransport:
        t = EnhancedStdioTransport.__new__(EnhancedStdioTransport)
        t.command = "npx"
        t.args = ["-y", "@vendor/mcp-server", f"--token={SECRET}"]
        t.working_directory = "/tmp"

        class _Proc:
            pid = 4242
            returncode = None

        t.process = _Proc()
        return t

    def test_command_ref_replaces_raw_command(self):
        info = asyncio.run(self._transport().get_process_info())
        assert SECRET not in str(info)
        assert "command_ref" in info
        # BREAKING rename, pinned: the raw key must NOT be reintroduced as an
        # alias, because a populated `command` keeps the credential on the wire.
        assert "command" not in info

    def test_still_reports_the_process_facts_it_exists_to_report(self):
        info = asyncio.run(self._transport().get_process_info())
        assert info["pid"] == 4242
        assert info["working_directory"] == "/tmp"

    def test_no_process_returns_empty(self):
        t = EnhancedStdioTransport.__new__(EnhancedStdioTransport)
        t.process = None
        assert asyncio.run(t.get_process_info()) == {}
