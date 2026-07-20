# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1841 S2b-2: DelegationRecord signs the cross-SDK V3Complete pre-image.

The FINAL shard of #1841 — the QUORUM-INTEGRITY headline. A MULTI-SIG
``DelegationRecord`` (``multi_sig=True`` + a ``multi_sig_policy``) carrying the
full structured fold (``constraints`` / ``resource_limits`` / ``scope``, unscoped
``dimension_scope``) signs the ``v3-complete`` engine pre-image instead of
``v2-complete`` — folding the multi-sig policy (threshold + canonically-sorted
authorized_signers) into the Ed25519-SIGNED bytes so a store-write actor cannot
weaken quorum (lower the threshold, swap/remove a signer) undetected.

This is a SECURITY-CRITICAL, BYTE-CHANGING, cross-SDK-lockstep migration. Pins:

* the 4 V3 byte vectors (V1_2_OF_3 / V3_3_OF_5 / S2_ZERO_ONE / S3_ONE_BYTE_DIFF)
  reproduced byte-for-byte at the RECORD dispatch level (the same kailash-rs
  cross-SDK anchor the engine-level test pins — vendored, not re-authored);
* V2 anchor byte-neutrality (V2C_NON_MULTI_SIG unchanged) + legacy unchanged —
  adding the multi_sig fields changes ZERO bytes for a non-multi-sig record;
* QUORUM INTEGRITY: a store-mutated threshold / swapped / removed signer breaks
  the v3 signature (the #1841 headline);
* downgrade v3→v2 / v3→legacy → verify fails;
* can't-force-v3 (a non-multi-sig record never signs v3) + fail-closed on the
  inconsistent multi-sig flag/policy combos;
* signer canonical-order invariance (shuffle the stored order → same bytes);
* real Ed25519 multi-sig sign→verify round-trip through the store;
* to_dict/from_dict of a v3 record reconstructs the policy (hex→bytes, validation
  re-runs) + reproduces the signature;
* the multi-sig delegate() path produces a signable+verifiable v3 record (the
  whole-second-timestamp end-to-end check).

The pinned V3 hex vectors are the kailash-rs canonical bytes, VENDORED (imported)
from ``test_delegation_signing_payload_vectors.py`` so the record-level dispatch
is byte-checked against the SAME cross-SDK anchor as the engine-level test and
cannot drift from it (cross-sdk-inspection.md Rule 4a).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.chain import (
    DELEGATION_SIGNING_VERSION_LEGACY,
    DELEGATION_SIGNING_VERSION_V2,
    DELEGATION_SIGNING_VERSION_V3,
    DelegationRecord,
)
from kailash.trust.signing.crypto import (
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)
from kailash.trust.signing.delegation_payload import (
    ConstraintDimensions,
    DelegationScope,
    MultiSigSigningPolicy,
    ResourceLimits,
    TrustLevel,
)
from kailash.trust.signing.delegation_record_signing import (
    delegation_canonical_payload_str,
    select_signing_version,
)

# Vendored kailash-rs V3Complete byte vectors — the SAME cross-SDK anchor the
# engine-level test pins (re-pin ONLY in a cross-SDK lockstep event, rs#1795).
from tests.regression.test_delegation_signing_payload_vectors import (
    S2_ZERO_ONE,
    S3_ONE_BYTE_DIFF,
    V1_2_OF_3,
    V2C_NON_MULTI_SIG,
    V3_3_OF_5,
)

# Reuse the S2b-1 real-ops fixture builder (real crypto + real store, NO mocking).
from tests.regression.test_issue_1841_s2b1_v2_enrich import _real_ops_with_delegator

pytestmark = pytest.mark.regression


# --- Fixed inputs (mirror the rs fixed_inputs() / key(n)=[n;32]) -------------


def _key(n: int) -> bytes:
    return bytes([n]) * 32


def _supervised_constraints() -> ConstraintDimensions:
    return ConstraintDimensions.for_level(TrustLevel.SUPERVISED)


def _supervised_limits() -> ResourceLimits:
    return ResourceLimits.for_level(TrustLevel.SUPERVISED)


def _engineering_read_scope() -> DelegationScope:
    return DelegationScope.new("engineering").with_operation("read")


def _v1_policy() -> MultiSigSigningPolicy:
    return MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)])


def _v3_policy() -> MultiSigSigningPolicy:
    return MultiSigSigningPolicy.new(3, [_key(1), _key(2), _key(3), _key(4), _key(5)])


def _s2_policy() -> MultiSigSigningPolicy:
    return MultiSigSigningPolicy.new(1, [_key(0), _key(1)])


def _s3_policy() -> MultiSigSigningPolicy:
    last = bytearray(32)
    last[31] = 1
    return MultiSigSigningPolicy.new(2, [_key(0), bytes(last)])


def _base_kwargs() -> dict:
    """The rs ``fixed_inputs()`` mapped onto a DelegationRecord's fields."""
    return dict(
        id="00000000-0000-4000-8000-000000000001",
        delegator_id="alice",
        delegatee_id="bob",
        task_id="task-fixed",
        capabilities_delegated=["LlmCall"],
        constraint_subset=[],
        delegated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="",
        constraints=_supervised_constraints(),
        resource_limits=_supervised_limits(),
        scope=_engineering_read_scope(),
    )


def _v3_record(policy: MultiSigSigningPolicy, **overrides) -> DelegationRecord:
    kwargs = _base_kwargs()
    kwargs.update(
        multi_sig=True,
        multi_sig_policy=policy,
        signing_payload_version=DELEGATION_SIGNING_VERSION_V3,
    )
    kwargs.update(overrides)
    return DelegationRecord(**kwargs)


def _v2_record(**overrides) -> DelegationRecord:
    kwargs = _base_kwargs()
    kwargs.update(signing_payload_version=DELEGATION_SIGNING_VERSION_V2)
    kwargs.update(overrides)
    return DelegationRecord(**kwargs)


def _v3_hex(policy: MultiSigSigningPolicy) -> str:
    return delegation_canonical_payload_str(_v3_record(policy)).encode("utf-8").hex()


# --- 4 V3 byte-pins (record dispatch reproduces the kailash-rs bytes) --------


def test_v3_record_dispatch_reproduces_pinned_vectors() -> None:
    """The record-level v3 dispatch reproduces the pinned kailash-rs V3 bytes."""
    assert _v3_hex(_v1_policy()) == V1_2_OF_3, "V1 (2-of-3) record dispatch drifted"
    assert _v3_hex(_v3_policy()) == V3_3_OF_5, "V3 (3-of-5) record dispatch drifted"
    assert _v3_hex(_s2_policy()) == S2_ZERO_ONE, "S2 (zero/one) record dispatch drifted"
    assert (
        _v3_hex(_s3_policy()) == S3_ONE_BYTE_DIFF
    ), "S3 (1-byte-diff) record dispatch drifted"


def test_v3_bytes_carry_folded_policy_and_v3_token() -> None:
    """The v3 pre-image self-describes (v3 token) + folds the policy; no bundle."""
    payload = delegation_canonical_payload_str(_v3_record(_v1_policy()))
    assert '"signing_payload_version":"v3-complete"' in payload
    assert '"multi_sig_threshold":2' in payload
    assert '"multi_sig_authorized_signers":[' in payload
    assert '"multi_sig":true' in payload
    assert "multi_sig_bundle" not in payload  # signatures are NOT folded


# --- Byte-neutrality: v2 anchor + legacy UNCHANGED ---------------------------


def test_v2_anchor_byte_neutral_alongside_v3() -> None:
    """A NON-multi-sig record still reproduces the pinned V2 bytes (byte-neutral).

    Adding multi_sig / multi_sig_policy fields MUST NOT change the v2 pre-image.
    """
    payload = delegation_canonical_payload_str(_v2_record())
    assert payload.encode("utf-8").hex() == V2C_NON_MULTI_SIG, "V2 anchor drifted"
    assert "multi_sig" not in payload, "non-multi-sig v2 record leaked a multi_sig key"
    assert '"signing_payload_version":"v2-complete"' in payload


def test_legacy_record_bytes_unchanged() -> None:
    """A legacy (no structured / no multi-sig) record signs byte-identically."""
    record = DelegationRecord(
        id="del-legacy-s2b2",
        delegator_id="alice",
        delegatee_id="bob",
        task_id="t",
        capabilities_delegated=["LlmCall", "FileRead"],
        constraint_subset=["read_only"],
        delegated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="",
    )
    assert record.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY
    dispatched = delegation_canonical_payload_str(record)
    assert dispatched == serialize_for_signing(record.to_signing_payload())
    assert "multi_sig" not in dispatched


# --- select_signing_version → v3 selection logic -----------------------------


def test_select_version_multisig_is_v3() -> None:
    """A full multi-sig record selects v3-complete."""
    assert select_signing_version(_v3_record(_v1_policy())) == (
        DELEGATION_SIGNING_VERSION_V3
    )


def test_non_multi_sig_record_cannot_be_forced_v3() -> None:
    """A non-multi-sig record (multi_sig=False) NEVER selects v3."""
    record = _v2_record(multi_sig=False, multi_sig_policy=None)
    assert select_signing_version(record) == DELEGATION_SIGNING_VERSION_V2
    # Even a full-structured non-multi-sig record cannot be forced to v3.
    assert select_signing_version(record) != DELEGATION_SIGNING_VERSION_V3


def test_multi_sig_true_without_policy_raises() -> None:
    """multi_sig=True with NO policy is a mis-constructed record — fail closed."""
    record = _v3_record(_v1_policy())
    record.multi_sig_policy = None  # flag on, policy stripped → inconsistent
    with pytest.raises(ValueError, match="requires a multi_sig_policy"):
        select_signing_version(record)


def test_policy_without_multi_sig_flag_raises() -> None:
    """A policy set with multi_sig=False is a mis-constructed record — fail closed."""
    record = _v3_record(_v1_policy())
    record.multi_sig = False  # policy set, flag off → inconsistent
    with pytest.raises(ValueError, match="multi_sig=False"):
        select_signing_version(record)


def test_multi_sig_record_missing_structured_fold_fails_closed() -> None:
    """A multi-sig record MUST have the full structured fold — else fail closed.

    A multi-sig record MUST sign v3 (never legacy/v2, which drop the quorum
    binding); when the v3 bytes are not producible it fails closed rather than
    silently downgrading.
    """
    record = _v3_record(_v1_policy(), scope=None)
    with pytest.raises(ValueError, match="multi-sig record requires"):
        select_signing_version(record)


def test_multi_sig_record_narrowed_scope_fails_closed() -> None:
    """A multi-sig record with a narrowed dimension_scope fails closed (un-pinned)."""
    record = _v3_record(_v1_policy(), dimension_scope=frozenset({"financial"}))
    with pytest.raises(ValueError, match="narrowed dimension_scope"):
        select_signing_version(record)


# --- Threshold integer-type guard (cross-SDK byte-parity) --------------------


def test_float_threshold_rejected_at_construction() -> None:
    """A float threshold (2.0 → JCS "2.0") diverges from the rs int contract.

    threshold is folded verbatim into the V3 JCS pre-image; ``json.dumps(2.0)``
    → ``"2.0"`` while rs (integer type) emits ``"2"`` — a cross-SDK byte-parity
    hole. Fail closed at construction.
    """
    with pytest.raises(ValueError, match="threshold must be an int"):
        MultiSigSigningPolicy.new(2.0, [_key(1), _key(2), _key(3)])


def test_bool_threshold_rejected_at_construction() -> None:
    """A bool threshold (True → JCS "true") diverges from the rs int contract.

    bool is a subclass of int in Python, so it passes a naive isinstance(int)
    check yet serializes to ``"true"`` — it MUST be rejected explicitly.
    """
    with pytest.raises(ValueError, match="threshold must be an int"):
        MultiSigSigningPolicy.new(True, [_key(1)])


def test_int_threshold_still_constructs() -> None:
    """A normal int threshold constructs unchanged (the guard rejects non-int only)."""
    policy = MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)])
    assert policy.threshold == 2
    assert isinstance(policy.threshold, int) and not isinstance(policy.threshold, bool)


def test_from_dict_float_threshold_rejected() -> None:
    """from_dict of a persisted policy carrying a float threshold fails closed.

    from_dict re-runs __post_init__, so a store-tampered float threshold is
    rejected at deserialization (never reconstructs a byte-diverging policy).
    """
    d = _v1_policy().to_dict()
    d["threshold"] = 2.0
    with pytest.raises(ValueError, match="threshold must be an int"):
        MultiSigSigningPolicy.from_dict(d)


# --- Signer canonical-order invariance ---------------------------------------


def test_signer_order_invariance() -> None:
    """The pre-image sorts signers by hex → invariant to stored insertion order."""
    forward = MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)])
    reverse = MultiSigSigningPolicy.new(2, [_key(3), _key(2), _key(1)])
    shuffled = MultiSigSigningPolicy.new(2, [_key(2), _key(1), _key(3)])
    assert _v3_hex(forward) == _v3_hex(reverse) == _v3_hex(shuffled) == V1_2_OF_3


# --- QUORUM INTEGRITY (the #1841 headline) -----------------------------------


def test_quorum_integrity_threshold_mutation_fails_verify() -> None:
    """A store-write actor lowering the threshold 2→1 breaks the v3 signature."""
    private_key, public_key = generate_keypair()
    record = _v3_record(MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)]))
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    # The signed record verifies before tampering.
    assert verify_signature(
        delegation_canonical_payload_str(record), record.signature, public_key
    )

    # A store-writer weakens quorum: threshold 2 → 1, same signers.
    record.multi_sig_policy = MultiSigSigningPolicy.new(1, [_key(1), _key(2), _key(3)])
    assert not verify_signature(
        delegation_canonical_payload_str(record), record.signature, public_key
    ), "threshold mutation MUST break the v3 signature (quorum integrity)"


def test_quorum_integrity_signer_swap_fails_verify() -> None:
    """A store-write actor swapping an authorized signer breaks the v3 signature."""
    private_key, public_key = generate_keypair()
    record = _v3_record(MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)]))
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    # Swap key(3) → key(4) (an attacker's key).
    record.multi_sig_policy = MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(4)])
    assert not verify_signature(
        delegation_canonical_payload_str(record), record.signature, public_key
    ), "signer swap MUST break the v3 signature (quorum integrity)"


def test_quorum_integrity_signer_removal_fails_verify() -> None:
    """A store-write actor removing an authorized signer breaks the v3 signature."""
    private_key, public_key = generate_keypair()
    record = _v3_record(MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)]))
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    # Remove key(3) → a 2-of-2 the original signer never authorized.
    record.multi_sig_policy = MultiSigSigningPolicy.new(2, [_key(1), _key(2)])
    assert not verify_signature(
        delegation_canonical_payload_str(record), record.signature, public_key
    ), "signer removal MUST break the v3 signature (quorum integrity)"


# --- Downgrade attacks -------------------------------------------------------


def test_downgrade_v3_to_v2_fails_verify() -> None:
    """A v3→v2 version flip drops the policy fold → verify fails."""
    private_key, public_key = generate_keypair()
    record = _v3_record(_v1_policy())
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    record.signing_payload_version = DELEGATION_SIGNING_VERSION_V2
    assert not verify_signature(
        delegation_canonical_payload_str(record), record.signature, public_key
    ), "v3→v2 downgrade MUST fail verification"


def test_downgrade_v3_to_legacy_fails_verify() -> None:
    """A v3→legacy version flip drops the whole fold → verify fails."""
    private_key, public_key = generate_keypair()
    record = _v3_record(_v1_policy())
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    record.signing_payload_version = DELEGATION_SIGNING_VERSION_LEGACY
    assert not verify_signature(
        delegation_canonical_payload_str(record), record.signature, public_key
    ), "v3→legacy downgrade MUST fail verification"


# --- Real Ed25519 multi-sig round-trip ---------------------------------------


def test_v3_real_ed25519_round_trip() -> None:
    """Sign a v3 record with a real Ed25519 key; verify over the SAME pre-image."""
    private_key, public_key = generate_keypair()
    record = _v3_record(_v1_policy())

    payload = delegation_canonical_payload_str(record)
    record.signature = sign(payload, private_key)

    verify_payload = delegation_canonical_payload_str(record)
    assert verify_signature(verify_payload, record.signature, public_key)


# --- Persistence round-trip (to_dict / from_dict) ----------------------------


def test_v3_to_dict_from_dict_reconstructs_and_reproduces_bytes() -> None:
    """to_dict → from_dict reconstructs the policy + reproduces the pre-image + sig."""
    private_key, public_key = generate_keypair()
    record = _v3_record(_v1_policy())
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    d = record.to_dict()
    assert d["multi_sig"] is True
    assert d["multi_sig_policy"]["threshold"] == 2
    assert len(d["multi_sig_policy"]["authorized_signers"]) == 3

    restored = DelegationRecord.from_dict(d)
    assert restored.multi_sig is True
    assert restored.multi_sig_policy == record.multi_sig_policy
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V3

    # Byte-identical pre-image after the round-trip + the signature still verifies.
    assert delegation_canonical_payload_str(restored).encode("utf-8").hex() == V1_2_OF_3
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    )


def test_from_dict_tampered_policy_fails_closed() -> None:
    """A persisted policy tampered to a duplicate signer fails closed on from_dict.

    from_dict re-runs MultiSigSigningPolicy.__post_init__, so a store-write actor
    who duplicates a signer (weakening the quorum) is rejected at deserialization.
    """
    d = _v3_record(_v1_policy()).to_dict()
    signers = d["multi_sig_policy"]["authorized_signers"]
    signers[1] = signers[0]  # duplicate → weakened quorum
    with pytest.raises(ValueError, match="distinct"):
        DelegationRecord.from_dict(d)


def test_non_multi_sig_record_persists_without_multi_sig_keys() -> None:
    """A non-multi-sig record round-trips with NO multi_sig keys (prune-when-unset)."""
    record = _v2_record()
    d = record.to_dict()
    assert "multi_sig" not in d
    assert "multi_sig_policy" not in d

    restored = DelegationRecord.from_dict(d)
    assert restored.multi_sig is False
    assert restored.multi_sig_policy is None
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V2


# --- Multi-sig delegate() creation path (real ops, through the store) --------


async def test_delegate_multi_sig_produces_verifiable_v3_record() -> None:
    """delegate(..., multi_sig_policy=...) mints a signable + verifiable v3 record.

    The whole-second-timestamp end-to-end check: the v3 engine pre-image fails
    closed on sub-second precision, so the creation path MUST truncate
    delegated_at (and any inherited expires_at) to whole-second — else the v3
    sign path raises for every real caller (the S2b-1 latent-stub failure mode).
    """
    ops, _ = await _real_ops_with_delegator()
    policy = MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)])

    deleg = await ops.delegate(
        delegator_id="agent-delegator",
        delegatee_id="agent-multisig",
        task_id="task-ms",
        capabilities=["LlmCall"],
        constraints=_supervised_constraints(),
        resource_limits=_supervised_limits(),
        scope=_engineering_read_scope(),
        multi_sig_policy=policy,
    )

    assert deleg.signing_payload_version == DELEGATION_SIGNING_VERSION_V3
    assert deleg.multi_sig is True
    assert deleg.multi_sig_policy == policy
    # Whole-second truncation applied (v3 engine fails closed on sub-second).
    assert deleg.delegated_at.microsecond == 0
    # Verifiable through the store (real Ed25519 round-trip).
    assert (await ops.verify_delegation_chain("agent-multisig")).valid is True


async def test_delegate_multi_sig_without_structured_fold_fails_closed() -> None:
    """delegate() with a policy but NO structured fold fails closed before signing."""
    ops, _ = await _real_ops_with_delegator()
    policy = MultiSigSigningPolicy.new(1, [_key(9)])

    with pytest.raises(ValueError, match="multi-sig record requires"):
        await ops.delegate(
            delegator_id="agent-delegator",
            delegatee_id="agent-nofold",
            task_id="task-nofold",
            capabilities=["LlmCall"],
            multi_sig_policy=policy,  # no constraints/resource_limits/scope
        )

    # The failed multi-sig delegation MUST NOT have been persisted.
    from kailash.trust.exceptions import TrustChainNotFoundError

    with pytest.raises(TrustChainNotFoundError):
        await ops.trust_store.get_chain("agent-nofold")
