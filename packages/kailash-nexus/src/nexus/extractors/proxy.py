# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trusted-proxy posture for the ``Request`` extractor.

Per ``specs/nexus-fastapi-parity.md`` § "Trusted proxy posture" and
``rules/security.md`` § Input Validation, Nexus does NOT trust
client-controllable proxy headers by default. The full forwarded-header
surface is defended — RFC 7239 ``Forwarded``, ``X-Forwarded-For``,
``X-Real-IP`` — not just the two original ``X-Forwarded-*`` headers.

Defaults (no operator opt-in):

- ``Request.client.host`` is the immediate TCP peer's IP address — never an
  ``X-Forwarded-For`` / ``X-Real-IP`` / ``Forwarded`` derivation.
- ``Request.url.scheme`` is derived from the TLS termination state of the
  immediate connection — never from ``X-Forwarded-Proto`` / ``Forwarded;
  proto=...``.

When deployed behind a trusted reverse proxy the operator opts in via
``Nexus(trusted_proxy_cidrs=["10.0.0.0/8", ...])``. The resolver verifies the
immediate peer is inside one of the declared CIDRs via the canonical
``ipaddress`` set-membership idiom — NOT a substring / prefix match.

This module has no third-party dependency; it is safe to import from any path
that needs the structural CIDR check.
"""

import ipaddress
import logging
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "peer_is_trusted",
    "resolve_client_host",
]


def peer_is_trusted(peer_ip: Optional[str], trusted_proxy_cidrs: Sequence[str]) -> bool:
    """Return True iff ``peer_ip`` falls inside any declared trusted CIDR.

    Uses the canonical ``ipaddress.ip_address(peer) in
    ipaddress.ip_network(cidr)`` set-membership idiom. This is structural
    (``IPv4Network`` / ``IPv6Network`` arithmetic), NOT a ``str.startswith``
    prefix match — ``"10.0.0.1"`` and ``"100.0.0.1"`` are never confused.

    **Directional correctness (mixed IP version).** The ``in`` operator on
    ``IPv4Network`` / ``IPv6Network`` returns ``False`` on a mixed-version
    peer-vs-cidr comparison (e.g. an IPv6 peer against an IPv4 trusted CIDR) —
    it does NOT raise. So a misconfigured or attacker-shaped mixed-version
    request fails closed (peer not trusted) rather than crashing the resolver
    mid-request with a ``TypeError`` that would surface internals in a 5xx.

    Empty ``trusted_proxy_cidrs`` (the default) means no peer is ever trusted —
    the safest posture for direct-internet-facing deployments.

    Args:
        peer_ip: Immediate TCP peer IP address (``request.client.host``), or
            ``None`` when the transport could not determine it.
        trusted_proxy_cidrs: Operator-declared CIDR strings.

    Returns:
        True if ``peer_ip`` is a valid address inside at least one declared
        CIDR; False otherwise (including ``None`` peer, unparseable peer,
        unparseable CIDR, empty CIDR list, or mixed-version mismatch).
    """
    if not peer_ip or not trusted_proxy_cidrs:
        return False

    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        # An unparseable peer address is never trusted (fail closed).
        return False

    for cidr in trusted_proxy_cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            # A malformed CIDR is skipped (fail closed for that entry) — it
            # cannot match any peer, and silently skipping it never widens
            # trust beyond the well-formed entries.
            logger.warning(
                "trusted_proxy_cidrs entry %r is not a valid CIDR; skipping",
                cidr,
            )
            continue
        # `peer in network` is False on mixed IP version — never raises.
        if peer in network:
            return True
    return False


def _parse_forwarded_for(forwarded_for: str) -> Optional[str]:
    """Extract the right-most untrusted entry from an X-Forwarded-For value.

    ``X-Forwarded-For`` is a comma-separated chain ``client, proxy1, proxy2``.
    The right-most entry is the most recent (closest-to-us) hop. Per the
    spec's "take the right-most untrusted entry" rule, we return the last
    non-empty, comma-split token.
    """
    parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
    if not parts:
        return None
    return parts[-1]


def _parse_rfc7239_forwarded(forwarded: str) -> Optional[str]:
    """Extract the ``for=`` value from the right-most RFC 7239 forwarded hop.

    RFC 7239 ``Forwarded`` is a comma-separated list of hops, each a
    semicolon-separated list of ``key=value`` directives, e.g.
    ``for=192.0.2.60;proto=http, for="[2001:db8::1]"``. The right-most hop is
    the most recent. IPv6 ``for=`` values are bracket-and-quote wrapped.
    """
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    if not hops:
        return None
    rightmost = hops[-1]
    for directive in rightmost.split(";"):
        directive = directive.strip()
        if directive.lower().startswith("for="):
            value = directive[4:].strip().strip('"')
            # IPv6 in RFC 7239 is bracketed: [2001:db8::1] (optionally :port)
            if value.startswith("["):
                end = value.find("]")
                if end != -1:
                    return value[1:end]
            # IPv4 may carry :port — strip it.
            if value.count(":") == 1:
                value = value.split(":", 1)[0]
            return value or None
    return None


def resolve_client_host(
    peer_ip: Optional[str],
    headers: "object",
    trusted_proxy_cidrs: Sequence[str],
) -> Optional[str]:
    """Resolve the originating client host honouring the trusted-proxy posture.

    - If the immediate ``peer_ip`` is NOT in ``trusted_proxy_cidrs`` (the
      default for the empty list), forwarded headers are IGNORED and
      ``peer_ip`` is returned as the originating identity.
    - If the peer IS trusted, headers are consulted in RFC 7239 §6.3 priority
      order: ``Forwarded`` → ``X-Forwarded-For`` (rightmost untrusted) →
      ``X-Real-IP``. The first that yields a value wins.

    ``headers`` is any object exposing a case-insensitive ``.get(name)`` (a
    Starlette ``Headers`` or the Nexus :class:`~nexus.extractors.Headers`).
    """
    if not peer_is_trusted(peer_ip, trusted_proxy_cidrs):
        return peer_ip

    get = getattr(headers, "get", None)
    if get is None:
        return peer_ip

    forwarded = get("forwarded")
    if forwarded:
        host = _parse_rfc7239_forwarded(forwarded)
        if host:
            return host

    xff = get("x-forwarded-for")
    if xff:
        host = _parse_forwarded_for(xff)
        if host:
            return host

    real_ip = get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return peer_ip
