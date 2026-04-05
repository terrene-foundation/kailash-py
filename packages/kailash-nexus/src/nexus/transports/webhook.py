# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import collections
import hashlib
import hmac
import ipaddress
import logging
import socket
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from nexus.registry import HandlerDef, HandlerRegistry
from nexus.transports.base import Transport

logger = logging.getLogger(__name__)

__all__ = ["WebhookTransport", "DeliveryStatus", "WebhookDelivery"]

_BLOCKED_IPV4 = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]

_BLOCKED_IPV6 = [
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
]


def _is_blocked_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address falls within a blocked private range."""
    if isinstance(addr, ipaddress.IPv6Address):
        # Check IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1)
        mapped = addr.ipv4_mapped
        if mapped is not None:
            return any(mapped in net for net in _BLOCKED_IPV4)
        return any(addr in net for net in _BLOCKED_IPV6)
    return any(addr in net for net in _BLOCKED_IPV4)


def _validate_target_url(url: str) -> None:
    """Validate a webhook target URL to prevent SSRF attacks.

    Rejects URLs with non-HTTP schemes or hostnames that resolve to
    private/internal IP ranges, including IPv4-mapped IPv6 addresses.
    If DNS resolution fails (e.g. offline), the URL is allowed —
    delivery will fail at send time instead.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    try:
        for info in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
            addr = ipaddress.ip_address(info[4][0])
            if _is_blocked_address(addr):
                raise ValueError("Target URL resolves to blocked private address")
    except socket.gaierror:
        # DNS resolution may fail in offline/sandboxed environments.
        # Allow registration; delivery will fail at send time.
        logger.debug("Could not resolve hostname %r during SSRF check", hostname)


class DeliveryStatus(str, Enum):
    """Status of an outbound webhook delivery attempt."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass
class WebhookDelivery:
    """Tracks the state of an outbound webhook delivery.

    Each delivery has a unique ID, the target URL, payload, status,
    and retry metadata.
    """

    delivery_id: str
    handler_name: str
    payload: Dict[str, Any]
    target_url: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    max_attempts: int = 5
    last_error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None


class WebhookTransport(Transport):
    """Webhook transport for inbound webhook reception and outbound delivery.

    Receives inbound POST requests carrying webhook payloads, verifies
    HMAC-SHA256 signatures for authenticity, deduplicates via idempotency
    keys, and dispatches to registered handlers.

    Outbound delivery sends handler results to configured target URLs
    with retry logic and exponential backoff.

    Args:
        secret: Shared secret for HMAC-SHA256 signature verification.
            When set, every inbound request must include a valid signature
            header. When None, signature verification is skipped (not
            recommended for production).
        signature_header: Name of the HTTP header carrying the HMAC
            signature (default ``X-Webhook-Signature``).
        idempotency_header: Name of the HTTP header carrying the
            idempotency key for deduplication (default
            ``X-Idempotency-Key``).
        max_retries: Maximum number of retry attempts for outbound
            delivery (default 5).
        base_delay: Base delay in seconds for exponential backoff
            (default 1.0).
        max_delay: Maximum delay cap in seconds for backoff (default 60.0).
        idempotency_ttl: Seconds to retain processed idempotency keys
            before eviction (default 3600).
        max_idempotency_keys: Maximum number of idempotency keys to
            retain. Oldest keys are evicted when this limit is exceeded
            (default 10000).
    """

    def __init__(
        self,
        *,
        secret: Optional[str] = None,
        signature_header: str = "X-Webhook-Signature",
        idempotency_header: str = "X-Idempotency-Key",
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        idempotency_ttl: float = 3600.0,
        max_idempotency_keys: int = 10000,
        max_deliveries: int = 10000,
    ):
        self._secret = secret
        self._signature_header = signature_header
        self._idempotency_header = idempotency_header
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._idempotency_ttl = idempotency_ttl
        self._max_idempotency_keys = max_idempotency_keys
        self._max_deliveries = max_deliveries

        self._running = False
        self._registry: Optional[HandlerRegistry] = None
        self._handler_map: Dict[str, HandlerDef] = {}

        # Idempotency tracking: key -> (timestamp, cached_response)
        self._processed_keys: Dict[str, tuple[float, Dict[str, Any]]] = {}

        # Outbound delivery tracking: delivery_id -> WebhookDelivery
        self._deliveries: Dict[str, WebhookDelivery] = {}

        # Outbound target URLs per handler: handler_name -> [urls]
        self._target_urls: Dict[str, List[str]] = {}

    # -- Transport protocol ------------------------------------------------

    @property
    def name(self) -> str:
        return "webhook"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, registry: HandlerRegistry) -> None:
        """Start the webhook transport.

        Reads all registered handlers from the registry and builds the
        internal dispatch map.
        """
        if self._running:
            return

        self._registry = registry

        for handler_def in registry.list_handlers():
            self._handler_map[handler_def.name] = handler_def

        self._running = True
        logger.info("WebhookTransport started")

    async def stop(self) -> None:
        """Stop the webhook transport and clear internal state."""
        self._running = False
        self._handler_map.clear()
        self._processed_keys.clear()
        logger.info("WebhookTransport stopped")

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        """Hot-register a handler added while the transport is running."""
        if self._running:
            self._handler_map[handler_def.name] = handler_def
            logger.debug(f"Webhook handler hot-registered: {handler_def.name}")

    # -- Signature verification --------------------------------------------

    def compute_signature(self, payload_bytes: bytes) -> str:
        """Compute HMAC-SHA256 signature for a payload.

        Args:
            payload_bytes: Raw request body bytes.

        Returns:
            Hex-encoded HMAC-SHA256 digest prefixed with ``sha256=``.

        Raises:
            ValueError: If no secret is configured.
        """
        if self._secret is None:
            raise ValueError(
                "Cannot compute signature: no secret configured. "
                "Set the 'secret' parameter on WebhookTransport."
            )
        mac = hmac.new(
            self._secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        )
        return f"sha256={mac.hexdigest()}"

    def verify_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """Verify an inbound webhook signature.

        Uses constant-time comparison to prevent timing attacks.

        Args:
            payload_bytes: Raw request body bytes.
            signature: The signature value from the request header,
                expected in ``sha256=<hex>`` format.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if self._secret is None:
            # No secret configured — verification is vacuously true
            return True

        expected = self.compute_signature(payload_bytes)
        return hmac.compare_digest(expected, signature)

    # -- Idempotency -------------------------------------------------------

    def _evict_expired_keys(self) -> None:
        """Remove idempotency keys that have exceeded their TTL."""
        now = time.time()
        expired = [
            key
            for key, (ts, _) in self._processed_keys.items()
            if (now - ts) >= self._idempotency_ttl
        ]
        for key in expired:
            del self._processed_keys[key]

        # If still over limit, evict oldest
        if len(self._processed_keys) > self._max_idempotency_keys:
            sorted_keys = sorted(
                self._processed_keys.items(), key=lambda item: item[1][0]
            )
            excess = len(self._processed_keys) - self._max_idempotency_keys
            for key, _ in sorted_keys[:excess]:
                del self._processed_keys[key]

    def is_duplicate(self, idempotency_key: Optional[str]) -> bool:
        """Check whether an idempotency key has already been processed.

        Args:
            idempotency_key: The idempotency key from the request header.
                If None, the request is never considered a duplicate.

        Returns:
            True if the key was previously processed and the cached
            response is available.
        """
        if idempotency_key is None:
            return False
        self._evict_expired_keys()
        return idempotency_key in self._processed_keys

    def get_cached_response(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve the cached response for a previously processed key.

        Args:
            idempotency_key: The idempotency key.

        Returns:
            The cached response dict, or None if not found.
        """
        entry = self._processed_keys.get(idempotency_key)
        if entry is not None:
            return entry[1]
        return None

    def _record_processed(self, idempotency_key: str, response: Dict[str, Any]) -> None:
        """Record a processed idempotency key with its response."""
        self._processed_keys[idempotency_key] = (time.time(), response)

    # -- Inbound dispatch --------------------------------------------------

    async def receive(
        self,
        handler_name: str,
        payload: Dict[str, Any],
        payload_bytes: Optional[bytes] = None,
        signature: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process an inbound webhook request.

        This is the primary entry point for inbound webhooks. It
        performs signature verification, idempotency deduplication,
        and dispatches to the target handler.

        Args:
            handler_name: Name of the handler to dispatch to.
            payload: Parsed JSON payload.
            payload_bytes: Raw request body bytes (required when
                signature verification is enabled).
            signature: Value from the signature header.
            idempotency_key: Value from the idempotency header.

        Returns:
            Dict with ``status``, ``handler``, and ``result`` keys.

        Raises:
            ValueError: If signature verification fails or the handler
                is not found.
            RuntimeError: If the transport is not running.
        """
        if not self._running:
            raise RuntimeError("WebhookTransport is not running")

        # Signature verification
        if self._secret is not None:
            if signature is None:
                raise ValueError(
                    f"Missing signature header '{self._signature_header}'. "
                    "All inbound webhooks must be signed when a secret is configured."
                )
            if payload_bytes is None:
                raise ValueError("payload_bytes is required for signature verification")
            if not self.verify_signature(payload_bytes, signature):
                raise ValueError("Invalid webhook signature")

        # Idempotency deduplication
        if self.is_duplicate(idempotency_key):
            cached = self.get_cached_response(idempotency_key)
            if cached is not None:
                logger.debug(
                    f"Duplicate webhook request (key={idempotency_key}), "
                    "returning cached response"
                )
                return cached

        # Dispatch to handler
        handler_def = self._handler_map.get(handler_name)
        if handler_def is None:
            raise ValueError(
                f"Handler '{handler_name}' not found in webhook transport. "
                f"Available handlers: {list(self._handler_map.keys())}"
            )

        if handler_def.func is None:
            raise ValueError(
                f"Handler '{handler_name}' has no callable function. "
                "Workflow-only handlers cannot receive webhooks directly."
            )

        # Call the handler
        import asyncio
        import inspect

        func = handler_def.func
        if inspect.iscoroutinefunction(func):
            result = await func(**payload)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: func(**payload))

        response = {
            "status": "ok",
            "handler": handler_name,
            "result": result,
        }

        # Record for idempotency
        if idempotency_key is not None:
            self._record_processed(idempotency_key, response)

        return response

    # -- Outbound delivery -------------------------------------------------

    def register_target(self, handler_name: str, url: str) -> None:
        """Register a target URL for outbound webhook delivery.

        When a handler produces a result, it can be delivered to one
        or more target URLs.

        Args:
            handler_name: The handler whose results should be delivered.
            url: The target URL to POST results to.

        Raises:
            ValueError: If the URL resolves to a private/internal address (SSRF prevention).
        """
        _validate_target_url(url)
        if handler_name not in self._target_urls:
            self._target_urls[handler_name] = []
        if url not in self._target_urls[handler_name]:
            self._target_urls[handler_name].append(url)

    def unregister_target(self, handler_name: str, url: str) -> None:
        """Remove a target URL for outbound delivery.

        Args:
            handler_name: The handler name.
            url: The target URL to remove.
        """
        urls = self._target_urls.get(handler_name, [])
        if url in urls:
            urls.remove(url)

    async def deliver(
        self,
        handler_name: str,
        payload: Dict[str, Any],
        target_url: str,
        send_func: Optional[Callable] = None,
    ) -> WebhookDelivery:
        """Deliver a payload to a target URL with retry and backoff.

        By default, uses an HTTP POST via the stdlib. A custom
        ``send_func`` can be provided for testing or custom transports.

        The ``send_func`` signature is::

            async def send_func(url: str, body: bytes, headers: dict) -> int:
                # Return HTTP status code

        Status codes 2xx are treated as success. 4xx (except 429) are
        permanent failures (no retry). 429 and 5xx trigger retries.

        Args:
            handler_name: Name of the handler that produced the payload.
            payload: The payload dict to deliver.
            target_url: The URL to POST to.
            send_func: Optional async callable for sending. If None, uses
                urllib (not recommended for production; provide an
                httpx/aiohttp sender).

        Returns:
            A WebhookDelivery tracking the delivery outcome.

        Raises:
            ValueError: If the URL resolves to a private/internal address (SSRF prevention).
        """
        _validate_target_url(target_url)

        import json

        delivery = WebhookDelivery(
            delivery_id=str(uuid.uuid4()),
            handler_name=handler_name,
            payload=payload,
            target_url=target_url,
            max_attempts=self._max_retries,
        )
        self._deliveries[delivery.delivery_id] = delivery

        # Evict oldest deliveries if over limit (H1: bounded collection)
        while len(self._deliveries) > self._max_deliveries:
            oldest_key = next(iter(self._deliveries))
            del self._deliveries[oldest_key]

        body = json.dumps(payload).encode("utf-8")
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if self._secret is not None:
            sig = self.compute_signature(body)
            headers[self._signature_header] = sig

        sender = send_func or self._default_send

        for attempt in range(1, self._max_retries + 1):
            delivery.attempts = attempt
            try:
                status_code = await sender(target_url, body, headers)

                if 200 <= status_code < 300:
                    delivery.status = DeliveryStatus.DELIVERED
                    delivery.delivered_at = time.time()
                    logger.info(
                        f"Webhook delivered: {delivery.delivery_id} "
                        f"to {target_url} (attempt {attempt})"
                    )
                    return delivery

                if 400 <= status_code < 500 and status_code != 429:
                    # Permanent client error — do not retry
                    delivery.status = DeliveryStatus.FAILED
                    delivery.last_error = f"Permanent failure: HTTP {status_code}"
                    logger.warning(
                        f"Webhook delivery failed permanently: "
                        f"{delivery.delivery_id} HTTP {status_code}"
                    )
                    return delivery

                # Retryable server error or 429
                delivery.last_error = f"HTTP {status_code}"

            except Exception as exc:
                delivery.last_error = str(exc)
                logger.warning(
                    f"Webhook delivery attempt {attempt} failed: "
                    f"{delivery.delivery_id} - {exc}"
                )

            # Exponential backoff with cap
            if attempt < self._max_retries:
                delay = min(
                    self._base_delay * (2 ** (attempt - 1)),
                    self._max_delay,
                )
                await asyncio.sleep(delay)

        # Exhausted retries
        delivery.status = DeliveryStatus.FAILED
        logger.error(
            f"Webhook delivery failed after {self._max_retries} attempts: "
            f"{delivery.delivery_id} to {target_url}"
        )
        return delivery

    def get_delivery(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """Look up a delivery by ID.

        Args:
            delivery_id: The unique delivery identifier.

        Returns:
            The WebhookDelivery, or None if not found.
        """
        return self._deliveries.get(delivery_id)

    def list_deliveries(
        self,
        *,
        handler_name: Optional[str] = None,
        status: Optional[DeliveryStatus] = None,
    ) -> List[WebhookDelivery]:
        """List deliveries, optionally filtered.

        Args:
            handler_name: Filter by handler name.
            status: Filter by delivery status.

        Returns:
            List of matching WebhookDelivery records.
        """
        results: List[WebhookDelivery] = []
        for delivery in self._deliveries.values():
            if handler_name is not None and delivery.handler_name != handler_name:
                continue
            if status is not None and delivery.status != status:
                continue
            results.append(delivery)
        return results

    # -- Health / diagnostics -----------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Webhook transport health status."""
        total_deliveries = len(self._deliveries)
        delivered = sum(
            1 for d in self._deliveries.values() if d.status == DeliveryStatus.DELIVERED
        )
        failed = sum(
            1 for d in self._deliveries.values() if d.status == DeliveryStatus.FAILED
        )
        pending = sum(
            1 for d in self._deliveries.values() if d.status == DeliveryStatus.PENDING
        )
        return {
            "transport": "webhook",
            "running": self._running,
            "handlers": len(self._handler_map),
            "idempotency_keys": len(self._processed_keys),
            "deliveries": {
                "total": total_deliveries,
                "delivered": delivered,
                "failed": failed,
                "pending": pending,
            },
            "signature_verification": self._secret is not None,
        }

    # -- Internal -----------------------------------------------------------

    @staticmethod
    async def _default_send(url: str, body: bytes, headers: Dict[str, str]) -> int:
        """Fallback sender using urllib (synchronous, for dev/testing).

        Production deployments should provide an httpx or aiohttp sender
        via the ``send_func`` parameter of :meth:`deliver`.
        """
        import urllib.request
        import urllib.error

        loop = asyncio.get_event_loop()

        def _do_send() -> int:
            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.status
            except urllib.error.HTTPError as e:
                return e.code

        return await loop.run_in_executor(None, _do_send)
