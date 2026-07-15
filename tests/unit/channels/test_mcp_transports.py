# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for MCP transport primitives — issue #600."""

from __future__ import annotations

import pytest

from kailash.channels.mcp import (
    HttpTransport,
    ProtocolError,
    SseTransport,
    StdioTransport,
    Transport,
    TransportError,
    validate_url,
)


# ----- validate_url SSRF guard ---------------------------------------------


class TestValidateUrl:
    def test_accepts_https(self) -> None:
        assert (
            validate_url("https://example.com/mcp", allow_private=False)
            == "https://example.com/mcp"
        )

    def test_accepts_http(self) -> None:
        assert (
            validate_url("http://example.com/mcp", allow_private=False)
            == "http://example.com/mcp"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "ws://example.com",
            "data:text/plain;,abc",
        ],
    )
    def test_rejects_non_http_scheme(self, url: str) -> None:
        with pytest.raises(TransportError, match="scheme"):
            validate_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/mcp",
            "http://localhost/mcp",
            "http://10.0.0.1/mcp",
            "http://192.168.1.1/mcp",
            "http://172.16.0.1/mcp",
            "http://[::1]/mcp",
        ],
    )
    def test_rejects_private_by_default(self, url: str) -> None:
        with pytest.raises(TransportError):
            validate_url(url, allow_private=False)

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/mcp",
            "http://10.0.0.1/mcp",
        ],
    )
    def test_allow_private_unblocks(self, url: str) -> None:
        # Should not raise — caller opted in.
        assert validate_url(url, allow_private=True) == url

    def test_rejects_empty(self) -> None:
        with pytest.raises(TransportError):
            validate_url("")

    def test_rejects_no_host(self) -> None:
        with pytest.raises(TransportError):
            validate_url("http:///path")


# ----- HttpTransport --------------------------------------------------------


class TestHttpTransport:
    def test_construct_with_validated_url(self) -> None:
        t = HttpTransport("https://example.com/mcp")
        assert t.endpoint_url == "https://example.com/mcp"

    def test_construct_rejects_private_by_default(self) -> None:
        with pytest.raises(TransportError):
            HttpTransport("http://127.0.0.1/mcp")

    def test_construct_allow_private(self) -> None:
        t = HttpTransport("http://127.0.0.1/mcp", allow_private=True)
        assert t.endpoint_url == "http://127.0.0.1/mcp"

    def test_construct_rejects_non_http_scheme(self) -> None:
        with pytest.raises(TransportError):
            HttpTransport("file:///etc/passwd")

    def test_is_transport_subclass(self) -> None:
        assert issubclass(HttpTransport, Transport)

    @pytest.mark.asyncio
    async def test_receive_raises_not_implemented(self) -> None:
        t = HttpTransport("https://example.com/mcp")
        with pytest.raises(NotImplementedError):
            await t.receive()
        await t.close()


# ----- SseTransport ---------------------------------------------------------


class TestSseTransport:
    def test_construct_with_base_url(self) -> None:
        t = SseTransport("https://example.com")
        assert t.base_url == "https://example.com"

    def test_strips_trailing_slash(self) -> None:
        t = SseTransport("https://example.com/")
        assert t.base_url == "https://example.com"

    def test_message_url_default(self) -> None:
        t = SseTransport("https://example.com")
        assert t.message_url == "https://example.com/message"

    def test_sse_url_default(self) -> None:
        t = SseTransport("https://example.com")
        assert t.sse_url == "https://example.com/sse"

    def test_construct_rejects_non_http_scheme(self) -> None:
        with pytest.raises(TransportError):
            SseTransport("ftp://example.com")

    def test_construct_rejects_private_by_default(self) -> None:
        with pytest.raises(TransportError):
            SseTransport("http://127.0.0.1")

    def test_is_transport_subclass(self) -> None:
        assert issubclass(SseTransport, Transport)


# ----- StdioTransport -------------------------------------------------------


class TestStdioTransport:
    def test_is_transport_subclass(self) -> None:
        assert issubclass(StdioTransport, Transport)

    @pytest.mark.asyncio
    async def test_spawn_rejects_disallowed_command(self) -> None:
        with pytest.raises(TransportError):
            await StdioTransport.spawn(
                command="/bin/bash",
                args=["-c", "echo pwned"],
                allowed_commands=["python3", "node"],
            )

    @pytest.mark.asyncio
    async def test_spawn_validates_empty_command(self) -> None:
        with pytest.raises(TransportError):
            await StdioTransport.spawn(command="", args=[])

    # ----- #1712: fail-closed spawn allowlist by default -------------------

    def test_validate_spawn_command_default_permits_launcher(self) -> None:
        from kailash.channels.mcp.stdio import validate_spawn_command

        validate_spawn_command("python3")  # curated default set -> no raise

    @pytest.mark.parametrize("cmd", ["bash", "sh", "curl", "rm", "/usr/bin/curl"])
    def test_validate_spawn_command_default_rejects_unlisted(self, cmd) -> None:
        from kailash.channels.mcp.stdio import validate_spawn_command

        with pytest.raises(TransportError):
            validate_spawn_command(cmd)  # fail-closed, not warn-and-allow

    def test_validate_spawn_command_opt_out_permits_arbitrary(self) -> None:
        from kailash.channels.mcp.stdio import validate_spawn_command

        validate_spawn_command("my-custom-server", allow_arbitrary_commands=True)

    @pytest.mark.parametrize("bad", ["../evil", "a/../../sh"])
    def test_validate_spawn_command_rejects_traversal_even_with_opt_out(
        self, bad
    ) -> None:
        from kailash.channels.mcp.stdio import validate_spawn_command

        with pytest.raises(TransportError):
            validate_spawn_command(bad, allow_arbitrary_commands=True)

    @pytest.mark.asyncio
    async def test_spawn_default_rejects_unlisted_command(self) -> None:
        # No allowed_commands: the fail-closed default rejects an unlisted
        # command BEFORE spawning a subprocess (MCP 2025-11-25 spawn safety).
        with pytest.raises(TransportError):
            await StdioTransport.spawn(command="bash", args=["-c", "echo hi"])


# ----- exception hierarchy --------------------------------------------------


class TestExceptions:
    def test_protocol_error_is_transport_error(self) -> None:
        assert issubclass(ProtocolError, TransportError)

    def test_transport_error_is_exception(self) -> None:
        assert issubclass(TransportError, Exception)
