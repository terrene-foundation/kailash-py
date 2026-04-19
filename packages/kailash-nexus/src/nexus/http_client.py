# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Nexus outbound HttpClient — SSRF-aware typed HTTP client primitive.

Nexus's inbound surface (handlers, routers, middleware) is extensive. Its
outbound surface was absent: downstream applications that needed to call
external services (webhooks, IdPs, agent forwarders, health probes) had to
reach for `httpx` directly, bypassing Nexus's observability, security, and
structured-logging guarantees.

This module provides ``HttpClient`` and ``HttpClientConfig`` — the single
supported construction path for Nexus outbound HTTP traffic.

# SSRF defence

Every outbound URL is validated at two points:

1. ``HttpClient`` routes the URL through ``check_url`` at request-dispatch
   time. That catches literal-IP SSRF, encoded-IP bypass forms, and DNS
   rebinding attempts that resolve to a private / loopback / metadata IP at
   parse time.
2. ``HttpClient`` installs ``SafeDnsTransport`` on the underlying
   ``httpx.AsyncClient``. The transport re-resolves the peer host at connect
   time and rejects the connection before the TCP SYN fires. That closes the
   TOCTOU window where a public hostname resolves to 1.2.3.4 at parse time
   and to 127.0.0.1 at connect time.

Both guards run. Removing either widens the surface.

# Observability

Every request emits three structured log lines
(``nexus.http.request.start`` / ``.ok`` / ``.error``). Each carries a UUID
``request_id`` correlation identifier that is injected as the
``X-Request-ID`` header on the outgoing request, so a downstream service can
trace the call back. The ``Authorization`` header value is NEVER logged;
endpoint host is logged but NOT the full URL (some legacy providers carry
credentials in query strings).

# Cross-SDK parity

Semantic match with ``kailash-rs#399`` HttpClient. Python uses ``httpx`` +
``socket.getaddrinfo``; Rust uses ``reqwest`` + hyper's resolver. Public
API shape is byte-identical: ``get`` / ``post`` / ``put`` / ``delete`` /
``patch`` verb methods, ``request_id`` kwarg for correlation, ``json`` and
``content`` kwargs mirroring httpx / reqwest semantics.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping, Optional, Sequence
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class HttpClientError(Exception):
    """Base class for HttpClient construction / dispatch errors.

    Kept narrow: dispatch-layer ``httpx`` errors are not rewrapped by
    ``HttpClient`` — they propagate to the caller unchanged. The higher-level
    ``ServiceClient`` wrapper translates them into typed subclasses.
    """


class InvalidEndpointError(HttpClientError):
    """The supplied URL failed SSRF validation.

    ``reason`` is a short code from a fixed allowlist (``scheme``,
    ``private_ipv4``, ``metadata_service``, ``malformed_url``, …). The URL
    itself is stored only as a SHA-256 fingerprint so log pipelines never
    echo a user-supplied URL verbatim.
    """

    _REASON_ALLOWLIST = frozenset(
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

    def __init__(self, reason: str, raw_url: Optional[str] = None) -> None:
        if reason not in self._REASON_ALLOWLIST:
            reason = "malformed_url"
        self.reason = reason
        self.url_fingerprint = _url_fingerprint(raw_url) if raw_url else None
        if self.url_fingerprint is not None:
            super().__init__(
                f"invalid endpoint: reason={reason} "
                f"url_fingerprint={self.url_fingerprint}"
            )
        else:
            super().__init__(f"invalid endpoint: reason={reason}")


# ---------------------------------------------------------------------------
# URL fingerprinting (secrets-safe logging)
# ---------------------------------------------------------------------------


def _url_fingerprint(raw: Optional[str]) -> str:
    """SHA-256 prefix of the raw URL. Matches cross-SDK 8-char contract."""
    if not raw:
        return "none"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# SSRF guard — private / loopback / link-local / metadata detection
# ---------------------------------------------------------------------------

# IPv6 embedded-IPv4 ranges — an attacker can wrap a private IPv4 in one of
# these forms to bypass a guard that only checks ``is_private`` on the IPv6
# wrapper. Reject both ranges unconditionally — no legitimate external
# service lives inside a translation-prefix range. Mirrors the kailash-rs
# SafeDnsResolver check and the kaizen.llm.url_safety implementation.
_IPV4_TRANSLATED_NETWORK = ipaddress.IPv6Network("::ffff:0:0:0/96")  # RFC 2765 SIIT
_NAT64_WELLKNOWN_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")  # RFC 6052

# Cloud metadata IPs and hostnames — these are the most common SSRF
# exfiltration targets on AWS / GCP / Azure. We reject both the numeric IP
# and the convenience hostname the cloud provider ships to the guest OS.
_METADATA_IPS = frozenset(
    {
        "169.254.169.254",
        "fd00:ec2::254",
    }
)

_METADATA_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.azure.com",
        "metadata.aws.internal",
    }
)


def _is_private_ipv4(ip: ipaddress.IPv4Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_private_ipv6(ip: ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    if ip.ipv4_mapped is not None:
        return _is_private_ipv4(ip.ipv4_mapped)
    if ip in _IPV4_TRANSLATED_NETWORK or ip in _NAT64_WELLKNOWN_NETWORK:
        return True
    return False


def _ip_reason(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> str:
    """Map an offending IP to an allowlisted ``InvalidEndpointError.reason``."""
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


def _detect_encoded_ip_bypass(host: str) -> bool:
    """Reject decimal / octal / hex IPv4 encodings.

    ``socket.gethostbyname("2130706433")`` returns ``127.0.0.1`` on many
    libc implementations; the standard ``ipaddress`` parser rejects these,
    so the guard needs its own detection.
    """
    if host.isdigit():
        return True
    for part in host.split("."):
        if part.startswith("0x") or part.startswith("0X"):
            return True
        if len(part) > 1 and part.startswith("0") and part[1:].isdigit():
            return True
    return False


def _iter_resolved_ips(
    host: str,
) -> "list[ipaddress.IPv4Address | ipaddress.IPv6Address]":
    """Yield every IP ``socket.getaddrinfo`` associates with ``host``.

    Returns an empty list on resolution failure so the caller can treat
    that as ``resolution_failed``.
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


def check_url(
    url: str,
    *,
    blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]] = None,
    host_allowlist: Optional[Sequence[str]] = None,
    allow_loopback: bool = False,
    resolve_dns: bool = True,
) -> None:
    """Validate ``url`` as an SSRF-safe outbound target.

    Raises ``InvalidEndpointError`` on any rejection. ``reason`` is from a
    fixed allowlist; the raw URL is hashed and stored only as a fingerprint
    on the exception so audit logs never echo the user-supplied URL.

    Ordering — per issue #473 non-negotiable 1: the private-IP / metadata
    check runs BEFORE the host allowlist check. An allowlisted private IP is
    still rejected. The allowlist ONLY narrows the already-safe set of
    public hosts; it MUST NOT be a back-door past the SSRF guard.

    ``allow_loopback=True`` is for tests against a local stub server. It
    narrowly permits 127.0.0.1 / localhost / ::1. Every other private range
    stays blocked.

    ``blocked_networks`` lets callers add additional CIDR blocks on top of
    the always-blocked set (e.g. a corporate internal block the attacker
    shouldn't reach even if it passes the RFC1918 check).
    """
    if not isinstance(url, str) or not url:
        raise InvalidEndpointError("malformed_url", raw_url=None)

    try:
        parsed = urlparse(url)
    except Exception:
        raise InvalidEndpointError("malformed_url", raw_url=url)

    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname or ""

    # ---- Scheme check -----------------------------------------------------
    # http / https only. Unknown schemes (file://, gopher://, ftp://) are
    # BLOCKED before DNS lookup — they are the classic SSRF bypass surface.
    # Run scheme check BEFORE the empty-host check because ``file:///path``
    # parses with empty host; we want the rejection reason to surface as
    # "scheme" so forensic aggregation can separate the file:// attempts
    # from merely malformed URLs.
    if scheme not in ("http", "https"):
        raise InvalidEndpointError("scheme", raw_url=url)

    if not host:
        raise InvalidEndpointError("malformed_url", raw_url=url)

    host_lc = host.lower()

    # ---- Metadata hostname check ------------------------------------------
    if host_lc in _METADATA_HOSTNAMES:
        raise InvalidEndpointError("metadata_host", raw_url=url)

    # ---- Encoded IP bypass check ------------------------------------------
    parsed_ip = _try_parse_ip(host)
    if parsed_ip is None and _detect_encoded_ip_bypass(host):
        raise InvalidEndpointError("encoded_ip_bypass", raw_url=url)

    # ---- inet_aton short-form check ---------------------------------------
    if parsed_ip is None:
        shortform = _try_inet_aton_shortform(host)
        if shortform is not None:
            if _is_private_ipv4(shortform) or str(shortform) in _METADATA_IPS:
                raise InvalidEndpointError("encoded_ip_bypass", raw_url=url)
            # Short-form IPv4 that resolves public: still reject — no
            # legitimate external service is addressed via the inet_aton
            # short-form, and accepting it widens the audit surface.
            raise InvalidEndpointError("encoded_ip_bypass", raw_url=url)

    # ---- Literal IP — private / metadata / extra-blocked ------------------
    if parsed_ip is not None:
        _validate_ip(parsed_ip, url, allow_loopback, blocked_networks, host_lc)
        # Literal IP, passed checks — allowlist still applies if set.
        _check_host_allowlist(host_lc, host_allowlist, url)
        return

    # ---- Host allowlist (layered AFTER SSRF per issue #473 NN1) -----------
    _check_host_allowlist(host_lc, host_allowlist, url)

    # ---- DNS resolution (rebinding defence) -------------------------------
    if not resolve_dns:
        return

    any_resolved = False
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    for ip in _iter_resolved_ips(host):
        any_resolved = True
        _validate_ip(ip, url, allow_loopback, blocked_networks, host_lc, loopback_hosts)

    if not any_resolved and not (allow_loopback and host_lc in loopback_hosts):
        raise InvalidEndpointError("resolution_failed", raw_url=url)


def _validate_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    url: str,
    allow_loopback: bool,
    blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]],
    host_lc: str,
    loopback_hosts: Optional[set[str]] = None,
) -> None:
    """Validate a single IP against the blocklist.

    Central routine used for both literal-IP URLs and DNS-resolved IPs. The
    caller-supplied ``blocked_networks`` list is applied on top of the
    always-blocked ranges so extra corporate / internal CIDRs cannot be
    bypassed by a caller forgetting to mix them in.
    """
    loopback_hosts = loopback_hosts or {"localhost", "127.0.0.1", "::1"}
    loopback_carveout = allow_loopback and ip.is_loopback and host_lc in loopback_hosts

    # Metadata always blocked regardless of allow_loopback.
    if str(ip) in _METADATA_IPS:
        raise InvalidEndpointError("metadata_service", raw_url=url)

    if isinstance(ip, ipaddress.IPv4Address):
        if _is_private_ipv4(ip):
            # Narrow allow_loopback carve-out: only 127.0.0.1 when the
            # hostname is a known loopback label. Every other private range
            # stays blocked so allow_loopback can't be used as a wildcard.
            if not loopback_carveout:
                raise InvalidEndpointError(_ip_reason(ip), raw_url=url)

    if isinstance(ip, ipaddress.IPv6Address):
        if _is_private_ipv6(ip):
            if not loopback_carveout:
                raise InvalidEndpointError(_ip_reason(ip), raw_url=url)

    # Extra blocklist (corporate / internal ranges callers supply).
    # When the loopback carve-out applies, skip the blocked_networks sweep
    # as well — otherwise the default blocklist (which contains 127.0.0.0/8
    # precisely because loopback is unsafe for production) re-rejects the
    # IP the carve-out just permitted. The carve-out is still narrow: only
    # literal loopback IPs under a known loopback hostname label are
    # exempted, so no extra-blocklist CIDR a caller added can hit an IP
    # that satisfies the carve-out anyway.
    if blocked_networks and not loopback_carveout:
        for net in blocked_networks:
            try:
                if ip in net:
                    raise InvalidEndpointError("private_ipv4", raw_url=url)
            except TypeError:
                # Network family mismatch (v4 vs v6) is normal — skip.
                continue


def _check_host_allowlist(
    host_lc: str,
    host_allowlist: Optional[Sequence[str]],
    url: str,
) -> None:
    """Enforce the optional host allowlist.

    The allowlist is ONLY consulted AFTER the SSRF private-IP check has
    passed (per issue #473 non-negotiable 1). The allowlist narrows the
    already-safe public set — it is NOT a bypass path.
    """
    if host_allowlist is None:
        return
    normalized = {h.lower() for h in host_allowlist}
    if host_lc not in normalized:
        raise InvalidEndpointError("host_not_allowlisted", raw_url=url)


# ---------------------------------------------------------------------------
# SafeDnsTransport — connect-time SSRF re-check
# ---------------------------------------------------------------------------


class SafeDnsTransport(httpx.AsyncHTTPTransport):
    """httpx transport that re-resolves the peer host at connect time.

    ``check_url`` validates at URL-parse time. Between parse and connect
    there is a TOCTOU window where a public hostname could resolve to a
    public IP once and to 127.0.0.1 the next time (classic DNS rebinding).
    This transport closes that window by re-checking every resolution
    immediately before the TCP SYN.

    Per issue #473 non-negotiable 1: the private-IP check runs BEFORE the
    host allowlist, so an allowlisted private IP is still rejected at
    connect time.
    """

    __slots__ = (
        "_blocked_networks",
        "_host_allowlist",
        "_allow_loopback",
    )

    def __init__(
        self,
        *,
        blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]] = None,
        host_allowlist: Optional[Sequence[str]] = None,
        allow_loopback: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._blocked_networks = blocked_networks
        self._host_allowlist = host_allowlist
        self._allow_loopback = allow_loopback

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        # Re-run the full guard with DNS resolution active so a rebinding
        # attack is caught before the connect. The URL is reconstructed from
        # the request to keep fingerprints consistent with the caller-facing
        # log line.
        check_url(
            str(request.url),
            blocked_networks=self._blocked_networks,
            host_allowlist=self._host_allowlist,
            allow_loopback=self._allow_loopback,
            resolve_dns=True,
        )
        return await super().handle_async_request(request)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HttpClientConfig:
    """Configuration for ``HttpClient``.

    All defaults are SSRF-safe: follow_redirects defaults to False because
    every redirect is a new SSRF surface; blocked_networks defaults to the
    RFC1918 + loopback + link-local + IMDS set; host_allowlist defaults to
    None (every public host is permitted, subject to the SSRF guard).
    """

    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0
    follow_redirects: bool = False
    blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]] = None
    host_allowlist: Optional[Sequence[str]] = None
    structured_log_prefix: str = "nexus.http"
    request_id_header: str = "X-Request-ID"
    allow_loopback: bool = False
    default_headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Fall back to the canonical always-blocked networks when the caller
        # didn't supply a list. Frozen dataclass so we have to use
        # object.__setattr__ to install the default.
        if self.blocked_networks is None:
            object.__setattr__(
                self,
                "blocked_networks",
                _DEFAULT_BLOCKED_NETWORKS,
            )


# Baseline blocked networks. Applied on top of the per-IP private-range
# check so extra IPv4 + IPv6 CIDRs are rejected even when a libc helper
# somehow resolves them to look "public". RFC1918 + loopback + link-local +
# IMDS + ULA + link-local-v6 + documentation ranges.
_DEFAULT_BLOCKED_NETWORKS: tuple[ipaddress._BaseNetwork, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + IMDS
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT — commonly internal
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA
    ipaddress.ip_network("fe80::/10"),  # link-local v6
)


# ---------------------------------------------------------------------------
# HttpResponse — plain dataclass mirroring httpx.Response
# ---------------------------------------------------------------------------


@dataclass
class HttpResponse:
    """Outbound HTTP response — minimal, framework-agnostic.

    Exposed from raw methods (``get_raw`` etc.) so callers can inspect the
    status code WITHOUT a status-check exception being raised. Typed JSON
    methods (``get`` / ``post``) return decoded dicts directly.
    """

    status_code: int
    headers: dict[str, str]
    body: bytes
    url: str
    request_id: str


# ---------------------------------------------------------------------------
# HttpClient — the public primitive
# ---------------------------------------------------------------------------


class HttpClient:
    """SSRF-aware outbound HTTP client for Nexus.

    Every outbound request routes through ``check_url`` and
    ``SafeDnsTransport``. The ``Authorization`` header is ALLOWED on
    requests but NEVER logged; the endpoint hostname is logged, not the full
    URL.

    Use as an async context manager:

        async with HttpClient(HttpClientConfig()) as client:
            resp = await client.get("https://example.com/api")

    Or close explicitly:

        client = HttpClient(HttpClientConfig())
        try:
            await client.get(...)
        finally:
            await client.aclose()

    The underlying ``httpx.AsyncClient`` is never exposed — every outbound
    request goes through the observability-instrumented ``request()`` path.
    """

    __slots__ = ("_client", "_config", "_closed", "_transport")

    def __init__(self, config: Optional[HttpClientConfig] = None) -> None:
        self._config = config or HttpClientConfig()
        self._transport = SafeDnsTransport(
            blocked_networks=self._config.blocked_networks,
            host_allowlist=self._config.host_allowlist,
            allow_loopback=self._config.allow_loopback,
        )
        timeout = httpx.Timeout(
            self._config.timeout_seconds,
            connect=self._config.connect_timeout_seconds,
        )
        # follow_redirects is driven by config; the default is False because
        # every redirect is a fresh SSRF surface and the caller should opt
        # in consciously.
        self._client = httpx.AsyncClient(
            transport=self._transport,
            timeout=timeout,
            follow_redirects=self._config.follow_redirects,
        )
        self._closed = False

    @property
    def config(self) -> HttpClientConfig:
        return self._config

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> "HttpClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying transport. Idempotent."""
        if self._closed:
            return
        await self._client.aclose()
        self._closed = True

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        json: Any = None,
        content: Any = None,
        params: Optional[Mapping[str, Any]] = None,
        request_id: Optional[str] = None,
        follow_redirects: Optional[bool] = None,
    ) -> HttpResponse:
        """Dispatch an HTTP request with full observability.

        ``method`` is uppercased and validated against the standard verb set.
        ``request_id`` is generated if not supplied and injected into the
        request as the header named by ``config.request_id_header``.
        """
        if self._closed:
            raise RuntimeError(
                "HttpClient is closed; cannot dispatch new requests "
                "(construct a new client or avoid aclose() before reuse)"
            )

        method_up = method.upper()

        # SSRF guard at URL-parse time. SafeDnsTransport re-runs this at
        # connect time — both layers fire per the defence-in-depth contract.
        check_url(
            url,
            blocked_networks=self._config.blocked_networks,
            host_allowlist=self._config.host_allowlist,
            allow_loopback=self._config.allow_loopback,
            resolve_dns=True,
        )

        if request_id is None:
            request_id = str(uuid.uuid4())

        # Merge default headers + per-call headers. The request_id header is
        # added last so a caller-supplied value for it wins if present.
        merged_headers: dict[str, str] = dict(self._config.default_headers)
        if headers:
            merged_headers.update(headers)
        merged_headers.setdefault(self._config.request_id_header, request_id)

        has_auth = any(k.lower() == "authorization" for k in merged_headers.keys())
        endpoint_host = urlparse(url).hostname or "<unknown-host>"
        url_fp = _url_fingerprint(url)
        prefix = self._config.structured_log_prefix
        t0 = time.monotonic()
        logger.info(
            f"{prefix}.request.start",
            extra={
                "request_id": request_id,
                "method": method_up,
                "endpoint_host": endpoint_host,
                "url_fingerprint": url_fp,
                "has_auth": has_auth,
            },
        )

        # Raw redirects: caller may override config per-call. Still falls
        # under the SafeDnsTransport guard because httpx follows redirects
        # via the same transport, so every hop is re-validated.
        effective_follow = (
            self._config.follow_redirects
            if follow_redirects is None
            else follow_redirects
        )

        try:
            resp = await self._client.request(
                method_up,
                url,
                headers=merged_headers,
                json=json,
                content=content,
                params=dict(params) if params else None,
                follow_redirects=effective_follow,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.error(
                f"{prefix}.request.error",
                extra={
                    "request_id": request_id,
                    "method": method_up,
                    "endpoint_host": endpoint_host,
                    "url_fingerprint": url_fp,
                    "has_auth": has_auth,
                    "exception_class": type(exc).__name__,
                    "latency_ms": latency_ms,
                },
            )
            raise
        latency_ms = (time.monotonic() - t0) * 1000
        logger.info(
            f"{prefix}.request.ok",
            extra={
                "request_id": request_id,
                "method": method_up,
                "endpoint_host": endpoint_host,
                "url_fingerprint": url_fp,
                "has_auth": has_auth,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
            },
        )
        return HttpResponse(
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items()},
            body=resp.content,
            url=str(resp.url),
            request_id=request_id,
        )

    # ---- Verb methods -----------------------------------------------------

    async def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("PATCH", url, **kwargs)

    # ---- Streaming --------------------------------------------------------

    async def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        json: Any = None,
        content: Any = None,
        params: Optional[Mapping[str, Any]] = None,
        request_id: Optional[str] = None,
        chunk_size: int = 8192,
    ) -> AsyncIterator[bytes]:
        """Stream response body in chunks.

        Used for large webhook / health-probe response bodies where reading
        the entire body into memory is undesirable. The SSRF guard still
        runs; only the body-delivery mode differs.
        """
        if self._closed:
            raise RuntimeError("HttpClient is closed; cannot stream")

        method_up = method.upper()
        check_url(
            url,
            blocked_networks=self._config.blocked_networks,
            host_allowlist=self._config.host_allowlist,
            allow_loopback=self._config.allow_loopback,
            resolve_dns=True,
        )
        if request_id is None:
            request_id = str(uuid.uuid4())

        merged_headers: dict[str, str] = dict(self._config.default_headers)
        if headers:
            merged_headers.update(headers)
        merged_headers.setdefault(self._config.request_id_header, request_id)

        prefix = self._config.structured_log_prefix
        has_auth = any(k.lower() == "authorization" for k in merged_headers.keys())
        endpoint_host = urlparse(url).hostname or "<unknown-host>"
        url_fp = _url_fingerprint(url)
        t0 = time.monotonic()
        logger.info(
            f"{prefix}.stream.start",
            extra={
                "request_id": request_id,
                "method": method_up,
                "endpoint_host": endpoint_host,
                "url_fingerprint": url_fp,
                "has_auth": has_auth,
            },
        )

        async def _generator() -> AsyncIterator[bytes]:
            try:
                async with self._client.stream(
                    method_up,
                    url,
                    headers=merged_headers,
                    json=json,
                    content=content,
                    params=dict(params) if params else None,
                ) as resp:
                    async for chunk in resp.aiter_bytes(chunk_size):
                        yield chunk
            except Exception as exc:
                latency_ms = (time.monotonic() - t0) * 1000
                logger.error(
                    f"{prefix}.stream.error",
                    extra={
                        "request_id": request_id,
                        "method": method_up,
                        "endpoint_host": endpoint_host,
                        "url_fingerprint": url_fp,
                        "has_auth": has_auth,
                        "exception_class": type(exc).__name__,
                        "latency_ms": latency_ms,
                    },
                )
                raise
            else:
                latency_ms = (time.monotonic() - t0) * 1000
                logger.info(
                    f"{prefix}.stream.ok",
                    extra={
                        "request_id": request_id,
                        "method": method_up,
                        "endpoint_host": endpoint_host,
                        "url_fingerprint": url_fp,
                        "has_auth": has_auth,
                        "latency_ms": latency_ms,
                    },
                )

        return _generator()


__all__ = [
    "HttpClient",
    "HttpClientConfig",
    "HttpResponse",
    "HttpClientError",
    "InvalidEndpointError",
    "SafeDnsTransport",
    "check_url",
]
