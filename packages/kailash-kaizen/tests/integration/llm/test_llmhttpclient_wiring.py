# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring: LlmHttpClient routes through SafeDnsResolver (#498 S4c, MED-2).

Per `rules/facade-manager-detection.md` §2, every manager-shape class
(`LlmHttpClient`) MUST have a Tier 2 wiring file whose absence is
grep-able by the predictable name.

This test proves the structural claim that `LlmHttpClient.__init__`
actually installs `SafeDnsResolver` on the underlying httpx transport —
NOT just that `SafeDnsResolver` exists in isolation. The wiring is the
security boundary; the isolated unit tests on SafeDnsResolver prove
the resolver's own logic but not that the framework uses it.
"""

from __future__ import annotations

import pytest

from kaizen.llm.http_client import LlmHttpClient, _SafeHttpTransport


@pytest.mark.integration
def test_llmhttpclient_installs_safe_dns_resolver_structurally() -> None:
    """Constructing LlmHttpClient wires SafeDnsResolver into the httpx transport.

    This is the orphan-detection test: LlmHttpClient is a facade; the
    resolver MUST be structurally installed, not optionally. If a future
    refactor accidentally removes the install, this test fires before
    the regression ships.
    """
    client = LlmHttpClient(
        deployment_preset="test_structural",
    )
    try:
        # httpx.AsyncClient's _transport attribute carries the transport.
        transport = client._client._transport  # type: ignore[attr-defined]
        assert isinstance(transport, _SafeHttpTransport), (
            "LlmHttpClient MUST install _SafeHttpTransport (wrapping "
            "SafeDnsResolver) on every outbound request. If this fails, "
            "a refactor removed the structural SSRF defense."
        )
        # Resolver reachable from transport — stable label means observability
        # dashboards (which use .kind()) can tell which resolver was wired.
        assert transport._resolver.kind() == "safe_dns"  # type: ignore[attr-defined]
    finally:
        # Close client cleanly — required for test isolation.
        import asyncio

        asyncio.run(client.aclose())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llmhttpclient_localhost_request_keeps_literal_loopback_blocked(
    httpserver,
) -> None:
    """The local-provider carve-out reaches a real server only by its label."""
    from urllib.parse import urlparse

    from kaizen.llm.url_safety import InvalidEndpoint, check_url

    httpserver.expect_request("/health").respond_with_data("ready")
    port = urlparse(httpserver.url_for("/health")).port
    url = f"http://localhost:{port}/health"
    check_url(url)
    async with LlmHttpClient(timeout=5.0) as client:
        with pytest.raises(InvalidEndpoint) as exc_info:
            await client.get(f"http://127.0.0.1:{port}/health")
        assert exc_info.value.reason == "loopback"
        response = await client.get(url)
        assert response.status_code == 200
        assert response.text == "ready"
    httpserver.check_assertions()


@pytest.mark.integration
def test_llmhttpclient_naming_convention_exists() -> None:
    """Wiring-test file naming convention per facade-manager-detection §2.

    This test file's existence is itself the guard. The name
    `test_llmhttpclient_wiring.py` is what /redteam greps for when
    auditing whether `LlmHttpClient` is wired through its Tier 2 path.
    """
    import pathlib

    here = pathlib.Path(__file__).resolve()
    assert here.name == "test_llmhttpclient_wiring.py"
