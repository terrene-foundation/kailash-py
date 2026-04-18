# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SSRF guard for LLM endpoint base URLs.

Every `LlmDeployment` / `LlmClient.from_deployment(...)` entry point routes
its `base_url` through `check_url()`. The guard rejects:

* Non-`https` schemes in production (http allowed only for localhost /
  127.0.0.1, enabling local tests against a stubbed endpoint);
* Private IPv4 ranges (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16);
* Private, loopback, and link-local IPv6 (::1, fe80::/10, fc00::/7) plus
  IPv4-mapped addresses (::ffff:127.0.0.1);
* Cloud metadata IPs and hostnames (169.254.169.254, fd00:ec2::254,
  metadata.google.internal, metadata.azure.com, metadata.aws.internal);
* Decimal / octal / hex encoded bypass attempts (2130706433, 0177.0.0.1);
* Hostnames whose DNS resolution returns any of the above private addresses
  (defeats DNS-rebinding where the attacker hosts a public domain that
  resolves to 127.0.0.1).

On reject, raises `EndpointError.InvalidEndpoint(reason="…", raw_url=…)`.
The `reason` comes from a closed allowlist in `errors.py`; the raw URL is
hashed and stored only as a fingerprint so log aggregators don't echo the
user-supplied URL verbatim.

Cross-SDK parity: semantic match with kailash-rs SafeDnsResolver. Python
uses `socket.getaddrinfo` for resolution, Rust uses hyper's resolver.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
from typing import Iterable
from urllib.parse import urlparse

from kaizen.llm.errors import InvalidEndpoint

logger = logging.getLogger(__name__)


def _url_fingerprint(raw: str | None) -> str:
    """Produce a short, non-reversible tag for a URL.

    Must match the shape used by `errors._fingerprint` so log entries can be
    correlated with the fingerprint stored on the raised `InvalidEndpoint`.
    """
    if not raw:
        return "none"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:8]


def _reject(reason: str, url: str | None) -> None:
    """Emit a structured WARN log, then raise `InvalidEndpoint`.

    The fingerprint attached here matches the one stored on the exception
    (`InvalidEndpoint._fingerprint`), so audit trails can join the log line
    with the exception instance via the shared tag. WARN is the correct level
    because the guard SUCCEEDED at blocking an attack — operators should see
    that in routine dashboards (rules/observability.md MUST Rule 3).
    """
    logger.warning(
        "url_safety.rejected",
        extra={"reason": reason, "url_fingerprint": _url_fingerprint(url)},
    )
    raise InvalidEndpoint(reason, raw_url=url)


# ---------------------------------------------------------------------------
# Known metadata hosts (string compare, case-insensitive)
# ---------------------------------------------------------------------------

_METADATA_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.azure.com",
        "metadata.aws.internal",
    }
)

# Cloud metadata IPs as strings for quick compare AND parsed for range checks.
_METADATA_IPS = frozenset(
    {
        "169.254.169.254",
        "fd00:ec2::254",
    }
)

# These hostnames are permitted with http:// in Session 1 so local tests can
# run against a stub endpoint. Any other host forces https://.
_HTTP_LOCALHOST_ALLOWLIST = frozenset({"localhost", "127.0.0.1", "::1"})


# IPv6 embedded-IPv4 ranges — an attacker who controls a v4 target (loopback,
# private, metadata) can wrap it in one of these IPv6 forms to bypass a guard
# that only checks IPv6 `is_private` / `ipv4_mapped`. See round-1 redteam H1.
_IPV4_TRANSLATED_NETWORK = ipaddress.IPv6Network("::ffff:0:0:0/96")  # RFC 2765 SIIT
_NAT64_WELLKNOWN_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")  # RFC 6052


# ---------------------------------------------------------------------------
# Private / loopback / link-local range tests
# ---------------------------------------------------------------------------


def _is_private_ipv4(ip: ipaddress.IPv4Address) -> bool:
    """Private / loopback / link-local IPv4."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_private_ipv6(ip: ipaddress.IPv6Address) -> bool:
    """Private / loopback / link-local IPv6, including IPv4-mapped.

    Also rejects RFC 2765 IPv4-translated (`::ffff:0:a.b.c.d`) and RFC 6052
    NAT64 well-known (`64:ff9b::a.b.c.d`) forms unconditionally — no
    legitimate LLM endpoint lives inside these translation-prefix ranges, and
    a permissive check lets an attacker wrap a private / loopback / metadata
    IPv4 and bypass `ip.ipv4_mapped` (which only matches the strict
    `::ffff:a.b.c.d/96` form). Round-1 redteam H1.
    """
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    # Strict IPv4-mapped addresses: ::ffff:127.0.0.1 (recognised by stdlib).
    if ip.ipv4_mapped is not None:
        return _is_private_ipv4(ip.ipv4_mapped)
    # RFC 2765 IPv4-translated + RFC 6052 NAT64 well-known: the embedded IPv4
    # is in the low 32 bits. We treat membership in either range as private
    # regardless of the embedded value — these prefixes do not appear on any
    # reachable LLM endpoint.
    if ip in _IPV4_TRANSLATED_NETWORK or ip in _NAT64_WELLKNOWN_NETWORK:
        return True
    return False


def _ip_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Map an offending IP to an allowlisted `InvalidEndpoint.reason` code."""
    ip_str = str(ip)
    if ip_str in _METADATA_IPS:
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
    # RFC 2765 / RFC 6052 embedded-IPv4 ranges: reuse the `ipv4_mapped`
    # reason code so downstream audit queries aggregate both the strict and
    # the translated forms under one bucket.
    if ip in _IPV4_TRANSLATED_NETWORK or ip in _NAT64_WELLKNOWN_NETWORK:
        return "ipv4_mapped"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    return "private_ipv6"


def _try_parse_ip(
    candidate: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Try the normal ipaddress parser. Does NOT accept encoded bypasses."""
    try:
        return ipaddress.ip_address(candidate)
    except (ValueError, TypeError):
        return None


def _try_inet_aton_shortform(candidate: str) -> ipaddress.IPv4Address | None:
    """Resolve a string via `socket.inet_aton` if it's an IPv4 short form.

    inet_aton accepts "127.1", "127.0.1", and "127" (single 32-bit int) and
    maps them to 127.0.0.1 / 0.0.0.127. The standard `ipaddress.ip_address`
    parser rejects these, so a guard that only checks the strict form is
    bypassable when the HTTP library / socket layer forwards to libc.

    Only returns a result for candidates that would NOT otherwise parse as a
    standard dotted-quad IP, so legitimate `a.b.c.d` strings are left to the
    regular parser. Round-1 redteam M5.
    """
    if not candidate or not isinstance(candidate, str):
        return None
    if ":" in candidate:  # likely IPv6 — inet_aton is v4-only
        return None
    # Avoid double-handling values `ipaddress` already accepts.
    if _try_parse_ip(candidate) is not None:
        return None
    try:
        packed = socket.inet_aton(candidate)
    except (OSError, ValueError, TypeError):
        return None
    return ipaddress.IPv4Address(packed)


def _detect_encoded_ip_bypass(host: str) -> bool:
    """Reject decimal / octal / hex encoded IPs that would resolve to IPv4.

    `socket.gethostbyname("2130706433")` returns "127.0.0.1" on many libc
    implementations because the BSD inet_aton syntax accepts a single 32-bit
    integer. The standard `ipaddress.ip_address("2130706433")` rejects this,
    which is why the guard needs its own detection.

    This function returns True if `host` is a string that would be
    interpreted as an IP by the libc resolver but is NOT a standard
    dotted-quad. It deliberately errs on the side of rejection.
    """
    # Pure digit string (decimal encoded 32-bit int) — rejected.
    if host.isdigit():
        return True
    # Mixed-base formats: starts with 0 (octal) or 0x (hex), followed by
    # dots. inet_aton accepts these. The regular ip_address parser does not.
    parts = host.split(".")
    for part in parts:
        # Remove an obvious negative sign or sign character; if anything
        # non-numeric-non-hex is left, not an encoded IP.
        if part.startswith("0x") or part.startswith("0X"):
            # Hex-prefixed — suspicious.
            return True
        if len(part) > 1 and part.startswith("0") and part[1:].isdigit():
            # Leading zero + digits = octal in inet_aton.
            return True
    return False


def _iter_resolved_ips(
    host: str,
) -> Iterable[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Yield every IP that `socket.getaddrinfo` associates with `host`.

    Returns an empty iterator if resolution fails; the caller treats that as
    `resolution_failed`. AI_CANONNAME is unused: we only care about the A /
    AAAA records.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return
    seen: set[str] = set()
    for info in infos:
        # info = (family, type, proto, canonname, sockaddr)
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        parsed = _try_parse_ip(ip_str)
        if parsed is not None:
            yield parsed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_url(url: str, *, resolve_dns: bool = True) -> None:
    """Validate `url` as an SSRF-safe LLM endpoint.

    Raises `InvalidEndpoint` on any rejection; `reason` comes from the fixed
    allowlist in `errors.InvalidEndpoint._REASON_ALLOWLIST`. The raw URL is
    hashed and attached only as a fingerprint on the exception, never echoed.

    `resolve_dns=False` is a test-only knob — unit tests that supply a
    synthetic hostname and want to assert the scheme/encoded-IP checks run
    without bringing up a DNS resolver.
    """
    if not isinstance(url, str) or not url:
        _reject("malformed_url", url if isinstance(url, str) else None)

    try:
        parsed = urlparse(url)
    except Exception:
        _reject("malformed_url", url)
        return  # unreachable; _reject always raises

    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname or ""

    if not host:
        _reject("malformed_url", url)

    # ---- Scheme check -------------------------------------------------
    if scheme not in ("http", "https"):
        _reject("scheme", url)

    host_lc = host.lower()
    if scheme == "http" and host_lc not in _HTTP_LOCALHOST_ALLOWLIST:
        _reject("scheme", url)

    # ---- Metadata hostname check ------------------------------------
    if host_lc in _METADATA_HOSTNAMES:
        _reject("metadata_host", url)

    # ---- Encoded IP bypass check ------------------------------------
    parsed_ip = _try_parse_ip(host)
    if parsed_ip is None and _detect_encoded_ip_bypass(host):
        _reject("encoded_ip_bypass", url)

    # ---- inet_aton short-form check ---------------------------------
    # `127.1` / `127.0.1` / `127` pass the dotted-split check above (no
    # part starts with `0`, no part is pure hex) but libc resolves them to
    # loopback. Round-1 redteam M5.
    if parsed_ip is None:
        shortform = _try_inet_aton_shortform(host)
        if shortform is not None:
            if _is_private_ipv4(shortform) or str(shortform) in _METADATA_IPS:
                _reject("encoded_ip_bypass", url)
            # Short-form resolving to a public IPv4: reject anyway — no
            # legitimate LLM endpoint is addressed via the inet_aton
            # short-form syntax, and allowing it widens the audit surface.
            _reject("encoded_ip_bypass", url)

    # ---- Literal IP check -------------------------------------------
    if parsed_ip is not None:
        if isinstance(parsed_ip, ipaddress.IPv4Address) and _is_private_ipv4(parsed_ip):
            _reject(_ip_reason(parsed_ip), url)
        if isinstance(parsed_ip, ipaddress.IPv6Address) and _is_private_ipv6(parsed_ip):
            _reject(_ip_reason(parsed_ip), url)
        if str(parsed_ip) in _METADATA_IPS:
            _reject("metadata_service", url)
        # Literal IP + passed range checks: accept.
        return

    # ---- Hostname resolution (DNS rebinding defense) -----------------
    if not resolve_dns:
        return

    # Special case: host is an allowlisted localhost label. Still resolve
    # defensively, but treat failure as benign — getaddrinfo for "localhost"
    # typically returns 127.0.0.1 which is loopback but the scheme check
    # already permits http for these hosts.
    any_resolved = False
    for ip in _iter_resolved_ips(host):
        any_resolved = True
        if isinstance(ip, ipaddress.IPv4Address) and _is_private_ipv4(ip):
            if host_lc in _HTTP_LOCALHOST_ALLOWLIST:
                # localhost legitimately resolves to 127.0.0.1; skip.
                continue
            _reject(_ip_reason(ip), url)
        if isinstance(ip, ipaddress.IPv6Address) and _is_private_ipv6(ip):
            if host_lc in _HTTP_LOCALHOST_ALLOWLIST:
                continue
            _reject(_ip_reason(ip), url)
        if str(ip) in _METADATA_IPS:
            _reject("metadata_service", url)

    if not any_resolved and host_lc not in _HTTP_LOCALHOST_ALLOWLIST:
        # Resolution failed entirely — treat as InvalidEndpoint with
        # `resolution_failed`. Caller can retry with resolve_dns=False if the
        # host is intentionally unreachable in the test environment.
        _reject("resolution_failed", url)


__all__ = ["check_url"]
