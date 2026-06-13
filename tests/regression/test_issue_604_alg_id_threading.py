# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: EATP-08 v1.1 alg_id conformance on SignedEnvelope (ISS-32).

Covers the SignedEnvelope signed-record surface against
``foundation/docs/02-standards/eatp/08-algorithm-identifier.md@v1.1``:

- the top-level ``alg_id`` wire string (§3.1) that sorts first under JCS
  (§3.2);
- the §3.3 registry default ``eatp-v1`` (NOT the pre-publication scaffold
  literal ``ed25519+sha256``);
- D2b (§4.2): a missing/empty ``alg_id`` on the post-adoption path is
  rejected with ``missing-alg-id-post-adoption`` — NOT silently default-
  filled (the E6 defect this erratum closes);
- D2d (§4.5): the deprecated pre-registry explicit forms are accepted ONLY
  on the bounded legacy path and map to ``eatp-v1``;
- dispatch (§5.1): a Reserved / unregistered token raises
  ``unsupported-algorithm`` and does NOT fall through to ``eatp-v1``.

Cross-SDK sibling: esperie-enterprise/kailash-rs ISS-33.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
)
from kailash.trust.pact.envelopes import (
    ALGORITHM_DEFAULT,
    AlgorithmIdentifier,
    SignedEnvelope,
    UnsupportedAlgorithmError,
    coerce_algorithm_id,
    sign_envelope,
)
from kailash.trust.signing.algorithm_id import (
    DEPRECATED_PRE_REGISTRY_LITERAL,
    resolve_dispatch,
)
from kailash.trust.signing.crypto import generate_keypair

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair() -> tuple[str, str]:
    """Generate an Ed25519 keypair."""

    return generate_keypair()


@pytest.fixture
def envelope() -> ConstraintEnvelopeConfig:
    """A minimal ConstraintEnvelopeConfig fixture for sign/verify."""

    return ConstraintEnvelopeConfig(
        id="test-env-604",
        description="EATP-08 v1.1 regression envelope",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(max_spend_usd=100.0),
    )


@pytest.fixture
def signed(envelope, keypair) -> SignedEnvelope:
    private_key, _ = keypair
    return sign_envelope(envelope, private_key, signed_by="D1-R1")


# ---------------------------------------------------------------------------
# AlgorithmIdentifier dataclass + registry
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_alg_default_is_eatp_v1():
    """EATP-08 §3.3: the registry default is the `eatp-v1` token."""

    assert ALGORITHM_DEFAULT == "eatp-v1"
    assert AlgorithmIdentifier().algorithm == "eatp-v1"


@pytest.mark.regression
def test_alg_identifier_accepts_registered_reserved_token():
    """A Reserved registry token is a valid *value* (but not dispatchable)."""

    alg = AlgorithmIdentifier(algorithm="eatp-v1.1")
    assert alg.algorithm == "eatp-v1.1"
    assert alg.is_active is False


@pytest.mark.regression
def test_alg_identifier_rejects_unregistered_token():
    """An unregistered token raises unsupported-algorithm at construction."""

    with pytest.raises(UnsupportedAlgorithmError) as exc:
        AlgorithmIdentifier(algorithm="ed25519+sha512")
    assert exc.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_alg_identifier_rejects_deprecated_literal_as_value():
    """The deprecated literal is NOT a registry token (only D2d-acceptable)."""

    with pytest.raises(UnsupportedAlgorithmError) as exc:
        AlgorithmIdentifier(algorithm=DEPRECATED_PRE_REGISTRY_LITERAL)
    assert exc.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_alg_identifier_frozen():
    alg = AlgorithmIdentifier()
    with pytest.raises(Exception):
        alg.algorithm = "rotated"  # type: ignore[misc]


@pytest.mark.regression
@pytest.mark.parametrize(
    "token",
    ["eatp-v1.1", "eatp-v2", "eatp-v2.ml-dsa", "eatp-v2.slh-dsa", "bogus"],
)
def test_resolve_dispatch_rejects_non_active(token):
    """EATP-08 §5.1: only Active dispatches; everything else is unsupported."""

    with pytest.raises(UnsupportedAlgorithmError) as exc:
        resolve_dispatch(token)
    assert exc.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_resolve_dispatch_active_eatp_v1():
    entry = resolve_dispatch("eatp-v1")
    assert entry.status.value == "Active"


# ---------------------------------------------------------------------------
# coerce_algorithm_id helper
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_coerce_default_fills_none():
    assert coerce_algorithm_id(None) == AlgorithmIdentifier()
    assert coerce_algorithm_id(None).algorithm == "eatp-v1"


@pytest.mark.regression
def test_coerce_passes_existing():
    given = AlgorithmIdentifier()
    assert coerce_algorithm_id(given) is given


# ---------------------------------------------------------------------------
# SignedEnvelope wire encoding (EATP-08 §3.1 / §3.2)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_to_dict_emits_top_level_alg_id(signed):
    """The wire form carries a top-level `alg_id` string token (§3.1)."""

    dict_form = signed.to_dict()
    assert dict_form["alg_id"] == "eatp-v1"
    # Must be a bare string, NOT a nested {"algorithm": ...} object.
    assert isinstance(dict_form["alg_id"], str)
    assert "algorithm" not in dict_form


@pytest.mark.regression
def test_signed_envelope_alg_id_sorts_first_under_jcs(signed):
    """EATP-08 §3.2: under JCS key ordering `alg_id` lands first."""

    keys = sorted(signed.to_dict().keys())
    assert keys[0] == "alg_id"
    assert keys == [
        "alg_id",
        "envelope",
        "expires_at",
        "signature",
        "signed_at",
        "signed_by",
    ]


@pytest.mark.regression
def test_signed_envelope_from_dict_round_trip(signed):
    """Conformant round-trip: to_dict → from_dict preserves the token."""

    reconstructed = SignedEnvelope.from_dict(signed.to_dict())
    assert reconstructed.alg_id == "eatp-v1"


# ---------------------------------------------------------------------------
# D2b: post-adoption missing/empty alg_id is REJECTED, not default-filled
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_from_dict_missing_alg_id_rejected(signed):
    """EATP-08 §4.2 (D2b) / E6: a missing alg_id MUST NOT be default-filled."""

    payload = signed.to_dict()
    payload.pop("alg_id")
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        SignedEnvelope.from_dict(payload)
    assert exc.value.code == "missing-alg-id-post-adoption"


@pytest.mark.regression
def test_signed_envelope_from_dict_empty_alg_id_rejected(signed):
    payload = signed.to_dict()
    payload["alg_id"] = ""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        SignedEnvelope.from_dict(payload)
    assert exc.value.code == "missing-alg-id-post-adoption"


# ---------------------------------------------------------------------------
# Shape mismatch + unsupported (EATP-08 §3.1 / §3.3 / §5.3)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_from_dict_nested_object_shape_mismatch(signed):
    """A nested {"algorithm": ...} value is non-conformant post-adoption."""

    payload = signed.to_dict()
    payload["alg_id"] = {"algorithm": DEPRECATED_PRE_REGISTRY_LITERAL}
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        SignedEnvelope.from_dict(payload)
    assert exc.value.code == "alg-id-shape-mismatch"


@pytest.mark.regression
def test_signed_envelope_from_dict_deprecated_literal_shape_mismatch(signed):
    """Bare deprecated literal post-adoption is a shape mismatch, not v1."""

    payload = signed.to_dict()
    payload["alg_id"] = DEPRECATED_PRE_REGISTRY_LITERAL
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        SignedEnvelope.from_dict(payload)
    assert exc.value.code == "alg-id-shape-mismatch"


@pytest.mark.regression
def test_signed_envelope_from_dict_unregistered_unsupported(signed):
    """An unregistered token raises unsupported-algorithm, no fall-through."""

    payload = signed.to_dict()
    payload["alg_id"] = "eatp-v9"
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        SignedEnvelope.from_dict(payload)
    assert exc.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_signed_envelope_from_dict_reserved_token_decodes_but_undispatchable(
    signed, keypair
):
    """A Reserved token is a valid registry value: `from_dict` accepts it
    (it is a registered token that may appear on the wire), but verify()
    rejects it as undispatchable per §3.3 / §5.1 — the dispatch gate is at
    verification, not at the decode boundary."""

    _, public_key = keypair
    payload = signed.to_dict()
    payload["alg_id"] = "eatp-v2.ml-dsa"
    reconstructed = SignedEnvelope.from_dict(payload)
    assert reconstructed.alg_id == "eatp-v2.ml-dsa"
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        reconstructed.verify(public_key)
    assert exc.value.code == "unsupported-algorithm"


# ---------------------------------------------------------------------------
# D2d: bounded legacy-path acceptance of pre-registry explicit forms
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_from_dict_d2d_bare_literal(signed):
    """EATP-08 §4.5 (D2d): bare deprecated literal maps to eatp-v1 on the
    legacy path."""

    payload = signed.to_dict()
    payload["alg_id"] = DEPRECATED_PRE_REGISTRY_LITERAL
    reconstructed = SignedEnvelope.from_dict(payload, legacy_path=True)
    assert reconstructed.alg_id == "eatp-v1"


@pytest.mark.regression
def test_signed_envelope_from_dict_d2d_nested_form(signed):
    """D2d: the nested {"algorithm": "ed25519+sha256"} form maps to eatp-v1."""

    payload = signed.to_dict()
    payload["alg_id"] = {"algorithm": DEPRECATED_PRE_REGISTRY_LITERAL}
    reconstructed = SignedEnvelope.from_dict(payload, legacy_path=True)
    assert reconstructed.alg_id == "eatp-v1"


@pytest.mark.regression
def test_signed_envelope_from_dict_d2d_unsigned_metadata_form(signed):
    """D2d: the unsigned top-level `algorithm` metadata form maps to eatp-v1.

    This is kailash-py's historical no-`alg_id` shape (the algorithm rode in
    unsigned caller metadata under `algorithm`); D2d rescues it on the
    bounded legacy path (per the spec's py/rs asymmetry note)."""

    payload = signed.to_dict()
    payload.pop("alg_id")
    payload["algorithm"] = DEPRECATED_PRE_REGISTRY_LITERAL
    reconstructed = SignedEnvelope.from_dict(payload, legacy_path=True)
    assert reconstructed.alg_id == "eatp-v1"


# ---------------------------------------------------------------------------
# verify() dispatch (EATP-08 §5.1)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_signed_envelope_verify_eatp_v1(signed, keypair):
    _, public_key = keypair
    assert signed.verify(public_key) is True


@pytest.mark.regression
def test_signed_envelope_verify_reserved_token_unsupported(signed, keypair):
    """A Reserved alg_id raises unsupported-algorithm BEFORE crypto (§5.1)."""

    _, public_key = keypair
    rogue = SignedEnvelope(
        envelope=signed.envelope,
        signature=signed.signature,
        signed_at=signed.signed_at,
        signed_by=signed.signed_by,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        alg_id="eatp-v2.ml-dsa",
    )
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        rogue.verify(public_key)
    assert exc.value.code == "unsupported-algorithm"


# ---------------------------------------------------------------------------
# End-to-end: signed + serialised + reconstructed + verifies
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_round_trip_through_dict_verifies(signed, keypair):
    """Persistence round-trip preserves every field needed for verify()."""

    _, public_key = keypair
    payload = signed.to_dict()
    reconstructed = SignedEnvelope.from_dict(payload)
    assert reconstructed.alg_id == "eatp-v1"
    assert reconstructed.verify(public_key) is True
