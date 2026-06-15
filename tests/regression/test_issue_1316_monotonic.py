# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: EATP-08 §4.2 / §4.5.3 / §5.1-step-3 monotonic-upgrade-violation.

Shard 3A of #1316. Once a principal-chain has emitted a registry-form (v2 /
eatp-v1) record, a subsequent absent-`alg_id` OR pre-registry explicit form is a
downgrade and MUST be rejected with `monotonic-upgrade-violation` — taking
precedence over D2a/D2d acceptance AND over `missing-alg-id-post-adoption`. The
verifier supplies the prior-v2 state either as an explicit
`prior_registry_form_seen` flag OR via a resolved `D2dWitness` carrying a signed
`first_v2_seen` (§4.3.1 — the boundary lives in the signed marker).

This is the read-side enforcement; per journal/0006 there is no marker store (D2c
is signed-not-remembered), so the WRITE side that SETS the signal is
verifier-integration, out of #1316 scope.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.signing.algorithm_id import (
    ALGORITHM_DEFAULT,
    AlgorithmIdentifier,
    D2dVerifierKeys,
    D2dWitness,
    UnsupportedAlgorithmError,
    decode_wire_alg_id,
)
from kailash.trust.signing.crl import CRLMetadata
from kailash.trust.signing.crypto import (
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)

_PRIV, _PUB = generate_keypair()
_WID = "eatp08-monotonic-witness"
_BEFORE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _verifier_keys() -> D2dVerifierKeys:
    return D2dVerifierKeys(keys={_WID: _PUB})


def _signed_pre_adoption_witness(first_v2_seen: datetime | None = None) -> D2dWitness:
    principal = "chain:eatp08-monotonic"
    payload = {"principal": principal, "first_seen": _BEFORE.isoformat()}
    if first_v2_seen is not None:
        payload["first_v2_seen"] = first_v2_seen.isoformat()
    return D2dWitness(
        witnessed_at=_BEFORE,
        chain_head_date=_BEFORE,
        principal=principal,
        first_seen=_BEFORE,
        marker_sig=sign(payload, _PRIV),
        witness_id=_WID,
        first_v2_seen=first_v2_seen,
    )


# ---------------------------------------------------------------------------
# M2 assertion 1 — monotonic replay
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_monotonic_replay_after_prior_v2_rejects_stripped_record():
    """A first-v2 record decodes fine (no prior v2); a SUBSEQUENT stripped record
    on the same chain (prior_registry_form_seen=True) MUST reject with
    monotonic-upgrade-violation."""
    # First emission: a conformant eatp-v1 record, fresh chain — accepts.
    assert decode_wire_alg_id({"alg_id": "eatp-v1"}) == "eatp-v1"
    # Replay: the chain has now emitted v2; a stripped record is a downgrade.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"payload": "v2-record-with-alg_id-stripped"},
            prior_registry_form_seen=True,
        )
    assert exc.value.code == "monotonic-upgrade-violation"


# ---------------------------------------------------------------------------
# M2 assertion 2 — §4.1.3 D2a trust-store-no-prior-v2 (D2a refused when prior v2)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_d2a_acceptance_refused_when_chain_has_prior_v2():
    """§4.1.3: D2a acceptance ALSO requires the trust store hold NO v2 record for
    the chain. An otherwise-valid signed pre-adoption witness (which WOULD accept
    as eatp-v1) MUST be refused with monotonic-upgrade-violation when the chain has
    already emitted a registry-form record — the monotonic check precedes D2a/D2d
    acceptance (§5.1 step 3)."""
    # Sanity: without prior-v2, the same witness accepts under D2a/D2d.
    assert (
        decode_wire_alg_id(
            {"algorithm": ""},
            witness=_signed_pre_adoption_witness(),
            verifier_keys=_verifier_keys(),
        )
        == ALGORITHM_DEFAULT
    )
    # With prior-v2, the SAME acceptance is refused.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"algorithm": ""},
            witness=_signed_pre_adoption_witness(),
            verifier_keys=_verifier_keys(),
            prior_registry_form_seen=True,
        )
    assert exc.value.code == "monotonic-upgrade-violation"


# ---------------------------------------------------------------------------
# Signed first_v2_seen marker path (§4.3.1 — boundary in the signed bytes)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_first_v2_seen_marker_triggers_monotonic_without_explicit_flag():
    """A resolved marker carrying first_v2_seen is itself the prior-v2 signal: a
    pre-registry / absent record decoded against it MUST reject with
    monotonic-upgrade-violation even when prior_registry_form_seen is left
    False (§4.3.1 — the boundary lives in the signed marker)."""
    witness = _signed_pre_adoption_witness(first_v2_seen=_BEFORE)
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"alg_id": {"algorithm": "ed25519+sha256"}},
            witness=witness,
            verifier_keys=_verifier_keys(),
        )
    assert exc.value.code == "monotonic-upgrade-violation"


@pytest.mark.regression
def test_first_v2_seen_is_in_signed_marker_bytes_when_set():
    """§4.3.1: first_v2_seen, when set, is inside the marker_sig pre-image — a
    verifier relying on it gets tamper protection. A marker WITHOUT it keeps the
    two-field {principal, first_seen} core (back-compat)."""
    fv2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    w = _signed_pre_adoption_witness(first_v2_seen=fv2)
    payload = w.signed_marker_payload()
    assert payload["first_v2_seen"] == fv2.isoformat()
    assert w.marker_sig is not None
    marker_sig = w.marker_sig
    # The genuine signed bytes verify…
    assert verify_signature(payload, marker_sig, _PUB) is True
    # …and tampering first_v2_seen breaks verification (it IS signed).
    tampered = dict(payload)
    tampered["first_v2_seen"] = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    assert verify_signature(tampered, marker_sig, _PUB) is False
    # Back-compat: a marker with no first_v2_seen keeps the two-field core.
    w0 = _signed_pre_adoption_witness()
    assert "first_v2_seen" not in w0.signed_marker_payload()
    assert serialize_for_signing(w0.signed_marker_payload())  # serialisable


# ---------------------------------------------------------------------------
# Over-block guards — a conformant v2 record is NOT blocked by prior-v2
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_conformant_token_not_blocked_by_prior_v2():
    """prior_registry_form_seen=True MUST NOT block a proper conformant registry
    token — only an absent/pre-registry downgrade. A chain emitting eatp-v1 after
    eatp-v1 is forward progress, not a violation."""
    assert (
        decode_wire_alg_id({"alg_id": "eatp-v1"}, prior_registry_form_seen=True)
        == "eatp-v1"
    )


@pytest.mark.regression
def test_bare_unregistered_string_keeps_unsupported_not_monotonic():
    """A bare unregistered top-level string is NOT a pre-registry form (v1.1.1):
    it stays unsupported-algorithm even from a prior-v2 chain — monotonic only
    covers absent-alg_id and recognized pre-registry forms (§5.3)."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"alg_id": "ed25519+sha256"}, prior_registry_form_seen=True)
    assert exc.value.code == "unsupported-algorithm"


# ---------------------------------------------------------------------------
# Precedence + through-consumer (orphan-detection: behavioral, via the facade)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_monotonic_precedes_d2d_accept_for_pre_registry_nested():
    """§4.5.3: once a registry-form record appears, the pre-registry form is
    rejected with monotonic-upgrade-violation — even with a valid signed
    pre-adoption witness that would otherwise accept it as eatp-v1."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"alg_id": {"algorithm": "ed25519+sha256"}},
            witness=_signed_pre_adoption_witness(),
            verifier_keys=_verifier_keys(),
            prior_registry_form_seen=True,
        )
    assert exc.value.code == "monotonic-upgrade-violation"


@pytest.mark.regression
def test_monotonic_threads_through_from_dict_surface():
    """The exported AlgorithmIdentifier.from_dict honors prior_registry_form_seen
    for direct callers (the v1.1.1 both-keys-style direct surface)."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        AlgorithmIdentifier.from_dict(
            {"alg_id": {"algorithm": "ed25519+sha256"}},
            witness=_signed_pre_adoption_witness(),
            verifier_keys=_verifier_keys(),
            prior_registry_form_seen=True,
        )
    assert exc.value.code == "monotonic-upgrade-violation"


@pytest.mark.regression
def test_monotonic_threads_through_consumer_from_dict():
    """Orphan-detection (agents.md): the prior_registry_form_seen signal reaches a
    real consumer (CRLMetadata.from_dict) and rejects a stripped record with
    monotonic-upgrade-violation through the production facade — not just the
    decode helper in isolation. The monotonic check fires on alg_id decode BEFORE
    other field parsing, so no other CRL fields are needed."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        CRLMetadata.from_dict(
            {"payload": "v2-crl-with-alg_id-stripped"},
            prior_registry_form_seen=True,
        )
    assert exc.value.code == "monotonic-upgrade-violation"
