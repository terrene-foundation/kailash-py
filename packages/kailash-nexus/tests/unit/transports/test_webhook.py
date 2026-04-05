# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for WebhookTransport.

Tests signature verification, delivery retry logic, idempotency
deduplication, inbound dispatch, and error handling.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from nexus.registry import HandlerDef, HandlerParam, HandlerRegistry
from nexus.transports.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookTransport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def secret():
    return "test-webhook-secret-key"


@pytest.fixture
def transport(secret):
    return WebhookTransport(secret=secret)


@pytest.fixture
def transport_no_secret():
    return WebhookTransport()


@pytest.fixture
def registry():
    return HandlerRegistry()


def _make_signature(secret: str, payload_bytes: bytes) -> str:
    """Compute the expected HMAC-SHA256 signature for test assertions."""
    mac = hmac_mod.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


# ---------------------------------------------------------------------------
# Transport protocol basics
# ---------------------------------------------------------------------------


class TestWebhookTransportProtocol:
    """Tests for Transport ABC compliance."""

    def test_name(self, transport):
        assert transport.name == "webhook"

    def test_not_running_initially(self, transport):
        assert transport.is_running is False

    @pytest.mark.asyncio
    async def test_start_sets_running(self, transport, registry):
        await transport.start(registry)
        assert transport.is_running is True

    @pytest.mark.asyncio
    async def test_start_idempotent(self, transport, registry):
        await transport.start(registry)
        await transport.start(registry)  # Should not raise
        assert transport.is_running is True

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, transport, registry):
        await transport.start(registry)
        await transport.stop()
        assert transport.is_running is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, transport, registry):
        await transport.start(registry)
        await transport.stop()
        await transport.stop()  # Should not raise
        assert transport.is_running is False

    @pytest.mark.asyncio
    async def test_start_loads_handlers(self, transport, registry):
        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet, description="Greet")
        await transport.start(registry)
        assert "greet" in transport._handler_map

    def test_on_handler_registered_when_not_running(self, transport):
        hd = HandlerDef(name="test", func=lambda x: x)
        transport.on_handler_registered(hd)  # Should not raise
        assert "test" not in transport._handler_map

    @pytest.mark.asyncio
    async def test_on_handler_registered_when_running(self, transport, registry):
        await transport.start(registry)
        hd = HandlerDef(name="late_handler", func=lambda x: x)
        transport.on_handler_registered(hd)
        assert "late_handler" in transport._handler_map


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    """Tests for HMAC-SHA256 signature computation and verification."""

    def test_compute_signature(self, transport, secret):
        payload = b'{"event": "test"}'
        sig = transport.compute_signature(payload)
        assert sig.startswith("sha256=")
        expected = _make_signature(secret, payload)
        assert sig == expected

    def test_compute_signature_no_secret_raises(self, transport_no_secret):
        with pytest.raises(ValueError, match="no secret configured"):
            transport_no_secret.compute_signature(b"test")

    def test_verify_valid_signature(self, transport, secret):
        payload = b'{"event": "user.created"}'
        sig = _make_signature(secret, payload)
        assert transport.verify_signature(payload, sig) is True

    def test_verify_invalid_signature(self, transport):
        payload = b'{"event": "user.created"}'
        assert transport.verify_signature(payload, "sha256=invalid") is False

    def test_verify_wrong_payload(self, transport, secret):
        payload = b'{"event": "user.created"}'
        sig = _make_signature(secret, payload)
        tampered = b'{"event": "user.deleted"}'
        assert transport.verify_signature(tampered, sig) is False

    def test_verify_no_secret_always_true(self, transport_no_secret):
        """Without a secret, verification is vacuously true."""
        assert transport_no_secret.verify_signature(b"anything", "sha256=bogus") is True

    def test_signature_deterministic(self, transport):
        payload = b"consistent"
        sig1 = transport.compute_signature(payload)
        sig2 = transport.compute_signature(payload)
        assert sig1 == sig2

    def test_different_payloads_different_signatures(self, transport):
        sig1 = transport.compute_signature(b"payload_a")
        sig2 = transport.compute_signature(b"payload_b")
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# Idempotency deduplication
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Tests for request deduplication via idempotency keys."""

    def test_none_key_never_duplicate(self, transport):
        assert transport.is_duplicate(None) is False

    def test_new_key_not_duplicate(self, transport):
        assert transport.is_duplicate("key-1") is False

    def test_processed_key_is_duplicate(self, transport):
        response = {"status": "ok", "result": 42}
        transport._record_processed("key-1", response)
        assert transport.is_duplicate("key-1") is True

    def test_cached_response_returned(self, transport):
        response = {"status": "ok", "handler": "greet", "result": {"msg": "hi"}}
        transport._record_processed("key-2", response)
        cached = transport.get_cached_response("key-2")
        assert cached == response

    def test_cached_response_none_for_unknown(self, transport):
        assert transport.get_cached_response("unknown") is None

    def test_ttl_eviction(self, transport):
        """Keys older than TTL are evicted."""
        transport._idempotency_ttl = 0.0  # Immediate expiry
        transport._record_processed("old-key", {"status": "ok"})
        # After eviction check, old key should be gone
        assert transport.is_duplicate("old-key") is False

    def test_max_keys_eviction(self):
        """Oldest keys are evicted when the limit is exceeded."""
        t = WebhookTransport(max_idempotency_keys=3, idempotency_ttl=3600.0)
        for i in range(5):
            t._processed_keys[f"key-{i}"] = (
                time.time() + i * 0.001,
                {"i": i},
            )
        # Trigger eviction via is_duplicate
        t.is_duplicate("trigger")
        assert len(t._processed_keys) <= 3


# ---------------------------------------------------------------------------
# Inbound dispatch
# ---------------------------------------------------------------------------


class TestInboundReceive:
    """Tests for the receive() inbound webhook handler."""

    @pytest.mark.asyncio
    async def test_receive_not_running_raises(self, transport):
        with pytest.raises(RuntimeError, match="not running"):
            await transport.receive("greet", {"name": "Alice"})

    @pytest.mark.asyncio
    async def test_receive_missing_signature_raises(self, transport, registry):
        """When secret is set, missing signature is rejected."""

        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)

        with pytest.raises(ValueError, match="Missing signature"):
            await transport.receive("greet", {"name": "Alice"})

    @pytest.mark.asyncio
    async def test_receive_invalid_signature_raises(self, transport, registry, secret):
        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)

        payload = {"name": "Alice"}
        payload_bytes = json.dumps(payload).encode("utf-8")

        with pytest.raises(ValueError, match="Invalid webhook signature"):
            await transport.receive(
                "greet",
                payload,
                payload_bytes=payload_bytes,
                signature="sha256=badbadbadbad",
            )

    @pytest.mark.asyncio
    async def test_receive_missing_payload_bytes_raises(self, transport, registry):
        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)

        with pytest.raises(ValueError, match="payload_bytes is required"):
            await transport.receive(
                "greet",
                {"name": "Alice"},
                signature="sha256=something",
            )

    @pytest.mark.asyncio
    async def test_receive_valid_signature_dispatches(
        self, transport, registry, secret
    ):
        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)

        payload = {"name": "Alice"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        sig = _make_signature(secret, payload_bytes)

        result = await transport.receive(
            "greet",
            payload,
            payload_bytes=payload_bytes,
            signature=sig,
        )
        assert result["status"] == "ok"
        assert result["handler"] == "greet"
        assert result["result"]["message"] == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_receive_no_secret_skips_verification(
        self, transport_no_secret, registry
    ):
        """Without a secret, signature verification is skipped entirely."""

        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport_no_secret.start(registry)

        result = await transport_no_secret.receive("greet", {"name": "Bob"})
        assert result["status"] == "ok"
        assert result["result"]["message"] == "Hello, Bob!"

    @pytest.mark.asyncio
    async def test_receive_unknown_handler_raises(self, transport_no_secret, registry):
        await transport_no_secret.start(registry)
        with pytest.raises(ValueError, match="not found"):
            await transport_no_secret.receive("nonexistent", {"key": "val"})

    @pytest.mark.asyncio
    async def test_receive_handler_no_func_raises(self, transport_no_secret, registry):
        """Handlers with func=None (workflow-only) cannot receive webhooks."""
        await transport_no_secret.start(registry)
        # Manually insert a handler without a function
        transport_no_secret._handler_map["wf_only"] = HandlerDef(
            name="wf_only", func=None
        )

        with pytest.raises(ValueError, match="no callable function"):
            await transport_no_secret.receive("wf_only", {"key": "val"})

    @pytest.mark.asyncio
    async def test_receive_sync_handler(self, transport_no_secret, registry):
        """Synchronous handler functions are executed in an executor."""

        def sync_greet(name: str) -> dict:
            return {"message": f"Sync Hello, {name}!"}

        registry.register_handler("sync_greet", sync_greet)
        await transport_no_secret.start(registry)

        result = await transport_no_secret.receive("sync_greet", {"name": "Eve"})
        assert result["status"] == "ok"
        assert result["result"]["message"] == "Sync Hello, Eve!"

    @pytest.mark.asyncio
    async def test_receive_idempotency_returns_cached(
        self, transport_no_secret, registry
    ):
        """Duplicate requests with the same idempotency key return cached responses."""
        call_count = 0

        async def counter(name: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        registry.register_handler("counter", counter)
        await transport_no_secret.start(registry)

        # First call
        r1 = await transport_no_secret.receive(
            "counter", {"name": "A"}, idempotency_key="idem-1"
        )
        assert r1["result"]["count"] == 1
        assert call_count == 1

        # Second call with same key — should return cached, not call handler
        r2 = await transport_no_secret.receive(
            "counter", {"name": "A"}, idempotency_key="idem-1"
        )
        assert r2["result"]["count"] == 1
        assert call_count == 1  # Handler NOT called again

    @pytest.mark.asyncio
    async def test_receive_different_idempotency_keys(
        self, transport_no_secret, registry
    ):
        """Different idempotency keys dispatch independently."""
        call_count = 0

        async def counter(name: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        registry.register_handler("counter", counter)
        await transport_no_secret.start(registry)

        await transport_no_secret.receive(
            "counter", {"name": "A"}, idempotency_key="k1"
        )
        await transport_no_secret.receive(
            "counter", {"name": "B"}, idempotency_key="k2"
        )
        assert call_count == 2


# ---------------------------------------------------------------------------
# Outbound delivery and retry logic
# ---------------------------------------------------------------------------


class TestOutboundDelivery:
    """Tests for outbound webhook delivery with retry and backoff."""

    @pytest.mark.asyncio
    async def test_deliver_success_on_first_attempt(self, transport):
        async def mock_send(url, body, headers):
            return 200

        delivery = await transport.deliver(
            "handler_a",
            {"event": "created"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 1
        assert delivery.delivered_at is not None
        assert delivery.last_error is None

    @pytest.mark.asyncio
    async def test_deliver_retries_on_500(self, transport):
        """Server errors trigger retries with eventual success."""
        attempts = []

        async def mock_send(url, body, headers):
            attempts.append(1)
            if len(attempts) < 3:
                return 500
            return 200

        # Use small delays for test speed
        transport._base_delay = 0.001
        transport._max_delay = 0.01

        delivery = await transport.deliver(
            "handler_a",
            {"event": "updated"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 3

    @pytest.mark.asyncio
    async def test_deliver_retries_on_429(self, transport):
        """429 Too Many Requests triggers retries."""
        attempts = []

        async def mock_send(url, body, headers):
            attempts.append(1)
            if len(attempts) < 2:
                return 429
            return 200

        transport._base_delay = 0.001

        delivery = await transport.deliver(
            "handler_a",
            {"event": "rate_limited"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 2

    @pytest.mark.asyncio
    async def test_deliver_permanent_failure_on_4xx(self, transport):
        """4xx errors (except 429) are permanent failures — no retry."""
        call_count = 0

        async def mock_send(url, body, headers):
            nonlocal call_count
            call_count += 1
            return 404

        delivery = await transport.deliver(
            "handler_a",
            {"event": "not_found"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1
        assert call_count == 1
        assert "Permanent failure" in delivery.last_error

    @pytest.mark.asyncio
    async def test_deliver_exhausted_retries(self, transport):
        """All retries exhausted results in FAILED status."""

        async def mock_send(url, body, headers):
            return 503

        transport._base_delay = 0.001
        transport._max_retries = 3

        delivery = await transport.deliver(
            "handler_a",
            {"event": "always_fail"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 3

    @pytest.mark.asyncio
    async def test_deliver_exception_triggers_retry(self, transport):
        """Network exceptions trigger retries."""
        attempts = []

        async def mock_send(url, body, headers):
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("Connection refused")
            return 200

        transport._base_delay = 0.001

        delivery = await transport.deliver(
            "handler_a",
            {"event": "network_error"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 2

    @pytest.mark.asyncio
    async def test_deliver_includes_signature_header(self, transport, secret):
        """Outbound deliveries include signature when secret is configured."""
        captured_headers = {}

        async def mock_send(url, body, headers):
            captured_headers.update(headers)
            return 200

        await transport.deliver(
            "handler_a",
            {"event": "signed"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert "X-Webhook-Signature" in captured_headers
        assert captured_headers["X-Webhook-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_deliver_no_signature_without_secret(self, transport_no_secret):
        """No signature header when no secret is configured."""
        captured_headers = {}

        async def mock_send(url, body, headers):
            captured_headers.update(headers)
            return 200

        await transport_no_secret.deliver(
            "handler_a",
            {"event": "unsigned"},
            "https://example.com/hook",
            send_func=mock_send,
        )
        assert "X-Webhook-Signature" not in captured_headers

    @pytest.mark.asyncio
    async def test_deliver_backoff_capped_at_max_delay(self):
        """Backoff delay never exceeds max_delay."""
        t = WebhookTransport(
            base_delay=10.0,
            max_delay=0.05,
            max_retries=3,
        )
        delays = []
        original_sleep = asyncio.sleep

        async def track_sleep(duration):
            delays.append(duration)
            # Do not actually sleep in tests

        async def mock_send(url, body, headers):
            return 500

        with patch("nexus.transports.webhook.asyncio.sleep", side_effect=track_sleep):
            await t.deliver(
                "handler_a",
                {"event": "backoff_test"},
                "https://example.com/hook",
                send_func=mock_send,
            )

        # All delays should be capped at max_delay
        for d in delays:
            assert d <= 0.05


# ---------------------------------------------------------------------------
# Delivery tracking
# ---------------------------------------------------------------------------


class TestDeliveryTracking:
    """Tests for delivery lookup and listing."""

    @pytest.mark.asyncio
    async def test_get_delivery(self, transport):
        async def mock_send(url, body, headers):
            return 200

        delivery = await transport.deliver(
            "h", {"k": "v"}, "https://example.com/hook", send_func=mock_send
        )
        found = transport.get_delivery(delivery.delivery_id)
        assert found is delivery

    def test_get_delivery_not_found(self, transport):
        assert transport.get_delivery("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_deliveries_all(self, transport):
        async def ok_send(url, body, headers):
            return 200

        async def fail_send(url, body, headers):
            return 404

        transport._base_delay = 0.001
        await transport.deliver("h1", {"a": 1}, "https://a.com", send_func=ok_send)
        await transport.deliver("h2", {"b": 2}, "https://b.com", send_func=fail_send)

        all_deliveries = transport.list_deliveries()
        assert len(all_deliveries) == 2

    @pytest.mark.asyncio
    async def test_list_deliveries_filtered_by_status(self, transport):
        async def ok_send(url, body, headers):
            return 200

        async def fail_send(url, body, headers):
            return 404

        await transport.deliver("h1", {"a": 1}, "https://a.com", send_func=ok_send)
        await transport.deliver("h2", {"b": 2}, "https://b.com", send_func=fail_send)

        delivered = transport.list_deliveries(status=DeliveryStatus.DELIVERED)
        failed = transport.list_deliveries(status=DeliveryStatus.FAILED)
        assert len(delivered) == 1
        assert len(failed) == 1
        assert delivered[0].handler_name == "h1"
        assert failed[0].handler_name == "h2"

    @pytest.mark.asyncio
    async def test_list_deliveries_filtered_by_handler(self, transport):
        async def ok_send(url, body, headers):
            return 200

        await transport.deliver("h1", {"a": 1}, "https://a.com", send_func=ok_send)
        await transport.deliver("h2", {"b": 2}, "https://b.com", send_func=ok_send)

        h1_only = transport.list_deliveries(handler_name="h1")
        assert len(h1_only) == 1
        assert h1_only[0].handler_name == "h1"


# ---------------------------------------------------------------------------
# Target URL management
# ---------------------------------------------------------------------------


class TestTargetRegistration:
    """Tests for outbound target URL management."""

    def test_register_target(self, transport):
        transport.register_target("handler_a", "https://a.com/hook")
        assert "https://a.com/hook" in transport._target_urls["handler_a"]

    def test_register_target_deduplicates(self, transport):
        transport.register_target("handler_a", "https://a.com/hook")
        transport.register_target("handler_a", "https://a.com/hook")
        assert len(transport._target_urls["handler_a"]) == 1

    def test_register_multiple_targets(self, transport):
        transport.register_target("handler_a", "https://a.com/hook")
        transport.register_target("handler_a", "https://b.com/hook")
        assert len(transport._target_urls["handler_a"]) == 2

    def test_unregister_target(self, transport):
        transport.register_target("handler_a", "https://a.com/hook")
        transport.unregister_target("handler_a", "https://a.com/hook")
        assert len(transport._target_urls["handler_a"]) == 0

    def test_unregister_nonexistent_target(self, transport):
        """Unregistering a URL that was never registered does not raise."""
        transport.unregister_target("handler_a", "https://a.com/hook")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for the health_check() diagnostics."""

    def test_health_check_not_running(self, transport):
        health = transport.health_check()
        assert health["transport"] == "webhook"
        assert health["running"] is False
        assert health["handlers"] == 0
        assert health["signature_verification"] is True
        assert health["deliveries"]["total"] == 0

    def test_health_check_no_secret(self, transport_no_secret):
        health = transport_no_secret.health_check()
        assert health["signature_verification"] is False

    @pytest.mark.asyncio
    async def test_health_check_running_with_handlers(self, transport, registry):
        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)

        health = transport.health_check()
        assert health["running"] is True
        assert health["handlers"] == 1

    @pytest.mark.asyncio
    async def test_health_check_delivery_counts(self, transport):
        async def ok_send(url, body, headers):
            return 200

        async def fail_send(url, body, headers):
            return 404

        await transport.deliver("h1", {"a": 1}, "https://a.com", send_func=ok_send)
        await transport.deliver("h2", {"b": 2}, "https://b.com", send_func=fail_send)

        health = transport.health_check()
        assert health["deliveries"]["total"] == 2
        assert health["deliveries"]["delivered"] == 1
        assert health["deliveries"]["failed"] == 1
        assert health["deliveries"]["pending"] == 0


# ---------------------------------------------------------------------------
# WebhookDelivery dataclass
# ---------------------------------------------------------------------------


class TestWebhookDeliveryDataclass:
    """Tests for the WebhookDelivery dataclass."""

    def test_defaults(self):
        d = WebhookDelivery(
            delivery_id="d1",
            handler_name="h1",
            payload={"k": "v"},
            target_url="https://example.com",
        )
        assert d.status == DeliveryStatus.PENDING
        assert d.attempts == 0
        assert d.max_attempts == 5
        assert d.last_error is None
        assert d.delivered_at is None
        assert isinstance(d.created_at, float)

    def test_delivery_status_enum(self):
        assert DeliveryStatus.PENDING.value == "pending"
        assert DeliveryStatus.DELIVERED.value == "delivered"
        assert DeliveryStatus.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and configuration variants."""

    def test_custom_headers(self):
        t = WebhookTransport(
            secret="s3cret",
            signature_header="X-Custom-Sig",
            idempotency_header="X-Custom-Idem",
        )
        assert t._signature_header == "X-Custom-Sig"
        assert t._idempotency_header == "X-Custom-Idem"

    def test_custom_retry_config(self):
        t = WebhookTransport(
            max_retries=10,
            base_delay=2.0,
            max_delay=120.0,
        )
        assert t._max_retries == 10
        assert t._base_delay == 2.0
        assert t._max_delay == 120.0

    @pytest.mark.asyncio
    async def test_stop_clears_handler_map(self, transport, registry):
        async def greet(name: str) -> dict:
            return {"message": f"Hello, {name}!"}

        registry.register_handler("greet", greet)
        await transport.start(registry)
        assert len(transport._handler_map) == 1

        await transport.stop()
        assert len(transport._handler_map) == 0

    @pytest.mark.asyncio
    async def test_stop_clears_processed_keys(self, transport, registry):
        await transport.start(registry)
        transport._record_processed("k1", {"status": "ok"})
        assert len(transport._processed_keys) == 1

        await transport.stop()
        assert len(transport._processed_keys) == 0
