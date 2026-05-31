# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Request-capture middleware for the extractor resolver.

``handler_extract`` resolvers need the originating Starlette ``Request`` to
bind the ``Request`` / ``Headers`` / ``Bytes`` extractors. The gateway runs
handler workflows without threading the request into the workflow inputs, so a
small ASGI middleware captures the request into a ContextVar (the same
propagation pattern ``JWTMiddleware`` uses for tenant/actor — see
``nexus/context.py``).

The middleware also stamps the configured ``max_request_body_bytes`` cap onto
the request so the ``Bytes`` extractor can short-circuit oversized bodies and
applies the trusted-proxy posture to ``request.client.host``.
"""

from typing import List, Optional

from starlette.middleware.base import BaseHTTPMiddleware

from nexus.context import _current_request, set_current_request
from nexus.extractors.proxy import resolve_client_host

__all__ = ["RequestCaptureMiddleware"]


class RequestCaptureMiddleware(BaseHTTPMiddleware):
    """Capture the originating request into the resolver ContextVar.

    Reset-in-``finally`` so a raised exception inside ``call_next`` cannot leak
    the request into the next request on the same worker.
    """

    def __init__(
        self,
        app,
        *,
        max_request_body_bytes: int,
        max_request_header_bytes: int,
        trusted_proxy_cidrs: Optional[List[str]] = None,
    ) -> None:
        super().__init__(app)
        self._max_request_body_bytes = max_request_body_bytes
        self._max_request_header_bytes = max_request_header_bytes
        self._trusted_proxy_cidrs = list(trusted_proxy_cidrs or [])

    async def dispatch(self, request, call_next):
        # Stamp the size caps so the Bytes / Headers extractors can short-circuit.
        request._nexus_max_request_body_bytes = self._max_request_body_bytes
        request._nexus_max_request_header_bytes = self._max_request_header_bytes

        # Trusted-proxy posture: the resolved originating host is computed
        # from the immediate peer + trusted CIDRs; forwarded headers are
        # honoured ONLY when the immediate peer is trusted. The structural
        # CIDR check never raises on mixed IP version (fails closed).
        peer_ip = request.client.host if request.client else None
        resolved_host = resolve_client_host(
            peer_ip, request.headers, self._trusted_proxy_cidrs
        )
        # Surface the trust decision + resolved client host without mutating
        # request.client (Starlette's client is immutable & TLS-derived).
        request._nexus_resolved_client_host = resolved_host

        token = set_current_request(request)
        try:
            return await call_next(request)
        finally:
            _current_request.reset(token)
