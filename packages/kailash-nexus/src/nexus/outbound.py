# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Outbound convenience helpers built on ``HttpClient`` / ``ServiceClient``.

These helpers exist so ``HttpClient`` and its friends have at least one
production call site inside the framework (satisfying
``rules/orphan-detection.md`` spirit — a user-facing primitive that
nothing in the framework itself invokes risks never being exercised on
the actual hot path).

They are also genuinely useful: a nexus-hosted workflow that needs to
fire a webhook, probe a remote health endpoint, or forward an audit
event should reach for these helpers rather than importing ``httpx``
directly, so the call is auto-wrapped with SSRF guard + structured
logs + bearer-token hygiene from the shared primitives.

Public API:

.. code-block:: python

    from nexus import post_webhook, probe_remote_health

    await post_webhook(
        "https://hooks.example.com/incidents",
        {"event": "alert.fired", "severity": "high"},
        bearer_token=token,
    )

    healthy = await probe_remote_health("https://upstream.internal/healthz")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from nexus.http_client import HttpClient, HttpClientConfig
from nexus.service_client import ServiceClient

logger = logging.getLogger(__name__)

__all__ = [
    "post_webhook",
    "probe_remote_health",
]


async def post_webhook(
    url: str,
    payload: Mapping[str, Any],
    *,
    bearer_token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 10.0,
    allowed_hosts: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Fire a JSON webhook to ``url`` and return the decoded response.

    Wraps ``ServiceClient`` so the call inherits SSRF guard, eager
    header validation, structured logging, and bearer-token CRLF
    rejection without the caller having to remember any of it.

    Raises ``ServiceClientError`` (or a typed subclass) on failure.
    """
    # The call is shaped as a one-shot client so the caller doesn't
    # accumulate HttpClient instances for ad-hoc webhook emission.
    client = ServiceClient(
        url,
        bearer_token=bearer_token,
        headers=dict(headers or {}),
        timeout_secs=timeout_seconds,
        allowed_hosts=allowed_hosts,
    )
    logger.info(
        "nexus.webhook.post.start",
        extra={"url_fingerprint": _fp(url), "has_auth": bearer_token is not None},
    )
    response: Dict[str, Any] = client.post("", dict(payload))  # type: ignore[assignment]
    logger.info(
        "nexus.webhook.post.ok",
        extra={"url_fingerprint": _fp(url)},
    )
    return response


async def probe_remote_health(
    url: str,
    *,
    timeout_seconds: float = 5.0,
    allowed_hosts: Optional[list[str]] = None,
) -> bool:
    """Return True iff ``url`` returns 2xx within the timeout.

    Uses ``HttpClient`` directly (no bearer, no JSON decode) so the
    probe stays cheap and composable into readiness checks. SSRF guard
    is unconditional.
    """
    config = HttpClientConfig(
        timeout_seconds=timeout_seconds,
        connect_timeout_seconds=min(timeout_seconds, 2.0),
        follow_redirects=False,
        host_allowlist=allowed_hosts,
        structured_log_prefix="nexus.probe",
    )
    client = HttpClient(config)
    try:
        response = await client.get(url)
        ok = 200 <= response.status_code < 300
        logger.info(
            "nexus.probe.remote_health.result",
            extra={"url_fingerprint": _fp(url), "status": response.status_code, "ok": ok},
        )
        return ok
    except Exception as exc:
        logger.warning(
            "nexus.probe.remote_health.error",
            extra={"url_fingerprint": _fp(url), "error": type(exc).__name__},
        )
        return False


def _fp(url: str) -> str:
    """8-char sha256 fingerprint of a URL — correlation-safe, reversible-unsafe."""
    import hashlib

    return hashlib.sha256(url.encode("utf-8", errors="replace")).hexdigest()[:8]
