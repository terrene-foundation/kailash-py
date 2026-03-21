# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for governance store protocols and in-memory implementations.

Covers:
- TODO-4001: Store protocols (OrgStore, EnvelopeStore, ClearanceStore, AccessPolicyStore)
- TODO-4002: In-memory implementations (Memory*Store classes)
- Bounded collection enforcement (MAX_STORE_SIZE eviction)
- Bidirectional KSP lookup
- Bidirectional bridge lookup
- Ancestor envelope resolution
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.envelopes import RoleEnvelope, TaskEnvelope
from pact.governance.store import (
    MAX_STORE_SIZE,
    AccessPolicyStore,
    ClearanceStore,
    EnvelopeStore,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
    OrgStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "test-org") -> CompiledOrg:
    """Create a minimal CompiledOrg with a few nodes for testing."""
    org = CompiledOrg(org_id=org_id)
    from pact.governance.addressing import NodeType

    org.nodes["D1"] = OrgNode(
        address="D1",
        node_type=NodeType.DEPARTMENT,
        name="Engineering",
        node_id="eng",
    )
    org.nodes["D1-R1"] = OrgNode(
        address="D1-R1",
        node_type=NodeType.ROLE,
        name="VP Eng",
        node_id="vp-eng",
        parent_address="D1",
    )
    org.nodes["D1-R1-T1"] = OrgNode(
        address="D1-R1-T1",
        node_type=NodeType.TEAM,
        name="Backend",
        node_id="backend",
        parent_address="D1-R1",
    )
    org.nodes["D1-R1-T1-R1"] = OrgNode(
        address="D1-R1-T1-R1",
        node_type=NodeType.ROLE,
        name="Backend Lead",
        node_id="backend-lead",
        parent_address="D1-R1-T1",
    )
    return org


def _make_envelope(env_id: str = "env-1") -> ConstraintEnvelopeConfig:
    """Create a minimal ConstraintEnvelopeConfig for testing."""
    return ConstraintEnvelopeConfig(
        id=env_id,
        description=f"Test envelope {env_id}",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(allowed_actions=["read", "write"]),
    )


def _make_role_envelope(
    env_id: str = "re-1",
    defining: str = "D1-R1",
    target: str = "D1-R1-T1-R1",
) -> RoleEnvelope:
    """Create a RoleEnvelope for testing."""
    return RoleEnvelope(
        id=env_id,
        defining_role_address=defining,
        target_role_address=target,
        envelope=_make_envelope(env_id),
    )


def _make_task_envelope(
    env_id: str = "te-1",
    task_id: str = "task-001",
    parent_env_id: str = "re-1",
    role_address: str = "D1-R1-T1-R1",
) -> TaskEnvelope:
    """Create a TaskEnvelope for testing."""
    return TaskEnvelope(
        id=env_id,
        task_id=task_id,
        parent_envelope_id=parent_env_id,
        envelope=_make_envelope(env_id),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _make_clearance(
    role_address: str = "D1-R1-T1-R1",
    max_clearance: ConfidentialityLevel = ConfidentialityLevel.CONFIDENTIAL,
) -> RoleClearance:
    """Create a RoleClearance for testing."""
    return RoleClearance(
        role_address=role_address,
        max_clearance=max_clearance,
        granted_by_role_address="D1-R1",
        vetting_status=VettingStatus.ACTIVE,
    )


def _make_ksp(
    ksp_id: str = "ksp-1",
    source: str = "D1",
    target: str = "D2",
    bilateral: bool = False,
) -> KnowledgeSharePolicy:
    """Create a KnowledgeSharePolicy for testing."""
    return KnowledgeSharePolicy(
        id=ksp_id,
        source_unit_address=source,
        target_unit_address=target,
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
    )


def _make_bridge(
    bridge_id: str = "bridge-1",
    role_a: str = "D1-R1",
    role_b: str = "D2-R1",
    bilateral: bool = True,
) -> PactBridge:
    """Create a PactBridge for testing."""
    return PactBridge(
        id=bridge_id,
        role_a_address=role_a,
        role_b_address=role_b,
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        bilateral=bilateral,
    )


# ===========================================================================
# Protocol conformance
# ===========================================================================


class TestProtocolConformance:
    """Verify in-memory stores satisfy their Protocol contracts."""

    def test_memory_org_store_is_org_store(self) -> None:
        store = MemoryOrgStore()
        assert isinstance(store, OrgStore)

    def test_memory_envelope_store_is_envelope_store(self) -> None:
        store = MemoryEnvelopeStore()
        assert isinstance(store, EnvelopeStore)

    def test_memory_clearance_store_is_clearance_store(self) -> None:
        store = MemoryClearanceStore()
        assert isinstance(store, ClearanceStore)

    def test_memory_access_policy_store_is_access_policy_store(self) -> None:
        store = MemoryAccessPolicyStore()
        assert isinstance(store, AccessPolicyStore)


# ===========================================================================
# MemoryOrgStore
# ===========================================================================


class TestMemoryOrgStore:
    """MemoryOrgStore CRUD and query operations."""

    def test_save_and_load_org(self) -> None:
        store = MemoryOrgStore()
        org = _make_compiled_org("org-1")
        store.save_org(org)
        loaded = store.load_org("org-1")
        assert loaded is not None
        assert loaded.org_id == "org-1"
        assert "D1" in loaded.nodes

    def test_load_nonexistent_org_returns_none(self) -> None:
        store = MemoryOrgStore()
        assert store.load_org("nonexistent") is None

    def test_get_node(self) -> None:
        store = MemoryOrgStore()
        org = _make_compiled_org("org-1")
        store.save_org(org)
        node = store.get_node("org-1", "D1-R1")
        assert node is not None
        assert node.name == "VP Eng"

    def test_get_node_nonexistent_org_returns_none(self) -> None:
        store = MemoryOrgStore()
        assert store.get_node("nonexistent", "D1") is None

    def test_get_node_nonexistent_address_returns_none(self) -> None:
        store = MemoryOrgStore()
        org = _make_compiled_org("org-1")
        store.save_org(org)
        assert store.get_node("org-1", "D99") is None

    def test_query_by_prefix(self) -> None:
        store = MemoryOrgStore()
        org = _make_compiled_org("org-1")
        store.save_org(org)
        results = store.query_by_prefix("org-1", "D1-R1")
        addresses = {n.address for n in results}
        # D1-R1, D1-R1-T1, D1-R1-T1-R1 all start with D1-R1
        assert "D1-R1" in addresses
        assert "D1-R1-T1" in addresses
        assert "D1-R1-T1-R1" in addresses
        # D1 does NOT start with D1-R1
        assert "D1" not in addresses

    def test_query_by_prefix_nonexistent_org_returns_empty(self) -> None:
        store = MemoryOrgStore()
        assert store.query_by_prefix("nonexistent", "D1") == []

    def test_save_overwrites_existing_org(self) -> None:
        store = MemoryOrgStore()
        org1 = _make_compiled_org("org-1")
        store.save_org(org1)
        org2 = CompiledOrg(org_id="org-1")  # empty org
        store.save_org(org2)
        loaded = store.load_org("org-1")
        assert loaded is not None
        assert len(loaded.nodes) == 0

    def test_bounded_eviction(self) -> None:
        store = MemoryOrgStore()
        # Fill beyond MAX_STORE_SIZE
        for i in range(MAX_STORE_SIZE + 5):
            org = CompiledOrg(org_id=f"org-{i}")
            store.save_org(org)
        # Store should not exceed MAX_STORE_SIZE
        # The earliest orgs should have been evicted
        assert store.load_org("org-0") is None
        # Latest orgs should still be present
        assert store.load_org(f"org-{MAX_STORE_SIZE + 4}") is not None


# ===========================================================================
# MemoryEnvelopeStore
# ===========================================================================


class TestMemoryEnvelopeStore:
    """MemoryEnvelopeStore CRUD and ancestor lookup."""

    def test_save_and_get_role_envelope(self) -> None:
        store = MemoryEnvelopeStore()
        re = _make_role_envelope("re-1", target="D1-R1-T1-R1")
        store.save_role_envelope(re)
        loaded = store.get_role_envelope("D1-R1-T1-R1")
        assert loaded is not None
        assert loaded.id == "re-1"

    def test_get_role_envelope_nonexistent_returns_none(self) -> None:
        store = MemoryEnvelopeStore()
        assert store.get_role_envelope("D99-R1") is None

    def test_save_and_get_task_envelope(self) -> None:
        store = MemoryEnvelopeStore()
        te = _make_task_envelope("te-1", task_id="task-001", role_address="D1-R1-T1-R1")
        store.save_task_envelope(te)
        loaded = store.get_active_task_envelope("D1-R1-T1-R1", "task-001")
        assert loaded is not None
        assert loaded.id == "te-1"

    def test_get_task_envelope_nonexistent_returns_none(self) -> None:
        store = MemoryEnvelopeStore()
        assert store.get_active_task_envelope("D1-R1", "task-999") is None

    def test_get_task_envelope_expired_returns_none(self) -> None:
        """Expired task envelopes should not be returned."""
        store = MemoryEnvelopeStore()
        te = TaskEnvelope(
            id="te-expired",
            task_id="task-old",
            parent_envelope_id="re-1",
            envelope=_make_envelope("te-expired"),
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # already expired
        )
        store.save_task_envelope(te)
        assert store.get_active_task_envelope("D1-R1-T1-R1", "task-old") is None

    def test_get_ancestor_envelopes(self) -> None:
        """Should return all RoleEnvelopes for addresses that are ancestors of the given address."""
        store = MemoryEnvelopeStore()
        # Create envelopes for different hierarchy levels
        re_root = _make_role_envelope("re-root", target="D1-R1")
        re_child = _make_role_envelope("re-child", target="D1-R1-T1-R1")
        re_unrelated = _make_role_envelope("re-unrelated", target="D2-R1")
        store.save_role_envelope(re_root)
        store.save_role_envelope(re_child)
        store.save_role_envelope(re_unrelated)

        ancestors = store.get_ancestor_envelopes("D1-R1-T1-R1")
        # D1-R1 is an ancestor of D1-R1-T1-R1, and D1-R1-T1-R1 is the address itself
        assert "D1-R1" in ancestors
        assert "D1-R1-T1-R1" in ancestors
        # D2-R1 is not an ancestor
        assert "D2-R1" not in ancestors

    def test_get_ancestor_envelopes_empty(self) -> None:
        store = MemoryEnvelopeStore()
        ancestors = store.get_ancestor_envelopes("D1-R1-T1-R1")
        assert ancestors == {}

    def test_save_role_envelope_overwrites(self) -> None:
        store = MemoryEnvelopeStore()
        re1 = _make_role_envelope("re-1", target="D1-R1")
        store.save_role_envelope(re1)
        re2 = _make_role_envelope("re-2", target="D1-R1")
        store.save_role_envelope(re2)
        loaded = store.get_role_envelope("D1-R1")
        assert loaded is not None
        assert loaded.id == "re-2"

    def test_bounded_role_envelope_eviction(self) -> None:
        store = MemoryEnvelopeStore()
        for i in range(MAX_STORE_SIZE + 5):
            re = _make_role_envelope(f"re-{i}", target=f"D{i}-R1")
            store.save_role_envelope(re)
        # Earliest entries should be evicted
        assert store.get_role_envelope("D0-R1") is None
        # Latest should remain
        assert store.get_role_envelope(f"D{MAX_STORE_SIZE + 4}-R1") is not None


# ===========================================================================
# MemoryClearanceStore
# ===========================================================================


class TestMemoryClearanceStore:
    """MemoryClearanceStore grant, get, revoke operations."""

    def test_grant_and_get_clearance(self) -> None:
        store = MemoryClearanceStore()
        clr = _make_clearance("D1-R1-T1-R1")
        store.grant_clearance(clr)
        loaded = store.get_clearance("D1-R1-T1-R1")
        assert loaded is not None
        assert loaded.max_clearance == ConfidentialityLevel.CONFIDENTIAL

    def test_get_clearance_nonexistent_returns_none(self) -> None:
        store = MemoryClearanceStore()
        assert store.get_clearance("D99-R1") is None

    def test_revoke_clearance(self) -> None:
        store = MemoryClearanceStore()
        clr = _make_clearance("D1-R1-T1-R1")
        store.grant_clearance(clr)
        store.revoke_clearance("D1-R1-T1-R1")
        assert store.get_clearance("D1-R1-T1-R1") is None

    def test_revoke_nonexistent_clearance_no_error(self) -> None:
        """Revoking a clearance that does not exist should not raise."""
        store = MemoryClearanceStore()
        store.revoke_clearance("D1-R1-T1-R1")  # should not raise

    def test_grant_overwrites_existing(self) -> None:
        store = MemoryClearanceStore()
        clr1 = _make_clearance("D1-R1", ConfidentialityLevel.RESTRICTED)
        store.grant_clearance(clr1)
        clr2 = _make_clearance("D1-R1", ConfidentialityLevel.SECRET)
        store.grant_clearance(clr2)
        loaded = store.get_clearance("D1-R1")
        assert loaded is not None
        assert loaded.max_clearance == ConfidentialityLevel.SECRET

    def test_bounded_clearance_eviction(self) -> None:
        store = MemoryClearanceStore()
        for i in range(MAX_STORE_SIZE + 5):
            clr = _make_clearance(f"D{i}-R1")
            store.grant_clearance(clr)
        # Earliest entries should be evicted
        assert store.get_clearance("D0-R1") is None
        # Latest should remain
        assert store.get_clearance(f"D{MAX_STORE_SIZE + 4}-R1") is not None


# ===========================================================================
# MemoryAccessPolicyStore
# ===========================================================================


class TestMemoryAccessPolicyStoreKSP:
    """MemoryAccessPolicyStore KSP operations."""

    def test_save_and_find_ksp(self) -> None:
        store = MemoryAccessPolicyStore()
        ksp = _make_ksp("ksp-1", source="D1", target="D2")
        store.save_ksp(ksp)
        found = store.find_ksp("D1", "D2")
        assert found is not None
        assert found.id == "ksp-1"

    def test_find_ksp_nonexistent_returns_none(self) -> None:
        store = MemoryAccessPolicyStore()
        assert store.find_ksp("D1", "D2") is None

    def test_find_ksp_reverse_direction_not_found(self) -> None:
        """Unidirectional KSP: searching in reverse direction should not find it."""
        store = MemoryAccessPolicyStore()
        ksp = _make_ksp("ksp-1", source="D1", target="D2")
        store.save_ksp(ksp)
        # Reverse direction lookup -- D2 -> D1 should NOT match
        # because KSP is directional (source shares WITH target)
        found = store.find_ksp("D2", "D1")
        assert found is None

    def test_list_ksps(self) -> None:
        store = MemoryAccessPolicyStore()
        ksp1 = _make_ksp("ksp-1", source="D1", target="D2")
        ksp2 = _make_ksp("ksp-2", source="D3", target="D4")
        store.save_ksp(ksp1)
        store.save_ksp(ksp2)
        ksps = store.list_ksps()
        assert len(ksps) == 2
        ids = {k.id for k in ksps}
        assert "ksp-1" in ids
        assert "ksp-2" in ids

    def test_list_ksps_empty(self) -> None:
        store = MemoryAccessPolicyStore()
        assert store.list_ksps() == []


class TestMemoryAccessPolicyStoreBridge:
    """MemoryAccessPolicyStore bridge operations."""

    def test_save_and_find_bridge(self) -> None:
        store = MemoryAccessPolicyStore()
        bridge = _make_bridge("bridge-1", role_a="D1-R1", role_b="D2-R1")
        store.save_bridge(bridge)
        found = store.find_bridge("D1-R1", "D2-R1")
        assert found is not None
        assert found.id == "bridge-1"

    def test_find_bridge_reverse_order(self) -> None:
        """Bridges should be findable regardless of address order."""
        store = MemoryAccessPolicyStore()
        bridge = _make_bridge("bridge-1", role_a="D1-R1", role_b="D2-R1")
        store.save_bridge(bridge)
        found = store.find_bridge("D2-R1", "D1-R1")
        assert found is not None
        assert found.id == "bridge-1"

    def test_find_bridge_nonexistent_returns_none(self) -> None:
        store = MemoryAccessPolicyStore()
        assert store.find_bridge("D1-R1", "D99-R1") is None

    def test_list_bridges(self) -> None:
        store = MemoryAccessPolicyStore()
        b1 = _make_bridge("bridge-1", role_a="D1-R1", role_b="D2-R1")
        b2 = _make_bridge("bridge-2", role_a="D3-R1", role_b="D4-R1")
        store.save_bridge(b1)
        store.save_bridge(b2)
        bridges = store.list_bridges()
        assert len(bridges) == 2

    def test_list_bridges_empty(self) -> None:
        store = MemoryAccessPolicyStore()
        assert store.list_bridges() == []

    def test_bounded_ksp_eviction(self) -> None:
        store = MemoryAccessPolicyStore()
        for i in range(MAX_STORE_SIZE + 5):
            ksp = _make_ksp(f"ksp-{i}", source=f"D{i}", target=f"D{i + 10000}")
            store.save_ksp(ksp)
        # Earliest should be evicted
        ksps = store.list_ksps()
        ksp_ids = {k.id for k in ksps}
        assert "ksp-0" not in ksp_ids
        # Latest should remain
        assert f"ksp-{MAX_STORE_SIZE + 4}" in ksp_ids

    def test_bounded_bridge_eviction(self) -> None:
        store = MemoryAccessPolicyStore()
        for i in range(MAX_STORE_SIZE + 5):
            bridge = _make_bridge(f"bridge-{i}", role_a=f"D{i}-R1", role_b=f"D{i + 10000}-R1")
            store.save_bridge(bridge)
        bridges = store.list_bridges()
        bridge_ids = {b.id for b in bridges}
        assert "bridge-0" not in bridge_ids
        assert f"bridge-{MAX_STORE_SIZE + 4}" in bridge_ids
