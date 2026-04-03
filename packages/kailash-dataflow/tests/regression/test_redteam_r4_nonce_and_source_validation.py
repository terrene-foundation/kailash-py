# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for red team round 4 findings:
- RT4-C1: _NonceBackend must use ABC (not raise NotImplementedError)
- RT4-H2: source_name must be validated against safe pattern
- RT4-M1: Timestamp NaN/Inf must be rejected
- RT4-M3: Redis SADD+EXPIRE should use pipeline when available
"""

from __future__ import annotations

import inspect

import pytest

from dataflow.fabric.webhooks import (
    WebhookReceiver,
    _InMemoryNonceBackend,
    _NonceBackend,
    _RedisNonceBackend,
)


@pytest.mark.regression
class TestRT4NonceBackendABC:
    """RT4-C1: _NonceBackend uses ABC, not raise NotImplementedError."""

    def test_nonce_backend_is_abstract(self):
        """Cannot instantiate _NonceBackend directly."""
        with pytest.raises(TypeError, match="abstract"):
            _NonceBackend()  # type: ignore[abstract]

    def test_contains_is_abstract_method(self):
        assert getattr(_NonceBackend.contains, "__isabstractmethod__", False)

    def test_add_is_abstract_method(self):
        assert getattr(_NonceBackend.add, "__isabstractmethod__", False)

    def test_no_not_implemented_error_in_source(self):
        """NotImplementedError must not appear in webhooks.py production code."""
        source = inspect.getsource(_NonceBackend)
        assert "NotImplementedError" not in source


@pytest.mark.regression
class TestRT4SourceNameValidation:
    """RT4-H2: source_name validated at registration time."""

    def test_empty_name_rejected(self):
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:")
        with pytest.raises(ValueError, match="Invalid source name"):
            db.source("", _InMemoryNonceBackend())  # type: ignore[arg-type]

    def test_name_with_colon_rejected(self):
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:")
        with pytest.raises(ValueError, match="Invalid source name"):
            db.source("bad:name", _InMemoryNonceBackend())  # type: ignore[arg-type]

    def test_name_with_slash_rejected(self):
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:")
        with pytest.raises(ValueError, match="Invalid source name"):
            db.source("../etc/passwd", _InMemoryNonceBackend())  # type: ignore[arg-type]

    def test_long_name_rejected(self):
        from dataflow import DataFlow

        db = DataFlow("sqlite:///:memory:")
        with pytest.raises(ValueError, match="Invalid source name"):
            db.source("a" * 65, _InMemoryNonceBackend())  # type: ignore[arg-type]

    def test_valid_name_accepted(self):
        from dataflow import DataFlow
        from dataflow.fabric.testing import MockSource

        db = DataFlow("sqlite:///:memory:")
        db.source("valid_source-1", MockSource(name="valid_source-1", data={"k": "v"}))
        assert "valid_source-1" in db._sources


@pytest.mark.regression
class TestRT4TimestampNaN:
    """RT4-M1: Timestamp NaN/Inf must be rejected."""

    @pytest.fixture(autouse=True)
    def set_secret(self, monkeypatch):
        monkeypatch.setenv("TEST_HOOK_SECRET", "secret123")

    def _make_receiver(self):
        from dataflow.fabric.config import RestSourceConfig, WebhookConfig

        sources = {
            "src": {
                "config": RestSourceConfig(
                    url="https://example.com",
                    webhook=WebhookConfig(path="/h", secret_env="TEST_HOOK_SECRET"),
                ),
                "adapter": None,
            }
        }
        return WebhookReceiver(sources)

    def _sign(self, body: bytes, secret: str) -> str:
        import hashlib
        import hmac as hmac_mod

        return hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()

    @pytest.mark.asyncio
    async def test_nan_timestamp_rejected(self):
        receiver = self._make_receiver()
        body = b"{}"
        sig = self._sign(body, "secret123")
        result = await receiver.handle_webhook(
            "src",
            {"X-Webhook-Signature": sig, "X-Webhook-Timestamp": "nan"},
            body,
        )
        assert result["accepted"] is False
        assert "Invalid timestamp" in result["reason"]

    @pytest.mark.asyncio
    async def test_inf_timestamp_rejected(self):
        receiver = self._make_receiver()
        body = b"{}"
        sig = self._sign(body, "secret123")
        result = await receiver.handle_webhook(
            "src",
            {"X-Webhook-Signature": sig, "X-Webhook-Timestamp": "inf"},
            body,
        )
        assert result["accepted"] is False
        assert "Invalid timestamp" in result["reason"]


@pytest.mark.regression
class TestRT4RedisPipeline:
    """RT4-M3/M4: Redis SADD+EXPIRE uses pipeline when available."""

    class _PipelineTrackingRedis:
        """Tracks whether pipeline was used."""

        def __init__(self):
            self._pipeline_used = False
            self._sets: dict[str, set[str]] = {}

        def pipeline(self):
            self._pipeline_used = True
            return _PipelineCtx(self)

        async def sismember(self, key: str, member: str) -> bool:
            return member in self._sets.get(key, set())

        async def sadd(self, key: str, *members: str) -> int:
            self._sets.setdefault(key, set()).update(members)
            return len(members)

        async def expire(self, key: str, ttl: int) -> bool:
            return True

    @pytest.mark.asyncio
    async def test_pipeline_used_when_available(self):
        redis = self._PipelineTrackingRedis()
        backend = _RedisNonceBackend(redis)
        await backend.add("src", "nonce-1")
        assert redis._pipeline_used


class _PipelineCtx:
    """Fake Redis pipeline context manager."""

    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    def sadd(self, key, *members):
        self._ops.append(("sadd", key, members))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    async def execute(self):
        for op in self._ops:
            if op[0] == "sadd":
                self._redis._sets.setdefault(op[1], set()).update(op[2])
