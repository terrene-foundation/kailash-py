# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 regression test for issue #1814.

Webhook signature verification MUST fail closed when no secret is
configured. Before the fix, ``WebhookTransport.verify_signature`` and
``verify_signature_for_request`` returned ``True`` when ``self._secret``
was ``None`` — accepting ANY forged payload+signature reaching the verify
path (a fail-open signature bypass on webhook ingress).

The fix mirrors the existing ``compute_signature`` guard: reaching a
verify entry point with a signature but no secret is a misconfiguration,
so verification raises ``ValueError`` rather than returning ``True``.

This exercises the real ``WebhookTransport`` + the real
``HmacSha256Signer`` (no mocking of the code under test, per
``rules/testing.md`` § Tier 2):

- No secret configured + a forged payload/signature → REJECTED (raises
  ``ValueError``), for BOTH ``verify_signature`` and
  ``verify_signature_for_request``.
- Secret configured + a forged signature → returns ``False`` (unchanged).
- Secret configured + a valid signature → returns ``True`` (unchanged).

Note the ``receive()`` unsigned-receive path was subsequently hardened by
issue #1836: ``receive()`` now also fails closed when no secret is
configured unless ``allow_unsigned=True`` is set. That behaviour is covered
by ``tests/regression/test_issue_1836_webhook_fail_closed.py`` and the unit
tests ``test_receive_no_secret_fails_closed`` /
``test_receive_no_secret_allow_unsigned_accepts``. This #1814 test remains
scoped to the ``verify_signature`` / ``verify_signature_for_request`` entry
points.
"""

import hashlib
import hmac

import pytest

from nexus.transports.webhook import WebhookTransport


def _make_signature(secret: str, payload_bytes: bytes) -> str:
    """Compute the canonical HMAC-SHA256 signature the signer expects."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.mark.regression
def test_verify_signature_no_secret_rejects_forged_payload():
    """No secret + forged signature → raises, never fail-open True (#1814)."""
    transport = WebhookTransport()  # no secret configured
    forged_payload = b'{"event": "payment.completed", "amount": 1000000}'
    forged_signature = "sha256=" + "0" * 64

    with pytest.raises(ValueError, match="no secret configured"):
        transport.verify_signature(forged_payload, forged_signature)


@pytest.mark.regression
def test_verify_signature_for_request_no_secret_rejects_forged_payload():
    """No secret + forged signature (URL-canonical path) → raises (#1814)."""
    transport = WebhookTransport()  # no secret configured
    forged_payload = b'{"event": "payment.completed", "amount": 1000000}'
    forged_signature = "sha256=" + "0" * 64

    with pytest.raises(ValueError, match="no secret configured"):
        transport.verify_signature_for_request(
            url="https://example.com/webhooks/inbound",
            payload_bytes=forged_payload,
            signature=forged_signature,
        )


@pytest.mark.regression
def test_verify_signature_secret_configured_rejects_forged_signature():
    """Secret configured + forged signature → False (unchanged behaviour)."""
    secret = "test-webhook-secret-key"
    transport = WebhookTransport(secret=secret)
    payload = b'{"event": "user.created"}'

    assert transport.verify_signature(payload, "sha256=deadbeef") is False


@pytest.mark.regression
def test_verify_signature_secret_configured_accepts_valid_signature():
    """Secret configured + valid signature → True (unchanged behaviour)."""
    secret = "test-webhook-secret-key"
    transport = WebhookTransport(secret=secret)
    payload = b'{"event": "user.created"}'
    valid_signature = _make_signature(secret, payload)

    assert transport.verify_signature(payload, valid_signature) is True
