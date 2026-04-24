# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Webhook Receiver — push-based source change detection.

Validates signatures via provider-specific verifiers (generic / github /
gitlab / stripe / slack), rejects stale timestamps, deduplicates via
nonce tracking. All workers accept webhooks; only the leader processes
them (RT-2 resolution).

The verifier is selected by ``WebhookConfig.provider``. Each verifier
encapsulates one third-party signature contract:

- ``generic`` — ``X-Webhook-Signature: <hex>`` over the raw body.
  Default for sources that follow Kailash webhook conventions.
- ``github`` — ``X-Hub-Signature-256: sha256=<hex>``. The signature
  prefix is mandatory and is rejected if missing.
- ``gitlab`` — ``X-Gitlab-Token: <secret>``. Plain shared-secret
  comparison (still constant-time via ``hmac.compare_digest``).
- ``stripe`` — ``Stripe-Signature: t=<unix>,v1=<hex>[,...]`` signed
  over ``{timestamp}.{raw_body}``. The verifier also enforces the
  Stripe-recommended 5-minute timestamp window so a replay sniffed
  hours later is rejected even if the body still verifies.
- ``slack`` — ``X-Slack-Signature: v0=<hex>`` plus
  ``X-Slack-Request-Timestamp`` signed over
  ``v0:{ts}:{raw_body}``. Slack's recommendation is also a 5-minute
  window which the verifier enforces independently of the receiver's
  generic timestamp check.

Nonce storage supports two backends:
- **Redis** (production): SADD + TTL for cross-worker deduplication.
- **In-memory** (dev mode): bounded LRU set for single-worker use.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import os
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Optional

from dataflow.fabric.config import WebhookConfig

logger = logging.getLogger(__name__)

__all__ = ["WebhookReceiver"]

_MAX_TIMESTAMP_AGE_SECONDS = 300  # 5 minutes (doc 01-redteam H1)
_MAX_NONCE_ENTRIES = 10_000
_NONCE_TTL_SECONDS = 300  # Match timestamp window


class _NonceBackend(ABC):
    """Abstract nonce deduplication backend."""

    @abstractmethod
    async def contains(self, source_name: str, nonce: str) -> bool: ...

    @abstractmethod
    async def add(self, source_name: str, nonce: str) -> None: ...


class _InMemoryNonceBackend(_NonceBackend):
    """LRU-evicting set for nonce deduplication, bounded to prevent OOM.

    Suitable for dev mode / single-worker deployments only.
    """

    def __init__(self, maxsize: int = _MAX_NONCE_ENTRIES) -> None:
        self._store: OrderedDict[str, float] = OrderedDict()
        self._maxsize = maxsize

    async def contains(self, source_name: str, nonce: str) -> bool:
        key = f"{source_name}:{nonce}"
        return key in self._store

    async def add(self, source_name: str, nonce: str) -> None:
        key = f"{source_name}:{nonce}"
        if key in self._store:
            self._store.move_to_end(key)
            return
        if len(self._store) >= self._maxsize:
            self._store.popitem(last=False)  # Evict oldest
        self._store[key] = time.monotonic()


class _RedisNonceBackend(_NonceBackend):
    """Redis-backed nonce deduplication for cross-worker deployments.

    Uses SADD + EXPIRE per source. Key pattern:
    ``fabric:webhook:nonces:{source_name}``
    TTL matches the timestamp rejection window (5 minutes).
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def contains(self, source_name: str, nonce: str) -> bool:
        key = f"fabric:webhook:nonces:{source_name}"
        return bool(await self._redis.sismember(key, nonce))

    async def add(self, source_name: str, nonce: str) -> None:
        key = f"fabric:webhook:nonces:{source_name}"
        # Pipeline ensures SADD + EXPIRE are atomic (no TTL-less orphan on crash)
        if hasattr(self._redis, "pipeline"):
            async with self._redis.pipeline() as pipe:
                pipe.sadd(key, nonce)
                pipe.expire(key, _NONCE_TTL_SECONDS)
                await pipe.execute()
        else:
            # Fallback for Redis clients without pipeline support.
            # If expire fails after sadd, remove the nonce to avoid
            # a TTL-less entry that persists indefinitely.
            await self._redis.sadd(key, nonce)
            try:
                await self._redis.expire(key, _NONCE_TTL_SECONDS)
            except Exception:
                logger.warning(
                    "Failed to set TTL on nonce set '%s'; removing nonce to prevent leak",
                    key,
                )
                await self._redis.srem(key, nonce)


# Backward-compatible alias for existing tests
class _BoundedNonceSet:
    """Legacy in-memory nonce set (kept for backward compatibility)."""

    def __init__(self, maxsize: int = _MAX_NONCE_ENTRIES) -> None:
        self._backend = _InMemoryNonceBackend(maxsize)

    def contains(self, nonce: str) -> bool:
        # Synchronous wrapper for legacy callers
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Cannot await in a running loop — check directly
            key = f":{nonce}"
            return key in self._backend._store
        return asyncio.run(self._backend.contains("", nonce))

    def add(self, nonce: str) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            key = f":{nonce}"
            store = self._backend._store
            if key in store:
                store.move_to_end(key)
                return
            if len(store) >= self._backend._maxsize:
                store.popitem(last=False)
            store[key] = time.monotonic()
        else:
            asyncio.run(self._backend.add("", nonce))

    def __len__(self) -> int:
        return len(self._backend._store)


# ---------------------------------------------------------------------------
# Provider signature verifiers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _VerifyResult:
    """Outcome of a provider-specific webhook signature verification."""

    accepted: bool
    reason: str
    nonce: Optional[str] = None


class _SignatureVerifier(ABC):
    """Provider signature verifier contract.

    Each verifier owns a single third-party signature scheme. Verifiers
    are pure functions of (headers, body, secret) — they MUST NOT
    consult external state (Redis, env, clocks beyond the now() the
    receiver supplies).
    """

    name: str = "abstract"

    @abstractmethod
    def verify(
        self,
        *,
        headers: Dict[str, str],
        body: bytes,
        secret: str,
        now: datetime,
    ) -> _VerifyResult: ...


class _GenericVerifier(_SignatureVerifier):
    """``X-Webhook-Signature: <sha256-hex>`` over the raw body.

    The Kailash default — used by sources that follow the platform's
    own webhook conventions instead of mimicking a third-party
    provider.
    """

    name = "generic"

    def verify(
        self,
        *,
        headers: Dict[str, str],
        body: bytes,
        secret: str,
        now: datetime,
    ) -> _VerifyResult:
        signature = headers.get("x-webhook-signature", "")
        if not signature:
            return _VerifyResult(False, "Missing X-Webhook-Signature header")
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return _VerifyResult(False, "Invalid signature")
        nonce = headers.get("x-webhook-delivery-id") or None
        return _VerifyResult(True, "ok", nonce=nonce)


class _GitHubVerifier(_SignatureVerifier):
    """``X-Hub-Signature-256: sha256=<hex>`` over the raw body.

    GitHub mandates the ``sha256=`` prefix; signatures without it are
    rejected because GitHub never sends them.
    """

    name = "github"

    def verify(
        self,
        *,
        headers: Dict[str, str],
        body: bytes,
        secret: str,
        now: datetime,
    ) -> _VerifyResult:
        header_value = headers.get("x-hub-signature-256", "")
        if not header_value:
            return _VerifyResult(False, "Missing X-Hub-Signature-256 header")
        if not header_value.startswith("sha256="):
            return _VerifyResult(False, "X-Hub-Signature-256 must start with sha256=")
        signature = header_value[len("sha256=") :]
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return _VerifyResult(False, "Invalid signature")
        # GitHub deliveries carry a unique X-GitHub-Delivery UUID.
        nonce = headers.get("x-github-delivery") or None
        return _VerifyResult(True, "ok", nonce=nonce)


class _GitLabVerifier(_SignatureVerifier):
    """``X-Gitlab-Token: <shared-secret>`` constant-time comparison.

    GitLab does not HMAC the body — it ships the configured secret
    token verbatim. We still use ``hmac.compare_digest`` so the check
    is constant-time and safe against length-extension probing.
    """

    name = "gitlab"

    def verify(
        self,
        *,
        headers: Dict[str, str],
        body: bytes,
        secret: str,
        now: datetime,
    ) -> _VerifyResult:
        token = headers.get("x-gitlab-token", "")
        if not token:
            return _VerifyResult(False, "Missing X-Gitlab-Token header")
        if not hmac.compare_digest(token, secret):
            return _VerifyResult(False, "Invalid token")
        # GitLab exposes a delivery UUID for replay protection.
        nonce = headers.get("x-gitlab-event-uuid") or None
        return _VerifyResult(True, "ok", nonce=nonce)


class _StripeVerifier(_SignatureVerifier):
    """``Stripe-Signature: t=<unix>,v1=<hex>[,...]`` over ``{t}.{body}``.

    The verifier:
    - Parses the ``t=`` and ``v1=`` fields out of the header (multiple
      ``v1=`` values are supported per Stripe's signing-key rotation
      docs; any matching v1 accepts the request).
    - Recomputes ``HMAC_SHA256(secret, "{t}.{raw_body}")`` and
      constant-time compares against each ``v1`` candidate.
    - Enforces a 5-minute tolerance window on ``t`` independently of
      the WebhookReceiver's generic timestamp check, because Stripe
      explicitly recommends this and the body never carries a
      separate ``X-Webhook-Timestamp`` header.
    """

    name = "stripe"
    _TOLERANCE_SECONDS = 300

    def verify(
        self,
        *,
        headers: Dict[str, str],
        body: bytes,
        secret: str,
        now: datetime,
    ) -> _VerifyResult:
        header_value = headers.get("stripe-signature", "")
        if not header_value:
            return _VerifyResult(False, "Missing Stripe-Signature header")
        timestamp: Optional[str] = None
        candidates: list[str] = []
        for part in header_value.split(","):
            kv = part.strip().split("=", 1)
            if len(kv) != 2:
                continue
            key, value = kv[0].strip(), kv[1].strip()
            if key == "t":
                timestamp = value
            elif key == "v1":
                candidates.append(value)
        if timestamp is None:
            return _VerifyResult(False, "Stripe-Signature missing 't' field")
        if not candidates:
            return _VerifyResult(False, "Stripe-Signature missing 'v1' field")

        # Tolerance window — guard NaN/Inf to match the receiver's
        # generic timestamp validator.
        try:
            ts_float = float(timestamp)
            if not math.isfinite(ts_float):
                raise ValueError("non-finite timestamp")
        except ValueError:
            return _VerifyResult(False, "Stripe-Signature timestamp not numeric")
        ts_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        age = (now - ts_dt).total_seconds()
        if age > self._TOLERANCE_SECONDS:
            return _VerifyResult(False, f"Stripe timestamp too old ({int(age)}s)")
        if age < -60:
            return _VerifyResult(False, "Stripe timestamp is in the future")

        signed_payload = f"{timestamp}.".encode("utf-8") + body
        expected = hmac.new(
            secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        for candidate in candidates:
            if hmac.compare_digest(candidate, expected):
                # Stripe events have a unique id in the body but parsing
                # JSON here would couple us to the payload schema; rely
                # on the body hash as the dedup nonce instead so replay
                # of the same body always collides.
                body_hash = hashlib.sha256(body).hexdigest()
                return _VerifyResult(True, "ok", nonce=body_hash)
        return _VerifyResult(False, "Invalid signature")


class _SlackVerifier(_SignatureVerifier):
    """``X-Slack-Signature: v0=<hex>`` signed over ``v0:{ts}:{body}``.

    Slack also enforces a 5-minute window on ``X-Slack-Request-
    Timestamp``. The verifier checks both the signature and the
    window because Slack's docs explicitly call out replay risk.
    """

    name = "slack"
    _TOLERANCE_SECONDS = 300

    def verify(
        self,
        *,
        headers: Dict[str, str],
        body: bytes,
        secret: str,
        now: datetime,
    ) -> _VerifyResult:
        signature = headers.get("x-slack-signature", "")
        timestamp = headers.get("x-slack-request-timestamp", "")
        if not signature:
            return _VerifyResult(False, "Missing X-Slack-Signature header")
        if not timestamp:
            return _VerifyResult(False, "Missing X-Slack-Request-Timestamp header")
        if not signature.startswith("v0="):
            return _VerifyResult(False, "X-Slack-Signature must start with v0=")

        try:
            ts_float = float(timestamp)
            if not math.isfinite(ts_float):
                raise ValueError("non-finite timestamp")
        except ValueError:
            return _VerifyResult(False, "Slack timestamp not numeric")
        ts_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        age = (now - ts_dt).total_seconds()
        if age > self._TOLERANCE_SECONDS:
            return _VerifyResult(False, f"Slack timestamp too old ({int(age)}s)")
        if age < -60:
            return _VerifyResult(False, "Slack timestamp is in the future")

        signed_payload = f"v0:{timestamp}:".encode("utf-8") + body
        expected_hex = hmac.new(
            secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        candidate = signature[len("v0=") :]
        if not hmac.compare_digest(candidate, expected_hex):
            return _VerifyResult(False, "Invalid signature")
        # Slack ships its own delivery id in the X-Slack-Retry-Reason
        # / X-Slack-Retry-Num headers; the body hash is the safest
        # dedup nonce because retries reuse the same body.
        body_hash = hashlib.sha256(body).hexdigest()
        return _VerifyResult(True, "ok", nonce=body_hash)


_VERIFIERS: Dict[str, _SignatureVerifier] = {
    "generic": _GenericVerifier(),
    "github": _GitHubVerifier(),
    "gitlab": _GitLabVerifier(),
    "stripe": _StripeVerifier(),
    "slack": _SlackVerifier(),
}


def _get_verifier(provider: str) -> _SignatureVerifier:
    """Look up a verifier by provider name; falls back to generic."""
    return _VERIFIERS.get(provider, _VERIFIERS["generic"])


class WebhookReceiver:
    """Receives and validates webhook payloads from push-based sources.

    Registered on ALL workers (not just leader). Valid webhook events
    are forwarded via the on_webhook_event callback for pipeline
    processing by the leader.

    Signature validation is delegated to a provider-specific verifier
    (generic / github / gitlab / stripe / slack) selected via
    ``WebhookConfig.provider``. The receiver only owns timestamp
    rejection (for providers that ship a separate header), nonce
    deduplication, and dispatch.

    Args:
        sources: Source registry dict.
        on_webhook_event: Async callback invoked on valid webhook.
        redis_client: Optional async Redis client for cross-worker nonce
            deduplication. When ``None``, falls back to in-memory storage
            (suitable for dev mode / single worker).
    """

    def __init__(
        self,
        sources: Dict[str, Dict[str, Any]],
        on_webhook_event: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
        redis_client: Any = None,
    ) -> None:
        self._webhooks: Dict[str, WebhookConfig] = {}
        self._on_webhook_event = on_webhook_event

        # Select nonce backend
        if redis_client is not None:
            self._nonce_backend: _NonceBackend = _RedisNonceBackend(redis_client)
            logger.debug("Webhook nonce storage: Redis (cross-worker)")
        else:
            self._nonce_backend = _InMemoryNonceBackend()
            logger.debug(
                "Webhook nonce storage: in-memory (dev mode). "
                "Nonce state will not survive process restart."
            )

        # Collect webhook configs from sources
        for name, source_info in sources.items():
            config = source_info.get("config")
            if config and hasattr(config, "webhook") and config.webhook:
                self._webhooks[name] = config.webhook

    async def handle_webhook(
        self,
        source_name: str,
        headers: Dict[str, str],
        body: bytes,
    ) -> Dict[str, Any]:
        """Process an incoming webhook payload.

        Pipeline:
        1. Look up the registered :class:`WebhookConfig` for the source.
        2. Resolve the per-source secret from the configured env var.
        3. Dispatch signature verification to the provider-specific
           verifier (generic / github / gitlab / stripe / slack).
        4. (Generic only) Honor the legacy ``X-Webhook-Timestamp``
           5-minute window — providers that own their own window do
           that inside their verifier.
        5. Deduplicate by nonce (delivery id or body hash).
        6. Dispatch to the registered ``on_webhook_event`` callback
           and emit the ``fabric_webhook_received_total`` metric.

        Args:
            source_name: The registered source this webhook is for.
            headers: HTTP headers (case-insensitive lookup recommended).
            body: Raw request body bytes.

        Returns:
            Dict with accepted (bool) and reason (str).
        """
        from dataflow.fabric.metrics import get_fabric_metrics

        metrics = get_fabric_metrics()

        # Normalize headers to lowercase keys
        hdrs = {k.lower(): v for k, v in headers.items()}

        # 1. Validate source is registered
        webhook_config = self._webhooks.get(source_name)
        if webhook_config is None:
            metrics.record_webhook(source=source_name, accepted=False)
            return {
                "accepted": False,
                "reason": f"Source '{source_name}' has no webhook config",
            }

        # 2. Resolve the per-source secret
        secret = os.environ.get(webhook_config.secret_env, "")
        if not secret:
            # Log the source name ONLY — CodeQL's
            # ``py/clear-text-logging-sensitive-data`` rule flags any
            # attribute read whose name contains ``secret``, including
            # ``webhook_config.secret_env`` which stores the NAME of
            # an env var (e.g. ``"STRIPE_WEBHOOK_SECRET"``) and never
            # its value. Operators can derive the expected env var name
            # from the WebhookConfig for the source; omitting it from
            # the log keeps the rule clean while preserving the action
            # signal (which source's configuration is broken).
            logger.error(
                "Webhook secret env var not set for source '%s'",
                source_name,
            )
            metrics.record_webhook(source=source_name, accepted=False)
            return {"accepted": False, "reason": "Server configuration error"}

        # 3. Provider-specific signature verification
        verifier = _get_verifier(webhook_config.provider)
        now = datetime.now(timezone.utc)
        verify_result = verifier.verify(headers=hdrs, body=body, secret=secret, now=now)
        if not verify_result.accepted:
            logger.warning(
                "Webhook signature rejected for source '%s' (provider=%s): %s",
                source_name,
                verifier.name,
                verify_result.reason,
            )
            metrics.record_webhook(source=source_name, accepted=False)
            return {"accepted": False, "reason": verify_result.reason}

        # 4. Generic-only legacy timestamp window. Provider-specific
        # verifiers own their own window (Stripe / Slack); applying
        # the generic check on top would be redundant and would
        # falsely reject GitLab/GitHub deliveries that don't ship a
        # timestamp header at all.
        if verifier.name == "generic":
            timestamp_str = hdrs.get("x-webhook-timestamp", "")
            if timestamp_str:
                try:
                    ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    try:
                        ts_float = float(timestamp_str)
                        if not math.isfinite(ts_float):
                            metrics.record_webhook(source=source_name, accepted=False)
                            return {
                                "accepted": False,
                                "reason": "Invalid timestamp format",
                            }
                        ts = datetime.fromtimestamp(ts_float, tz=timezone.utc)
                    except (ValueError, OverflowError):
                        metrics.record_webhook(source=source_name, accepted=False)
                        return {
                            "accepted": False,
                            "reason": "Invalid timestamp format",
                        }

                age = (now - ts).total_seconds()
                if age > _MAX_TIMESTAMP_AGE_SECONDS:
                    metrics.record_webhook(source=source_name, accepted=False)
                    return {
                        "accepted": False,
                        "reason": (
                            f"Timestamp too old ({int(age)}s > "
                            f"{_MAX_TIMESTAMP_AGE_SECONDS}s)"
                        ),
                    }
                if age < -60:
                    metrics.record_webhook(source=source_name, accepted=False)
                    return {
                        "accepted": False,
                        "reason": "Timestamp is in the future",
                    }

        # 5. Nonce deduplication. The verifier picks the most reliable
        # nonce per provider (delivery id, event id, or body hash).
        nonce = verify_result.nonce
        if nonce:
            if await self._nonce_backend.contains(source_name, nonce):
                metrics.record_webhook(source=source_name, accepted=False)
                return {
                    "accepted": False,
                    "reason": "Duplicate delivery (nonce already seen)",
                }
            await self._nonce_backend.add(source_name, nonce)

        # 6. Dispatch to callback
        if self._on_webhook_event is not None:
            try:
                await self._on_webhook_event(source_name)
            except Exception:
                logger.exception("Webhook event handler failed for '%s'", source_name)

        logger.debug(
            "Accepted webhook for source '%s' (provider=%s)",
            source_name,
            verifier.name,
        )
        metrics.record_webhook(source=source_name, accepted=True)
        return {"accepted": True, "reason": "ok"}

    def get_registered_webhooks(self) -> Dict[str, WebhookConfig]:
        """Return all registered webhook configurations."""
        return dict(self._webhooks)

    @property
    def webhook_count(self) -> int:
        return len(self._webhooks)
