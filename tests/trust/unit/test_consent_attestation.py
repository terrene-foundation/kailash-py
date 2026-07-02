# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ConsentAttestation + ConsentLedger (issue #1481).

Covers:
- document_hash covers the EXACT rendered bytes.
- sign -> verify round-trip through the ledger.
- tampered document_hash / typed_name / assent_signals -> verify fails.
- chain linkage + head-anchor holds; a broken link is rejected.
- frozen immutability and lossless to_dict/from_dict round-trip.

Tier 1 (real crypto, no mocking — pynacl is a hard dependency of the primitive).
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from kailash.trust.consent import (
    ConsentAttestation,
    ConsentChainError,
    ConsentLedger,
    hash_document,
    verify_consent_attestation,
)
from kailash.trust.signing import generate_keypair

_GENESIS = "0" * 64


@pytest.fixture
def keypair():
    priv, pub = generate_keypair()
    return priv, pub


@pytest.fixture
def ledger(keypair):
    priv, pub = keypair
    return ConsentLedger(signing_private_key=priv, signing_public_key=pub)


# ---------------------------------------------------------------------------
# hash_document
# ---------------------------------------------------------------------------


class TestHashDocument:
    def test_hashes_exact_utf8_bytes(self):
        text = "I accept the terms and conditions."
        assert hash_document(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_bytes_input_hashed_verbatim(self):
        raw = b"\x00\x01exact-bytes\xff"
        assert hash_document(raw) == hashlib.sha256(raw).hexdigest()

    def test_str_and_equivalent_bytes_agree(self):
        text = "unicode: 漢字 é"
        assert hash_document(text) == hash_document(text.encode("utf-8"))

    def test_single_byte_change_changes_hash(self):
        assert hash_document("terms A") != hash_document("terms B")

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            hash_document(1234)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Sign -> verify round-trip
# ---------------------------------------------------------------------------


class TestSignVerifyRoundTrip:
    def test_recorded_attestation_verifies(self, ledger, keypair):
        _, pub = keypair
        att = ledger.record_consent(
            human_origin_id="user-42",
            document="I accept the terms.",
            document_version="tos-v3",
            typed_name="Ada Lovelace",
            assent_signals={
                "scrolled_to_end": True,
                "dwell_ms": 8200,
                "method": "click",
            },
            ip_address="203.0.113.7",
            user_agent="Mozilla/5.0",
        )
        assert att.document_hash == hash_document("I accept the terms.")
        assert att.verify_integrity() is True
        assert verify_consent_attestation(att, pub) is True

    def test_verify_fails_with_wrong_public_key(self, ledger):
        other_priv, other_pub = generate_keypair()
        att = ledger.record_consent(
            human_origin_id="user-1",
            document="doc",
            document_version="v1",
            typed_name="Grace Hopper",
        )
        assert verify_consent_attestation(att, other_pub) is False

    def test_dual_signature_hmac_path(self, keypair):
        priv, pub = keypair
        hmac_key = b"shared-internal-hmac-key-32bytes!"
        led = ConsentLedger(
            signing_private_key=priv, signing_public_key=pub, hmac_key=hmac_key
        )
        att = led.record_consent(
            human_origin_id="user-9",
            document="doc",
            document_version="v1",
            typed_name="Katherine Johnson",
        )
        assert att.hmac_signature is not None
        assert verify_consent_attestation(att, pub, hmac_key=hmac_key) is True


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


class TestTamperDetection:
    def _record(self, ledger):
        return ledger.record_consent(
            human_origin_id="user-42",
            document="I accept.",
            document_version="v1",
            typed_name="Ada Lovelace",
            assent_signals={"scrolled_to_end": True},
        )

    def test_tampered_document_hash_fails(self, ledger, keypair):
        _, pub = keypair
        att = self._record(ledger)
        tampered = dataclasses.replace(att, document_hash="0" * 64)
        assert tampered.verify_integrity() is False
        assert verify_consent_attestation(tampered, pub) is False

    def test_tampered_typed_name_fails(self, ledger, keypair):
        _, pub = keypair
        att = self._record(ledger)
        tampered = dataclasses.replace(att, typed_name="Someone Else")
        assert tampered.verify_integrity() is False
        assert verify_consent_attestation(tampered, pub) is False

    def test_tampered_assent_signals_fails(self, ledger, keypair):
        _, pub = keypair
        att = self._record(ledger)
        tampered = dataclasses.replace(att, assent_signals={"scrolled_to_end": False})
        assert tampered.verify_integrity() is False
        assert verify_consent_attestation(tampered, pub) is False

    def test_tampered_prev_hash_fails(self, ledger, keypair):
        _, pub = keypair
        att = self._record(ledger)
        tampered = dataclasses.replace(att, prev_hash="f" * 64)
        assert tampered.verify_integrity() is False
        assert verify_consent_attestation(tampered, pub) is False

    def test_signature_transplant_across_slot_fails(self, ledger, keypair):
        # A valid signature from slot 0 does not validate against a different
        # prev_hash (chain position is part of the signed pre-image).
        _, pub = keypair
        att = self._record(ledger)
        transplanted = dataclasses.replace(att, prev_hash="a" * 64)
        assert verify_consent_attestation(transplanted, pub) is False


# ---------------------------------------------------------------------------
# Chain linkage / head-anchor
# ---------------------------------------------------------------------------


class TestChainLinkage:
    def test_first_attestation_anchored_to_genesis(self, ledger):
        att = ledger.record_consent(
            human_origin_id="u1", document="d", document_version="v1", typed_name="A"
        )
        assert att.prev_hash == _GENESIS

    def test_second_links_to_first(self, ledger):
        a1 = ledger.record_consent(
            human_origin_id="u1", document="d1", document_version="v1", typed_name="A"
        )
        a2 = ledger.record_consent(
            human_origin_id="u2", document="d2", document_version="v1", typed_name="B"
        )
        assert a2.prev_hash == a1.hash
        assert ledger.head_hash == a2.hash

    def test_verify_chain_holds(self, ledger):
        for i in range(5):
            ledger.record_consent(
                human_origin_id=f"u{i}",
                document=f"doc-{i}",
                document_version="v1",
                typed_name=f"Name {i}",
            )
        assert ledger.count == 5
        assert ledger.verify_chain() is True

    def test_append_broken_link_rejected(self, ledger, keypair):
        priv, pub = keypair
        ledger.record_consent(
            human_origin_id="u1", document="d", document_version="v1", typed_name="A"
        )
        # Build a foreign attestation whose prev_hash does not match head.
        foreign = ConsentLedger(signing_private_key=priv, signing_public_key=pub)
        bad = foreign.record_consent(
            human_origin_id="u2", document="d2", document_version="v1", typed_name="B"
        )
        # bad.prev_hash is genesis, but ledger.head_hash is a1.hash → mismatch.
        with pytest.raises(ConsentChainError):
            ledger.append(bad)

    def test_duplicate_consent_id_rejected(self, ledger):
        ledger.record_consent(
            human_origin_id="u1",
            document="d",
            document_version="v1",
            typed_name="A",
            consent_id="fixed-id",
        )
        with pytest.raises(ConsentChainError):
            ledger.record_consent(
                human_origin_id="u2",
                document="d2",
                document_version="v1",
                typed_name="B",
                consent_id="fixed-id",
            )

    def test_get_and_list_for_human(self, ledger):
        ledger.record_consent(
            human_origin_id="alice",
            document="d",
            document_version="v1",
            typed_name="A",
            consent_id="c-alice-1",
        )
        ledger.record_consent(
            human_origin_id="bob", document="d", document_version="v1", typed_name="B"
        )
        ledger.record_consent(
            human_origin_id="alice",
            document="d2",
            document_version="v2",
            typed_name="A",
        )
        assert ledger.get("c-alice-1") is not None
        assert len(ledger.list_for_human("alice")) == 2
        assert len(ledger.list_for_human("bob")) == 1


# ---------------------------------------------------------------------------
# Frozen + serialization
# ---------------------------------------------------------------------------


class TestFrozenAndSerialization:
    def test_frozen(self, ledger):
        att = ledger.record_consent(
            human_origin_id="u1", document="d", document_version="v1", typed_name="A"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            att.typed_name = "hacker"  # type: ignore[misc]

    def test_to_from_dict_roundtrip(self, ledger, keypair):
        _, pub = keypair
        att = ledger.record_consent(
            human_origin_id="u1",
            document="d",
            document_version="v1",
            typed_name="A",
            assent_signals={"scrolled_to_end": True, "dwell_ms": 42},
            metadata={"channel": "web"},
        )
        restored = ConsentAttestation.from_dict(att.to_dict())
        assert restored == att
        assert restored.verify_integrity() is True
        assert verify_consent_attestation(restored, pub) is True


class TestLedgerConstruction:
    def test_missing_private_key_raises(self):
        _, pub = generate_keypair()
        with pytest.raises(Exception):
            ConsentLedger(signing_private_key="", signing_public_key=pub)
