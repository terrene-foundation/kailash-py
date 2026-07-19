# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 regression test for issue #1836.

``WebhookTransport.receive()`` MUST fail closed when no signing secret is
configured. Before the fix, ``receive()`` guarded signature verification
with ``if self._secret is not None`` and so SKIPPED verification entirely
when no secret was set — a no-secret deployment silently accepted ANY
forged inbound webhook event.

#1814 already hardened ``verify_signature`` / ``verify_signature_for_request``
to fail closed; #1836 (Option A) closes the remaining hole at ``receive()``
itself: with no secret AND without the explicit ``allow_unsigned=True``
opt-in, ``receive()`` now raises ``ValueError`` rather than dispatching the
unsigned payload. Deployments that intentionally run unsigned (or verify at
an edge proxy) opt in via ``WebhookTransport(allow_unsigned=True)``.

This exercises the real ``WebhookTransport`` + the real ``HmacSha256Signer``
with real HMAC signatures over real payloads (no mocking of the code under
test, per ``rules/testing.md`` § Tier 2):

1. No secret + ``allow_unsigned`` unset → REJECTED (raises ``ValueError``).
2. No secret + ``allow_unsigned=True`` → ACCEPTED (unsigned mode preserved).
3. Secret configured + VALID signature → ACCEPTED (unchanged).
4. Secret configured + INVALID signature → REJECTED (unchanged from #1814).
"""

import hashlib
import hmac
import json

import pytest

from nexus.registry import HandlerRegistry
from nexus.transports.webhook import WebhookTransport


def _make_signature(secret: str, payload_bytes: bytes) -> str:
    """Compute the canonical HMAC-SHA256 signature the signer expects."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


async def _started_transport(transport: WebhookTransport) -> WebhookTransport:
    """Register a real handler and start the transport."""
    registry = HandlerRegistry()

    async def process_event(event: str, amount: int) -> dict:
        return {"processed": event, "amount": amount}

    registry.register_handler("process_event", process_event)
    await transport.start(registry)
    return transport


@pytest.mark.regression
@pytest.mark.asyncio
async def test_receive_no_secret_no_optin_fails_closed():
    """Case 1: no secret + allow_unsigned unset → raises (#1836)."""
    transport = await _started_transport(WebhookTransport())  # secure default
    forged_payload = {"event": "payment.completed", "amount": 1000000}
    forged_bytes = json.dumps(forged_payload).encode("utf-8")

    with pytest.raises(ValueError, match="unsigned webhook"):
        await transport.receive(
            "process_event",
            forged_payload,
            payload_bytes=forged_bytes,
            signature="sha256=" + "0" * 64,
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_receive_no_secret_allow_unsigned_accepts():
    """Case 2: no secret + allow_unsigned=True → accepted, unsigned mode preserved (#1836)."""
    transport = await _started_transport(WebhookTransport(allow_unsigned=True))
    payload = {"event": "payment.completed", "amount": 4200}

    result = await transport.receive("process_event", payload)

    assert result["status"] == "ok"
    assert result["handler"] == "process_event"
    assert result["result"] == {"processed": "payment.completed", "amount": 4200}


@pytest.mark.regression
@pytest.mark.asyncio
async def test_receive_secret_valid_signature_accepts():
    """Case 3: secret + valid HMAC signature → accepted (unchanged)."""
    secret = "test-webhook-secret-key"
    transport = await _started_transport(WebhookTransport(secret=secret))
    payload = {"event": "user.created", "amount": 1}
    payload_bytes = json.dumps(payload).encode("utf-8")
    valid_signature = _make_signature(secret, payload_bytes)

    result = await transport.receive(
        "process_event",
        payload,
        payload_bytes=payload_bytes,
        signature=valid_signature,
    )

    assert result["status"] == "ok"
    assert result["result"] == {"processed": "user.created", "amount": 1}


@pytest.mark.regression
@pytest.mark.asyncio
async def test_receive_secret_invalid_signature_rejects():
    """Case 4: secret + forged signature → rejected (unchanged from #1814)."""
    secret = "test-webhook-secret-key"
    transport = await _started_transport(WebhookTransport(secret=secret))
    payload = {"event": "user.created", "amount": 1}
    payload_bytes = json.dumps(payload).encode("utf-8")
    # Signature computed with the WRONG secret → invalid.
    forged_signature = _make_signature("attacker-secret", payload_bytes)

    with pytest.raises(ValueError, match="Invalid webhook signature"):
        await transport.receive(
            "process_event",
            payload,
            payload_bytes=payload_bytes,
            signature=forged_signature,
        )
