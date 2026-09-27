# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Governance API endpoint handlers.

All endpoint handlers are pure functions that take a GovernanceEngine and
request models, and return response models. They are mounted by router.py.

Endpoints:
    POST /api/v1/governance/check-access     -- 5-step access enforcement
    POST /api/v1/governance/verify-action     -- envelope + gradient evaluation
    GET  /api/v1/governance/org               -- organization summary
    GET  /api/v1/governance/org/nodes/{addr}  -- single node lookup
    GET  /api/v1/governance/org/tree          -- full org tree
    POST /api/v1/governance/clearances        -- grant clearance
    POST /api/v1/governance/bridges           -- create bridge
    POST /api/v1/governance/ksps              -- create KSP
    POST /api/v1/governance/envelopes         -- set role envelope

Each endpoint includes a ``request: Request`` parameter as required by
slowapi rate limiting. The limiter and rate_limit are optionally passed
into the router constructor for per-route rate limiting.

ACTOR PROVENANCE (issue #2194)
------------------------------
Actor fields -- ``granted_by_role_address``, ``created_by_role_address``,
``defining_role_address`` -- arrive in the request body. They are caller
ASSERTIONS: ``GovernanceAuth`` authenticates a single shared bearer token
and yields a constant identity, so no actor role address can be derived
server-side (``security.md`` § Identity-derivation parity).

Rather than fabricate an authorization check against a constant, every such
assertion is passed through ``unverified_actor_claim`` so that it is never
recorded in the same grammar as a server-derived fact:

* durable records store the claim prefixed with ``unverified-claim:``;
* governance events publish it under ``<field>_claimed`` alongside
  ``actor_verified`` and the server-derived ``authenticated_identity``.

One exception, and it is deliberate: ``defining_role_address`` is resolved
by the engine to compute the parent envelope for the monotonic-tightening
check, so marking the STORED value would make that lookup miss and skip the
check. Only its audit payload is labelled.

This is an honesty fix, not an authorization model. Which model to adopt --
per-principal tokens, token-scope authorization, or keeping the labelled
claim -- is the open decision in #2194.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.knowledge import KnowledgeItem
from pact.governance.api.auth import GovernanceAuth, unverified_actor_claim
from pact.governance.api.events import GovernanceEventType, emit_governance_event
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

logger = logging.getLogger(__name__)

__all__ = ["create_governance_router"]


def create_governance_router(
    engine: GovernanceEngine,
    auth: GovernanceAuth,
    *,
    limiter: Any = None,
    rate_limit: str = "60/minute",
) -> APIRouter:
    """Create the governance API router with all endpoints.

    Args:
        engine: The GovernanceEngine instance for governance decisions.
        auth: The GovernanceAuth instance for authentication.
        limiter: Optional slowapi Limiter instance for rate limiting.
        rate_limit: Rate limit string (e.g., "60/minute"). Only used
            when limiter is provided.

    Returns:
        A FastAPI APIRouter with all governance endpoints mounted.
    """
    router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

    def _sanitize_error(exc: Exception) -> str:
        """Return a sanitized error message, hiding internal details (P-H6)."""
        from kailash.trust.pact.exceptions import PactError

        if isinstance(exc, PactError):
            return str(exc)  # PactError messages are designed for users
        logger.exception("Internal error in governance API")
        return "Internal governance error — check server logs"

    def _rate_limit(func: Any) -> Any:
        """Apply rate limiting if a limiter is configured."""
        if limiter is not None:
            return limiter.limit(rate_limit)(func)
        return func

    # ------------------------------------------------------------------
    # POST /check-access
    # ------------------------------------------------------------------

    @router.post("/check-access", response_model=CheckAccessResponse)
    @_rate_limit
    async def check_access(
        request: Request,
        req: CheckAccessRequest,
        identity: str = Depends(auth.require_read),
    ) -> CheckAccessResponse:
        """Evaluate whether a role can access a classified knowledge item.

        Uses the 5-step access enforcement algorithm: clearance resolution,
        classification check, compartment check, containment check, and
        fail-closed denial.
        """
        # Build KnowledgeItem from request
        item = KnowledgeItem(
            item_id=req.item_id,
            classification=ConfidentialityLevel(req.item_classification),
            owning_unit_address=req.item_owning_unit,
            compartments=frozenset(req.item_compartments),
            path=req.item_path,
            knowledge_type=req.item_knowledge_type,
        )

        # Map posture string to enum
        posture = TrustPostureLevel(req.posture)

        # Delegate to engine (environment carries request-context facts the
        # engine cannot observe itself; the engine uses its own clock for
        # time_window conditions)
        decision = engine.check_access(
            req.role_address, item, posture, environment=req.environment
        )

        # Emit governance event (fire-and-forget)
        await emit_governance_event(
            GovernanceEventType.ACCESS_CHECKED,
            {
                "role_address": req.role_address,
                "item_id": req.item_id,
                "allowed": decision.allowed,
                # #2194: role_address above is the SUBJECT of the evaluation,
                # supplied by the caller. This is the only fact the server
                # derived about who made the call.
                "authenticated_identity": identity,
            },
            source_role_address=req.role_address,
        )

        return CheckAccessResponse(
            allowed=decision.allowed,
            reason=decision.reason,
            step_failed=decision.step_failed,
            audit_details=decision.audit_details,
        )

    # ------------------------------------------------------------------
    # POST /verify-action
    # ------------------------------------------------------------------

    @router.post("/verify-action", response_model=VerifyActionResponse)
    @_rate_limit
    async def verify_action(
        request: Request,
        req: VerifyActionRequest,
        identity: str = Depends(auth.require_read),
    ) -> VerifyActionResponse:
        """Evaluate an action against the effective constraint envelope.

        Combines envelope enforcement, verification gradient classification,
        and optional knowledge access checks.
        """
        # Build context from request
        context: dict[str, Any] = {}
        if req.cost is not None:
            context["cost"] = req.cost
        if req.channel is not None:
            context["channel"] = req.channel

        # Delegate to engine
        verdict = engine.verify_action(req.role_address, req.action, context)

        # Emit governance event
        await emit_governance_event(
            GovernanceEventType.ACTION_VERIFIED,
            {
                "role_address": req.role_address,
                "action": req.action,
                "level": verdict.level,
                "allowed": verdict.allowed,
                # #2194: role_address is the caller-supplied SUBJECT.
                "authenticated_identity": identity,
            },
            source_role_address=req.role_address,
        )

        return VerifyActionResponse(
            level=verdict.level,
            allowed=verdict.allowed,
            reason=verdict.reason,
            role_address=verdict.role_address,
            action=verdict.action,
        )

    # ------------------------------------------------------------------
    # GET /org
    # ------------------------------------------------------------------

    @router.get("/org", response_model=OrgSummaryResponse)
    @_rate_limit
    async def get_org_summary(
        request: Request,
        identity: str = Depends(auth.require_read),
    ) -> OrgSummaryResponse:
        """Get a summary of the compiled organization structure."""
        compiled = engine.get_org()
        dept_count = 0
        team_count = 0
        role_count = 0
        for node in compiled.nodes.values():
            if node.node_type.value == "D":
                dept_count += 1
            elif node.node_type.value == "T":
                team_count += 1
            elif node.node_type.value == "R":
                role_count += 1

        return OrgSummaryResponse(
            org_id=compiled.org_id,
            name=engine.org_name,
            department_count=dept_count,
            team_count=team_count,
            role_count=role_count,
            total_nodes=len(compiled.nodes),
        )

    # ------------------------------------------------------------------
    # GET /org/nodes/{address}
    # ------------------------------------------------------------------

    @router.get("/org/nodes/{address:path}", response_model=OrgNodeResponse)
    @_rate_limit
    async def get_node(
        request: Request,
        address: str,
        identity: str = Depends(auth.require_read),
    ) -> OrgNodeResponse:
        """Look up a single node by its positional address.

        Supports both exact addresses and partial D/T/R resolution (#216).
        If exact match fails, searches for nodes whose address ends with
        the given suffix (e.g., 'R2' finds 'D1-T1-R2').
        """
        node = engine.get_node(address)
        if node is None:
            # Try suffix-based resolution for non-head roles (#216)
            compiled = engine.get_org()
            for addr, n in compiled.nodes.items():
                if addr.endswith(address) or n.name == address:
                    node = n
                    break
        if node is None:
            raise HTTPException(
                status_code=404,
                detail=f"No node found at address '{address}'",
            )

        return OrgNodeResponse(
            address=node.address,
            name=node.name,
            node_type=node.node_type.value,
            parent_address=node.parent_address,
            is_vacant=node.is_vacant,
            children=list(node.children_addresses),
        )

    # ------------------------------------------------------------------
    # GET /org/tree
    # ------------------------------------------------------------------

    @router.get("/org/tree")
    @_rate_limit
    async def get_org_tree(
        request: Request,
        identity: str = Depends(auth.require_read),
    ) -> dict[str, Any]:
        """Get the full organizational tree as a flat list of nodes."""
        compiled = engine.get_org()
        nodes = []
        for addr, node in compiled.nodes.items():
            nodes.append(
                {
                    "address": node.address,
                    "name": node.name,
                    "node_type": node.node_type.value,
                    "parent_address": node.parent_address,
                    "is_vacant": node.is_vacant,
                    "children": list(node.children_addresses),
                }
            )
        return {"org_id": compiled.org_id, "nodes": nodes}

    # ------------------------------------------------------------------
    # POST /clearances
    # ------------------------------------------------------------------

    @router.post("/clearances", status_code=201)
    @_rate_limit
    async def grant_clearance(
        request: Request,
        req: GrantClearanceRequest,
        identity: str = Depends(auth.require_write),
    ) -> dict[str, Any]:
        """Grant knowledge clearance to a role."""
        # Resolve D/T/R address to actual node address (#215)
        resolved_address = req.role_address
        node = engine.get_node(req.role_address)
        if node is not None:
            resolved_address = node.address

        # #2194: the grantor address is a caller ASSERTION -- the shared
        # bearer token yields no principal to derive it from, so it is
        # recorded marked-unverified rather than in the grammar of a
        # server-derived fact. The claim itself is preserved.
        recorded_granted_by, actor_audit = unverified_actor_claim(
            req.granted_by_role_address, identity, field="granted_by"
        )

        clearance = RoleClearance(
            role_address=resolved_address,
            max_clearance=ConfidentialityLevel(req.max_clearance),
            compartments=frozenset(req.compartments),
            granted_by_role_address=recorded_granted_by,
            vetting_status=VettingStatus.ACTIVE,
        )

        try:
            engine.grant_clearance(resolved_address, clearance)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=_sanitize_error(exc))

        await emit_governance_event(
            GovernanceEventType.CLEARANCE_GRANTED,
            {
                "role_address": req.role_address,
                "max_clearance": req.max_clearance,
                **actor_audit,
            },
            source_role_address=recorded_granted_by,
        )

        return {
            "status": "granted",
            "role_address": req.role_address,
            "max_clearance": req.max_clearance,
        }

    # ------------------------------------------------------------------
    # POST /bridges
    # ------------------------------------------------------------------

    @router.post("/bridges", status_code=201)
    @_rate_limit
    async def create_bridge(
        request: Request,
        req: CreateBridgeRequest,
        identity: str = Depends(auth.require_write),
    ) -> dict[str, Any]:
        """Create a Cross-Functional Bridge between two roles."""
        bridge_id = f"bridge-{uuid4().hex[:8]}"
        bridge = PactBridge(
            id=bridge_id,
            role_a_address=req.role_a_address,
            role_b_address=req.role_b_address,
            bridge_type=req.bridge_type,
            max_classification=ConfidentialityLevel(req.max_classification),
            operational_scope=tuple(req.operational_scope),
            bilateral=req.bilateral,
            shared_paths=tuple(req.shared_paths),
        )

        try:
            engine.create_bridge(bridge)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=_sanitize_error(exc))

        await emit_governance_event(
            GovernanceEventType.BRIDGE_CREATED,
            {
                "bridge_id": bridge_id,
                "role_a": req.role_a_address,
                "role_b": req.role_b_address,
                "bridge_type": req.bridge_type,
                # #2194: role_a is a bridge ENDPOINT, not the caller. It is
                # carried in source_role_address only as a correlation key.
                "authenticated_identity": identity,
            },
            source_role_address=req.role_a_address,
        )

        return {
            "status": "created",
            "bridge_id": bridge_id,
            "bridge_type": req.bridge_type,
        }

    # ------------------------------------------------------------------
    # POST /ksps
    # ------------------------------------------------------------------

    @router.post("/ksps", status_code=201)
    @_rate_limit
    async def create_ksp(
        request: Request,
        req: CreateKSPRequest,
        identity: str = Depends(auth.require_write),
    ) -> dict[str, Any]:
        """Create a Knowledge Share Policy for cross-unit access."""
        ksp_id = f"ksp-{uuid4().hex[:8]}"
        # #2194: same shape as POST /clearances -- caller-asserted actor.
        recorded_created_by, actor_audit = unverified_actor_claim(
            req.created_by_role_address, identity, field="created_by"
        )
        ksp = KnowledgeSharePolicy(
            id=ksp_id,
            source_unit_address=req.source_unit_address,
            target_unit_address=req.target_unit_address,
            max_classification=ConfidentialityLevel(req.max_classification),
            compartments=frozenset(req.compartments),
            created_by_role_address=recorded_created_by,
            min_clearance=(
                ConfidentialityLevel(req.min_clearance)
                if req.min_clearance is not None
                else None
            ),
            shared_paths=tuple(req.shared_paths),
            shared_types=frozenset(req.shared_types),
            shared_classifications=frozenset(
                ConfidentialityLevel(c) for c in req.shared_classifications
            ),
            conditions=req.conditions,
        )

        try:
            engine.create_ksp(ksp)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=_sanitize_error(exc))

        await emit_governance_event(
            GovernanceEventType.KSP_CREATED,
            {
                "ksp_id": ksp_id,
                "source_unit": req.source_unit_address,
                "target_unit": req.target_unit_address,
                **actor_audit,
            },
            source_role_address=recorded_created_by,
        )

        return {
            "status": "created",
            "ksp_id": ksp_id,
            "source_unit": req.source_unit_address,
            "target_unit": req.target_unit_address,
        }

    # ------------------------------------------------------------------
    # POST /envelopes
    # ------------------------------------------------------------------

    @router.post("/envelopes", status_code=201)
    @_rate_limit
    async def set_envelope(
        request: Request,
        req: SetEnvelopeRequest,
        identity: str = Depends(auth.require_write),
    ) -> dict[str, Any]:
        """Set a role envelope with constraint dimensions."""
        # Build ConstraintEnvelopeConfig from the raw constraints dict
        constraint_kwargs: dict[str, Any] = {"id": req.envelope_id}

        if "financial" in req.constraints and req.constraints["financial"] is not None:
            constraint_kwargs["financial"] = FinancialConstraintConfig(
                **req.constraints["financial"]
            )
        else:
            constraint_kwargs["financial"] = None

        if "operational" in req.constraints:
            constraint_kwargs["operational"] = OperationalConstraintConfig(
                **req.constraints["operational"]
            )

        envelope_config = ConstraintEnvelopeConfig(**constraint_kwargs)

        role_envelope = RoleEnvelope(
            id=req.envelope_id,
            defining_role_address=req.defining_role_address,
            target_role_address=req.target_role_address,
            envelope=envelope_config,
        )

        try:
            engine.set_role_envelope(role_envelope)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=_sanitize_error(exc))

        # #2194: defining_role_address is ALSO a caller assertion, but unlike
        # granted_by / created_by it is FUNCTIONALLY load-bearing --
        # GovernanceEngine.set_role_envelope resolves it to compute the parent
        # envelope for the monotonic-tightening check. Marking the stored value
        # would make that lookup miss and SKIP the check, so only the audit
        # payload is labelled here; the durable field stays resolvable.
        _, actor_audit = unverified_actor_claim(
            req.defining_role_address, identity, field="defining_role"
        )

        await emit_governance_event(
            GovernanceEventType.ENVELOPE_SET,
            {
                "envelope_id": req.envelope_id,
                "defining_role": req.defining_role_address,
                "target_role": req.target_role_address,
                **actor_audit,
            },
            source_role_address=req.defining_role_address,
        )

        return {
            "status": "set",
            "envelope_id": req.envelope_id,
            "target_role_address": req.target_role_address,
        }

    return router
