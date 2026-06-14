# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 Wave-1 byte-pin + foundation regression suite.

Pins the §12.2 (N12-CB-01) commitment and §12.3 (N12-CB-04(d)) KCV golden hashes
from the normative Appendix B fixture, plus the canonical pre-image strings — the
cross-SDK byte contract kailash-rs must reproduce. Tier-1 (offline, deterministic).

Covers Wave-1 shards: F1 (KeyClass/kek_generation), FT (closed taxonomy + gate
skeletons), F2 (DTO floors), C1 (commitment/KCV byte-pins + constant-time verify),
T1 (this fixture).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kailash.trust._json import canonical_json_dumps
from kailash.trust.key_manager import KeyClass, KeyMetadata
from kailash.trust.vault.commitment import (
    kek_identity_commitment,
    key_check_value,
    verify_commitment,
    verify_kcv,
)
from kailash.trust.vault.errors import (
    RESTORE_GATE_ORDER,
    N12FT01Code,
    VaultBindingError,
    first_failing,
    map_wrapper_exception,
)
from kailash.trust.vault.types import BackupReceipt, ClearanceContext, VaultKeyHandle

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "test-vectors" / "eatp12-vault-canonical.json"
)


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture() -> dict:
    return _load_fixture()


# --- C1 / T1 byte-pins (N12-CB-01, N12-CB-04(d), §12.2/§12.3) ----------------


@pytest.mark.regression
def test_commitment_byte_pin_matches_spec_12_2(fixture):
    fixed = fixture["fixed_inputs"]
    vec = next(v for v in fixture["vectors"] if v["conformance_id"] == "N12-CB-01")
    secret = bytes.fromhex(fixed["master_secret_hex"])
    commitment = kek_identity_commitment(
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
        passphrase_provenance=fixed["passphrase_provenance"],
        alg=fixed["kek_commitment_alg"],
    )
    assert commitment == vec["kek_identity_commitment"], "commitment hash drifted"


@pytest.mark.regression
def test_commitment_pre_image_is_canonical_jcs(fixture):
    """The pre-image string MUST match §12.2 byte-for-byte (the cross-SDK contract)."""
    fixed = fixture["fixed_inputs"]
    vec = next(v for v in fixture["vectors"] if v["conformance_id"] == "N12-CB-01")
    rebuilt = canonical_json_dumps(
        {
            "domain_sep": "EATP-12/kek-identity-commitment/v1",
            "kek_generation": fixed["kek_generation"],
            "master_secret": fixed["master_secret_hex"],
            "passphrase_provenance": fixed["passphrase_provenance"],
            "vault_id": fixed["vault_id"],
        }
    )
    assert rebuilt == vec["pre_image"], "canonical pre-image drifted from §12.2"


@pytest.mark.regression
def test_kcv_byte_pin_matches_spec_12_3(fixture):
    fixed = fixture["fixed_inputs"]
    vec = next(v for v in fixture["vectors"] if v["conformance_id"] == "N12-CB-04(d)")
    secret = bytes.fromhex(fixed["master_secret_hex"])
    kcv = key_check_value(
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
        alg=fixed["kek_commitment_alg"],
    )
    assert kcv == vec["kcv"]
    assert len(kcv) == 16  # 8 bytes, key-free


@pytest.mark.regression
def test_commitment_and_kcv_are_domain_separated(fixture):
    """Distinct domain_sep → commitment and KCV never collide on the same inputs."""
    fixed = fixture["fixed_inputs"]
    secret = bytes.fromhex(fixed["master_secret_hex"])
    c = kek_identity_commitment(
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
        passphrase_provenance=fixed["passphrase_provenance"],
    )
    k = key_check_value(
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
    )
    assert not c.startswith(k)  # not a prefix relationship


@pytest.mark.regression
def test_verify_commitment_constant_time_roundtrip_and_tamper(fixture):
    fixed = fixture["fixed_inputs"]
    secret = bytes.fromhex(fixed["master_secret_hex"])
    c = kek_identity_commitment(
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
        passphrase_provenance=fixed["passphrase_provenance"],
    )
    assert verify_commitment(
        expected_commitment=c,
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
        passphrase_provenance=fixed["passphrase_provenance"],
    )
    # relabelled generation → mismatch (N12-SG-01(b): generation bound in)
    assert not verify_commitment(
        expected_commitment=c,
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"] + 1,
        master_secret=secret,
        passphrase_provenance=fixed["passphrase_provenance"],
    )


@pytest.mark.regression
def test_kcv_tamper_detected_offline(fixture):
    fixed = fixture["fixed_inputs"]
    secret = bytes.fromhex(fixed["master_secret_hex"])
    k = key_check_value(
        vault_id=fixed["vault_id"],
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
    )
    # tampered vault_id → KCV mismatch, detectable without the live vault
    assert not verify_kcv(
        expected_kcv=k,
        vault_id="vault:other",
        kek_generation=fixed["kek_generation"],
        master_secret=secret,
    )


@pytest.mark.regression
def test_unregistered_commitment_alg_fails_closed():
    with pytest.raises(VaultBindingError) as ei:
        kek_identity_commitment(
            vault_id="v",
            kek_generation=1,
            master_secret=b"\x00" * 16,
            passphrase_provenance="p",
            alg="eatp-vX",
        )
    assert ei.value.code is N12FT01Code.COMMITMENT_ALG_MISMATCH


# --- FT (taxonomy + gate-order skeletons, N12-FT-01/02/03) -------------------


@pytest.mark.regression
def test_taxonomy_is_closed_and_distinct():
    values = [c.value for c in N12FT01Code]
    assert len(values) == len(set(values)), "duplicate code strings"
    # reused EATP-10 codes carry the canonical string
    assert N12FT01Code.UNKNOWN_SHARD.value == "unknown-shard"
    assert N12FT01Code.INSUFFICIENT_SHARDS.value == "insufficient-shards"
    assert N12FT01Code.UNKNOWN_TIER.value == "unknown-tier"


@pytest.mark.regression
def test_ft02_first_failing_is_deterministic_order():
    # clearance fails AND foreign-shard would fail → clearance wins (step 1 < step 6)
    def check(gate):
        if gate == "clearance":
            return N12FT01Code.MISSING_CLEARANCE
        if gate == "foreign-shard":
            return N12FT01Code.UNKNOWN_SHARD
        return None

    assert first_failing(RESTORE_GATE_ORDER, check) is N12FT01Code.MISSING_CLEARANCE

    # only foreign-shard fails → unknown-shard (step 6), nothing earlier
    assert (
        first_failing(
            RESTORE_GATE_ORDER,
            lambda g: N12FT01Code.UNKNOWN_SHARD if g == "foreign-shard" else None,
        )
        is N12FT01Code.UNKNOWN_SHARD
    )
    # all gates pass → None
    assert first_failing(RESTORE_GATE_ORDER, lambda g: None) is None


@pytest.mark.regression
def test_wrapper_exception_mapping():
    assert (
        map_wrapper_exception(ValueError("invalid mnemonic checksum"))
        is N12FT01Code.CORRUPTED_SHARD
    )
    assert (
        map_wrapper_exception(ValueError("identifier parameters don't match"))
        is N12FT01Code.PARAMETER_MISMATCH
    )
    # unrecognized wrapper exception → None (fail-closed: caller re-raises internal)
    assert map_wrapper_exception(RuntimeError("some opaque failure")) is None


# --- F1 (KeyClass + kek_generation, §3.4) -----------------------------------


@pytest.mark.regression
def test_keymetadata_backward_compatible_defaults():
    m = KeyMetadata(key_id="agent-1")
    assert m.key_class is KeyClass.DATA and m.kek_generation == 0


@pytest.mark.regression
def test_keymetadata_kek_generation_invariants():
    KeyMetadata(key_id="kek", key_class=KeyClass.KEK, kek_generation=7)
    with pytest.raises(ValueError):
        KeyMetadata(key_id="bad", kek_generation=-1)
    with pytest.raises(ValueError):
        KeyMetadata(key_id="bad", kek_generation=True)  # bool rejected


# --- F2 (DTO floors, §4.1/§4.4) ---------------------------------------------


@pytest.mark.regression
def test_backupreceipt_enforces_ritual_floor_and_kcv_length():
    BackupReceipt(
        vault_id="v",
        kek_generation=7,
        kek_commitment_alg="eatp-v1",
        kek_identity_commitment="ab" * 32,
        kcv="00051364b85b0a43",
        k=3,
        n=5,
    )
    with pytest.raises(ValueError):  # 1-of-1 below floor
        BackupReceipt(
            vault_id="v",
            kek_generation=7,
            kek_commitment_alg="eatp-v1",
            kek_identity_commitment="ab" * 32,
            kcv="00051364b85b0a43",
            k=1,
            n=1,
        )
    with pytest.raises(ValueError):  # n > 9 above floor
        BackupReceipt(
            vault_id="v",
            kek_generation=7,
            kek_commitment_alg="eatp-v1",
            kek_identity_commitment="ab" * 32,
            kcv="00051364b85b0a43",
            k=3,
            n=10,
        )
    with pytest.raises(ValueError):  # KCV wrong length
        BackupReceipt(
            vault_id="v",
            kek_generation=7,
            kek_commitment_alg="eatp-v1",
            kek_identity_commitment="ab" * 32,
            kcv="dead",
            k=3,
            n=5,
        )


@pytest.mark.regression
def test_vaultkeyhandle_and_clearance_no_secret_fields():
    h = VaultKeyHandle(key_id="kek-1", vault_id="vault:x", kek_generation=7)
    assert h.to_dict()["kek_generation"] == 7
    cc = ClearanceContext(
        principal="delegate:r", tenant="t", domain="d", capabilities=("vault:restore",)
    )
    assert cc.has_capability("vault:restore")
    assert not cc.has_capability("vault:backup")  # fail-closed absence
