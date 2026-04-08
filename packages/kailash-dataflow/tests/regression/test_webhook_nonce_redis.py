# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression: webhook nonce deduplication MUST be cross-replica when a
shared Redis client is provided.

Bug history: ``FabricRuntime.start()`` constructed
``WebhookReceiver(...)`` without forwarding the shared Redis client, so
every replica fell back to in-memory nonce sets and the same delivery
ID could be processed by multiple replicas. Phase 5.4 wires the shared
client through. This regression test verifies the fix by:

1. Sharing one async Redis client between two ``WebhookReceiver``
   instances (simulating two replicas of the same fabric service).
2. Sending the same delivery ID + body + signature to both receivers.
3. Asserting only ONE receiver fires its event callback (the second
   sees the nonce in Redis and rejects the duplicate).

This test requires a real Redis instance reachable at
``FABRIC_TEST_REDIS_URL`` (default ``redis://localhost:6380/0``). It
exercises the real ``_RedisNonceBackend`` SADD + EXPIRE pipeline.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone

import pytest

from dataflow.fabric.config import WebhookConfig
from dataflow.fabric.webhooks import WebhookReceiver

REDIS_URL = os.environ.get("FABRIC_TEST_REDIS_URL", "redis://localhost:6380/0")


def _redis_reachable(url: str) -> bool:
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=0.5)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.regression,
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _redis_reachable(REDIS_URL),
        reason=f"Redis not reachable at {REDIS_URL}",
    ),
]


@pytest.fixture
async def shared_redis_client():
    import redis.asyncio as aioredis

    client = aioredis.from_url(REDIS_URL, decode_responses=False)
    yield client
    try:
        await client.flushdb()
    finally:
        await client.aclose()


def _build_sources_with_webhook(secret_env: str) -> dict:
    """Build a source registry with one webhook-enabled source."""

    class _Cfg:
        def __init__(self) -> None:
            self.webhook = WebhookConfig(
                path="/fabric/webhook/src1", secret_env=secret_env
            )

    return {"src1": {"name": "src1", "config": _Cfg(), "adapter": None}}


async def test_two_replicas_dedupe_same_delivery_via_redis(
    shared_redis_client, monkeypatch
) -> None:
    """Two WebhookReceiver instances share a Redis client; only one fires."""
    secret_env = "FABRIC_TEST_WEBHOOK_SECRET"
    monkeypatch.setenv(secret_env, "shared-secret-value")

    # Both replicas wire the same async Redis client.
    sources = _build_sources_with_webhook(secret_env)

    fired_a: list[str] = []
    fired_b: list[str] = []

    async def cb_a(name: str) -> None:
        fired_a.append(name)

    async def cb_b(name: str) -> None:
        fired_b.append(name)

    replica_a = WebhookReceiver(
        sources=sources,
        on_webhook_event=cb_a,
        redis_client=shared_redis_client,
    )
    replica_b = WebhookReceiver(
        sources=sources,
        on_webhook_event=cb_b,
        redis_client=shared_redis_client,
    )

    body = b'{"event": "ping"}'
    signature = hmac.new(b"shared-secret-value", body, hashlib.sha256).hexdigest()
    delivery_id = f"delivery-{uuid.uuid4().hex}"
    timestamp = datetime.now(timezone.utc).isoformat()

    headers = {
        "x-webhook-signature": signature,
        "x-webhook-timestamp": timestamp,
        "x-webhook-delivery-id": delivery_id,
    }

    # Replica A receives and processes
    result_a = await replica_a.handle_webhook("src1", headers, body)
    assert result_a["accepted"] is True
    assert fired_a == ["src1"]

    # Replica B receives the SAME delivery — must be rejected as duplicate
    result_b = await replica_b.handle_webhook("src1", headers, body)
    assert result_b["accepted"] is False
    assert "duplicate" in result_b["reason"].lower()
    assert fired_b == [], "replica B must NOT have fired its callback"


async def test_in_memory_fallback_when_redis_url_absent(monkeypatch) -> None:
    """Without a shared Redis client, the receiver still works in-memory.

    This is the dev-mode path. Two separate replicas would each see the
    delivery as fresh because each has its own in-memory nonce set;
    that's expected behavior in dev. We assert the same instance dedups
    its own retries.
    """
    secret_env = "FABRIC_TEST_WEBHOOK_SECRET2"
    monkeypatch.setenv(secret_env, "dev-secret")
    sources = _build_sources_with_webhook(secret_env)

    fired: list[str] = []

    async def cb(name: str) -> None:
        fired.append(name)

    receiver = WebhookReceiver(
        sources=sources,
        on_webhook_event=cb,
        redis_client=None,
    )

    body = b'{"x":1}'
    signature = hmac.new(b"dev-secret", body, hashlib.sha256).hexdigest()
    delivery_id = f"dev-delivery-{uuid.uuid4().hex}"
    timestamp = datetime.now(timezone.utc).isoformat()
    headers = {
        "x-webhook-signature": signature,
        "x-webhook-timestamp": timestamp,
        "x-webhook-delivery-id": delivery_id,
    }

    first = await receiver.handle_webhook("src1", headers, body)
    second = await receiver.handle_webhook("src1", headers, body)
    assert first["accepted"] is True
    assert second["accepted"] is False
    assert fired == ["src1"]
