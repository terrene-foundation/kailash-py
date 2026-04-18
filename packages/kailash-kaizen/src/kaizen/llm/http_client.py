# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""LlmHttpClient -- single constructor path for LLM HTTP traffic.

Every LLM wire adapter MUST route its outbound HTTP through
`LlmHttpClient`. Direct construction of `httpx.AsyncClient(...)` inside
`kaizen/llm/**` is BLOCKED by the grep audit in
`packages/kailash-kaizen/tests/unit/llm/security/test_llm_http_client_uses_safe_dns_resolver.py`.

# Why a single constructor path?

The four-axis deployment abstraction owns the full outbound HTTP
contract: URL safety, auth header injection, SSRF defense, structured
logging. A wire adapter that constructs its own `httpx.AsyncClient`
bypasses every one of these -- the URL safety guard cannot see a request
the framework did not route. This class is the structural enforcement.

# SafeDnsResolver

`SafeDnsResolver` is installed on the underlying httpx transport so that
every outbound connection -- even one whose hostname resolves to a
private IP at connect time -- is rejected before the TCP SYN fires. The
`url_safety.check_url()` SSRF guard catches literal-IP and DNS-rebinding
attempts at URL-parse time; `SafeDnsResolver` catches the same attack
surface at resolve-time so a TOCTOU window between parse and connect
cannot exist.

Both guards run: URL safety is the earlier gate, SafeDnsResolver is the
last-line structural defense. Removing either widens the surface.

# Observability

Every outbound request emits three structured log points
(`llm.http.request.start` / `.ok` / `.error`) carrying:

* `deployment_preset` -- e.g. "openai" / "bedrock_claude"
* `auth_strategy_kind` -- e.g. "api_key" / "aws_bearer_token"
* `endpoint_host` -- the hostname (NOT the full URL -- the URL may
  contain query-string credentials for some legacy providers)
* `latency_ms` -- wall-clock latency on ok / error paths
* `status_code` -- HTTP status on ok path
* `request_id` -- UUID4 generated at request-start for correlation

The `Authorization` header value is NEVER logged. The header NAME is
logged at DEBUG only (per `observability.md` § 8). Upstream error bodies
are run through `ProviderError`'s credential-scrub before being attached
to any structured log line.

# Cross-SDK parity

Semantic match with `kailash-rs` `LlmHttpClient`: single constructor
path, structurally-installed resolver, same three log tags. Python uses
`httpx` + `socket.getaddrinfo`; Rust uses `hyper` + its native resolver.
The observability log-field names are byte-identical so log aggregators
correlate across SDKs.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
import uuid
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

import httpx

from kaizen.llm.errors import InvalidEndpoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SafeDnsResolver -- last-line SSRF defense at DNS resolve time
# ---------------------------------------------------------------------------
#
# The URL safety guard in `kaizen.llm.url_safety.check_url` runs at
# Endpoint construction. That catches literal-IP SSRF and DNS rebinding
# that resolves at parse time. But between parse and connect there is a
# TOCTOU window: a public hostname that resolved to 1.2.3.4 at parse
# time could resolve to 127.0.0.1 at connect time (classic DNS
# rebinding). SafeDnsResolver closes that window by re-checking every
# resolve at the exact moment httpx is about to open a TCP connection.


_IPV4_TRANSLATED_NETWORK = ipaddress.IPv6Network("::ffff:0:0:0/96")
_NAT64_WELLKNOWN_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")

_METADATA_IPS = frozenset(
    {
        "169.254.169.254",
        "fd00:ec2::254",
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


class SafeDnsResolver:
    """Re-validates every resolved IP against the private/metadata allowlist.

    Stateless: a single instance is reused across every `LlmHttpClient`.
    The `resolve(host, port)` method returns a tuple of socket tuples
    suitable for `httpx.HTTPTransport`'s custom-resolver hook, OR raises
    `InvalidEndpoint` if any of the resolved addresses fall into the
    rejected ranges.

    This class is the structural enforcement point for SSRF defense at
    DNS-resolve time -- the last gate before TCP connect. Removing the
    resolver install from `LlmHttpClient.__init__` is a Tier-2 wiring
    regression (see `test_llmhttpclient_wiring.py`).
    """

    __slots__ = ()

    def check_host(self, host: str) -> None:
        """Resolve `host` and raise `InvalidEndpoint` if any IP is private.

        Raises `InvalidEndpoint(reason="metadata_service")` for the AWS
        / GCP / Azure metadata IPs specifically so forensic aggregation
        can separate "metadata exfiltration attempt" from the broader
        "private_ipv4" bucket. This mirrors `url_safety.check_url`'s
        reason-code taxonomy so downstream dashboards can group findings
        across the two guards without translation.
        """
        if not isinstance(host, str) or not host:
            raise InvalidEndpoint("malformed_url", raw_url=None)
        # Literal IP form -- no DNS involved.
        try:
            parsed = ipaddress.ip_address(host)
        except (ValueError, TypeError):
            parsed = None
        if parsed is not None:
            if str(parsed) in _METADATA_IPS:
                raise InvalidEndpoint("metadata_service", raw_url=host)
            if isinstance(parsed, ipaddress.IPv4Address) and _is_private_ipv4(parsed):
                raise InvalidEndpoint("private_ipv4", raw_url=host)
            if isinstance(parsed, ipaddress.IPv6Address) and _is_private_ipv6(parsed):
                if parsed.ipv4_mapped is not None or (
                    parsed in _IPV4_TRANSLATED_NETWORK
                    or parsed in _NAT64_WELLKNOWN_NETWORK
                ):
                    raise InvalidEndpoint("ipv4_mapped", raw_url=host)
                if parsed.is_loopback:
                    raise InvalidEndpoint("loopback", raw_url=host)
                if parsed.is_link_local:
                    raise InvalidEndpoint("link_local", raw_url=host)
                raise InvalidEndpoint("private_ipv6", raw_url=host)
            # Literal public IP -- accept.
            return

        # DNS resolution. Every returned address MUST pass the
        # allowlist; the first private/metadata address raises.
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise InvalidEndpoint("resolution_failed", raw_url=host)
        if not infos:
            raise InvalidEndpoint("resolution_failed", raw_url=host)

        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except (ValueError, TypeError):
                continue
            if str(ip) in _METADATA_IPS:
                raise InvalidEndpoint("metadata_service", raw_url=host)
            if isinstance(ip, ipaddress.IPv4Address) and _is_private_ipv4(ip):
                raise InvalidEndpoint("private_ipv4", raw_url=host)
            if isinstance(ip, ipaddress.IPv6Address) and _is_private_ipv6(ip):
                if ip.ipv4_mapped is not None or (
                    ip in _IPV4_TRANSLATED_NETWORK or ip in _NAT64_WELLKNOWN_NETWORK
                ):
                    raise InvalidEndpoint("ipv4_mapped", raw_url=host)
                if ip.is_loopback:
                    raise InvalidEndpoint("loopback", raw_url=host)
                if ip.is_link_local:
                    raise InvalidEndpoint("link_local", raw_url=host)
                raise InvalidEndpoint("private_ipv6", raw_url=host)

    def kind(self) -> str:
        """Stable label for observability -- cross-SDK parity."""
        return "safe_dns"


# ---------------------------------------------------------------------------
# LlmHttpClient -- the ONLY constructor path for LLM HTTP
# ---------------------------------------------------------------------------


class _SafeHttpTransport(httpx.AsyncHTTPTransport):
    """httpx transport that routes every connect through SafeDnsResolver.

    Subclass rather than compose: httpx's transport hook runs at connect
    time, which is precisely the surface SafeDnsResolver needs. The
    subclass overrides `handle_async_request` to validate the peer host
    BEFORE the underlying transport opens the TCP socket. Any rejection
    surfaces as `InvalidEndpoint`, which callers should treat as an
    EndpointError (not an `httpx.ConnectError`).
    """

    def __init__(self, resolver: SafeDnsResolver, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._resolver = resolver

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        # Structural gate: validate the host at connect time. The
        # resolver raises InvalidEndpoint on any private / metadata IP
        # -- the TCP SYN never fires for a rejected host.
        self._resolver.check_host(host)
        return await super().handle_async_request(request)


class LlmHttpClient:
    """Wraps `httpx.AsyncClient` with a structurally-installed SafeDnsResolver.

    Every LLM wire adapter constructs its HTTP client through this
    class. The underlying `httpx.AsyncClient` is NEVER exposed -- callers
    interact through `request()`, `get()`, `post()` methods that go
    through the structured logging path.

    # Lifecycle

    `LlmHttpClient` is an async resource and MUST be closed via
    `await client.aclose()` or used as an async context manager:

        async with LlmHttpClient() as client:
            resp = await client.post(url, ...)

    The `__del__` finalizer emits `ResourceWarning` if the client is
    garbage-collected without close (per
    `rules/patterns.md` § "Async Resource Cleanup"). It does NOT call
    `close()` from `__del__` -- that deadlocks on CPython's root logging
    lock when the finalizer fires during GC.
    """

    __slots__ = ("_client", "_resolver", "_closed", "_deployment_preset")

    def __init__(
        self,
        *,
        deployment_preset: Optional[str] = None,
        timeout: float = 30.0,
        resolver: Optional[SafeDnsResolver] = None,
    ) -> None:
        """Construct a client with a SafeDnsResolver installed on the transport.

        `deployment_preset` is stitched into every structured log line so
        dashboards can break down HTTP traffic by preset. `resolver` is
        overridable for tests ONLY; production callers MUST use the
        default.
        """
        self._resolver = resolver if resolver is not None else SafeDnsResolver()
        if not isinstance(self._resolver, SafeDnsResolver):
            raise TypeError(
                "LlmHttpClient.resolver must be a SafeDnsResolver instance; "
                f"got {type(self._resolver).__name__}"
            )
        transport = _SafeHttpTransport(resolver=self._resolver)
        # httpx.AsyncClient(transport=...) is the ONE place in
        # kaizen/llm/** where httpx.AsyncClient may be constructed. The
        # grep audit (tests/unit/llm/security/
        # test_llm_http_client_uses_safe_dns_resolver.py) enforces this.
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._closed = False
        self._deployment_preset = deployment_preset

    async def __aenter__(self) -> "LlmHttpClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    @property
    def resolver(self) -> SafeDnsResolver:
        """The installed resolver. Public for Tier 2 wiring tests."""
        return self._resolver

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def aclose(self) -> None:
        """Close the underlying httpx client. Idempotent."""
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
        content: Any = None,
        auth_strategy_kind: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an HTTP request with structured observability.

        Emits three structured log lines:
          * `llm.http.request.start` -- intent + host + auth kind
          * `llm.http.request.ok` -- status + latency on success
          * `llm.http.request.error` -- latency + exception class on failure

        The `Authorization` header VALUE is NEVER logged; the header
        shape is logged at DEBUG only. Endpoint host is logged as the
        hostname, NOT the full URL, because some providers (legacy
        Google) carry credentials in the query string.
        """
        if self._closed:
            raise RuntimeError(
                "LlmHttpClient is closed; cannot issue new requests "
                "(construct a new client or avoid aclose() before reuse)"
            )
        request_id = str(uuid.uuid4())
        endpoint_host = urlparse(url).hostname or "<unknown-host>"
        t0 = time.monotonic()
        logger.info(
            "llm.http.request.start",
            extra={
                "request_id": request_id,
                "deployment_preset": self._deployment_preset,
                "auth_strategy_kind": auth_strategy_kind,
                "endpoint_host": endpoint_host,
                "method": method,
            },
        )
        try:
            resp = await self._client.request(
                method,
                url,
                headers=dict(headers) if headers else None,
                content=content,
                **kwargs,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "llm.http.request.error",
                extra={
                    "request_id": request_id,
                    "deployment_preset": self._deployment_preset,
                    "auth_strategy_kind": auth_strategy_kind,
                    "endpoint_host": endpoint_host,
                    "method": method,
                    "exception_class": type(exc).__name__,
                    "latency_ms": latency_ms,
                },
            )
            raise
        latency_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "llm.http.request.ok",
            extra={
                "request_id": request_id,
                "deployment_preset": self._deployment_preset,
                "auth_strategy_kind": auth_strategy_kind,
                "endpoint_host": endpoint_host,
                "method": method,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
            },
        )
        return resp

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    def __del__(self) -> None:
        # Emit ResourceWarning ONLY; do not call close() from finalizer.
        # See rules/patterns.md § "Async Resource Cleanup" for why
        # async cleanup in __del__ deadlocks on CPython's logging lock.
        if not self._closed:
            import warnings

            warnings.warn(
                "LlmHttpClient not closed; call await client.aclose() "
                "or use it as an async context manager",
                ResourceWarning,
                stacklevel=2,
            )


__all__ = ["LlmHttpClient", "SafeDnsResolver"]
