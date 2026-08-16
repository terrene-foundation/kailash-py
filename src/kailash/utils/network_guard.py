# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared SSRF network guard -- private / loopback / link-local / metadata.

This module is the ONE implementation of "is this outbound destination safe to
reach", used by every core surface that resolves a caller- or
deployment-supplied URL.

Provenance and the no-drift contract
------------------------------------

The implementation was **lifted from** ``nexus.http_client``, which the #2091
analysis correctly named as the reference: the SSRF posture, the encoded-IP
bypass detection, the IPv4-in-IPv6 translation ranges and the metadata sets
were all worked out there first, with the reasoning recorded inline.

It was lifted rather than COPIED, and the direction matters.
``kailash-nexus`` depends on ``kailash``, never the reverse, so the shared
piece has to live in core for both to use it. ``nexus.http_client`` now
IMPORTS this module and keeps only its own error type and client wiring --
there is no second copy of the logic to drift from. Writing a parallel guard
in core would have been the obvious move and is exactly what
``zero-tolerance.md`` Rule 4 forbids: two implementations of one security
control diverge, and the divergence is discovered by an attacker.

Two knobs exist because two callers need genuinely different postures:

* ``error_factory`` -- nexus raises its own ``InvalidEndpointError`` (a
  subclass of its ``HttpClientError``) so ``except HttpClientError`` in nexus
  keeps working. Core raises :class:`BlockedDestinationError`. The DECISION
  logic is identical; only the exception type differs.
* ``allow_private`` -- nexus's outbound client talks to the public internet,
  so RFC1918 is a red flag. Core's reverse proxy is *usually pointed at an
  internal service on purpose*. Blocking RFC1918 by default there would break
  the primary legitimate use, so the proxy permits it and blocks the subset
  with no legitimate proxy use at all: link-local, IMDS, and the cloud
  metadata hostnames.

What ``allow_private`` does NOT relax
-------------------------------------

Cloud metadata addresses and link-local (169.254.0.0/16, fe80::/10) are
**always** refused, on every posture. ``allow_private=True`` is not a way to
reach 169.254.169.254 -- it widens RFC1918 and loopback only. The single
documented way past the metadata block is the caller passing
``allow_metadata=True``, which the proxy surfaces expose as a loudly-logged
registration argument rather than a silent default.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
from typing import Callable, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_BLOCKED_NETWORKS",
    "DEFAULT_LOOPBACK_HOSTS",
    "IPV4_TRANSLATED_NETWORK",
    "NAT64_WELLKNOWN_NETWORK",
    "METADATA_HOSTNAMES",
    "METADATA_IPS",
    "REASON_ALLOWLIST",
    "BlockedDestinationError",
    "check_url",
    "detect_encoded_ip_bypass",
    "IPV4_TRANSLATED_NETWORK",
    "NAT64_WELLKNOWN_NETWORK",
    "embedded_ipv4",
    "is_private_ipv4",
    "is_private_ipv6",
    "ip_reason",
    "iter_resolved_ips",
    "metadata_candidates",
    "url_fingerprint",
]


#: Rejection reasons. A fixed allowlist so log aggregation can bucket
#: rejections without a user-supplied string ever reaching the log stream.
REASON_ALLOWLIST: frozenset = frozenset(
    {
        "scheme",
        "private_ipv4",
        "private_ipv6",
        "loopback",
        "link_local",
        "metadata_service",
        "metadata_host",
        "malformed_url",
        "resolution_failed",
        "ipv4_mapped",
        "encoded_ip_bypass",
        "host_not_allowlisted",
    }
)


class BlockedDestinationError(ValueError):
    """A URL failed the SSRF destination check.

    ``reason`` is drawn from :data:`REASON_ALLOWLIST`. The URL itself is
    stored only as a SHA-256 fingerprint so log pipelines never echo a
    user-supplied URL verbatim.

    Subclasses ``ValueError`` because the core proxy surfaces raise it from
    ``proxy_workflow()`` at REGISTRATION time, where every other
    misconfiguration already surfaces as ``ValueError``.
    """

    def __init__(self, reason: str, raw_url: Optional[str] = None) -> None:
        if reason not in REASON_ALLOWLIST:
            reason = "malformed_url"
        self.reason = reason
        self.url_fingerprint = url_fingerprint(raw_url) if raw_url else None
        if self.url_fingerprint is not None:
            super().__init__(
                f"blocked destination: reason={reason} "
                f"url_fingerprint={self.url_fingerprint}"
            )
        else:
            super().__init__(f"blocked destination: reason={reason}")


def url_fingerprint(raw: Optional[str]) -> str:
    """SHA-256 prefix of the raw URL. Matches the cross-SDK 8-char contract."""
    if not raw:
        return "none"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Address classification
# ---------------------------------------------------------------------------

# IPv6 embedded-IPv4 ranges -- an attacker can wrap a private IPv4 in one of
# these forms to bypass a guard that only checks ``is_private`` on the IPv6
# wrapper. Reject both ranges unconditionally -- no legitimate external
# service lives inside a translation-prefix range.
IPV4_TRANSLATED_NETWORK = ipaddress.IPv6Network("::ffff:0:0:0/96")  # RFC 2765 SIIT
NAT64_WELLKNOWN_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")  # RFC 6052

#: Back-compat aliases for the private spellings used before these ranges
#: became part of the shared surface; existing internal references keep
#: resolving through them.
_IPV4_TRANSLATED_NETWORK = IPV4_TRANSLATED_NETWORK
_NAT64_WELLKNOWN_NETWORK = NAT64_WELLKNOWN_NETWORK

#: Cloud metadata IPs -- the most common SSRF exfiltration targets on
#: AWS / GCP / Azure. Blocked on EVERY posture, including ``allow_private``.
METADATA_IPS: frozenset = frozenset(
    {
        "169.254.169.254",
        "fd00:ec2::254",
    }
)

#: The convenience hostnames cloud providers ship to the guest OS. Blocked by
#: NAME as well as by resolved address, so a registration naming one is
#: refused even when DNS is unavailable to resolve it.
METADATA_HOSTNAMES: frozenset = frozenset(
    {
        "metadata.google.internal",
        "metadata.azure.com",
        "metadata.aws.internal",
    }
)

#: Baseline blocked networks. Applied on top of the per-IP private-range
#: check so extra IPv4 + IPv6 CIDRs are rejected even when a libc helper
#: somehow resolves them to look "public". RFC1918 + loopback + link-local +
#: IMDS + CGNAT + ULA + link-local-v6.
#: Host labels the ``allow_loopback`` carve-out applies to by default.
#: Includes the literal loopback IPs, so ``allow_loopback=True`` permits both
#: ``localhost`` and ``127.0.0.1``. Callers needing the LABEL-only posture
#: pass ``loopback_hosts={"localhost"}`` -- see ``check_url``.
DEFAULT_LOOPBACK_HOSTS: frozenset = frozenset({"localhost", "127.0.0.1", "::1"})

DEFAULT_BLOCKED_NETWORKS: tuple[ipaddress._BaseNetwork, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + IMDS
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT -- commonly internal
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA
    ipaddress.ip_network("fe80::/10"),  # link-local v6
)


def is_private_ipv4(ip: ipaddress.IPv4Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_private_ipv6(ip: ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    if ip.ipv4_mapped is not None:
        return is_private_ipv4(ip.ipv4_mapped)
    if ip in _IPV4_TRANSLATED_NETWORK or ip in _NAT64_WELLKNOWN_NETWORK:
        return True
    return False


def embedded_ipv4(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> Optional[ipaddress.IPv4Address]:
    """Return the IPv4 address an IPv6 wrapper embeds, or ``None``.

    Covers the three forms that carry an IPv4 in their low 32 bits:

    * ``::ffff:a.b.c.d`` -- the strict IPv4-mapped form ``ipaddress`` models
      directly via ``.ipv4_mapped``;
    * ``::ffff:0:a.b.c.d`` -- RFC 2765 SIIT IPv4-translated, which
      ``.ipv4_mapped`` does NOT recognise;
    * ``64:ff9b::a.b.c.d`` -- the RFC 6052 NAT64 well-known prefix.

    The last two are why this helper exists: an attacker wrapping
    169.254.169.254 in either prefix produces an address whose STRING form
    matches no metadata entry and whose ``.is_link_local`` is False, so a
    guard testing only the wrapper waves it through.
    """
    if not isinstance(ip, ipaddress.IPv6Address):
        return None
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in IPV4_TRANSLATED_NETWORK or ip in NAT64_WELLKNOWN_NETWORK:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def metadata_candidates(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> "list[ipaddress.IPv4Address | ipaddress.IPv6Address]":
    """The address plus any IPv4 it embeds -- both must clear the metadata gate.

    PUBLIC because the metadata gate has more than one enforcement surface.
    ``check_url`` below is the parse-time one; ``kaizen.llm.http_client``'s
    ``SafeDnsResolver.check_host`` is the connect-time one, and it MUST reach
    the same verdict AND the same reason bucket. Sharing this function is how
    that is guaranteed rather than hoped for: a wrapper-aware metadata check
    added here lands at every surface at once (``security.md`` §
    Enforcement-Surface Parity).
    """
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ip]
    inner = embedded_ipv4(ip)
    if inner is not None:
        candidates.append(inner)
    return candidates


def ip_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Map an offending IP to an allowlisted rejection reason.

    PUBLIC for the same reason as :func:`metadata_candidates`: the reason
    BUCKET is part of the security contract, not a private detail. Two
    enforcement surfaces that agree on the verdict but disagree on the bucket
    produce dashboards that under-count the category they were split out to
    surface. ``kaizen.llm.http_client.SafeDnsResolver`` shares this function
    so the connect-time gate and the parse-time gate cannot drift.
    """
    ip_str = str(ip)
    if ip_str in METADATA_IPS:
        return "metadata_service"
    if isinstance(ip, ipaddress.IPv4Address):
        if ip.is_loopback:
            return "loopback"
        if ip.is_link_local:
            return "link_local"
        return "private_ipv4"
    # IPv6
    if ip.ipv4_mapped is not None:
        return "ipv4_mapped"
    if ip in _IPV4_TRANSLATED_NETWORK or ip in _NAT64_WELLKNOWN_NETWORK:
        return "ipv4_mapped"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    return "private_ipv6"


def _try_parse_ip(
    candidate: str,
) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return ipaddress.ip_address(candidate)
    except (ValueError, TypeError):
        return None


def _try_inet_aton_shortform(candidate: str) -> Optional[ipaddress.IPv4Address]:
    """Detect ``socket.inet_aton`` short-form IPv4 (``127.1`` -> 127.0.0.1).

    ``ipaddress.ip_address`` rejects these, but libc resolves them, and a
    guard that only checks the strict form is bypassable when the HTTP stack
    forwards to the libc resolver.
    """
    if not candidate or not isinstance(candidate, str):
        return None
    if ":" in candidate:
        return None
    if _try_parse_ip(candidate) is not None:
        return None
    try:
        packed = socket.inet_aton(candidate)
    except (OSError, ValueError, TypeError):
        return None
    return ipaddress.IPv4Address(packed)


def detect_encoded_ip_bypass(host: str) -> bool:
    """Reject decimal / octal / hex IPv4 encodings.

    ``socket.gethostbyname("2130706433")`` returns ``127.0.0.1`` on many libc
    implementations; the standard ``ipaddress`` parser rejects these, so the
    guard needs its own detection.
    """
    if host.isdigit():
        return True
    for part in host.split("."):
        if part.startswith("0x") or part.startswith("0X"):
            return True
        if len(part) > 1 and part.startswith("0") and part[1:].isdigit():
            return True
    return False


def iter_resolved_ips(
    host: str,
) -> "list[ipaddress.IPv4Address | ipaddress.IPv6Address]":
    """Every IP ``socket.getaddrinfo`` associates with ``host``.

    Returns an empty list on resolution failure so the caller can decide
    whether that is fatal.
    """
    results: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return results
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        parsed = _try_parse_ip(ip_str)
        if parsed is not None:
            results.append(parsed)
    return results


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def check_url(
    url: str,
    *,
    blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]] = None,
    host_allowlist: Optional[Sequence[str]] = None,
    allow_loopback: bool = False,
    resolve_dns: bool = True,
    allow_private: bool = False,
    allow_metadata: bool = False,
    loopback_hosts: Optional[Sequence[str]] = None,
    error_factory: Callable[..., Exception] = BlockedDestinationError,
) -> None:
    """Validate ``url`` as an SSRF-safe destination.

    Raises ``error_factory(reason, raw_url=url)`` on any rejection.

    Ordering -- per issue #473 non-negotiable 1: the private-IP / metadata
    check runs BEFORE the host allowlist check. An allowlisted private IP is
    still rejected. The allowlist ONLY narrows the already-safe set of public
    hosts; it MUST NOT be a back-door past the SSRF guard.

    Args:
        url: The destination to validate.
        blocked_networks: Extra CIDRs refused on top of the always-blocked
            ranges, so a caller adding a corporate block cannot have it
            bypassed by forgetting to mix in the defaults.
        host_allowlist: When set, narrows the already-safe public set.
        allow_loopback: Narrowly permits 127.0.0.1 / localhost / ::1 -- for
            tests against a local stub server. Every other private range
            stays blocked.
        resolve_dns: Resolve the host and check every resolved address. When
            False only the literal-IP and hostname checks run.
        allow_private: Permit RFC1918 / loopback / ULA destinations. For the
            core reverse proxy, whose whole purpose is often an internal
            backend. Does NOT permit metadata or link-local -- see
            ``allow_metadata``.
        allow_metadata: Permit cloud-metadata and link-local destinations.
            The ONLY way past that block, deliberately separate from
            ``allow_private`` so widening RFC1918 never silently widens IMDS.
        loopback_hosts: Host labels the ``allow_loopback`` carve-out applies
            to. Defaults to ``{"localhost", "127.0.0.1", "::1"}``.

            Narrowing this to ``{"localhost"}`` makes the carve-out apply to
            the LABEL only, so a literal ``127.0.0.1`` / ``::1`` URL is still
            refused while ``http://localhost:11434`` is permitted. That
            asymmetry is not hypothetical: ``kaizen.llm.url_safety`` relies on
            it, and ``kaizen.llm.deployment_resolver`` documents choosing the
            ``localhost`` hostname over a literal loopback IP for its Ollama /
            Docker-Model-Runner defaults precisely because a literal-IP
            default would raise before any request was built (#2091 follow-up).
            Parameterised rather than hard-coded so consolidating that guard
            neither widens nor narrows what it accepts.
        error_factory: Exception constructor, called as
            ``error_factory(reason, raw_url=url)``. Lets ``nexus.http_client``
            keep raising its own ``InvalidEndpointError`` from this one
            implementation.
    """
    if not isinstance(url, str) or not url:
        raise error_factory("malformed_url", raw_url=None)

    try:
        parsed = urlparse(url)
    except Exception:
        raise error_factory("malformed_url", raw_url=url)

    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname or ""

    # ---- Scheme check -----------------------------------------------------
    # http / https only. Unknown schemes (file://, gopher://, ftp://) are
    # BLOCKED before DNS lookup -- they are the classic SSRF bypass surface.
    # Run this BEFORE the empty-host check because ``file:///path`` parses
    # with an empty host, and the rejection should surface as "scheme" so
    # forensic aggregation can separate file:// attempts from merely
    # malformed URLs.
    if scheme not in ("http", "https"):
        raise error_factory("scheme", raw_url=url)

    if not host:
        raise error_factory("malformed_url", raw_url=url)

    host_lc = host.lower()

    # ---- Metadata hostname check ------------------------------------------
    # By NAME, before any resolution, so this fires even where DNS is
    # unavailable -- and it is not relaxed by allow_private.
    if host_lc in METADATA_HOSTNAMES and not allow_metadata:
        raise error_factory("metadata_host", raw_url=url)

    # ---- Encoded IP bypass check ------------------------------------------
    parsed_ip = _try_parse_ip(host)
    if parsed_ip is None and detect_encoded_ip_bypass(host):
        raise error_factory("encoded_ip_bypass", raw_url=url)

    # ---- inet_aton short-form check ---------------------------------------
    if parsed_ip is None:
        shortform = _try_inet_aton_shortform(host)
        if shortform is not None:
            # Reject regardless of where it points: no legitimate service is
            # addressed via the inet_aton short-form, and accepting it widens
            # the audit surface for no benefit.
            raise error_factory("encoded_ip_bypass", raw_url=url)

    # ---- Literal IP -------------------------------------------------------
    if parsed_ip is not None:
        _validate_ip(
            parsed_ip,
            url,
            allow_loopback,
            blocked_networks,
            host_lc,
            set(loopback_hosts or DEFAULT_LOOPBACK_HOSTS),
            allow_private=allow_private,
            allow_metadata=allow_metadata,
            error_factory=error_factory,
        )
        # Literal IP, passed checks -- allowlist still applies if set.
        _check_host_allowlist(host_lc, host_allowlist, url, error_factory)
        return

    # ---- Host allowlist (layered AFTER SSRF per issue #473 NN1) -----------
    _check_host_allowlist(host_lc, host_allowlist, url, error_factory)

    # ---- DNS resolution (rebinding defence) -------------------------------
    if not resolve_dns:
        return

    any_resolved = False
    carve_out_hosts = set(loopback_hosts or DEFAULT_LOOPBACK_HOSTS)
    for ip in iter_resolved_ips(host):
        any_resolved = True
        _validate_ip(
            ip,
            url,
            allow_loopback,
            blocked_networks,
            host_lc,
            carve_out_hosts,
            allow_private=allow_private,
            allow_metadata=allow_metadata,
            error_factory=error_factory,
        )

    if not any_resolved and not (allow_loopback and host_lc in carve_out_hosts):
        raise error_factory("resolution_failed", raw_url=url)


def _validate_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    url: str,
    allow_loopback: bool,
    blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]],
    host_lc: str,
    loopback_hosts: Optional[set[str]] = None,
    *,
    allow_private: bool = False,
    allow_metadata: bool = False,
    error_factory: Callable[..., Exception] = BlockedDestinationError,
) -> None:
    """Validate a single IP against the blocklist.

    Central routine for both literal-IP URLs and DNS-resolved IPs.
    """
    loopback_hosts = loopback_hosts or set(DEFAULT_LOOPBACK_HOSTS)
    loopback_carveout = allow_loopback and ip.is_loopback and host_lc in loopback_hosts

    # Metadata and link-local are checked FIRST and are not relaxed by
    # ``allow_private``. Hoisting them above the private-range check is
    # behaviour-preserving for the strict posture -- a link-local address is
    # already caught by ``is_private_ipv4``/``is_private_ipv6`` there, and
    # ``ip_reason`` returns the same "link_local" / "metadata_service"
    # string -- while making them un-widenable by the relaxed one. They are
    # also never loopback, so hoisting above the carve-out changes nothing.
    #
    # The check runs over the address AND any IPv4 it EMBEDS. An IPv6 wrapper
    # is a real bypass, not a theoretical one -- measured on the default proxy
    # posture (allow_private=True) before this loop existed:
    #
    #     http://[64:ff9b::169.254.169.254]/  -> ACCEPTED  <== IMDS REACHABLE
    #     http://[::ffff:0:a9fe:a9fe]/        -> ACCEPTED  <== IMDS REACHABLE
    #
    # The translation-range constants existed and were documented
    # "unconditional", but were only consulted from ``is_private_ipv6``, which
    # runs ONLY under ``if not allow_private:`` -- so on the posture the proxy
    # actually ships they never executed. Matching on ``str(ip)`` alone was
    # the other half: the wrapper's string form is never equal to the bare
    # metadata address, so the equality test could not see through it.
    if not allow_metadata:
        for candidate in metadata_candidates(ip):
            if str(candidate) in METADATA_IPS:
                raise error_factory("metadata_service", raw_url=url)
            if candidate.is_link_local:
                raise error_factory("link_local", raw_url=url)

    if not allow_private:
        if isinstance(ip, ipaddress.IPv4Address) and is_private_ipv4(ip):
            # Narrow allow_loopback carve-out: only 127.0.0.1 under a known
            # loopback hostname label. Every other private range stays
            # blocked so allow_loopback can't be used as a wildcard.
            if not loopback_carveout:
                raise error_factory(ip_reason(ip), raw_url=url)
        if isinstance(ip, ipaddress.IPv6Address) and is_private_ipv6(ip):
            if not loopback_carveout:
                raise error_factory(ip_reason(ip), raw_url=url)

    # Extra blocklist (corporate / internal ranges callers supply).
    # When the loopback carve-out applies, skip this sweep as well --
    # otherwise the default blocklist (which contains 127.0.0.0/8 precisely
    # because loopback is unsafe for production) re-rejects the IP the
    # carve-out just permitted.
    if blocked_networks and not loopback_carveout:
        for net in blocked_networks:
            try:
                if ip in net:
                    raise error_factory(ip_reason(ip), raw_url=url)
            except TypeError:
                # Network family mismatch (v4 vs v6) is normal -- skip.
                continue


def _check_host_allowlist(
    host_lc: str,
    host_allowlist: Optional[Sequence[str]],
    url: str,
    error_factory: Callable[..., Exception] = BlockedDestinationError,
) -> None:
    """Enforce the optional host allowlist.

    Consulted ONLY AFTER the SSRF private-IP check has passed (issue #473
    non-negotiable 1). The allowlist narrows the already-safe public set --
    it is NOT a bypass path.
    """
    if host_allowlist is None:
        return
    normalized = {h.lower() for h in host_allowlist}
    if host_lc not in normalized:
        raise error_factory("host_not_allowlisted", raw_url=url)
