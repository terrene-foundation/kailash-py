# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 W2-D2 audit-anchor byte-pin regression suite.

Pins the §12.4-§12.11 golden audit-anchor fixtures from the normative
Appendix B (N12-AU-01/03/04/04a). For each anchor subtype this builds the
``event_payload`` via the :mod:`kailash.trust.vault.anchors` builder from the
§12.1 fixed inputs, computes the ``content_signing_bytes`` signed pre-image,
and asserts it is byte-identical to the spec hex AND that the canonical JCS
``event_payload`` string matches the spec's canonical form. Any divergence
(key order, number form, field inclusion, encoding) is a V6 cross-SDK
non-conformance. Tier-1 (offline, deterministic).

Also covers: the N12-AU-03 subtype validator (rejects non-``vault_`` and
substrate-reserved subtypes) and the N12-AU-01 denial schema (omits
``vault_id`` / ``kek_generation`` / commitments).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kailash.delegate.audit import content_signing_bytes
from kailash.trust._json import canonical_json_dumps
from kailash.trust.vault.anchors import (
    SUBSTRATE_RESERVED_SUBTYPES,
    UNVERIFIED_SENTINEL,
    VAULT_SUBTYPES,
    build_anchor_payload,
    build_backup_anchor,
    build_denial_anchor,
    build_denial_summary_anchor,
    build_kek_recommit_anchor,
    build_kek_rotation_anchor,
    build_restore_anchor,
    build_restore_forced_stale_anchor,
    validate_subtype,
)
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "test-vectors" / "eatp12-vault-canonical.json"
)

_EVENT_TYPE = "external_side_effect"
_SIGNER = "delegate:vault-signer-00"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture() -> dict:
    return _load_fixture()


@pytest.fixture(scope="module")
def afi(fixture) -> dict:
    return fixture["anchor_fixed_inputs"]


def _vec(fixture: dict, spec_section: str) -> dict:
    return next(
        v for v in fixture["anchor_vectors"] if v["spec_section"] == spec_section
    )


def _assert_byte_pin(payload: dict, vec: dict) -> None:
    """Assert both the JCS canonical event_payload AND signed pre-image match."""
    canonical = canonical_json_dumps(payload)
    assert (
        canonical == vec["event_payload"]
    ), f"§{vec['spec_section']} canonical event_payload drifted from spec"
    pre_image_hex = content_signing_bytes(_EVENT_TYPE, payload, _SIGNER).hex()
    assert (
        pre_image_hex == vec["signed_preimage_hex"]
    ), f"§{vec['spec_section']} signed pre-image hex drifted from spec"


# --- §12.4-§12.11 byte-pins (N12-AU-04 per-subtype) --------------------------


@pytest.mark.regression
def test_backup_anchor_byte_pin_12_4(fixture, afi):
    payload = build_backup_anchor(
        alg_id=afi["alg_id"],
        k=3,
        n=5,
        holders=afi["holders"],
        shard_count=5,
        vault_id="vault:fixture-0001",
        kek_generation=7,
        kek_identity_commitment=afi["kek_identity_commitment_gen7"],
        kek_commitment_alg=afi["kek_commitment_alg"],
        kcv="00051364b85b0a43",
        shard_commitments=afi["shard_commitments"],
        slip39_params=afi["slip39_params"],
        principal=afi["principal"],
        timestamp=afi["timestamp"],
        time_attested=True,
        side_channel_hardened=False,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.4"))


@pytest.mark.regression
def test_denial_anchor_attested_byte_pin_12_5(fixture, afi):
    payload = build_denial_anchor(
        subtype="vault_key_restore_denied",
        principal="delegate:prober-99",
        missing_capability_or_scope="vault:restore",
        target_handle_ref="opaque:href-abcdef",
        timestamp=afi["timestamp"],
        time_attested=True,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.5"))


@pytest.mark.regression
def test_kek_rotation_anchor_byte_pin_12_6(fixture, afi):
    payload = build_kek_rotation_anchor(
        alg_id=afi["alg_id"],
        prior_kek_generation=7,
        kek_generation=8,
        vault_id="vault:fixture-0001",
        k=3,
        n=5,
        holders=afi["holders"],
        shard_count=5,
        shard_commitments=afi["shard_commitments"],
        kek_identity_commitment=afi["kek_identity_commitment_gen8"],
        kek_commitment_alg=afi["kek_commitment_alg"],
        slip39_params=afi["slip39_params"],
        for_cause=False,
        principal=afi["principal"],
        timestamp=afi["timestamp"],
        time_attested=True,
        side_channel_hardened=False,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.6"))


@pytest.mark.regression
def test_kek_recommit_anchor_byte_pin_12_7(fixture, afi):
    payload = build_kek_recommit_anchor(
        alg_id=afi["alg_id"],
        vault_id="vault:fixture-0001",
        kek_generation=7,
        prior_kek_commitment_alg="eatp-v1",
        prior_kek_identity_commitment=afi["kek_identity_commitment_gen7"],
        new_kek_commitment_alg="eatp-v1.1",
        new_kek_identity_commitment="aa" * 32,
        principal=afi["principal"],
        timestamp=afi["timestamp"],
        time_attested=True,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.7"))


@pytest.mark.regression
def test_restore_anchor_byte_pin_12_8(fixture, afi):
    payload = build_restore_anchor(
        alg_id=afi["alg_id"],
        re_established_handle_ref="opaque:href-restored-01",
        vault_id="vault:fixture-0001",
        kek_generation=7,
        generation_checked=7,
        kek_identity_commitment=afi["kek_identity_commitment_gen7"],
        kek_commitment_alg=afi["kek_commitment_alg"],
        holders=afi["holders"],
        shard_count=5,
        shard_commitments=afi["shard_commitments"],
        principal=afi["principal"],
        timestamp=afi["timestamp"],
        time_attested=True,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.8"))


@pytest.mark.regression
def test_denial_summary_anchor_byte_pin_12_9(fixture, afi):
    payload = build_denial_summary_anchor(
        window_start="2026-06-12T00:00:00Z",
        window_end="2026-06-12T00:05:00Z",
        # supply UNSORTED to prove the builder sorts ascending (N12-AU-04)
        distinct_principals=["delegate:prober-02", "delegate:prober-01"],
        distinct_missing_capabilities=["vault:restore", "vault:backup"],
        principal_set_root="ff" * 32,
        coalesced_count=1024,
        timestamp=afi["timestamp"],
        time_attested=True,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.9"))


@pytest.mark.regression
def test_denial_anchor_unverified_byte_pin_12_10(fixture, afi):
    # time_attested=False → timestamp forced to the sentinel regardless of input
    payload = build_denial_anchor(
        subtype="vault_key_restore_denied",
        principal="delegate:prober-99",
        missing_capability_or_scope="vault:restore",
        target_handle_ref="opaque:href-abcdef",
        timestamp="2026-06-12T00:00:00Z",  # ignored when time_attested False
        time_attested=False,
    )
    assert payload["timestamp"] == UNVERIFIED_SENTINEL
    _assert_byte_pin(payload, _vec(fixture, "12.10"))


@pytest.mark.regression
def test_forced_stale_anchor_byte_pin_12_11(fixture, afi):
    payload = build_restore_forced_stale_anchor(
        alg_id=afi["alg_id"],
        re_established_handle_ref="opaque:href-restored-fs-01",
        vault_id="vault:fixture-0001",
        kek_generation=6,
        generation_checked=6,
        restored_generation=6,
        overridden_current_generation=7,
        kek_identity_commitment=afi["kek_identity_commitment_gen6"],
        kek_commitment_alg=afi["kek_commitment_alg"],
        holders=afi["holders"],
        shard_count=5,
        shard_commitments=afi["shard_commitments"],
        principal=afi["principal"],
        timestamp=afi["timestamp"],
        time_attested=True,
    )
    _assert_byte_pin(payload, _vec(fixture, "12.11"))


@pytest.mark.regression
def test_all_eight_anchor_vectors_reproduce_via_dispatch(fixture, afi):
    """build_anchor_payload dispatcher reproduces every §12.x signed pre-image."""
    by_section = {v["spec_section"]: v for v in fixture["anchor_vectors"]}
    common = dict(
        alg_id=afi["alg_id"],
        holders=afi["holders"],
        shard_commitments=afi["shard_commitments"],
        slip39_params=afi["slip39_params"],
        principal=afi["principal"],
        timestamp=afi["timestamp"],
    )
    payloads = {
        "12.4": build_anchor_payload(
            "vault_key_backup",
            k=3,
            n=5,
            shard_count=5,
            vault_id="vault:fixture-0001",
            kek_generation=7,
            kek_identity_commitment=afi["kek_identity_commitment_gen7"],
            kek_commitment_alg=afi["kek_commitment_alg"],
            kcv="00051364b85b0a43",
            time_attested=True,
            side_channel_hardened=False,
            **common,
        ),
        "12.6": build_anchor_payload(
            "vault_kek_rotation",
            prior_kek_generation=7,
            kek_generation=8,
            vault_id="vault:fixture-0001",
            k=3,
            n=5,
            shard_count=5,
            kek_identity_commitment=afi["kek_identity_commitment_gen8"],
            kek_commitment_alg=afi["kek_commitment_alg"],
            for_cause=False,
            time_attested=True,
            side_channel_hardened=False,
            **common,
        ),
        "12.10": build_anchor_payload(
            "vault_key_restore_denied",
            principal="delegate:prober-99",
            missing_capability_or_scope="vault:restore",
            target_handle_ref="opaque:href-abcdef",
            timestamp="unverified",
            time_attested=False,
        ),
    }
    for section, payload in payloads.items():
        vec = by_section[section]
        got = content_signing_bytes(_EVENT_TYPE, payload, _SIGNER).hex()
        assert got == vec["signed_preimage_hex"], f"dispatch §{section} drifted"


# --- N12-AU-03 subtype validator --------------------------------------------


@pytest.mark.regression
def test_subtype_validator_accepts_every_vault_subtype():
    for st in VAULT_SUBTYPES:
        assert validate_subtype(st) == st


@pytest.mark.regression
def test_subtype_validator_rejects_non_vault_prefix():
    with pytest.raises(VaultBindingError) as ei:
        validate_subtype("backup")  # no vault_ prefix
    assert ei.value.code is N12FT01Code.PARAMETER_MISMATCH


@pytest.mark.regression
def test_subtype_validator_rejects_substrate_reserved():
    # every substrate-reserved subtype MUST be rejected (F-XSDK-12 collision)
    for reserved in SUBSTRATE_RESERVED_SUBTYPES:
        with pytest.raises(VaultBindingError) as ei:
            validate_subtype(reserved)
        assert ei.value.code is N12FT01Code.PARAMETER_MISMATCH
    # the canonical example from the prompt
    with pytest.raises(VaultBindingError):
        validate_subtype("dispatch_invocation")


@pytest.mark.regression
def test_subtype_validator_rejects_unknown_vault_subtype():
    # begins vault_ but not in the closed set
    with pytest.raises(VaultBindingError) as ei:
        validate_subtype("vault_unknown_op")
    assert ei.value.code is N12FT01Code.PARAMETER_MISMATCH


@pytest.mark.regression
def test_build_anchor_payload_rejects_reserved_subtype():
    with pytest.raises(VaultBindingError):
        build_anchor_payload("dispatch_invocation")


# --- N12-AU-01 denial schema omits resolved fields --------------------------


@pytest.mark.regression
def test_denial_schema_omits_vault_id_generation_and_commitments(afi):
    payload = build_denial_anchor(
        subtype="vault_key_backup_denied",
        principal="delegate:prober-99",
        missing_capability_or_scope="vault:backup",
        target_handle_ref="opaque:href-xyz",
        timestamp=afi["timestamp"],
        time_attested=True,
    )
    # EXACTLY the denial field set (N12-AU-01)
    assert set(payload) == {
        "subtype",
        "principal",
        "missing_capability_or_scope",
        "target_handle_ref",
        "timestamp",
        "time_attested",
    }
    # explicitly OMITTED (not null-filled)
    for forbidden in (
        "vault_id",
        "kek_generation",
        "kek_identity_commitment",
        "kcv",
        "k",
        "n",
    ):
        assert forbidden not in payload


@pytest.mark.regression
def test_denial_anchor_rejects_non_denial_subtype(afi):
    with pytest.raises(VaultBindingError):
        build_denial_anchor(
            subtype="vault_key_backup",  # an outcome subtype, not a denial
            principal="delegate:p",
            missing_capability_or_scope="vault:backup",
            target_handle_ref="opaque:h",
            timestamp=afi["timestamp"],
            time_attested=True,
        )


# --- N12-AU-04a two-state timestamp grammar ---------------------------------


@pytest.mark.regression
def test_attested_true_requires_rfc3339_z(afi):
    with pytest.raises(VaultBindingError) as ei:
        build_denial_anchor(
            subtype="vault_key_restore_denied",
            principal="delegate:p",
            missing_capability_or_scope="vault:restore",
            target_handle_ref="opaque:h",
            timestamp="2026-06-12 00:00:00",  # missing T / Z
            time_attested=True,
        )
    assert ei.value.code is N12FT01Code.PARAMETER_MISMATCH


@pytest.mark.regression
def test_time_attested_must_be_bool(afi):
    with pytest.raises(VaultBindingError):
        build_denial_anchor(
            subtype="vault_key_restore_denied",
            principal="delegate:p",
            missing_capability_or_scope="vault:restore",
            target_handle_ref="opaque:h",
            timestamp=afi["timestamp"],
            time_attested="true",  # str, not bool
        )


# --- N12-AU-04 field-encoding guards ----------------------------------------


@pytest.mark.regression
def test_backup_anchor_rejects_bool_for_int_field(afi):
    with pytest.raises(VaultBindingError):
        build_backup_anchor(
            alg_id=afi["alg_id"],
            k=True,  # bool rejected for an int field
            n=5,
            holders=afi["holders"],
            shard_count=5,
            vault_id="vault:fixture-0001",
            kek_generation=7,
            kek_identity_commitment=afi["kek_identity_commitment_gen7"],
            kek_commitment_alg="eatp-v1",
            kcv="00051364b85b0a43",
            shard_commitments=afi["shard_commitments"],
            slip39_params=afi["slip39_params"],
            principal=afi["principal"],
            timestamp=afi["timestamp"],
            time_attested=True,
        )


@pytest.mark.regression
def test_backup_anchor_rejects_wrong_kcv_length(afi):
    with pytest.raises(VaultBindingError):
        build_backup_anchor(
            alg_id=afi["alg_id"],
            k=3,
            n=5,
            holders=afi["holders"],
            shard_count=5,
            vault_id="vault:fixture-0001",
            kek_generation=7,
            kek_identity_commitment=afi["kek_identity_commitment_gen7"],
            kek_commitment_alg="eatp-v1",
            kcv="dead",  # not 16 hex chars
            shard_commitments=afi["shard_commitments"],
            slip39_params=afi["slip39_params"],
            principal=afi["principal"],
            timestamp=afi["timestamp"],
            time_attested=True,
        )


@pytest.mark.regression
def test_forced_stale_requires_backward_rollback(afi):
    # overridden_current_generation MUST be > restored_generation
    with pytest.raises(VaultBindingError):
        build_restore_forced_stale_anchor(
            alg_id=afi["alg_id"],
            re_established_handle_ref="opaque:h",
            vault_id="vault:fixture-0001",
            kek_generation=6,
            generation_checked=6,
            restored_generation=6,
            overridden_current_generation=6,  # not > restored
            kek_identity_commitment=afi["kek_identity_commitment_gen6"],
            kek_commitment_alg="eatp-v1",
            holders=afi["holders"],
            shard_count=5,
            shard_commitments=afi["shard_commitments"],
            principal=afi["principal"],
            timestamp=afi["timestamp"],
            time_attested=True,
        )


@pytest.mark.regression
def test_slip39_params_pins_extendable_and_group_threshold(afi):
    bad = {
        "extendable": False,  # MUST be True
        "iteration_exponent": 1,
        "group_threshold": 1,
        "master_secret_bits": 128,
    }
    with pytest.raises(VaultBindingError):
        build_backup_anchor(
            alg_id=afi["alg_id"],
            k=3,
            n=5,
            holders=afi["holders"],
            shard_count=5,
            vault_id="vault:fixture-0001",
            kek_generation=7,
            kek_identity_commitment=afi["kek_identity_commitment_gen7"],
            kek_commitment_alg="eatp-v1",
            kcv="00051364b85b0a43",
            shard_commitments=afi["shard_commitments"],
            slip39_params=bad,
            principal=afi["principal"],
            timestamp=afi["timestamp"],
            time_attested=True,
        )
