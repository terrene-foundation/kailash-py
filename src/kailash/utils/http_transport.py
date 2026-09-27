# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HTTPX adapter with validated numeric TCP admission and original TLS origin.

Policy belongs to the supplied validators; this module binds their exact
address result to HTTPCore's public network-backend interface. It never rewrites
request URLs or pool origins. Proxies and Unix sockets are rejected because they
would bypass destination TCP admission.
"""

from __future__ import annotations

import ipaddress
from contextvars import ContextVar
from typing import Callable, Sequence

try:
    import anyio
    import httpcore
    import httpx
except ImportError as exc:
    raise ImportError(
        "Guarded HTTP transport requires pip install kailash[http-client]"
    ) from exc


from kailash.utils.http_logging import (
    owned_http_diagnostics,
    unowned_http_diagnostics,
)


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, resolve_addresses: Callable[[str], Sequence[str]]) -> None:
        self._resolve_addresses = resolve_addresses
        self.request_url: ContextVar[str] = ContextVar("guarded_http_request_url")
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):
        # One deadline covers resolution and every numeric candidate. A failed
        # first address cannot multiply the caller's connection time budget.
        try:
            with anyio.fail_after(timeout):
                with unowned_http_diagnostics():
                    addresses = await anyio.to_thread.run_sync(
                        self._resolve_addresses,
                        self.request_url.get(),
                        abandon_on_cancel=True,
                    )
                if not addresses:
                    raise httpcore.ConnectError("No validated TCP addresses")
                # Enforce the callback contract before admitting ANY candidate.
                addresses = tuple(str(ipaddress.ip_address(ip)) for ip in addresses)
                for index, address in enumerate(addresses):
                    try:
                        return await self._backend.connect_tcp(
                            address,
                            port,
                            timeout=None,
                            local_address=local_address,
                            socket_options=socket_options,
                        )
                    except (httpcore.ConnectError, httpcore.ConnectTimeout):
                        if index == len(addresses) - 1:
                            raise
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout("Validated TCP connection timed out") from exc

    async def sleep(self, seconds):
        await self._backend.sleep(seconds)


class DnsPinnedAsyncTransport(httpx.AsyncHTTPTransport):
    """Standard HTTPX response/exception adapter over a guarded HTTPCore pool.

    The supported HTTPX options retain their normal meaning. ``proxy`` and
    ``uds`` must be absent. Request headers, TLS SNI, certificate hostname
    verification, streaming, and origin isolation remain HTTPCore-owned.
    """

    def __init__(
        self,
        *,
        resolve_addresses: Callable[[str], Sequence[str]],
        validate_url: Callable[[str], None],
        verify=True,
        cert=None,
        trust_env=True,
        http1=True,
        http2=False,
        limits=None,
        proxy=None,
        uds=None,
        local_address=None,
        retries=0,
        socket_options=None,
    ) -> None:
        if proxy is not None or uds is not None:
            raise ValueError("Guarded HTTP transport does not support proxy or uds")
        if http2:
            try:
                import h2  # noqa: F401
            except ImportError as exc:
                raise ImportError("HTTP/2 requires pip install httpx[http2]") from exc
        limits = (
            limits
            if limits is not None
            else httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        self._validate_url = validate_url
        self._pinned_backend = _PinnedNetworkBackend(resolve_addresses)
        # Own the public pool from construction. The inherited HTTPX adapter
        # supplies request/response conversion, exception mapping and aclose.
        with owned_http_diagnostics():
            self._pool = httpcore.AsyncConnectionPool(
                ssl_context=httpx.create_ssl_context(
                    verify=verify, cert=cert, trust_env=trust_env
                ),
                max_connections=limits.max_connections,
                max_keepalive_connections=limits.max_keepalive_connections,
                keepalive_expiry=limits.keepalive_expiry,
                http1=http1,
                http2=http2,
                retries=retries,
                local_address=local_address,
                socket_options=socket_options,
                network_backend=self._pinned_backend,
            )

    async def handle_async_request(self, request):
        url = str(request.url)
        with unowned_http_diagnostics():
            self._validate_url(url)
        token = self._pinned_backend.request_url.set(url)
        try:
            return await super().handle_async_request(request)
        finally:
            self._pinned_backend.request_url.reset(token)
