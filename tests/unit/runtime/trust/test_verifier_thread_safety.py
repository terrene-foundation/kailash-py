"""Unit tests for TrustVerifier cache thread safety (ROUND6-001).

Tests concurrent access to the TrustVerifier cache to ensure the
threading.Lock properly protects against race conditions.

These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set

import pytest
from kailash.runtime.trust.verifier import (
    TrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)


class TestCacheLockExists:
    """Test that the _cache_lock attribute exists and is correct type."""

    def test_cache_lock_attribute_exists(self):
        """ROUND6-001: Verify _cache_lock attribute exists on TrustVerifier."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        assert hasattr(
            verifier, "_cache_lock"
        ), "TrustVerifier must have _cache_lock attribute for thread safety"

    def test_cache_lock_is_threading_lock(self):
        """ROUND6-001: Verify _cache_lock is a threading.Lock instance."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # Check that _cache_lock is a threading.Lock
        # threading.Lock() returns a _thread.lock object, not threading.Lock
        # We verify it has the acquire/release interface
        assert hasattr(
            verifier._cache_lock, "acquire"
        ), "_cache_lock must have acquire() method"
        assert hasattr(
            verifier._cache_lock, "release"
        ), "_cache_lock must have release() method"
        assert hasattr(
            verifier._cache_lock, "__enter__"
        ), "_cache_lock must support context manager protocol"
        assert hasattr(
            verifier._cache_lock, "__exit__"
        ), "_cache_lock must support context manager protocol"

    def test_cache_lock_is_reentrant_safe(self):
        """Test that cache lock can be acquired and released properly."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # Test that lock can be acquired and released
        acquired = verifier._cache_lock.acquire(blocking=False)
        assert acquired, "Should be able to acquire lock"
        verifier._cache_lock.release()

        # Test context manager usage
        with verifier._cache_lock:
            pass  # Should not deadlock


class TestConcurrentCacheWrites:
    """Test concurrent cache writes don't lose entries."""

    def test_concurrent_writes_no_lost_entries(self):
        """ROUND6-001: Concurrent cache writes from multiple threads don't lose entries."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        num_threads = 10
        entries_per_thread = 100
        total_expected = num_threads * entries_per_thread
        errors: List[Exception] = []

        def write_entries(thread_id: int) -> None:
            """Write multiple entries from a single thread."""
            try:
                for i in range(entries_per_thread):
                    key = f"thread_{thread_id}_key_{i}"
                    result = VerificationResult(
                        allowed=True,
                        reason=f"Thread {thread_id} entry {i}",
                    )
                    verifier._set_cache(key, result)
            except Exception as e:
                errors.append(e)

        # Run concurrent writes
        threads = []
        for thread_id in range(num_threads):
            t = threading.Thread(target=write_entries, args=(thread_id,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=10)

        # Check no exceptions occurred
        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"

        # Verify all entries are present
        actual_count = len(verifier._cache)
        assert actual_count == total_expected, (
            f"Lost entries during concurrent writes: "
            f"expected {total_expected}, got {actual_count}"
        )

    def test_concurrent_writes_preserve_all_keys(self):
        """ROUND6-001: All cache keys are preserved during concurrent writes."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        num_threads = 5
        entries_per_thread = 50
        expected_keys: Set[str] = set()

        def write_entries(thread_id: int) -> None:
            """Write entries and track expected keys."""
            for i in range(entries_per_thread):
                key = f"t{thread_id}_e{i}"
                expected_keys.add(key)
                result = VerificationResult(allowed=True)
                verifier._set_cache(key, result)

        # Pre-calculate expected keys to avoid race in set operations
        for thread_id in range(num_threads):
            for i in range(entries_per_thread):
                expected_keys.add(f"t{thread_id}_e{i}")

        # Run concurrent writes
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(write_entries, thread_id)
                for thread_id in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Verify all expected keys are present
        actual_keys = set(verifier._cache.keys())
        missing_keys = expected_keys - actual_keys
        assert (
            len(missing_keys) == 0
        ), f"Missing keys after concurrent writes: {missing_keys}"


class TestConcurrentReadsAndWrites:
    """Test concurrent reads and writes don't raise exceptions."""

    def test_concurrent_read_write_no_exceptions(self):
        """ROUND6-001: Concurrent cache reads and writes don't raise exceptions."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # Pre-populate some cache entries
        for i in range(50):
            key = f"initial_key_{i}"
            result = VerificationResult(allowed=True, reason=f"Initial {i}")
            verifier._set_cache(key, result)

        errors: List[Exception] = []
        stop_flag = threading.Event()

        def reader() -> None:
            """Continuously read from cache."""
            try:
                while not stop_flag.is_set():
                    for i in range(50):
                        key = f"initial_key_{i}"
                        verifier._get_cached(key)
                        # Also try to read keys being written
                        verifier._get_cached(f"new_key_{i}")
            except Exception as e:
                errors.append(e)

        def writer() -> None:
            """Continuously write to cache."""
            try:
                count = 0
                while not stop_flag.is_set() and count < 200:
                    key = f"new_key_{count % 100}"
                    result = VerificationResult(allowed=True, reason=f"New {count}")
                    verifier._set_cache(key, result)
                    count += 1
            except Exception as e:
                errors.append(e)

        # Start reader and writer threads
        reader_threads = [threading.Thread(target=reader) for _ in range(3)]
        writer_threads = [threading.Thread(target=writer) for _ in range(3)]

        all_threads = reader_threads + writer_threads
        for t in all_threads:
            t.start()

        # Let them run for a short time
        time.sleep(0.5)
        stop_flag.set()

        # Wait for completion
        for t in all_threads:
            t.join(timeout=5)

        # Check no exceptions occurred
        assert len(errors) == 0, f"Exceptions during concurrent read/write: {errors}"

    def test_concurrent_read_returns_valid_or_none(self):
        """ROUND6-001: Concurrent reads return valid results or None, never partial data."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        key = "shared_key"
        results_seen: List[VerificationResult] = []
        errors: List[Exception] = []
        stop_flag = threading.Event()

        def writer() -> None:
            """Write different results to same key."""
            try:
                for i in range(100):
                    if stop_flag.is_set():
                        break
                    result = VerificationResult(
                        allowed=(i % 2 == 0),
                        reason=f"Iteration {i}",
                    )
                    verifier._set_cache(key, result)
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            """Read the shared key and validate results."""
            try:
                for _ in range(200):
                    if stop_flag.is_set():
                        break
                    result = verifier._get_cached(key)
                    if result is not None:
                        # Validate result is complete
                        assert isinstance(
                            result.allowed, bool
                        ), "Result.allowed should be bool"
                        assert result.reason is None or isinstance(
                            result.reason, str
                        ), "Result.reason should be None or str"
                        results_seen.append(result)
            except Exception as e:
                errors.append(e)

        # Run concurrent read/write
        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader) for _ in range(5)]

        writer_thread.start()
        for t in reader_threads:
            t.start()

        writer_thread.join(timeout=5)
        stop_flag.set()
        for t in reader_threads:
            t.join(timeout=5)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"


class TestConcurrentInvalidateAgent:
    """Test concurrent invalidate_agent during cache writes."""

    def test_invalidate_agent_during_writes(self):
        """ROUND6-001: Concurrent invalidate_agent while cache writes happening."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        agent_to_invalidate = "agent-to-remove"
        other_agent = "other-agent"
        errors: List[Exception] = []
        stop_flag = threading.Event()

        def write_entries_for_agent(agent_id: str) -> None:
            """Continuously write cache entries for an agent."""
            try:
                count = 0
                while not stop_flag.is_set() and count < 500:
                    # Use null byte separator as in the real implementation
                    key = f"wf\x00workflow_{count}\x00{agent_id}"
                    result = VerificationResult(allowed=True, reason=f"Entry {count}")
                    verifier._set_cache(key, result)
                    count += 1
            except Exception as e:
                errors.append(e)

        def invalidate_agent() -> None:
            """Continuously invalidate the target agent."""
            try:
                for _ in range(100):
                    if stop_flag.is_set():
                        break
                    verifier.invalidate_agent(agent_to_invalidate)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Start concurrent operations
        writer1 = threading.Thread(
            target=write_entries_for_agent, args=(agent_to_invalidate,)
        )
        writer2 = threading.Thread(target=write_entries_for_agent, args=(other_agent,))
        invalidator = threading.Thread(target=invalidate_agent)

        writer1.start()
        writer2.start()
        invalidator.start()

        # Let them run
        time.sleep(0.5)
        stop_flag.set()

        writer1.join(timeout=5)
        writer2.join(timeout=5)
        invalidator.join(timeout=5)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent invalidate_agent: {errors}"

        # Verify other agent's entries still exist
        other_agent_entries = [
            k for k in verifier._cache.keys() if k.endswith(f"\x00{other_agent}")
        ]
        assert (
            len(other_agent_entries) > 0
        ), "Other agent's entries should not be affected by invalidation"

    def test_invalidate_agent_returns_correct_count(self):
        """ROUND6-001: invalidate_agent returns correct count of removed entries."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        agent_id = "test-agent"
        num_entries = 50

        # Add entries for the agent
        for i in range(num_entries):
            key = f"wf\x00workflow_{i}\x00{agent_id}"
            result = VerificationResult(allowed=True)
            verifier._set_cache(key, result)

        # Add entries for other agent
        for i in range(30):
            key = f"wf\x00workflow_{i}\x00other-agent"
            result = VerificationResult(allowed=True)
            verifier._set_cache(key, result)

        # Invalidate
        removed = verifier.invalidate_agent(agent_id)

        assert (
            removed == num_entries
        ), f"Expected {num_entries} entries removed, got {removed}"

        # Verify entries are gone
        agent_entries = [
            k for k in verifier._cache.keys() if k.endswith(f"\x00{agent_id}")
        ]
        assert len(agent_entries) == 0, "Agent entries should be removed"


class TestConcurrentClearCache:
    """Test clear_cache under concurrent access."""

    def test_clear_cache_during_writes(self):
        """ROUND6-001: clear_cache under concurrent access doesn't cause errors."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        errors: List[Exception] = []
        stop_flag = threading.Event()

        def writer() -> None:
            """Continuously write to cache."""
            try:
                count = 0
                while not stop_flag.is_set() and count < 1000:
                    key = f"key_{count}"
                    result = VerificationResult(allowed=True, reason=f"Entry {count}")
                    verifier._set_cache(key, result)
                    count += 1
            except Exception as e:
                errors.append(e)

        def clearer() -> None:
            """Periodically clear the cache."""
            try:
                for _ in range(50):
                    if stop_flag.is_set():
                        break
                    verifier.clear_cache()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            """Continuously read from cache."""
            try:
                for _ in range(500):
                    if stop_flag.is_set():
                        break
                    for i in range(20):
                        verifier._get_cached(f"key_{i}")
            except Exception as e:
                errors.append(e)

        # Start all operations
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=clearer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in threads:
            t.join(timeout=5)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent clear_cache: {errors}"

    def test_clear_cache_removes_all_entries(self):
        """Test clear_cache completely empties the cache."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        # Add many entries
        for i in range(100):
            key = f"key_{i}"
            result = VerificationResult(allowed=True)
            verifier._set_cache(key, result)

        assert len(verifier._cache) == 100

        # Clear
        verifier.clear_cache()

        assert len(verifier._cache) == 0, "Cache should be empty after clear"


class TestConcurrentInvalidateNode:
    """Test concurrent invalidate_node operations."""

    def test_invalidate_node_during_writes(self):
        """ROUND6-001: invalidate_node is thread-safe during concurrent writes."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        node_to_invalidate = "BashCommand"
        other_node = "HttpRequest"
        errors: List[Exception] = []
        stop_flag = threading.Event()

        def write_node_entries(node_type: str) -> None:
            """Write cache entries for a node type."""
            try:
                count = 0
                while not stop_flag.is_set() and count < 300:
                    # node cache key format: node\x00{node_id}\x00{node_type}\x00{agent_id}
                    key = f"node\x00node_{count}\x00{node_type}\x00agent-1"
                    result = VerificationResult(allowed=True)
                    verifier._set_cache(key, result)
                    count += 1
            except Exception as e:
                errors.append(e)

        def invalidate_node() -> None:
            """Continuously invalidate the target node type."""
            try:
                for _ in range(50):
                    if stop_flag.is_set():
                        break
                    verifier.invalidate_node(node_to_invalidate)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        # Start concurrent operations
        threads = [
            threading.Thread(target=write_node_entries, args=(node_to_invalidate,)),
            threading.Thread(target=write_node_entries, args=(other_node,)),
            threading.Thread(target=invalidate_node),
        ]

        for t in threads:
            t.start()

        time.sleep(0.3)
        stop_flag.set()

        for t in threads:
            t.join(timeout=5)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent invalidate_node: {errors}"

        # Other node entries should still exist
        other_node_entries = [
            k for k in verifier._cache.keys() if f"\x00{other_node}\x00" in k
        ]
        assert (
            len(other_node_entries) > 0
        ), "Other node's entries should not be affected by invalidation"

    def test_invalidate_node_returns_correct_count(self):
        """Test invalidate_node returns correct count of removed entries."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        node_type = "TestNode"
        num_entries = 25

        # Add entries for the node type
        for i in range(num_entries):
            key = f"node\x00node_{i}\x00{node_type}\x00agent-1"
            result = VerificationResult(allowed=True)
            verifier._set_cache(key, result)

        # Add entries for other node type
        for i in range(15):
            key = f"node\x00node_{i}\x00OtherNode\x00agent-1"
            result = VerificationResult(allowed=True)
            verifier._set_cache(key, result)

        # Invalidate
        removed = verifier.invalidate_node(node_type)

        assert (
            removed == num_entries
        ), f"Expected {num_entries} entries removed, got {removed}"


class TestHighConcurrencyStress:
    """Stress test with high concurrency to detect race conditions."""

    def test_high_concurrency_mixed_operations(self):
        """ROUND6-001: Stress test with many threads doing mixed operations."""
        config = TrustVerifierConfig(mode="enforcing", cache_enabled=True)
        verifier = TrustVerifier(config=config)

        num_threads = 20
        operations_per_thread = 200
        errors: List[Exception] = []

        def mixed_operations(thread_id: int) -> None:
            """Perform mixed cache operations."""
            try:
                for i in range(operations_per_thread):
                    op = i % 5
                    if op == 0:
                        # Write
                        key = f"t{thread_id}_k{i}"
                        result = VerificationResult(allowed=True)
                        verifier._set_cache(key, result)
                    elif op == 1:
                        # Read own key
                        key = f"t{thread_id}_k{max(0, i-5)}"
                        verifier._get_cached(key)
                    elif op == 2:
                        # Read other thread's key
                        other_thread = (thread_id + 1) % num_threads
                        key = f"t{other_thread}_k{i}"
                        verifier._get_cached(key)
                    elif op == 3:
                        # Invalidate agent (low frequency)
                        if i % 50 == 0:
                            verifier.invalidate_agent(f"agent-{thread_id}")
                    elif op == 4:
                        # Clear cache (very low frequency)
                        if i % 100 == 0 and thread_id == 0:
                            verifier.clear_cache()
            except Exception as e:
                errors.append(e)

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
