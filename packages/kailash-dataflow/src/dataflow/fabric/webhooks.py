# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Webhook Receiver — push-based source change detection.

Validates HMAC signatures (constant-time), rejects stale timestamps,
deduplicates via nonce tracking. All workers accept webhooks; only the
leader processes them (RT-2 resolution).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Optional

from dataflow.fabric.config import WebhookConfig

logger = logging.getLogger(__name__)

__all__ = ["WebhookReceiver"]

_MAX_TIMESTAMP_AGE_SECONDS = 300  # 5 minutes (doc 01-redteam H1)
_MAX_NONCE_ENTRIES = 10_000


class _BoundedNonceSet:
    """LRU-evicting set for nonce deduplication, bounded to prevent OOM."""

    def __init__(self, maxsize: int = _MAX_NONCE_ENTRIES) -> None:
        self._store: OrderedDict[str, float] = OrderedDict()
        self._maxsize = maxsize

    def contains(self, nonce: str) -> bool:
        return nonce in self._store

    def add(self, nonce: str) -> None:
        if nonce in self._store:
            self._store.move_to_end(nonce)
            return
        if len(self._store) >= self._maxsize:
            self._store.popitem(last=False)  # Evict oldest
        self._store[nonce] = time.monotonic()

    def __len__(self) -> int:
        return len(self._store)


class WebhookReceiver:
    """Receives and validates webhook payloads from push-based sources.

    Registered on ALL workers (not just leader). Valid webhook events
    are forwarded via the on_webhook_event callback for pipeline
    processing by the leader.
    """

    def __init__(
        self,
        sources: Dict[str, Dict[str, Any]],
        on_webhook_event: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
    ) -> None:
        self._webhooks: Dict[str, WebhookConfig] = {}
        self._on_webhook_event = on_webhook_event
        self._nonces = _BoundedNonceSet()

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

        Args:
            source_name: The registered source this webhook is for.
            headers: HTTP headers (case-insensitive lookup recommended).
            body: Raw request body bytes.

        Returns:
            Dict with accepted (bool) and reason (str).
        """
        # Normalize headers to lowercase keys
        hdrs = {k.lower(): v for k, v in headers.items()}

        # 1. Validate source is registered
        webhook_config = self._webhooks.get(source_name)
        if webhook_config is None:
            return {
                "accepted": False,
                "reason": f"Source '{source_name}' has no webhook config",
            }

        # 2. HMAC signature validation
        signature = hdrs.get("x-webhook-signature", "")
        if not signature:
            return {"accepted": False, "reason": "Missing X-Webhook-Signature header"}

        secret = os.environ.get(webhook_config.secret_env, "")
        if not secret:
            logger.error(
                "Webhook secret env var '%s' not set for source '%s'",
                webhook_config.secret_env,
                source_name,
            )
            return {"accepted": False, "reason": "Server configuration error"}

        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        # MUST use compare_digest — NEVER == (trust-plane-security.md)
        if not hmac.compare_digest(signature, expected):
            logger.warning("Invalid webhook signature for source '%s'", source_name)
            return {"accepted": False, "reason": "Invalid signature"}

        # 3. Timestamp validation (H1: reject > 5 minutes old)
        timestamp_str = hdrs.get("x-webhook-timestamp", "")
        if timestamp_str:
            try:
                # Try ISO-8601 first
                ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    # Try Unix timestamp
                    ts = datetime.fromtimestamp(float(timestamp_str), tz=timezone.utc)
                except (ValueError, OverflowError):
                    return {"accepted": False, "reason": "Invalid timestamp format"}

            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > _MAX_TIMESTAMP_AGE_SECONDS:
                return {
                    "accepted": False,
                    "reason": f"Timestamp too old ({int(age)}s > {_MAX_TIMESTAMP_AGE_SECONDS}s)",
                }
            if age < -60:  # Allow 1 minute clock skew into future
                return {"accepted": False, "reason": "Timestamp is in the future"}

        # 4. Nonce deduplication
        nonce = hdrs.get("x-webhook-delivery-id", "")
        if nonce:
            if self._nonces.contains(nonce):
                return {
                    "accepted": False,
                    "reason": "Duplicate delivery (nonce already seen)",
                }
            self._nonces.add(nonce)

        # 5. Dispatch to callback
        if self._on_webhook_event is not None:
            try:
                await self._on_webhook_event(source_name)
            except Exception:
                logger.exception("Webhook event handler failed for '%s'", source_name)

        logger.debug("Accepted webhook for source '%s'", source_name)
        return {"accepted": True, "reason": "ok"}

    def get_registered_webhooks(self) -> Dict[str, WebhookConfig]:
        """Return all registered webhook configurations."""
        return dict(self._webhooks)

    @property
    def webhook_count(self) -> int:
        return len(self._webhooks)
