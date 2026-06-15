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
    D2dVerifierKeys,
    D2dWitness,
    UnsupportedAlgorithmError,
    decode_wire_alg_id,
    resolve_dispatch,
)
from kailash.trust.signing.crypto import generate_keypair, serialize_for_signing, sign

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
    # Unsigned witness — for the rejection paths (bare-literal, unknown token,
    # both-keys) where the value is rejected at the registry/shape gate BEFORE
    # the D2d signed-marker gate is ever reached, so the marker need not verify.
    before = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return D2dWitness(witnessed_at=before, chain_head_date=before)


# A trusted verifier keypair, fixed for the module so the signed-marker accept
# path (§4.3.2) is deterministic. The witness signs the §4.3.1 core
# {principal, first_seen} with the private key; the verifier holds the public.
_WITNESS_PRIVATE_KEY, _WITNESS_PUBLIC_KEY = generate_keypair()
_WITNESS_ID = "eatp08-test-witness"


def _verifier_keys() -> D2dVerifierKeys:
    return D2dVerifierKeys(keys={_WITNESS_ID: _WITNESS_PUBLIC_KEY})


def _signed_pre_adoption_witness() -> D2dWitness:
    # A complete, signed, pre-adoption D2d marker that passes all five gate
    # checks: principal + signed first_seen (both strictly < ADOPTION_DATE),
    # marker_sig over the §4.3.1 signed core, no expiry.
    before = datetime(2026, 1, 1, tzinfo=timezone.utc)
    principal = "chain:eatp08-test"
    first_seen = datetime(2026, 1, 1, tzinfo=timezone.utc)
    marker_sig = sign(
        {"principal": principal, "first_seen": first_seen.isoformat()},
        _WITNESS_PRIVATE_KEY,
    )
    return D2dWitness(
        witnessed_at=before,
        chain_head_date=before,
        principal=principal,
        first_seen=first_seen,
        marker_sig=marker_sig,
        witness_id=_WITNESS_ID,
    )


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
    # v1.1.1 / mint#26: a bare top-level-string `alg_id` equal to the deprecated
    # literal is an UNREGISTERED top-level token -> `unsupported-algorithm`, in
    # BOTH the no-witness and witnessed cases. It is NOT a D2d form, and a
    # witness MUST NOT rescue it (§5.1 step 2 registry-matches a top-level
    # string; the literal is not a registry token). The two D2d forms are the
    # nested-object value and unsigned `algorithm` metadata, exercised by the
    # sibling tests below.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"alg_id": "ed25519+sha256"})
    assert exc.value.code == "unsupported-algorithm"
    # An otherwise-valid pre-adoption witness does NOT rescue the bare
    # top-level-string literal (it is not a D2d encoding).
    with pytest.raises(UnsupportedAlgorithmError) as exc_witnessed:
        decode_wire_alg_id(
            {"alg_id": "ed25519+sha256"}, witness=_pre_adoption_witness()
        )
    assert exc_witnessed.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_alg_id_key_is_authoritative_over_algorithm_sibling():
    """A present `alg_id` key is authoritative; a bare-literal `alg_id` is NOT
    rescued by an `algorithm` sibling.

    Boundary case (v1.1.1 / mint#26): a record carrying BOTH a bare top-level
    `alg_id` string literal AND an `algorithm` metadata key must resolve from
    `alg_id` and reject with `unsupported-algorithm` — the `algorithm`-sibling
    D2d form applies only when there is NO `alg_id` member. Exercises
    `AlgorithmIdentifier.from_dict` directly (the exported surface), not only
    the `decode_wire_alg_id` production path."""

    both_keys = {"alg_id": "ed25519+sha256", "algorithm": "ed25519+sha256"}
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        AlgorithmIdentifier.from_dict(both_keys, witness=_pre_adoption_witness())
    assert exc.value.code == "unsupported-algorithm"
    # And without a witness.
    with pytest.raises(UnsupportedAlgorithmError) as exc_nw:
        AlgorithmIdentifier.from_dict(both_keys)
    assert exc_nw.value.code == "unsupported-algorithm"


@pytest.mark.regression
def test_non_conformant_nested_pre_registry_object_decode_regime():
    # The kailash-rs pre-publication scaffold form: nested {"algorithm": "..."}.
    nested = {"alg_id": {"algorithm": "ed25519+sha256"}}
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(nested)
    assert exc.value.code == "alg-id-shape-mismatch"
    # D2d accept requires a SIGNED marker verified against a trusted key
    # (§4.3.2). An unsigned witness no longer rescues (see the signed-marker
    # gate tests in test_issue_1316_d2c_marker.py).
    got = decode_wire_alg_id(
        nested,
        witness=_signed_pre_adoption_witness(),
        verifier_keys=_verifier_keys(),
    )
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


# ---------------------------------------------------------------------------
# Named EATP-08 §6 conformance vectors (V4-V7 + V9 — the #1316 acceptance bar)
# ---------------------------------------------------------------------------
#
# The coverage map lives in the canonical vector file under `conformance_vectors`;
# each acceptance-bar V-id maps to a named `test_vN_*` here (the coverage-map test
# below asserts the mapping holds). V1/V2 are the registry round-trips above; V3 is
# the chain-walk layer (out of this module); V8 is non-runtime. Exact V1-V9 table:
# workspaces/issue-1316-eatp08-marker-regime-py/01-analysis/02-spec-locked-facts.md.


def _tampered_signed_witness() -> D2dWitness:
    # A signed pre-adoption marker whose marker_sig has been tampered (one byte
    # flipped) — it no longer verifies against the trusted key. V7 / §4.3.2.
    w = _signed_pre_adoption_witness()
    sig = w.marker_sig or ""
    # Flip a base64 char deterministically (no RNG — `testing.md` determinism).
    flipped = ("B" if sig[0] != "B" else "C") + sig[1:]
    return D2dWitness(
        witnessed_at=w.witnessed_at,
        chain_head_date=w.chain_head_date,
        principal=w.principal,
        first_seen=w.first_seen,
        marker_sig=flipped,
        witness_id=w.witness_id,
    )


@pytest.mark.regression
def test_v4_implicit_v1_pre_adoption_accepts():
    """V4 (§6 / §4.1 D2a): a record WITHOUT an explicit alg_id, carrying only
    empty/implicit algorithm metadata, with a signed pre-adoption marker and no
    prior v2 in the chain, accepts as eatp-v1 (the implicit arm of
    decode_wire_alg_id's `legacy_value in ('', None)` branch — distinct from V9's
    explicit pre-registry literal/nested arms)."""
    got = decode_wire_alg_id(
        {"algorithm": ""},
        witness=_signed_pre_adoption_witness(),
        verifier_keys=_verifier_keys(),
    )
    assert got == ALGORITHM_DEFAULT == "eatp-v1"


@pytest.mark.regression
def test_v5_implicit_v1_post_adoption_rejects():
    """V5 (§6 / §4.2 D2b): a record WITHOUT alg_id and with no qualifying witness
    (cannot be dated pre-adoption) MUST reject with missing-alg-id-post-adoption,
    never default-fill."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"envelope": "post-adoption-record"})
    assert exc.value.code == "missing-alg-id-post-adoption"


@pytest.mark.regression
def test_v6ii_strip_fresh_post_adoption_missing():
    """V6 sub-case (ii) (§6 / §4.4): a stripped v2 record from a chain with no
    prior records, head post-adoption (no witness) MUST reject with
    missing-alg-id-post-adoption."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id({"payload": "v2-record-with-alg_id-stripped"})
    assert exc.value.code == "missing-alg-id-post-adoption"


@pytest.mark.regression
def test_v6iii_strip_fresh_attacker_pre_adoption_witness_failure():
    """V6 sub-case (iii) (§6 / §4.3.2 — fixture REQUIRED): a stripped record from a
    fresh chain with an attacker-chosen pre-adoption date but NO signed
    pre-adoption marker (the witness is unsigned) MUST reject with
    implicit-v1-witness-failure — the backdating defense. An attacker can set the
    claimed date but cannot obtain a signed pre-adoption first_seen."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"algorithm": ""},
            witness=_pre_adoption_witness(),  # unsigned — no marker_sig/principal
        )
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_v7_marker_tamper_detected_complete_level():
    """V7 (§6 — Complete only / §4.3.2): an attacker tampers the local signed
    marker (marker_sig) to make a post-adoption stripped record look pre-adoption;
    the §4.3.2 detection rule MUST catch the failed Ed25519 verification and reject
    with implicit-v1-witness-failure."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"alg_id": {"algorithm": "ed25519+sha256"}},
            witness=_tampered_signed_witness(),
            verifier_keys=_verifier_keys(),
        )
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_v9_pre_registry_nested_d2d_accepts():
    """V9 (§6 / §4.5 D2d): the nested-object pre-registry explicit form with a
    signed pre-adoption marker accepts as eatp-v1."""
    got = decode_wire_alg_id(
        {"alg_id": {"algorithm": "ed25519+sha256"}},
        witness=_signed_pre_adoption_witness(),
        verifier_keys=_verifier_keys(),
    )
    assert got == ALGORITHM_DEFAULT == "eatp-v1"


@pytest.mark.regression
def test_v9_pre_registry_unsigned_metadata_d2d_accepts():
    """V9 (§6 / §4.5 D2d): the unsigned-`algorithm`-metadata pre-registry explicit
    form (the kailash-py historical shape) with a signed pre-adoption marker
    accepts as eatp-v1."""
    got = decode_wire_alg_id(
        {"algorithm": "ed25519+sha256"},
        witness=_signed_pre_adoption_witness(),
        verifier_keys=_verifier_keys(),
    )
    assert got == ALGORITHM_DEFAULT == "eatp-v1"


@pytest.mark.regression
def test_v6i_strip_prior_v2_monotonic():
    """V6 sub-case (i) (§6 / §4.2 / §4.5.3): a stripped record from a principal-
    chain that has previously emitted a registry-form (v2) record MUST reject with
    monotonic-upgrade-violation. Enforced in Shard 3A: the read-check is surfaced
    via `decode_wire_alg_id(..., prior_registry_form_seen=True)` (was xfail-strict
    in Shard 2 until the enforcer landed)."""
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(
            {"payload": "v2-record-stripped"},
            prior_registry_form_seen=True,
        )
    assert exc.value.code == "monotonic-upgrade-violation"


@pytest.mark.regression
def test_conformance_vector_coverage_map():
    """H1 coverage gate: the canonical file's `conformance_vectors` names every
    EATP-08 §6 vector V1-V9, and every #1316 acceptance-bar vector (V4-V7 + V9)
    maps to a named test function present in this module. V6 sub-case (i) is the
    only deferred contract and MUST be marked deferred-shard-3a (xfail-strict
    test present), never silently dropped."""
    data = _vectors()
    cv = {v["vector_id"]: v for v in data["conformance_vectors"]}
    assert set(cv) == {f"V{n}" for n in range(1, 10)}, "V1-V9 must all be named"

    # The acceptance bar is exactly V4-V7 + V9.
    acceptance = {vid for vid, v in cv.items() if v["acceptance_bar"]}
    assert acceptance == {"V4", "V5", "V6", "V7", "V9"}

    # V7 is Complete-only; the other acceptance-bar vectors are Conformant.
    assert cv["V7"]["level"] == "Complete"
    for vid in ("V4", "V5", "V6", "V9"):
        assert cv[vid]["level"] == "Conformant", f"{vid} level"

    # Every acceptance-bar vector's `covered_by` test(s) exist in this module.
    module = globals()
    expected_tests = {
        "V4": ["test_v4_implicit_v1_pre_adoption_accepts"],
        "V5": ["test_v5_implicit_v1_post_adoption_rejects"],
        "V7": ["test_v7_marker_tamper_detected_complete_level"],
        "V9": [
            "test_v9_pre_registry_nested_d2d_accepts",
            "test_v9_pre_registry_unsigned_metadata_d2d_accepts",
        ],
    }
    for vid, names in expected_tests.items():
        for name in names:
            assert callable(module.get(name)), f"{vid} missing test {name!r}"

    # V6 sub-cases: all three enforced (named tests present). Sub-case (i) was
    # xfail-strict in Shard 2 and is enforced as of Shard 3A.
    subs = {s["sub_case"]: s for s in cv["V6"]["sub_cases"]}
    assert subs["i"]["status"] == "enforced"
    assert callable(module.get("test_v6i_strip_prior_v2_monotonic"))
    assert subs["ii"]["status"] == "enforced"
    assert callable(module.get("test_v6ii_strip_fresh_post_adoption_missing"))
    assert subs["iii"]["status"] == "enforced"
    assert callable(
        module.get("test_v6iii_strip_fresh_attacker_pre_adoption_witness_failure")
    )
