# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""§6 -- `LlmHttpClient.SafeDnsResolver` rejects literal private IPs.

Every outbound LLM HTTP call routes through `SafeDnsResolver.check_host`
at TCP-connect time. Literal private / link-local / loopback / multicast
/ metadata IPs MUST be rejected with a typed `InvalidEndpoint`, with the
reason code drawn from the same allowlist as `url_safety.check_url`.

This test is the structural complement to
`tests/unit/llm/test_endpoint.py` (which covers URL-safety at Endpoint
construction time). The SafeDnsResolver runs at the LATER stage -- at
the moment httpx opens a TCP socket -- so a TOCTOU window between URL
parse and TCP connect cannot exist.
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.http_client import SafeDnsResolver


@pytest.fixture
def resolver() -> SafeDnsResolver:
    return SafeDnsResolver()


@pytest.mark.parametrize(
    "host,expected_reason",
    [
        ("10.0.0.1", "private_ipv4"),
        ("10.255.255.255", "private_ipv4"),
        ("172.16.0.1", "private_ipv4"),
        ("172.31.255.254", "private_ipv4"),
        ("192.168.0.1", "private_ipv4"),
        ("192.168.1.100", "private_ipv4"),
        ("127.0.0.1", "private_ipv4"),
        ("127.1.2.3", "private_ipv4"),
        ("169.254.0.1", "private_ipv4"),  # link-local but triggers private_ipv4 bucket
    ],
)
def test_resolver_rejects_private_ipv4(
    resolver: SafeDnsResolver, host: str, expected_reason: str
) -> None:
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host(host)
    assert excinfo.value.reason == expected_reason


def test_resolver_rejects_aws_metadata_endpoint(resolver: SafeDnsResolver) -> None:
    """169.254.169.254 is the AWS/GCP/Azure metadata service; it MUST
    surface as `metadata_service` (not `private_ipv4`) so downstream
    alerting can distinguish metadata exfiltration attempts.
    """
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host("169.254.169.254")
    assert excinfo.value.reason == "metadata_service"


def test_resolver_rejects_ipv6_metadata_endpoint(
    resolver: SafeDnsResolver,
) -> None:
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host("fd00:ec2::254")
    assert excinfo.value.reason == "metadata_service"


@pytest.mark.parametrize(
    "host,expected_reason",
    [
        ("::1", "loopback"),
        ("fe80::1", "link_local"),
        ("fe80::dead:beef", "link_local"),
    ],
)
def test_resolver_rejects_ipv6_loopback_and_link_local(
    resolver: SafeDnsResolver, host: str, expected_reason: str
) -> None:
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host(host)
    assert excinfo.value.reason == expected_reason


@pytest.mark.parametrize(
    "host",
    [
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",  # IPv4-mapped private
        "::ffff:169.254.169.254",  # IPv4-mapped metadata
    ],
)
def test_resolver_rejects_ipv4_mapped_ipv6(
    resolver: SafeDnsResolver, host: str
) -> None:
    """RFC 4291 IPv4-mapped IPv6 (::ffff:a.b.c.d) MUST be rejected --
    otherwise an attacker wraps a loopback in the v6 form to bypass a
    v4-only guard.
    """
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host(host)
    # All three reasons (metadata / ipv4_mapped / private_ipv4) surface here;
    # the metadata-IP takes precedence even when wrapped.
    assert excinfo.value.reason in {"ipv4_mapped", "metadata_service"}


def test_resolver_accepts_public_literal_ipv4(resolver: SafeDnsResolver) -> None:
    """A public literal IPv4 -- e.g. 1.1.1.1 -- is NOT private and MUST
    pass the check. The resolver is SSRF-defense-only, not general URL
    validation; public IPs are the legitimate case.
    """
    # Must not raise.
    resolver.check_host("1.1.1.1")
    resolver.check_host("8.8.8.8")


def test_resolver_accepts_public_literal_ipv6(resolver: SafeDnsResolver) -> None:
    # 2606:4700:4700::1111 is Cloudflare DNS public IPv6 -- legitimate.
    resolver.check_host("2606:4700:4700::1111")


def test_resolver_rejects_malformed_host(resolver: SafeDnsResolver) -> None:
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host("")
    assert excinfo.value.reason == "malformed_url"
    with pytest.raises(InvalidEndpoint) as excinfo:
        resolver.check_host(None)  # type: ignore[arg-type]
    assert excinfo.value.reason == "malformed_url"


def test_resolver_kind_is_stable_literal(resolver: SafeDnsResolver) -> None:
    """Cross-SDK parity: the kind() label is 'safe_dns'."""
    assert resolver.kind() == "safe_dns"
