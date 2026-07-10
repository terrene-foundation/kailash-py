# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1510 — BH3 origin-authentication.

Binds an agent-declared action-trace to its ORIGINATING INSTRUCTION so a
fabricated trace FAILS authentication even when its Ed25519 signature verifies.
Real crypto throughout (ephemeral fixture keys); the signer is NEVER mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("nacl")  # real Ed25519 — never mocked (testing.md Tier 2/3)

from kailash.trust.reasoning.origin import (  # noqa: E402
    OriginBoundTrace,
    compute_origin_digest,
    origin_signing_payload,
    sign_origin_bound_trace,
    verify_origin_bound_trace,
)
from kailash.trust.reasoning.traces import (  # noqa: E402
    ConfidentialityLevel,
    ReasoningTrace,
)
from kailash.trust.signing.crypto import (  # noqa: E402
    generate_keypair,
    serialize_for_signing,
    sign_reasoning_trace,
    verify_reasoning_signature,
)

pytestmark = pytest.mark.regression

_TS = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)


def _trace() -> ReasoningTrace:
    return ReasoningTrace(
        decision="approve deploy",
        rationale="cost within envelope",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=_TS,
        alternatives_considered=["defer"],
        evidence=[{"cost": 500}],
        methodology="cost_benefit",
        confidence=0.9,
    )


_INSTRUCTION = {
    "instruction": "deploy service X to staging",
    "issued_by": "D1-R1",
    "nonce": "abc123",
}
# A DIFFERENT instruction — the attacker's real origin, distinct from what the
# fabricated trace declares.
_OTHER_INSTRUCTION = {
    "instruction": "delete prod database",
    "issued_by": "D1-R1",
    "nonce": "abc123",
}


@pytest.fixture
def keypair():
    return generate_keypair()  # (private, public)


# ---------------------------------------------------------------------------
# (a) without-origin record is byte-identical to a pre-BH3 trace signature
# ---------------------------------------------------------------------------


class TestUnboundByteIdentity:
    def test_unbound_preimage_byte_identical_to_current_trace(self) -> None:
        trace = _trace()
        bh3 = serialize_for_signing(origin_signing_payload(trace))
        current = serialize_for_signing(trace.to_signing_payload())
        assert bh3 == current  # backward-compat: no origin field in the bytes

    def test_unbound_signature_verifies_via_pre_bh3_path(self, keypair) -> None:
        """An unbound BH3 signature is a plain trace signature: the SAME bytes
        the pre-BH3 sign_reasoning_trace/verify_reasoning_signature path uses."""
        priv, pub = keypair
        trace = _trace()
        record = sign_origin_bound_trace(trace, priv, "D1-R1-agent")
        assert record.origin_bound is False
        assert record.origin_digest is None
        # BH3 verify passes with no instruction (backward-compatible path).
        assert verify_origin_bound_trace(record, pub) is True
        # And the SAME signature verifies through the pre-BH3 reasoning path —
        # proving byte-identity of the pre-image.
        pre_bh3_sig = sign_reasoning_trace(trace, priv)
        assert record.signature == pre_bh3_sig
        assert verify_reasoning_signature(trace, record.signature, pub) is True


# ---------------------------------------------------------------------------
# (b) with-origin verify passes when authenticated against the true instruction
# ---------------------------------------------------------------------------


class TestBoundVerifyPasses:
    def test_bound_record_authenticates_against_true_origin(self, keypair) -> None:
        priv, pub = keypair
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        assert record.origin_bound is True
        assert record.origin_digest == compute_origin_digest(_INSTRUCTION)
        assert (
            verify_origin_bound_trace(record, pub, originating_instruction=_INSTRUCTION)
            is True
        )


# ---------------------------------------------------------------------------
# (c) fabricated / mismatched origin FAILS despite a valid signature
# ---------------------------------------------------------------------------


class TestFabricatedOriginRejected:
    def test_fabricated_origin_fails_despite_valid_signature(self, keypair) -> None:
        """The core BH3 gap: a key-holding agent signs a valid trace but the
        declared origin does NOT match the authoritative originating
        instruction. The Ed25519 signature verifies; origin auth REJECTS."""
        priv, pub = keypair
        # Agent signs a record CLAIMING origin = _INSTRUCTION.
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        # Sanity: the Ed25519 signature IS valid over the signed pre-image.
        from kailash.trust.signing.crypto import verify_signature

        preimage = serialize_for_signing(
            origin_signing_payload(record.trace, origin_digest=record.origin_digest)
        )
        assert verify_signature(preimage, record.signature, pub) is True
        # But the verifier holds a DIFFERENT authoritative instruction → REJECT.
        assert (
            verify_origin_bound_trace(
                record, pub, originating_instruction=_OTHER_INSTRUCTION
            )
            is False
        )

    def test_bound_record_without_instruction_fails_closed(self, keypair) -> None:
        """A bound record makes an origin CLAIM; passing it on integrity alone
        (no authoritative instruction) is the 'record of what the agent
        reported' failure SAFR warns against — fail-closed."""
        priv, pub = keypair
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        assert verify_origin_bound_trace(record, pub) is False

    def test_unbound_record_when_origin_demanded_fails_closed(self, keypair) -> None:
        """Downgrade defense: an unbound record cannot satisfy a caller that
        DEMANDS origin authentication."""
        priv, pub = keypair
        record = sign_origin_bound_trace(_trace(), priv, "D1-R1-agent")
        assert (
            verify_origin_bound_trace(record, pub, originating_instruction=_INSTRUCTION)
            is False
        )


# ---------------------------------------------------------------------------
# (d) stripping the discriminator fails closed (the #1590 schema_version trick)
# ---------------------------------------------------------------------------


class TestDiscriminatorStripFailsClosed:
    def test_stripping_origin_bound_forces_unbound_reconstruction(
        self, keypair
    ) -> None:
        """origin_bound is EXCLUDED from the signed pre-image. Stripping it on a
        with-origin record forces the without-origin reconstruction, so the
        signature (made over the with-origin bytes) no longer matches → REJECT,
        both with and without the authoritative instruction."""
        priv, pub = keypair
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        data = record.to_dict()
        assert data["origin_bound"] is True
        del data["origin_bound"]  # tamper: strip the discriminator

        downgraded = OriginBoundTrace.from_dict(data)
        # Absent discriminator defaults to unbound (NOT re-derived to bound).
        assert downgraded.origin_bound is False
        assert downgraded.origin_digest is None
        # Fail-closed with origin demanded (downgrade defense)...
        assert (
            verify_origin_bound_trace(
                downgraded, pub, originating_instruction=_INSTRUCTION
            )
            is False
        )
        # ...AND fail-closed even with NO instruction: the signature was made
        # over the with-origin pre-image, but the unbound reconstruction omits
        # the origin key → signature mismatch → REJECT.
        assert verify_origin_bound_trace(downgraded, pub) is False

    def test_flipping_origin_bound_true_but_dropping_digest_fails_closed(
        self, keypair
    ) -> None:
        priv, pub = keypair
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        data = record.to_dict()
        del data["origin_digest"]  # claims bound, but no digest
        tampered = OriginBoundTrace.from_dict(data)
        assert tampered.origin_bound is True
        assert tampered.origin_digest is None
        assert (
            verify_origin_bound_trace(
                tampered, pub, originating_instruction=_INSTRUCTION
            )
            is False
        )


# ---------------------------------------------------------------------------
# round-trip + tamper on the trace body
# ---------------------------------------------------------------------------


class TestRoundTripAndTamper:
    def test_bound_record_round_trips_through_dict(self, keypair) -> None:
        priv, pub = keypair
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        restored = OriginBoundTrace.from_dict(record.to_dict())
        assert restored.origin_bound is True
        assert restored.origin_digest == record.origin_digest
        assert (
            verify_origin_bound_trace(
                restored, pub, originating_instruction=_INSTRUCTION
            )
            is True
        )

    def test_tampering_the_trace_body_fails_verification(self, keypair) -> None:
        priv, pub = keypair
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        data = record.to_dict()
        data["trace"]["decision"] = "approve DELETE prod"  # tamper the trace
        forged = OriginBoundTrace.from_dict(data)
        # Origin still matches, but the trace body changed → signature mismatch.
        assert (
            verify_origin_bound_trace(forged, pub, originating_instruction=_INSTRUCTION)
            is False
        )

    def test_wrong_public_key_fails(self, keypair) -> None:
        priv, _pub = keypair
        _other_priv, other_pub = generate_keypair()
        record = sign_origin_bound_trace(
            _trace(), priv, "D1-R1-agent", originating_instruction=_INSTRUCTION
        )
        assert (
            verify_origin_bound_trace(
                record, other_pub, originating_instruction=_INSTRUCTION
            )
            is False
        )
