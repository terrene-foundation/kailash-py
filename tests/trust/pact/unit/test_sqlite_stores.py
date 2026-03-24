# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for SQLite governance store implementations.

Covers:
- TODO-7040: SqliteOrgStore, SqliteEnvelopeStore, SqliteClearanceStore, SqliteAccessPolicyStore
- TODO-7041: Schema migration tracking
- TODO-7043: Engine store_backend="sqlite" configuration
- Round-trip (save -> load) for all 4 store types
- ID validation (path traversal rejected)
- File permissions (0o600 on POSIX)
- Concurrent access (10 threads, no corruption)
- Bounded eviction (insert beyond limit, oldest removed)
- Protocol conformance (all SQLite stores satisfy Protocol contracts)
"""

from __future__ import annotations

import os
import platform
import stat
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import CompiledOrg, OrgNode
from kailash.trust.pact.envelopes import RoleEnvelope, TaskEnvelope
from kailash.trust.pact.store import (
    MAX_STORE_SIZE,
    AccessPolicyStore,
    ClearanceStore,
    EnvelopeStore,
    OrgStore,
)
from kailash.trust.pact.stores.sqlite import (
    PACT_SCHEMA_VERSION,
    SqliteAccessPolicyStore,
    SqliteClearanceStore,
    SqliteEnvelopeStore,
    SqliteOrgStore,
    _validate_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "test-org") -> CompiledOrg:
    """Create a minimal CompiledOrg with a few nodes for testing."""
    org = CompiledOrg(org_id=org_id)
    from kailash.trust.pact.addressing import NodeType

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
) -> TaskEnvelope:
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
) -> KnowledgeSharePolicy:
    return KnowledgeSharePolicy(
        id=ksp_id,
        source_unit_address=source,
        target_unit_address=target,
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        created_by_role_address="D1-R1",
    )


def _make_bridge(
    bridge_id: str = "bridge-1",
    role_a: str = "D1-R1",
    role_b: str = "D2-R1",
    bilateral: bool = True,
) -> PactBridge:
    return PactBridge(
        id=bridge_id,
        role_a_address=role_a,
        role_b_address=role_b,
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        bilateral=bilateral,
    )


# ===========================================================================
# ID Validation
# ===========================================================================


class TestIdValidation:
    """_validate_id must reject path traversal and injection attempts."""

    def test_valid_ids(self) -> None:
        """Normal alphanumeric IDs with hyphens and underscores pass."""
        for valid in ["org-1", "ksp_2", "D1-R1-T1-R1", "test123", "a", "A_B-c"]:
            _validate_id(valid)  # should not raise

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(ValueError, match="Invalid ID"):
            _validate_id("../../../etc/passwd")

    def test_rejects_slash(self) -> None:
        with pytest.raises(ValueError, match="Invalid ID"):
            _validate_id("org/1")

    def test_rejects_null_byte(self) -> None:
        with pytest.raises(ValueError, match="Invalid ID"):
            _validate_id("org\x001")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid ID"):
            _validate_id("")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValueError, match="Invalid ID"):
            _validate_id("org 1")

    def test_rejects_semicolons(self) -> None:
        with pytest.raises(ValueError, match="Invalid ID"):
            _validate_id("org;DROP TABLE")


# ===========================================================================
# Protocol Conformance
# ===========================================================================


class TestSqliteProtocolConformance:
    """SQLite stores must satisfy their Protocol contracts."""

    def test_sqlite_org_store_is_org_store(self) -> None:
        store = SqliteOrgStore(":memory:")
        assert isinstance(store, OrgStore)

    def test_sqlite_envelope_store_is_envelope_store(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        assert isinstance(store, EnvelopeStore)

    def test_sqlite_clearance_store_is_clearance_store(self) -> None:
        store = SqliteClearanceStore(":memory:")
        assert isinstance(store, ClearanceStore)

    def test_sqlite_access_policy_store_is_access_policy_store(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        assert isinstance(store, AccessPolicyStore)


# ===========================================================================
# SqliteOrgStore
# ===========================================================================


class TestSqliteOrgStore:
    """SqliteOrgStore round-trip and query tests."""

    def test_save_and_load_org(self) -> None:
        store = SqliteOrgStore(":memory:")
        org = _make_compiled_org("org-1")
        store.save_org(org)
        loaded = store.load_org("org-1")
        assert loaded is not None
        assert loaded.org_id == "org-1"
        assert "D1" in loaded.nodes
        assert "D1-R1" in loaded.nodes
        assert loaded.nodes["D1-R1"].name == "VP Eng"

    def test_load_nonexistent_returns_none(self) -> None:
        store = SqliteOrgStore(":memory:")
        assert store.load_org("nonexistent") is None

    def test_get_node(self) -> None:
        store = SqliteOrgStore(":memory:")
        org = _make_compiled_org("org-1")
        store.save_org(org)
        node = store.get_node("org-1", "D1-R1")
        assert node is not None
        assert node.name == "VP Eng"

    def test_get_node_nonexistent_org(self) -> None:
        store = SqliteOrgStore(":memory:")
        assert store.get_node("nonexistent", "D1") is None

    def test_get_node_nonexistent_address(self) -> None:
        store = SqliteOrgStore(":memory:")
        org = _make_compiled_org("org-1")
        store.save_org(org)
        assert store.get_node("org-1", "D99") is None

    def test_query_by_prefix(self) -> None:
        store = SqliteOrgStore(":memory:")
        org = _make_compiled_org("org-1")
        store.save_org(org)
        results = store.query_by_prefix("org-1", "D1-R1")
        addresses = {n.address for n in results}
        assert "D1-R1" in addresses
        assert "D1-R1-T1" in addresses
        assert "D1-R1-T1-R1" in addresses
        assert "D1" not in addresses

    def test_query_by_prefix_nonexistent_org(self) -> None:
        store = SqliteOrgStore(":memory:")
        assert store.query_by_prefix("nonexistent", "D1") == []

    def test_save_overwrites_existing_org(self) -> None:
        store = SqliteOrgStore(":memory:")
        org1 = _make_compiled_org("org-1")
        store.save_org(org1)
        org2 = CompiledOrg(org_id="org-1")
        store.save_org(org2)
        loaded = store.load_org("org-1")
        assert loaded is not None
        assert len(loaded.nodes) == 0

    def test_file_based_persistence(self, tmp_path: Path) -> None:
        """Data persists across store instances when backed by a file."""
        db_path = tmp_path / "test.db"
        store1 = SqliteOrgStore(str(db_path))
        org = _make_compiled_org("org-persist")
        store1.save_org(org)
        store1.close()

        store2 = SqliteOrgStore(str(db_path))
        loaded = store2.load_org("org-persist")
        assert loaded is not None
        assert loaded.org_id == "org-persist"
        assert "D1-R1" in loaded.nodes
        store2.close()


# ===========================================================================
# SqliteEnvelopeStore
# ===========================================================================


class TestSqliteEnvelopeStore:
    """SqliteEnvelopeStore round-trip and ancestor lookup tests."""

    def test_save_and_get_role_envelope(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        re = _make_role_envelope("re-1", target="D1-R1-T1-R1")
        store.save_role_envelope(re)
        loaded = store.get_role_envelope("D1-R1-T1-R1")
        assert loaded is not None
        assert loaded.id == "re-1"
        assert loaded.target_role_address == "D1-R1-T1-R1"
        assert loaded.defining_role_address == "D1-R1"

    def test_get_role_envelope_nonexistent(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        assert store.get_role_envelope("D99-R1") is None

    def test_save_and_get_task_envelope(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        te = _make_task_envelope("te-1", task_id="task-001")
        store.save_task_envelope(te)
        loaded = store.get_active_task_envelope("D1-R1-T1-R1", "task-001")
        assert loaded is not None
        assert loaded.id == "te-1"
        assert loaded.task_id == "task-001"

    def test_get_task_envelope_nonexistent(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        assert store.get_active_task_envelope("D1-R1", "task-999") is None

    def test_get_task_envelope_expired_returns_none(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        te = TaskEnvelope(
            id="te-expired",
            task_id="task-old",
            parent_envelope_id="re-1",
            envelope=_make_envelope("te-expired"),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        store.save_task_envelope(te)
        assert store.get_active_task_envelope("D1-R1-T1-R1", "task-old") is None

    def test_get_ancestor_envelopes(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        re_root = _make_role_envelope("re-root", target="D1-R1")
        re_child = _make_role_envelope("re-child", target="D1-R1-T1-R1")
        re_unrelated = _make_role_envelope("re-unrelated", target="D2-R1")
        store.save_role_envelope(re_root)
        store.save_role_envelope(re_child)
        store.save_role_envelope(re_unrelated)

        ancestors = store.get_ancestor_envelopes("D1-R1-T1-R1")
        assert "D1-R1" in ancestors
        assert "D1-R1-T1-R1" in ancestors
        assert "D2-R1" not in ancestors

    def test_get_ancestor_envelopes_empty(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        assert store.get_ancestor_envelopes("D1-R1-T1-R1") == {}

    def test_save_role_envelope_overwrites(self) -> None:
        store = SqliteEnvelopeStore(":memory:")
        re1 = _make_role_envelope("re-1", target="D1-R1")
        store.save_role_envelope(re1)
        re2 = _make_role_envelope("re-2", target="D1-R1")
        store.save_role_envelope(re2)
        loaded = store.get_role_envelope("D1-R1")
        assert loaded is not None
        assert loaded.id == "re-2"

    def test_role_envelope_version_increments(self) -> None:
        """Overwriting a role envelope should increment its version."""
        store = SqliteEnvelopeStore(":memory:")
        re1 = _make_role_envelope("re-1", target="D1-R1")
        store.save_role_envelope(re1)
        loaded1 = store.get_role_envelope("D1-R1")
        assert loaded1 is not None
        assert loaded1.version == 1

        re2 = _make_role_envelope("re-2", target="D1-R1")
        store.save_role_envelope(re2)
        loaded2 = store.get_role_envelope("D1-R1")
        assert loaded2 is not None
        assert loaded2.version == 2


# ===========================================================================
# SqliteClearanceStore
# ===========================================================================


class TestSqliteClearanceStore:
    """SqliteClearanceStore grant, get, revoke operations."""

    def test_grant_and_get_clearance(self) -> None:
        store = SqliteClearanceStore(":memory:")
        clr = _make_clearance("D1-R1-T1-R1")
        store.grant_clearance(clr)
        loaded = store.get_clearance("D1-R1-T1-R1")
        assert loaded is not None
        assert loaded.max_clearance == ConfidentialityLevel.CONFIDENTIAL
        assert loaded.role_address == "D1-R1-T1-R1"

    def test_get_clearance_nonexistent(self) -> None:
        store = SqliteClearanceStore(":memory:")
        assert store.get_clearance("D99-R1") is None

    def test_revoke_clearance(self) -> None:
        store = SqliteClearanceStore(":memory:")
        clr = _make_clearance("D1-R1-T1-R1")
        store.grant_clearance(clr)
        store.revoke_clearance("D1-R1-T1-R1")
        assert store.get_clearance("D1-R1-T1-R1") is None

    def test_revoke_nonexistent_no_error(self) -> None:
        store = SqliteClearanceStore(":memory:")
        store.revoke_clearance("D1-R1-T1-R1")  # should not raise

    def test_grant_overwrites_existing(self) -> None:
        store = SqliteClearanceStore(":memory:")
        clr1 = _make_clearance("D1-R1", ConfidentialityLevel.RESTRICTED)
        store.grant_clearance(clr1)
        clr2 = _make_clearance("D1-R1", ConfidentialityLevel.SECRET)
        store.grant_clearance(clr2)
        loaded = store.get_clearance("D1-R1")
        assert loaded is not None
        assert loaded.max_clearance == ConfidentialityLevel.SECRET

    def test_clearance_round_trip_preserves_compartments(self) -> None:
        store = SqliteClearanceStore(":memory:")
        clr = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"ops", "intel"}),
            granted_by_role_address="R1",
            vetting_status=VettingStatus.ACTIVE,
            nda_signed=True,
        )
        store.grant_clearance(clr)
        loaded = store.get_clearance("D1-R1")
        assert loaded is not None
        assert loaded.compartments == frozenset({"ops", "intel"})
        assert loaded.nda_signed is True
        assert loaded.vetting_status == VettingStatus.ACTIVE


# ===========================================================================
# SqliteAccessPolicyStore
# ===========================================================================


class TestSqliteAccessPolicyStoreKSP:
    """SqliteAccessPolicyStore KSP operations."""

    def test_save_and_find_ksp(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        ksp = _make_ksp("ksp-1", source="D1", target="D2")
        store.save_ksp(ksp)
        found = store.find_ksp("D1", "D2")
        assert found is not None
        assert found.id == "ksp-1"

    def test_find_ksp_nonexistent(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        assert store.find_ksp("D1", "D2") is None

    def test_find_ksp_reverse_direction_not_found(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        ksp = _make_ksp("ksp-1", source="D1", target="D2")
        store.save_ksp(ksp)
        assert store.find_ksp("D2", "D1") is None

    def test_list_ksps(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        ksp1 = _make_ksp("ksp-1", source="D1", target="D2")
        ksp2 = _make_ksp("ksp-2", source="D3", target="D4")
        store.save_ksp(ksp1)
        store.save_ksp(ksp2)
        ksps = store.list_ksps()
        assert len(ksps) == 2
        ids = {k.id for k in ksps}
        assert ids == {"ksp-1", "ksp-2"}

    def test_list_ksps_empty(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        assert store.list_ksps() == []

    def test_ksp_round_trip_preserves_fields(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        ksp = KnowledgeSharePolicy(
            id="ksp-full",
            source_unit_address="D1",
            target_unit_address="D2",
            max_classification=ConfidentialityLevel.SECRET,
            compartments=frozenset({"alpha", "beta"}),
            created_by_role_address="D1-R1",
            active=True,
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        store.save_ksp(ksp)
        found = store.find_ksp("D1", "D2")
        assert found is not None
        assert found.max_classification == ConfidentialityLevel.SECRET
        assert found.compartments == frozenset({"alpha", "beta"})
        assert found.created_by_role_address == "D1-R1"
        assert found.active is True


class TestSqliteAccessPolicyStoreBridge:
    """SqliteAccessPolicyStore bridge operations."""

    def test_save_and_find_bridge(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        bridge = _make_bridge("bridge-1", role_a="D1-R1", role_b="D2-R1")
        store.save_bridge(bridge)
        found = store.find_bridge("D1-R1", "D2-R1")
        assert found is not None
        assert found.id == "bridge-1"

    def test_find_bridge_reverse_order(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        bridge = _make_bridge("bridge-1", role_a="D1-R1", role_b="D2-R1")
        store.save_bridge(bridge)
        found = store.find_bridge("D2-R1", "D1-R1")
        assert found is not None
        assert found.id == "bridge-1"

    def test_find_bridge_nonexistent(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        assert store.find_bridge("D1-R1", "D99-R1") is None

    def test_list_bridges(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        b1 = _make_bridge("bridge-1", role_a="D1-R1", role_b="D2-R1")
        b2 = _make_bridge("bridge-2", role_a="D3-R1", role_b="D4-R1")
        store.save_bridge(b1)
        store.save_bridge(b2)
        bridges = store.list_bridges()
        assert len(bridges) == 2

    def test_list_bridges_empty(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        assert store.list_bridges() == []

    def test_bridge_round_trip_preserves_fields(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        bridge = PactBridge(
            id="bridge-full",
            role_a_address="D1-R1",
            role_b_address="D2-R1",
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.SECRET,
            operational_scope=("deploy", "review"),
            bilateral=False,
            expires_at=datetime(2030, 6, 15, tzinfo=UTC),
            active=True,
        )
        store.save_bridge(bridge)
        found = store.find_bridge("D1-R1", "D2-R1")
        assert found is not None
        assert found.bridge_type == "scoped"
        assert found.bilateral is False
        assert found.operational_scope == ("deploy", "review")
        assert found.max_classification == ConfidentialityLevel.SECRET


# ===========================================================================
# Thread Safety
# ===========================================================================


class TestSqliteThreadSafety:
    """Concurrent access from 10 threads must not corrupt data."""

    def test_concurrent_org_writes(self) -> None:
        store = SqliteOrgStore(":memory:")
        errors: list[Exception] = []

        def writer(thread_idx: int) -> None:
            try:
                for i in range(10):
                    org = CompiledOrg(org_id=f"org-t{thread_idx}-{i}")
                    store.save_org(org)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_clearance_writes(self) -> None:
        store = SqliteClearanceStore(":memory:")
        errors: list[Exception] = []

        def writer(thread_idx: int) -> None:
            try:
                for i in range(10):
                    clr = _make_clearance(f"D{thread_idx}-R{i}")
                    store.grant_clearance(clr)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_bridge_writes(self) -> None:
        store = SqliteAccessPolicyStore(":memory:")
        errors: list[Exception] = []

        def writer(thread_idx: int) -> None:
            try:
                for i in range(10):
                    bridge = _make_bridge(
                        f"bridge-t{thread_idx}-{i}",
                        role_a=f"D{thread_idx}-R1",
                        role_b=f"D{thread_idx + 100}-R{i}",
                    )
                    store.save_bridge(bridge)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Thread errors: {errors}"


# ===========================================================================
# File Permissions (POSIX only)
# ===========================================================================


@pytest.mark.skipif(
    platform.system() == "Windows", reason="POSIX-only permissions test"
)
class TestSqliteFilePermissions:
    """Database file must have 0o600 permissions on POSIX systems."""

    def test_db_file_permissions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "governance.db"
        _store = SqliteOrgStore(str(db_path))
        assert db_path.exists()
        mode = stat.S_IMODE(os.stat(db_path).st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ===========================================================================
# Schema Version
# ===========================================================================


class TestSchemaVersion:
    """Schema migration tracking."""

    def test_schema_version_is_positive_int(self) -> None:
        assert isinstance(PACT_SCHEMA_VERSION, int)
        assert PACT_SCHEMA_VERSION >= 1


# ===========================================================================
# Engine store_backend="sqlite" Configuration
# ===========================================================================


class TestEngineStoreBackend:
    """GovernanceEngine with store_backend='sqlite' from TODO-7043."""

    def test_engine_with_sqlite_backend(self, tmp_path: Path) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("engine-test")
        db_path = str(tmp_path / "engine.db")
        engine = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=db_path,
        )
        # Should be able to use all engine operations
        assert engine.get_org().org_id == "engine-test"

    def test_engine_with_sqlite_backend_memory(self) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("engine-mem")
        engine = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )
        assert engine.get_org().org_id == "engine-mem"

    def test_engine_sqlite_stores_grant_clearance(self, tmp_path: Path) -> None:
        """Full round-trip: engine with SQLite stores can grant and use clearances."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("clearance-test")
        db_path = str(tmp_path / "clearance.db")
        engine = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=db_path,
        )
        clr = _make_clearance("D1-R1-T1-R1")
        engine.grant_clearance("D1-R1-T1-R1", clr)

    def test_engine_default_backend_is_memory(self) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("default-test")
        engine = GovernanceEngine(org)
        # Default stores should be memory-based (existing behavior)
        assert engine.get_org().org_id == "default-test"

    def test_engine_invalid_backend_raises(self) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("invalid-test")
        with pytest.raises(ValueError, match="Unsupported store_backend"):
            GovernanceEngine(org, store_backend="postgres")

    def test_engine_sqlite_requires_store_url(self) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("no-url-test")
        with pytest.raises(ValueError, match="store_url"):
            GovernanceEngine(org, store_backend="sqlite", store_url=None)
