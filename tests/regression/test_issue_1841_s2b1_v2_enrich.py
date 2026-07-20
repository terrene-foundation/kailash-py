# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1841 S2b-1: DelegationRecord signs the cross-SDK V2Complete pre-image.

A NON-multi-sig ``DelegationRecord`` carrying structured
``constraints`` / ``resource_limits`` / ``scope`` (and an unscoped
``dimension_scope``) signs the ``v2-complete`` engine pre-image instead of the
pre-migration ``legacy-python-v0`` schema. This is a SECURITY-CRITICAL,
BYTE-CHANGING, cross-SDK-lockstep migration; the tests here pin:

* the ``V2C_NON_MULTI_SIG`` byte vector (byte-for-byte cross-SDK contract);
* legacy bytes UNCHANGED for a pre-S2b record (backward-compat, byte-identical);
* the ``dimension_scope`` gate (a narrowed record stays legacy; a direct bridge
  call on narrowed scope raises);
* real Ed25519 round-trip sign -> verify over the V2 pre-image (Tier-2 crypto,
  NO mocking);
* to_dict -> from_dict persistence reconstructs the structured fields and
  reproduces the signature;
* capability INSERTION ORDER is preserved on the V2 path (the engine matches
  kailash-rs; the legacy path SORTS).

The pinned ``V2C_NON_MULTI_SIG`` hex is the kailash-rs canonical byte vector
(vendored in ``test_delegation_signing_payload_vectors.py``); it is re-used here
so the record-level dispatch is byte-checked against the SAME cross-SDK anchor
as the engine-level test.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.chain import (
    ALL_DIMENSIONS,
    DELEGATION_SIGNING_VERSION_LEGACY,
    DELEGATION_SIGNING_VERSION_V2,
    DelegationRecord,
)
from kailash.trust.exceptions import UnsupportedSigningPayloadVersionError
from kailash.trust.signing.crypto import (
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)
from kailash.trust.signing.delegation_payload import (
    ConstraintDimensions,
    DelegationScope,
    ResourceLimits,
    SigningPayloadVersion,
    TrustLevel,
)
from kailash.trust.signing.delegation_record_signing import (
    delegation_canonical_payload_str,
    delegation_record_signing_payload,
    select_signing_version,
)

# The pinned kailash-rs V2Complete byte vector for the NON-multi-sig fixed
# record (identical hex to test_delegation_signing_payload_vectors.py :: V2C).
V2C_NON_MULTI_SIG = "7b226361706162696c6974696573223a5b224c6c6d43616c6c225d2c22636f6e73747261696e7473223a7b22616c6c6f775f636f64655f657865637574696f6e223a66616c73652c22616c6c6f775f64656c65676174696f6e223a66616c73652c22616c6c6f775f66696c6573797374656d223a66616c73652c22616c6c6f775f6e6574776f726b223a747275652c22616c6c6f775f73746174655f6d75746174696f6e223a747275652c22616c6c6f7765645f746f6f6c73223a6e756c6c2c226d61785f636f6e746578745f746f6b656e73223a31363338342c22726561736f6e696e675f7265717569726564223a66616c73657d2c22637265617465645f6174223a22323032362d30312d30325430333a30343a30352b30303a3030222c2264656c6567617465223a22626f62222c2264656c65676174696f6e5f6964223a2230303030303030302d303030302d343030302d383030302d303030303030303030303031222c2264656c656761746f72223a22616c696365222c22657870697265735f6174223a6e756c6c2c22706172656e745f64656c65676174696f6e5f6964223a6e756c6c2c22726561736f6e696e675f74726163655f68617368223a6e756c6c2c227265736f757263655f6c696d697473223a7b226d61785f657865637574696f6e5f73656373223a3330302c226d61785f6c6c6d5f63616c6c73223a35302c226d61785f746f6f6c5f63616c6c73223a32302c226d61785f746f74616c5f746f6b656e73223a3130303030307d2c2273636f7065223a7b22646f6d61696e223a22656e67696e656572696e67222c226d61785f66696e616e6369616c5f63656e7473223a6e756c6c2c226f7065726174696f6e73223a5b2272656164225d7d2c227369676e696e675f7061796c6f61645f76657273696f6e223a2276322d636f6d706c657465227d"

pytestmark = pytest.mark.regression


def _supervised_constraints() -> ConstraintDimensions:
    return ConstraintDimensions.for_level(TrustLevel.SUPERVISED)


def _supervised_limits() -> ResourceLimits:
    return ResourceLimits.for_level(TrustLevel.SUPERVISED)


def _engineering_read_scope() -> DelegationScope:
    return DelegationScope.new("engineering").with_operation("read")


def _v2_record(**overrides) -> DelegationRecord:
    """Build the fixed-input V2 record (matches the rs ``fixed_inputs()``)."""
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


def _legacy_record(**overrides) -> DelegationRecord:
    """A pre-S2b record: no structured fields, default legacy version."""
    kwargs = dict(
        id="del-legacy-1",
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


# --- Byte-pin (TDD anchor) ---------------------------------------------------


def test_v2c_non_multi_sig_byte_pin() -> None:
    """A V2 record's canonical dispatch string == the pinned rs V2Complete bytes."""
    record = _v2_record()
    payload_str = delegation_canonical_payload_str(record)
    assert (
        payload_str.encode("utf-8").hex() == V2C_NON_MULTI_SIG
    ), "V2Complete record-dispatch bytes drifted from the kailash-rs pin"
    # Structural spot-checks the byte-pin also encodes.
    assert '"signing_payload_version":"v2-complete"' in payload_str
    assert "multi_sig" not in payload_str


# --- Backward-compat: legacy bytes UNCHANGED ---------------------------------


def test_legacy_record_dispatch_is_byte_identical_to_pre_migration() -> None:
    """A default (no structured fields) record signs the legacy pre-image unchanged."""
    record = _legacy_record()
    assert record.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY
    assert select_signing_version(record) == DELEGATION_SIGNING_VERSION_LEGACY

    dispatched = delegation_canonical_payload_str(record)
    expected = serialize_for_signing(record.to_signing_payload())
    assert (
        dispatched == expected
    ), "legacy dispatch bytes drifted from to_signing_payload"


def test_legacy_to_signing_payload_has_no_v2_fields() -> None:
    """The legacy pre-image MUST NOT carry the new structured / version keys."""
    record = (
        _v2_record()
    )  # structured fields present, but legacy pre-image ignores them
    legacy_payload = record.to_signing_payload()
    for absent in (
        "constraints",
        "resource_limits",
        "scope",
        "signing_payload_version",
    ):
        assert (
            absent not in legacy_payload
        ), f"legacy to_signing_payload leaked {absent!r} — legacy bytes changed"


# --- dimension_scope gate ----------------------------------------------------


def test_narrowed_dimension_scope_stays_legacy() -> None:
    """A narrowed-dimension_scope record with structured fields stays legacy-python-v0."""
    record = _v2_record(
        dimension_scope=frozenset({"financial", "operational"}),
        signing_payload_version=DELEGATION_SIGNING_VERSION_LEGACY,
    )
    assert select_signing_version(record) == DELEGATION_SIGNING_VERSION_LEGACY


def test_narrowed_scope_direct_bridge_call_raises() -> None:
    """A direct engine-bridge call on a narrowed-scope record fails closed."""
    record = _v2_record(dimension_scope=frozenset({"financial"}))
    with pytest.raises(ValueError, match="dimension_scope is narrowed"):
        delegation_record_signing_payload(
            record,
            SigningPayloadVersion.V2_COMPLETE,
            constraints=record.constraints,
            resource_limits=record.resource_limits,
            scope=record.scope,
        )


def test_v3_version_fails_closed() -> None:
    """A record declaring v3-complete fails closed (multi-sig is a later shard)."""
    from kailash.trust.chain import DELEGATION_SIGNING_VERSION_V3

    record = _v2_record(signing_payload_version=DELEGATION_SIGNING_VERSION_V3)
    with pytest.raises(UnsupportedSigningPayloadVersionError):
        delegation_canonical_payload_str(record)


# --- select_signing_version selection logic ----------------------------------


def test_select_version_all_three_present_is_v2_none_is_legacy() -> None:
    """All three structured fields → v2; none → legacy."""
    assert select_signing_version(_v2_record()) == DELEGATION_SIGNING_VERSION_V2

    none_record = _v2_record(
        constraints=None,
        resource_limits=None,
        scope=None,
        signing_payload_version=DELEGATION_SIGNING_VERSION_LEGACY,
    )
    assert select_signing_version(none_record) == DELEGATION_SIGNING_VERSION_LEGACY


@pytest.mark.parametrize(
    "kwargs,missing",
    [
        ({"scope": None}, "scope"),
        ({"constraints": None}, "constraints"),
        ({"resource_limits": None}, "resource_limits"),
        ({"constraints": None, "resource_limits": None}, "constraints"),
        ({"resource_limits": None, "scope": None}, "resource_limits"),
    ],
)
def test_select_version_partial_supply_raises(kwargs, missing) -> None:
    """PARTIAL structured-field supply fails closed (all-or-nothing) — #1841 S2b-1 FIX 1.

    A partial-supply record would silently downgrade to legacy (dropping the
    supplied fields from the signature) while to_dict persists them UNSIGNED —
    a fail-open secure-default. select_signing_version MUST raise instead.
    """
    record = _v2_record(**kwargs)
    with pytest.raises(ValueError, match="must be supplied together or all omitted"):
        select_signing_version(record)
    # The raised message names the missing field(s).
    with pytest.raises(ValueError, match=missing):
        select_signing_version(record)


# --- Real Ed25519 round-trip (Tier-2 crypto, NO mocking) ---------------------


def test_v2_record_real_ed25519_round_trip() -> None:
    """Sign a V2 record with a real Ed25519 key; verify over the SAME pre-image."""
    private_key, public_key = generate_keypair()
    record = _v2_record()

    payload = delegation_canonical_payload_str(record)
    signature = sign(payload, private_key)
    record.signature = signature

    # Re-derive the pre-image and verify (mirrors _verify_delegation_signature).
    verify_payload = delegation_canonical_payload_str(record)
    assert verify_signature(verify_payload, record.signature, public_key)

    # A tampered scope changes the pre-image → verification MUST fail.
    tampered = _v2_record(scope=DelegationScope.new("finance").with_operation("read"))
    tampered.signature = record.signature
    assert not verify_signature(
        delegation_canonical_payload_str(tampered), tampered.signature, public_key
    )


def test_legacy_record_real_ed25519_round_trip_survives_persistence() -> None:
    """A legacy record signs, persists via to_dict/from_dict, and re-verifies."""
    private_key, public_key = generate_keypair()
    record = _legacy_record()
    record.signature = sign(delegation_canonical_payload_str(record), private_key)

    restored = DelegationRecord.from_dict(record.to_dict())
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY
    assert verify_signature(
        delegation_canonical_payload_str(restored), restored.signature, public_key
    )


# --- Persistence round-trip (V2) ---------------------------------------------


def test_v2_to_dict_from_dict_reconstructs_and_reproduces_bytes() -> None:
    """to_dict -> from_dict reconstructs the structured fields + reproduces the pre-image."""
    record = _v2_record()
    restored = DelegationRecord.from_dict(record.to_dict())

    assert restored.constraints == record.constraints
    assert restored.resource_limits == record.resource_limits
    assert restored.scope == record.scope
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_V2

    # Byte-identical pre-image after the round-trip.
    assert (
        delegation_canonical_payload_str(restored).encode("utf-8").hex()
        == V2C_NON_MULTI_SIG
    )


def test_pre_s2b_record_from_dict_all_none_and_legacy() -> None:
    """from_dict of a persisted pre-S2b record (no structured keys) → all None, legacy."""
    legacy_dict = _legacy_record().to_dict()
    # Simulate an on-wire pre-S2b record: strip the structured keys entirely.
    for k in ("constraints", "resource_limits", "scope"):
        legacy_dict.pop(k, None)
    restored = DelegationRecord.from_dict(legacy_dict)
    assert restored.constraints is None
    assert restored.resource_limits is None
    assert restored.scope is None
    assert restored.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY


# --- Capability insertion-order preservation (V2 path) -----------------------


def test_v2_preserves_capability_insertion_order() -> None:
    """The V2 engine path PRESERVES capability insertion order (legacy SORTS)."""
    unsorted_caps = ["Zeta", "Alpha", "Mid"]
    record = _v2_record(capabilities_delegated=unsorted_caps)
    payload = delegation_canonical_payload_str(record)
    assert (
        '"capabilities":["Zeta","Alpha","Mid"]' in payload
    ), "V2 path MUST preserve capability insertion order (must NOT sort)"

    # Contrast: the legacy pre-image SORTS the same capabilities.
    legacy_payload = record.to_signing_payload()
    assert legacy_payload["capabilities_delegated"] == ["Alpha", "Mid", "Zeta"]


# --- dimension_scope binding survives to_dict/from_dict ----------------------


def test_dimension_scope_default_unset_yields_v2_after_roundtrip() -> None:
    """A default (all-dimensions) V2 record round-trips to V2, not legacy."""
    record = _v2_record()
    assert frozenset(record.dimension_scope) == frozenset(ALL_DIMENSIONS)
    restored = DelegationRecord.from_dict(record.to_dict())
    assert select_signing_version(restored) == DELEGATION_SIGNING_VERSION_V2


# --- FIX 2: verify FAILS CLOSED (returns valid=False), never raises -----------


class _SimpleRegistry:
    """Real in-memory authority registry (NOT a mock) — mirrors the lifecycle test."""

    def __init__(self):
        self._authorities = {}

    async def initialize(self):  # noqa: D401 - protocol no-op
        pass

    def register(self, authority):
        self._authorities[authority.id] = authority

    async def get_authority(self, authority_id, include_inactive=False):
        from kailash.trust.exceptions import AuthorityNotFoundError

        authority = self._authorities.get(authority_id)
        if authority is None:
            raise AuthorityNotFoundError(authority_id)
        return authority

    async def update_authority(self, authority):
        self._authorities[authority.id] = authority


async def _real_ops_with_delegator():
    """Build a real TrustOperations (real crypto + real store, NO mocking) and a
    delegator trust chain rooted at ``org-acme``."""
    from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
    from kailash.trust.chain import AuthorityType, CapabilityType
    from kailash.trust.chain_store.memory import InMemoryTrustStore
    from kailash.trust.operations import (
        CapabilityRequest,
        TrustKeyManager,
        TrustOperations,
    )

    private_key, public_key = generate_keypair()
    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="acme-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )
    registry = _SimpleRegistry()
    registry.register(authority)
    key_manager = TrustKeyManager()
    key_manager.register_key("acme-key-001", private_key)
    store = InMemoryTrustStore()
    await store.initialize()
    ops = TrustOperations(
        authority_registry=registry, key_manager=key_manager, trust_store=store
    )
    await ops.initialize()
    delegator_chain = await ops.establish(
        agent_id="agent-delegator",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="LlmCall", capability_type=CapabilityType.ACTION
            )
        ],
    )
    return ops, delegator_chain


async def test_verify_returns_false_on_v2_record_missing_structured_fields() -> None:
    """A v2-labelled record with NO structured fields → verify returns valid=False.

    #1841 S2b-1 FIX 2: the engine bridge fails closed with a ValueError; the verify
    path MUST catch it and return valid=False, NOT let the exception escape
    (DoS-via-exception).
    """
    ops, delegator_chain = await _real_ops_with_delegator()

    bad = DelegationRecord(
        id="del-bad-v2",
        delegator_id="agent-delegator",
        delegatee_id="agent-x",
        task_id="t",
        capabilities_delegated=["LlmCall"],
        constraint_subset=[],
        delegated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="not-a-real-sig",
        signing_payload_version=DELEGATION_SIGNING_VERSION_V2,
        # constraints / resource_limits / scope deliberately absent → bridge raises.
    )

    result = await ops._verify_delegation_signature(bad, delegator_chain)
    assert result.valid is False
    assert result.reason and "could not be built" in result.reason


async def test_verify_chain_returns_false_on_v2_record_missing_fields() -> None:
    """verify_delegation_chain also fails closed (does NOT raise) on the bad record."""
    ops, delegator_chain = await _real_ops_with_delegator()

    bad = DelegationRecord(
        id="del-bad-v2-chain",
        delegator_id="agent-delegator",
        delegatee_id="agent-y",
        task_id="t",
        capabilities_delegated=["LlmCall"],
        constraint_subset=[],
        delegated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        signature="not-a-real-sig",
        signing_payload_version=DELEGATION_SIGNING_VERSION_V2,
    )
    # Attach the bad delegation to agent-y's chain and verify the chain.
    delegatee_chain = await ops.trust_store.get_chain("agent-delegator")
    delegatee_chain.delegations.append(bad)
    await ops.trust_store.update_chain("agent-delegator", delegatee_chain)

    result = await ops.verify_delegation_chain("agent-delegator")
    assert result.valid is False  # fails closed, no exception escaped


async def test_delegate_partial_structured_supply_raises() -> None:
    """delegate() with PARTIAL structured params fails closed — #1841 S2b-1 FIX 1."""
    ops, _ = await _real_ops_with_delegator()

    with pytest.raises(ValueError, match="must be supplied together or all omitted"):
        await ops.delegate(
            delegator_id="agent-delegator",
            delegatee_id="agent-z",
            task_id="task-partial",
            capabilities=["LlmCall"],
            constraints=_supervised_constraints(),
            resource_limits=_supervised_limits(),
            scope=None,  # partial supply → raise before signing/persisting
        )
    # The partial-supply delegation MUST NOT have been persisted.
    from kailash.trust.exceptions import TrustChainNotFoundError

    with pytest.raises(TrustChainNotFoundError):
        await ops.trust_store.get_chain("agent-z")


async def test_delegate_all_three_v2_none_legacy_unchanged() -> None:
    """delegate() all-3 → v2 record; none → legacy record (behavior UNCHANGED)."""
    ops, _ = await _real_ops_with_delegator()

    v2_deleg = await ops.delegate(
        delegator_id="agent-delegator",
        delegatee_id="agent-v2",
        task_id="task-v2",
        capabilities=["LlmCall"],
        constraints=_supervised_constraints(),
        resource_limits=_supervised_limits(),
        scope=_engineering_read_scope(),
    )
    assert v2_deleg.signing_payload_version == DELEGATION_SIGNING_VERSION_V2

    legacy_deleg = await ops.delegate(
        delegator_id="agent-delegator",
        delegatee_id="agent-legacy",
        task_id="task-legacy",
        capabilities=["LlmCall"],
    )
    assert legacy_deleg.signing_payload_version == DELEGATION_SIGNING_VERSION_LEGACY

    # Both records verify (real Ed25519 round-trip through the store).
    assert (await ops.verify_delegation_chain("agent-v2")).valid is True
    assert (await ops.verify_delegation_chain("agent-legacy")).valid is True
