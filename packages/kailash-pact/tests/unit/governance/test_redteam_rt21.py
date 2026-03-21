# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Red team RT21 -- adversarial governance hardening tests.

Comprehensive adversarial testing of the PACT governance framework:
- Access bypass attempts (forged addresses, empty posture, compartment bypasses)
- Envelope bypass attempts (NaN/Inf, negative values, degenerate envelopes)
- Store bypass attempts (path traversal, SQL injection, MAX_STORE_SIZE)
- Agent bypass attempts (self-modification, engine access, default-deny)
- API bypass attempts (unauthenticated access, wrong scope, rate limiting)
- TOCTOU defense (envelope version hash detection)
- Multi-level VERIFY (ancestor envelope blocks leaf-allowed action)
"""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
    TrustPostureLevel,
)
from pact.governance.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from pact.governance.agent import (
    GovernanceBlockedError,
    GovernanceHeldError,
    PactGovernedAgent,
)
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.context import GovernanceContext
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import (
    EffectiveEnvelopeSnapshot,
    RoleEnvelope,
    compute_effective_envelope_with_version,
)
from pact.governance.knowledge import KnowledgeItem
from pact.governance.store import (
    MAX_STORE_SIZE,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
)
from pact.governance.verdict import GovernanceVerdict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "rt21-org") -> CompiledOrg:
    """Build a minimal compiled org for testing."""
    from pact.governance.addressing import NodeType

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


def _make_engine(
    org: CompiledOrg | None = None,
) -> GovernanceEngine:
    """Create an engine with memory backend and standard config."""
    if org is None:
        org = _make_compiled_org()
    return GovernanceEngine(org)


_SENTINEL = object()


def _make_envelope(
    env_id: str = "env-test",
    max_spend: float = 1000.0,
    allowed_actions: list[str] | None | object = _SENTINEL,
    blocked_actions: list[str] | None = None,
) -> ConstraintEnvelopeConfig:
    if allowed_actions is _SENTINEL:
        resolved_actions: list[str] = ["read", "write"]
    else:
        resolved_actions = allowed_actions if allowed_actions is not None else ["read", "write"]  # type: ignore[assignment]
    return ConstraintEnvelopeConfig(
        id=env_id,
        financial=FinancialConstraintConfig(max_spend_usd=max_spend),
        operational=OperationalConstraintConfig(
            allowed_actions=resolved_actions,
            blocked_actions=blocked_actions or [],
        ),
    )


# ===========================================================================
# RT21-A: Access Bypass Attempts
# ===========================================================================


class TestAccessBypass:
    """Adversarial attempts to bypass the 5-step access algorithm."""

    def test_forged_address_outside_org_tree(self) -> None:
        """Forging an address outside the org tree must be denied (step 1: no clearance)."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        item = KnowledgeItem(
            item_id="doc-1",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        # Forged address that doesn't exist in the org
        decision = can_access(
            role_address="D99-R99",
            knowledge_item=item,
            posture=TrustPostureLevel.SUPERVISED,
            compiled_org=org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 1  # No clearance for forged address

    def test_none_posture_type_error(self) -> None:
        """Passing None as posture must raise an error, not silently pass."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        item = KnowledgeItem(
            item_id="doc-1",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        # None posture must not be accepted -- effective_clearance expects TrustPostureLevel
        with pytest.raises((TypeError, KeyError)):
            can_access(
                role_address="D1-R1",
                knowledge_item=item,
                posture=None,  # type: ignore[arg-type]
                compiled_org=org,
                clearances=clearances,
                ksps=[],
                bridges=[],
            )

    def test_bypass_compartment_with_empty_set(self) -> None:
        """Empty compartments on the role must NOT bypass item compartment requirements."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.TOP_SECRET,
                compartments=frozenset(),  # No compartments
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        item = KnowledgeItem(
            item_id="secret-doc",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
            compartments=frozenset({"project-x"}),
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,  # Ceiling: TOP_SECRET
            compiled_org=org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 3  # Compartment check

    def test_inject_ksp_for_nonexistent_unit(self) -> None:
        """A KSP referencing non-existent units must not grant access to real items."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        # KSP from a non-existent source to D1
        fake_ksp = KnowledgeSharePolicy(
            id="fake-ksp",
            source_unit_address="D999",  # Does not exist in org
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.TOP_SECRET,
            created_by_role_address="D1-R1",
        )
        item = KnowledgeItem(
            item_id="foreign-doc",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D2",  # Item is in D2
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SUPERVISED,
            compiled_org=org,
            clearances=clearances,
            ksps=[fake_ksp],
            bridges=[],
        )
        # KSP source (D999) doesn't match item owner (D2), so no access
        assert decision.allowed is False

    def test_bridge_to_self(self) -> None:
        """A bridge connecting a role to itself must not create a privilege escalation path."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.RESTRICTED,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        self_bridge = PactBridge(
            id="self-bridge",
            role_a_address="D1-R1",
            role_b_address="D1-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.TOP_SECRET,
        )
        item = KnowledgeItem(
            item_id="secret-doc",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D2",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SUPERVISED,
            compiled_org=org,
            clearances=clearances,
            ksps=[],
            bridges=[self_bridge],
        )
        # Self-bridge: item owner (D2) is NOT in the bridge domain of D1-R1.
        # A self-bridge should not grant access to foreign units.
        # Also: effective clearance (RESTRICTED) < item classification (SECRET) blocks at step 2.
        assert decision.allowed is False

    def test_expired_ksp_not_honored(self) -> None:
        """An expired KSP must not grant access (TOCTOU defense)."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1-T1-R1": RoleClearance(
                role_address="D1-R1-T1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="D1-R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        expired_ksp = KnowledgeSharePolicy(
            id="expired-ksp",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            created_by_role_address="D2-R1",
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired 1 hour ago
        )
        item = KnowledgeItem(
            item_id="fin-doc",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D2",
        )
        decision = can_access(
            role_address="D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=org,
            clearances=clearances,
            ksps=[expired_ksp],
            bridges=[],
        )
        assert decision.allowed is False  # Expired KSP must not grant access


# ===========================================================================
# RT21-B: Envelope Bypass Attempts
# ===========================================================================


class TestEnvelopeBypass:
    """Adversarial attempts to bypass envelope constraint checks."""

    def test_nan_cost_blocked_by_engine(self) -> None:
        """NaN cost must be blocked (not silently pass financial checks)."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-nan-test",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=1000.0),
        )
        engine.set_role_envelope(role_env)

        verdict = engine.verify_action(
            "D1-R1-T1-R1",
            "read",
            {"cost": float("nan")},
        )
        assert verdict.level == "blocked"
        assert "not finite" in verdict.reason.lower() or "nan" in verdict.reason.lower()

    def test_inf_cost_blocked_by_engine(self) -> None:
        """Inf cost must be blocked (not silently pass financial checks)."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-inf-test",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=1000.0),
        )
        engine.set_role_envelope(role_env)

        verdict = engine.verify_action(
            "D1-R1-T1-R1",
            "read",
            {"cost": float("inf")},
        )
        assert verdict.level == "blocked"

    def test_negative_cost_blocked(self) -> None:
        """Negative cost must be blocked (not used to reduce accumulated spend)."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-neg-test",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=1000.0),
        )
        engine.set_role_envelope(role_env)

        verdict = engine.verify_action(
            "D1-R1-T1-R1",
            "read",
            {"cost": -100.0},
        )
        assert verdict.level == "blocked"
        assert "negative" in verdict.reason.lower()

    def test_empty_allowed_actions_blocks_all(self) -> None:
        """An envelope with empty allowed_actions must block all actions."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-empty-actions",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(allowed_actions=[]),
        )
        engine.set_role_envelope(role_env)

        # "read" is not in the empty allowed list -> blocked
        verdict = engine.verify_action("D1-R1-T1-R1", "read")
        assert verdict.level == "blocked"
        assert "not in the allowed actions" in verdict.reason.lower()

    def test_degenerate_zero_spend_envelope(self) -> None:
        """An envelope with $0 max_spend blocks any action with cost > 0."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-zero-spend",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=0.0, allowed_actions=["read"]),
        )
        engine.set_role_envelope(role_env)

        verdict = engine.verify_action(
            "D1-R1-T1-R1",
            "read",
            {"cost": 0.01},
        )
        assert verdict.level == "blocked"
        assert "exceeds financial limit" in verdict.reason.lower()


# ===========================================================================
# RT21-C: Store Bypass Attempts
# ===========================================================================


class TestStoreBypass:
    """Adversarial attempts to bypass store security."""

    def test_path_traversal_in_id_rejected(self) -> None:
        """Path traversal characters in IDs must be rejected by validate_id."""
        from pact.governance.stores.sqlite import _validate_id

        malicious_ids = [
            "../../etc/passwd",
            "../secret",
            "/etc/shadow",
            "id with spaces",
            "id;DROP TABLE pact_orgs;",
            "id\x00null",
            "",
            "id/slash",
            "id\\backslash",
            "id..double_dot",
        ]
        for bad_id in malicious_ids:
            with pytest.raises(ValueError, match="Invalid ID"):
                _validate_id(bad_id)

    def test_sql_injection_in_address_fields(self) -> None:
        """SQL injection through address fields must be prevented by parameterized queries."""
        from pact.governance.stores.sqlite import SqliteOrgStore

        store = SqliteOrgStore(":memory:")
        # Attempt SQL injection via org_id
        with pytest.raises(ValueError):
            store.load_org("'; DROP TABLE pact_orgs; --")

    def test_concurrent_writes_to_same_key(self) -> None:
        """Concurrent writes to the same clearance key must not corrupt state."""
        import threading

        store = MemoryClearanceStore()
        errors: list[str] = []

        def write_clearance(level: ConfidentialityLevel, thread_id: int) -> None:
            try:
                clr = RoleClearance(
                    role_address="D1-R1",
                    max_clearance=level,
                    granted_by_role_address="R1",
                    vetting_status=VettingStatus.ACTIVE,
                )
                for _ in range(100):
                    store.grant_clearance(clr)
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [
            threading.Thread(
                target=write_clearance,
                args=(ConfidentialityLevel.CONFIDENTIAL, 0),
            ),
            threading.Thread(
                target=write_clearance,
                args=(ConfidentialityLevel.SECRET, 1),
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No corruption errors
        assert not errors, f"Concurrent write errors: {errors}"
        # Final state should be one of the two levels (last writer wins)
        result = store.get_clearance("D1-R1")
        assert result is not None
        assert result.max_clearance in (
            ConfidentialityLevel.CONFIDENTIAL,
            ConfidentialityLevel.SECRET,
        )

    def test_exceed_max_store_size_evicts_oldest(self) -> None:
        """Adding entries beyond MAX_STORE_SIZE must evict oldest entries."""
        store = MemoryClearanceStore()
        # Fill store to capacity + 1
        num_entries = MAX_STORE_SIZE + 10
        for i in range(num_entries):
            clr = RoleClearance(
                role_address=f"D{i}-R1",
                max_clearance=ConfidentialityLevel.PUBLIC,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            )
            store.grant_clearance(clr)

        # Oldest entries should have been evicted
        assert store.get_clearance("D0-R1") is None
        assert store.get_clearance("D1-R1") is None
        # Newest entries should still be present
        assert store.get_clearance(f"D{num_entries - 1}-R1") is not None


# ===========================================================================
# RT21-D: Agent Bypass Attempts
# ===========================================================================


class TestAgentBypass:
    """Adversarial attempts to bypass agent governance controls."""

    def test_governance_context_is_frozen(self) -> None:
        """GovernanceContext fields must reject mutation attempts."""
        engine = _make_engine()
        agent = PactGovernedAgent(
            engine=engine,
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
        )
        ctx = agent.context

        with pytest.raises(AttributeError):
            ctx.posture = TrustPostureLevel.DELEGATED  # type: ignore[misc]
        with pytest.raises(AttributeError):
            ctx.role_address = "D99-R99"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            ctx.org_id = "hacked"  # type: ignore[misc]

    def test_agent_cannot_access_engine(self) -> None:
        """The agent context must NOT expose the governance engine."""
        engine = _make_engine()
        agent = PactGovernedAgent(
            engine=engine,
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
        )
        ctx = agent.context

        # GovernanceContext must not have an 'engine' attribute
        assert not hasattr(ctx, "engine")
        assert not hasattr(ctx, "_engine")

        # The agent itself has _engine (private), but ctx does not
        # Verify ctx class has no engine-related fields
        field_names = {f.name for f in ctx.__dataclass_fields__.values()}
        assert "engine" not in field_names
        assert "_engine" not in field_names

    def test_unregistered_tool_blocked(self) -> None:
        """Calling an unregistered tool must raise GovernanceBlockedError (default-deny)."""
        engine = _make_engine()
        agent = PactGovernedAgent(
            engine=engine,
            role_address="D1-R1",
            posture=TrustPostureLevel.SUPERVISED,
        )
        # Do NOT register any tools

        with pytest.raises(GovernanceBlockedError) as exc_info:
            agent.execute_tool("unregistered_tool", _tool_fn=lambda: "hacked")

        assert "not governance-registered" in str(exc_info.value)

    def test_nan_cost_in_tool_call_blocked(self) -> None:
        """A tool registered with NaN cost must not bypass financial checks."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-agent-nan",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=100.0, allowed_actions=["compute"]),
        )
        engine.set_role_envelope(role_env)

        agent = PactGovernedAgent(
            engine=engine,
            role_address="D1-R1-T1-R1",
            posture=TrustPostureLevel.SUPERVISED,
        )
        agent.register_tool("compute", cost=float("nan"))

        with pytest.raises(GovernanceBlockedError):
            agent.execute_tool("compute", _tool_fn=lambda: "result")


# ===========================================================================
# RT21-E: API Bypass Attempts
# ===========================================================================


class TestAPIBypass:
    """Adversarial attempts to bypass API authentication and authorization."""

    def test_unauthenticated_endpoint_access(self) -> None:
        """Unauthenticated requests must be rejected when API token is set."""
        from pact.governance.api.auth import GovernanceAuth

        auth = GovernanceAuth(api_token="super-secret-token")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token(None)  # No token
        assert exc_info.value.status_code == 401

    def test_wrong_token_rejected(self) -> None:
        """A wrong API token must be rejected."""
        from pact.governance.api.auth import GovernanceAuth

        auth = GovernanceAuth(api_token="correct-token")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("wrong-token")
        assert exc_info.value.status_code == 401

    def test_timing_safe_comparison(self) -> None:
        """Token comparison must use constant-time hmac.compare_digest (not ==)."""
        import inspect

        from pact.governance.api.auth import GovernanceAuth

        source = inspect.getsource(GovernanceAuth.verify_token)
        assert "compare_digest" in source, (
            "GovernanceAuth.verify_token must use hmac.compare_digest for "
            "constant-time token comparison to prevent timing attacks"
        )

    def test_dev_mode_no_token_allows_anonymous(self) -> None:
        """Dev mode (no token configured) returns 'anonymous', not error."""
        from pact.governance.api.auth import GovernanceAuth

        auth = GovernanceAuth(api_token=None)  # Explicit None -> dev mode
        identity = auth.verify_token(None)
        assert identity == "anonymous"


# ===========================================================================
# RT21-F: TOCTOU Defense
# ===========================================================================


class TestTOCTOUDefense:
    """Test Time-of-Check-to-Time-of-Use defense mechanisms."""

    def test_envelope_version_in_verdict(self) -> None:
        """verify_action() must include envelope_version hash in the verdict."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-toctou",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=1000.0),
        )
        engine.set_role_envelope(role_env)

        verdict = engine.verify_action("D1-R1-T1-R1", "read")
        assert verdict.envelope_version != ""
        assert len(verdict.envelope_version) == 64  # SHA-256 hex digest

    def test_envelope_version_changes_on_update(self) -> None:
        """Updating an envelope must change the version hash."""
        engine = _make_engine()
        role_env_v1 = RoleEnvelope(
            id="re-v1",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=1000.0),
        )
        engine.set_role_envelope(role_env_v1)
        verdict_v1 = engine.verify_action("D1-R1-T1-R1", "read")

        # Update the envelope
        role_env_v2 = RoleEnvelope(
            id="re-v2",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=500.0),
        )
        engine.set_role_envelope(role_env_v2)
        verdict_v2 = engine.verify_action("D1-R1-T1-R1", "read")

        # The version hash must be different because the envelope changed
        assert verdict_v1.envelope_version != verdict_v2.envelope_version

    def test_envelope_version_in_audit_details(self) -> None:
        """envelope_version must appear in the audit_details of the verdict."""
        engine = _make_engine()
        role_env = RoleEnvelope(
            id="re-audit-ver",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(max_spend=1000.0),
        )
        engine.set_role_envelope(role_env)

        verdict = engine.verify_action("D1-R1-T1-R1", "read")
        assert "envelope_version" in verdict.audit_details
        assert verdict.audit_details["envelope_version"] == verdict.envelope_version

    def test_access_decision_valid_until_from_ksp(self) -> None:
        """AccessDecision via KSP must include valid_until from KSP expiry."""
        org = _make_compiled_org()
        expires = datetime.now(UTC) + timedelta(hours=2)
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        ksp = KnowledgeSharePolicy(
            id="timed-ksp",
            source_unit_address="D2",
            target_unit_address="D1",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            created_by_role_address="D2-R1",
            expires_at=expires,
        )
        item = KnowledgeItem(
            item_id="fin-doc",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D2",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=org,
            clearances=clearances,
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is True
        assert decision.valid_until is not None
        assert decision.valid_until == expires

    def test_access_decision_valid_until_from_bridge(self) -> None:
        """AccessDecision via bridge must include valid_until from bridge expiry."""
        org = _make_compiled_org()
        expires = datetime.now(UTC) + timedelta(days=1)
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        bridge = PactBridge(
            id="timed-bridge",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            expires_at=expires,
        )
        item = KnowledgeItem(
            item_id="fin-doc",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D2",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=org,
            clearances=clearances,
            ksps=[],
            bridges=[bridge],
        )
        assert decision.allowed is True
        assert decision.valid_until is not None
        assert decision.valid_until == expires

    def test_structural_access_has_no_valid_until(self) -> None:
        """Structural access (same-unit, downward) has no expiry."""
        org = _make_compiled_org()
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        }
        item = KnowledgeItem(
            item_id="eng-doc",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is True
        assert decision.valid_until is None  # Structural access, no expiry


# ===========================================================================
# RT21-G: Multi-Level VERIFY
# ===========================================================================


class TestMultiLevelVerify:
    """Test multi-level VERIFY: ancestor envelopes block leaf-allowed actions."""

    def test_action_allowed_at_leaf_blocked_by_ancestor(self) -> None:
        """An action allowed at the leaf but blocked by an ancestor's envelope must be BLOCKED."""
        engine = _make_engine()

        # VP Eng (D1-R1) blocks "deploy"
        vp_env = RoleEnvelope(
            id="re-vp",
            defining_role_address="R1",  # Board sets VP envelope
            target_role_address="D1-R1",
            envelope=_make_envelope(
                env_id="vp-envelope",
                allowed_actions=["read", "write"],
                blocked_actions=["deploy"],
            ),
        )
        engine.set_role_envelope(vp_env)

        # Backend Lead (D1-R1-T1-R1) allows "deploy" -- but ancestor blocks it
        lead_env = RoleEnvelope(
            id="re-lead",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(
                env_id="lead-envelope",
                allowed_actions=["read", "write", "deploy"],
            ),
        )
        engine.set_role_envelope(lead_env)

        verdict = engine.verify_action("D1-R1-T1-R1", "deploy")
        # The effective envelope intersection already handles this case
        # because intersect_envelopes unions blocked_actions.
        # Multi-level verify provides an additional safety check.
        assert verdict.level == "blocked"

    def test_action_allowed_at_all_levels(self) -> None:
        """An action allowed at all levels must be auto_approved."""
        engine = _make_engine()

        vp_env = RoleEnvelope(
            id="re-vp-ok",
            defining_role_address="R1",
            target_role_address="D1-R1",
            envelope=_make_envelope(
                env_id="vp-ok-envelope",
                allowed_actions=["read", "write"],
            ),
        )
        engine.set_role_envelope(vp_env)

        lead_env = RoleEnvelope(
            id="re-lead-ok",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(
                env_id="lead-ok-envelope",
                allowed_actions=["read", "write"],
            ),
        )
        engine.set_role_envelope(lead_env)

        verdict = engine.verify_action("D1-R1-T1-R1", "read")
        assert verdict.level == "auto_approved"

    def test_ancestor_cost_limit_blocks_expensive_action(self) -> None:
        """If ancestor has $100 limit but leaf has $1000, action at $500 must be BLOCKED."""
        engine = _make_engine()

        # VP Eng: max_spend = $100
        vp_env = RoleEnvelope(
            id="re-vp-cheap",
            defining_role_address="R1",
            target_role_address="D1-R1",
            envelope=_make_envelope(
                env_id="vp-cheap",
                max_spend=100.0,
                allowed_actions=["read", "write", "compute"],
            ),
        )
        engine.set_role_envelope(vp_env)

        # Backend Lead: max_spend = $1000 (but this violates tightening,
        # and the effective envelope will have min = $100)
        lead_env = RoleEnvelope(
            id="re-lead-expensive",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-T1-R1",
            envelope=_make_envelope(
                env_id="lead-expensive",
                max_spend=1000.0,
                allowed_actions=["read", "write", "compute"],
            ),
        )
        engine.set_role_envelope(lead_env)

        # $500 action: effective envelope from intersection has max_spend $100
        verdict = engine.verify_action(
            "D1-R1-T1-R1",
            "compute",
            {"cost": 500.0},
        )
        assert verdict.level == "blocked"
        assert "exceeds financial limit" in verdict.reason.lower()


# ===========================================================================
# RT21-H: Audit Chain Integrity
# ===========================================================================


class TestAuditChainIntegrity:
    """Verify audit chain hash integrity for governance mutations."""

    def test_mutations_create_audit_entries(self) -> None:
        """Governance mutations (grant_clearance, create_bridge, etc.) must create audit entries."""
        engine = GovernanceEngine(
            _make_compiled_org(),
            store_backend="sqlite",
            store_url=":memory:",
        )

        clr = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance("D1-R1", clr)

        bridge = PactBridge(
            id="audit-bridge",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
        )
        engine.create_bridge(bridge)

        # Verify integrity
        is_valid, error = engine.verify_audit_integrity()
        assert is_valid is True, f"Audit chain integrity failed: {error}"

    def test_tampered_audit_entry_detected(self) -> None:
        """If an audit entry is tampered with, verify_audit_integrity detects it."""
        engine = GovernanceEngine(
            _make_compiled_org(),
            store_backend="sqlite",
            store_url=":memory:",
        )

        clr = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance("D1-R1", clr)

        # Tamper with the audit log
        audit_log = engine._sqlite_audit_log
        conn = audit_log._get_connection()
        conn.execute(
            "UPDATE pact_audit_log SET details_json = ? WHERE id = 1",
            ('{"tampered": true}',),
        )
        conn.commit()

        is_valid, error = engine.verify_audit_integrity()
        assert is_valid is False
        assert error is not None
        assert "tamper" in error.lower() or "mismatch" in error.lower()


# ===========================================================================
# RT21-I: Fail-Closed Behavior
# ===========================================================================


class TestFailClosed:
    """Verify fail-closed behavior on all error paths."""

    def test_verify_action_on_exception_returns_blocked(self) -> None:
        """verify_action must return BLOCKED on internal exception (fail-closed)."""
        engine = _make_engine()

        # Create a situation that will cause an internal error by using
        # a broken envelope store
        original_store = engine._envelope_store

        class BrokenStore:
            def get_ancestor_envelopes(self, role_address: str) -> dict:
                raise RuntimeError("Store is down")

            def get_active_task_envelope(self, role_address: str, task_id: str) -> None:
                raise RuntimeError("Store is down")

            def get_role_envelope(self, target_role_address: str) -> None:
                return None

            def save_role_envelope(self, envelope: Any) -> None:
                pass

            def save_task_envelope(self, envelope: Any) -> None:
                pass

        engine._envelope_store = BrokenStore()  # type: ignore[assignment]

        verdict = engine.verify_action("D1-R1", "read")
        assert verdict.level == "blocked"
        assert "internal error" in verdict.reason.lower()

        # Restore
        engine._envelope_store = original_store

    def test_check_access_on_exception_returns_deny(self) -> None:
        """check_access must return DENY on internal exception (fail-closed)."""
        engine = _make_engine()

        # Inject broken clearance store
        original_store = engine._clearance_store

        class BrokenClearanceStore:
            def get_clearance(self, role_address: str) -> None:
                raise RuntimeError("Store is down")

            def grant_clearance(self, clearance: Any) -> None:
                pass

            def revoke_clearance(self, role_address: str) -> None:
                pass

        engine._clearance_store = BrokenClearanceStore()  # type: ignore[assignment]

        item = KnowledgeItem(
            item_id="test-doc",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1",
        )
        decision = engine.check_access(
            "D1-R1",
            item,
            TrustPostureLevel.SUPERVISED,
        )
        assert decision.allowed is False
        assert "internal error" in decision.reason.lower()

        engine._clearance_store = original_store


# ===========================================================================
# RT21-J: Snapshot Versioning Correctness
# ===========================================================================


class TestSnapshotVersioning:
    """Verify EffectiveEnvelopeSnapshot version hashing is correct."""

    def test_same_inputs_produce_same_hash(self) -> None:
        """The same set of envelopes must produce the same version hash."""
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-1",
                defining_role_address="R1",
                target_role_address="D1-R1",
                envelope=_make_envelope(),
                version=1,
            ),
        }

        snap1 = compute_effective_envelope_with_version("D1-R1", role_envs)
        snap2 = compute_effective_envelope_with_version("D1-R1", role_envs)

        assert snap1.version_hash == snap2.version_hash
        assert snap1.version_hash != ""

    def test_different_version_produces_different_hash(self) -> None:
        """Changing an envelope version must produce a different version hash."""
        role_envs_v1 = {
            "D1-R1": RoleEnvelope(
                id="re-1",
                defining_role_address="R1",
                target_role_address="D1-R1",
                envelope=_make_envelope(),
                version=1,
            ),
        }
        role_envs_v2 = {
            "D1-R1": RoleEnvelope(
                id="re-1",
                defining_role_address="R1",
                target_role_address="D1-R1",
                envelope=_make_envelope(),
                version=2,
            ),
        }

        snap1 = compute_effective_envelope_with_version("D1-R1", role_envs_v1)
        snap2 = compute_effective_envelope_with_version("D1-R1", role_envs_v2)

        assert snap1.version_hash != snap2.version_hash

    def test_no_envelopes_produces_empty_hash(self) -> None:
        """No contributing envelopes should produce an empty version hash."""
        snap = compute_effective_envelope_with_version("D1-R1", {})
        assert snap.version_hash == ""
        assert snap.envelope is None
        assert snap.contributor_versions == {}

    def test_contributor_versions_tracked(self) -> None:
        """EffectiveEnvelopeSnapshot must track which envelopes contributed."""
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-1",
                defining_role_address="R1",
                target_role_address="D1-R1",
                envelope=_make_envelope(),
                version=3,
            ),
        }

        snap = compute_effective_envelope_with_version("D1-R1", role_envs)
        assert "D1-R1" in snap.contributor_versions
        assert snap.contributor_versions["D1-R1"] == 3
