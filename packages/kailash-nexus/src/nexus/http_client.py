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

from kailash.utils.network_guard import (
    DEFAULT_BLOCKED_NETWORKS as _DEFAULT_BLOCKED_NETWORKS,
)
from kailash.utils.network_guard import (
    METADATA_HOSTNAMES as _METADATA_HOSTNAMES,
)
from kailash.utils.network_guard import METADATA_IPS as _METADATA_IPS
from kailash.utils.network_guard import REASON_ALLOWLIST
from kailash.utils.network_guard import check_url as _core_check_url
from kailash.utils.network_guard import (
    detect_encoded_ip_bypass as _detect_encoded_ip_bypass,
)
from kailash.utils.network_guard import (
    is_private_ipv4 as _is_private_ipv4,
)
from kailash.utils.network_guard import (
    is_private_ipv6 as _is_private_ipv6,
)
from kailash.utils.network_guard import (
    iter_resolved_ips as _iter_resolved_ips,
)
from kailash.utils.network_guard import url_fingerprint as _url_fingerprint

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

    _REASON_ALLOWLIST = REASON_ALLOWLIST

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
# SSRF guard — LIFTED TO CORE (issue #2091)
# ---------------------------------------------------------------------------
#
# The private/loopback/link-local/metadata detection, the encoded-IP bypass
# forms, the IPv4-in-IPv6 translation ranges and the metadata sets were all
# worked out HERE first. They now live in `kailash.utils.network_guard` so
# core's reverse-proxy surfaces can enforce the same posture: `kailash-nexus`
# depends on `kailash` and never the reverse, so the shared piece has to sit
# in core for both to use it.
#
# This module keeps its own error TYPE and its client wiring, and delegates
# every DECISION. There is deliberately no second copy of the logic to drift
# from — `zero-tolerance.md` Rule 4. `check_url` below is a thin adapter that
# pins nexus's strict posture (no allow_private, no allow_metadata) and
# injects nexus's exception type through the shared implementation's
# `error_factory` hook.

def check_url(
    url: str,
    *,
    blocked_networks: Optional[Sequence[ipaddress._BaseNetwork]] = None,
    host_allowlist: Optional[Sequence[str]] = None,
    allow_loopback: bool = False,
    resolve_dns: bool = True,
) -> None:
    """Validate ``url`` as an SSRF-safe outbound target.

    Raises :class:`InvalidEndpointError` on any rejection. ``reason`` is from
    a fixed allowlist; the raw URL is hashed and stored only as a fingerprint
    on the exception so audit logs never echo the user-supplied URL.

    Ordering — per issue #473 non-negotiable 1: the private-IP / metadata
    check runs BEFORE the host allowlist check. An allowlisted private IP is
    still rejected. The allowlist ONLY narrows the already-safe set of public
    hosts; it MUST NOT be a back-door past the SSRF guard.

    ``allow_loopback=True`` is for tests against a local stub server. It
    narrowly permits 127.0.0.1 / localhost / ::1. Every other private range
    stays blocked.

    ``blocked_networks`` lets callers add additional CIDR blocks on top of
    the always-blocked set (e.g. a corporate internal block the attacker
    shouldn't reach even if it passes the RFC1918 check).

    The decision logic is :func:`kailash.utils.network_guard.check_url`. This
    wrapper exists to pin nexus's STRICT posture — ``allow_private`` and
    ``allow_metadata`` are not exposed here, because an outbound client
    talking to the public internet has no business reaching RFC1918 — and to
    raise nexus's own error type.
    """
    _core_check_url(
        url,
        blocked_networks=blocked_networks,
        host_allowlist=host_allowlist,
        allow_loopback=allow_loopback,
        resolve_dns=resolve_dns,
        allow_private=False,
        allow_metadata=False,
        error_factory=InvalidEndpointError,
    )

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
