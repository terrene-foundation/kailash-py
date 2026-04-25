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
        with pytest.raises(ValueError, match="scheme"):
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
        with pytest.raises(ValueError):
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
        with pytest.raises(ValueError):
            validate_url("")

    def test_rejects_no_host(self) -> None:
        with pytest.raises(ValueError):
            validate_url("http:///path")


# ----- HttpTransport --------------------------------------------------------


class TestHttpTransport:
    def test_construct_with_validated_url(self) -> None:
        t = HttpTransport("https://example.com/mcp")
        assert t.endpoint_url == "https://example.com/mcp"

    def test_construct_rejects_private_by_default(self) -> None:
        with pytest.raises(ValueError):
            HttpTransport("http://127.0.0.1/mcp")

    def test_construct_allow_private(self) -> None:
        t = HttpTransport("http://127.0.0.1/mcp", allow_private=True)
        assert t.endpoint_url == "http://127.0.0.1/mcp"

    def test_construct_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ValueError):
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
        with pytest.raises(ValueError):
            SseTransport("ftp://example.com")

    def test_construct_rejects_private_by_default(self) -> None:
        with pytest.raises(ValueError):
            SseTransport("http://127.0.0.1")

    def test_is_transport_subclass(self) -> None:
        assert issubclass(SseTransport, Transport)


# ----- StdioTransport -------------------------------------------------------


class TestStdioTransport:
    def test_is_transport_subclass(self) -> None:
        assert issubclass(StdioTransport, Transport)

    @pytest.mark.asyncio
    async def test_spawn_rejects_disallowed_command(self) -> None:
        with pytest.raises(ValueError):
            await StdioTransport.spawn(
                command="/bin/bash",
                args=["-c", "echo pwned"],
                allowed=["python3", "node"],
            )

    @pytest.mark.asyncio
    async def test_spawn_validates_empty_command(self) -> None:
        with pytest.raises(ValueError):
            await StdioTransport.spawn(command="", args=[])


# ----- exception hierarchy --------------------------------------------------


class TestExceptions:
    def test_protocol_error_is_transport_error(self) -> None:
        assert issubclass(ProtocolError, TransportError)

    def test_transport_error_is_exception(self) -> None:
        assert issubclass(TransportError, Exception)
