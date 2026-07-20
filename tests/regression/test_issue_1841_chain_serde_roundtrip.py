# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1841 chain/store/interop serializer fold-field round-trip (HIGH correctness).

#1841 S2b-1/S2b-2 added structured signing fields (``constraints`` /
``resource_limits`` / ``scope`` / ``multi_sig`` / ``multi_sig_policy``) to
``DelegationRecord`` so a v2/v3 record signs the cross-SDK V2Complete/V3Complete
pre-image. They extended ``DelegationRecord.to_dict`` / ``from_dict`` — BUT the
SIBLING chain-level serializer ``TrustLineageChain._serialize_delegation`` /
``_deserialize_delegation`` (used by ``TrustLineageChain.to_dict`` / ``from_dict``,
the chain-level serialization every persistent store uses) AND the two interop
serializers (W3C VC ``interop/w3c_vc.py`` + JWT ``interop/jwt.py``) OMITTED all
five fold fields.

RESULT (the break): a v2/v3 delegation serialized-then-deserialized through chain
persistence (or interop) reloads with ``signing_payload_version`` set but the
fold fields ``None`` → ``delegation_canonical_payload_str`` recomputes a DIFFERENT
(or fail-closed) pre-image → ``verify_signature`` returns False. v2/v3 signing is
non-functional end-to-end through the store — the ``security.md`` Multi-Site
Kwarg Plumbing failure (fields plumbed through ONE serializer, missed the
siblings).

The persistence dict is NOT a cross-SDK signing pre-image (the signing bytes come
from ``delegation_canonical_payload_str`` reading the RECORD FIELDS, not the
dict) — so the dict shape needs NO cross-SDK byte-pin; it just needs to FAITHFULLY
round-trip the five fields so the reconstructed record recomputes the SAME signing
pre-image and the signature verifies.

Tier-2: real Ed25519, NO mocking (the user-flow-validation MUST-7 write-surface
boundary fixtures — the store/chain round-trip IS the persistence boundary).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.chain import (
    ALL_DIMENSIONS,
    DELEGATION_SIGNING_VERSION_LEGACY,
    DELEGATION_SIGNING_VERSION_V2,
    DELEGATION_SIGNING_VERSION_V3,
    AuthorityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.chain_store.sqlite import SqliteTrustStore
from kailash.trust.interop import jwt as jwt_interop
from kailash.trust.interop import w3c_vc
from kailash.trust.interop.ucan import from_ucan, to_ucan
from kailash.trust.signing.crypto import generate_keypair, sign, verify_signature
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

pytestmark = pytest.mark.regression


# --- Fixed inputs (mirror the S2b-1 / S2b-2 record builders) -----------------


def _key(n: int) -> bytes:
    return bytes([n]) * 32


def _supervised_constraints() -> ConstraintDimensions:
    return ConstraintDimensions.for_level(TrustLevel.SUPERVISED)


def _supervised_limits() -> ResourceLimits:
    return ResourceLimits.for_level(TrustLevel.SUPERVISED)


def _engineering_read_scope() -> DelegationScope:
    return DelegationScope.new("engineering").with_operation("read")


def _v2_record(**overrides) -> DelegationRecord:
    kwargs = dict(
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
        signing_payload_version=DELEGATION_SIGNING_VERSION_V2,
    )
    kwargs.update(overrides)
    return DelegationRecord(**kwargs)


def _v3_record(**overrides) -> DelegationRecord:
    kwargs = dict(
        id="00000000-0000-4000-8000-000000000002",
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
        multi_sig=True,
        multi_sig_policy=MultiSigSigningPolicy.new(2, [_key(1), _key(2), _key(3)]),
        signing_payload_version=DELEGATION_SIGNING_VERSION_V3,
    )
    kwargs.update(overrides)
    return DelegationRecord(**kwargs)


def _legacy_record(**overrides) -> DelegationRecord:
    kwargs = dict(
        id="del-legacy-chainserde",
        delegator_id="alice",
        delegatee_id="bob",
        task_id="task-legacy",
        capabilities_delegated=["LlmCall", "FileRead"],
        constraint_subset=["read_only"],
        delegated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="",
    )
    kwargs.update(overrides)
    return DelegationRecord(**kwargs)


def _genesis() -> GenesisRecord:
    return GenesisRecord(
        id="genesis-1",
        agent_id="agent-bob",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="genesis-sig",
    )


def _signed(record: DelegationRecord, private_key) -> DelegationRecord:
    """Sign a record over its canonical pre-image (real Ed25519)."""
    record.signature = sign(delegation_canonical_payload_str(record), private_key)
    return record


def _chain_with(record: DelegationRecord) -> TrustLineageChain:
    return TrustLineageChain(genesis=_genesis(), delegations=[record])


async def _store_roundtrip(record: DelegationRecord, db_path) -> DelegationRecord:
    """Persist a signed delegation through a REAL SqliteTrustStore and reload.

    The SqliteTrustStore serializes via ``chain.to_dict()`` then PATCHES IN the
    genesis / capability / delegation signatures (to_dict omits them for inline
    dicts) — but does NOT patch the S2b fold fields, so a chain serializer that
    drops them makes the reloaded v2/v3 record unverifiable. This is the exact
    end-to-end persistence path (user-flow-validation MUST-7 write boundary).
    """
    store = SqliteTrustStore(db_path=str(db_path))
    await store.initialize()
    try:
        agent_id = await store.store_chain(_chain_with(record))
        reloaded = await store.get_chain(agent_id)
    finally:
        await store.close()
    (restored,) = reloaded.delegations
    return restored


# =============================================================================
# STEP 1 — the break (v2/v3 non-functional through the store)
# =============================================================================


async def test_v2_record_verifies_after_store_roundtrip(tmp_path) -> None:
    """A v2 record signed, persisted through the SQLite store, re-verifies."""
    private_key, public_key = generate_keypair()
    record = _signed(_v2_record(), private_key)

    restored = await _store_roundtrip(record, tmp_path / "v2.db")

    # The fold fields survived the store round-trip (field-identical record).
    assert restored.constraints == record.constraints
    assert restored.resource_limits == record.resource_limits
    assert restored.scope == record.scope
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V2
    assert select_signing_version(restored) == DELEGATION_SIGNING_VERSION_V2

    # The reconstructed record recomputes the SAME signing pre-image → verifies.
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v2 delegation signature invalid after store round-trip (fold fields dropped)"


async def test_v3_record_verifies_after_store_roundtrip(tmp_path) -> None:
    """A v3 multi-sig record signed, persisted through the store, re-verifies."""
    private_key, public_key = generate_keypair()
    record = _signed(_v3_record(), private_key)

    restored = await _store_roundtrip(record, tmp_path / "v3.db")

    assert restored.multi_sig is True
    assert restored.multi_sig_policy == record.multi_sig_policy
    assert restored.constraints == record.constraints
    assert restored.resource_limits == record.resource_limits
    assert restored.scope == record.scope
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V3
    assert select_signing_version(restored) == DELEGATION_SIGNING_VERSION_V3

    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v3 delegation signature invalid after store round-trip (fold fields dropped)"


# =============================================================================
# STEP 4 — interop (W3C VC + JWT) round-trip: fold fields survive + verify
# =============================================================================


def _w3c_roundtrip(
    record: DelegationRecord, private_key, public_key
) -> DelegationRecord:
    """Round a signed delegation through the real W3C VC export/import user path.

    The VC PROOF is signed/verified with the issuer keypair (here reused as the
    delegation keypair); the delegation's OWN Ed25519 signature is what the caller
    re-verifies after import.
    """
    vc = w3c_vc.export_as_verifiable_credential(
        _chain_with(record), issuer_did="did:eatp:org:acme", signing_key=private_key
    )
    restored_chain = w3c_vc.import_from_verifiable_credential(vc, public_key=public_key)
    (restored,) = restored_chain.delegations
    return restored


def test_v2_record_survives_w3c_vc_roundtrip() -> None:
    """A v2 record round-tripped through the W3C VC export/import path verifies."""
    private_key, public_key = generate_keypair()
    record = _signed(_v2_record(), private_key)

    restored = _w3c_roundtrip(record, private_key, public_key)

    assert restored.constraints == record.constraints
    assert restored.resource_limits == record.resource_limits
    assert restored.scope == record.scope
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V2
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v2 delegation signature invalid after W3C VC round-trip"


def test_v3_record_survives_w3c_vc_roundtrip() -> None:
    """A v3 record round-tripped through the W3C VC export/import path verifies."""
    private_key, public_key = generate_keypair()
    record = _signed(_v3_record(), private_key)

    restored = _w3c_roundtrip(record, private_key, public_key)

    assert restored.multi_sig is True
    assert restored.multi_sig_policy == record.multi_sig_policy
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V3
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v3 delegation signature invalid after W3C VC round-trip"


def test_v2_record_survives_jwt_roundtrip() -> None:
    """A v2 record round-tripped through the JWT serializer verifies."""
    private_key, public_key = generate_keypair()
    record = _signed(_v2_record(), private_key)

    serialized = jwt_interop._serialize_delegation(record)
    restored = jwt_interop._deserialize_delegation(serialized)

    assert restored.constraints == record.constraints
    assert restored.resource_limits == record.resource_limits
    assert restored.scope == record.scope
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V2
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v2 delegation signature invalid after JWT round-trip"


def test_v3_record_survives_jwt_roundtrip() -> None:
    """A v3 record round-tripped through the JWT serializer verifies (quorum bound)."""
    private_key, public_key = generate_keypair()
    record = _signed(_v3_record(), private_key)

    serialized = jwt_interop._serialize_delegation(record)
    restored = jwt_interop._deserialize_delegation(serialized)

    assert restored.multi_sig is True
    assert restored.multi_sig_policy == record.multi_sig_policy
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V3
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v3 delegation signature invalid after JWT round-trip"


def test_v2_record_survives_ucan_roundtrip() -> None:
    """A v2 record round-tripped through the UCAN serializer verifies.

    UCAN preserves the ORIGINAL EATP delegation signature (``eatp_original_
    signature``); it is a fourth same-class serializer that dropped the fold
    fields (found via the security.md multi-site sweep, not named in the brief).
    """
    private_key, public_key = generate_keypair()
    record = _signed(_v2_record(), private_key)

    restored = from_ucan(to_ucan(record, private_key), public_key)

    assert restored.constraints == record.constraints
    assert restored.resource_limits == record.resource_limits
    assert restored.scope == record.scope
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V2
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v2 delegation signature invalid after UCAN round-trip"


def test_v3_record_survives_ucan_roundtrip() -> None:
    """A v3 record round-tripped through the UCAN serializer verifies (quorum bound)."""
    private_key, public_key = generate_keypair()
    record = _signed(_v3_record(), private_key)

    restored = from_ucan(to_ucan(record, private_key), public_key)

    assert restored.multi_sig is True
    assert restored.multi_sig_policy == record.multi_sig_policy
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V3
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "v3 delegation signature invalid after UCAN round-trip"


def test_legacy_record_survives_ucan_roundtrip() -> None:
    """A legacy record still round-trips through UCAN + verifies (byte-neutral facts)."""
    private_key, public_key = generate_keypair()
    record = _signed(_legacy_record(), private_key)

    token = to_ucan(record, private_key)
    restored = from_ucan(token, public_key)

    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY
    assert restored.constraints is None
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "legacy delegation signature invalid after UCAN round-trip"


# =============================================================================
# BYTE-NEUTRALITY — a legacy record's chain-serialized dict is UNCHANGED
# =============================================================================


def test_legacy_record_chain_dict_carries_no_fold_keys() -> None:
    """A legacy record's chain-serialized delegation dict has NO fold-field keys."""
    chain = _chain_with(_legacy_record())
    (deleg_dict,) = chain.to_dict()["delegations"]

    for absent in (
        "constraints",
        "resource_limits",
        "scope",
        "multi_sig",
        "multi_sig_policy",
    ):
        assert absent not in deleg_dict, (
            f"legacy chain-serialized delegation leaked {absent!r} — prune-when-unset "
            "byte-neutrality violated"
        )


async def test_legacy_record_verifies_after_store_roundtrip(tmp_path) -> None:
    """A legacy record still signs + round-trips through the store + verifies."""
    private_key, public_key = generate_keypair()
    record = _signed(_legacy_record(), private_key)

    restored = await _store_roundtrip(record, tmp_path / "legacy.db")

    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY
    assert restored.constraints is None
    assert restored.resource_limits is None
    assert restored.scope is None
    assert restored.multi_sig is False
    assert restored.multi_sig_policy is None
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "legacy delegation signature invalid after chain round-trip"


# =============================================================================
# STEP 3 — from_dict consistency reject (fail-closed on a tampered record)
# =============================================================================


def test_deserialize_rejects_multi_sig_without_policy() -> None:
    """A persisted chain dict with multi_sig=True but no policy → ValueError."""
    chain_dict = _chain_with(_v3_record()).to_dict()
    (deleg,) = chain_dict["delegations"]
    deleg.pop("multi_sig_policy", None)  # tamper: strip the policy

    with pytest.raises(ValueError, match="multi_sig"):
        TrustLineageChain.from_dict(chain_dict)


def test_deserialize_rejects_multi_sig_with_non_v3_version() -> None:
    """A persisted chain dict with multi_sig=True + v2 version → ValueError."""
    chain_dict = _chain_with(_v3_record()).to_dict()
    (deleg,) = chain_dict["delegations"]
    deleg["signing_payload_version"] = DELEGATION_SIGNING_VERSION_V2  # tamper

    with pytest.raises(ValueError, match="multi_sig"):
        TrustLineageChain.from_dict(chain_dict)


def test_record_from_dict_rejects_multi_sig_without_policy() -> None:
    """DelegationRecord.from_dict itself fails closed on the inconsistent record."""
    record_dict = _v3_record().to_dict()
    record_dict.pop("multi_sig_policy", None)

    with pytest.raises(ValueError, match="multi_sig"):
        DelegationRecord.from_dict(record_dict)


# =============================================================================
# dimension_scope faithful round-trip (same serializer, same bug class)
# =============================================================================


async def test_narrowed_dimension_scope_survives_store_roundtrip(tmp_path) -> None:
    """A legacy record with a NARROWED dimension_scope round-trips + verifies.

    ``to_signing_payload`` (the legacy pre-image) binds ``sorted(dimension_scope)``;
    the chain sibling serializer historically DROPPED dimension_scope → a narrowed
    record reloaded as ALL_DIMENSIONS → different legacy pre-image → verify False.
    Same serializer, same faithful-round-trip class as the fold fields.
    """
    private_key, public_key = generate_keypair()
    record = _signed(
        _legacy_record(dimension_scope=frozenset({"financial", "operational"})),
        private_key,
    )
    assert frozenset(record.dimension_scope) != frozenset(ALL_DIMENSIONS)

    restored = await _store_roundtrip(record, tmp_path / "narrowed.db")

    assert frozenset(restored.dimension_scope) == frozenset(record.dimension_scope)
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    ), "narrowed-dimension_scope legacy record fails verify after store round-trip"
