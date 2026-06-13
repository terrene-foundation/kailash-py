# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK byte-pin conformance for the EATP-08 v1.1 algorithm identifier.

These vectors are the canonical author surface for the `alg_id` wire contract
(kailash-py implements EATP-08 v1.1 first; kailash-rs vendors this file
byte-for-byte per esperie-enterprise/kailash-rs#1315). The test re-derives every
pinned `canonical_member` + `expected_sha256` from the live implementation and
exercises the §4 decode regime against the documented non-conformant forms, so a
future refactor that drifts the wire shape fails loudly here.

See rules/cross-sdk-inspection.md Rule 4 (pin actual byte vectors + sentinels)
and Rule 4a (sibling-canonical fixtures are vendored, not re-authored).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.trust.signing.algorithm_id import (
    ADOPTION_DATE_PARSED,
    ALGORITHM_DEFAULT,
    ALGORITHM_REGISTRY,
    AlgorithmIdentifier,
    D2dWitness,
    UnsupportedAlgorithmError,
    decode_wire_alg_id,
    resolve_dispatch,
)
from kailash.trust.signing.crypto import serialize_for_signing

_VECTORS_PATH = (
    Path(__file__).resolve().parents[1]
    / "test-vectors"
    / "eatp08-alg-id-canonical.json"
)


def _vectors() -> dict:
    return json.loads(_VECTORS_PATH.read_text())


def _canonical_member_bytes(token: str) -> bytes:
    member = serialize_for_signing(AlgorithmIdentifier(algorithm=token).to_dict())
    return member if isinstance(member, (bytes, bytearray)) else member.encode("utf-8")


def _pre_adoption_witness() -> D2dWitness:
    # Both dates strictly before ADOPTION_DATE (2026-04-26).
    before = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return D2dWitness(witnessed_at=before, chain_head_date=before)


@pytest.mark.regression
def test_vectors_file_loads_and_pins_the_active_default():
    data = _vectors()
    assert data["contract"] == "eatp-08-alg-id-canonical"
    assert data["active_token"] == ALGORITHM_DEFAULT == "eatp-v1"
    assert data["adoption_date"] == ADOPTION_DATE_PARSED.isoformat()
    pinned_tokens = {row["token"] for row in data["registry"]}
    assert pinned_tokens == set(ALGORITHM_REGISTRY), (
        "registry vector set drifted from ALGORITHM_REGISTRY: "
        f"{pinned_tokens ^ set(ALGORITHM_REGISTRY)}"
    )


@pytest.mark.regression
@pytest.mark.parametrize("row", _vectors()["registry"], ids=lambda r: r["token"])
def test_registry_canonical_member_and_sha_reproduce(row):
    token = row["token"]
    canon = _canonical_member_bytes(token)
    assert (
        canon.decode() == row["canonical_member"]
    ), f"canonical alg_id member drifted for {token!r}"
    assert (
        hashlib.sha256(canon).hexdigest() == row["expected_sha256"]
    ), f"sha256 byte-pin drifted for {token!r}"


@pytest.mark.regression
@pytest.mark.parametrize("row", _vectors()["registry"], ids=lambda r: r["token"])
def test_registry_status_and_dispatchability_match(row):
    token = row["token"]
    entry = ALGORITHM_REGISTRY[token]
    assert entry.status.value == row["status"]
    if row["dispatchable"]:
        assert resolve_dispatch(token).alg_id == token
    else:
        with pytest.raises(UnsupportedAlgorithmError) as exc:
            resolve_dispatch(token)
        assert exc.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_non_conformant_deprecated_literal_decode_regime():
    # Post-adoption (no witness): the bare deprecated literal is shape-mismatch.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"alg_id": "ed25519+sha256"})
    assert exc.value.code == "alg-id-shape-mismatch"
    # D2d witnessed legacy path: accepted as eatp-v1.
    got = decode_wire_alg_id(
        {"alg_id": "ed25519+sha256"}, witness=_pre_adoption_witness()
    )
    assert got == ALGORITHM_DEFAULT == "eatp-v1"


@pytest.mark.regression
def test_non_conformant_nested_pre_registry_object_decode_regime():
    # The kailash-rs pre-publication scaffold form: nested {"algorithm": "..."}.
    nested = {"alg_id": {"algorithm": "ed25519+sha256"}}
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(nested)
    assert exc.value.code == "alg-id-shape-mismatch"
    got = decode_wire_alg_id(nested, witness=_pre_adoption_witness())
    assert got == ALGORITHM_DEFAULT == "eatp-v1"


@pytest.mark.regression
def test_non_conformant_missing_alg_id_post_adoption():
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"envelope": "..."})
    assert exc.value.code == "missing-alg-id-post-adoption"


@pytest.mark.regression
def test_non_conformant_unregistered_token_never_falls_through():
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"alg_id": "ed25519+sha512"})
    assert exc.value.code == "unsupported-algorithm"
    # Even with a pre-adoption witness, an unknown non-pre-registry token is not rescued.
    with pytest.raises(UnsupportedAlgorithmError):
        decode_wire_alg_id(
            {"alg_id": "ed25519+sha512"}, witness=_pre_adoption_witness()
        )
