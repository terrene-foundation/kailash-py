# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1590 — RFC 8785 (JCS) encoder + conditional
subject_hash on the EATP Audit Anchor (the EATP v3 keystone).

This is a SIGNED CRYPTOGRAPHIC surface — byte-exactness is the security
property. Every JCS assertion here checks output against an INDEPENDENT RFC 8785
published reference string (the RFC's own canonical output), never against the
encoder's own emission.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from kailash.trust._jcs import jcs_encode, jcs_subject_hash
from kailash.trust.pact.audit import (
    SCHEMA_VERSION_V2,
    SCHEMA_VERSION_V3,
    AuditAnchor,
    AuditChain,
)
from kailash.trust.pact.config import VerificationLevel

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# RFC 8785 (JCS) encoder — independent reference vectors
# ---------------------------------------------------------------------------


class TestJcsRfc8785References:
    """jcs_encode output MUST match RFC 8785's PUBLISHED canonical strings."""

    def test_rfc8785_numbers_reference(self) -> None:
        # RFC 8785 §3.2.2 canonical "numbers" example. The RIGHT-HAND SIDE is the
        # RFC's published canonical output — an independent reference, NOT our
        # encoder's own emission.
        subject = {"numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27]}
        assert (
            jcs_encode(subject)
            == '{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
        )

    def test_rfc8785_locale_key_sort_reference(self) -> None:
        # RFC 8785 Appendix B locale/UTF-16 example: keys sort by UTF-16 code
        # unit (peach, péché, pêche, sin) and non-ASCII is emitted as raw UTF-8.
        subject = {
            "peach": "This sorting order",
            "péché": "is wrong according to French",
            "pêche": "but canonicalization MUST",
            "sin": "ignore locale",
        }
        assert jcs_encode(subject) == (
            '{"peach":"This sorting order",'
            '"péché":"is wrong according to French",'
            '"pêche":"but canonicalization MUST",'
            '"sin":"ignore locale"}'
        )

    def test_utf16_supplementary_plane_sorts_before_bmp(self) -> None:
        # U+1D11E (musical G-clef, UTF-16 high surrogate 0xD834) MUST sort BEFORE
        # U+E000 (BMP private-use) by UTF-16 code unit (0xD834 < 0xE000) — the
        # OPPOSITE of code-point order. This is the surrogate-pair case that
        # distinguishes RFC 8785's UTF-16 sort from a naive code-point sort.
        encoded = jcs_encode({"\U0001d11e": 1, "": 2})
        assert encoded.index('"\U0001d11e"') < encoded.index('""')

    @pytest.mark.parametrize(
        "value,expected",
        [
            (1.0, "1"),
            (-0.0, "0"),
            (0.1, "0.1"),
            (100.0, "100"),
            (0.5, "0.5"),
            (-0.5, "-0.5"),
            (1e21, "1e+21"),
            (1e20, "100000000000000000000"),
            (1e-7, "1e-7"),
            (1e-6, "0.000001"),
            (4.5, "4.5"),
            (123.45, "123.45"),
            (1e30, "1e+30"),
            (1e-27, "1e-27"),
        ],
    )
    def test_ecmascript_number_serialization(self, value: float, expected: str) -> None:
        # Each expected value is the ECMAScript Number::toString form mandated by
        # RFC 8785 §3.2.2.3 — distinct from Python repr (1.0→"1.0", 1e-7→"1e-07").
        assert jcs_encode(value) == expected

    def test_non_finite_floats_rejected(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValueError):
                jcs_encode(bad)

    def test_subject_hash_format(self) -> None:
        subject = {"a": 1}
        h = jcs_subject_hash(subject)
        expected = "sha256:" + hashlib.sha256(jcs_encode(subject).encode()).hexdigest()
        assert h == expected
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64


# ---------------------------------------------------------------------------
# EATP v3 AuditAnchor — subject_hash binding + fail-closed discriminator
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)


def _anchor(subject=None, schema_version=None, anchor_id="anc-1590"):
    return AuditAnchor(
        anchor_id=anchor_id,
        sequence=0,
        previous_hash=None,
        agent_id="agent-a",
        action="envelope_created",
        verification_level=VerificationLevel.AUTO_APPROVED,
        envelope_id="env-001",
        result="success",
        metadata={"pact_action": "envelope_created", "role_address": "D1-R1"},
        timestamp=_TS,
        subject=subject,
        schema_version=schema_version,
    )


class TestV3AuditAnchor:
    def test_no_subject_preimage_byte_identical_to_v2(self) -> None:
        """A no-subject v3-path anchor's signed pre-image is BYTE-IDENTICAL to a
        v2.2 anchor's (the core EATP-v3 backward-compat guarantee)."""
        v3_path = _anchor(subject=None)  # v3-aware constructor, no subject
        plain_v2 = _anchor(subject=None, schema_version=SCHEMA_VERSION_V2)
        assert v3_path.schema_version == SCHEMA_VERSION_V2
        # Byte-for-byte identical pre-image AND hash.
        assert v3_path._canonical_input() == plain_v2._canonical_input()
        v3_path.seal()
        plain_v2.seal()
        assert v3_path.content_hash == plain_v2.content_hash
        # No v3 keys leak into serialization for a v2.2 anchor.
        assert "subject" not in v3_path.to_dict()
        assert "subject_hash" not in v3_path.to_dict()
        assert "schema_version" not in v3_path.to_dict()

    def test_subject_present_makes_v3_and_binds_subject_hash(self) -> None:
        anchor = _anchor(subject={"cred": "abc"})
        assert anchor.schema_version == SCHEMA_VERSION_V3
        pre = anchor._canonical_input()
        assert f"subject_hash={jcs_subject_hash({'cred': 'abc'})}" in pre

    def test_subject_hash_absent_from_v2_preimage(self) -> None:
        anchor = _anchor(subject=None)
        assert "subject_hash=" not in anchor._canonical_input()

    def test_float_subject_hash_matches_independent_reference(self) -> None:
        subject = {"numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27]}
        # Independent RFC 8785 canonical string → its sha256 is the subject_hash.
        rfc_canonical = '{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
        expected = "sha256:" + hashlib.sha256(rfc_canonical.encode()).hexdigest()
        assert _anchor(subject=subject)._subject_hash() == expected

    def test_v3_anchor_round_trips_and_verifies(self) -> None:
        anchor = _anchor(subject={"cred": "abc"})
        anchor.seal()
        assert anchor.verify_integrity()
        restored = AuditAnchor.from_dict(anchor.to_dict())
        assert restored.schema_version == SCHEMA_VERSION_V3
        assert restored.subject == {"cred": "abc"}
        assert restored.verify_integrity()
        assert restored.content_hash == anchor.content_hash

    def test_stripping_schema_version_fails_verification(self) -> None:
        """schema_version is EXCLUDED from the signing payload and fail-closed:
        stripping it on a with-subject anchor forces v2.2-shape reconstruction,
        so the recomputed hash diverges and verification REJECTS the record."""
        anchor = _anchor(subject={"cred": "abc"})
        anchor.seal()
        data = anchor.to_dict()
        assert data["schema_version"] == SCHEMA_VERSION_V3
        del data["schema_version"]  # tamper: strip the discriminator

        downgraded = AuditAnchor.from_dict(data)
        # Absent discriminator forces v2.2 reconstruction (NOT re-derived to v3).
        assert downgraded.schema_version == SCHEMA_VERSION_V2
        assert downgraded.subject == {"cred": "abc"}
        # Fail-closed: recomputed hash no longer matches the stored v3 hash.
        assert downgraded.compute_hash() != downgraded.content_hash
        assert not downgraded.verify_integrity()

    def test_stripped_v3_reads_as_tampered_in_chain(self) -> None:
        anchor = _anchor(subject={"cred": "abc"})
        anchor.seal()
        data = anchor.to_dict()
        del data["schema_version"]
        chain = AuditChain("c")
        chain.anchors.append(AuditAnchor.from_dict(data))
        valid, errors = chain.verify_chain_integrity()
        assert valid is False
        assert any("tampered" in e for e in errors)

    def test_tampering_subject_fails_verification(self) -> None:
        anchor = _anchor(subject={"cred": "abc"})
        anchor.seal()
        data = anchor.to_dict()
        data["subject"] = {"cred": "EVIL"}  # tamper the subject payload
        forged = AuditAnchor.from_dict(data)
        # subject_hash is re-derived from subject on verify, so a tampered
        # subject diverges from the stored content_hash.
        assert not forged.verify_integrity()

    def test_append_with_subject_seals_v3(self) -> None:
        """AuditChain.append(subject=...) is the production call site (no orphan)."""
        chain = AuditChain("chain-1590")
        anchor = chain.append(
            "agent-a",
            "clearance_granted",
            VerificationLevel.FLAGGED,
            subject={"did": "did:example:123"},
        )
        assert anchor.schema_version == SCHEMA_VERSION_V3
        assert anchor.verify_integrity()
        valid, errors = chain.verify_chain_integrity()
        assert valid, errors

    def test_append_without_subject_is_v2(self) -> None:
        chain = AuditChain("chain-1590")
        anchor = chain.append(
            "agent-a", "envelope_created", VerificationLevel.AUTO_APPROVED
        )
        assert anchor.schema_version == SCHEMA_VERSION_V2
        assert "subject_hash" not in anchor.to_dict()
