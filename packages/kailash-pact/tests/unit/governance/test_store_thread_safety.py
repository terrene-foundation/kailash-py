# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Thread safety tests for governance in-memory store implementations.

Verifies that concurrent reads and writes to Memory*Store classes do not
corrupt state or raise RuntimeError (dictionary changed size during iteration).

All four store classes are tested:
- MemoryOrgStore
- MemoryEnvelopeStore
- MemoryClearanceStore
- MemoryAccessPolicyStore
"""

from __future__ import annotations

import concurrent.futures
import threading
from datetime import UTC, datetime, timedelta

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.addressing import NodeType
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.envelopes import RoleEnvelope, TaskEnvelope
from pact.governance.store import (
    MAX_STORE_SIZE,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
)

# ---------------------------------------------------------------------------
# Helpers -- lightweight object constructors for concurrent tests
# ---------------------------------------------------------------------------

NUM_THREADS = 100
"""Number of threads for concurrent write tests."""

NUM_READERS = 50
"""Number of reader threads for mixed read-write tests."""

NUM_WRITERS = 50
"""Number of writer threads for mixed read-write tests."""


def _make_compiled_org(org_id: str) -> CompiledOrg:
    """Create a minimal CompiledOrg for threading tests."""
    org = CompiledOrg(org_id=org_id)
    org.nodes["D1"] = OrgNode(
        address="D1",
        node_type=NodeType.DEPARTMENT,
        name=f"Dept-{org_id}",
        node_id=f"dept-{org_id}",
    )
    org.nodes["D1-R1"] = OrgNode(
        address="D1-R1",
        node_type=NodeType.ROLE,
        name=f"Role-{org_id}",
        node_id=f"role-{org_id}",
        parent_address="D1",
    )
    return org


def _make_envelope_config(env_id: str) -> ConstraintEnvelopeConfig:
    """Create a minimal ConstraintEnvelopeConfig."""
    return ConstraintEnvelopeConfig(
        id=env_id,
        description=f"Test envelope {env_id}",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(allowed_actions=["read", "write"]),
    )


def _make_role_envelope(env_id: str, target: str) -> RoleEnvelope:
    """Create a RoleEnvelope for threading tests."""
    return RoleEnvelope(
        id=env_id,
        defining_role_address="D1-R1",
        target_role_address=target,
        envelope=_make_envelope_config(env_id),
    )


def _make_task_envelope(env_id: str, task_id: str) -> TaskEnvelope:
    """Create a TaskEnvelope for threading tests."""
    return TaskEnvelope(
        id=env_id,
        task_id=task_id,
        parent_envelope_id="re-parent",
        envelope=_make_envelope_config(env_id),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _make_clearance(role_address: str) -> RoleClearance:
    """Create a RoleClearance for threading tests."""
    return RoleClearance(
        role_address=role_address,
        max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        granted_by_role_address="D1-R1",
        vetting_status=VettingStatus.ACTIVE,
    )


def _make_ksp(ksp_id: str, source: str, target: str) -> KnowledgeSharePolicy:
    """Create a KnowledgeSharePolicy for threading tests."""
    return KnowledgeSharePolicy(
        id=ksp_id,
        source_unit_address=source,
        target_unit_address=target,
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
    )


def _make_bridge(bridge_id: str, role_a: str, role_b: str) -> PactBridge:
    """Create a PactBridge for threading tests."""
    return PactBridge(
        id=bridge_id,
        role_a_address=role_a,
        role_b_address=role_b,
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        bilateral=True,
    )


# ===========================================================================
# MemoryOrgStore thread safety
# ===========================================================================


class TestMemoryOrgStoreThreadSafety:
    """Concurrent access to MemoryOrgStore must not corrupt state."""

    def test_concurrent_writes_no_corruption(self) -> None:
        """100 threads writing simultaneously should not corrupt state."""
        store = MemoryOrgStore()
        errors: list[Exception] = []

        def write_org(i: int) -> None:
            try:
                org = _make_compiled_org(f"org-{i}")
                store.save_org(org)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(write_org, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent writes raised exceptions: {errors}"
        # Every org should be retrievable -- no data loss
        for i in range(NUM_THREADS):
            loaded = store.load_org(f"org-{i}")
            assert loaded is not None, f"org-{i} missing after concurrent writes"
            assert loaded.org_id == f"org-{i}"

    def test_concurrent_reads_and_writes(self) -> None:
        """Mixed reads and writes must not raise RuntimeError."""
        store = MemoryOrgStore()
        # Pre-populate with some data so readers have something to read
        for i in range(20):
            store.save_org(_make_compiled_org(f"seed-{i}"))

        errors: list[Exception] = []
        barrier = threading.Barrier(NUM_READERS + NUM_WRITERS)

        def writer(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.save_org(_make_compiled_org(f"concurrent-{i}"))
            except Exception as exc:
                errors.append(exc)

        def reader(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                # Read existing orgs and query nodes
                store.load_org(f"seed-{i % 20}")
                store.get_node(f"seed-{i % 20}", "D1")
                store.query_by_prefix(f"seed-{i % 20}", "D1")
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=NUM_READERS + NUM_WRITERS,
        ) as pool:
            futures = []
            for i in range(NUM_WRITERS):
                futures.append(pool.submit(writer, i))
            for i in range(NUM_READERS):
                futures.append(pool.submit(reader, i))
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent read/write raised exceptions: {errors}"

    def test_concurrent_overwrite_same_key(self) -> None:
        """Multiple threads overwriting the same org_id should not corrupt."""
        store = MemoryOrgStore()
        errors: list[Exception] = []

        def overwrite(i: int) -> None:
            try:
                org = _make_compiled_org("shared-org")
                store.save_org(org)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(overwrite, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent overwrites raised exceptions: {errors}"
        loaded = store.load_org("shared-org")
        assert loaded is not None
        assert loaded.org_id == "shared-org"


# ===========================================================================
# MemoryEnvelopeStore thread safety
# ===========================================================================


class TestMemoryEnvelopeStoreThreadSafety:
    """Concurrent access to MemoryEnvelopeStore must not corrupt state."""

    def test_concurrent_role_envelope_writes(self) -> None:
        """100 threads writing role envelopes should not corrupt state."""
        store = MemoryEnvelopeStore()
        errors: list[Exception] = []

        def write_envelope(i: int) -> None:
            try:
                env = _make_role_envelope(f"re-{i}", target=f"D{i}-R1")
                store.save_role_envelope(env)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(write_envelope, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent writes raised exceptions: {errors}"
        for i in range(NUM_THREADS):
            loaded = store.get_role_envelope(f"D{i}-R1")
            assert loaded is not None, f"Role envelope D{i}-R1 missing"

    def test_concurrent_task_envelope_writes(self) -> None:
        """100 threads writing task envelopes should not corrupt state."""
        store = MemoryEnvelopeStore()
        errors: list[Exception] = []

        def write_task_env(i: int) -> None:
            try:
                env = _make_task_envelope(f"te-{i}", task_id=f"task-{i}")
                store.save_task_envelope(env)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(write_task_env, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent task writes raised exceptions: {errors}"
        for i in range(NUM_THREADS):
            loaded = store.get_active_task_envelope(f"D1-R1", f"task-{i}")
            assert loaded is not None, f"Task envelope task-{i} missing"

    def test_concurrent_ancestor_lookups_during_writes(self) -> None:
        """get_ancestor_envelopes iterates dict -- must not fail during writes."""
        store = MemoryEnvelopeStore()
        # Pre-populate with a hierarchy
        for i in range(20):
            store.save_role_envelope(
                _make_role_envelope(f"re-{i}", target=f"D1-R1-T{i}-R1"),
            )

        errors: list[Exception] = []
        barrier = threading.Barrier(NUM_READERS + NUM_WRITERS)

        def writer(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.save_role_envelope(
                    _make_role_envelope(f"re-new-{i}", target=f"D1-R1-T{100 + i}-R1"),
                )
            except Exception as exc:
                errors.append(exc)

        def reader(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                # This iterates _role_envelopes -- the critical path
                store.get_ancestor_envelopes(f"D1-R1-T{i % 20}-R1")
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=NUM_READERS + NUM_WRITERS,
        ) as pool:
            futures = []
            for i in range(NUM_WRITERS):
                futures.append(pool.submit(writer, i))
            for i in range(NUM_READERS):
                futures.append(pool.submit(reader, i))
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent ancestor lookup raised exceptions: {errors}"


# ===========================================================================
# MemoryClearanceStore thread safety
# ===========================================================================


class TestMemoryClearanceStoreThreadSafety:
    """Concurrent access to MemoryClearanceStore must not corrupt state."""

    def test_concurrent_grant_clearance(self) -> None:
        """100 threads granting clearance should not corrupt state."""
        store = MemoryClearanceStore()
        errors: list[Exception] = []

        def grant(i: int) -> None:
            try:
                clr = _make_clearance(f"D{i}-R1")
                store.grant_clearance(clr)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(grant, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent grants raised exceptions: {errors}"
        for i in range(NUM_THREADS):
            loaded = store.get_clearance(f"D{i}-R1")
            assert loaded is not None, f"Clearance D{i}-R1 missing"

    def test_concurrent_read_write_clearance(self) -> None:
        """Concurrent reads and writes should not raise RuntimeError."""
        store = MemoryClearanceStore()
        # Pre-populate
        for i in range(20):
            store.grant_clearance(_make_clearance(f"seed-D{i}-R1"))

        errors: list[Exception] = []
        barrier = threading.Barrier(NUM_READERS + NUM_WRITERS)

        def writer(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.grant_clearance(_make_clearance(f"new-D{i}-R1"))
            except Exception as exc:
                errors.append(exc)

        def reader(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.get_clearance(f"seed-D{i % 20}-R1")
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=NUM_READERS + NUM_WRITERS,
        ) as pool:
            futures = []
            for i in range(NUM_WRITERS):
                futures.append(pool.submit(writer, i))
            for i in range(NUM_READERS):
                futures.append(pool.submit(reader, i))
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent read/write raised exceptions: {errors}"
        # All writes should be visible after synchronization
        for i in range(NUM_WRITERS):
            assert store.get_clearance(f"new-D{i}-R1") is not None

    def test_concurrent_grant_and_revoke(self) -> None:
        """Concurrent grants and revokes on different keys should not corrupt."""
        store = MemoryClearanceStore()
        # Pre-populate keys that will be revoked
        for i in range(NUM_THREADS):
            store.grant_clearance(_make_clearance(f"revoke-D{i}-R1"))

        errors: list[Exception] = []
        barrier = threading.Barrier(NUM_THREADS * 2)

        def grant(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.grant_clearance(_make_clearance(f"grant-D{i}-R1"))
            except Exception as exc:
                errors.append(exc)

        def revoke(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.revoke_clearance(f"revoke-D{i}-R1")
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS * 2) as pool:
            futures = []
            for i in range(NUM_THREADS):
                futures.append(pool.submit(grant, i))
                futures.append(pool.submit(revoke, i))
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent grant/revoke raised exceptions: {errors}"
        # All grants should be present, all revokes should have taken effect
        for i in range(NUM_THREADS):
            assert store.get_clearance(f"grant-D{i}-R1") is not None
            assert store.get_clearance(f"revoke-D{i}-R1") is None


# ===========================================================================
# MemoryAccessPolicyStore thread safety
# ===========================================================================


class TestMemoryAccessPolicyStoreThreadSafety:
    """Concurrent access to MemoryAccessPolicyStore must not corrupt state."""

    def test_concurrent_ksp_writes(self) -> None:
        """100 threads writing KSPs should not corrupt state."""
        store = MemoryAccessPolicyStore()
        errors: list[Exception] = []

        def write_ksp(i: int) -> None:
            try:
                ksp = _make_ksp(f"ksp-{i}", source=f"D{i}", target=f"D{i + 1000}")
                store.save_ksp(ksp)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(write_ksp, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent KSP writes raised exceptions: {errors}"
        ksps = store.list_ksps()
        assert len(ksps) == NUM_THREADS

    def test_concurrent_bridge_writes(self) -> None:
        """100 threads writing bridges should not corrupt state."""
        store = MemoryAccessPolicyStore()
        errors: list[Exception] = []

        def write_bridge(i: int) -> None:
            try:
                bridge = _make_bridge(
                    f"bridge-{i}",
                    role_a=f"D{i}-R1",
                    role_b=f"D{i + 1000}-R1",
                )
                store.save_bridge(bridge)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
            futures = [pool.submit(write_bridge, i) for i in range(NUM_THREADS)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent bridge writes raised exceptions: {errors}"
        bridges = store.list_bridges()
        assert len(bridges) == NUM_THREADS

    def test_concurrent_ksp_find_during_writes(self) -> None:
        """find_ksp iterates all KSPs -- must not fail during concurrent writes."""
        store = MemoryAccessPolicyStore()
        # Pre-populate
        for i in range(20):
            store.save_ksp(_make_ksp(f"seed-{i}", source=f"S{i}", target=f"T{i}"))

        errors: list[Exception] = []
        barrier = threading.Barrier(NUM_READERS + NUM_WRITERS)

        def writer(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.save_ksp(
                    _make_ksp(f"new-{i}", source=f"NS{i}", target=f"NT{i}"),
                )
            except Exception as exc:
                errors.append(exc)

        def reader(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.find_ksp(f"S{i % 20}", f"T{i % 20}")
                store.list_ksps()
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=NUM_READERS + NUM_WRITERS,
        ) as pool:
            futures = []
            for i in range(NUM_WRITERS):
                futures.append(pool.submit(writer, i))
            for i in range(NUM_READERS):
                futures.append(pool.submit(reader, i))
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent KSP find raised exceptions: {errors}"

    def test_concurrent_bridge_find_during_writes(self) -> None:
        """find_bridge iterates all bridges -- must not fail during concurrent writes."""
        store = MemoryAccessPolicyStore()
        # Pre-populate
        for i in range(20):
            store.save_bridge(
                _make_bridge(f"seed-{i}", role_a=f"A{i}-R1", role_b=f"B{i}-R1"),
            )

        errors: list[Exception] = []
        barrier = threading.Barrier(NUM_READERS + NUM_WRITERS)

        def writer(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.save_bridge(
                    _make_bridge(f"new-{i}", role_a=f"NA{i}-R1", role_b=f"NB{i}-R1"),
                )
            except Exception as exc:
                errors.append(exc)

        def reader(i: int) -> None:
            try:
                barrier.wait(timeout=5)
                store.find_bridge(f"A{i % 20}-R1", f"B{i % 20}-R1")
                store.list_bridges()
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=NUM_READERS + NUM_WRITERS,
        ) as pool:
            futures = []
            for i in range(NUM_WRITERS):
                futures.append(pool.submit(writer, i))
            for i in range(NUM_READERS):
                futures.append(pool.submit(reader, i))
            concurrent.futures.wait(futures)

        assert errors == [], f"Concurrent bridge find raised exceptions: {errors}"


# ===========================================================================
# Eviction under concurrency
# ===========================================================================


class TestEvictionUnderConcurrency:
    """Store at MAX_STORE_SIZE with concurrent writes should evict safely."""

    def test_org_store_eviction_under_concurrency(self) -> None:
        """Fill store to capacity, then write from 10 threads concurrently."""
        store = MemoryOrgStore()
        # Fill to capacity
        for i in range(MAX_STORE_SIZE):
            store.save_org(CompiledOrg(org_id=f"prefill-{i}"))

        errors: list[Exception] = []
        num_concurrent = 10

        def write_over_capacity(i: int) -> None:
            try:
                store.save_org(_make_compiled_org(f"overflow-{i}"))
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as pool:
            futures = [pool.submit(write_over_capacity, i) for i in range(num_concurrent)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Eviction under concurrency raised exceptions: {errors}"
        # Store size must not exceed MAX_STORE_SIZE
        # Access internal dict size directly for validation
        assert len(store._orgs) <= MAX_STORE_SIZE

    def test_clearance_store_eviction_under_concurrency(self) -> None:
        """Fill clearance store to capacity, then write concurrently."""
        store = MemoryClearanceStore()
        # Fill to capacity
        for i in range(MAX_STORE_SIZE):
            store.grant_clearance(_make_clearance(f"prefill-D{i}-R1"))

        errors: list[Exception] = []
        num_concurrent = 10

        def write_over_capacity(i: int) -> None:
            try:
                store.grant_clearance(_make_clearance(f"overflow-D{i}-R1"))
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as pool:
            futures = [pool.submit(write_over_capacity, i) for i in range(num_concurrent)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Eviction under concurrency raised exceptions: {errors}"
        assert len(store._clearances) <= MAX_STORE_SIZE

    def test_envelope_store_eviction_under_concurrency(self) -> None:
        """Fill envelope store to capacity, then write concurrently."""
        store = MemoryEnvelopeStore()
        for i in range(MAX_STORE_SIZE):
            store.save_role_envelope(
                _make_role_envelope(f"re-{i}", target=f"D{i}-R1"),
            )

        errors: list[Exception] = []
        num_concurrent = 10

        def write_over_capacity(i: int) -> None:
            try:
                store.save_role_envelope(
                    _make_role_envelope(f"re-overflow-{i}", target=f"OV{i}-R1"),
                )
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as pool:
            futures = [pool.submit(write_over_capacity, i) for i in range(num_concurrent)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Eviction under concurrency raised exceptions: {errors}"
        assert len(store._role_envelopes) <= MAX_STORE_SIZE

    def test_access_policy_store_eviction_under_concurrency(self) -> None:
        """Fill access policy store to capacity, then write concurrently."""
        store = MemoryAccessPolicyStore()
        for i in range(MAX_STORE_SIZE):
            store.save_ksp(_make_ksp(f"ksp-{i}", source=f"S{i}", target=f"T{i}"))

        errors: list[Exception] = []
        num_concurrent = 10

        def write_over_capacity(i: int) -> None:
            try:
                store.save_ksp(
                    _make_ksp(f"ksp-overflow-{i}", source=f"OS{i}", target=f"OT{i}"),
                )
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as pool:
            futures = [pool.submit(write_over_capacity, i) for i in range(num_concurrent)]
            concurrent.futures.wait(futures)

        assert errors == [], f"Eviction under concurrency raised exceptions: {errors}"
        assert len(store._ksps) <= MAX_STORE_SIZE
