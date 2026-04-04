# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for LCA bridge approval (PACT Section 4.4).

Before creating a cross-functional bridge, the lowest common ancestor (LCA)
of the source and target roles must approve the bridge via approve_bridge().

Covers:
- LCA calculation for various tree structures
- create_bridge without approval raises PactError
- create_bridge with valid LCA approval succeeds
- Expired approval raises PactError
- Wrong approver (not LCA) raises PactError
- Cross-org / no-common-ancestor bridges blocked
- BridgeApproval serialization (to_dict / from_dict)
- Address.lowest_common_ancestor() correctness
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from kailash.trust.pact.access import PactBridge
from kailash.trust.pact.addressing import Address, NodeType
from kailash.trust.pact.compilation import CompiledOrg, OrgNode
from kailash.trust.pact.config import ConfidentialityLevel
from kailash.trust.pact.engine import BridgeApproval, GovernanceEngine
from kailash.trust.pact.exceptions import PactError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "lca-test-org") -> CompiledOrg:
    """Build a compiled org with a shared root for LCA testing.

    Tree:
      R1 (CEO)
        D1 (Engineering)
          D1-R1 (VP Eng)
            D1-R1-T1 (Backend)
              D1-R1-T1-R1 (Backend Lead)
            D1-R1-T2 (Frontend)
              D1-R1-T2-R1 (Frontend Lead)
        D2 (Finance)
          D2-R1 (CFO)
            D2-R1-T1 (Accounting)
              D2-R1-T1-R1 (Accounting Lead)
    """
    org = CompiledOrg(org_id=org_id)

    # Root role
    org.nodes["R1"] = OrgNode(
        address="R1",
        node_type=NodeType.ROLE,
        name="CEO",
        node_id="ceo",
    )
    # Engineering department
    org.nodes["D1"] = OrgNode(
        address="D1",
        node_type=NodeType.DEPARTMENT,
        name="Engineering",
        node_id="eng",
        parent_address="R1",
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
    org.nodes["D1-R1-T2"] = OrgNode(
        address="D1-R1-T2",
        node_type=NodeType.TEAM,
        name="Frontend",
        node_id="frontend",
        parent_address="D1-R1",
    )
    org.nodes["D1-R1-T2-R1"] = OrgNode(
        address="D1-R1-T2-R1",
        node_type=NodeType.ROLE,
        name="Frontend Lead",
        node_id="frontend-lead",
        parent_address="D1-R1-T2",
    )
    # Finance department
    org.nodes["D2"] = OrgNode(
        address="D2",
        node_type=NodeType.DEPARTMENT,
        name="Finance",
        node_id="fin",
        parent_address="R1",
    )
    org.nodes["D2-R1"] = OrgNode(
        address="D2-R1",
        node_type=NodeType.ROLE,
        name="CFO",
        node_id="cfo",
        parent_address="D2",
    )
    org.nodes["D2-R1-T1"] = OrgNode(
        address="D2-R1-T1",
        node_type=NodeType.TEAM,
        name="Accounting",
        node_id="accounting",
        parent_address="D2-R1",
    )
    org.nodes["D2-R1-T1-R1"] = OrgNode(
        address="D2-R1-T1-R1",
        node_type=NodeType.ROLE,
        name="Accounting Lead",
        node_id="accounting-lead",
        parent_address="D2-R1-T1",
    )
    return org


def _make_disjoint_org(org_id: str = "disjoint-org") -> CompiledOrg:
    """Build a compiled org with two disjoint trees (no shared root).

    Tree:
      D1 (Engineering)
        D1-R1 (VP Eng)
      D2 (Finance)
        D2-R1 (CFO)
    """
    org = CompiledOrg(org_id=org_id)
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
    org.nodes["D2"] = OrgNode(
        address="D2",
        node_type=NodeType.DEPARTMENT,
        name="Finance",
        node_id="fin",
    )
    org.nodes["D2-R1"] = OrgNode(
        address="D2-R1",
        node_type=NodeType.ROLE,
        name="CFO",
        node_id="cfo",
        parent_address="D2",
    )
    return org


# ---------------------------------------------------------------------------
# Address.lowest_common_ancestor() tests
# ---------------------------------------------------------------------------


class TestLowestCommonAncestor:
    """Test Address.lowest_common_ancestor() for various tree shapes."""

    def test_sibling_roles_under_same_parent(self) -> None:
        """Two siblings under the same parent share that parent as LCA."""
        # D1-R1-T1-R1 and D1-R1-T2-R1 both have D1-R1 in their chain
        addr_a = Address.parse("D1-R1-T1-R1")
        addr_b = Address.parse("D1-R1-T2-R1")
        lca = Address.lowest_common_ancestor(addr_a, addr_b)
        assert lca is not None
        assert str(lca) == "D1-R1"

    def test_parent_child_lca_is_parent(self) -> None:
        """Parent and child: LCA is the parent itself."""
        addr_a = Address.parse("D1-R1")
        addr_b = Address.parse("D1-R1-T1-R1")
        lca = Address.lowest_common_ancestor(addr_a, addr_b)
        assert lca is not None
        assert str(lca) == "D1-R1"

    def test_same_address_lca_is_self(self) -> None:
        """Same address: LCA is the address itself."""
        addr = Address.parse("D1-R1-T1-R1")
        lca = Address.lowest_common_ancestor(addr, addr)
        assert lca is not None
        assert str(lca) == "D1-R1-T1-R1"

    def test_cross_department_lca_is_shared_root(self) -> None:
        """Roles in different departments under a shared root share that root as LCA.

        R1 -> D1-R1 -> D1-R1-T1-R1
        R1 -> D2-R1 -> D2-R1-T1-R1

        Note: R1 is not in the accountability chain of D1-R1 because R1 is not
        a prefix of D1-R1 in the D/T/R grammar. The accountability chain only
        includes Role segments within the address itself. So D1-R1's chain is
        [D1-R1] and D2-R1's chain is [D2-R1]. No common ancestor.
        """
        addr_a = Address.parse("D1-R1")
        addr_b = Address.parse("D2-R1")
        lca = Address.lowest_common_ancestor(addr_a, addr_b)
        # These are in separate top-level departments with no shared Role prefix
        assert lca is None

    def test_deep_hierarchy_finds_deepest_common(self) -> None:
        """In a deep hierarchy, the deepest common role ancestor is found."""
        # D1-R1-D1-R1-D1-R1 and D1-R1-D1-R1-T1-R1
        # Both share D1-R1 and D1-R1-D1-R1 in their accountability chains
        addr_a = Address.parse("D1-R1-D1-R1-D1-R1")
        addr_b = Address.parse("D1-R1-D1-R1-T1-R1")
        lca = Address.lowest_common_ancestor(addr_a, addr_b)
        assert lca is not None
        assert str(lca) == "D1-R1-D1-R1"

    def test_no_common_ancestor_returns_none(self) -> None:
        """Addresses with no shared Role ancestor return None."""
        addr_a = Address.parse("D1-R1")
        addr_b = Address.parse("D2-R1")
        lca = Address.lowest_common_ancestor(addr_a, addr_b)
        assert lca is None


# ---------------------------------------------------------------------------
# approve_bridge() tests
# ---------------------------------------------------------------------------


class TestApproveBridge:
    """Test approve_bridge() -- LCA validation."""

    def test_approve_bridge_with_correct_lca(self) -> None:
        """Approving a bridge with the correct LCA succeeds."""
        engine = GovernanceEngine(_make_compiled_org())
        approval = engine.approve_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approver_address="D1-R1",  # LCA of both
        )
        assert isinstance(approval, BridgeApproval)
        assert approval.source_address == "D1-R1-T1-R1"
        assert approval.target_address == "D1-R1-T2-R1"
        assert approval.approved_by == "D1-R1"
        assert approval.expires_at > approval.approved_at

    def test_approve_bridge_wrong_approver_raises(self) -> None:
        """Approving a bridge with the wrong approver raises PactError."""
        engine = GovernanceEngine(_make_compiled_org())
        with pytest.raises(PactError, match="Bridge approval must come from the LCA"):
            engine.approve_bridge(
                source_address="D1-R1-T1-R1",
                target_address="D1-R1-T2-R1",
                approver_address="D1-R1-T1-R1",  # Not the LCA
            )

    def test_approve_bridge_no_common_ancestor_raises(self) -> None:
        """Approving a bridge between addresses with no common ancestor raises PactError."""
        engine = GovernanceEngine(_make_disjoint_org())
        with pytest.raises(PactError, match="no common ancestor"):
            engine.approve_bridge(
                source_address="D1-R1",
                target_address="D2-R1",
                approver_address="D1-R1",
            )

    def test_approve_bridge_emits_audit(self) -> None:
        """approve_bridge emits an audit anchor."""
        from kailash.trust.pact.audit import AuditChain

        audit_chain = AuditChain(chain_id="test-audit")
        engine = GovernanceEngine(_make_compiled_org(), audit_chain=audit_chain)
        initial_length = audit_chain.length

        engine.approve_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approver_address="D1-R1",
        )

        assert audit_chain.length > initial_length
        latest = audit_chain.latest
        assert latest is not None
        assert latest.action == "bridge_approved"


# ---------------------------------------------------------------------------
# create_bridge() with LCA enforcement tests
# ---------------------------------------------------------------------------


class TestCreateBridgeLCA:
    """Test that create_bridge enforces LCA approval."""

    def test_create_bridge_without_approval_raises(self) -> None:
        """Creating a bridge without prior LCA approval raises PactError."""
        engine = GovernanceEngine(_make_compiled_org())
        bridge = PactBridge(
            id="bridge-no-approval",
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        with pytest.raises(PactError, match="Bridge requires approval from LCA"):
            engine.create_bridge(bridge)

    def test_create_bridge_with_valid_approval_succeeds(self) -> None:
        """Creating a bridge after valid LCA approval succeeds."""
        engine = GovernanceEngine(_make_compiled_org())

        # Step 1: LCA approves
        engine.approve_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approver_address="D1-R1",
        )

        # Step 2: Create bridge
        bridge = PactBridge(
            id="bridge-approved",
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        engine.create_bridge(bridge)  # Should not raise

        # Verify bridge was persisted
        bridges = engine._access_policy_store.list_bridges()
        assert any(b.id == "bridge-approved" for b in bridges)

    def test_create_bridge_with_reversed_address_approval_succeeds(self) -> None:
        """Approval for A->B should satisfy bridge creation for B->A."""
        engine = GovernanceEngine(_make_compiled_org())

        # Approve with source/target in one order
        engine.approve_bridge(
            source_address="D1-R1-T2-R1",
            target_address="D1-R1-T1-R1",
            approver_address="D1-R1",
        )

        # Create bridge with addresses in opposite order
        bridge = PactBridge(
            id="bridge-reversed",
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        engine.create_bridge(bridge)  # Should not raise

    def test_expired_approval_raises(self) -> None:
        """Creating a bridge with an expired approval raises PactError."""
        engine = GovernanceEngine(_make_compiled_org())

        # Manually inject an expired approval
        now = datetime.now(UTC)
        expired_approval = BridgeApproval(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approved_by="D1-R1",
            approved_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),  # Expired 1 hour ago
        )
        key = "D1-R1-T1-R1|D1-R1-T2-R1"
        with engine._lock:
            engine._bridge_approvals[key] = expired_approval

        bridge = PactBridge(
            id="bridge-expired",
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        with pytest.raises(PactError, match="Bridge requires approval from LCA"):
            engine.create_bridge(bridge)

    def test_no_common_ancestor_blocks_bridge(self) -> None:
        """Bridges between addresses with no common ancestor are blocked."""
        engine = GovernanceEngine(_make_disjoint_org())

        bridge = PactBridge(
            id="bridge-no-ancestor",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        with pytest.raises(PactError, match="no common ancestor"):
            engine.create_bridge(bridge)

    def test_create_bridge_audit_includes_lca(self) -> None:
        """Audit record for bridge creation includes the LCA approver."""
        from kailash.trust.pact.audit import AuditChain

        audit_chain = AuditChain(chain_id="test-audit")
        engine = GovernanceEngine(_make_compiled_org(), audit_chain=audit_chain)

        engine.approve_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approver_address="D1-R1",
        )

        bridge = PactBridge(
            id="bridge-audited",
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        engine.create_bridge(bridge)

        latest = audit_chain.latest
        assert latest is not None
        assert latest.action == "bridge_established"
        assert latest.metadata.get("lca_approver") == "D1-R1"


# ---------------------------------------------------------------------------
# BridgeApproval serialization tests
# ---------------------------------------------------------------------------


class TestApproveBridgeVacancy:
    """Test that approve_bridge() blocks vacant approvers."""

    def test_approve_bridge_with_vacant_approver_raises(self) -> None:
        """Approving a bridge with a vacant LCA role raises PactError."""
        org = _make_compiled_org()
        # Make VP Eng (D1-R1, the LCA) vacant
        org.nodes["D1-R1"] = OrgNode(
            address="D1-R1",
            node_type=NodeType.ROLE,
            name="VP Eng",
            node_id="vp-eng",
            parent_address="D1",
            is_vacant=True,
        )
        engine = GovernanceEngine(org)
        with pytest.raises(PactError, match="vacant role"):
            engine.approve_bridge(
                source_address="D1-R1-T1-R1",
                target_address="D1-R1-T2-R1",
                approver_address="D1-R1",
            )

    def test_approve_bridge_with_non_vacant_approver_succeeds(self) -> None:
        """Approving a bridge with a non-vacant LCA role succeeds."""
        engine = GovernanceEngine(_make_compiled_org())
        approval = engine.approve_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approver_address="D1-R1",
        )
        assert isinstance(approval, BridgeApproval)
        assert approval.approved_by == "D1-R1"


# ---------------------------------------------------------------------------
# reject_bridge() tests
# ---------------------------------------------------------------------------


class TestRejectBridge:
    """Test reject_bridge() -- LCA validation and vacancy checks."""

    def test_reject_bridge_success(self) -> None:
        """Approve then reject a bridge -- approval is removed."""
        engine = GovernanceEngine(_make_compiled_org())
        engine.approve_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approver_address="D1-R1",
        )
        result = engine.reject_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            rejector_address="D1-R1",
        )
        assert result is True
        # Verify approval is gone -- creating a bridge should now fail
        bridge = PactBridge(
            id="bridge-after-reject",
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        with pytest.raises(PactError, match="Bridge requires approval from LCA"):
            engine.create_bridge(bridge)

    def test_reject_bridge_with_vacant_rejector_raises(self) -> None:
        """Rejecting a bridge with a vacant LCA role raises PactError."""
        org = _make_compiled_org()
        # Make VP Eng (D1-R1, the LCA) vacant
        org.nodes["D1-R1"] = OrgNode(
            address="D1-R1",
            node_type=NodeType.ROLE,
            name="VP Eng",
            node_id="vp-eng",
            parent_address="D1",
            is_vacant=True,
        )
        engine = GovernanceEngine(org)
        with pytest.raises(PactError, match="vacant role"):
            engine.reject_bridge(
                source_address="D1-R1-T1-R1",
                target_address="D1-R1-T2-R1",
                rejector_address="D1-R1",
            )

    def test_reject_bridge_with_non_lca_raises(self) -> None:
        """Rejecting a bridge with a non-LCA role raises PactError."""
        engine = GovernanceEngine(_make_compiled_org())
        with pytest.raises(PactError, match="Bridge rejection must come from the LCA"):
            engine.reject_bridge(
                source_address="D1-R1-T1-R1",
                target_address="D1-R1-T2-R1",
                rejector_address="D1-R1-T1-R1",  # Not the LCA
            )

    def test_reject_bridge_no_approval_returns_false(self) -> None:
        """Rejecting a bridge with no existing approval returns False."""
        engine = GovernanceEngine(_make_compiled_org())
        result = engine.reject_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            rejector_address="D1-R1",
        )
        assert result is False

    def test_reject_bridge_emits_audit(self) -> None:
        """reject_bridge emits an audit anchor."""
        from kailash.trust.pact.audit import AuditChain

        audit_chain = AuditChain(chain_id="test-audit")
        engine = GovernanceEngine(_make_compiled_org(), audit_chain=audit_chain)
        initial_length = audit_chain.length

        engine.reject_bridge(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            rejector_address="D1-R1",
        )

        assert audit_chain.length > initial_length
        latest = audit_chain.latest
        assert latest is not None
        assert latest.action == "bridge_rejected"


# ---------------------------------------------------------------------------
# designate_acting_occupant vacancy guard tests
# ---------------------------------------------------------------------------


class TestDesignateActingOccupantOnFilledRole:
    """Test that designate_acting_occupant() rejects filled roles."""

    def test_designate_acting_occupant_on_filled_role_raises(self) -> None:
        """Designating an acting occupant on a non-vacant role raises PactError."""
        engine = GovernanceEngine(_make_compiled_org())
        # D1-R1 is not vacant in the standard org
        with pytest.raises(PactError, match="is not vacant"):
            engine.designate_acting_occupant(
                vacant_role="D1-R1",
                acting_role="D1-R1-T1-R1",
                designated_by="R1",
            )


# ---------------------------------------------------------------------------
# BridgeApproval serialization tests
# ---------------------------------------------------------------------------


class TestBridgeApprovalSerialization:
    """Test BridgeApproval to_dict() / from_dict() round-trip."""

    def test_round_trip(self) -> None:
        """BridgeApproval survives to_dict -> from_dict round-trip."""
        now = datetime.now(UTC)
        approval = BridgeApproval(
            source_address="D1-R1-T1-R1",
            target_address="D1-R1-T2-R1",
            approved_by="D1-R1",
            approved_at=now,
            expires_at=now + timedelta(hours=24),
        )
        data = approval.to_dict()
        restored = BridgeApproval.from_dict(data)

        assert restored.source_address == approval.source_address
        assert restored.target_address == approval.target_address
        assert restored.approved_by == approval.approved_by
        assert restored.approved_at == approval.approved_at
        assert restored.expires_at == approval.expires_at

    def test_frozen(self) -> None:
        """BridgeApproval is frozen (immutable)."""
        now = datetime.now(UTC)
        approval = BridgeApproval(
            source_address="D1-R1",
            target_address="D1-R1-T1-R1",
            approved_by="D1-R1",
            approved_at=now,
            expires_at=now + timedelta(hours=24),
        )
        with pytest.raises(AttributeError):
            approval.approved_by = "hacked"  # type: ignore[misc]
