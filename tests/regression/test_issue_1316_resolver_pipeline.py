# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: EATP-08 §5.1 resolver-dispatch pipeline, end-to-end (#1316 Shard 5).

`testing.md` § "End-to-End Pipeline Regression Above Unit + Integration". The
per-path unit tests (`test_issue_1316_d2c_marker.py`, `test_issue_1316_monotonic.py`,
`test_eatp08_alg_id_canonical_vectors.py`) each exercise ONE decode branch in
isolation via `decode_wire_alg_id`. This module exercises the COMPOSED §5.1
resolver dispatch — D2a / D2b / D2c / D2d + the §4.5.3 monotonic boundary —
through a REAL signed-record consumer facade (`CRLMetadata.from_dict`), asserting
the final accept/reject outcome a user observes, not a single-path unit.

Why a composed test is load-bearing (the fake-integration risk this catches):
the frozen `D2dWitness` gained fields (`marker_sig`, `first_v2_seen`) that may be
`None` at construction; a consumer that forwards `witness=` into the composed
decode path must handle a `None` `marker_sig` with a typed
`implicit-v1-witness-failure`, NOT crash with an opaque `AttributeError` /
`TypeError`. A single-path unit that always builds a fully-populated witness
never observes that composed-path None.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.signing.algorithm_id import (
    ALGORITHM_DEFAULT,
    D2dVerifierKeys,
    D2dWitness,
    UnsupportedAlgorithmError,
)
from kailash.trust.signing.crl import CRLMetadata
from kailash.trust.signing.crypto import generate_keypair, sign

_PRIV, _PUB = generate_keypair()
_WID = "eatp08-pipeline-witness"
_BEFORE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _verifier_keys() -> D2dVerifierKeys:
    return D2dVerifierKeys(keys={_WID: _PUB})


def _signed_pre_adoption_witness(first_v2_seen: datetime | None = None) -> D2dWitness:
    principal = "chain:eatp08-pipeline"
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


def _base_crl_dict() -> dict:
    """A valid conformant CRL wire dict (alg_id='eatp-v1'), via a real round-trip
    through the production `to_dict`. Mutated per-test to craft each D2 form."""
    crl = CRLMetadata(
        crl_id="crl-001",
        issuer_id="issuer-ca",
        issued_at=_BEFORE,
        next_update=None,
        entry_count=0,
    )
    return crl.to_dict()


@pytest.mark.regression
def test_pipeline_d2c_conformant_round_trip_accepts():
    """D2c / V1: a conformant `eatp-v1` record round-trips through the real
    consumer facade — to_dict() → from_dict() → alg_id resolves, no crash on the
    composed path (the fake-integration smoke test)."""
    data = _base_crl_dict()
    assert data["alg_id"] == "eatp-v1"
    crl = CRLMetadata.from_dict(data)
    assert crl.alg_id == ALGORITHM_DEFAULT == "eatp-v1"
    assert crl.crl_id == "crl-001"  # the rest of the record reconstructs too


@pytest.mark.regression
def test_pipeline_d2b_missing_alg_id_rejects():
    """D2b: a post-adoption record stripped of `alg_id`, no witness → the composed
    resolver rejects with missing-alg-id-post-adoption through the facade."""
    data = _base_crl_dict()
    del data["alg_id"]
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        CRLMetadata.from_dict(data)
    assert exc.value.code == "missing-alg-id-post-adoption"


@pytest.mark.regression
def test_pipeline_d2d_nested_pre_registry_witnessed_accepts():
    """D2d: a nested pre-registry explicit form + a signed pre-adoption marker
    resolves to eatp-v1 through the facade (the composed D2d accept)."""
    data = _base_crl_dict()
    data["alg_id"] = {"algorithm": "ed25519+sha256"}
    crl = CRLMetadata.from_dict(
        data,
        witness=_signed_pre_adoption_witness(),
        verifier_keys=_verifier_keys(),
    )
    assert crl.alg_id == "eatp-v1"


@pytest.mark.regression
def test_pipeline_d2a_unsigned_metadata_witnessed_accepts():
    """D2a/D2d: a record carrying the algorithm only in unsigned `algorithm`
    metadata (no top-level alg_id) + a signed pre-adoption marker resolves to
    eatp-v1 through the facade."""
    data = _base_crl_dict()
    del data["alg_id"]
    data["algorithm"] = "ed25519+sha256"
    crl = CRLMetadata.from_dict(
        data,
        witness=_signed_pre_adoption_witness(),
        verifier_keys=_verifier_keys(),
    )
    assert crl.alg_id == "eatp-v1"


@pytest.mark.regression
def test_pipeline_monotonic_replay_rejects_through_facade():
    """§4.5.3: a stripped record from a prior-v2 chain rejects with
    monotonic-upgrade-violation through the facade — precedence over the D2b
    missing path the same stripped record would otherwise hit."""
    data = _base_crl_dict()
    del data["alg_id"]
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        CRLMetadata.from_dict(data, prior_registry_form_seen=True)
    assert exc.value.code == "monotonic-upgrade-violation"


@pytest.mark.regression
def test_pipeline_unsigned_witness_none_marker_sig_fails_typed_not_crash():
    """The fake-integration guard: a consumer forwarding an UNSIGNED witness
    (marker_sig=None) into the composed decode on a pre-registry form MUST surface
    the typed implicit-v1-witness-failure, NOT crash on the None field. This is the
    composed-path failure single-path units (which always build a full witness)
    never observe."""
    data = _base_crl_dict()
    data["alg_id"] = {"algorithm": "ed25519+sha256"}
    unsigned = D2dWitness(
        witnessed_at=_BEFORE, chain_head_date=_BEFORE
    )  # marker_sig=None
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        CRLMetadata.from_dict(data, witness=unsigned, verifier_keys=_verifier_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_pipeline_composed_sequence_each_outcome():
    """The composed resolver dispatch in one sequence through the real facade:
    every D2 form decoded back-to-back, asserting each final outcome — the
    end-to-end demonstration that the dispatch table holds together (not just
    each branch in isolation)."""
    base = _base_crl_dict()

    # 1. D2c conformant → accept eatp-v1
    assert CRLMetadata.from_dict(dict(base)).alg_id == "eatp-v1"

    # 2. D2b missing → reject
    d_missing = dict(base)
    del d_missing["alg_id"]
    with pytest.raises(UnsupportedAlgorithmError) as e2:
        CRLMetadata.from_dict(d_missing)
    assert e2.value.code == "missing-alg-id-post-adoption"

    # 3. D2d nested + signed witness → accept eatp-v1
    d_nested = dict(base)
    d_nested["alg_id"] = {"algorithm": "ed25519+sha256"}
    assert (
        CRLMetadata.from_dict(
            d_nested,
            witness=_signed_pre_adoption_witness(),
            verifier_keys=_verifier_keys(),
        ).alg_id
        == "eatp-v1"
    )

    # 4. Monotonic replay (prior-v2 via signed first_v2_seen marker) → reject
    d_replay = dict(base)
    d_replay["alg_id"] = {"algorithm": "ed25519+sha256"}
    with pytest.raises(UnsupportedAlgorithmError) as e4:
        CRLMetadata.from_dict(
            d_replay,
            witness=_signed_pre_adoption_witness(first_v2_seen=_BEFORE),
            verifier_keys=_verifier_keys(),
        )
    assert e4.value.code == "monotonic-upgrade-violation"

    # 5. Unregistered token → reject (never falls through to eatp-v1)
    d_unreg = dict(base)
    d_unreg["alg_id"] = "ed25519+sha512"
    with pytest.raises(UnsupportedAlgorithmError) as e5:
        CRLMetadata.from_dict(d_unreg)
    assert e5.value.code == "unsupported-algorithm"
