# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Phase 5.9 — Multi-webhook-source adapters.

Tests the per-provider signature verifiers wired into
:class:`dataflow.fabric.webhooks.WebhookReceiver`. Each provider has
its own signature contract; these tests assert each verifier accepts
the canonical signed payload and rejects the standard tampering
patterns (wrong secret, missing header, replay window violation).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import pytest

from dataflow.fabric.config import RestSourceConfig, WebhookConfig
from dataflow.fabric.webhooks import (
    WebhookReceiver,
    _GenericVerifier,
    _GitHubVerifier,
    _GitLabVerifier,
    _SlackVerifier,
    _StripeVerifier,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Verifier helpers
# ---------------------------------------------------------------------------


def _hex_sig(secret: str, body: bytes) -> str:
    """Compute the canonical SHA256 hex digest used by every provider."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Generic verifier
# ---------------------------------------------------------------------------


class TestGenericVerifier:
    def test_accepts_valid_signature(self):
        verifier = _GenericVerifier()
        body = b'{"event": "ping"}'
        secret = "topsecret"
        result = verifier.verify(
            headers={
                "x-webhook-signature": _hex_sig(secret, body),
                "x-webhook-delivery-id": "delivery-1",
            },
            body=body,
            secret=secret,
            now=_now(),
        )
        assert result.accepted is True
        assert result.nonce == "delivery-1"

    def test_rejects_missing_header(self):
        result = _GenericVerifier().verify(headers={}, body=b"", secret="x", now=_now())
        assert result.accepted is False
        assert "Missing" in result.reason

    def test_rejects_wrong_secret(self):
        body = b"payload"
        result = _GenericVerifier().verify(
            headers={"x-webhook-signature": _hex_sig("wrong", body)},
            body=body,
            secret="real",
            now=_now(),
        )
        assert result.accepted is False
        assert result.reason == "Invalid signature"


# ---------------------------------------------------------------------------
# GitHub verifier
# ---------------------------------------------------------------------------


class TestGitHubVerifier:
    def test_accepts_valid_sha256_signature(self):
        body = b'{"action": "opened"}'
        secret = "gh-secret"
        sig = _hex_sig(secret, body)
        result = _GitHubVerifier().verify(
            headers={
                "x-hub-signature-256": f"sha256={sig}",
                "x-github-delivery": "550e8400-e29b-41d4-a716-446655440000",
            },
            body=body,
            secret=secret,
            now=_now(),
        )
        assert result.accepted is True
        assert result.nonce == "550e8400-e29b-41d4-a716-446655440000"

    def test_rejects_unprefixed_signature(self):
        body = b"payload"
        secret = "gh-secret"
        result = _GitHubVerifier().verify(
            headers={"x-hub-signature-256": _hex_sig(secret, body)},
            body=body,
            secret=secret,
            now=_now(),
        )
        assert result.accepted is False
        assert "sha256=" in result.reason

    def test_rejects_missing_header(self):
        result = _GitHubVerifier().verify(headers={}, body=b"", secret="x", now=_now())
        assert result.accepted is False
        assert "Missing" in result.reason

    def test_rejects_wrong_secret(self):
        body = b'{"action": "opened"}'
        result = _GitHubVerifier().verify(
            headers={"x-hub-signature-256": "sha256=" + _hex_sig("wrong", body)},
            body=body,
            secret="real",
            now=_now(),
        )
        assert result.accepted is False


# ---------------------------------------------------------------------------
# GitLab verifier
# ---------------------------------------------------------------------------


class TestGitLabVerifier:
    def test_accepts_matching_token(self):
        result = _GitLabVerifier().verify(
            headers={
                "x-gitlab-token": "shared-secret",
                "x-gitlab-event-uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
            body=b'{"event": "push"}',
            secret="shared-secret",
            now=_now(),
        )
        assert result.accepted is True
        assert result.nonce == "550e8400-e29b-41d4-a716-446655440000"

    def test_rejects_wrong_token(self):
        result = _GitLabVerifier().verify(
            headers={"x-gitlab-token": "guess"},
            body=b"",
            secret="real-secret",
            now=_now(),
        )
        assert result.accepted is False
        assert result.reason == "Invalid token"

    def test_rejects_missing_token(self):
        result = _GitLabVerifier().verify(headers={}, body=b"", secret="x", now=_now())
        assert result.accepted is False


# ---------------------------------------------------------------------------
# Stripe verifier
# ---------------------------------------------------------------------------


class TestStripeVerifier:
    def _build_header(self, secret: str, body: bytes, ts: int) -> str:
        signed = f"{ts}.".encode("utf-8") + body
        sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    def test_accepts_valid_signature(self):
        body = b'{"object": "event"}'
        secret = "whsec_test"
        now = _now()
        ts = int(now.timestamp())
        header = self._build_header(secret, body, ts)

        result = _StripeVerifier().verify(
            headers={"stripe-signature": header},
            body=body,
            secret=secret,
            now=now,
        )
        assert result.accepted is True
        assert result.nonce == hashlib.sha256(body).hexdigest()

    def test_accepts_signature_with_secondary_v1(self):
        """Stripe rotates keys; multiple v1= entries means any matching one wins."""
        body = b'{"object": "event"}'
        secret = "whsec_test"
        now = _now()
        ts = int(now.timestamp())
        signed = f"{ts}.".encode("utf-8") + body
        good = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        header = f"t={ts},v1=deadbeef,v1={good}"

        result = _StripeVerifier().verify(
            headers={"stripe-signature": header},
            body=body,
            secret=secret,
            now=now,
        )
        assert result.accepted is True

    def test_rejects_old_timestamp(self):
        body = b"{}"
        secret = "whsec_test"
        old_ts = int((_now() - timedelta(minutes=10)).timestamp())
        header = self._build_header(secret, body, old_ts)
        result = _StripeVerifier().verify(
            headers={"stripe-signature": header},
            body=body,
            secret=secret,
            now=_now(),
        )
        assert result.accepted is False
        assert "too old" in result.reason

    def test_rejects_wrong_secret(self):
        body = b"{}"
        ts = int(_now().timestamp())
        header = self._build_header("wrong", body, ts)
        result = _StripeVerifier().verify(
            headers={"stripe-signature": header},
            body=body,
            secret="real",
            now=_now(),
        )
        assert result.accepted is False
        assert result.reason == "Invalid signature"

    def test_rejects_missing_t_field(self):
        result = _StripeVerifier().verify(
            headers={"stripe-signature": "v1=abcdef"},
            body=b"",
            secret="x",
            now=_now(),
        )
        assert result.accepted is False
        assert "'t'" in result.reason

    def test_rejects_missing_v1_field(self):
        result = _StripeVerifier().verify(
            headers={"stripe-signature": "t=123"},
            body=b"",
            secret="x",
            now=_now(),
        )
        assert result.accepted is False
        assert "'v1'" in result.reason


# ---------------------------------------------------------------------------
# Slack verifier
# ---------------------------------------------------------------------------


class TestSlackVerifier:
    def _build(self, secret: str, body: bytes, ts: int) -> str:
        signed = f"v0:{ts}:".encode("utf-8") + body
        sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return f"v0={sig}"

    def test_accepts_valid_signature(self):
        body = b"command=ping&user=alice"
        secret = "slack-signing-secret"
        now = _now()
        ts = int(now.timestamp())

        result = _SlackVerifier().verify(
            headers={
                "x-slack-signature": self._build(secret, body, ts),
                "x-slack-request-timestamp": str(ts),
            },
            body=body,
            secret=secret,
            now=now,
        )
        assert result.accepted is True
        assert result.nonce == hashlib.sha256(body).hexdigest()

    def test_rejects_missing_timestamp(self):
        result = _SlackVerifier().verify(
            headers={"x-slack-signature": "v0=deadbeef"},
            body=b"",
            secret="x",
            now=_now(),
        )
        assert result.accepted is False
        assert "Timestamp" in result.reason

    def test_rejects_old_timestamp(self):
        body = b"x"
        secret = "slack"
        old = int((_now() - timedelta(minutes=10)).timestamp())
        result = _SlackVerifier().verify(
            headers={
                "x-slack-signature": self._build(secret, body, old),
                "x-slack-request-timestamp": str(old),
            },
            body=body,
            secret=secret,
            now=_now(),
        )
        assert result.accepted is False
        assert "too old" in result.reason

    def test_rejects_unprefixed_signature(self):
        body = b"x"
        secret = "slack"
        ts = int(_now().timestamp())
        sig = hmac.new(
            secret.encode("utf-8"),
            f"v0:{ts}:".encode("utf-8") + body,
            hashlib.sha256,
        ).hexdigest()
        result = _SlackVerifier().verify(
            headers={
                "x-slack-signature": sig,  # missing "v0=" prefix
                "x-slack-request-timestamp": str(ts),
            },
            body=body,
            secret=secret,
            now=_now(),
        )
        assert result.accepted is False
        assert "v0=" in result.reason


# ---------------------------------------------------------------------------
# Receiver-level dispatch — provider config flows through end-to-end
# ---------------------------------------------------------------------------


class TestReceiverProviderDispatch:
    def _make_receiver(self, provider: str, secret_env: str, secret: str):
        os.environ[secret_env] = secret
        webhook = WebhookConfig(path="/hook", secret_env=secret_env, provider=provider)
        config = RestSourceConfig(url="https://api.example.com", webhook=webhook)
        sources = {"src": {"config": config}}
        return WebhookReceiver(sources=sources)

    def teardown_method(self) -> None:
        for env in (
            "WEBHOOK_GITHUB",
            "WEBHOOK_GITLAB",
            "WEBHOOK_STRIPE",
            "WEBHOOK_SLACK",
        ):
            os.environ.pop(env, None)

    @pytest.mark.asyncio
    async def test_github_dispatch_accepts_valid(self):
        receiver = self._make_receiver("github", "WEBHOOK_GITHUB", "gh-secret")
        body = b'{"action": "opened"}'
        sig = _hex_sig("gh-secret", body)
        result = await receiver.handle_webhook(
            "src",
            headers={
                "x-hub-signature-256": f"sha256={sig}",
                "x-github-delivery": "delivery-123",
            },
            body=body,
        )
        assert result["accepted"] is True

    @pytest.mark.asyncio
    async def test_gitlab_dispatch_accepts_valid(self):
        receiver = self._make_receiver("gitlab", "WEBHOOK_GITLAB", "gl-token")
        result = await receiver.handle_webhook(
            "src",
            headers={
                "x-gitlab-token": "gl-token",
                "x-gitlab-event-uuid": "uuid-1",
            },
            body=b'{"event_name": "push"}',
        )
        assert result["accepted"] is True

    @pytest.mark.asyncio
    async def test_stripe_dispatch_accepts_valid(self):
        secret = "whsec_dispatch"
        receiver = self._make_receiver("stripe", "WEBHOOK_STRIPE", secret)
        body = b'{"object": "event"}'
        ts = int(_now().timestamp())
        signed = f"{ts}.".encode("utf-8") + body
        sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        result = await receiver.handle_webhook(
            "src",
            headers={"stripe-signature": f"t={ts},v1={sig}"},
            body=body,
        )
        assert result["accepted"] is True

    @pytest.mark.asyncio
    async def test_slack_dispatch_accepts_valid(self):
        secret = "slack-dispatch"
        receiver = self._make_receiver("slack", "WEBHOOK_SLACK", secret)
        body = b"command=ping"
        ts = int(_now().timestamp())
        signed = f"v0:{ts}:".encode("utf-8") + body
        sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        result = await receiver.handle_webhook(
            "src",
            headers={
                "x-slack-signature": f"v0={sig}",
                "x-slack-request-timestamp": str(ts),
            },
            body=body,
        )
        assert result["accepted"] is True

    @pytest.mark.asyncio
    async def test_provider_rejects_legacy_generic_signature(self):
        """A receiver configured for github MUST NOT accept the legacy
        X-Webhook-Signature header even if the body HMAC matches —
        otherwise sources could be tricked across provider schemes."""
        receiver = self._make_receiver("github", "WEBHOOK_GITHUB", "gh-secret")
        body = b'{"action": "opened"}'
        result = await receiver.handle_webhook(
            "src",
            headers={"x-webhook-signature": _hex_sig("gh-secret", body)},
            body=body,
        )
        assert result["accepted"] is False
        assert "Missing X-Hub-Signature-256" in result["reason"]
