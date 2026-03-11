"""Unit tests for TenantTrustManager thread safety (ROUND7-001).

Tests concurrent access to TenantTrustManager delegation operations to ensure
the threading.Lock properly protects against race conditions.

These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set

import pytest

from dataflow.trust.multi_tenant import CrossTenantDelegation, TenantTrustManager


class TestTenantTrustManagerLockExists:
    """Test that the _lock attribute exists and is correct type."""

    def test_lock_attribute_exists(self):
        """ROUND7-001: Verify _lock attribute exists on TenantTrustManager."""
        manager = TenantTrustManager(strict_mode=True)

        assert hasattr(
            manager, "_lock"
        ), "TenantTrustManager must have _lock attribute for thread safety"

    def test_lock_is_threading_lock(self):
        """ROUND7-001: Verify _lock is a threading.Lock instance."""
        manager = TenantTrustManager(strict_mode=True)

        # Check that _lock is a threading.Lock
        # threading.Lock() returns a _thread.lock object, not threading.Lock
        # We verify it has the acquire/release interface
        assert hasattr(manager._lock, "acquire"), "_lock must have acquire() method"
        assert hasattr(manager._lock, "release"), "_lock must have release() method"
        assert hasattr(
            manager._lock, "__enter__"
        ), "_lock must support context manager protocol"
        assert hasattr(
            manager._lock, "__exit__"
        ), "_lock must support context manager protocol"

    def test_lock_is_reentrant_safe(self):
        """Test that lock can be acquired and released properly."""
        manager = TenantTrustManager(strict_mode=True)

        # Test that lock can be acquired and released
        acquired = manager._lock.acquire(blocking=False)
        assert acquired, "Should be able to acquire lock"
        manager._lock.release()

        # Test context manager usage
        with manager._lock:
            pass  # Should not deadlock


class TestConcurrentDelegationCreation:
    """Test concurrent delegation creation from multiple threads."""

    def test_concurrent_creates_no_lost_entries(self):
        """ROUND7-001: Concurrent delegation creates from multiple threads don't lose entries."""
        manager = TenantTrustManager(strict_mode=True)

        num_threads = 10
        delegations_per_thread = 100
        total_expected = num_threads * delegations_per_thread
        errors: List[Exception] = []
        created_ids: List[str] = []
        created_ids_lock = threading.Lock()

        def create_delegations(thread_id: int) -> None:
            """Create multiple delegations from a single thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(delegations_per_thread):
                    delegation = loop.run_until_complete(
                        manager.create_cross_tenant_delegation(
                            source_tenant_id=f"source-{thread_id}-{i}",
                            target_tenant_id=f"target-{thread_id}-{i}",
                            delegating_agent_id=f"delegator-{thread_id}",
                            receiving_agent_id=f"receiver-{thread_id}",
                            allowed_models=["User", "Order"],
                            allowed_operations={"SELECT"},
                        )
                    )
                    with created_ids_lock:
                        created_ids.append(delegation.delegation_id)
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Run concurrent creates
        threads = []
        for thread_id in range(num_threads):
            t = threading.Thread(target=create_delegations, args=(thread_id,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=30)

        # Check no exceptions occurred
        assert len(errors) == 0, f"Errors during concurrent creates: {errors}"

        # Verify all entries are present
        actual_count = len(manager._delegations)
        assert actual_count == total_expected, (
            f"Lost entries during concurrent creates: "
            f"expected {total_expected}, got {actual_count}"
        )

        # Verify all delegation IDs are unique
        assert (
            len(created_ids) == total_expected
        ), "Not all delegation IDs were recorded"
        assert len(set(created_ids)) == total_expected, "Delegation IDs are not unique"

    def test_concurrent_creates_preserve_all_delegation_ids(self):
        """ROUND7-001: All delegation IDs are preserved during concurrent creates."""
        manager = TenantTrustManager(strict_mode=True)

        num_threads = 5
        delegations_per_thread = 50
        delegation_ids: Set[str] = set()
        delegation_ids_lock = threading.Lock()

        def create_delegations(thread_id: int) -> None:
            """Create delegations and track their IDs."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(delegations_per_thread):
                    delegation = loop.run_until_complete(
                        manager.create_cross_tenant_delegation(
                            source_tenant_id=f"source-t{thread_id}-e{i}",
                            target_tenant_id=f"target-t{thread_id}-e{i}",
                            delegating_agent_id=f"delegator-{thread_id}",
                            receiving_agent_id=f"receiver-{thread_id}",
                            allowed_models=["Product"],
                        )
                    )
                    with delegation_ids_lock:
                        delegation_ids.add(delegation.delegation_id)
            finally:
                loop.close()

        # Run concurrent creates
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(create_delegations, thread_id)
                for thread_id in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Verify all delegation IDs are in the manager
        stored_ids = set(manager._delegations.keys())
        missing_ids = delegation_ids - stored_ids
        assert (
            len(missing_ids) == 0
        ), f"Missing delegation IDs after concurrent creates: {missing_ids}"


class TestConcurrentCreateAndRevoke:
    """Test concurrent delegation creation and revocation."""

    def test_create_while_revoking_no_exceptions(self):
        """ROUND7-001: Concurrent creates while revoking don't raise exceptions."""
        manager = TenantTrustManager(strict_mode=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()
        revoked_count = [0]  # Use list for mutable counter in closure
        revoked_count_lock = threading.Lock()

        def creator() -> None:
            """Continuously create delegations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 200:
                    loop.run_until_complete(
                        manager.create_cross_tenant_delegation(
                            source_tenant_id=f"src-{count}",
                            target_tenant_id=f"tgt-{count}",
                            delegating_agent_id="delegator",
                            receiving_agent_id="receiver",
                            allowed_models=["Entity"],
                        )
                    )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def revoker() -> None:
            """Continuously revoke delegations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                while not stop_flag.is_set():
                    # Get a copy of delegation IDs to avoid dict changed during iteration
                    with manager._lock:
                        ids = list(manager._delegations.keys())

                    for del_id in ids[:5]:  # Revoke first 5
                        if stop_flag.is_set():
                            break
                        result = loop.run_until_complete(
                            manager.revoke_delegation(del_id, reason="test revocation")
                        )
                        if result:
                            with revoked_count_lock:
                                revoked_count[0] += 1
                    time.sleep(0.01)  # Small delay between batches
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Start concurrent operations
        creator_threads = [threading.Thread(target=creator) for _ in range(3)]
        revoker_thread = threading.Thread(target=revoker)

        for t in creator_threads:
            t.start()
        revoker_thread.start()

        # Let them run
        time.sleep(0.5)
        stop_flag.set()

        for t in creator_threads:
            t.join(timeout=10)
        revoker_thread.join(timeout=10)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent create/revoke: {errors}"

    def test_revoke_returns_correct_value(self):
        """ROUND7-001: revoke_delegation returns correct boolean under concurrency."""
        manager = TenantTrustManager(strict_mode=True)

        # Create some delegations first
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        delegations = []
        for i in range(20):
            d = loop.run_until_complete(
                manager.create_cross_tenant_delegation(
                    source_tenant_id=f"src-{i}",
                    target_tenant_id=f"tgt-{i}",
                    delegating_agent_id="delegator",
                    receiving_agent_id="receiver",
                    allowed_models=["Model"],
                )
            )
            delegations.append(d)

        # Revoke each only once - should all succeed
        for d in delegations:
            result = loop.run_until_complete(manager.revoke_delegation(d.delegation_id))
            assert (
                result is True
            ), f"First revocation should succeed for {d.delegation_id}"

        # All should now be revoked
        for d in delegations:
            assert d.revoked is True, f"Delegation {d.delegation_id} should be revoked"

        loop.close()


class TestConcurrentCreateAndVerify:
    """Test concurrent delegation creation and verification."""

    def test_create_while_verifying_no_exceptions(self):
        """ROUND7-001: Concurrent creates while verifying don't raise exceptions."""
        manager = TenantTrustManager(strict_mode=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()

        def creator() -> None:
            """Continuously create delegations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 300:
                    loop.run_until_complete(
                        manager.create_cross_tenant_delegation(
                            source_tenant_id=f"source-{count % 10}",
                            target_tenant_id=f"target-{count % 10}",
                            delegating_agent_id="delegator",
                            receiving_agent_id="receiver",
                            allowed_models=["User"],
                            allowed_operations={"SELECT"},
                        )
                    )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def verifier() -> None:
            """Continuously verify access."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                while not stop_flag.is_set():
                    for i in range(10):
                        if stop_flag.is_set():
                            break
                        result = loop.run_until_complete(
                            manager.verify_cross_tenant_access(
                                source_tenant_id=f"source-{i}",
                                target_tenant_id=f"target-{i}",
                                agent_id="receiver",
                                model="User",
                                operation="SELECT",
                            )
                        )
                        # Result should be (bool, Optional[str])
                        assert isinstance(
                            result, tuple
                        ), "verify result should be tuple"
                        assert len(result) == 2, "verify result should have 2 elements"
                        assert isinstance(
                            result[0], bool
                        ), "first element should be bool"
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Start concurrent operations
        creator_threads = [threading.Thread(target=creator) for _ in range(3)]
        verifier_threads = [threading.Thread(target=verifier) for _ in range(3)]

        all_threads = creator_threads + verifier_threads
        for t in all_threads:
            t.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in all_threads:
            t.join(timeout=10)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent create/verify: {errors}"

    def test_verify_returns_consistent_results(self):
        """ROUND7-001: Concurrent verifications return consistent results."""
        manager = TenantTrustManager(strict_mode=True)

        # Create a known delegation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(
            manager.create_cross_tenant_delegation(
                source_tenant_id="tenant-a",
                target_tenant_id="tenant-b",
                delegating_agent_id="agent-a",
                receiving_agent_id="agent-b",
                allowed_models=["User"],
                allowed_operations={"SELECT"},
            )
        )

        results: List[tuple] = []
        results_lock = threading.Lock()
        errors: List[Exception] = []

        def verify_access() -> None:
            """Verify access and record result."""
            tl = asyncio.new_event_loop()
            asyncio.set_event_loop(tl)
            try:
                for _ in range(50):
                    result = tl.run_until_complete(
                        manager.verify_cross_tenant_access(
                            source_tenant_id="tenant-a",
                            target_tenant_id="tenant-b",
                            agent_id="agent-b",
                            model="User",
                            operation="SELECT",
                        )
                    )
                    with results_lock:
                        results.append(result)
            except Exception as e:
                errors.append(e)
            finally:
                tl.close()

        # Run concurrent verifications
        threads = [threading.Thread(target=verify_access) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        loop.close()

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent verify: {errors}"

        # All results should be (True, None) since we created a valid delegation
        for r in results:
            assert r[0] is True, f"All verifications should succeed, got {r}"
            assert (
                r[1] is None
            ), f"Successful verification should have None reason, got {r}"


class TestConcurrentCreateAndList:
    """Test concurrent delegation creation and listing."""

    def test_create_while_listing_no_exceptions(self):
        """ROUND7-001: Concurrent creates while listing don't raise exceptions."""
        manager = TenantTrustManager(strict_mode=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()

        def creator() -> None:
            """Continuously create delegations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 200:
                    loop.run_until_complete(
                        manager.create_cross_tenant_delegation(
                            source_tenant_id=f"src-{count}",
                            target_tenant_id=f"tgt-{count}",
                            delegating_agent_id="delegator",
                            receiving_agent_id="receiver",
                            allowed_models=["Model"],
                        )
                    )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def lister() -> None:
            """Continuously list delegations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                while not stop_flag.is_set():
                    # List all
                    all_delegations = loop.run_until_complete(
                        manager.list_delegations()
                    )
                    assert isinstance(
                        all_delegations, list
                    ), "list_delegations should return list"

                    # List by tenant
                    tenant_delegations = loop.run_until_complete(
                        manager.list_delegations(tenant_id="src-0")
                    )
                    assert isinstance(
                        tenant_delegations, list
                    ), "list_delegations with tenant should return list"

                    time.sleep(0.005)  # Small delay
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Start concurrent operations
        creator_threads = [threading.Thread(target=creator) for _ in range(3)]
        lister_threads = [threading.Thread(target=lister) for _ in range(3)]

        all_threads = creator_threads + lister_threads
        for t in all_threads:
            t.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in all_threads:
            t.join(timeout=10)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent create/list: {errors}"

    def test_list_delegations_returns_complete_data(self):
        """ROUND7-001: list_delegations returns complete delegation objects."""
        manager = TenantTrustManager(strict_mode=True)

        # Create delegations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for i in range(10):
            loop.run_until_complete(
                manager.create_cross_tenant_delegation(
                    source_tenant_id=f"src-{i}",
                    target_tenant_id=f"tgt-{i}",
                    delegating_agent_id=f"delegator-{i}",
                    receiving_agent_id=f"receiver-{i}",
                    allowed_models=["ModelA", "ModelB"],
                    allowed_operations={"SELECT", "INSERT"},
                )
            )

        errors: List[Exception] = []

        def check_delegations() -> None:
            """Check delegation objects are complete."""
            tl = asyncio.new_event_loop()
            asyncio.set_event_loop(tl)
            try:
                for _ in range(20):
                    delegations = tl.run_until_complete(manager.list_delegations())
                    for d in delegations:
                        # Verify all fields are present and valid
                        assert (
                            d.delegation_id is not None
                        ), "delegation_id should not be None"
                        assert (
                            d.source_tenant_id is not None
                        ), "source_tenant_id should not be None"
                        assert (
                            d.target_tenant_id is not None
                        ), "target_tenant_id should not be None"
                        assert isinstance(
                            d.allowed_models, list
                        ), "allowed_models should be list"
                        assert isinstance(
                            d.allowed_operations, set
                        ), "allowed_operations should be set"
            except Exception as e:
                errors.append(e)
            finally:
                tl.close()

        threads = [threading.Thread(target=check_delegations) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        loop.close()

        assert len(errors) == 0, f"Errors during delegation checks: {errors}"


class TestHighConcurrencyStress:
    """Stress test with high concurrency to detect race conditions."""

    def test_high_concurrency_mixed_operations(self):
        """ROUND7-001: Stress test with many threads doing mixed operations."""
        manager = TenantTrustManager(strict_mode=True)

        num_threads = 20
        operations_per_thread = 100
        errors: List[Exception] = []

        def mixed_operations(thread_id: int) -> None:
            """Perform mixed delegation operations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(operations_per_thread):
                    op = i % 6
                    if op == 0:
                        # Create delegation
                        loop.run_until_complete(
                            manager.create_cross_tenant_delegation(
                                source_tenant_id=f"stress-src-{thread_id}-{i}",
                                target_tenant_id=f"stress-tgt-{thread_id}-{i}",
                                delegating_agent_id=f"agent-{thread_id}",
                                receiving_agent_id=f"receiver-{thread_id}",
                                allowed_models=["StressModel"],
                            )
                        )
                    elif op == 1:
                        # Verify access
                        loop.run_until_complete(
                            manager.verify_cross_tenant_access(
                                source_tenant_id=f"stress-src-{thread_id}-{max(0, i-5)}",
                                target_tenant_id=f"stress-tgt-{thread_id}-{max(0, i-5)}",
                                agent_id=f"receiver-{thread_id}",
                                model="StressModel",
                                operation="SELECT",
                            )
                        )
                    elif op == 2:
                        # List all delegations
                        loop.run_until_complete(manager.list_delegations())
                    elif op == 3:
                        # List delegations by tenant
                        loop.run_until_complete(
                            manager.list_delegations(
                                tenant_id=f"stress-src-{thread_id}-0"
                            )
                        )
                    elif op == 4:
                        # Get active delegations for agent
                        loop.run_until_complete(
                            manager.get_active_delegations_for_agent(
                                f"receiver-{thread_id}"
                            )
                        )
                    elif op == 5:
                        # Get row filter
                        manager.get_row_filter_for_access(
                            source_tenant_id=f"stress-src-{thread_id}-0",
                            target_tenant_id=f"stress-tgt-{thread_id}-0",
                            agent_id=f"receiver-{thread_id}",
                            model="StressModel",
                        )
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Run with thread pool
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(mixed_operations, tid) for tid in range(num_threads)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    errors.append(e)

        # Check no exceptions
        assert (
            len(errors) == 0
        ), f"Errors during high-concurrency stress test: {errors[:5]}"

        # Verify state is consistent - we created many delegations
        expected_creates = num_threads * (operations_per_thread // 6 + 1)
        actual_count = len(manager._delegations)
        # At minimum we should have many delegations (exact count depends on rounding)
        assert (
            actual_count >= expected_creates - num_threads
        ), f"Expected at least {expected_creates - num_threads} delegations, got {actual_count}"

    def test_extreme_concurrency_no_crashes(self):
        """ROUND7-001: Extreme concurrency doesn't cause crashes or hangs."""
        manager = TenantTrustManager(
            strict_mode=False
        )  # Non-strict for faster execution

        num_threads = 25
        operations_per_thread = 50
        errors: List[Exception] = []
        completed_threads = [0]
        completed_lock = threading.Lock()

        def rapid_operations(thread_id: int) -> None:
            """Perform rapid delegation operations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(operations_per_thread):
                    # Rapid creates
                    loop.run_until_complete(
                        manager.create_cross_tenant_delegation(
                            source_tenant_id=f"extreme-{thread_id}-{i}",
                            target_tenant_id=f"extreme-tgt-{thread_id}-{i}",
                            delegating_agent_id="agent",
                            receiving_agent_id="receiver",
                            allowed_models=["Model"],
                        )
                    )
                    # Rapid verifies
                    loop.run_until_complete(
                        manager.verify_cross_tenant_access(
                            source_tenant_id=f"extreme-{thread_id}-{i}",
                            target_tenant_id=f"extreme-tgt-{thread_id}-{i}",
                            agent_id="receiver",
                            model="Model",
                            operation="SELECT",
                        )
                    )
                with completed_lock:
                    completed_threads[0] += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Run all threads
        threads = []
        for tid in range(num_threads):
            t = threading.Thread(target=rapid_operations, args=(tid,))
            threads.append(t)
            t.start()

        # Wait with timeout
        for t in threads:
            t.join(timeout=30)

        # Verify all threads completed
        assert (
            completed_threads[0] == num_threads
        ), f"Not all threads completed: {completed_threads[0]}/{num_threads}"

        # Check no exceptions
        assert len(errors) == 0, f"Errors during extreme concurrency test: {errors[:5]}"
