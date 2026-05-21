# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 tests for the S3 trust cascade (TenantScope + TenantScopedCascade +
GrantMoment) per kailash-rs M3-01 + M3-02.

Mirrors invariants surfaced in the kailash-rs reference extraction report at
``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-
extraction.md`` § trust-cascade. The cascade is fail-closed at every step;
each test exercises one step's typed-error gate or the success-path
GrantMoment emission.
"""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
from kailash.delegate.trust import (
    CascadeScopeExpansionError,
    CascadeTenantViolationError,
    GrantMoment,
    TenantScope,
    TenantScopedCascade,
)
from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    RoleScope,
)
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType
from kailash.trust.chain import GenesisRecord as SubstrateGenesisRecord
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint

# ---------------------------------------------------------------------------
# Fixtures — minimal substrate + Delegate-layer constructs
# ---------------------------------------------------------------------------


def _identity(*, suffix: str = "1") -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref=f"sov-{suffix}",
        role_binding_ref=f"role-{suffix}",
        genesis_ref=f"genesis-{suffix}",
    )


def _envelope_with_budget(
    budget: float, *, genesis_id: str = "g-1"
) -> DelegateConstraintEnvelope:
    block = SubstrateGenesisRecord(
        id=genesis_id,
        agent_id="agent-1",
        authority_id="auth-1",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    return DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=budget)),
        genesis,
    )


def _scope(
    domain: str = "finance", caps: tuple[str, ...] = ("read", "approve")
) -> RoleScope:
    return RoleScope(domain=domain, capabilities=CapabilitySet(capabilities=caps))


# ---------------------------------------------------------------------------
# TenantScope — typed 2-variant union, M-1 misconfiguration guard
# ---------------------------------------------------------------------------


def test_tenant_scope_global_is_explicit_variant() -> None:
    """Global is a named variant distinct from any tenant (rs M-1 guard)."""
    g = TenantScope.global_()
    assert g.is_global
    assert g.tenant_id is None


def test_tenant_scope_for_tenant_carries_id() -> None:
    t = TenantScope.for_tenant("tenant-a")
    assert not t.is_global
    assert t.tenant_id == "tenant-a"


def test_tenant_scope_global_not_equal_to_tenant_named_global() -> None:
    """Global != Tenant('global') — the typed enum is structural, not stringly."""
    assert TenantScope.global_() != TenantScope.for_tenant("global")


def test_tenant_scope_for_tenant_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="str tenant_id"):
        TenantScope.for_tenant(42)  # type: ignore[arg-type]


def test_tenant_scope_for_tenant_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        TenantScope.for_tenant("")


def test_tenant_scope_direct_construction_with_invalid_invariant_raises() -> None:
    """Direct __init__ with mismatched discriminant fields raises (defense)."""
    with pytest.raises(ValueError, match="Global variant MUST NOT carry"):
        TenantScope(_is_global=True, _tenant_id="bad")
    with pytest.raises(ValueError, match="Tenant variant MUST carry"):
        TenantScope(_is_global=False, _tenant_id=None)


def test_tenant_scope_is_frozen() -> None:
    g = TenantScope.global_()
    with pytest.raises(FrozenInstanceError):
        g._is_global = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GrantMoment — frozen, tz-aware, hex-validated
# ---------------------------------------------------------------------------


def _grant_moment(**overrides: object) -> GrantMoment:
    defaults: dict[str, object] = {
        "cascade_id": uuid.uuid4(),
        "parent_delegate_id": uuid.uuid4(),
        "child_delegate_id": uuid.uuid4(),
        "tenant": TenantScope.for_tenant("tenant-a"),
        "granted_at": datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        "grant_proof": "a" * 128,
    }
    defaults.update(overrides)
    return GrantMoment(**defaults)  # type: ignore[arg-type]


def test_grant_moment_constructs() -> None:
    gm = _grant_moment()
    assert isinstance(gm.cascade_id, uuid.UUID)
    assert isinstance(gm.parent_delegate_id, uuid.UUID)
    assert isinstance(gm.child_delegate_id, uuid.UUID)
    assert gm.tenant.tenant_id == "tenant-a"
    assert gm.granted_at.tzinfo is not None


def test_grant_moment_is_frozen() -> None:
    gm = _grant_moment()
    with pytest.raises(FrozenInstanceError):
        gm.grant_proof = "b" * 128  # type: ignore[misc]


def test_grant_moment_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _grant_moment(granted_at=datetime(2026, 5, 21, 12, 0, 0))


def test_grant_moment_rejects_non_uuid_ids() -> None:
    with pytest.raises(TypeError, match="cascade_id MUST be a uuid.UUID"):
        _grant_moment(cascade_id="not-a-uuid")
    with pytest.raises(TypeError, match="parent_delegate_id MUST be a uuid.UUID"):
        _grant_moment(parent_delegate_id="not-a-uuid")


def test_grant_moment_rejects_non_tenant_scope() -> None:
    with pytest.raises(TypeError, match="tenant MUST be a TenantScope"):
        _grant_moment(tenant="tenant-a")


def test_grant_moment_rejects_short_or_non_hex_signature() -> None:
    with pytest.raises(ValueError, match="128 hex chars"):
        _grant_moment(grant_proof="a" * 64)
    with pytest.raises(ValueError, match="lowercase hex"):
        _grant_moment(grant_proof="A" * 128)


def test_grant_moment_to_signing_dict_excludes_grant_proof() -> None:
    """F7 sign/verify split: to_signing_dict excludes the signature."""
    gm = _grant_moment()
    signing = gm.to_signing_dict()
    assert "grant_proof" not in signing
    assert "cascade_id" in signing
    assert "parent_delegate_id" in signing
    assert "child_delegate_id" in signing
    assert "tenant" in signing
    assert "granted_at" in signing


def test_grant_moment_to_canonical_dict_includes_grant_proof() -> None:
    """to_canonical_dict is the full transport shape (includes signature)."""
    gm = _grant_moment()
    canonical = gm.to_canonical_dict()
    assert canonical["grant_proof"] == "a" * 128
    # Everything in signing payload is also in canonical
    for key in gm.to_signing_dict():
        assert key in canonical


def test_grant_moment_canonical_dict_byte_stable_across_constructions() -> None:
    """Same inputs → byte-identical canonical-JSON output (cross-SDK contract)."""
    cid = uuid.uuid4()
    pid = uuid.uuid4()
    chid = uuid.uuid4()
    t = TenantScope.for_tenant("tenant-a")
    when = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    proof = "a" * 128

    gm1 = GrantMoment(
        cascade_id=cid,
        parent_delegate_id=pid,
        child_delegate_id=chid,
        tenant=t,
        granted_at=when,
        grant_proof=proof,
    )
    gm2 = GrantMoment(
        cascade_id=cid,
        parent_delegate_id=pid,
        child_delegate_id=chid,
        tenant=t,
        granted_at=when,
        grant_proof=proof,
    )
    assert canonical_json_dumps(gm1.to_canonical_dict()) == canonical_json_dumps(
        gm2.to_canonical_dict()
    )


def test_grant_moment_tenant_serializes_as_tagged_union() -> None:
    """Tenant variant: {"type": "Tenant", "tenant_id": "..."}."""
    gm = _grant_moment(tenant=TenantScope.for_tenant("tenant-a"))
    canonical = gm.to_canonical_dict()
    assert canonical["tenant"] == {"type": "Tenant", "tenant_id": "tenant-a"}


def test_grant_moment_global_tenant_serializes_as_tagged_union() -> None:
    gm = _grant_moment(tenant=TenantScope.global_())
    canonical = gm.to_canonical_dict()
    assert canonical["tenant"] == {"type": "Global"}


# ---------------------------------------------------------------------------
# TenantScopedCascade — construction + type discipline
# ---------------------------------------------------------------------------


def test_cascade_constructs_with_tenant() -> None:
    c = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    assert c.tenant.tenant_id == "tenant-a"


def test_cascade_rejects_non_tenant_scope() -> None:
    with pytest.raises(TypeError, match="tenant MUST be a TenantScope"):
        TenantScopedCascade(tenant="tenant-a")  # type: ignore[arg-type]


def test_cascade_is_frozen() -> None:
    c = TenantScopedCascade(tenant=TenantScope.global_())
    with pytest.raises(FrozenInstanceError):
        c.tenant = TenantScope.for_tenant("other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# cascade_child — Step 1 fail-closed: tenant boundary (Option A RATIFIED)
# ---------------------------------------------------------------------------


def test_cascade_cross_tenant_child_raises_tenant_violation() -> None:
    """Step 1: Tenant-A cascade cannot admit Tenant-B child, even with valid
    scope + envelope tightening."""
    casc = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)
    scope = _scope()

    with pytest.raises(CascadeTenantViolationError) as exc_info:
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=scope,
            child_scope=scope,
            child_tenant=TenantScope.for_tenant("tenant-b"),
            grant_proof="a" * 128,
        )
    assert exc_info.value.parent_tenant == "tenant-a"
    assert exc_info.value.child_tenant == "tenant-b"


def test_cascade_global_to_tenant_raises_tenant_violation() -> None:
    """Global cascade rejects a tenant-scoped child (no implicit upcast)."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)
    scope = _scope()
    with pytest.raises(CascadeTenantViolationError):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=scope,
            child_scope=scope,
            child_tenant=TenantScope.for_tenant("tenant-a"),
            grant_proof="a" * 128,
        )


# ---------------------------------------------------------------------------
# cascade_child — Step 2 fail-closed: scope subset (F1 downward-only)
# ---------------------------------------------------------------------------


def test_cascade_cross_domain_child_raises_scope_expansion() -> None:
    """F1: child domain MUST equal parent's domain — no cross-domain edge."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)

    with pytest.raises(CascadeScopeExpansionError) as exc_info:
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=_scope(domain="finance"),
            child_scope=_scope(domain="hr"),
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )
    assert exc_info.value.parent_domain == "finance"
    assert exc_info.value.child_domain == "hr"


def test_cascade_capability_widening_raises_scope_expansion() -> None:
    """F1: child capabilities MUST be a subset of parent's."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)

    with pytest.raises(CascadeScopeExpansionError) as exc_info:
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=_scope(caps=("read",)),
            # Child adds 'approve' — widening
            child_scope=_scope(caps=("read", "approve")),
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )
    assert "approve" in exc_info.value.added_capabilities


def test_cascade_subset_capability_child_succeeds_step_2() -> None:
    """Child with strictly-subset capabilities passes Step 2 (success-path
    requires Steps 3+4 to also pass — see test_cascade_emits_grant_moment)."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)

    gm = casc.cascade_child(
        parent_env,
        child_env,
        parent_identity=_identity(suffix="parent"),
        child_identity=_identity(suffix="child"),
        parent_scope=_scope(caps=("read", "approve")),
        child_scope=_scope(caps=("read",)),  # strict subset
        child_tenant=TenantScope.global_(),
        grant_proof="a" * 128,
    )
    assert isinstance(gm, GrantMoment)


# ---------------------------------------------------------------------------
# cascade_child — Step 3 fail-closed: envelope tightening (F5)
# ---------------------------------------------------------------------------


def test_cascade_widening_envelope_propagates_envelope_widening_error() -> None:
    """Step 3: child envelope that widens parent raises EnvelopeWideningError
    (delegated to DelegateConstraintEnvelope.tighten_with's pre-intersection
    widening check — F5)."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(50.0)
    child_env = _envelope_with_budget(100.0)  # widens
    scope = _scope()

    with pytest.raises(EnvelopeWideningError, match="widen"):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=scope,
            child_scope=scope,
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )


# ---------------------------------------------------------------------------
# cascade_child — Step 4 success-path: emit GrantMoment
# ---------------------------------------------------------------------------


def test_cascade_emits_well_formed_grant_moment_on_success() -> None:
    """All three checks pass → GrantMoment with parent+child identities
    + tenant + tz-aware granted_at + signature."""
    casc = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)
    scope = _scope()
    parent = _identity(suffix="parent")
    child = _identity(suffix="child")
    when = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)

    gm = casc.cascade_child(
        parent_env,
        child_env,
        parent_identity=parent,
        child_identity=child,
        parent_scope=scope,
        child_scope=scope,
        child_tenant=TenantScope.for_tenant("tenant-a"),
        grant_proof="b" * 128,
        granted_at=when,
    )
    assert isinstance(gm, GrantMoment)
    assert gm.parent_delegate_id == parent.delegate_id
    assert gm.child_delegate_id == child.delegate_id
    assert gm.tenant == TenantScope.for_tenant("tenant-a")
    assert gm.granted_at == when
    assert gm.grant_proof == "b" * 128


def test_cascade_default_granted_at_is_tz_aware_utc_now() -> None:
    """When granted_at is omitted, the cascade defaults to tz-aware utc now."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)
    scope = _scope()

    gm = casc.cascade_child(
        parent_env,
        child_env,
        parent_identity=_identity(suffix="parent"),
        child_identity=_identity(suffix="child"),
        parent_scope=scope,
        child_scope=scope,
        child_tenant=TenantScope.global_(),
        grant_proof="a" * 128,
    )
    assert gm.granted_at.tzinfo is not None


def test_cascade_step_order_tenant_check_runs_before_scope_check() -> None:
    """Step ordering: tenant violation fires BEFORE scope-expansion check,
    so a cross-tenant cascade with cross-domain scope raises
    CascadeTenantViolationError, not CascadeScopeExpansionError."""
    casc = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    parent_env = _envelope_with_budget(100.0)
    child_env = _envelope_with_budget(50.0)

    with pytest.raises(CascadeTenantViolationError):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=_scope(domain="finance"),
            child_scope=_scope(domain="hr"),  # would raise scope error
            child_tenant=TenantScope.for_tenant("tenant-b"),  # tenant fires first
            grant_proof="a" * 128,
        )


def test_cascade_step_order_scope_check_runs_before_envelope_check() -> None:
    """Step ordering: scope expansion fires BEFORE envelope widening check."""
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(50.0)
    child_env = _envelope_with_budget(100.0)  # would widen

    with pytest.raises(CascadeScopeExpansionError):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity(suffix="parent"),
            child_identity=_identity(suffix="child"),
            parent_scope=_scope(caps=("read",)),
            child_scope=_scope(caps=("read", "approve")),  # widens scope
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )


# ---------------------------------------------------------------------------
# Type discipline at the cascade boundary (defense-in-depth)
# ---------------------------------------------------------------------------


def test_cascade_rejects_non_envelope_types() -> None:
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope_with_budget(100.0)
    scope = _scope()
    with pytest.raises(TypeError, match="parent_envelope MUST"):
        casc.cascade_child(
            "not-an-envelope",  # type: ignore[arg-type]
            parent_env,
            parent_identity=_identity(suffix="p"),
            child_identity=_identity(suffix="c"),
            parent_scope=scope,
            child_scope=scope,
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )


def test_cascade_rejects_non_identity_types() -> None:
    casc = TenantScopedCascade(tenant=TenantScope.global_())
    env = _envelope_with_budget(100.0)
    scope = _scope()
    with pytest.raises(TypeError, match="parent_identity MUST"):
        casc.cascade_child(
            env,
            env,
            parent_identity="not-an-identity",  # type: ignore[arg-type]
            child_identity=_identity(suffix="c"),
            parent_scope=scope,
            child_scope=scope,
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )


# ---------------------------------------------------------------------------
# from_dict — H2 deferral closure tests for identity + envelope
# ---------------------------------------------------------------------------


def test_delegate_identity_to_dict_from_dict_round_trip() -> None:
    """to_dict → from_dict reconstructs identity equality."""
    ident = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-1",
        role_binding_ref="role-1",
        genesis_ref="genesis-1",
    )
    reconstructed = DelegateIdentity.from_dict(ident.to_dict())
    assert reconstructed == ident


def test_delegate_identity_from_dict_rejects_missing_field() -> None:
    with pytest.raises(ValueError, match="missing required field"):
        DelegateIdentity.from_dict(
            {"delegate_id": str(uuid.uuid4()), "sovereign_ref": "sov-1"}
        )


def test_delegate_identity_from_dict_rejects_bad_uuid_string() -> None:
    with pytest.raises(ValueError, match="not a valid UUID"):
        DelegateIdentity.from_dict(
            {
                "delegate_id": "not-a-uuid",
                "sovereign_ref": "sov-1",
                "role_binding_ref": "role-1",
                "genesis_ref": "genesis-1",
            }
        )


def test_delegate_identity_from_dict_rejects_non_string_refs() -> None:
    with pytest.raises(TypeError, match="MUST be a str"):
        DelegateIdentity.from_dict(
            {
                "delegate_id": str(uuid.uuid4()),
                "sovereign_ref": 123,  # type: ignore[dict-item]
                "role_binding_ref": "role-1",
                "genesis_ref": "genesis-1",
            }
        )


def test_delegate_identity_from_dict_runs_post_init_validation() -> None:
    """Path-traversal in a ref string is rejected via __post_init__ chain."""
    with pytest.raises(ValueError, match="rejected"):
        DelegateIdentity.from_dict(
            {
                "delegate_id": str(uuid.uuid4()),
                "sovereign_ref": "../escape",  # validate_id rejects
                "role_binding_ref": "role-1",
                "genesis_ref": "genesis-1",
            }
        )


def test_delegate_constraint_envelope_to_dict_from_dict_round_trip() -> None:
    """to_dict → from_dict reconstructs envelope wrapper."""
    env = _envelope_with_budget(75.0, genesis_id="g-roundtrip")
    payload = env.to_dict()
    reconstructed = DelegateConstraintEnvelope.from_dict(payload)
    assert reconstructed.genesis_id == env.genesis_id
    assert reconstructed.inner.financial is not None
    assert reconstructed.inner.financial.budget_limit == 75.0


def test_delegate_constraint_envelope_from_dict_rejects_missing_field() -> None:
    with pytest.raises(ValueError, match="missing required field"):
        DelegateConstraintEnvelope.from_dict({"inner": {}})


def test_delegate_constraint_envelope_from_dict_rejects_empty_genesis_id() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        DelegateConstraintEnvelope.from_dict({"inner": {}, "genesis_id": ""})


def test_delegate_constraint_envelope_from_dict_rejects_non_dict_inner() -> None:
    with pytest.raises(TypeError, match="inner MUST be a"):
        DelegateConstraintEnvelope.from_dict(
            {"inner": "not-a-dict", "genesis_id": "g-1"}
        )


def test_delegate_identity_from_dict_accepts_uuid_object_directly() -> None:
    """In-process callers may pass a uuid.UUID object directly; from_dict
    accepts both string and UUID for the delegate_id slot."""
    uid = uuid.uuid4()
    reconstructed = DelegateIdentity.from_dict(
        {
            "delegate_id": uid,
            "sovereign_ref": "sov-1",
            "role_binding_ref": "role-1",
            "genesis_ref": "genesis-1",
        }
    )
    assert reconstructed.delegate_id == uid
