# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: AlgorithmIdentifier threading on SignedEnvelope (issue #604).

Covers the SignedEnvelope half of #604 — round-trip + verify path.
Other signed-record sites (audit chain, timestamping, CRL, message
signer) are tracked in
``workspaces/issues-604-607/01-analysis/issue-604-signed-record-sites.md``
and threaded in subsequent shards.

Cross-SDK: kailash-rs#33. Wire format: pending mint ISS-31.
"""

from __future__ import annotations

import warnings as _warnings
from datetime import UTC, datetime, timedelta

import pytest

import kailash.trust.pact.envelopes as _envelopes_mod
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
)
from kailash.trust.pact.envelopes import (
    ALGORITHM_DEFAULT,
    AlgorithmIdentifier,
    SignedEnvelope,
    coerce_algorithm_id,
    sign_envelope,
)
from kailash.trust.signing.crypto import generate_keypair


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_legacy_warning():
    """Reset the once-per-process legacy-record DeprecationWarning guard.

    The shared module-level ``_LEGACY_SIGNED_ENVELOPE_WARNED`` flag is
    set ``True`` after first emission across either ``verify()`` or
    ``from_dict()``. Tests that exercise the warning path MUST reset it
    before AND after to make assertions deterministic regardless of
    sibling-test ordering.
    """

    _envelopes_mod._LEGACY_SIGNED_ENVELOPE_WARNED = False
    yield
    _envelopes_mod._LEGACY_SIGNED_ENVELOPE_WARNED = False


@pytest.fixture
def keypair() -> tuple[str, str]:
    """Generate an Ed25519 keypair."""

    return generate_keypair()


@pytest.fixture
def envelope() -> ConstraintEnvelopeConfig:
    """A minimal ConstraintEnvelopeConfig fixture for sign/verify."""

    return ConstraintEnvelopeConfig(
        id="test-env-604",
        description="Issue #604 regression envelope",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(max_spend_usd=100.0),
    )


@pytest.fixture
def signed(envelope, keypair) -> SignedEnvelope:
    private_key, _ = keypair
    return sign_envelope(envelope, private_key, signed_by="D1-R1")


# ---------------------------------------------------------------------------
# AlgorithmIdentifier dataclass
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_alg_identifier_default_value():
    assert AlgorithmIdentifier().algorithm == ALGORITHM_DEFAULT


@pytest.mark.regression
def test_alg_identifier_non_default_raises():
    with pytest.raises(NotImplementedError, match=r"awaits mint ISS-31"):
        AlgorithmIdentifier(algorithm="ed25519+sha512")


@pytest.mark.regression
def test_alg_identifier_frozen():
    alg = AlgorithmIdentifier()
    with pytest.raises(Exception):
        # frozen=True dataclass blocks attribute assignment
        alg.algorithm = "rotated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# coerce_algorithm_id helper
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_coerce_default_fills_none():
    assert coerce_algorithm_id(None) == AlgorithmIdentifier()


@pytest.mark.regression
def test_coerce_passes_existing():
    given = AlgorithmIdentifier()
    assert coerce_algorithm_id(given) is given


# ---------------------------------------------------------------------------
# SignedEnvelope serialisation round-trip
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_to_dict_emits_algorithm(signed):
    dict_form = signed.to_dict()
    assert dict_form["algorithm"] == ALGORITHM_DEFAULT


@pytest.mark.regression
def test_signed_envelope_to_dict_lexicographic_keys(signed):
    """Sorted-key form is the canonical wire shape (deterministic JSON)."""

    keys = sorted(signed.to_dict().keys())
    expected = [
        "algorithm",
        "envelope",
        "expires_at",
        "signature",
        "signed_at",
        "signed_by",
    ]
    assert keys == expected


@pytest.mark.regression
def test_signed_envelope_from_dict_default(signed):
    """Round-trip: to_dict → from_dict preserves algorithm field."""

    reconstructed = SignedEnvelope.from_dict(signed.to_dict())
    assert reconstructed.algorithm == ALGORITHM_DEFAULT


@pytest.mark.regression
def test_signed_envelope_from_dict_non_default_raises(signed):
    payload = signed.to_dict()
    payload["algorithm"] = "ed25519+sha512"
    with pytest.raises(NotImplementedError, match=r"awaits mint ISS-31"):
        SignedEnvelope.from_dict(payload)


# ---------------------------------------------------------------------------
# Legacy-record DeprecationWarning (once per process across verify+from_dict)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_from_dict_legacy_warns(signed, reset_legacy_warning):
    """Pre-#604 dict (no algorithm key) parses + emits DeprecationWarning."""

    payload = signed.to_dict()
    payload.pop("algorithm")
    with pytest.warns(
        DeprecationWarning,
        match=r"scaffold for #604; wire format pending mint ISS-31",
    ):
        reconstructed = SignedEnvelope.from_dict(payload)
    # Defaults applied so subsequent round-trip emits the canonical value.
    assert reconstructed.algorithm == ALGORITHM_DEFAULT


@pytest.mark.regression
def test_legacy_warning_fires_only_once_per_process(signed, reset_legacy_warning):
    """Shared guard suppresses duplicate emission across from_dict + verify."""

    payload = signed.to_dict()
    payload.pop("algorithm")
    # First trigger: emits.
    with pytest.warns(DeprecationWarning, match=r"scaffold for #604"):
        SignedEnvelope.from_dict(payload)
    # Second trigger (same process, guard latched): no new warning.
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always", DeprecationWarning)
        SignedEnvelope.from_dict(payload)
        scaffold_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "scaffold for #604" in str(w.message)
        ]
        assert scaffold_warnings == []


@pytest.mark.regression
def test_signed_envelope_verify_legacy_warns_then_silent(
    signed, keypair, reset_legacy_warning
):
    """Verify path on legacy record warns once, subsequent verifies silent."""

    _, public_key = keypair
    # Force legacy state by reconstructing without algorithm.
    payload = signed.to_dict()
    payload.pop("algorithm")
    # from_dict emits the warning (latches the guard); silence it for setup.
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", DeprecationWarning)
        legacy = SignedEnvelope.from_dict(payload)
    # The reconstructed envelope has algorithm=DEFAULT, so verify() does NOT
    # take the legacy branch. Drop directly into the construct-with-empty-
    # algorithm path used by external persisted records.
    legacy_empty = SignedEnvelope(
        envelope=legacy.envelope,
        signature=legacy.signature,
        signed_at=legacy.signed_at,
        signed_by=legacy.signed_by,
        expires_at=legacy.expires_at,
        algorithm="",
    )
    # Reset the guard so we can observe the verify-path emission cleanly.
    _envelopes_mod._LEGACY_SIGNED_ENVELOPE_WARNED = False
    with pytest.warns(DeprecationWarning, match=r"scaffold for #604"):
        legacy_empty.verify(public_key)


@pytest.mark.regression
def test_signed_envelope_verify_non_default_raises(signed, keypair):
    _, public_key = keypair
    rogue = SignedEnvelope(
        envelope=signed.envelope,
        signature=signed.signature,
        signed_at=signed.signed_at,
        signed_by=signed.signed_by,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        algorithm="ed25519+sha512",
    )
    with pytest.raises(NotImplementedError, match=r"awaits mint ISS-31"):
        rogue.verify(public_key)


# ---------------------------------------------------------------------------
# End-to-end: signed + serialised + reconstructed + verifies
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_round_trip_through_dict_verifies(signed, keypair):
    """Persistence round-trip preserves every field needed for verify()."""

    _, public_key = keypair
    payload = signed.to_dict()
    reconstructed = SignedEnvelope.from_dict(payload)
    assert reconstructed.algorithm == ALGORITHM_DEFAULT
    assert reconstructed.verify(public_key) is True
