"""Unit tests for RuntimeAuditGenerator thread safety (ROUND7-002).

Tests concurrent access to RuntimeAuditGenerator event recording to ensure
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
from kailash.runtime.trust.audit import (
    AuditEvent,
    AuditEventType,
    RuntimeAuditGenerator,
)


class TestAuditGeneratorLockExists:
    """Test that the _lock attribute exists and is correct type."""

    def test_lock_attribute_exists(self):
        """ROUND7-002: Verify _lock attribute exists on RuntimeAuditGenerator."""
        generator = RuntimeAuditGenerator(enabled=True)

        assert hasattr(
            generator, "_lock"
        ), "RuntimeAuditGenerator must have _lock attribute for thread safety"

    def test_lock_is_threading_lock(self):
        """ROUND7-002: Verify _lock is a threading.Lock instance."""
        generator = RuntimeAuditGenerator(enabled=True)

        # Check that _lock is a threading.Lock
        # threading.Lock() returns a _thread.lock object, not threading.Lock
        # We verify it has the acquire/release interface
        assert hasattr(generator._lock, "acquire"), "_lock must have acquire() method"
        assert hasattr(generator._lock, "release"), "_lock must have release() method"
        assert hasattr(
            generator._lock, "__enter__"
        ), "_lock must support context manager protocol"
        assert hasattr(
            generator._lock, "__exit__"
        ), "_lock must support context manager protocol"

    def test_lock_is_reentrant_safe(self):
        """Test that lock can be acquired and released properly."""
        generator = RuntimeAuditGenerator(enabled=True)

        # Test that lock can be acquired and released
        acquired = generator._lock.acquire(blocking=False)
        assert acquired, "Should be able to acquire lock"
        generator._lock.release()

        # Test context manager usage
        with generator._lock:
            pass  # Should not deadlock


class TestConcurrentEventRecording:
    """Test concurrent event recording from multiple threads."""

    def test_concurrent_recording_no_lost_events(self):
        """ROUND7-002: Concurrent event recording from multiple threads doesn't lose events."""
        generator = RuntimeAuditGenerator(enabled=True)

        num_threads = 10
        events_per_thread = 100
        total_expected = num_threads * events_per_thread
        errors: List[Exception] = []
        recorded_ids: List[str] = []
        recorded_ids_lock = threading.Lock()

        def record_events(thread_id: int) -> None:
            """Record multiple events from a single thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(events_per_thread):
                    event = loop.run_until_complete(
                        generator.workflow_started(
                            run_id=f"run-{thread_id}-{i}",
                            workflow_name=f"workflow-{thread_id}-{i}",
                            trust_context=None,
                        )
                    )
                    with recorded_ids_lock:
                        recorded_ids.append(event.event_id)
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Run concurrent recording
        threads = []
        for thread_id in range(num_threads):
            t = threading.Thread(target=record_events, args=(thread_id,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=30)

        # Check no exceptions occurred
        assert len(errors) == 0, f"Errors during concurrent recording: {errors}"

        # Verify all events are present
        actual_count = len(generator.get_events())
        assert actual_count == total_expected, (
            f"Lost events during concurrent recording: "
            f"expected {total_expected}, got {actual_count}"
        )

        # Verify all event IDs are unique
        assert len(recorded_ids) == total_expected, "Not all event IDs were recorded"
        assert len(set(recorded_ids)) == total_expected, "Event IDs are not unique"

    def test_concurrent_recording_preserve_all_event_ids(self):
        """ROUND7-002: All event IDs are preserved during concurrent recording."""
        generator = RuntimeAuditGenerator(enabled=True)

        num_threads = 5
        events_per_thread = 50
        event_ids: Set[str] = set()
        event_ids_lock = threading.Lock()

        def record_events(thread_id: int) -> None:
            """Record events and track their IDs."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(events_per_thread):
                    event = loop.run_until_complete(
                        generator.node_executed(
                            run_id=f"run-t{thread_id}-e{i}",
                            node_id=f"node-{thread_id}-{i}",
                            node_type="TestNode",
                            duration_ms=100,
                            trust_context=None,
                        )
                    )
                    with event_ids_lock:
                        event_ids.add(event.event_id)
            finally:
                loop.close()

        # Run concurrent recording
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(record_events, thread_id)
                for thread_id in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Verify all event IDs are in the generator
        stored_events = generator.get_events()
        stored_ids = {e.event_id for e in stored_events}
        missing_ids = event_ids - stored_ids
        assert (
            len(missing_ids) == 0
        ), f"Missing event IDs after concurrent recording: {missing_ids}"


class TestConcurrentRecordAndRead:
    """Test concurrent event recording and reading."""

    def test_record_while_reading_no_exceptions(self):
        """ROUND7-002: Concurrent recording while reading doesn't raise exceptions."""
        generator = RuntimeAuditGenerator(enabled=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()

        def recorder() -> None:
            """Continuously record events."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 200:
                    loop.run_until_complete(
                        generator.workflow_started(
                            run_id=f"run-{count}",
                            workflow_name=f"workflow-{count}",
                            trust_context=None,
                        )
                    )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def reader() -> None:
            """Continuously read events."""
            try:
                while not stop_flag.is_set():
                    # Read all events
                    events = generator.get_events()
                    assert isinstance(events, list), "get_events should return list"

                    # Verify each event is complete
                    for event in events:
                        assert event.event_id is not None
                        assert event.event_type is not None
                        assert event.timestamp is not None

                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Start concurrent operations
        recorder_threads = [threading.Thread(target=recorder) for _ in range(3)]
        reader_threads = [threading.Thread(target=reader) for _ in range(3)]

        all_threads = recorder_threads + reader_threads
        for t in all_threads:
            t.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in all_threads:
            t.join(timeout=10)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent record/read: {errors}"

    def test_get_events_returns_snapshot(self):
        """ROUND7-002: get_events returns a snapshot, not a live view."""
        generator = RuntimeAuditGenerator(enabled=True)

        # Record some events
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for i in range(10):
            loop.run_until_complete(
                generator.workflow_started(
                    run_id=f"run-{i}",
                    workflow_name=f"workflow-{i}",
                    trust_context=None,
                )
            )

        # Get snapshot
        snapshot = generator.get_events()
        original_count = len(snapshot)

        # Record more events
        for i in range(10, 20):
            loop.run_until_complete(
                generator.workflow_started(
                    run_id=f"run-{i}",
                    workflow_name=f"workflow-{i}",
                    trust_context=None,
                )
            )

        loop.close()

        # Snapshot should be unchanged (it's a copy)
        assert (
            len(snapshot) == original_count
        ), "Snapshot should not be affected by new events"

        # But new get_events should have more
        new_events = generator.get_events()
        assert len(new_events) == 20, "New get_events should include all events"


class TestConcurrentRecordAndClear:
    """Test concurrent event recording and clearing."""

    def test_record_while_clearing_no_exceptions(self):
        """ROUND7-002: Concurrent recording while clearing doesn't raise exceptions."""
        generator = RuntimeAuditGenerator(enabled=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()
        clear_count = [0]
        clear_count_lock = threading.Lock()

        def recorder() -> None:
            """Continuously record events."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 500:
                    loop.run_until_complete(
                        generator.workflow_started(
                            run_id=f"run-{count}",
                            workflow_name=f"workflow-{count}",
                            trust_context=None,
                        )
                    )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def clearer() -> None:
            """Periodically clear events."""
            try:
                while not stop_flag.is_set():
                    generator.clear_events()
                    with clear_count_lock:
                        clear_count[0] += 1
                    time.sleep(0.02)  # Small delay between clears
            except Exception as e:
                errors.append(e)

        # Start concurrent operations
        recorder_threads = [threading.Thread(target=recorder) for _ in range(3)]
        clearer_thread = threading.Thread(target=clearer)

        for t in recorder_threads:
            t.start()
        clearer_thread.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in recorder_threads:
            t.join(timeout=10)
        clearer_thread.join(timeout=10)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent record/clear: {errors}"

        # Verify clear was called multiple times
        assert clear_count[0] > 0, "Clear should have been called"

    def test_clear_events_empties_list(self):
        """ROUND7-002: clear_events empties the event list completely."""
        generator = RuntimeAuditGenerator(enabled=True)

        # Record some events
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for i in range(50):
            loop.run_until_complete(
                generator.workflow_started(
                    run_id=f"run-{i}",
                    workflow_name=f"workflow-{i}",
                    trust_context=None,
                )
            )

        loop.close()

        assert len(generator.get_events()) == 50, "Should have 50 events"

        # Clear
        generator.clear_events()

        assert len(generator.get_events()) == 0, "Events should be empty after clear"


class TestConcurrentRecordAndFilter:
    """Test concurrent event recording and filtering."""

    def test_record_while_filtering_by_type_no_exceptions(self):
        """ROUND7-002: Concurrent recording while filtering by type doesn't raise exceptions."""
        generator = RuntimeAuditGenerator(enabled=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()

        def recorder() -> None:
            """Record various event types."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 200:
                    # Alternate between event types
                    if count % 3 == 0:
                        loop.run_until_complete(
                            generator.workflow_started(
                                run_id=f"run-{count}",
                                workflow_name="workflow",
                                trust_context=None,
                            )
                        )
                    elif count % 3 == 1:
                        loop.run_until_complete(
                            generator.node_executed(
                                run_id=f"run-{count}",
                                node_id=f"node-{count}",
                                node_type="TestNode",
                                duration_ms=100,
                                trust_context=None,
                            )
                        )
                    else:
                        loop.run_until_complete(
                            generator.workflow_completed(
                                run_id=f"run-{count}",
                                duration_ms=500,
                                trust_context=None,
                            )
                        )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def filter_by_type() -> None:
            """Filter events by type."""
            try:
                while not stop_flag.is_set():
                    # Filter by each type
                    for event_type in [
                        AuditEventType.WORKFLOW_START,
                        AuditEventType.NODE_END,
                        AuditEventType.WORKFLOW_END,
                    ]:
                        events = generator.get_events_by_type(event_type)
                        assert isinstance(
                            events, list
                        ), "get_events_by_type should return list"
                        for event in events:
                            assert (
                                event.event_type == event_type
                            ), f"Event type should be {event_type}, got {event.event_type}"
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        # Start concurrent operations
        recorder_threads = [threading.Thread(target=recorder) for _ in range(3)]
        filter_threads = [threading.Thread(target=filter_by_type) for _ in range(3)]

        all_threads = recorder_threads + filter_threads
        for t in all_threads:
            t.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in all_threads:
            t.join(timeout=10)

        # Check no exceptions
        assert len(errors) == 0, f"Errors during concurrent record/filter: {errors}"

    def test_record_while_filtering_by_trace_no_exceptions(self):
        """ROUND7-002: Concurrent recording while filtering by trace doesn't raise exceptions."""
        generator = RuntimeAuditGenerator(enabled=True)

        errors: List[Exception] = []
        stop_flag = threading.Event()
        trace_ids = [f"trace-{i}" for i in range(5)]

        def recorder() -> None:
            """Record events with various trace IDs."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                count = 0
                while not stop_flag.is_set() and count < 200:
                    trace_id = trace_ids[count % len(trace_ids)]
                    loop.run_until_complete(
                        generator.workflow_started(
                            run_id=trace_id,  # Use trace_id as run_id for simplicity
                            workflow_name=f"workflow-{count}",
                            trust_context=None,
                        )
                    )
                    count += 1
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        def filter_by_trace() -> None:
            """Filter events by trace ID."""
            try:
                while not stop_flag.is_set():
                    for trace_id in trace_ids:
                        events = generator.get_events_by_trace(trace_id)
                        assert isinstance(
                            events, list
                        ), "get_events_by_trace should return list"
                        for event in events:
                            assert (
                                event.trace_id == trace_id
                            ), f"Event trace should be {trace_id}, got {event.trace_id}"
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        # Start concurrent operations
        recorder_threads = [threading.Thread(target=recorder) for _ in range(3)]
        filter_threads = [threading.Thread(target=filter_by_trace) for _ in range(3)]

        all_threads = recorder_threads + filter_threads
        for t in all_threads:
            t.start()

        time.sleep(0.5)
        stop_flag.set()

        for t in all_threads:
            t.join(timeout=10)

        # Check no exceptions
        assert (
            len(errors) == 0
        ), f"Errors during concurrent record/filter by trace: {errors}"


class TestHighConcurrencyStress:
    """Stress test with high concurrency to detect race conditions."""

    def test_high_concurrency_mixed_operations(self):
        """ROUND7-002: Stress test with many threads doing mixed operations."""
        generator = RuntimeAuditGenerator(enabled=True)

        num_threads = 20
        operations_per_thread = 100
        errors: List[Exception] = []

        def mixed_operations(thread_id: int) -> None:
            """Perform mixed audit operations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(operations_per_thread):
                    op = i % 7
                    if op == 0:
                        # Record workflow start
                        loop.run_until_complete(
                            generator.workflow_started(
                                run_id=f"stress-{thread_id}-{i}",
                                workflow_name="stress-workflow",
                                trust_context=None,
                            )
                        )
                    elif op == 1:
                        # Record node executed
                        loop.run_until_complete(
                            generator.node_executed(
                                run_id=f"stress-{thread_id}-{i}",
                                node_id=f"node-{i}",
                                node_type="StressNode",
                                duration_ms=50,
                                trust_context=None,
                            )
                        )
                    elif op == 2:
                        # Record workflow completed
                        loop.run_until_complete(
                            generator.workflow_completed(
                                run_id=f"stress-{thread_id}-{i}",
                                duration_ms=200,
                                trust_context=None,
                            )
                        )
                    elif op == 3:
                        # Get all events
                        generator.get_events()
                    elif op == 4:
                        # Get events by type
                        generator.get_events_by_type(AuditEventType.WORKFLOW_START)
                    elif op == 5:
                        # Get events by trace
                        generator.get_events_by_trace(f"stress-{thread_id}-0")
                    elif op == 6:
                        # Clear events (low frequency)
                        if i % 50 == 0 and thread_id == 0:
                            generator.clear_events()
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

    def test_extreme_concurrency_no_crashes(self):
        """ROUND7-002: Extreme concurrency doesn't cause crashes or hangs."""
        generator = RuntimeAuditGenerator(enabled=True)

        num_threads = 25
        operations_per_thread = 50
        errors: List[Exception] = []
        completed_threads = [0]
        completed_lock = threading.Lock()

        def rapid_operations(thread_id: int) -> None:
            """Perform rapid audit operations."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(operations_per_thread):
                    # Rapid recording
                    loop.run_until_complete(
                        generator.workflow_started(
                            run_id=f"extreme-{thread_id}-{i}",
                            workflow_name="extreme-workflow",
                            trust_context=None,
                        )
                    )
                    # Rapid reading
                    generator.get_events()

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

    def test_concurrent_recording_all_event_types(self):
        """ROUND7-002: All event recording methods are thread-safe."""
        generator = RuntimeAuditGenerator(enabled=True)

        num_threads = 10
        errors: List[Exception] = []

        def record_all_types(thread_id: int) -> None:
            """Record all types of events."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for i in range(20):
                    # Workflow events
                    loop.run_until_complete(
                        generator.workflow_started(
                            run_id=f"run-{thread_id}-{i}",
                            workflow_name="workflow",
                            trust_context=None,
                        )
                    )
                    loop.run_until_complete(
                        generator.workflow_completed(
                            run_id=f"run-{thread_id}-{i}",
                            duration_ms=100,
                            trust_context=None,
                        )
                    )
                    loop.run_until_complete(
                        generator.workflow_failed(
                            run_id=f"run-{thread_id}-{i}-fail",
                            error="Test error",
                            duration_ms=50,
                            trust_context=None,
                        )
                    )

                    # Node events
                    loop.run_until_complete(
                        generator.node_executed(
                            run_id=f"run-{thread_id}-{i}",
                            node_id=f"node-{i}",
                            node_type="TestNode",
                            duration_ms=10,
                            trust_context=None,
                        )
                    )
                    loop.run_until_complete(
                        generator.node_failed(
                            run_id=f"run-{thread_id}-{i}",
                            node_id=f"node-{i}-fail",
                            node_type="FailNode",
                            error="Node error",
                            duration_ms=5,
                            trust_context=None,
                        )
                    )

                    # Trust events
                    loop.run_until_complete(
                        generator.trust_verification_performed(
                            run_id=f"run-{thread_id}-{i}",
                            target="workflow:test",
                            allowed=True,
                            reason="Allowed",
                            trust_context=None,
                        )
                    )

                    # Resource events
                    loop.run_until_complete(
                        generator.resource_accessed(
                            run_id=f"run-{thread_id}-{i}",
                            resource="/path/to/resource",
                            action="read",
                            result="success",
                            trust_context=None,
                        )
                    )
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        # Run concurrent recording of all types
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(record_all_types, tid) for tid in range(num_threads)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    errors.append(e)

        # Check no exceptions
        assert (
            len(errors) == 0
        ), f"Errors during all event types recording: {errors[:5]}"

        # Verify events were recorded
        events = generator.get_events()
        assert len(events) > 0, "Events should have been recorded"

        # Verify multiple event types are present
        event_types = {e.event_type for e in events}
        expected_types = {
            AuditEventType.WORKFLOW_START,
            AuditEventType.WORKFLOW_END,
            AuditEventType.WORKFLOW_ERROR,
            AuditEventType.NODE_END,
            AuditEventType.NODE_ERROR,
            AuditEventType.TRUST_VERIFICATION,
            AuditEventType.RESOURCE_ACCESS,
        }
        assert (
            event_types == expected_types
        ), f"All event types should be present. Missing: {expected_types - event_types}"
