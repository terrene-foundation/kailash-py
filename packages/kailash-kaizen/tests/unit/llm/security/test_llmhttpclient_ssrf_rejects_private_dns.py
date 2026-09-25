# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SSRF defense — SafeDnsResolver.check_host rejects private ranges (#498 S4c).

Companion to `test_llmhttpclient_ssrf_rejects_private_ips.py`. Covers:

1. Literal private IPs rejected with the correct reason-code taxonomy.
2. Public IPs pass through (no false positives).
3. DNS that resolves to a private IP is rejected at resolve time — the
   DNS-rebinding / TOCTOU defense.

Real resolver, real private-range checks — no mocking of the allowlist.
DNS resolution itself is monkey-patched so the test is deterministic.
"""

from __future__ import annotations

import socket

import pytest

from kaizen.llm.http_client import SafeDnsResolver
from kaizen.llm.url_safety import InvalidEndpoint


@pytest.mark.parametrize(
    "private_ip,expected_reason",
    [
        ("10.0.0.1", "private_ipv4"),
        ("10.255.255.255", "private_ipv4"),
        ("172.16.0.1", "private_ipv4"),
        ("172.31.255.255", "private_ipv4"),
        ("192.168.1.1", "private_ipv4"),
        # loopback / link-local get their OWN buckets here, matching the
        # parse-time gate exactly -- both now share network_guard.ip_reason.
        ("127.0.0.1", "loopback"),
        ("127.255.255.254", "loopback"),
        ("169.254.169.254", "metadata_service"),  # AWS / GCP metadata IP
        ("169.254.0.1", "link_local"),  # link-local (non-metadata)
        ("0.0.0.0", "private_ipv4"),
        ("::1", "loopback"),
        ("fe80::1", "link_local"),
        ("fc00::1", "private_ipv6"),
    ],
)
def test_safe_dns_resolver_rejects_private_ip_literal(
    private_ip: str, expected_reason: str
) -> None:
    """Literal private IPs rejected with the correct reason code."""
    resolver = SafeDnsResolver()
    with pytest.raises(InvalidEndpoint) as exc_info:
        resolver.check_host(private_ip)
    # reason code is the enum-like string carried on InvalidEndpoint
    assert exc_info.value.reason == expected_reason, (
        f"Expected reason={expected_reason!r} for {private_ip}, "
        f"got {exc_info.value.reason!r}"
    )


@pytest.mark.parametrize(
    "public_ip",
    [
        "8.8.8.8",  # Google DNS
        "1.1.1.1",  # Cloudflare DNS
        "2606:4700:4700::1111",  # Cloudflare DNS IPv6
    ],
)
def test_safe_dns_resolver_accepts_public_ip_literal(public_ip: str) -> None:
    """Public IPs pass through without error (no false positives)."""
    resolver = SafeDnsResolver()
    # Should not raise.
    resolver.check_host(public_ip)


def test_safe_dns_resolver_rejects_dns_that_resolves_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public-looking hostname that resolves to a private IP MUST be rejected.

    DNS-rebinding / TOCTOU defense. The URL parser cannot see what
    hostname will ultimately resolve to; SafeDnsResolver is the
    structural last-line defense at resolve time.
    """
    resolver = SafeDnsResolver()

    def fake_getaddrinfo(host, port, *args, **kwargs):
        # Simulate DNS returning AWS metadata endpoint for a public name.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(InvalidEndpoint) as exc_info:
        resolver.check_host("metadata.example.com")
    # Exact reason match — metadata IPs get their own forensic bucket.
    assert exc_info.value.reason == "metadata_service"


def test_safe_dns_resolver_rejects_dns_that_resolves_to_rfc1918(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFC 1918 range rejected via DNS resolution path."""
    resolver = SafeDnsResolver()

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(InvalidEndpoint) as exc_info:
        resolver.check_host("intranet.example.com")
    assert exc_info.value.reason == "private_ipv4"


def test_safe_dns_resolver_kind_label_stable() -> None:
    """Observability label MUST be stable across SDKs ('safe_dns')."""
    assert SafeDnsResolver().kind() == "safe_dns"


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "provider.example"])
@pytest.mark.parametrize("addr", ["127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1"])
def test_loopback_carveout_requires_localhost_label(monkeypatch, host, addr):
    import ipaddress

    from kaizen.llm.url_safety import check_url

    family = socket.AF_INET6 if ":" in addr else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(family, socket.SOCK_STREAM, 6, "", (addr, 80))],
    )
    # Exercise the older stdlib behavior for IPv4-mapped loopback addresses.
    if addr.startswith("::ffff:"):
        monkeypatch.setattr(
            ipaddress.IPv6Address, "is_loopback", property(lambda ip: False)
        )
    if host.lower() == "localhost":
        check_url(f"https://{host}/")
        SafeDnsResolver().check_host(host)
    else:
        for check in (
            lambda: check_url(f"https://{host}/"),
            lambda: SafeDnsResolver().check_host(host),
        ):
            with pytest.raises(InvalidEndpoint) as exc:
                check()
            assert exc.value.reason == (
                "ipv4_mapped" if "::ffff:" in addr else "loopback"
            )


@pytest.mark.parametrize(
    "addr,reason",
    [
        ("10.0.0.1", "private_ipv4"),
        ("169.254.169.254", "metadata_service"),
        ("fd00:ec2::254", "metadata_service"),
        ("::ffff:169.254.169.254", "metadata_service"),
        ("64:ff9b::127.0.0.1", "ipv4_mapped"),
    ],
)
def test_localhost_dns_poison_still_rejects_every_private_answer(
    monkeypatch, addr, reason
):
    from kaizen.llm.url_safety import check_url

    family = socket.AF_INET6 if ":" in addr else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
            (family, socket.SOCK_STREAM, 6, "", (addr, 80)),
        ],
    )
    for check in (
        lambda: check_url("http://localhost:11434/"),
        lambda: SafeDnsResolver().check_host("localhost"),
    ):
        with pytest.raises(InvalidEndpoint) as exc:
            check()
        assert exc.value.reason == reason
