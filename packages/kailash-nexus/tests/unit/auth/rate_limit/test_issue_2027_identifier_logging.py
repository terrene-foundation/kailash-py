# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Issue #2027 — the rate-limit WARN must not carry the raw identifier.

Lives in the nexus package's own tree rather than the root regression suite:
the root ``pytest.ini`` puts only core's ``src`` on the path, so a root test
importing ``nexus`` resolves whatever is pip-installed rather than the tree
under test — which would silently report on the wrong source.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

BEARER = "sk-live-0123456789abcdefghij"


@pytest.mark.unit
def test_rate_limit_warning_does_not_log_the_raw_identifier(caplog) -> None:
    """nexus rate-limit middleware — the identifier is an IP, a user id, or
    (by the extractor's convention) an API key. The exceeded-limit WARN must
    carry a fingerprint, not the value.

    ``dispatch`` is driven directly rather than through a TestClient: the
    middleware's rate-limit decision needs only ``request.url.path`` and the
    injected extractor, and the log line under test is emitted on the 429
    branch of that same method.
    """
    pytest.importorskip("nexus.auth.rate_limit.middleware")
    from kailash.trust.rate_limit.config import RateLimitConfig
    from nexus.auth.rate_limit.middleware import RateLimitMiddleware

    class _Url:
        path = "/api/things"

    class _Request:
        url = _Url()

    middleware = RateLimitMiddleware(
        app=None,
        config=RateLimitConfig(requests_per_minute=1, backend="memory"),
        identifier_extractor=lambda _request: BEARER,
    )

    async def _drive():
        # call_next is only reached while the request is ALLOWED; the
        # middleware then writes rate-limit headers onto what it returns.
        class _AllowedResponse:
            def __init__(self) -> None:
                self.headers: dict = {}
                self.status_code = 200

        async def _ok(_request):
            return _AllowedResponse()

        # Loop until the limit actually trips rather than assuming it does so
        # on request 2: the backend enforces its own default window size, not
        # the ``requests_per_minute=1`` echoed in the X-RateLimit-Limit header
        # (a config-plumbing discrepancy outside this issue's scope). The test
        # asserts a 429 was genuinely reached, so it cannot pass vacuously.
        with caplog.at_level(logging.WARNING):
            for _ in range(40):
                response = await middleware.dispatch(_Request(), _ok)
                if getattr(response, "status_code", None) == 429:
                    return response
        return None

    response = asyncio.run(_drive())

    assert response is not None, "the limit never tripped; test would be vacuous"
    assert response.status_code == 429, "the limit was not enforced"
    assert caplog.text, "no WARN captured; test would be vacuous"
    assert BEARER not in caplog.text, "raw rate-limit identifier reached the log"
    assert "identifier_fp=" in caplog.text
