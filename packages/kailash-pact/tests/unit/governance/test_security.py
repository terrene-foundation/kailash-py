# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""M6 security invariants -- 5 invariants verifying access enforcement hardening.

Invariant 1: Pre-retrieval gate (can_access has no store/db references)
Invariant 2: KSP absence = default deny (BLOCKED -> ALLOWED -> BLOCKED lifecycle)
Invariant 3: Compartment enforcement (SECRET enforced, TOP_SECRET enforced, CONFIDENTIAL NOT)
Invariant 4: NaN/Inf (all clearance order values are finite ints, monotonic ordering)
Invariant 5: Address validation (empty, whitespace, path traversal, SQL injection, null bytes)
"""

from __future__ import annotations

import inspect
import math

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    DepartmentConfig,
    TeamConfig,
    TrustPostureLevel,
)
from pact.build.org.builder import OrgDefinition
from pact.governance import access as access_module
from pact.governance.access import (
    KnowledgeSharePolicy,
    can_access,
)
from pact.governance.addressing import Address, AddressError, AddressSegment
from pact.governance.clearance import (
    RoleClearance,
    _CLEARANCE_ORDER,
)
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org
from pact.governance.knowledge import KnowledgeItem


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_org() -> CompiledOrg:
    """Simple org: D1 with T1."""
    roles = [
        RoleDefinition(
            role_id="r-head",
            name="Head",
            reports_to_role_id=None,
            is_primary_for_unit="d-main",
        ),
        RoleDefinition(
            role_id="r-lead",
            name="Lead",
            reports_to_role_id="r-head",
            is_primary_for_unit="t-alpha",
        ),
    ]
    departments = [DepartmentConfig(department_id="d-main", name="Main")]
    teams = [TeamConfig(id="t-alpha", name="Alpha", workspace="ws")]
    org = OrgDefinition(
        org_id="sec-test",
        name="Security Test Org",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


# ===========================================================================
# Invariant 1: Pre-retrieval gate
# ===========================================================================


class TestPreRetrievalGate:
    """can_access() is a pure function with no store/database references.

    The function signature takes all data as parameters. The source module
    must not import or reference any database, store, or persistence layer.
    """

    def test_can_access_signature_takes_all_data_as_params(self) -> None:
        """can_access() signature must include all 7 required parameters."""
        sig = inspect.signature(can_access)
        param_names = list(sig.parameters.keys())
        required = [
            "role_address",
            "knowledge_item",
            "posture",
            "compiled_org",
            "clearances",
            "ksps",
            "bridges",
        ]
        for name in required:
            assert name in param_names, (
                f"can_access() missing required parameter '{name}'. "
                f"All access data must be passed explicitly (pre-retrieval gate)."
            )

    def test_access_module_has_no_store_imports(self) -> None:
        """The access module must not import any store/db/persistence modules."""
        source = inspect.getsource(access_module)
        forbidden_patterns = [
            "import sqlite",
            "import asyncpg",
            "import sqlalchemy",
            "import aiosqlite",
            "from pact.governance.stores",
            "from pact.trust.store",
            ".store import",
            "Store(",
            "database",
            "cursor",
            "connection",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"access module contains forbidden store reference: '{pattern}'. "
                f"can_access() must be a pure function with no database dependencies."
            )


# ===========================================================================
# Invariant 2: KSP absence = default deny
# ===========================================================================


class TestKSPAbsenceDefaultDeny:
    """No KSP -> BLOCKED, add KSP -> ALLOWED, deactivate KSP -> BLOCKED."""

    def test_no_ksp_blocked(self, simple_org: CompiledOrg) -> None:
        """Without any KSP, cross-unit access is denied."""
        # Need a two-dept org for this
        roles = [
            RoleDefinition(
                role_id="r-a", name="A", reports_to_role_id=None, is_primary_for_unit="d-a"
            ),
            RoleDefinition(
                role_id="r-b", name="B", reports_to_role_id=None, is_primary_for_unit="d-b"
            ),
        ]
        depts = [
            DepartmentConfig(department_id="d-a", name="A"),
            DepartmentConfig(department_id="d-b", name="B"),
        ]
        org = OrgDefinition(org_id="deny-test", name="Deny", departments=depts, roles=roles)
        compiled = compile_org(org)
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="a-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=compiled,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False, "No KSP should mean BLOCKED (default deny)"

    def test_add_ksp_allowed(self, simple_org: CompiledOrg) -> None:
        """With active KSP, cross-unit access is allowed."""
        roles = [
            RoleDefinition(
                role_id="r-a", name="A", reports_to_role_id=None, is_primary_for_unit="d-a"
            ),
            RoleDefinition(
                role_id="r-b", name="B", reports_to_role_id=None, is_primary_for_unit="d-b"
            ),
        ]
        depts = [
            DepartmentConfig(department_id="d-a", name="A"),
            DepartmentConfig(department_id="d-b", name="B"),
        ]
        org = OrgDefinition(org_id="allow-test", name="Allow", departments=depts, roles=roles)
        compiled = compile_org(org)
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="a-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        ksp = KnowledgeSharePolicy(
            id="ksp-a-to-b",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            active=True,
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=compiled,
            clearances=clearances,
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is True, "Active KSP should grant access"

    def test_deactivate_ksp_blocked_again(self, simple_org: CompiledOrg) -> None:
        """Deactivated KSP no longer grants access."""
        roles = [
            RoleDefinition(
                role_id="r-a", name="A", reports_to_role_id=None, is_primary_for_unit="d-a"
            ),
            RoleDefinition(
                role_id="r-b", name="B", reports_to_role_id=None, is_primary_for_unit="d-b"
            ),
        ]
        depts = [
            DepartmentConfig(department_id="d-a", name="A"),
            DepartmentConfig(department_id="d-b", name="B"),
        ]
        org = OrgDefinition(org_id="reblock-test", name="Reblock", departments=depts, roles=roles)
        compiled = compile_org(org)
        clearances = {
            "D2-R1": RoleClearance(
                role_address="D2-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            ),
        }
        item = KnowledgeItem(
            item_id="a-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1",
        )
        ksp = KnowledgeSharePolicy(
            id="ksp-a-to-b",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            active=False,  # Deactivated
        )
        decision = can_access(
            role_address="D2-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=compiled,
            clearances=clearances,
            ksps=[ksp],
            bridges=[],
        )
        assert decision.allowed is False, "Deactivated KSP should mean BLOCKED again"


# ===========================================================================
# Invariant 3: Compartment enforcement
# ===========================================================================


class TestCompartmentEnforcement:
    """SECRET enforced, TOP_SECRET enforced, CONFIDENTIAL NOT enforced.

    Known gap (by design per thesis): compartment enforcement only kicks in
    at SECRET (order=3) and above. CONFIDENTIAL items with compartments do
    NOT enforce compartment checks -- this is intentional per the PACT spec
    threshold at SECRET+.
    """

    def test_secret_compartment_enforced(self, simple_org: CompiledOrg) -> None:
        """SECRET items with compartments enforce the compartment check."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.SECRET,
                compartments=frozenset(),  # No compartments
                nda_signed=True,
            ),
        }
        item = KnowledgeItem(
            item_id="secret-comped",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1",
            compartments=frozenset({"alpha"}),
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 3

    def test_top_secret_compartment_enforced(self, simple_org: CompiledOrg) -> None:
        """TOP_SECRET items with compartments enforce the compartment check."""
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.TOP_SECRET,
                compartments=frozenset(),  # No compartments
                nda_signed=True,
            ),
        }
        item = KnowledgeItem(
            item_id="ts-comped",
            classification=ConfidentialityLevel.TOP_SECRET,
            owning_unit_address="D1",
            compartments=frozenset({"omega"}),
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        assert decision.allowed is False
        assert decision.step_failed == 3

    def test_confidential_compartment_not_enforced(self, simple_org: CompiledOrg) -> None:
        """CONFIDENTIAL items with compartments do NOT enforce compartment check.

        DOCUMENTED GAP: Compartment enforcement threshold is SECRET+ (order >= 3).
        CONFIDENTIAL (order=2) compartmented items are accessible without matching
        compartments. This is by design per the PACT thesis -- compartment enforcement
        at lower levels would impose excessive operational overhead for data that
        does not require need-to-know restrictions.
        """
        clearances = {
            "D1-R1": RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                compartments=frozenset(),  # No compartments
            ),
        }
        item = KnowledgeItem(
            item_id="conf-comped",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address="D1",
            compartments=frozenset({"some-compartment"}),
        )
        decision = can_access(
            role_address="D1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=simple_org,
            clearances=clearances,
            ksps=[],
            bridges=[],
        )
        # This PASSES -- compartments not enforced at CONFIDENTIAL level
        assert decision.allowed is True, (
            "CONFIDENTIAL items should NOT enforce compartment checks (threshold is SECRET+). "
            "This is a documented design choice, not a bug."
        )


# ===========================================================================
# Invariant 4: NaN/Inf protection for clearance ordering
# ===========================================================================


class TestClearanceOrderIntegrity:
    """All clearance order values must be finite ints with monotonic ordering."""

    def test_all_values_are_finite_ints(self) -> None:
        """Every value in _CLEARANCE_ORDER must be a finite integer."""
        for level, order_val in _CLEARANCE_ORDER.items():
            assert isinstance(order_val, int), (
                f"_CLEARANCE_ORDER[{level.value}] = {order_val!r} is {type(order_val).__name__}, "
                f"expected int. Non-integer values could bypass NaN comparison checks."
            )
            assert math.isfinite(order_val), (
                f"_CLEARANCE_ORDER[{level.value}] = {order_val} is not finite. "
                f"NaN/Inf values bypass numeric comparisons."
            )

    def test_monotonic_ordering(self) -> None:
        """Clearance levels must be strictly monotonically ordered."""
        expected_order = [
            ConfidentialityLevel.PUBLIC,
            ConfidentialityLevel.RESTRICTED,
            ConfidentialityLevel.CONFIDENTIAL,
            ConfidentialityLevel.SECRET,
            ConfidentialityLevel.TOP_SECRET,
        ]
        for i in range(len(expected_order) - 1):
            lower = expected_order[i]
            higher = expected_order[i + 1]
            assert _CLEARANCE_ORDER[lower] < _CLEARANCE_ORDER[higher], (
                f"Clearance ordering violation: {lower.value} (order={_CLEARANCE_ORDER[lower]}) "
                f"should be strictly less than {higher.value} (order={_CLEARANCE_ORDER[higher]})"
            )

    def test_all_levels_have_order_values(self) -> None:
        """Every ConfidentialityLevel must have an entry in _CLEARANCE_ORDER."""
        for level in ConfidentialityLevel:
            assert level in _CLEARANCE_ORDER, (
                f"ConfidentialityLevel.{level.value} is missing from _CLEARANCE_ORDER. "
                f"Missing entries would cause KeyError in access decisions."
            )

    def test_no_duplicate_order_values(self) -> None:
        """No two levels may share the same numeric order value."""
        values = list(_CLEARANCE_ORDER.values())
        assert len(values) == len(set(values)), (
            f"Duplicate values in _CLEARANCE_ORDER: {values}. "
            f"Duplicates would make different levels indistinguishable."
        )


# ===========================================================================
# Invariant 5: Address validation
# ===========================================================================


class TestAddressValidation:
    """Address parsing must reject malicious/malformed inputs."""

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(AddressError):
            Address.parse("")

    def test_whitespace_only_rejected(self) -> None:
        with pytest.raises(AddressError):
            Address.parse("   ")

    def test_path_traversal_rejected(self) -> None:
        """Path traversal attempts must not parse as valid addresses."""
        with pytest.raises(AddressError):
            Address.parse("../../../etc/passwd")

    def test_sql_injection_rejected(self) -> None:
        """SQL injection attempts must not parse as valid addresses."""
        with pytest.raises(AddressError):
            Address.parse("D1'; DROP TABLE orgs; --")

    def test_null_bytes_rejected(self) -> None:
        """Null bytes must not parse as valid addresses."""
        with pytest.raises(AddressError):
            Address.parse("D1\x00R1")

    def test_very_long_address_does_not_crash(self) -> None:
        """Very long addresses should not cause crashes (OOM, stack overflow)."""
        # A very long but structurally valid-ish string
        # 1000 segments of D1-R1
        long_addr = "-".join(["D1", "R1"] * 500)
        # This should either parse or raise AddressError, but never crash
        try:
            result = Address.parse(long_addr)
            # If it parses, it should have 1000 segments
            assert len(result.segments) == 1000
        except AddressError:
            pass  # Acceptable to reject very long addresses

    def test_negative_sequence_rejected(self) -> None:
        """Negative sequence numbers must be rejected."""
        with pytest.raises(AddressError):
            AddressSegment.parse("D-1")

    def test_zero_sequence_rejected(self) -> None:
        """Zero sequence numbers must be rejected (sequences are 1-based)."""
        with pytest.raises(AddressError):
            AddressSegment.parse("D0")
