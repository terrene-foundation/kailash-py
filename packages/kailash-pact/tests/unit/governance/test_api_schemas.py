# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Unit tests for governance API Pydantic request/response schemas.

Tests schema validation, NaN/Inf rejection, D/T/R address format checks,
enum validation, and serialization round-trips.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Schema imports (will be created in src/pact/governance/api/schemas.py)
# ---------------------------------------------------------------------------
from pact.governance.api.schemas import (
    CheckAccessRequest,
    CheckAccessResponse,
    CreateBridgeRequest,
    CreateKSPRequest,
    GrantClearanceRequest,
    OrgNodeResponse,
    OrgSummaryResponse,
    SetEnvelopeRequest,
    VerifyActionRequest,
    VerifyActionResponse,
)


# ===================================================================
# CheckAccessRequest validation
# ===================================================================


class TestCheckAccessRequest:
    """Validate CheckAccessRequest field validation and constraints."""

    def test_valid_request(self) -> None:
        """A fully valid request passes validation."""
        req = CheckAccessRequest(
            role_address="D1-R1-T1-R1",
            item_id="doc-001",
            item_classification="public",
            item_owning_unit="D1-R1-T1",
            item_compartments=[],
            posture="supervised",
        )
        assert req.role_address == "D1-R1-T1-R1"
        assert req.item_classification == "public"
        assert req.posture == "supervised"

    def test_valid_request_with_compartments(self) -> None:
        """Compartments list is accepted when provided."""
        req = CheckAccessRequest(
            role_address="D1-R1",
            item_id="doc-002",
            item_classification="secret",
            item_owning_unit="D1",
            item_compartments=["alpha", "bravo"],
            posture="delegated",
        )
        assert req.item_compartments == ["alpha", "bravo"]

    def test_rejects_address_without_dtr_segments(self) -> None:
        """Address must contain at least one D, T, or R segment."""
        with pytest.raises(ValidationError, match="D/T/R"):
            CheckAccessRequest(
                role_address="invalid-address",
                item_id="doc-001",
                item_classification="public",
                item_owning_unit="some-unit",
                posture="supervised",
            )

    def test_rejects_empty_address(self) -> None:
        """Empty address string is rejected."""
        with pytest.raises(ValidationError):
            CheckAccessRequest(
                role_address="",
                item_id="doc-001",
                item_classification="public",
                item_owning_unit="some-unit",
                posture="supervised",
            )

    def test_rejects_invalid_classification(self) -> None:
        """Classification must be a valid ConfidentialityLevel value."""
        with pytest.raises(ValidationError, match="item_classification"):
            CheckAccessRequest(
                role_address="D1-R1",
                item_id="doc-001",
                item_classification="ultra_secret",
                item_owning_unit="D1",
                posture="supervised",
            )

    def test_rejects_invalid_posture(self) -> None:
        """Posture must be a valid TrustPostureLevel value."""
        with pytest.raises(ValidationError, match="posture"):
            CheckAccessRequest(
                role_address="D1-R1",
                item_id="doc-001",
                item_classification="public",
                item_owning_unit="D1",
                posture="fully_autonomous",
            )

    def test_accepts_all_valid_classifications(self) -> None:
        """All five ConfidentialityLevel values are accepted."""
        for level in ("public", "restricted", "confidential", "secret", "top_secret"):
            req = CheckAccessRequest(
                role_address="D1-R1",
                item_id="doc-001",
                item_classification=level,
                item_owning_unit="D1",
                posture="supervised",
            )
            assert req.item_classification == level

    def test_accepts_all_valid_postures(self) -> None:
        """All five TrustPostureLevel values are accepted."""
        for posture in (
            "pseudo_agent",
            "supervised",
            "shared_planning",
            "continuous_insight",
            "delegated",
        ):
            req = CheckAccessRequest(
                role_address="D1-R1",
                item_id="doc-001",
                item_classification="public",
                item_owning_unit="D1",
                posture=posture,
            )
            assert req.posture == posture


class TestCheckAccessResponse:
    """Validate CheckAccessResponse serialization."""

    def test_allowed_response(self) -> None:
        resp = CheckAccessResponse(
            allowed=True,
            reason="Same unit access",
            step_failed=None,
            audit_details={"step": "4a"},
        )
        assert resp.allowed is True
        assert resp.step_failed is None

    def test_denied_response(self) -> None:
        resp = CheckAccessResponse(
            allowed=False,
            reason="No clearance found",
            step_failed=1,
            audit_details={"detail": "missing_clearance"},
        )
        assert resp.allowed is False
        assert resp.step_failed == 1

    def test_serialization_roundtrip(self) -> None:
        resp = CheckAccessResponse(
            allowed=True,
            reason="KSP grants access",
            step_failed=None,
            audit_details={"ksp_id": "ksp-001"},
        )
        data = resp.model_dump()
        restored = CheckAccessResponse(**data)
        assert restored.allowed == resp.allowed
        assert restored.reason == resp.reason


# ===================================================================
# VerifyActionRequest validation
# ===================================================================


class TestVerifyActionRequest:
    """Validate VerifyActionRequest field validation."""

    def test_valid_minimal_request(self) -> None:
        """Minimal valid request with required fields only."""
        req = VerifyActionRequest(
            role_address="D1-R1-T1-R1",
            action="read",
        )
        assert req.cost is None
        assert req.resource is None
        assert req.channel is None

    def test_valid_full_request(self) -> None:
        """Fully populated request."""
        req = VerifyActionRequest(
            role_address="D1-R1",
            action="deploy",
            cost=100.50,
            resource="/data/reports",
            channel="internal",
        )
        assert req.cost == 100.50
        assert req.resource == "/data/reports"

    def test_rejects_nan_cost(self) -> None:
        """NaN cost values are rejected -- they bypass governance checks."""
        with pytest.raises(ValidationError, match="cost"):
            VerifyActionRequest(
                role_address="D1-R1",
                action="purchase",
                cost=float("nan"),
            )

    def test_rejects_inf_cost(self) -> None:
        """Inf cost values are rejected."""
        with pytest.raises(ValidationError, match="cost"):
            VerifyActionRequest(
                role_address="D1-R1",
                action="purchase",
                cost=float("inf"),
            )

    def test_rejects_negative_inf_cost(self) -> None:
        """Negative Inf cost values are rejected."""
        with pytest.raises(ValidationError, match="cost"):
            VerifyActionRequest(
                role_address="D1-R1",
                action="purchase",
                cost=float("-inf"),
            )

    def test_rejects_negative_cost(self) -> None:
        """Negative cost values are rejected."""
        with pytest.raises(ValidationError, match="cost"):
            VerifyActionRequest(
                role_address="D1-R1",
                action="purchase",
                cost=-10.0,
            )

    def test_allows_zero_cost(self) -> None:
        """Zero cost is valid (free action)."""
        req = VerifyActionRequest(
            role_address="D1-R1",
            action="read",
            cost=0.0,
        )
        assert req.cost == 0.0

    def test_rejects_invalid_address(self) -> None:
        """Address validation applies to verify-action too."""
        with pytest.raises(ValidationError, match="D/T/R"):
            VerifyActionRequest(
                role_address="no-segments-here",
                action="read",
            )

    def test_rejects_empty_action(self) -> None:
        """Action must not be empty."""
        with pytest.raises(ValidationError, match="action"):
            VerifyActionRequest(
                role_address="D1-R1",
                action="",
            )


class TestVerifyActionResponse:
    """Validate VerifyActionResponse."""

    def test_auto_approved_response(self) -> None:
        resp = VerifyActionResponse(
            level="auto_approved",
            allowed=True,
            reason="Within all constraint dimensions",
            role_address="D1-R1",
            action="read",
        )
        assert resp.allowed is True

    def test_blocked_response(self) -> None:
        resp = VerifyActionResponse(
            level="blocked",
            allowed=False,
            reason="Action explicitly blocked",
            role_address="D1-R1",
            action="deploy",
        )
        assert resp.allowed is False
        assert resp.level == "blocked"

    def test_rejects_invalid_level(self) -> None:
        """Level must be one of the four verification gradient values."""
        with pytest.raises(ValidationError, match="level"):
            VerifyActionResponse(
                level="maybe",
                allowed=True,
                reason="test",
                role_address="D1-R1",
                action="read",
            )


# ===================================================================
# OrgSummaryResponse / OrgNodeResponse
# ===================================================================


class TestOrgSummaryResponse:
    """Validate organization summary response."""

    def test_valid_summary(self) -> None:
        resp = OrgSummaryResponse(
            org_id="test-org",
            name="Test Organization",
            department_count=2,
            team_count=4,
            role_count=12,
            total_nodes=18,
        )
        assert resp.total_nodes == 18


class TestOrgNodeResponse:
    """Validate single org node response."""

    def test_valid_node(self) -> None:
        resp = OrgNodeResponse(
            address="D1-R1-T1-R1",
            name="Developer",
            node_type="R",
            parent_address="D1-R1-T1",
            is_vacant=False,
            children=[],
        )
        assert resp.address == "D1-R1-T1-R1"
        assert resp.node_type == "R"

    def test_node_with_children(self) -> None:
        resp = OrgNodeResponse(
            address="D1-R1",
            name="VP Engineering",
            node_type="R",
            parent_address="D1",
            is_vacant=False,
            children=["D1-R1-T1", "D1-R1-T2"],
        )
        assert len(resp.children) == 2


# ===================================================================
# GrantClearanceRequest
# ===================================================================


class TestGrantClearanceRequest:
    """Validate clearance granting request."""

    def test_valid_request(self) -> None:
        req = GrantClearanceRequest(
            role_address="D1-R1-T1-R1",
            max_clearance="confidential",
            compartments=["alpha"],
            granted_by_role_address="D1-R1",
        )
        assert req.max_clearance == "confidential"
        assert req.compartments == ["alpha"]

    def test_rejects_invalid_clearance_level(self) -> None:
        with pytest.raises(ValidationError, match="max_clearance"):
            GrantClearanceRequest(
                role_address="D1-R1",
                max_clearance="above_top_secret",
                granted_by_role_address="D1-R1",
            )

    def test_defaults_for_optional_fields(self) -> None:
        req = GrantClearanceRequest(
            role_address="D1-R1",
            max_clearance="public",
            granted_by_role_address="D1-R1",
        )
        assert req.compartments == []

    def test_rejects_invalid_address(self) -> None:
        with pytest.raises(ValidationError, match="D/T/R"):
            GrantClearanceRequest(
                role_address="bad-address",
                max_clearance="public",
                granted_by_role_address="D1-R1",
            )


# ===================================================================
# CreateBridgeRequest
# ===================================================================


class TestCreateBridgeRequest:
    """Validate bridge creation request."""

    def test_valid_request(self) -> None:
        req = CreateBridgeRequest(
            role_a_address="D1-R1-T1-R1",
            role_b_address="D1-R1-T2-R1",
            bridge_type="standing",
            max_classification="restricted",
        )
        assert req.bridge_type == "standing"
        assert req.bilateral is True  # default

    def test_rejects_invalid_bridge_type(self) -> None:
        with pytest.raises(ValidationError, match="bridge_type"):
            CreateBridgeRequest(
                role_a_address="D1-R1",
                role_b_address="D2-R1",
                bridge_type="permanent",
                max_classification="public",
            )

    def test_accepts_all_bridge_types(self) -> None:
        for btype in ("standing", "scoped", "ad_hoc"):
            req = CreateBridgeRequest(
                role_a_address="D1-R1",
                role_b_address="D2-R1",
                bridge_type=btype,
                max_classification="public",
            )
            assert req.bridge_type == btype

    def test_unilateral_bridge(self) -> None:
        req = CreateBridgeRequest(
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="scoped",
            max_classification="confidential",
            bilateral=False,
        )
        assert req.bilateral is False


# ===================================================================
# CreateKSPRequest
# ===================================================================


class TestCreateKSPRequest:
    """Validate Knowledge Share Policy creation request."""

    def test_valid_request(self) -> None:
        req = CreateKSPRequest(
            source_unit_address="D1-R1-T1",
            target_unit_address="D1-R1-T2",
            max_classification="restricted",
            created_by_role_address="D1-R1",
        )
        assert req.source_unit_address == "D1-R1-T1"

    def test_rejects_invalid_classification(self) -> None:
        with pytest.raises(ValidationError, match="max_classification"):
            CreateKSPRequest(
                source_unit_address="D1-R1-T1",
                target_unit_address="D1-R1-T2",
                max_classification="invalid",
                created_by_role_address="D1-R1",
            )


# ===================================================================
# SetEnvelopeRequest
# ===================================================================


class TestSetEnvelopeRequest:
    """Validate envelope creation request."""

    def test_valid_request(self) -> None:
        req = SetEnvelopeRequest(
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope_id="env-001",
            constraints={
                "financial": {"max_spend_usd": 1000.0},
                "operational": {"allowed_actions": ["read", "write"]},
            },
        )
        assert req.envelope_id == "env-001"

    def test_rejects_nan_in_constraints(self) -> None:
        """NaN in nested financial constraints must be rejected."""
        with pytest.raises(ValidationError, match="finite"):
            SetEnvelopeRequest(
                defining_role_address="D1-R1",
                target_role_address="D1-R1-T1-R1",
                envelope_id="env-002",
                constraints={
                    "financial": {"max_spend_usd": float("nan")},
                },
            )

    def test_rejects_inf_in_constraints(self) -> None:
        """Inf in nested financial constraints must be rejected."""
        with pytest.raises(ValidationError, match="finite"):
            SetEnvelopeRequest(
                defining_role_address="D1-R1",
                target_role_address="D1-R1-T1-R1",
                envelope_id="env-003",
                constraints={
                    "financial": {"max_spend_usd": float("inf")},
                },
            )
