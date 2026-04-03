# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for WebhookReceiver (TODO-16).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone

import pytest

from dataflow.fabric.config import RestSourceConfig, WebhookConfig
from dataflow.fabric.webhooks import (
    WebhookReceiver,
    _BoundedNonceSet,
    _InMemoryNonceBackend,
    _RedisNonceBackend,
)


def _make_sources(webhook_secret_env: str = "TEST_HOOK_SECRET") -> dict:
    """Create a sources dict with a webhook-enabled source."""
    return {
        "crm": {
            "config": RestSourceConfig(
                url="https://api.example.com",
                webhook=WebhookConfig(
                    path="/hooks/crm",
                    secret_env=webhook_secret_env,
                ),
            ),
            "adapter": None,
        }
    }


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestWebhookReceiver:
    @pytest.fixture(autouse=True)
    def set_secret(self, monkeypatch):
        monkeypatch.setenv("TEST_HOOK_SECRET", "my_secret_123")

    def test_registers_webhooks_from_sources(self):
        receiver = WebhookReceiver(_make_sources())
        assert receiver.webhook_count == 1
        assert "crm" in receiver.get_registered_webhooks()

    @pytest.mark.asyncio
    async def test_valid_webhook_accepted(self):
        receiver = WebhookReceiver(_make_sources())
        body = b'{"event": "deal.created"}'
        sig = _sign(body, "my_secret_123")

        result = await receiver.handle_webhook(
            "crm",
            {"X-Webhook-Signature": sig},
            body,
        )
        assert result["accepted"] is True

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self):
        receiver = WebhookReceiver(_make_sources())
        body = b'{"event": "deal.created"}'

        result = await receiver.handle_webhook(
            "crm",
            {"X-Webhook-Signature": "bad_signature"},
            body,
        )
        assert result["accepted"] is False
        assert "Invalid signature" in result["reason"]

    @pytest.mark.asyncio
    async def test_missing_signature_rejected(self):
        receiver = WebhookReceiver(_make_sources())
        result = await receiver.handle_webhook("crm", {}, b"body")
        assert result["accepted"] is False
        assert "Missing" in result["reason"]

    @pytest.mark.asyncio
    async def test_unknown_source_rejected(self):
        receiver = WebhookReceiver(_make_sources())
        result = await receiver.handle_webhook("unknown", {}, b"body")
        assert result["accepted"] is False
        assert "no webhook config" in result["reason"]

    @pytest.mark.asyncio
    async def test_stale_timestamp_rejected(self):
        receiver = WebhookReceiver(_make_sources())
        body = b'{"event": "test"}'
        sig = _sign(body, "my_secret_123")
        old_ts = "2020-01-01T00:00:00Z"

        result = await receiver.handle_webhook(
            "crm",
            {"X-Webhook-Signature": sig, "X-Webhook-Timestamp": old_ts},
            body,
        )
        assert result["accepted"] is False
        assert "too old" in result["reason"]

    @pytest.mark.asyncio
    async def test_duplicate_nonce_rejected(self):
        receiver = WebhookReceiver(_make_sources())
        body = b'{"event": "test"}'
        sig = _sign(body, "my_secret_123")

        headers = {"X-Webhook-Signature": sig, "X-Webhook-Delivery-Id": "nonce-123"}
        result1 = await receiver.handle_webhook("crm", headers, body)
        assert result1["accepted"] is True

        result2 = await receiver.handle_webhook("crm", headers, body)
        assert result2["accepted"] is False
        assert "Duplicate" in result2["reason"]

    @pytest.mark.asyncio
    async def test_callback_invoked(self):
        called_with = []

        async def on_event(source_name: str) -> None:
            called_with.append(source_name)

        receiver = WebhookReceiver(_make_sources(), on_webhook_event=on_event)
        body = b'{"event": "test"}'
        sig = _sign(body, "my_secret_123")

        await receiver.handle_webhook("crm", {"X-Webhook-Signature": sig}, body)
        assert called_with == ["crm"]


class TestBoundedNonceSet:
    def test_add_and_check(self):
        nonces = _BoundedNonceSet(maxsize=5)
        nonces.add("a")
        assert nonces.contains("a")
        assert not nonces.contains("b")

    def test_evicts_oldest(self):
        nonces = _BoundedNonceSet(maxsize=3)
        nonces.add("a")
        nonces.add("b")
        nonces.add("c")
        nonces.add("d")  # Evicts "a"
        assert not nonces.contains("a")
        assert nonces.contains("d")
        assert len(nonces) == 3


class TestInMemoryNonceBackend:
    @pytest.mark.asyncio
    async def test_add_and_contains(self):
        backend = _InMemoryNonceBackend(maxsize=10)
        assert not await backend.contains("src", "nonce-1")
        await backend.add("src", "nonce-1")
        assert await backend.contains("src", "nonce-1")

    @pytest.mark.asyncio
    async def test_source_isolation(self):
        """Nonces are scoped per source — different sources don't collide."""
        backend = _InMemoryNonceBackend(maxsize=10)
        await backend.add("src_a", "nonce-1")
        assert await backend.contains("src_a", "nonce-1")
        assert not await backend.contains("src_b", "nonce-1")

    @pytest.mark.asyncio
    async def test_eviction(self):
        backend = _InMemoryNonceBackend(maxsize=3)
        await backend.add("s", "a")
        await backend.add("s", "b")
        await backend.add("s", "c")
        await backend.add("s", "d")  # Evicts "a"
        assert not await backend.contains("s", "a")
        assert await backend.contains("s", "d")


class TestRedisNonceBackend:
    """Tests Redis nonce backend with a fake async Redis client."""

    class _FakeRedis:
        """Minimal async Redis stub for unit tests."""

        def __init__(self):
            self._sets: dict[str, set[str]] = {}
            self._ttls: dict[str, int] = {}

        async def sismember(self, key: str, member: str) -> bool:
            return member in self._sets.get(key, set())

        async def sadd(self, key: str, *members: str) -> int:
            if key not in self._sets:
                self._sets[key] = set()
            added = 0
            for m in members:
                if m not in self._sets[key]:
                    self._sets[key].add(m)
                    added += 1
            return added

        async def expire(self, key: str, ttl: int) -> bool:
            self._ttls[key] = ttl
            return True

    @pytest.mark.asyncio
    async def test_add_and_contains(self):
        redis = self._FakeRedis()
        backend = _RedisNonceBackend(redis)
        assert not await backend.contains("crm", "nonce-1")
        await backend.add("crm", "nonce-1")
        assert await backend.contains("crm", "nonce-1")

    @pytest.mark.asyncio
    async def test_sets_ttl(self):
        redis = self._FakeRedis()
        backend = _RedisNonceBackend(redis)
        await backend.add("crm", "nonce-1")
        assert redis._ttls["fabric:webhook:nonces:crm"] == 300

    @pytest.mark.asyncio
    async def test_source_isolation(self):
        redis = self._FakeRedis()
        backend = _RedisNonceBackend(redis)
        await backend.add("src_a", "n1")
        assert await backend.contains("src_a", "n1")
        assert not await backend.contains("src_b", "n1")


class TestWebhookReceiverWithRedis:
    @pytest.fixture(autouse=True)
    def set_secret(self, monkeypatch):
        monkeypatch.setenv("TEST_HOOK_SECRET", "my_secret_123")

    @pytest.mark.asyncio
    async def test_redis_nonce_dedup(self):
        """Duplicate nonces are rejected when using Redis backend."""
        redis = TestRedisNonceBackend._FakeRedis()
        receiver = WebhookReceiver(_make_sources(), redis_client=redis)
        body = b'{"event": "test"}'
        sig = _sign(body, "my_secret_123")
        headers = {"X-Webhook-Signature": sig, "X-Webhook-Delivery-Id": "nonce-42"}

        r1 = await receiver.handle_webhook("crm", headers, body)
        assert r1["accepted"] is True

        r2 = await receiver.handle_webhook("crm", headers, body)
        assert r2["accepted"] is False
        assert "Duplicate" in r2["reason"]
