# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Unit tests for governance REST API endpoints with HTTPX test client.

Tests all governance API routes: check-access, verify-action, org queries,
clearance granting, bridge/KSP creation, rate limiting, and WebSocket events.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TeamConfig,
    TrustPostureLevel,
)
from pact.build.org.builder import OrgDefinition
from pact.governance.access import PactBridge
from pact.governance.api.auth import GovernanceAuth
from pact.governance.api.router import create_governance_app
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import RoleEnvelope
from pact.governance.knowledge import KnowledgeItem


# ===================================================================
# Test fixtures
# ===================================================================


def _build_test_org() -> tuple[CompiledOrg, OrgDefinition]:
    """Build a minimal org for API testing.

    Structure:
        D1 (Engineering) -> R1 (VP Engineering)
            T1 (Backend)  -> R1 (Lead Developer)
            T2 (Frontend) -> R1 (Lead Designer)

    Returns:
        A tuple of (CompiledOrg, OrgDefinition).
    """
    departments = [
        DepartmentConfig(department_id="d-engineering", name="Engineering"),
    ]
    teams = [
        TeamConfig(id="t-backend", name="Backend", workspace="ws-backend"),
        TeamConfig(id="t-frontend", name="Frontend", workspace="ws-frontend"),
    ]
    roles = [
        RoleDefinition(
            role_id="r-vp-eng",
            name="VP Engineering",
            reports_to_role_id=None,
            is_primary_for_unit="d-engineering",
        ),
        RoleDefinition(
            role_id="r-lead-dev",
            name="Lead Developer",
            reports_to_role_id="r-vp-eng",
            is_primary_for_unit="t-backend",
        ),
        RoleDefinition(
            role_id="r-lead-designer",
            name="Lead Designer",
            reports_to_role_id="r-vp-eng",
            is_primary_for_unit="t-frontend",
        ),
    ]
    org_def = OrgDefinition(
        org_id="api-test-org",
        name="API Test Organization",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    compiled = compile_org(org_def)
    return compiled, org_def


def _create_test_engine() -> GovernanceEngine:
    """Create a GovernanceEngine with the test org and some initial state."""
    compiled, org_def = _build_test_org()
    engine = GovernanceEngine(org_def)

    # Grant clearance to the VP Engineering role
    vp_address = None
    lead_dev_address = None
    for addr, node in compiled.nodes.items():
        if node.name == "VP Engineering":
            vp_address = addr
        if node.name == "Lead Developer":
            lead_dev_address = addr

    if vp_address:
        engine.grant_clearance(
            vp_address,
            RoleClearance(
                role_address=vp_address,
                max_clearance=ConfidentialityLevel.SECRET,
                vetting_status=VettingStatus.ACTIVE,
                granted_by_role_address=vp_address,
            ),
        )

    if lead_dev_address:
        engine.grant_clearance(
            lead_dev_address,
            RoleClearance(
                role_address=lead_dev_address,
                max_clearance=ConfidentialityLevel.RESTRICTED,
                vetting_status=VettingStatus.ACTIVE,
                granted_by_role_address=vp_address or "",
            ),
        )

    # Set a role envelope for VP Engineering
    if vp_address:
        envelope_config = ConstraintEnvelopeConfig(
            id="env-vp-eng",
            description="VP Engineering envelope",
            financial=FinancialConstraintConfig(
                max_spend_usd=10000.0,
                requires_approval_above_usd=5000.0,
            ),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "deploy", "review"],
                blocked_actions=["delete_production"],
            ),
        )
        engine.set_role_envelope(
            RoleEnvelope(
                id="role-env-vp",
                defining_role_address=vp_address,
                target_role_address=vp_address,
                envelope=envelope_config,
            )
        )

    return engine


@pytest.fixture
def test_engine() -> GovernanceEngine:
    """A test GovernanceEngine with sample data."""
    return _create_test_engine()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Auth headers with a test token."""
    return {"Authorization": "Bearer test-governance-token"}


@pytest.fixture
def test_auth() -> GovernanceAuth:
    """GovernanceAuth configured with a test token."""
    return GovernanceAuth(api_token="test-governance-token")


@pytest.fixture
def app(test_engine: GovernanceEngine, test_auth: GovernanceAuth):
    """FastAPI app with governance routes mounted."""
    return create_governance_app(engine=test_engine, auth=test_auth)


@pytest.fixture
async def client(app) -> AsyncClient:
    """HTTPX async client for testing the governance API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _find_address_by_name(engine: GovernanceEngine, name: str) -> str:
    """Find a node's address by its name in the compiled org."""
    compiled = engine.get_org()
    for addr, node in compiled.nodes.items():
        if node.name == name:
            return addr
    raise ValueError(f"No node named '{name}' found in compiled org")


# ===================================================================
# Authentication tests
# ===================================================================


class TestAuthentication:
    """Test that governance endpoints require authentication."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Requests without a token return 401."""
        resp = await client.get("/api/v1/governance/org")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self, client: AsyncClient) -> None:
        """Requests with a wrong token return 401."""
        resp = await client.get(
            "/api/v1/governance/org",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_200(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Requests with a valid token succeed."""
        resp = await client.get(
            "/api/v1/governance/org",
            headers=auth_headers,
        )
        assert resp.status_code == 200


# ===================================================================
# GET /api/v1/governance/org
# ===================================================================


class TestGetOrgSummary:
    """Test the organization summary endpoint."""

    @pytest.mark.asyncio
    async def test_returns_org_summary(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get("/api/v1/governance/org", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == "api-test-org"
        assert data["name"] == "API Test Organization"
        assert data["department_count"] >= 1
        assert data["team_count"] >= 2
        assert data["role_count"] >= 3
        assert data["total_nodes"] >= 6  # 1 dept + 2 teams + 3 roles


# ===================================================================
# GET /api/v1/governance/org/nodes/{address}
# ===================================================================


class TestGetNode:
    """Test the node lookup endpoint."""

    @pytest.mark.asyncio
    async def test_existing_node_returns_200(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        resp = await client.get(
            f"/api/v1/governance/org/nodes/{vp_addr}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "VP Engineering"
        assert data["node_type"] == "R"

    @pytest.mark.asyncio
    async def test_nonexistent_node_returns_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get(
            "/api/v1/governance/org/nodes/D99-R99",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ===================================================================
# POST /api/v1/governance/check-access
# ===================================================================


class TestCheckAccess:
    """Test the access enforcement endpoint."""

    @pytest.mark.asyncio
    async def test_same_unit_access_allowed(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        """A role in the same unit as the knowledge item gets access."""
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        # VP Engineering accesses data in their own department (D1)
        # Find the department prefix for the VP's address
        parts = vp_addr.split("-")
        # The VP's unit is the department
        dept_prefix = "-".join(parts[:1])  # First segment: D1

        resp = await client.post(
            "/api/v1/governance/check-access",
            json={
                "role_address": vp_addr,
                "item_id": "doc-001",
                "item_classification": "restricted",
                "item_owning_unit": dept_prefix,
                "item_compartments": [],
                "posture": "delegated",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True

    @pytest.mark.asyncio
    async def test_no_clearance_denied(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """A role without clearance is denied access."""
        resp = await client.post(
            "/api/v1/governance/check-access",
            json={
                "role_address": "D99-R99",
                "item_id": "doc-001",
                "item_classification": "public",
                "item_owning_unit": "D99",
                "item_compartments": [],
                "posture": "supervised",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False
        assert data["step_failed"] is not None

    @pytest.mark.asyncio
    async def test_invalid_request_returns_422(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Invalid request body returns 422 Unprocessable Entity."""
        resp = await client.post(
            "/api/v1/governance/check-access",
            json={
                "role_address": "no-segments",
                "item_id": "doc-001",
                "item_classification": "invalid_level",
                "item_owning_unit": "D1",
                "posture": "supervised",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ===================================================================
# POST /api/v1/governance/verify-action
# ===================================================================


class TestVerifyAction:
    """Test the action verification endpoint."""

    @pytest.mark.asyncio
    async def test_allowed_action_auto_approved(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        """An allowed action returns auto_approved."""
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        resp = await client.post(
            "/api/v1/governance/verify-action",
            json={
                "role_address": vp_addr,
                "action": "read",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "auto_approved"
        assert data["allowed"] is True

    @pytest.mark.asyncio
    async def test_blocked_action(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        """An explicitly blocked action returns blocked."""
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        resp = await client.post(
            "/api/v1/governance/verify-action",
            json={
                "role_address": vp_addr,
                "action": "delete_production",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "blocked"
        assert data["allowed"] is False

    @pytest.mark.asyncio
    async def test_cost_exceeding_limit_blocked(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        """An action whose cost exceeds the financial limit is blocked."""
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        resp = await client.post(
            "/api/v1/governance/verify-action",
            json={
                "role_address": vp_addr,
                "action": "read",
                "cost": 20000.0,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "blocked"

    @pytest.mark.asyncio
    async def test_cost_held_for_approval(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        """An action cost above approval threshold is held."""
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        resp = await client.post(
            "/api/v1/governance/verify-action",
            json={
                "role_address": vp_addr,
                "action": "read",
                "cost": 7500.0,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "held"

    @pytest.mark.asyncio
    async def test_nan_cost_rejected_by_schema(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """NaN cost is caught by schema validation before reaching the engine."""
        resp = await client.post(
            "/api/v1/governance/verify-action",
            json={
                "role_address": "D1-R1",
                "action": "read",
                "cost": "NaN",
            },
            headers=auth_headers,
        )
        # Should be 422 because the schema rejects NaN
        assert resp.status_code == 422


# ===================================================================
# POST /api/v1/governance/clearances (grant clearance)
# ===================================================================


class TestGrantClearance:
    """Test the clearance granting endpoint."""

    @pytest.mark.asyncio
    async def test_grant_clearance_then_check_access(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        """Granting clearance enables subsequent access checks."""
        lead_addr = _find_address_by_name(test_engine, "Lead Designer")
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")

        # Grant clearance to Lead Designer
        resp = await client.post(
            "/api/v1/governance/clearances",
            json={
                "role_address": lead_addr,
                "max_clearance": "confidential",
                "compartments": [],
                "granted_by_role_address": vp_addr,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

        # Now check access -- the Lead Designer in Frontend team
        parts = lead_addr.split("-")
        # Find the team prefix (everything before the last R segment)
        team_prefix_parts = []
        for part in parts:
            team_prefix_parts.append(part)
            if part.startswith("T"):
                break
        team_prefix = "-".join(team_prefix_parts)

        resp = await client.post(
            "/api/v1/governance/check-access",
            json={
                "role_address": lead_addr,
                "item_id": "design-doc-001",
                "item_classification": "restricted",
                "item_owning_unit": team_prefix,
                "item_compartments": [],
                "posture": "shared_planning",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True


# ===================================================================
# POST /api/v1/governance/bridges (create bridge)
# ===================================================================


class TestCreateBridge:
    """Test the bridge creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_bridge_returns_201(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        lead_dev_addr = _find_address_by_name(test_engine, "Lead Developer")
        lead_des_addr = _find_address_by_name(test_engine, "Lead Designer")

        resp = await client.post(
            "/api/v1/governance/bridges",
            json={
                "role_a_address": lead_dev_addr,
                "role_b_address": lead_des_addr,
                "bridge_type": "scoped",
                "max_classification": "restricted",
                "bilateral": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "bridge_id" in data


# ===================================================================
# POST /api/v1/governance/ksps (create KSP)
# ===================================================================


class TestCreateKSP:
    """Test the KSP creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_ksp_returns_201(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        test_engine: GovernanceEngine,
    ) -> None:
        vp_addr = _find_address_by_name(test_engine, "VP Engineering")
        # Find team prefixes
        compiled = test_engine.get_org()
        team_addrs = [addr for addr, node in compiled.nodes.items() if node.node_type.value == "T"]
        assert len(team_addrs) >= 2

        resp = await client.post(
            "/api/v1/governance/ksps",
            json={
                "source_unit_address": team_addrs[0],
                "target_unit_address": team_addrs[1],
                "max_classification": "restricted",
                "created_by_role_address": vp_addr,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "ksp_id" in data


# ===================================================================
# GET /api/v1/governance/org/tree
# ===================================================================


class TestOrgTree:
    """Test the org tree endpoint."""

    @pytest.mark.asyncio
    async def test_returns_full_tree(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get("/api/v1/governance/org/tree", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) >= 6  # At least 6 nodes in test org


# ===================================================================
# Rate limiting
# ===================================================================


class TestRateLimiting:
    """Test that rate limiting is applied to governance endpoints."""

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429(
        self,
        test_engine: GovernanceEngine,
        test_auth: GovernanceAuth,
    ) -> None:
        """Exceeding the rate limit returns 429 Too Many Requests."""
        # Create app with very low rate limit for testing
        from pact.governance.api.router import create_governance_app

        app = create_governance_app(
            engine=test_engine,
            auth=test_auth,
            rate_limit="2/minute",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer test-governance-token"}
            # First 2 requests should succeed
            for _ in range(2):
                resp = await client.get("/api/v1/governance/org", headers=headers)
                assert resp.status_code == 200

            # Third request should be rate limited
            resp = await client.get("/api/v1/governance/org", headers=headers)
            assert resp.status_code == 429
