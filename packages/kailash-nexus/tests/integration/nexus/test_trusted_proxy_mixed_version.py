# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 tests for the trusted-proxy posture (spec §277-295).

The structural CIDR check (``nexus.extractors.proxy``) is the load-bearing
defense: it uses ``ipaddress`` set-membership (never substring), and on a
mixed IP-version comparison (IPv6 peer vs IPv4-only trusted CIDR) it returns
False (peer-not-trusted) WITHOUT raising — eliminating the mixed-version DoS
surface a ``supernet_of`` approach would create (NEW-HIGH-5).

These are exercised directly against the proxy helper AND through a real
Nexus instance configured with ``trusted_proxy_cidrs``.
"""

import socket

import pytest

from nexus import Nexus
from nexus.extractors.proxy import peer_is_trusted, resolve_client_host


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------
# Mixed-version safety — the headline NEW-HIGH-5 contract
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_ipv6_peer_against_ipv4_cidr_not_trusted_no_raise():
    """IPv6 peer vs IPv4-only trusted CIDR: not trusted, never raises."""
    # The canonical NEW-HIGH-5 case: an IPv6 peer (2001:db8::1) against an
    # IPv4-only trusted CIDR (10.0.0.0/8). MUST return False, MUST NOT raise.
    result = peer_is_trusted("2001:db8::1", ["10.0.0.0/8"])
    assert result is False


@pytest.mark.integration
def test_ipv4_peer_against_ipv6_cidr_not_trusted_no_raise():
    """The symmetric case: IPv4 peer vs IPv6-only trusted CIDR."""
    result = peer_is_trusted("10.1.2.3", ["2001:db8::/32"])
    assert result is False


@pytest.mark.integration
def test_forwarded_headers_ignored_for_untrusted_mixed_version_peer():
    """A mixed-version (untrusted) peer's forwarded headers are NOT honoured."""

    class _Headers:
        def get(self, name, default=None):
            return {
                "x-forwarded-for": "203.0.113.9",
                "x-real-ip": "203.0.113.9",
            }.get(name.lower(), default)

    # IPv6 peer, IPv4-only trusted CIDR -> peer NOT trusted -> forwarded
    # headers ignored -> the immediate peer IS the originating identity.
    host = resolve_client_host("2001:db8::1", _Headers(), ["10.0.0.0/8"])
    assert host == "2001:db8::1"


# --------------------------------------------------------------------------
# Structural CIDR membership — never substring / prefix
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_cidr_membership_is_structural_not_substring():
    """10.0.0.1 is in 10.0.0.0/8; 100.0.0.1 is NOT (no substring confusion)."""
    assert peer_is_trusted("10.0.0.1", ["10.0.0.0/8"]) is True
    # A substring/startswith approach would wrongly match "100.0.0.1".
    assert peer_is_trusted("100.0.0.1", ["10.0.0.0/8"]) is False


@pytest.mark.integration
def test_empty_cidrs_never_trusts_any_peer():
    """Default trusted_proxy_cidrs=[] honours no forwarded headers."""
    assert peer_is_trusted("10.0.0.1", []) is False
    assert peer_is_trusted("2001:db8::1", []) is False


@pytest.mark.integration
def test_malformed_cidr_skipped_fails_closed():
    """A malformed CIDR entry is skipped (fails closed for that entry)."""
    # The well-formed entry still matches; the malformed one never widens trust.
    assert peer_is_trusted("10.0.0.1", ["not-a-cidr", "10.0.0.0/8"]) is True
    assert peer_is_trusted("203.0.113.9", ["not-a-cidr"]) is False


@pytest.mark.integration
def test_unparseable_peer_never_trusted():
    """An unparseable peer address is never trusted (fail closed)."""
    assert peer_is_trusted("not-an-ip", ["10.0.0.0/8"]) is False
    assert peer_is_trusted(None, ["10.0.0.0/8"]) is False


# --------------------------------------------------------------------------
# Trusted-peer header priority (RFC 7239 §6.3) — Forwarded > XFF > X-Real-IP
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_trusted_peer_consults_forwarded_first():
    """When the peer is trusted, RFC 7239 Forwarded wins over X-Forwarded-For."""

    class _Headers:
        def get(self, name, default=None):
            return {
                "forwarded": "for=198.51.100.7;proto=https",
                "x-forwarded-for": "203.0.113.9",
                "x-real-ip": "203.0.113.50",
            }.get(name.lower(), default)

    host = resolve_client_host("10.0.0.5", _Headers(), ["10.0.0.0/8"])
    assert host == "198.51.100.7"


@pytest.mark.integration
def test_trusted_peer_xff_rightmost_untrusted_when_no_forwarded():
    """Falls back to X-Forwarded-For rightmost UNTRUSTED entry when no Forwarded."""

    class _Headers:
        def get(self, name, default=None):
            return {
                "x-forwarded-for": "203.0.113.9, 198.51.100.7",
            }.get(name.lower(), default)

    # Neither hop is in 10.0.0.0/8, so the rightmost (198.51.100.7) is the
    # rightmost-untrusted entry.
    host = resolve_client_host("10.0.0.5", _Headers(), ["10.0.0.0/8"])
    assert host == "198.51.100.7"


@pytest.mark.integration
def test_trusted_peer_xff_skips_trusted_hops_returns_real_client():
    """R1 reviewer F1 regression — XFF walk returns the rightmost UNTRUSTED entry.

    Multi-proxy chain ``client, trusted1, trusted2`` with the trusted hops
    inside ``trusted_proxy_cidrs``. A literal-rightmost parse would return
    ``10.0.0.8`` (trusted infra) as the "client" and poison rate-limit /
    audit / geofencing keys; the chain-walk skips the trusted hops and returns
    the real client (203.0.113.9).
    """

    class _Headers:
        def get(self, name, default=None):
            return {
                "x-forwarded-for": "203.0.113.9, 10.0.0.7, 10.0.0.8",
            }.get(name.lower(), default)

    host = resolve_client_host("10.0.0.9", _Headers(), ["10.0.0.0/8"])
    assert host == "203.0.113.9"


@pytest.mark.integration
def test_trusted_peer_rfc7239_skips_trusted_hops_returns_real_client():
    """R1 reviewer F1 regression — RFC 7239 walk returns rightmost UNTRUSTED for=."""

    class _Headers:
        def get(self, name, default=None):
            return {
                "forwarded": "for=203.0.113.9, for=10.0.0.7, for=10.0.0.8",
            }.get(name.lower(), default)

    host = resolve_client_host("10.0.0.9", _Headers(), ["10.0.0.0/8"])
    assert host == "203.0.113.9"


@pytest.mark.integration
def test_trusted_peer_xff_all_hops_trusted_returns_leftmost_origin():
    """R1 reviewer F1 regression — when every hop is trusted, the origin is leftmost."""

    class _Headers:
        def get(self, name, default=None):
            return {
                "x-forwarded-for": "10.0.0.5, 10.0.0.6",
            }.get(name.lower(), default)

    host = resolve_client_host("10.0.0.9", _Headers(), ["10.0.0.0/8"])
    assert host == "10.0.0.5"


# --------------------------------------------------------------------------
# Real Nexus instance wiring — the config kwarg reaches the resolver
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_nexus_trusted_proxy_cidrs_default_empty():
    """Nexus defaults trusted_proxy_cidrs to [] (no forwarded trust)."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)
    assert app._trusted_proxy_cidrs == []


@pytest.mark.integration
def test_nexus_trusted_proxy_cidrs_stored():
    """Operator-supplied trusted_proxy_cidrs is stored on the instance."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_auth=False,
        trusted_proxy_cidrs=["10.0.0.0/8", "192.168.0.0/16"],
    )
    assert app._trusted_proxy_cidrs == ["10.0.0.0/8", "192.168.0.0/16"]
