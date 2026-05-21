# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 tests for the canonical Delegate type substrate (S2 + S2.5 of #1035).

Mirrors invariants surfaced in the kailash-rs reference extraction report at
``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-
extraction.md`` §1 (kailash-delegate-types). S2.5 restructures S2's flat
anchor types into the canonical rs shape per /autonomize Option A:

- ``Identity`` → ``DelegateIdentity`` with opaque delegate_id UUID + 3 refs
- ``Role`` with opaque role_id UUID + structured RoleScope + RoleLifecycleState
- ``GenesisRecord`` → ``DelegateGenesisRecord`` composing the existing
  ``kailash.trust.chain.GenesisRecord`` (§249 compose-don't-re-derive)
- ``PrincipalDirectory.resolve`` keyed on UUID delegate_id
"""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    LifecycleError,
    LifecycleState,
    PrincipalDirectory,
    Role,
    RoleLifecycleState,
    RoleScope,
)
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType
from kailash.trust.chain import GenesisRecord as SubstrateGenesisRecord

# ---------------------------------------------------------------------------
# Test fixtures — substrate genesis block (cryptographic surface)
# ---------------------------------------------------------------------------


def _substrate_genesis(
    *,
    signature: str = "d" * 128,
    signature_algorithm: str = "Ed25519",
) -> SubstrateGenesisRecord:
    """Build a substrate GenesisRecord with default Ed25519 128-hex signature."""
    return SubstrateGenesisRecord(
        id="g-test-0001",
        agent_id="agent-1",
        authority_id="auth-1",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature=signature,
        signature_algorithm=signature_algorithm,
    )


def _delegate_genesis(**overrides: object) -> DelegateGenesisRecord:
    defaults: dict[str, object] = {
        "block": _substrate_genesis(),
        "spec_version": "1",
        "capabilities": ("read", "write"),
    }
    defaults.update(overrides)
    return DelegateGenesisRecord(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LifecycleState — D3 linear chain
# ---------------------------------------------------------------------------


def test_lifecycle_state_chain_exhaustive() -> None:
    """The 6-state chain mirrors rs ``LifecycleState`` exactly."""
    members = list(LifecycleState)
    assert len(members) == 6
    assert [m.value for m in members] == [
        "proposed",
        "instantiated",
        "posture_graded",
        "active",
        "retired",
        "archived",
    ]


def test_lifecycle_state_wire_format_is_lowercase_string() -> None:
    """Cross-SDK canonical wire format: lowercase string value."""
    assert LifecycleState.POSTURE_GRADED.value == "posture_graded"
    assert LifecycleState.ACTIVE == "active"


# ---------------------------------------------------------------------------
# LifecycleError — typed exception with named-successor message
# ---------------------------------------------------------------------------


def test_lifecycle_error_typed() -> None:
    err = LifecycleError(
        from_state=LifecycleState.PROPOSED,
        to_state=LifecycleState.ACTIVE,
        expected=LifecycleState.INSTANTIATED,
    )
    assert isinstance(err, Exception)
    msg = str(err)
    assert "proposed" in msg
    assert "active" in msg
    assert "instantiated" in msg


def test_lifecycle_error_without_expected_successor() -> None:
    err = LifecycleError(
        from_state=LifecycleState.ARCHIVED,
        to_state=LifecycleState.ACTIVE,
    )
    assert "no legal successor" in str(err)


# ---------------------------------------------------------------------------
# RoleLifecycleState — distinct from LifecycleState (rs role.rs:50-61)
# ---------------------------------------------------------------------------


def test_role_lifecycle_state_chain_exhaustive() -> None:
    """4-state role lifecycle: draft, active, suspended, retired."""
    members = list(RoleLifecycleState)
    assert len(members) == 4
    assert {m.value for m in members} == {"draft", "active", "suspended", "retired"}


# ---------------------------------------------------------------------------
# DelegateIdentity — F2 restructure (opaque UUID + 3 eager-required refs)
# ---------------------------------------------------------------------------


def _make_identity(**overrides: object) -> DelegateIdentity:
    defaults: dict[str, object] = {
        "delegate_id": uuid.uuid4(),
        "sovereign_ref": "sov-1",
        "role_binding_ref": "rb-1",
        "genesis_ref": "g-1",
    }
    defaults.update(overrides)
    return DelegateIdentity(**defaults)  # type: ignore[arg-type]


def test_delegate_identity_frozen() -> None:
    ident = _make_identity()
    with pytest.raises(FrozenInstanceError):
        ident.sovereign_ref = "other"  # type: ignore[misc]


def test_delegate_identity_requires_uuid_delegate_id() -> None:
    with pytest.raises(TypeError, match="uuid.UUID"):
        DelegateIdentity(
            delegate_id="not-a-uuid",  # type: ignore[arg-type]
            sovereign_ref="s",
            role_binding_ref="rb",
            genesis_ref="g",
        )


def test_delegate_identity_post_init_rejects_empty_sovereign_ref() -> None:
    with pytest.raises(ValueError, match="sovereign_ref"):
        _make_identity(sovereign_ref="")


def test_delegate_identity_post_init_rejects_empty_role_binding_ref() -> None:
    with pytest.raises(ValueError, match="role_binding_ref"):
        _make_identity(role_binding_ref="")


def test_delegate_identity_post_init_rejects_empty_genesis_ref() -> None:
    with pytest.raises(ValueError, match="genesis_ref"):
        _make_identity(genesis_ref="")


def test_delegate_identity_no_legacy_fields() -> None:
    """Post-F2: tenant_id / principal_id / display_name are gone.

    Structural invariant test: if those fields ever return, this test
    fires and forces a re-audit against the rs canonical shape.
    """
    ident = _make_identity()
    assert not hasattr(ident, "tenant_id")
    assert not hasattr(ident, "principal_id")
    assert not hasattr(ident, "display_name")


# ---------------------------------------------------------------------------
# CapabilitySet — explicit intersect (no union — rs B1)
# ---------------------------------------------------------------------------


def test_capability_set_intersect_returns_set_intersection() -> None:
    a = CapabilitySet(capabilities=("read", "write", "admin"))
    b = CapabilitySet(capabilities=("read", "admin", "delete"))
    result = a.intersect(b)
    assert set(result.capabilities) == {"read", "admin"}


def test_capability_set_intersect_preserves_self_order() -> None:
    """Order from self is preserved (rs Vec.contains iteration semantics)."""
    a = CapabilitySet(capabilities=("c", "a", "b"))
    b = CapabilitySet(capabilities=("a", "b", "c"))
    result = a.intersect(b)
    assert result.capabilities == ("c", "a", "b")


def test_capability_set_intersect_empty_pair_is_empty() -> None:
    a = CapabilitySet(capabilities=("read",))
    b = CapabilitySet(capabilities=("write",))
    assert a.intersect(b).capabilities == ()


def test_capability_set_no_union_method() -> None:
    """Structural invariant: union is deliberately NOT provided (rs B1).

    Union would be a privilege-escalation primitive. If a sibling method
    ever lands here, this test fires and forces a re-audit.
    """
    assert not hasattr(CapabilitySet, "union")


def test_capability_set_coerces_iterable_to_tuple() -> None:
    cs = CapabilitySet(capabilities=["a", "b"])  # type: ignore[arg-type]
    assert isinstance(cs.capabilities, tuple)


def test_capability_set_intersect_rejects_non_capability_set() -> None:
    a = CapabilitySet(capabilities=("read",))
    with pytest.raises(TypeError, match="CapabilitySet"):
        a.intersect(["read"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RoleScope — both axes (rs B4)
# ---------------------------------------------------------------------------


def test_role_scope_holds_both_axes() -> None:
    cs = CapabilitySet(capabilities=("read",))
    scope = RoleScope(domain="d/t/r", capabilities=cs)
    assert scope.domain == "d/t/r"
    assert scope.capabilities is cs


def test_role_scope_rejects_empty_domain() -> None:
    with pytest.raises(ValueError, match="domain"):
        RoleScope(domain="", capabilities=CapabilitySet())


def test_role_scope_rejects_non_capability_set() -> None:
    with pytest.raises(TypeError, match="CapabilitySet"):
        RoleScope(domain="d", capabilities=["read"])  # type: ignore[arg-type]


def test_role_scope_default_capabilities_is_empty() -> None:
    scope = RoleScope(domain="d")
    assert scope.capabilities == CapabilitySet()


# ---------------------------------------------------------------------------
# Role — opaque UUID + structured scope + lifecycle (F3)
# ---------------------------------------------------------------------------


def _make_role(**overrides: object) -> Role:
    defaults: dict[str, object] = {
        "role_id": uuid.uuid4(),
        "display_name": "Reader",
        "scope": RoleScope(domain="d", capabilities=CapabilitySet(("read",))),
        "lifecycle": RoleLifecycleState.ACTIVE,
    }
    defaults.update(overrides)
    return Role(**defaults)  # type: ignore[arg-type]


def test_role_frozen() -> None:
    r = _make_role()
    with pytest.raises(FrozenInstanceError):
        r.display_name = "Other"  # type: ignore[misc]


def test_role_requires_uuid_role_id() -> None:
    with pytest.raises(TypeError, match="uuid.UUID"):
        _make_role(role_id="not-a-uuid")


def test_role_rejects_empty_display_name() -> None:
    with pytest.raises(ValueError, match="display_name"):
        _make_role(display_name="")


def test_role_rejects_non_role_scope() -> None:
    with pytest.raises(TypeError, match="RoleScope"):
        _make_role(scope={"domain": "d"})


def test_role_rejects_non_lifecycle_state() -> None:
    with pytest.raises(TypeError, match="RoleLifecycleState"):
        _make_role(lifecycle="active")


def test_role_no_legacy_scope_frozenset() -> None:
    """Post-F3: scope is RoleScope, NOT frozenset[str].

    Structural invariant test: if scope ever regresses to frozenset, this
    fires and forces a re-audit against the rs canonical shape.
    """
    r = _make_role()
    assert isinstance(r.scope, RoleScope)
    assert not isinstance(r.scope, frozenset)


# ---------------------------------------------------------------------------
# DelegateGenesisRecord — composes substrate chain.GenesisRecord (F4 + F6 + F7)
# ---------------------------------------------------------------------------


def test_delegate_genesis_record_frozen() -> None:
    g = _delegate_genesis()
    with pytest.raises(FrozenInstanceError):
        g.spec_version = "2"  # type: ignore[misc]


def test_delegate_genesis_record_composes_substrate_block() -> None:
    """Per §249 — block is composed by value (snapshot), not by reference.

    B4 (Round 2 sec M-2): the wrapper takes a ``dataclasses.replace``
    snapshot of the substrate block in ``__post_init__`` so that
    post-construction mutation of the original is invisible through
    the wrapper. The snapshot has identical canonical bytes (same
    cryptographic identity) but isolated Python identity.
    """
    block = _substrate_genesis()
    g = DelegateGenesisRecord(block=block, spec_version="1", capabilities=())
    # Snapshot identity: NOT the same Python object, but value-equal.
    assert g.block is not block
    assert g.block == block
    # The composed block remains the canonical source of cryptographic
    # fields. genesis_id is a convenience accessor.
    assert g.genesis_id == block.id


def test_delegate_genesis_record_snapshot_isolates_post_construction_mutation() -> None:
    """B4 (Round 2 sec M-2): mutating the ORIGINAL block does not affect
    the wrapper's composed block.

    Without the ``dataclasses.replace`` snapshot in ``__post_init__``, a
    caller could mutate ``block.signature`` AFTER construction; the
    ``_validate_hex`` check fires once at construction and never re-fires,
    leaving the wrapper holding a now-invalid hex signature with no
    structural signal. Snapshotting the block makes the wrapper's view
    immune to such mutation.
    """
    block = _substrate_genesis(signature="d" * 128)
    g = DelegateGenesisRecord(block=block, spec_version="1")
    # Mutate the ORIGINAL block's signature post-construction — would be
    # invisible-but-tampering without B4's snapshot.
    block.signature = "e" * 128
    # The wrapper retains the validated, canonical bytes.
    assert g.block.signature == "d" * 128
    assert block.signature == "e" * 128  # original is mutated, snapshot is not


def test_delegate_genesis_record_rejects_non_substrate_block() -> None:
    with pytest.raises(TypeError, match="kailash.trust.chain.GenesisRecord"):
        DelegateGenesisRecord(
            block={"id": "g"},  # type: ignore[arg-type]
            spec_version="1",
        )


def test_delegate_genesis_record_rejects_empty_spec_version() -> None:
    with pytest.raises(ValueError, match="spec_version"):
        _delegate_genesis(spec_version="")


def test_delegate_genesis_record_rejects_naive_datetime() -> None:
    naive_block = SubstrateGenesisRecord(
        id="g-1",
        agent_id="a",
        authority_id="u",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0),  # naive
        signature="d" * 128,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        DelegateGenesisRecord(block=naive_block, spec_version="1")


def test_delegate_genesis_record_capabilities_coerced_to_tuple() -> None:
    g = _delegate_genesis(capabilities=["read", "write"])
    assert g.capabilities == ("read", "write")


# F6 — hex length + format validation


def test_delegate_genesis_record_rejects_short_signature() -> None:
    """Ed25519 signature MUST be exactly 128 hex chars."""
    block = _substrate_genesis(signature="d" * 64)  # too short
    with pytest.raises(ValueError, match="128 hex chars"):
        DelegateGenesisRecord(block=block, spec_version="1")


def test_delegate_genesis_record_rejects_long_signature() -> None:
    block = _substrate_genesis(signature="d" * 256)  # too long
    with pytest.raises(ValueError, match="128 hex chars"):
        DelegateGenesisRecord(block=block, spec_version="1")


def test_delegate_genesis_record_rejects_uppercase_hex_signature() -> None:
    """Lowercase-only hex preserves cross-SDK byte parity."""
    block = _substrate_genesis(signature="D" * 128)
    with pytest.raises(ValueError, match="lowercase hex"):
        DelegateGenesisRecord(block=block, spec_version="1")


def test_delegate_genesis_record_rejects_non_hex_signature() -> None:
    block = _substrate_genesis(signature="g" * 128)  # 'g' not in [0-9a-f]
    with pytest.raises(ValueError, match="lowercase hex"):
        DelegateGenesisRecord(block=block, spec_version="1")


def test_delegate_genesis_record_skips_hex_validation_for_non_ed25519() -> None:
    """ECDSA / KMS signatures use different length conventions.

    The hex check fires only for ``Ed25519`` (the EATP-mandated default).
    Per ``eatp.md`` §Cryptography: 'AWS KMS uses ECDSA P-256 — document
    the algorithm mismatch.'
    """
    block = _substrate_genesis(
        signature="abcdef",  # short — but algorithm is ECDSA
        signature_algorithm="ECDSA-P256",
    )
    g = DelegateGenesisRecord(block=block, spec_version="1")
    assert g.block.signature == "abcdef"


# F7 — to_signing_dict / to_canonical_dict split


def test_to_signing_dict_excludes_signature() -> None:
    """The signing payload is the pre-signature canonical bytes.

    Signers compute the signature over THIS dict's canonical-JSON
    encoding; including the signature would create a circular dependency.
    """
    g = _delegate_genesis()
    signing = g.to_signing_dict()
    assert "block" in signing
    assert "signature" not in signing["block"]
    assert signing["spec_version"] == "1"


def test_to_canonical_dict_includes_signature() -> None:
    g = _delegate_genesis()
    canonical = g.to_canonical_dict()
    assert canonical["block"]["signature"] == "d" * 128
    assert canonical["block"]["signature_algorithm"] == "Ed25519"
    assert canonical["spec_version"] == "1"


def test_to_canonical_dict_byte_canonical_round_trip() -> None:
    """Two records with identical fields emit byte-identical canonical JSON."""
    g1 = _delegate_genesis()
    g2 = _delegate_genesis()
    json1 = canonical_json_dumps(g1.to_canonical_dict())
    json2 = canonical_json_dumps(g2.to_canonical_dict())
    assert json1 == json2
    # Nested block payload is grep-able in the canonical output.
    for field_name in ("block", "spec_version", "capabilities"):
        assert f'"{field_name}"' in json1


# ---------------------------------------------------------------------------
# PrincipalDirectory — F5 keyed on delegate_id UUID
# ---------------------------------------------------------------------------


def test_principal_directory_resolve_hit_miss() -> None:
    alice_id = uuid.uuid4()
    bob_id = uuid.uuid4()
    eve_id = uuid.uuid4()
    alice = _make_identity(delegate_id=alice_id)
    bob = _make_identity(delegate_id=bob_id)
    directory = PrincipalDirectory(identities=(alice, bob))
    assert directory.resolve(alice_id) is alice
    assert directory.resolve(bob_id) is bob
    assert directory.resolve(eve_id) is None


def test_principal_directory_resolve_requires_uuid() -> None:
    directory = PrincipalDirectory()
    with pytest.raises(TypeError, match="uuid.UUID"):
        directory.resolve("not-a-uuid")  # type: ignore[arg-type]


def test_principal_directory_rejects_duplicate_delegate_id() -> None:
    shared_id = uuid.uuid4()
    one = _make_identity(delegate_id=shared_id, sovereign_ref="sov-1")
    two = _make_identity(delegate_id=shared_id, sovereign_ref="sov-2")
    with pytest.raises(ValueError, match="duplicate identity"):
        PrincipalDirectory(identities=(one, two))


def test_principal_directory_frozen() -> None:
    directory = PrincipalDirectory()
    with pytest.raises(FrozenInstanceError):
        directory.identities = ()  # type: ignore[misc]


def test_principal_directory_coerces_iterable_to_tuple() -> None:
    directory = PrincipalDirectory(identities=[_make_identity()])  # type: ignore[arg-type]
    assert isinstance(directory.identities, tuple)
