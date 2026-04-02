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
from dataflow.fabric.webhooks import WebhookReceiver, _BoundedNonceSet


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
