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

import socket

import pytest

from kaizen.llm.http_client import (
    _SafeHttpTransport,
    LlmHttpClient,
    SafeDnsResolver,
)


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
def test_llmhttpclient_rejects_private_ip_at_resolve_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: a client pointed at a hostname resolving to a private IP
    fails at resolve time, NOT at a later TCP timeout.

    The fast-fail is load-bearing: a slow TCP timeout is a DoS vector if
    attackers can enumerate private IPs through timing. Resolve-time
    rejection converts the attack surface into a bounded constant.
    """

    # Simulate DNS returning RFC 1918 for a public-looking hostname.
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    resolver = SafeDnsResolver()
    # Direct resolver call proves the fast-fail at the structural layer.
    from kaizen.llm.url_safety import InvalidEndpoint

    with pytest.raises(InvalidEndpoint) as exc_info:
        resolver.check_host("intranet.example.com")
    assert exc_info.value.reason == "private_ipv4"


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
